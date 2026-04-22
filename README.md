# NittanyAuction

A full-stack auction web application built with **Flask**, **SQLite**, and vanilla HTML/CSS for CMPSC 431W — Database Management Systems (Spring 2026).

## Project Description

NittanyAuction is an online auction platform for members of Lion State University (LSU) to buy and sell goods via time-limited, bid-count-based auctions. Three user roles are supported: **Bidders**, **Sellers**, and **HelpDesk staff**.

## Setup & Run

### Requirements
- Python 3.x
- Flask (`pip install flask`)

### Steps

```bash
# 1. Populate the database from CSV files
python3 seed_data.py
python3 seed_users.py

# 2. Start the server
python3 app.py

# 3. Open in browser
http://127.0.0.1:5001/
```

Test accounts are in `Users.csv`. Copy an email and password directly from that file to log in.

## Directory Structure

```
Nittany-Auction/
├── app.py                     # Flask routes, business logic, DB access
├── seed_data.py               # Populates listings, categories, bids, etc. from CSV files
├── seed_users.py              # Populates auth_users and bidders from Users.csv
├── nittanyauction.db          # SQLite database (auto-created on first run)
├── Users.csv                  # Test user accounts
├── NittanyAuctionDataset_v1/  # Raw CSV datasets from course
├── templates/                 # Jinja2 HTML templates (one per page)
└── static/
    ├── style.css              # Global stylesheet
    ├── logo.svg               # Site logo (light)
    ├── logo-dark.svg          # Site logo (dark, used on login/register)
    └── timer.js               # Countdown timer for auction cards
```

## Implemented Features

### Required Functionality (Phase 2 Spec)

#### 1. User Login
- Email + password authentication
- Passwords stored as **salted SHA-256 hashes** (never plaintext)
- Role-specific redirect on login: Bidder → `/bidder`, Seller → `/seller`, HelpDesk → `/helpdesk`
- Password field masked during entry

#### 2. Category Hierarchy
- Full multi-level category tree stored in the `categories` table (`parent_category` field)
- Root node (`'Root'`) serves as the entry point no products attached
- Browsable at `/bidder/browse` each click dynamically queries the DB for subcategories and listings at that level
- Breadcrumb navigation across all levels
- No hardcoded category structure fully database-driven

#### 3. Auction Listing Management (Seller)
- Sellers create listings at `/seller/listings/new` with title, description, condition, category, reserve price, and `max_bids`
- Listings immediately visible under their category once published
- Listings page (`/seller/listings`) groups listings by status: **Active**, **Inactive**, **Sold**
- Edit restricted: sellers can only edit listings with zero bids; a clear message is shown if bids exist
- Sellers can remove an active listing removal records:
  - Seller-provided removal reason
  - Remaining bids at time of removal (`max_bids − bid_count`)
- Filter and sort listings by category, price, bid count

#### 4. Auction Bidding (Bidder)
- **$1 increment rule**: each bid must exceed the current highest bid by at least $1
- **Auction end rule**: auction closes when `bid_count` reaches `max_bids` (not a stop time)
- **Turn-taking rule**: a bidder cannot place two consecutive bids — must wait for a competing bid
- After every bid: updated remaining bids and current highest bid are shown immediately
- Clear UI feedback on rejected bids: "bid too low", "auction ended", "you must wait for another bidder"
- When auction ends (`max_bids` reached):
  - If highest bid ≥ reserve price → status set to `'ended'`; winner notified and directed to payment
  - If highest bid < reserve price → status set to `'inactive'` with reason; all bidders notified of failure
  - All bidders notified via the in-app notifications system

#### 5. Payment Flow
- Winner completes payment at `/bidder/listings/<id>/pay` using a saved or new credit card
- Transaction recorded in `transactions` table
- Listing status updated to `'sold'` and removed from all browsing/search results

#### 6. User Registration
- New users register at `/register` choosing **Bidder** or **Seller**
- HelpDesk accounts are internal not available via public registration
- Passwords hashed on creation

