"""Low-stock alerts across ALL three tiers, not just the machine (feature 6)."""
from app.data import seed_data as db


def _alert(tier, location, machine_id, product_id, row):
    qty = row["qty"]
    return {
        "tier": tier, "location": location, "machine_id": machine_id,
        "product": db.PRODUCTS[product_id]["name"],
        "qty": qty, "threshold": row["threshold"],
        "severity": "Out of stock" if qty == 0 else "Low",
        "tone": "danger" if qty == 0 else "warning",
    }


def get_alerts():
    """Every stock row at or below its threshold, most urgent first."""
    alerts = []
    for (m_id, p_id), row in db.MACHINE_STOCK.items():
        if row["qty"] <= row["threshold"]:
            alerts.append(_alert("Machine", db.MACHINES[m_id]["code"], m_id, p_id, row))
    for (m_id, p_id), row in db.DRAWER_STOCK.items():
        if row["qty"] <= row["threshold"]:
            alerts.append(_alert("Drawer", db.MACHINES[m_id]["code"], m_id, p_id, row))
    for p_id, row in db.CENTRAL_STOCK.items():
        if row["qty"] <= row["threshold"]:
            alerts.append(_alert("Central", "Central storage", None, p_id, row))
    tier_order = {"Machine": 0, "Drawer": 1, "Central": 2}
    alerts.sort(key=lambda a: (a["qty"] != 0, tier_order[a["tier"]], a["location"], a["product"]))
    return alerts
