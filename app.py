from flask import Flask, flash, render_template, request, redirect, session
import sqlite3
import hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"


def init_db():
    conn = sqlite3.connect("nittanyauction.db")
    conn.executescript("""
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
    """)
    conn.close()


init_db()


@app.route("/")
def homepage():
    return render_template("homepage.html")

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

    category_id = request.args.get("category_id", type=int)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")

    with sqlite3.connect("nittanyauction.db") as conn:
        conn.row_factory = sqlite3.Row
        categories = conn.execute(
            "SELECT * FROM categories ORDER BY category_name"
        ).fetchall()

        if category_id:
            listings = conn.execute("""
                SELECT l.*, c.category_name,
                       (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                       (SELECT COUNT(*) FROM bids WHERE listing_id = l.listing_id) AS bid_count
                FROM listings l
                LEFT JOIN categories c ON l.category_id = c.category_id
                WHERE l.status = 'active' AND l.auction_stop_time > ?
                  AND l.category_id = ?
                ORDER BY l.auction_stop_time ASC
            """, (now, category_id)).fetchall()
        else:
            listings = conn.execute("""
                SELECT l.*, c.category_name,
                       (SELECT MAX(bid_amount) FROM bids WHERE listing_id = l.listing_id) AS current_bid,
                       (SELECT COUNT(*) FROM bids WHERE listing_id = l.listing_id) AS bid_count
                FROM listings l
                LEFT JOIN categories c ON l.category_id = c.category_id
                WHERE l.status = 'active' AND l.auction_stop_time > ?
                ORDER BY l.auction_stop_time ASC
            """, (now,)).fetchall()

    return render_template("bidder_listings.html",
                           email=session["email"],
                           listings=listings,
                           categories=categories,
                           selected_category=category_id)


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

    return render_template("bidder_listing_view.html",
                           email=email,
                           listing=listing,
                           top_bid=top_bid,
                           my_bid=my_bid,
                           is_winner=is_winner,
                           auction_ended=auction_ended,
                           transaction=transaction,
                           rated=rated,
                           my_questions=my_questions)


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
    return render_template("helpdesk_welcome.html")

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
    app.run(debug=True)