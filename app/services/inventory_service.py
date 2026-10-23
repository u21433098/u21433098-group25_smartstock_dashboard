"""Reading and changing stock in the three tiers: machine, drawer, central storage."""
import logging
from datetime import datetime

from app.data import seed_data as db
from models.allocation import split_restock

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ reading
def get_machines():
    return sorted(db.MACHINES.values(), key=lambda machine: machine["id"])


def get_machine(machine_id):
    return db.MACHINES.get(machine_id)


def get_machine_rows(machine_id):
    """One row per product the machine carries, combining all three tiers (O2)."""
    rows = []
    for (m_id, p_id), machine_stock in db.MACHINE_STOCK.items():
        if m_id == machine_id:
            rows.append({
                "product_id": p_id,
                "name": db.PRODUCTS[p_id]["name"],
                "machine": machine_stock,
                "drawer": db.DRAWER_STOCK[(m_id, p_id)],
                "central": db.CENTRAL_STOCK[p_id],
            })
    return sorted(rows, key=lambda row: row["name"])


def get_central_rows():
    rows = []
    for p_id, stock in db.CENTRAL_STOCK.items():
        product = db.PRODUCTS[p_id]
        rows.append({"product_id": p_id, "name": product["name"],
                     "supplier": db.SUPPLIERS[product["supplier_id"]]["name"],
                     "qty": stock["qty"], "threshold": stock["threshold"],
                     "value": stock["qty"] * product["unit_cost"]})
    return sorted(rows, key=lambda row: row["name"])


def get_recent_movements(machine_id=None, limit=8):
    moves = [m for m in db.MOVEMENTS if machine_id is None or m["machine_id"] == machine_id]
    return moves[:limit]


# ------------------------------------------------------------------ changing
def _log_movement(machine_id, product_id, tier, old, new, user_name, note):
    """Record who changed what (the audit trail the data model asks for)."""
    db.MOVEMENTS.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "machine_id": machine_id,
        "machine": db.MACHINES[machine_id]["code"] if machine_id else "-",
        "product": db.PRODUCTS[product_id]["name"],
        "tier": tier, "old": old, "new": new, "user": user_name, "note": note,
    })
    del db.MOVEMENTS[200:]  # keep the log from growing forever
    log.info("%s: %s %s %s -> %s (%s)", user_name, tier, db.PRODUCTS[product_id]["name"], old, new, note)


def set_machine_count(machine_id, product_id, qty, user_name):
    """Record a physical count of one product inside a machine.

    This is the manual fallback for the sensor feed named in the proposal.
    """
    row = db.MACHINE_STOCK.get((machine_id, product_id))
    if row is None:
        raise ValueError("That machine does not carry this product.")
    if not 0 <= qty <= row["capacity"]:
        raise ValueError(f"The count must be between 0 and {row['capacity']}.")
    old, row["qty"] = row["qty"], qty
    _log_movement(machine_id, product_id, "Machine", old, qty, user_name, "Manual count")


def restock_visit(machine_id, product_id, units_brought, user_name):
    """Log a restock: fill the machine, top up the drawer, return the rest.

    Returns how the units were split, e.g. {"to_machine": 12, "to_drawer": 6, "to_central": 2}.
    """
    machine_row = db.MACHINE_STOCK.get((machine_id, product_id))
    drawer_row = db.DRAWER_STOCK.get((machine_id, product_id))
    if machine_row is None or drawer_row is None:
        raise ValueError("That machine does not carry this product.")
    if not 1 <= units_brought <= 1000:
        raise ValueError("Units brought must be between 1 and 1000.")

    to_machine, to_drawer, to_central = split_restock(
        units_brought,
        machine_row["capacity"] - machine_row["qty"],
        drawer_row["capacity"] - drawer_row["qty"])

    for tier, row, added in (("Machine", machine_row, to_machine),
                             ("Drawer", drawer_row, to_drawer)):
        if added:
            old = row["qty"]
            row["qty"] += added
            _log_movement(machine_id, product_id, tier, old, row["qty"], user_name, "Restock visit")
    if to_central:
        central = db.CENTRAL_STOCK[product_id]
        old = central["qty"]
        central["qty"] += to_central
        _log_movement(machine_id, product_id, "Central", old, central["qty"], user_name,
                      "Returned after restock visit")
    return {"to_machine": to_machine, "to_drawer": to_drawer, "to_central": to_central}


def set_central_count(product_id, qty, user_name):
    """Record a stock take of the central storage pool."""
    stock = db.CENTRAL_STOCK.get(product_id)
    if stock is None:
        raise ValueError("Unknown product.")
    if not 0 <= qty <= 5000:
        raise ValueError("The count must be between 0 and 5000.")
    old, stock["qty"] = stock["qty"], qty
    _log_movement(None, product_id, "Central", old, qty, user_name, "Stock take")
