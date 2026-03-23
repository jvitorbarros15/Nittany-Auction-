import csv
import hashlib
import secrets
import sqlite3
from pathlib import Path


def sha256_hash(password: str, salt_hex: str):
    return hashlib.sha256((salt_hex + password).encode("utf-8")).hexdigest()


def load_email_set(csv_path: Path):
    emails: set[str] = set()
    if not csv_path.exists():
        return emails

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = (row.get("email") or row.get("\ufeffemail") or "").strip().lower()
            if email:
                emails.add(email)

    return emails


def main():
    root = Path(__file__).resolve().parent
    dataset_dir = root / "NittanyAuctionDataset_v1"

    users_csv = dataset_dir / "Users.csv"

    if not users_csv.exists():
        raise FileNotFoundError(f"Missing dataset file: {users_csv}")

    db_path = root / "nittanyauction.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )

        inserted = 0
        updated = 0

        with users_csv.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = (row.get("email") or row.get("\ufeffemail") or "").strip().lower()
                password = (row.get("password") or "").strip()
                
                role = (row.get("role") or "").strip().lower()
                
                if not email or not password or not role: 
                    continue

                salt = secrets.token_hex(16)
                password_hash = sha256_hash(password, salt)

                existing = conn.execute(
                    "SELECT 1 FROM auth_users WHERE email = ?",
                    (email,),
                ).fetchone()

                conn.execute(
                    """
                    INSERT INTO auth_users (email, password_hash, salt, role)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        password_hash=excluded.password_hash,
                        salt=excluded.salt,
                        role=excluded.role
                    """,
                    (email, password_hash, salt, role),
                )

                if existing:
                    updated += 1
                else:
                    inserted += 1

        conn.commit()
        print(f"Database: {db_path}")
        print(f"Users upserted. inserted={inserted} updated={updated}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
