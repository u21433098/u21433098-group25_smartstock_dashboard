"""Low-stock alerts across ALL three tiers, not just the machine (feature 6)."""
from app.extensions import db
from app.models import CentralStock, DrawerStock, Machine, MachineStock, Product
from app.services.pagination import paginate_list, parse_choice, parse_int

TIER_ORDER = {"Machine": 0, "Drawer": 1, "Central": 2}


def _alert(tier, location, machine_id, product, row):
    return {
        "tier": tier, "location": location, "machine_id": machine_id,
        "product_id": product.product_id, "product": product.name,
        "qty": row.qty, "threshold": row.threshold,
        "severity": "Out of stock" if row.qty == 0 else "Low",
        "tone": "danger" if row.qty == 0 else "warning",
    }


def get_alerts():
    """Every stock row at or below its threshold, most urgent first."""
    alerts = []
    for tier, model in (("Machine", MachineStock), ("Drawer", DrawerStock)):
        query = (db.select(model, Machine, Product)
                 .join(Machine, Machine.machine_id == model.machine_id)
                 .join(Product, Product.product_id == model.product_id)
                 .where(model.qty <= model.threshold))
        for row, machine, product in db.session.execute(query):
            alerts.append(_alert(tier, machine.code, machine.machine_id, product, row))

    query = (db.select(CentralStock, Product)
             .join(Product, Product.product_id == CentralStock.product_id)
             .where(CentralStock.qty <= CentralStock.threshold))
    for row, product in db.session.execute(query):
        alerts.append(_alert("Central", "Central storage", None, product, row))

    alerts.sort(key=lambda a: (a["qty"] != 0, TIER_ORDER[a["tier"]], a["location"], a["product"]))
    return alerts


def list_alerts(tier=None, severity=None, machine_id=None, page=None, per_page=None):
    """Alerts filtered by tier (Machine/Drawer/Central), severity (out/low) and machine, then paged."""
    tier = parse_choice(tier, "tier", tuple(TIER_ORDER))
    severity = parse_choice(severity, "severity", ("out", "low"))
    machine_id = parse_int(machine_id, "machine_id", minimum=1)
    alerts = get_alerts()
    if tier:
        alerts = [a for a in alerts if a["tier"] == tier]
    if severity:
        alerts = [a for a in alerts if (a["qty"] == 0) == (severity == "out")]
    if machine_id is not None:
        alerts = [a for a in alerts if a["machine_id"] == machine_id]
    return paginate_list(alerts, page, per_page)
