# SmartStock: Adlers Vending Machine Operations

BFB 321, Group 25. Claudia Aird (u21433098) and Josua Olivier (u23524431).

SmartStock is a web dashboard that gives Mr Msiza **one system** for the three places his vending stock lives:
the **machine**, the small **drawer** at its base, and the shared **central storage** at the Adlers café.
It also turns what is needed into **one consolidated order per supplier**.
It replaces the paper log and goes beyond what the third-party app Moma tracks.

> **Demo data.** Every machine, product, sale and stock level in this repo is synthetic.
> The Moma sensor feed named in the proposal is not available, so machine stock is entered as a
> manual count (the fallback stated in the proposal).

## Features (mapped to the proposal)

| Feature | Page | Objective |
|---|---|---|
| Machine, drawer and central stock side by side | Machines list, then a detailed machine’s page | O1, O2 |
| Record a manual machine count | Machine page | O1 (fallback) |
| Log a restock visit (fills machine, then drawer, then returns the rest to central) | Machine page | O2 |
| Central storage tracker | Central storage | O2 |
| Drawer allocation ranking from 30-day sales | Allocation | O3 |
| Consolidated shopping list, one order per supplier | Shopping list | O4 |
| Low-stock alerts across all three tiers | Alerts | O3, O5 |
| KPI dashboard (alerts, central value, trips saved, best sellers, impact estimate) | Dashboard | O5 |

## Quick start (Windows PowerShell)

```
git clone https://github.com/u21433098/u21433098-group25_smartstock_dashboard.git
cd u21433098-group25_smartstock_dashboard
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000 in a browser. The page styles load Bootstrap's CSS from a CDN, so an internet connection is needed.

**Demo login:** `msiza@adlers.test` / `SmartStock123`

If activation says "running scripts is disabled", run once:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

Optional: copy `.env.example` to `.env` and set your own `SECRET_KEY`.

## Run the tests

```
pytest
```

- `tests/test_safety_stock.py`, `test_allocation.py`, `test_procurement.py`: unit tests for the supply chain model, checked against hand-calculated answers.
- `tests/test_routes.py`: integration tests for login, access control, CSRF protection, and the stock-changing flows.

## Project structure

```
app/
  __init__.py         create_app(): settings, login, CSRF, error pages
  blueprints/         one file per feature: auth, dashboard, inventory, allocation, procurement
  services/           the only layer that touches data (swap for MySQL later) and calls the models
  data/seed_data.py   synthetic demo data (in memory)
  templates/          one HTML file per page + base.html and _macros.html
  static/css/         style.css (on top of Bootstrap CSS)
  models/             (reserved) database table classes for the MySQL version
  schemas/            (reserved) request/response schemas for the REST API version
models/               supply chain model: pure Python, no Flask, no database
  safety_stock.py     average demand, std deviation, safety stock, reorder point
  allocation.py       turnover ranking, greedy drawer allocation, restock split
  procurement.py      order-up-to level, order quantity, supplier grouping, trips saved, EOQ
