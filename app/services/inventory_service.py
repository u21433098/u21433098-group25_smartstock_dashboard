"""Reading and changing stock in the three tiers: machine, drawer, central storage.

Every function returns plain dictionaries (numbers, text and ISO dates only), so the
templates and the JSON API never depend on how the data is stored.

The list_* functions take the raw query-string values (page, per_page, sort and
filters), check them, and return a page envelope:
    {"items": [...], "page": 1, "per_page": 20, "total": 37, "pages": 2, "has_prev": False, "has_next": True}

Errors are raised as ValidationError (400), NotFoundError (404) and so on from
app/services/errors.py; all of them are ValueErrors.
"""
import logging
from datetime import timedelta

from app.extensions import db
from flask_login import current_user

from app.models import (CentralStock, DrawerStock, Machine, MachineStock, Product, StockMovement,
                        Supplier, User)
from app.services import alert_service, analytics_service
from app.services.errors import NotFoundError, ValidationError
from app.services.pagination import (paginate_list, paginate_query, parse_choice, parse_date,
                                     parse_int, parse_sort, sort_list)
from models.allocation import split_restock

log = logging.getLogger(__name__)

MAX_UNITS_BROUGHT = 1000
MAX_CENTRAL_COUNT = 5000


def _machine_dict(machine):
    return {"id": machine.machine_id, "code": machine.code, "location": machine.location,
            "drawer_capacity": machine.drawer_capacity}


def _stock_dict(row):
    return {"qty": row.qty, "capacity": getattr(row, "capacity", None), "threshold": row.threshold}


# ------------------------------------------------------------------ reading
def get_machines():
    return [_machine_dict(m) for m in db.session.scalars(db.select(Machine).order_by(Machine.machine_id))]


def get_machine(machine_id):
    machine = db.session.get(Machine, machine_id)
    return _machine_dict(machine) if machine else None


def get_machine_rows(machine_id):
    """One row per product the machine carries, combining all three tiers (O2)."""
    query = (db.select(Product, MachineStock, DrawerStock, CentralStock)
             .join(MachineStock, MachineStock.product_id == Product.product_id)
             .join(DrawerStock, (DrawerStock.machine_id == MachineStock.machine_id)
                   & (DrawerStock.product_id == MachineStock.product_id))
             .join(CentralStock, CentralStock.product_id == Product.product_id)
             .where(MachineStock.machine_id == machine_id)
             .order_by(Product.name))
    return [{"product_id": product.product_id, "name": product.name,
             "machine": _stock_dict(machine), "drawer": _stock_dict(drawer),
             "central": _stock_dict(central)}
            for product, machine, drawer, central in db.session.execute(query)]


def get_central_rows():
    query = (db.select(Product, Supplier, CentralStock)
             .join(Supplier, Supplier.supplier_id == Product.supplier_id)
             .join(CentralStock, CentralStock.product_id == Product.product_id)
             .order_by(Product.name))
    return [{"product_id": product.product_id, "name": product.name,
             "supplier_id": supplier.supplier_id, "supplier": supplier.name,
             "unit_cost": float(product.unit_cost), "qty": stock.qty, "threshold": stock.threshold,
             "value": stock.qty * float(product.unit_cost)}
            for product, supplier, stock in db.session.execute(query)]


def require_machine(machine_id):
    """Return the machine as a dict, or raise NotFoundError."""
    machine = get_machine(machine_id)
    if machine is None:
        raise NotFoundError(f"Machine {machine_id} does not exist.")
    return machine


def get_machine_detail(machine_id):
    """One machine with its three-tier stock rows (for GET /machines/<id>)."""
    return {**require_machine(machine_id), "products": get_machine_rows(machine_id)}


# ------------------------------------------------------------------ lists for the API (filter, sort, page)
MACHINE_SORTS = {"code", "location", "alerts"}
CENTRAL_SORTS = {"name", "supplier", "qty", "value"}
TIER_CHOICES = ("Machine", "Drawer", "Central")


