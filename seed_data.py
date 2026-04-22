import csv
import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "NittanyAuctionDataset"
DB_PATH = Path(__file__).resolve().parent / "nittanyauction.db"


def sha256_hash(password: str, salt_hex: str) -> str:
    return hashlib.sha256((salt_hex + password).encode("utf-8")).hexdigest()


def read_csv(filename: str) -> list[dict]:
    path = DATASET_DIR / filename
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def clean(value: str) -> str:
    return value.strip() if value else ""


def clean_price(value: str) -> float:
    return float(clean(value).replace("$", "").replace(",", "") or "0")


def parse_date(date_str: str, fmt: str = "%m/%d/%y") -> str:
    try:
        return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return "2021-01-01T00:00"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")

    # -- Create categories table (missing from app.py init_db) --
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL UNIQUE
        )
    """)
    existing_cat_cols = {row[1] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "parent_category" not in existing_cat_cols:
        conn.execute("ALTER TABLE categories ADD COLUMN parent_category TEXT")
    conn.commit()

    # ------------------------------------------------------------------
    # 1. Determine roles from role-specific CSVs
    # ------------------------------------------------------------------
    bidder_emails  = {clean(r["email"]).lower() for r in read_csv("Bidders.csv")}
    seller_emails  = {clean(r["email"]).lower() for r in read_csv("Sellers.csv")}
    helpdesk_emails = {clean(r["email"]).lower() for r in read_csv("Helpdesk.csv")}

    def get_role(email: str) -> str:
        e = email.lower()
        if e in helpdesk_emails:
            return "helpdesk"
        if e in seller_emails:
            return "seller"
        return "buyer"

    # ------------------------------------------------------------------
    # 2. auth_users  (same SHA-256 scheme as seed_users.py)
    # ------------------------------------------------------------------
    users = read_csv("Users.csv")
    inserted_users = updated_users = 0
    for row in users:
        email    = clean(row.get("email", "")).lower()
        password = clean(row.get("password", ""))
        if not email or not password:
            continue
        role = get_role(email)
        salt = secrets.token_hex(16)
        pw_hash = sha256_hash(password, salt)
        existing = conn.execute(
            "SELECT 1 FROM auth_users WHERE email = ?", (email,)
        ).fetchone()
        conn.execute("""
            INSERT INTO auth_users (email, password_hash, salt, role)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password_hash = excluded.password_hash,
                salt          = excluded.salt,
                role          = excluded.role
        """, (email, pw_hash, salt, role))
        if existing:
            updated_users += 1
        else:
            inserted_users += 1

    conn.commit()
    print(f"auth_users:    inserted={inserted_users}  updated={updated_users}")

    # ------------------------------------------------------------------
    # 3. categories
    # ------------------------------------------------------------------
    cat_rows = read_csv("Categories.csv")
    for row in cat_rows:
        parent = clean(row.get("parent_category", ""))
        name   = clean(row.get("category_name", ""))
        if not name:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO categories (parent_category, category_name)
            VALUES (?, ?)
        """, (parent, name))
    conn.commit()

    cat_name_to_id: dict[str, int] = {
        row[1].lower(): row[0]
        for row in conn.execute("SELECT category_id, category_name FROM categories")
    }
    print(f"categories:    {len(cat_name_to_id)} loaded")

    # ------------------------------------------------------------------
    # 4. bidders  (join Address + Zipcode_Info for street/city/state)
    # ------------------------------------------------------------------
    addresses = {clean(r["address_id"]): r for r in read_csv("Address.csv")}
    zipcodes  = {clean(r["zipcode"]): r  for r in read_csv("Zipcode_Info.csv")}

    inserted_bidders = 0
    for row in read_csv("Bidders.csv"):
        email   = clean(row["email"]).lower()
        addr_id = clean(row.get("home_address_id", ""))
        addr    = addresses.get(addr_id, {})
        zipcode = clean(addr.get("zipcode", ""))
        zip_info = zipcodes.get(zipcode, {})
        street  = f"{clean(addr.get('street_num',''))} {clean(addr.get('street_name',''))}".strip()
        city    = clean(zip_info.get("city",  ""))
        state   = clean(zip_info.get("state", ""))
        age_val = clean(row.get("age", ""))
        age     = int(age_val) if age_val.isdigit() else None

        conn.execute("""
            INSERT INTO bidders
                (email, first_name, last_name, street, city, state, zipcode, major, age)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                first_name = excluded.first_name,
                last_name  = excluded.last_name,
                street     = excluded.street,
                city       = excluded.city,
                state      = excluded.state,
                zipcode    = excluded.zipcode,
                major      = excluded.major,
                age        = excluded.age
        """, (email, clean(row.get("first_name","")), clean(row.get("last_name","")),
              street, city, state, zipcode,
              clean(row.get("major", "")), age))
        inserted_bidders += 1

    conn.commit()
    print(f"bidders:       {inserted_bidders} processed")

    # ------------------------------------------------------------------
    # 5. listings  (preserve CSV listing_id so bids/transactions match)
    # ------------------------------------------------------------------
    transactions_raw = read_csv("Transactions.csv")
    sold_listing_ids = {clean(r["Listing_ID"]) for r in transactions_raw}

    seen_ids = set()
    inserted_listings = 0
    for row in read_csv("Auction_Listings.csv"):
        lid = clean(row.get("Listing_ID", ""))
        if not lid or lid in seen_ids:
            continue
        seen_ids.add(lid)

        seller_email  = clean(row.get("Seller_Email", "")).lower()
        cat_name      = clean(row.get("Category", ""))
        category_id   = cat_name_to_id.get(cat_name.lower())
        title         = clean(row.get("Auction_Title", "")) or clean(row.get("Product_Name", ""))
        description   = clean(row.get("Product_Description", ""))
        reserve_price = clean_price(row.get("Reserve_Price", "0"))
        max_bids_val  = clean(row.get("Max_bids", "0"))
        max_bids      = int(max_bids_val) if max_bids_val.isdigit() else 0
        csv_status    = clean(row.get("Status", "1"))

        if lid in sold_listing_ids:
            status    = "sold"
            stop_time = "2021-12-31T23:59"
        elif csv_status == "1":
            status    = "active"
            stop_time = "2027-12-31T23:59"
        else:
            status    = "inactive"
            stop_time = "2021-12-31T23:59"

        conn.execute("""
            INSERT OR IGNORE INTO listings
                (listing_id, seller_email, title, description, category_id,
                 reserve_price, auction_stop_time, status, max_bids)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(lid), seller_email, title, description, category_id,
              reserve_price, stop_time, status, max_bids))
        inserted_listings += 1

    conn.commit()
    print(f"listings:      {inserted_listings} inserted")

    # ------------------------------------------------------------------
    # 6. bids
    # ------------------------------------------------------------------
    inserted_bids = 0
    for row in read_csv("Bids.csv"):
        bid_id       = clean(row.get("Bid_ID", ""))
        listing_id   = clean(row.get("Listing_ID", ""))
        bidder_email = clean(row.get("Bidder_Email", "")).lower()
        bid_price    = clean_price(row.get("Bid_Price", "0"))
        if not bid_id or not listing_id:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO bids (bid_id, listing_id, bidder_email, bid_amount)
            VALUES (?, ?, ?, ?)
        """, (int(bid_id), int(listing_id), bidder_email, bid_price))
        inserted_bids += 1

    conn.commit()
    print(f"bids:          {inserted_bids} inserted")

    # ------------------------------------------------------------------
    # 7. credit_cards
    # ------------------------------------------------------------------
    inserted_cards = 0
    for row in read_csv("Credit_Cards.csv"):
        owner      = clean(row.get("Owner_email", "")).lower()
        card_num   = clean(row.get("credit_card_num", ""))
        card_type  = clean(row.get("card_type", ""))
        exp_month  = clean(row.get("expire_month", "")).zfill(2)
        exp_year   = clean(row.get("expire_year", ""))
        expiration = f"{exp_month}/{exp_year}"
        if not owner or not card_num:
            continue
        conn.execute("""
            INSERT INTO credit_cards (bidder_email, card_type, card_number, expiration_date)
            VALUES (?, ?, ?, ?)
        """, (owner, card_type, card_num, expiration))
        inserted_cards += 1

    conn.commit()
    print(f"credit_cards:  {inserted_cards} inserted")

    # ------------------------------------------------------------------
    # 8. transactions
    # ------------------------------------------------------------------
    inserted_tx = 0
    for row in transactions_raw:
        tx_id        = clean(row.get("Transaction_ID", ""))
        listing_id   = clean(row.get("Listing_ID", ""))
        bidder_email = clean(row.get("Bidder_Email", "")).lower()
        amount       = clean_price(row.get("Payment", "0"))
        tx_date      = parse_date(row.get("Date", ""))
        if not tx_id or not listing_id:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO transactions
                (transaction_id, listing_id, bidder_email, amount, transaction_date)
            VALUES (?, ?, ?, ?, ?)
        """, (int(tx_id), int(listing_id), bidder_email, amount, tx_date))
        inserted_tx += 1

    conn.commit()
    print(f"transactions:  {inserted_tx} inserted")

    # ------------------------------------------------------------------
    # 9. ratings  (match bidder+seller pair to a transaction listing_id)
    #    The ratings table requires listing_id UNIQUE, so skip ratings
    #    that can't be matched to a completed transaction.
    # ------------------------------------------------------------------
    tx_map: dict[tuple, list[int]] = {}
    for row in transactions_raw:
        key = (
            clean(row["Bidder_Email"]).lower(),
            clean(row["Seller_Email"]).lower(),
        )
        tx_map.setdefault(key, []).append(int(clean(row["Listing_ID"])))

    used_listing_ids: set[int] = set()
    inserted_ratings = skipped_ratings = 0
    for row in read_csv("Ratings.csv"):
        bidder = clean(row.get("Bidder_Email", "")).lower()
        seller = clean(row.get("Seller_Email", "")).lower()
        stars_val = clean(row.get("Rating", "0"))
        stars  = int(stars_val) if stars_val.isdigit() else 0
        rated_at = parse_date(row.get("Date", ""))

        candidates = [
            lid for lid in tx_map.get((bidder, seller), [])
            if lid not in used_listing_ids
        ]
        if not candidates:
            skipped_ratings += 1
            continue

        listing_id = candidates[0]
        used_listing_ids.add(listing_id)
        conn.execute("""
            INSERT OR IGNORE INTO ratings
                (listing_id, bidder_email, seller_email, stars, rated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (listing_id, bidder, seller, stars, rated_at))
        inserted_ratings += 1

    conn.commit()
    print(f"ratings:       {inserted_ratings} inserted  ({skipped_ratings} skipped — no matching transaction)")

    # ------------------------------------------------------------------
    # 10. helpdesk_requests
    # ------------------------------------------------------------------
    inserted_req = 0
    for row in read_csv("Requests.csv"):
        req_id      = clean(row.get("request_id", ""))
        requester   = clean(row.get("sender_email", "")).lower()
        assigned_to = clean(row.get("helpdesk_staff_email", "")).lower() or "helpdeskteam@lsu.edu"
        req_type    = clean(row.get("request_type", "general"))
        details     = clean(row.get("request_desc", ""))
        status_val  = clean(row.get("request_status", "0"))
        if status_val == "1":
            status = "completed"
        elif assigned_to and assigned_to != "helpdeskteam@lsu.edu":
            status = "assigned"
        else:
            status = "unassigned"

        if not req_id:
            continue
        conn.execute("""
            INSERT OR IGNORE INTO helpdesk_requests
                (request_id, requester_email, request_type, details, assigned_to, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (int(req_id), requester, req_type, details, assigned_to, status))
        inserted_req += 1

    conn.commit()
    print(f"helpdesk_requests: {inserted_req} inserted")

    conn.close()
    print(f"\nDone. Database: {DB_PATH}")


if __name__ == "__main__":
    main()
