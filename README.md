This project implements a user login system for the NittanyAuction assignment using Flask, HTML, SQLite.

## Features
- User authentication using email and password
- Passwords securely stored using salted SHA256 hashing
- Database populated from `Users.csv`

## Project Structure
The structure of our code has 3 folders, for styling, test data and webpages, in addition to scripts for populating the database and handling routes and SQLite
- `app.py` – Flask application and login logic
- `seed_users.py` – Script to populate database from CSV
- `Users.csv` – Dataset containing users (email, password, role)
- `nittanyauction.db` – SQLite database
- `NittanyAuctionDataset_v1` - Test CSVs
- `templates/` – HTML pages
- `static/` – CSS files

## Setup & Run
In order to run the code we firstly run python3 seed_users.py in the terminal to populate the database. Then we run python3 app.py to run the website and open http://127.0.0.1:5000/ in the browser. After that go to login and copy and paste the test emails and passwords that are in the Users.csv.