def list_machines(search=None, sort=None, page=None, per_page=None):
    """Machines with their open alert count. `search` matches the code or location."""
    key, descending = parse_sort(sort, MACHINE_SORTS, "code")
    alert_counts = {}
    for alert in alert_service.get_alerts():
        if alert["machine_id"]:
            alert_counts[alert["machine_id"]] = alert_counts.get(alert["machine_id"], 0) + 1
    rows = [{**m, "alerts": alert_counts.get(m["id"], 0)} for m in get_machines()]
    if search:
        needle = search.strip().lower()
        rows = [m for m in rows if needle in m["code"].lower() or needle in m["location"].lower()]
    return paginate_list(sort_list(rows, key, descending), page, per_page)


def list_central(search=None, supplier_id=None, low_only=False, sort=None, page=None, per_page=None):
    """Central storage rows. Filters: product name text, supplier, only items at/below threshold."""
    key, descending = parse_sort(sort, CENTRAL_SORTS, "name")
    supplier_id = parse_int(supplier_id, "supplier_id", minimum=1)
    rows = get_central_rows()
    if search:
        rows = [r for r in rows if search.strip().lower() in r["name"].lower()]
    if supplier_id is not None:
        rows = [r for r in rows if r["supplier_id"] == supplier_id]
    if low_only:
        rows = [r for r in rows if r["qty"] <= r["threshold"]]
    return paginate_list(sort_list(rows, key, descending), page, per_page)


def _movement_dict(row):
    m = row[0]
    return {"id": m.movement_id, "time": m.created_at.strftime("%Y-%m-%d %H:%M"),
            "created_at": m.created_at.isoformat(timespec="seconds"),
            "machine_id": m.machine_id, "machine": m.machine.code if m.machine else "-",
            "product_id": m.product_id, "product": m.product.name, "tier": m.tier,
            "old": m.old_qty, "new": m.new_qty, "change": m.new_qty - m.old_qty,
            "user": m.user.name if m.user else "(deleted user)", "note": m.note}


