"""Synthetic demo data for SmartStock, written into the MySQL tables.

Everything here is INVENTED for the demo; it is not real Adlers data.

Run it with:   flask seed            (asks before wiping existing rows)
               flask seed --yes      (no question; used by scripts)

random.Random(42) makes the stock levels and sales identical on every machine.
Sales dates end yesterday, counted from the day you run the seed.
"""
import random
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (CentralStock, DrawerStock, Machine, MachineStock, Product, Sale,
                        StockMovement, Supplier, User)

DAYS = 30  # days of sales history to generate

# ------------------------------------------------------------------ raw data
SUPPLIERS = [  # id, name, lead time (days)
    (1, "Supplier A - Beverages", 2),
    (2, "Supplier B - Snacks", 3),
    (3, "Supplier C - Water", 1),
]

PRODUCTS = [  # id, name, supplier, unit cost (R), case size, avg daily sales per machine, central stock
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

LOCATIONS = [
    "Engineering 1", "Library", "Law Building", "Student Centre", "Humanities",
    "Natural Sciences", "Sports Centre", "Education Building", "EMS Building",
    "IT Building", "Health Sciences", "Residence Commons",
]

CORE_PRODUCTS = [1, 7, 8, 13]  # every machine carries these four best sellers

MACHINE_SLOT_CAPACITY, MACHINE_THRESHOLD = 20, 5
DRAWER_SLOT_CAPACITY, DRAWER_THRESHOLD = 12, 2
DRAWER_TOTAL_CAPACITY = 50     # units one machine's drawer can hold in total
CENTRAL_THRESHOLD = 20

# A few hand-set low levels so the alerts page has something to show.
LOW_MACHINE = {(1, 1): 4, (3, 8): 3, (5, 13): 0, (8, 7): 2}    # (machine, product): qty
LOW_DRAWER = {(1, 7): 2, (4, 1): 0, (9, 13): 1}

# Demo logins. Only a hash of each password is stored.
DEMO_PASSWORD = "SmartStock123"
USERS = [  # id, name, email, role
    (1, "Mr Msiza", "msiza@adlers.test", "user"),
    (2, "Claudia Aird", "admin@smartstock.test", "admin"),
]

# Child tables first, so foreign keys never block the delete.
_TABLES_CHILD_FIRST = [StockMovement, Sale, CentralStock, DrawerStock, MachineStock,
                       Product, Supplier, Machine, User]


def clear():
    """Delete every row from every table (the tables themselves stay)."""
    for model in _TABLES_CHILD_FIRST:
        db.session.query(model).delete()
    db.session.commit()


def seed(today=None):
    """Wipe the tables and fill them with the deterministic demo data."""
    today = today or date.today()
    first_day = today - timedelta(days=DAYS)          # sales run from here up to yesterday
    rng = random.Random(42)
    clear()

    db.session.add_all(Supplier(supplier_id=sid, name=name, lead_time_days=lead)
                       for sid, name, lead in SUPPLIERS)
    db.session.add_all(Product(product_id=pid, name=name, supplier_id=sid,
                               unit_cost=cost, case_size=case)
                       for pid, name, sid, cost, case, _mean, _central in PRODUCTS)
    db.session.add_all(CentralStock(product_id=pid, qty=central, threshold=CENTRAL_THRESHOLD)
                       for pid, *_rest, central in PRODUCTS)
    db.session.flush()

    mean_sales = {pid: mean for pid, _n, _s, _c, _k, mean, _q in PRODUCTS}
    optional = [pid for pid, *_ in PRODUCTS if pid not in CORE_PRODUCTS]

    for mid, location in enumerate(LOCATIONS, start=1):
        db.session.add(Machine(machine_id=mid, code=f"UP-{mid:02d}", location=location,
                               drawer_capacity=DRAWER_TOTAL_CAPACITY))
        db.session.flush()  # the machine row must exist before its stock rows (foreign keys)
        popularity = rng.uniform(0.6, 1.4)  # some locations are busier than others
        carried = CORE_PRODUCTS + rng.sample(optional, 4)  # 8 products per machine

        for pid in carried:
            machine_qty = rng.randint(8, MACHINE_SLOT_CAPACITY)
            drawer_qty = min(rng.randint(3, 8), 6)
            db.session.add(MachineStock(
                machine_id=mid, product_id=pid,
                qty=LOW_MACHINE.get((mid, pid), machine_qty),
                capacity=MACHINE_SLOT_CAPACITY, threshold=MACHINE_THRESHOLD))
            db.session.add(DrawerStock(
                machine_id=mid, product_id=pid,
                qty=LOW_DRAWER.get((mid, pid), drawer_qty),
                capacity=DRAWER_SLOT_CAPACITY, threshold=DRAWER_THRESHOLD))

            # 30 days of daily sales; weekends (Saturday, Sunday) are quieter on campus.
            for offset in range(DAYS):
                day = first_day + timedelta(days=offset)
                mean = mean_sales[pid] * popularity * (0.5 if day.weekday() >= 5 else 1.0)
                units = max(0, round(rng.gauss(mean, max(mean, 0.5) ** 0.5)))
                db.session.add(Sale(machine_id=mid, product_id=pid, sale_date=day, qty=units))

    password_hash = generate_password_hash(DEMO_PASSWORD)
    db.session.add_all(User(user_id=uid, name=name, email=email, role=role,
                            password_hash=password_hash)
                       for uid, name, email, role in USERS)
    db.session.commit()
