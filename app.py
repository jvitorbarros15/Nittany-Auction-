from flask import Flask, flash, render_template, request, redirect, session
import sqlite3
import hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"


def init_db():
    conn = sqlite3.connect("nittanyauction.db")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS listings (
            listing_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_email      TEXT NOT NULL,
            title             TEXT NOT NULL,
            description       TEXT,
            condition         TEXT,
            category_id       INTEGER,
            reserve_price     REAL NOT NULL,
            auction_stop_time DATETIME NOT NULL,
            status            TEXT DEFAULT 'active',
            removal_reason    TEXT,
            max_bids          INTEGER DEFAULT 0,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS bids (
            bid_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id    INTEGER NOT NULL,
            bidder_email  TEXT NOT NULL,
            bid_amount    REAL NOT NULL,
            bid_time      DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS bidders (
            email         TEXT PRIMARY KEY,
            first_name    TEXT,
            last_name     TEXT,
            street        TEXT,
            city          TEXT,
            state         TEXT,
            zipcode       TEXT,
            phone_number  TEXT,
            major         TEXT,
            age           INTEGER,
            annual_income REAL
        );
        CREATE TABLE IF NOT EXISTS credit_cards (
            card_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            bidder_email    TEXT NOT NULL,
            card_type       TEXT NOT NULL,
            card_number     TEXT NOT NULL,
            expiration_date TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS questions (
            question_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id    INTEGER NOT NULL,
            bidder_email  TEXT NOT NULL,
            question_text TEXT NOT NULL,
            asked_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id       INTEGER NOT NULL UNIQUE,
            bidder_email     TEXT NOT NULL,
            amount           REAL NOT NULL,
            transaction_date DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ratings (
            rating_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id   INTEGER NOT NULL UNIQUE,
            bidder_email TEXT NOT NULL,
            seller_email TEXT NOT NULL,
            stars        INTEGER NOT NULL,
            rated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS seller_applications (
            application_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bidder_email   TEXT NOT NULL,
            submitted_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            status         TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS helpdesk_requests (
            request_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_email  TEXT NOT NULL,
            request_type     TEXT NOT NULL DEFAULT 'add_category',
            category_name    TEXT,
            details          TEXT,
            assigned_to      TEXT NOT NULL DEFAULT 'helpdeskteam@lsu.edu',
            status           TEXT NOT NULL DEFAULT 'unassigned',
            submitted_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at     DATETIME
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            watchlist_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            bidder_email  TEXT NOT NULL,
            listing_id    INTEGER NOT NULL,
            added_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bidder_email, listing_id)
        );
    """)

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()}
    if "promoted" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN promoted INTEGER DEFAULT 0")
    if "promoted_at" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN promoted_at DATETIME")
    if "promotion_fee" not in existing_cols:
        conn.execute("ALTER TABLE listings ADD COLUMN promotion_fee REAL")
    conn.commit()
    conn.close()


init_db()


@app.route("/")
def homepage():
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        # Live auctions carousel — most bids, active
        carousel_listings = conn.execute("""
            SELECT l.listing_id, l.title, l.seller_email, l.reserve_price,
                   l.auction_stop_time, l.promoted,
                   c.category_name, c.parent_category,
                   (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                   (SELECT COUNT(*)       FROM bids WHERE listing_id = l.listing_id) AS bid_count
            FROM listings l
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE l.status = 'active' AND l.auction_stop_time > ?
            ORDER BY bid_count DESC, l.promoted DESC
            LIMIT 10
        """, (now,)).fetchall()

        # Featured grid — promoted first, then highest current bid, limit 6
        featured_listings = conn.execute("""
            SELECT l.listing_id, l.title, l.seller_email, l.reserve_price,
                   l.auction_stop_time, l.condition, l.promoted,
                   c.category_name,
                   (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                   (SELECT COUNT(*)       FROM bids WHERE listing_id = l.listing_id) AS bid_count
            FROM listings l
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE l.status = 'active' AND l.auction_stop_time > ?
            ORDER BY l.promoted DESC, current_bid DESC, l.reserve_price DESC
            LIMIT 6
        """, (now,)).fetchall()

        # Seller spotlight — sellers with ratings, ordered by avg stars
        top_sellers = conn.execute("""
            SELECT r.seller_email,
                   ROUND(AVG(r.stars), 1) AS avg_stars,
                   COUNT(r.rating_id)     AS rating_count,
                   (SELECT COUNT(*) FROM listings
                    WHERE seller_email = r.seller_email AND status = 'active'
                      AND auction_stop_time > ?) AS active_count
            FROM ratings r
            GROUP BY r.seller_email
            ORDER BY avg_stars DESC, rating_count DESC
            LIMIT 4
        """, (now,)).fetchall()

        # Stats
        live_count = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE status='active' AND auction_stop_time > ?", (now,)
        ).fetchone()[0]
        seller_count = conn.execute(
            "SELECT COUNT(DISTINCT seller_email) FROM listings WHERE status='active' AND auction_stop_time > ?", (now,)
        ).fetchone()[0]
        bid_count = conn.execute("SELECT COUNT(*) FROM bids").fetchone()[0]

    return render_template("homepage.html",
                           carousel_listings=carousel_listings,
                           featured_listings=featured_listings,
                           top_sellers=top_sellers,
                           live_count=live_count,
                           seller_count=seller_count,
                           bid_count=bid_count)

@app.route("/login", methods=["GET", "POST"])
def login():
    # When user submits the form
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Connect to SQLite database
        connection = sqlite3.connect("nittanyauction.db")
        cursor = connection.cursor()
        cursor.execute(
            "SELECT email, password_hash, salt, role FROM auth_users WHERE email = ?", (email,)) # Look for a user with this email 
        user = cursor.fetchone()  
        connection.close()  

        if user:
            stored_password_hash = user[1]
            salt = user[2]
            role = user[3].lower()

            # This checks if the password matches the hash stored in the database and gets the role from the database (seller, buyer, helpdesk)
            hashed_input = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

            if stored_password_hash == hashed_input:
                session["email"] = user[0]
                session["role"]  = role
                if role == "seller":
                    return redirect("/seller")
                elif role == "buyer":
                    return redirect("/bidder")
                elif role == "helpdesk":
                    return redirect("/helpdesk")
        
        flash("Invalid email or password.", "error")
        return redirect("/login")

    return render_template("login.html")

def role_required(role):
    if session.get("role") != role:
        flash(f"Please log in as {role} to access that page.", "error")
        return redirect("/login")
    return None

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect("/login")


@app.route("/seller")
def seller():
    guard = role_required("seller")
    if guard:
        return guard
    return render_template("seller_welcome.html", email=session["email"])

@app.route("/seller/listings")
def seller_listings():
    guard = role_required("seller")
    if guard:
        return guard

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT l.*,
                   c.category_name AS category,
                   (SELECT COUNT(*) FROM bids WHERE listing_id = l.listing_id) AS bid_count
            FROM listings l
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE l.seller_email = ?
        """, (session["email"],))
        rows = cursor.fetchall()

    active   = [r for r in rows if r["status"] == "active"]
    inactive = [r for r in rows if r["status"] == "inactive"]
    sold     = [r for r in rows if r["status"] == "sold"]

    return render_template("seller_listings.html",
                           active=active,
                           inactive=inactive,
                           sold=sold,
                           email=session["email"])

@app.route("/seller/listings/new", methods=["GET", "POST"])
def seller_listing_new():
    guard = role_required("seller")
    if guard:
        return guard

    if request.method == "POST":
        title             = request.form["title"]
        description       = request.form["description"]
        condition         = request.form["condition"]
        category_id       = int(request.form["category_id"])
        reserve_price     = float(request.form["reserve_price"])
        auction_stop_time = request.form["auction_stop_time"]
        seller_email      = session["email"]

        with sqlite3.connect("nittanyauction.db") as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO listings 
                    (seller_email, title, description, condition, category_id, reserve_price, auction_stop_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """, (seller_email, title, description, condition, category_id, reserve_price, auction_stop_time))
            conn.commit()

        flash("Listing created successfully.", "success")
        return redirect("/seller/listings")

    # Fetch categories to populate the dropdown
    with sqlite3.connect("nittanyauction.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT category_id, category_name FROM categories")
        categories = [{"category_id": row[0], "category_name": row[1]} for row in cursor.fetchall()]

    return render_template("seller_listing_new.html",
                           categories=categories,
                           email=session["email"])

@app.route("/seller/listings/<int:listing_id>/remove", methods=["GET", "POST"])
def seller_listing_remove(listing_id):
    guard = role_required("seller")
    if guard:
        return guard

    connection = sqlite3.connect("nittanyauction.db")
    connection.row_factory = sqlite3.Row  # this lets us use listing['title'] instead of listing[0]
    cursor = connection.cursor()

    # get the listing so we can show the title on the page
    cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
    listing = cursor.fetchone()
    

    if not listing or listing["seller_email"] != session["email"]:
        connection.close()
        flash("Listing not found or you do not have permission to remove it.", "error")
        return redirect("/seller/listings")

    cursor.execute("SELECT COUNT(*) FROM bids WHERE listing_id = ?", (listing_id,))
    bid_count = cursor.fetchone()[0]

    if request.method == "POST":
        removal_reason = request.form["removal_reason"]

        # mark as inactive instead of deleting it so we keep the history
        cursor.execute("""
            UPDATE listings 
            SET status = 'inactive', removal_reason = ?
            WHERE listing_id = ?
        """, (removal_reason, listing_id))
        connection.commit()
        connection.close()

        flash("Listing removed successfully.", "success")
        return redirect("/seller/listings")

    connection.close()

    return render_template("seller_listing_remove.html",
                           listing=listing,
                           bid_count=bid_count,
                           email=session["email"])

@app.route("/seller/listings/<int:listing_id>/edit", methods=["GET", "POST"])
def seller_listing_edit(listing_id):
    guard = role_required("seller")
    if guard:
        return guard

    connection = sqlite3.connect("nittanyauction.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM listings WHERE listing_id = ?", (listing_id,))
    listing = cursor.fetchone()

    # make sure the listing exists and belongs to this seller
    if not listing or listing["seller_email"] != session["email"]:
        connection.close()
        flash("Listing not found or you do not have permission to edit it.", "error")
        return redirect("/seller/listings")

    cursor.execute("SELECT COUNT(*) FROM bids WHERE listing_id = ?", (listing_id,))
    bid_count = cursor.fetchone()[0]

    if bid_count > 0:
        connection.close()
        return render_template("seller_listing_edit.html",
                               editable=False,
                               block_reason="This listing already has bids and cannot be edited.",
                               listing=None,
                               categories=[],
                               email=session["email"])

    if request.method == "POST":
        title             = request.form["title"]
        description       = request.form["description"]
        condition         = request.form["condition"]
        category_id       = int(request.form["category_id"])
        reserve_price     = float(request.form["reserve_price"])
        auction_stop_time = request.form["auction_stop_time"]

        cursor.execute("""
            UPDATE listings
            SET title = ?, description = ?, condition = ?, category_id = ?,
                reserve_price = ?, auction_stop_time = ?
            WHERE listing_id = ?
        """, (title, description, condition, category_id, reserve_price, auction_stop_time, listing_id))
        connection.commit()
        connection.close()

        flash("Listing updated successfully.", "success")
        return redirect("/seller/listings")

    # categories for the dropdown
    cursor.execute("SELECT category_id, category_name FROM categories")
    categories = [{"category_id": row[0], "category_name": row[1]} for row in cursor.fetchall()]
    connection.close()

    return render_template("seller_listing_edit.html",
                           editable=True,
                           block_reason=None,
                           listing=listing,
                           categories=categories,
                           email=session["email"])

@app.route("/buyer")
def buyer():
    return redirect("/bidder")


# Bidder

@app.route("/bidder")
def bidder():
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        won_auctions = conn.execute("""
            SELECT l.listing_id, l.title,
                   (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS winning_bid
            FROM listings l
            WHERE l.status = 'active' AND l.auction_stop_time < ?
              AND NOT EXISTS (SELECT 1 FROM transactions WHERE listing_id = l.listing_id)
              AND (SELECT bidder_email FROM bids
                   WHERE listing_id = l.listing_id
                   ORDER BY bid_amount DESC LIMIT 1) = ?
        """, (now, email)).fetchall()

        pending_ratings = conn.execute("""
            SELECT l.listing_id, l.title, t.amount
            FROM transactions t
            JOIN listings l ON t.listing_id = l.listing_id
            WHERE t.bidder_email = ?
              AND NOT EXISTS (
                  SELECT 1 FROM ratings r
                  WHERE r.listing_id = l.listing_id AND r.bidder_email = ?
              )
        """, (email, email)).fetchall()

    return render_template("bidder_welcome.html",
                           email=email,
                           won_auctions=won_auctions,
                           pending_ratings=pending_ratings)


@app.route("/bidder/profile", methods=["GET", "POST"])
def bidder_profile():
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]

    if request.method == "POST":
        first_name    = request.form.get("first_name", "")
        last_name     = request.form.get("last_name", "")
        street        = request.form.get("street", "")
        city          = request.form.get("city", "")
        state         = request.form.get("state", "")
        zipcode       = request.form.get("zipcode", "")
        phone_number  = request.form.get("phone_number", "")
        major         = request.form.get("major", "")
        age_str       = request.form.get("age", "").strip()
        income_str    = request.form.get("annual_income", "").strip()
        age           = int(age_str) if age_str else None
        annual_income = float(income_str) if income_str else None

        with sqlite3.connect("nittanyauction.db") as conn:
            conn.execute("""
                INSERT INTO bidders (email, first_name, last_name, street, city, state, zipcode,
                                     phone_number, major, age, annual_income)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    first_name=excluded.first_name, last_name=excluded.last_name,
                    street=excluded.street, city=excluded.city, state=excluded.state,
                    zipcode=excluded.zipcode, phone_number=excluded.phone_number,
                    major=excluded.major, age=excluded.age, annual_income=excluded.annual_income
            """, (email, first_name, last_name, street, city, state, zipcode,
                  phone_number, major, age, annual_income))

        flash("Profile updated successfully.", "success")
        return redirect("/bidder/profile")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        profile = conn.execute("SELECT * FROM bidders WHERE email = ?", (email,)).fetchone()

    return render_template("bidder_profile.html", email=email, profile=profile)


@app.route("/bidder/cards", methods=["GET", "POST"])
def bidder_cards():
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            with sqlite3.connect("nittanyauction.db") as conn:
                conn.execute("""
                    INSERT INTO credit_cards (bidder_email, card_type, card_number, expiration_date)
                    VALUES (?, ?, ?, ?)
                """, (email, request.form["card_type"], request.form["card_number"],
                      request.form["expiration_date"]))
            flash("Card added.", "success")

        elif action == "remove":
            with sqlite3.connect("nittanyauction.db") as conn:
                conn.execute(
                    "DELETE FROM credit_cards WHERE card_id = ? AND bidder_email = ?",
                    (int(request.form["card_id"]), email)
                )
            flash("Card removed.", "success")

        return redirect("/bidder/cards")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        cards = conn.execute(
            "SELECT * FROM credit_cards WHERE bidder_email = ?", (email,)
        ).fetchall()

    return render_template("bidder_cards.html", email=email, cards=cards)


@app.route("/bidder/listings")
def bidder_listings():
    guard = role_required("buyer")
    if guard:
        return guard

    category_id     = request.args.get("category_id", type=int)
    parent_category = request.args.get("parent_category", "").strip()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        all_cats = conn.execute(
            "SELECT * FROM categories ORDER BY parent_category, category_name"
        ).fetchall()

        # Build {parent: [cat, ...]} for the template dropdown
        grouped_categories = {}
        for cat in all_cats:
            parent = cat["parent_category"] or "Other"
            grouped_categories.setdefault(parent, []).append(dict(cat))

        base_select = """
            SELECT l.*, c.category_name, c.parent_category,
                   (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                   (SELECT COUNT(*) FROM bids WHERE listing_id = l.listing_id) AS bid_count
            FROM listings l
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE l.status = 'active' AND l.auction_stop_time > ?
        """

        if category_id:
            listings = conn.execute(
                base_select + " AND l.category_id = ? ORDER BY l.promoted DESC, l.auction_stop_time ASC",
                (now, category_id)
            ).fetchall()
        elif parent_category:
            listings = conn.execute(
                base_select + " AND c.parent_category = ? ORDER BY l.promoted DESC, l.auction_stop_time ASC",
                (now, parent_category)
            ).fetchall()
        else:
            listings = conn.execute(
                base_select + " ORDER BY l.promoted DESC, l.auction_stop_time ASC",
                (now,)
            ).fetchall()

    return render_template("bidder_listings.html",
                           email=session["email"],
                           listings=listings,
                           grouped_categories=grouped_categories,
                           selected_category=category_id,
                           selected_parent=parent_category)


@app.route("/bidder/listings/<int:listing_id>")
def bidder_listing_view(listing_id):
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        listing = conn.execute("""
            SELECT l.*, c.category_name
            FROM listings l
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE l.listing_id = ? AND l.status = 'active'
        """, (listing_id,)).fetchone()

        if not listing:
            flash("Listing not found or no longer available.", "error")
            return redirect("/bidder/listings")

        top_bid = conn.execute(
            "SELECT MAX(bid_amount) FROM bids WHERE listing_id = ?", (listing_id,)
        ).fetchone()[0]

        my_bid = conn.execute(
            "SELECT MAX(bid_amount) FROM bids WHERE listing_id = ? AND bidder_email = ?",
            (listing_id, email)
        ).fetchone()[0]

        winner_row = conn.execute(
            "SELECT bidder_email FROM bids WHERE listing_id = ? ORDER BY bid_amount DESC LIMIT 1",
            (listing_id,)
        ).fetchone()

        auction_ended = listing["auction_stop_time"] < now
        is_winner = bool(winner_row and winner_row["bidder_email"] == email)

        transaction = conn.execute(
            "SELECT 1 FROM transactions WHERE listing_id = ? AND bidder_email = ?",
            (listing_id, email)
        ).fetchone()

        rated = conn.execute(
            "SELECT 1 FROM ratings WHERE listing_id = ? AND bidder_email = ?",
            (listing_id, email)
        ).fetchone()

        my_questions = conn.execute(
            "SELECT * FROM questions WHERE listing_id = ? AND bidder_email = ? ORDER BY asked_at ASC",
            (listing_id, email)
        ).fetchall()

        in_watchlist = conn.execute(
            "SELECT 1 FROM watchlist WHERE bidder_email = ? AND listing_id = ?",
            (email, listing_id)
        ).fetchone() is not None

    return render_template("bidder_listing_view.html",
                           email=email,
                           listing=listing,
                           top_bid=top_bid,
                           my_bid=my_bid,
                           is_winner=is_winner,
                           auction_ended=auction_ended,
                           transaction=transaction,
                           rated=rated,
                           my_questions=my_questions,
                           in_watchlist=in_watchlist)


@app.route("/bidder/listings/<int:listing_id>/bid", methods=["GET", "POST"])
def bidder_bid(listing_id):
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        listing = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ? AND status = 'active'", (listing_id,)
        ).fetchone()

        if not listing or listing["auction_stop_time"] < now:
            flash("This auction is not available for bidding.", "error")
            return redirect(f"/bidder/listings/{listing_id}")

        top_bid = conn.execute(
            "SELECT MAX(bid_amount) FROM bids WHERE listing_id = ?", (listing_id,)
        ).fetchone()[0]

        if request.method == "POST":
            try:
                bid_amount = float(request.form["bid_amount"])
            except (ValueError, KeyError):
                flash("Invalid bid amount.", "error")
                return redirect(f"/bidder/listings/{listing_id}/bid")

            if bid_amount < listing["reserve_price"]:
                flash(f"Bid must be at least the reserve price of ${listing['reserve_price']:.2f}.", "error")
                return redirect(f"/bidder/listings/{listing_id}/bid")

            if top_bid is not None and bid_amount <= top_bid:
                flash(f"Bid must be higher than the current highest bid of ${top_bid:.2f}.", "error")
                return redirect(f"/bidder/listings/{listing_id}/bid")

            conn.execute(
                "INSERT INTO bids (listing_id, bidder_email, bid_amount) VALUES (?, ?, ?)",
                (listing_id, email, bid_amount)
            )
            flash(f"Bid of ${bid_amount:.2f} placed successfully!", "success")
            return redirect(f"/bidder/listings/{listing_id}")

        min_bid = max(listing["reserve_price"], (top_bid or 0) + 0.01)

    return render_template("bidder_bid.html",
                           email=email,
                           listing=listing,
                           top_bid=top_bid,
                           min_bid=min_bid)


@app.route("/bidder/listings/<int:listing_id>/question", methods=["GET", "POST"])
def bidder_question(listing_id):
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        listing = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ? AND status = 'active'", (listing_id,)
        ).fetchone()

        if not listing:
            flash("Listing not found.", "error")
            return redirect("/bidder/listings")

        if request.method == "POST":
            question_text = request.form.get("question_text", "").strip()
            if not question_text:
                flash("Please enter a question.", "error")
                return redirect(f"/bidder/listings/{listing_id}/question")

            conn.execute(
                "INSERT INTO questions (listing_id, bidder_email, question_text) VALUES (?, ?, ?)",
                (listing_id, email, question_text)
            )
            flash("Your question has been sent to the seller.", "success")
            return redirect(f"/bidder/listings/{listing_id}")

    return render_template("bidder_question.html", email=email, listing=listing)


@app.route("/bidder/listings/<int:listing_id>/pay", methods=["GET", "POST"])
def bidder_pay(listing_id):
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        listing = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ? AND status = 'active'", (listing_id,)
        ).fetchone()

        if not listing or listing["auction_stop_time"] >= now:
            flash("This auction has not ended yet.", "error")
            return redirect("/bidder")

        winner_row = conn.execute(
            "SELECT bidder_email, MAX(bid_amount) AS amount FROM bids WHERE listing_id = ?",
            (listing_id,)
        ).fetchone()

        if not winner_row or winner_row["bidder_email"] != email:
            flash("You did not win this auction.", "error")
            return redirect("/bidder")

        if conn.execute("SELECT 1 FROM transactions WHERE listing_id = ?", (listing_id,)).fetchone():
            flash("This auction has already been paid.", "error")
            return redirect("/bidder")

        cards = conn.execute(
            "SELECT * FROM credit_cards WHERE bidder_email = ?", (email,)
        ).fetchall()

        if request.method == "POST":
            if not request.form.get("card_id"):
                flash("Please select a payment card.", "error")
                return redirect(f"/bidder/listings/{listing_id}/pay")

            amount = winner_row["amount"]
            conn.execute(
                "INSERT INTO transactions (listing_id, bidder_email, amount) VALUES (?, ?, ?)",
                (listing_id, email, amount)
            )
            conn.execute("UPDATE listings SET status = 'sold' WHERE listing_id = ?", (listing_id,))
            flash(f"Payment of ${amount:.2f} completed. Thank you!", "success")
            return redirect("/bidder")

    return render_template("bidder_payment.html",
                           email=email,
                           listing=listing,
                           winning_amount=winner_row["amount"],
                           cards=cards)


@app.route("/bidder/listings/<int:listing_id>/rate", methods=["GET", "POST"])
def bidder_rate(listing_id):
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row

        transaction = conn.execute(
            "SELECT * FROM transactions WHERE listing_id = ? AND bidder_email = ?",
            (listing_id, email)
        ).fetchone()

        if not transaction:
            flash("You can only rate sellers after completing a purchase.", "error")
            return redirect("/bidder")

        if conn.execute(
            "SELECT 1 FROM ratings WHERE listing_id = ? AND bidder_email = ?",
            (listing_id, email)
        ).fetchone():
            flash("You have already rated this seller.", "error")
            return redirect("/bidder")

        listing = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ?", (listing_id,)
        ).fetchone()

        if request.method == "POST":
            try:
                stars = int(request.form["stars"])
                if not 1 <= stars <= 5:
                    raise ValueError
            except (ValueError, KeyError):
                flash("Please select a rating between 1 and 5.", "error")
                return redirect(f"/bidder/listings/{listing_id}/rate")

            conn.execute(
                "INSERT INTO ratings (listing_id, bidder_email, seller_email, stars) VALUES (?, ?, ?, ?)",
                (listing_id, email, listing["seller_email"], stars)
            )
            flash("Thank you for rating the seller!", "success")
            return redirect("/bidder")

    return render_template("bidder_rate_seller.html",
                           email=email,
                           listing=listing,
                           transaction=transaction)


@app.route("/bidder/apply-seller", methods=["GET", "POST"])
def bidder_apply_seller():
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM seller_applications WHERE bidder_email = ? AND status = 'pending'",
            (email,)
        ).fetchone()

        if request.method == "POST":
            if existing:
                flash("You already have a pending application.", "error")
                return redirect("/bidder/apply-seller")
            conn.execute(
                "INSERT INTO seller_applications (bidder_email) VALUES (?)", (email,)
            )
            flash("Your application has been submitted to the HelpDesk for review.", "success")
            return redirect("/bidder")

    return render_template("bidder_seller_application.html", email=email, existing=existing)


@app.route("/helpdesk")
def helpdesk():
    guard = role_required("helpdesk")
    if guard:
        return guard

    email = session["email"]
    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        unassigned_count = conn.execute(
            "SELECT COUNT(*) FROM helpdesk_requests WHERE status = 'unassigned'"
        ).fetchone()[0]
        mine_count = conn.execute(
            "SELECT COUNT(*) FROM helpdesk_requests WHERE assigned_to = ? AND status = 'assigned'",
            (email,)
        ).fetchone()[0]

    return render_template("helpdesk_welcome.html",
                           email=email,
                           unassigned_count=unassigned_count,
                           mine_count=mine_count)


@app.route("/helpdesk/requests")
def helpdesk_requests():
    guard = role_required("helpdesk")
    if guard:
        return guard

    email = session["email"]
    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        unassigned = conn.execute(
            "SELECT * FROM helpdesk_requests WHERE status = 'unassigned' ORDER BY submitted_at ASC"
        ).fetchall()
        mine = conn.execute(
            "SELECT * FROM helpdesk_requests WHERE assigned_to = ? AND status = 'assigned' ORDER BY submitted_at ASC",
            (email,)
        ).fetchall()
        completed = conn.execute(
            "SELECT * FROM helpdesk_requests WHERE assigned_to = ? AND status = 'completed' ORDER BY completed_at DESC LIMIT 20",
            (email,)
        ).fetchall()

    return render_template("helpdesk_requests.html",
                           email=email,
                           unassigned=unassigned,
                           mine=mine,
                           completed=completed)


@app.route("/helpdesk/requests/<int:request_id>/claim", methods=["POST"])
def helpdesk_claim(request_id):
    guard = role_required("helpdesk")
    if guard:
        return guard

    email = session["email"]
    with sqlite3.connect("nittanyauction.db") as conn:
        row = conn.execute(
            "SELECT status FROM helpdesk_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if not row or row[0] != "unassigned":
            flash("Request is no longer available to claim.", "error")
            return redirect("/helpdesk/requests")
        conn.execute(
            "UPDATE helpdesk_requests SET assigned_to = ?, status = 'assigned' WHERE request_id = ?",
            (email, request_id)
        )
    flash("Request claimed.", "success")
    return redirect("/helpdesk/requests")


@app.route("/helpdesk/requests/<int:request_id>/complete", methods=["POST"])
def helpdesk_complete(request_id):
    guard = role_required("helpdesk")
    if guard:
        return guard

    email = session["email"]
    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        req = conn.execute(
            "SELECT * FROM helpdesk_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        if not req or req["assigned_to"] != email or req["status"] != "assigned":
            flash("You cannot complete this request.", "error")
            return redirect("/helpdesk/requests")

        if req["request_type"] == "add_category" and req["category_name"]:
            existing = conn.execute(
                "SELECT category_id FROM categories WHERE LOWER(category_name) = LOWER(?)",
                (req["category_name"],)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO categories (category_name) VALUES (?)",
                    (req["category_name"],)
                )

        conn.execute(
            "UPDATE helpdesk_requests SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE request_id = ?",
            (request_id,)
        )

    flash("Request marked as completed.", "success")
    return redirect("/helpdesk/requests")


@app.route("/seller/category-request", methods=["GET", "POST"])
def seller_category_request():
    guard = role_required("seller")
    if guard:
        return guard

    email = session["email"]

    if request.method == "POST":
        category_name = request.form.get("category_name", "").strip()
        details       = request.form.get("details", "").strip()
        if not category_name:
            flash("Please enter a category name.", "error")
            return redirect("/seller/category-request")

        with sqlite3.connect("nittanyauction.db") as conn:
            conn.execute("""
                INSERT INTO helpdesk_requests (requester_email, request_type, category_name, details)
                VALUES (?, 'add_category', ?, ?)
            """, (email, category_name, details))

        flash("Your request has been submitted to HelpDesk.", "success")
        return redirect("/seller/category-request")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        my_requests = conn.execute("""
            SELECT * FROM helpdesk_requests
            WHERE requester_email = ? AND request_type = 'add_category'
            ORDER BY submitted_at DESC
        """, (email,)).fetchall()

    return render_template("seller_category_request.html",
                           email=email, my_requests=my_requests)


@app.route("/seller/listings/<int:listing_id>/promote", methods=["GET", "POST"])
def seller_listing_promote(listing_id):
    guard = role_required("seller")
    if guard:
        return guard

    email = session["email"]
    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        listing = conn.execute(
            "SELECT * FROM listings WHERE listing_id = ?", (listing_id,)
        ).fetchone()

        if not listing or listing["seller_email"] != email:
            flash("Listing not found.", "error")
            return redirect("/seller/listings")

        if listing["status"] != "active":
            flash("Only active listings can be promoted.", "error")
            return redirect("/seller/listings")

        if listing["promoted"]:
            flash("This listing is already promoted.", "error")
            return redirect("/seller/listings")

        fee = round(listing["reserve_price"] * 0.05, 2)

        if request.method == "POST":
            conn.execute("""
                UPDATE listings
                SET promoted = 1, promoted_at = CURRENT_TIMESTAMP, promotion_fee = ?
                WHERE listing_id = ?
            """, (fee, listing_id))
            flash(f"Listing promoted! Fee of ${fee:.2f} recorded.", "success")
            return redirect("/seller/listings")

    return render_template("seller_listing_promote.html",
                           email=email, listing=listing, fee=fee)


@app.route("/bidder/watchlist", methods=["GET", "POST"])
def bidder_watchlist():
    guard = role_required("buyer")
    if guard:
        return guard

    email = session["email"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if request.method == "POST":
        action = request.form.get("action")
        listing_id = int(request.form["listing_id"])
        with sqlite3.connect("nittanyauction.db") as conn:
            if action == "add":
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist (bidder_email, listing_id) VALUES (?, ?)",
                    (email, listing_id)
                )
                flash("Added to your watchlist.", "success")
            elif action == "remove":
                conn.execute(
                    "DELETE FROM watchlist WHERE bidder_email = ? AND listing_id = ?",
                    (email, listing_id)
                )
                flash("Removed from your watchlist.", "success")
        next_url = request.form.get("next") or "/bidder/watchlist"
        return redirect(next_url)

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        items = conn.execute("""
            SELECT w.listing_id, w.added_at,
                   l.title, l.seller_email, l.reserve_price, l.max_bids, l.status,
                   l.auction_stop_time, l.promoted,
                   c.category_name,
                   (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                   (SELECT COUNT(*)       FROM bids WHERE listing_id = l.listing_id) AS bid_count
            FROM watchlist w
            JOIN listings l   ON w.listing_id = l.listing_id
            LEFT JOIN categories c ON l.category_id = c.category_id
            WHERE w.bidder_email = ?
            ORDER BY w.added_at DESC
        """, (email,)).fetchall()

    enriched = []
    for row in items:
        d = dict(row)
        d["is_active"] = (d["status"] == "active" and d["auction_stop_time"] > now)
        enriched.append(d)

    return render_template("bidder_watchlist.html", email=email, items=enriched)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        role = request.form.get("role")

        valid_roles = ["seller", "buyer", "helpdesk"]
        if role not in valid_roles:
            flash("Invalid role selected.")
            return redirect("/register")

        connection = sqlite3.connect("nittanyauction.db")
        cursor = connection.cursor()

        # Here we are checking if user already exists
        cursor.execute("SELECT * FROM auth_users WHERE email = ?", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            connection.close()
            flash("Email already registered.", "error")
            return redirect("/register")
        salt = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
        password_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

        # Insert new user
        cursor.execute(
            "INSERT INTO auth_users (email, password_hash, salt, role) VALUES (?, ?, ?, ?)",
            (email, password_hash, salt, role)
        )
        connection.commit()
        connection.close()

        flash("Welcome to NittanyAuction. Your account has been created.", "success")
        return redirect("/login")

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)