def list_movements(machine_id=None, product_id=None, tier=None, date_from=None, date_to=None,
                   page=None, per_page=None):
    """The audit trail, newest first, filtered in the database and paged with LIMIT/OFFSET."""
    machine_id = parse_int(machine_id, "machine_id", minimum=1)
    product_id = parse_int(product_id, "product_id", minimum=1)
    tier = parse_choice(tier, "tier", TIER_CHOICES)
    date_from, date_to = parse_date(date_from, "date_from"), parse_date(date_to, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("date_from must be on or before date_to.", "date_from")

    query = db.select(StockMovement).order_by(StockMovement.created_at.desc(),
                                              StockMovement.movement_id.desc())
    if machine_id is not None:
        query = query.where(StockMovement.machine_id == machine_id)
    if product_id is not None:
        query = query.where(StockMovement.product_id == product_id)
    if tier:
        query = query.where(StockMovement.tier == tier)
    if date_from:
        query = query.where(StockMovement.created_at >= date_from)
    if date_to:
        query = query.where(StockMovement.created_at < date_to + timedelta(days=1))
    return paginate_query(query, _movement_dict, page, per_page)


def get_recent_movements(machine_id=None, limit=8):
    """Newest stock changes first, optionally for one machine only."""
    query = db.select(StockMovement).order_by(StockMovement.created_at.desc(),
                                              StockMovement.movement_id.desc())
    if machine_id is not None:
        query = query.where(StockMovement.machine_id == machine_id)
    return [{"time": m.created_at.strftime("%Y-%m-%d %H:%M"),
             "machine_id": m.machine_id,
             "machine": m.machine.code if m.machine else "-",
             "product": m.product.name, "tier": m.tier, "old": m.old_qty, "new": m.new_qty,
             "user": m.user.name if m.user else "(deleted user)", "note": m.note}
            for m in db.session.scalars(query.limit(limit))]


# ------------------------------------------------------------------ changing
def _user_id(user_name):
    """Find the user_id to store in the audit trail.

    Routes pass the logged-in user's name; the logged-in user's id is used when it
    matches, otherwise the account with that name (None if there is no such account).
    """
    if getattr(current_user, "is_authenticated", False) and current_user.name == user_name:
        return int(current_user.id)
    return db.session.scalar(db.select(User.user_id).where(User.name == user_name).limit(1))


def _log_movement(machine_id, product_id, tier, old, new, user_name, note):
    """Record who changed what (the audit trail). Saved in the same transaction as the change."""
    db.session.add(StockMovement(machine_id=machine_id, product_id=product_id,
                                 user_id=_user_id(user_name),
                                 tier=tier, old_qty=old, new_qty=new, note=note))
    log.info("%s: %s product %s %s -> %s (%s)", user_name, tier, product_id, old, new, note)


def _locked(model, key):
    """Read one stock row and lock it until commit, so two people saving at once cannot
    overwrite each other's change (SELECT ... FOR UPDATE in MySQL)."""
    return db.session.get(model, key, with_for_update=True)


def set_machine_count(machine_id, product_id, qty, user_name):
    """Record a physical count of one product inside a machine.

    This is the manual fallback for the sensor feed named in the proposal.
    """
    row = _locked(MachineStock, (machine_id, product_id))
    if row is None:
        raise NotFoundError("That machine does not carry this product.", "product_id")
    if not 0 <= qty <= row.capacity:
        db.session.rollback()
        raise ValidationError(f"The count must be between 0 and {row.capacity}.", "qty")
    old, row.qty = row.qty, qty
    _log_movement(machine_id, product_id, "Machine", old, qty, user_name, "Manual count")
    db.session.commit()


def restock_visit(machine_id, product_id, units_brought, user_name):
    """Log a restock visit, the way Mr Msiza works:

    1. take the units out of central storage (the bulk box),
    2. fill the machine, then top up the drawer,
    3. return whatever is left to central storage.

    Central storage therefore only goes down by what went into the machine and the drawer,
    and a visit can never take more than central storage holds.
    Returns how the units were split, e.g. {"to_machine": 12, "to_drawer": 6, "to_central": 2}
    ("to_central" is the number returned).
    """
    if not 1 <= units_brought <= MAX_UNITS_BROUGHT:
        raise ValidationError(f"Units taken must be between 1 and {MAX_UNITS_BROUGHT}.", "units")
    if db.session.get(MachineStock, (machine_id, product_id)) is None:
        raise NotFoundError("That machine does not carry this product.", "product_id")

    # The drawer is only topped up to the Allocation page's recommendation,
    # and never past the drawer's total capacity.
    plan = analytics_service.get_allocation(machine_id)
    recommended = next(r["recommended"] for r in plan["rows"] if r["product_id"] == product_id)

    # Lock central first: the units come out of it, so two visits at once cannot
    # both take the same stock.
    central = _locked(CentralStock, product_id)
    if central.qty < units_brought:
        db.session.rollback()
        raise ValidationError(
            f"Central storage only holds {central.qty} of this product, so {units_brought} "
            "cannot be taken. Record the supplier delivery on the Central storage page first.",
            "units")
    machine_row = _locked(MachineStock, (machine_id, product_id))
    drawer_row = _locked(DrawerStock, (machine_id, product_id))
    drawer_total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(DrawerStock.qty), 0))
        .where(DrawerStock.machine_id == machine_id))
    drawer_space = max(0, min(recommended - drawer_row.qty,
                              plan["capacity"] - drawer_total,
                              drawer_row.capacity - drawer_row.qty))

    to_machine, to_drawer, to_central = split_restock(
        units_brought, machine_row.capacity - machine_row.qty, drawer_space)

    for tier, row, added in (("Machine", machine_row, to_machine), ("Drawer", drawer_row, to_drawer)):
        if added:
            old = row.qty
            row.qty += added
            _log_movement(machine_id, product_id, tier, old, row.qty, user_name, "Restock visit")
    used = to_machine + to_drawer
    if used:
        old = central.qty
        central.qty -= used
        _log_movement(machine_id, product_id, "Central", old, central.qty, user_name,
                      f"Restock visit: {units_brought} taken, {to_central} returned")
    db.session.commit()
    return {"to_machine": to_machine, "to_drawer": to_drawer, "to_central": to_central}


def set_central_count(product_id, qty, user_name):
    """Record a stock take of the central storage pool."""
    stock = _locked(CentralStock, product_id)
    if stock is None:
        raise NotFoundError("Unknown product.", "product_id")
    if not 0 <= qty <= MAX_CENTRAL_COUNT:
        db.session.rollback()
        raise ValidationError(f"The count must be between 0 and {MAX_CENTRAL_COUNT}.", "qty")
    old, stock.qty = stock.qty, qty
    _log_movement(None, product_id, "Central", old, qty, user_name, "Stock take")
    db.session.commit()
