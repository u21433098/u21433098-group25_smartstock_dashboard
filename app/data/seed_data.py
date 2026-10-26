"""Synthetic demo data for SmartStock (lean version: held in memory).

Everything here is INVENTED for the demo; it is not real Adlers data.
The tables mirror the planned MySQL tables (see the ERD in README.md), so moving
to MySQL later means rewriting only app/services, not the templates.

Call reset() to rebuild all data (used when the app starts and in tests).
random.Random(42) makes the data identical on every machine.
"""
import random

from werkzeug.security import generate_password_hash

DAYS = 30  # days of sales history

# --- "tables" (filled in place by reset(), so other modules can keep references)
SUPPLIERS = {}       # supplier_id -> {id, name, lead_time_days}
PRODUCTS = {}        # product_id  -> {id, name, supplier_id, unit_cost, case_size}
MACHINES = {}        # machine_id  -> {id, code, location}
MACHINE_STOCK = {}   # (machine_id, product_id) -> {qty, capacity, threshold}
DRAWER_STOCK = {}    # (machine_id, product_id) -> {qty, capacity, threshold}
CENTRAL_STOCK = {}   # product_id -> {qty, threshold}   (one shared pool)
SALES = {}           # (machine_id, product_id) -> list of DAYS daily unit sales
USERS = {}           # user_id -> {id, name, email, password_hash, role}
MOVEMENTS = []       # audit trail of stock changes, newest first

# ------------------------------------------------------------------ raw tables
_SUPPLIERS = [  # id, name, lead time (days)
    (1, "Supplier A - Beverages", 2),
    (2, "Supplier B - Snacks", 3),
    (3, "Supplier C - Water", 1),
]

_PRODUCTS = [  # id, name, supplier, unit cost (R), case size, avg daily sales per machine, central stock
    (1, "Coca-Cola 300ml", 1, 9, 24, 5.0, 60),
    (2, "Fanta 300ml", 1, 9, 24, 2.0, 70),
    (3, "Sprite 300ml", 1, 9, 24, 2.0, 50),
    (4, "Iced Tea 500ml", 1, 12, 12, 2.0, 40),
    (5, "Energy Drink 250ml", 1, 14, 24, 2.5, 30),
    (6, "Orange Juice 330ml", 1, 11, 12, 1.5, 25),
    (7, "Bar One 55g", 2, 8, 24, 4.0, 12),
    (8, "Chips 36g", 2, 9, 20, 3.0, 45),
    (9, "Pretzels 40g", 2, 10, 20, 1.0, 30),
    (10, "Peanuts 50g", 2, 7, 20, 1.0, 25),
    (11, "Granola Bar 40g", 2, 8, 24, 1.5, 20),
    (12, "Biscuits 45g", 2, 7, 24, 1.2, 25),
    (13, "Water 500ml", 3, 5, 24, 4.0, 10),
    (14, "Sparkling Water 500ml", 3, 7, 24, 1.0, 20),
    (15, "Flavoured Water 500ml", 3, 7, 24, 1.2, 18),
]

_LOCATIONS = [
    "Engineering 1", "Library", "Law Building", "Student Centre", "Humanities",
    "Natural Sciences", "Sports Centre", "Education Building", "EMS Building",
    "IT Building", "Health Sciences", "Residence Commons",
]

CORE_PRODUCTS = [1, 7, 8, 13]  # every machine carries these four best sellers

MACHINE_SLOT_CAPACITY, MACHINE_THRESHOLD = 20, 5
DRAWER_SLOT_CAPACITY, DRAWER_THRESHOLD = 12, 2
CENTRAL_THRESHOLD = 20

# A few hand-set low levels so the alerts page has something to show.
LOW_MACHINE = {(1, 1): 4, (3, 8): 3, (5, 13): 0, (8, 7): 2}    # (machine, product): qty
LOW_DRAWER = {(1, 7): 2, (4, 1): 0, (9, 13): 1}


def reset():
    """Rebuild every table from scratch (deterministic)."""
    rng = random.Random(42)
    for table in (SUPPLIERS, PRODUCTS, MACHINES, MACHINE_STOCK, DRAWER_STOCK,
                  CENTRAL_STOCK, SALES, USERS):
        table.clear()
    MOVEMENTS.clear()

    for sid, name, lead in _SUPPLIERS:
        SUPPLIERS[sid] = {"id": sid, "name": name, "lead_time_days": lead}

    for pid, name, sid, cost, case, _mean, central in _PRODUCTS:
        PRODUCTS[pid] = {"id": pid, "name": name, "supplier_id": sid,
                         "unit_cost": cost, "case_size": case}
        CENTRAL_STOCK[pid] = {"qty": central, "threshold": CENTRAL_THRESHOLD}

    mean_sales = {pid: mean for pid, _n, _s, _c, _k, mean, _q in _PRODUCTS}
    optional = [pid for pid in PRODUCTS if pid not in CORE_PRODUCTS]

    for mid, location in enumerate(_LOCATIONS, start=1):
        MACHINES[mid] = {"id": mid, "code": f"UP-{mid:02d}", "location": location}
        popularity = rng.uniform(0.6, 1.4)  # some locations are busier than others
        carried = CORE_PRODUCTS + rng.sample(optional, 4)  # 8 products per machine

        for pid in carried:
            MACHINE_STOCK[(mid, pid)] = {
                "qty": LOW_MACHINE.get((mid, pid), rng.randint(8, MACHINE_SLOT_CAPACITY)),
                "capacity": MACHINE_SLOT_CAPACITY, "threshold": MACHINE_THRESHOLD}
            DRAWER_STOCK[(mid, pid)] = {
                "qty": LOW_DRAWER.get((mid, pid), rng.randint(2, 6)),
                "capacity": DRAWER_SLOT_CAPACITY, "threshold": DRAWER_THRESHOLD}

            # 30 days of sales; weekends (days 5 and 6 of each week) are quieter.
            sales = []
            for day in range(DAYS):
                mean = mean_sales[pid] * popularity * (0.5 if day % 7 in (5, 6) else 1.0)
                sales.append(max(0, round(rng.gauss(mean, max(mean, 0.5) ** 0.5))))
            SALES[(mid, pid)] = sales

    # Demo login for Mr Msiza. Only a hash of the password is saved, not the password itself.
    USERS[1] = {"id": 1, "name": "Mr Msiza", "email": "msiza@adlers.test",
                "password_hash": generate_password_hash("SmartStock123"),
                "role": "restocker"}


reset()