#### 7. User Profile Update
- **Bidders** (`/bidder/profile`): update name, address, phone, major, age, annual income; change password
- **Sellers** (`/seller/profile`): update name, bank routing/account numbers, business info; change password
- Email (user ID) cannot be changed by the user must go through HelpDesk
- Password change requires current password verification; new password must be ≥ 6 characters

#### 8. Product Search
- Search at `/bidder/listings` by keyword (matches title, description, category name, seller email)
- Filter by price range (min/max)
- Filter by category (dropdown or left sidebar)
- Sort by price or bid count
- All queries run directly against the SQLite database no external search libraries

#### 9. Seller Rating
- After winning and paying, bidder may rate the seller 1–5 stars at `/bidder/listings/<id>/rate`
- Only one rating allowed per completed transaction (duplicate prevention enforced in DB)
- Seller's average rating displayed on every listing detail page and seller info section

### Optional / Extra Credit Functionality

#### HelpDesk Support
- Bidders can apply to become sellers via `/bidder/apply-seller`
- Sellers can request new categories via `/seller/category-request`, specifying the category name and its parent in the hierarchy
- Requests submitted to `helpdeskteam@lsu.edu` as `'unassigned'`
- HelpDesk staff at `/helpdesk/requests` can:
  - View all unassigned and their own assigned requests
  - **Claim** an unassigned request
  - **Complete** a request — for `add_category` requests, automatically inserts the new category into the hierarchy under the specified parent

#### Auction Promotion (Seller)
- Sellers pay a promotion fee of **5% of the reserve price** to promote a listing
- Promoted listings appear **at the top** of search results and category pages (sorted before non-promoted)
- Promotion recorded in the DB with timestamp and fee paid
- Promoted badge (★ Promoted) shown on listing cards and detail pages
- Promoted listings still obey all normal auction rules

#### Watchlist (Bidder)
- Bidders add/remove listings from their watchlist at `/bidder/watchlist`
- Watchlist persists across sessions (stored in `watchlist` table, not session memory)
- Each saved item shows: title, current highest bid, remaining bids, seller, listing status
- Bidders can bid directly from the watchlist page if the listing is still active
- Watchlist button also available on every listing detail page

#### In-App Notifications
- All bidders on a listing are notified when an auction ends (win, loss, or reserve not met)
- Notifications appear on the Bidder Dashboard and are marked read automatically on visit

#### Q&A System
- Bidders ask questions on any active listing (`/bidder/listings/<id>/question`)
- Sellers answer at `/seller/listings/<id>/questions`
- Answered questions are shown publicly on the listing detail page for all bidders

#### Amazon-Style Category Sidebar
- `/bidder/listings` features a sticky left sidebar with the full category tree
- Top-level categories are collapsible; active category auto-expands and highlights
- Category selection preserved across search and sort changes

## Database Schema

Key tables (all created automatically via `init_db()` in `app.py`):

| Table | Description |
|---|---|
| `auth_users` | Email, hashed password, salt, role |
| `bidders` | Bidder personal info (name, address, major, income, etc.) |
| `sellers` | Seller info (name, bank details, business info, balance) |
| `listings` | Auction listings with status, reserve price, max_bids, promoted flag |
| `bids` | Individual bids (listing, bidder, amount, timestamp) |
| `categories` | Category hierarchy (`category_name`, `parent_category`) |
| `credit_cards` | Bidder payment methods |
| `transactions` | Completed payments for won auctions |
| `ratings` | Post-purchase seller ratings (1–5 stars) |
| `questions` | Q&A between bidders and sellers |
| `watchlist` | Saved listings per bidder |
| `notifications` | In-app auction outcome notifications |
| `helpdesk_requests` | Category/role change requests and their status |
| `seller_applications` | Bidder-to-seller upgrade applications |

## Test Accounts

Sample accounts from `Users.csv`. Use any email/password pair from that file. Roles are pre-assigned. To test a specific role, filter the CSV by the `role` column for `buyer`, `seller`, or `helpdesk`.