tests/                pytest unit and integration tests
config.py             DEV / TEST / PROD settings
run.py                entry point
```

## Supply chain model

All formulas are in `models/` with docstrings stating assumptions.

| Quantity | Formula |
|---|---|
| Safety stock | `SS = z x s x sqrt(L)` (z = 1.645, a 95% service level) |
| Reorder point | `ROP = d x L + SS` |
| Order-up-to level (weekly review) | `U = d x (L + R) + z x s x sqrt(L + R)` |
| Order quantity | `(U - stock on hand)`, rounded **up** to whole cases |
| Trips saved | `products to order - suppliers to visit` |
| Economic order quantity | `EOQ = sqrt(2DS / H)` |

**Symbols**

| Symbol | Meaning |
|---|---|
| d | average daily demand (units per day) |
| s | standard deviation of daily demand (units per day) |
| z | service-level factor (1.645 for a 95% service level) |
| L | supplier lead time (days) |
| R | review period (days); 7, because Mr Msiza makes a weekly supplier run |
| SS | safety stock (units) |
| ROP | reorder point (units) |
| U | order-up-to level: the stock level each weekly order tops up to (units) |
| D | annual demand (units per year); EOQ only |
| S | cost of placing one order (rand per order); EOQ only |
| H | cost of holding one unit in stock for a year (rand per unit per year); EOQ only |

"Stock on hand" adds the machine, drawer and central tiers together.

**Why the app does not use EOQ.** There are two common ways to decide how much to order.

- **EOQ (economic order quantity)** finds the best size for each order, balancing the cost of ordering often against the cost of storing too much. It assumes you can place an order whenever you like, and it needs figures we do not have: the cost of placing one order and the cost of holding stock for a year.
- **The order-up-to method** works the way Mr Msiza actually buys. He does one supplier run each week. On every run, the app adds up the stock in the machines, drawers and central storage, then orders enough to reach a target level that covers the week ahead, the supplier's lead time and some safety stock. The order is rounded up to whole cases.

SmartStock uses the order-up-to method for the shopping list, because it fits a fixed weekly run and needs no cost data. The `eoq()` function is still in `models/procurement.py` and is unit-tested, but the app does not call it. It is kept as a reference calculation, so the report can explain the alternative that was considered.

**Drawer allocation (O3):** rank products by units sold in the last 30 days; give each its desired buffer
(3 days of sales, capped by its slot size), fastest sellers first, until the drawer's total space (50 units) is used.
Anything that does not fit stays in central storage.

**Impact estimate.** Two 60-minute unplanned supplier trips a week is about 8.7 hours of driving a month.
A 25% cut in trips (O4) therefore saves about **2.2 hours a month**. This is a modelled estimate, not a measurement.


## Design decisions

- **No JavaScript.** Every action is an HTML form submit and every page is a server-rendered Jinja template.
  Bootstrap is used for its CSS only. The navigation bar wraps on small screens instead of using a menu button.
- **One template per page**, with shared pieces (navigation bar, flash messages, KPI cards, stock badges) in `base.html` and `_macros.html`.
- **Passwords are hashed**, forms are protected by a CSRF token, and login redirects only to pages inside this site.
- **Services layer.** Routes never touch the data directly, so moving to MySQL means rewriting `app/services` and leaving the templates alone.

## Planned MySQL data model (next stage)

```mermaid
erDiagram
    users {
        int user_id PK
        string name
        string email UK
        string password_hash
        string role
        datetime created_at
    }
    suppliers {
        int supplier_id PK
        string name
        int lead_time_days
    }
    products {
        int product_id PK
        string name
        int supplier_id FK
        decimal unit_cost
        int case_size
    }
    machines {
        int machine_id PK
        string code UK
        string location
    }
    machine_stock {
        int machine_id PK, FK
        int product_id PK, FK
        int qty
        int capacity
        int threshold
    }
    drawer_stock {
        int machine_id PK, FK
        int product_id PK, FK
        int qty
        int capacity
        int threshold
    }
    central_storage {
        int product_id PK, FK
        int qty
        int threshold
    }
    sales {
        int sale_id PK
        int machine_id FK
        int product_id FK
        int qty
        date sale_date
    }
    stock_movements {
        int movement_id PK
        int machine_id FK
        int product_id FK
        int user_id FK
        string tier
        int old_qty
        int new_qty
        string note
        datetime created_at
    }
    suppliers ||--o{ products : supplies
    products ||--o{ machine_stock : "stocked in"
    machines ||--o{ machine_stock : holds
    products ||--o{ drawer_stock : "buffered in"
    machines ||--o{ drawer_stock : has
    products ||--|| central_storage : "pooled in"
    machines ||--o{ sales : records
    products ||--o{ sales : "sold as"
    users ||--o{ stock_movements : makes
    products ||--o{ stock_movements : "moves"
```

In this lean version the tables are Python dictionaries in `app/data/seed_data.py`, and each `(machine, product)` pair keeps a list of 30 daily sales numbers instead of dated `sales` rows.

## Known limitations

- Data lives in memory and **resets when the server restarts** (MySQL is the next stage).
- No live sensor feed: machine stock is a manual count.
- No pagination or column sorting yet (both need extra work for the final stage).
- Runs on Flask's development server; no production deployment was done for the semester project.

## Task allocation

| Member | Student no. | Files owned | Reviewed by |
|---|---|---|---|
| Claudia Aird | u21433098 | Supply chain model (`models/`) and its unit tests (`tests/test_safety_stock.py`, `test_allocation.py`, `test_procurement.py`), demo data (`app/data/seed_data.py`), services layer (`app/services/`), `config.py`, `run.py`, `.env.example`, `README.md` | Josua Olivier |
| Josua Olivier | u23524431 | Frontend: page templates (`app/templates/`) and stylesheet (`app/static/css/style.css`); routes (`app/blueprints/`), app factory (`app/__init__.py`), integration tests (`tests/test_routes.py`) | Claudia Aird |
