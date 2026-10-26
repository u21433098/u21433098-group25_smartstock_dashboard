"""Glue between the data and the pure supply chain models in /models.

The models only take numbers in and give numbers out; this file collects the
numbers from the data tables, calls the models, and shapes the results for the
templates.
"""
import math

from flask import current_app

from app.data import seed_data as db
from models import allocation, procurement, safety_stock


def _cfg(key):
    return current_app.config[key]


def fleet_daily_sales():
    """{product_id: [units sold across ALL machines on each of the last 30 days]}."""
    series = {p_id: [0] * db.DAYS for p_id in db.PRODUCTS}
    for (_m_id, p_id), sales in db.SALES.items():
        for day, units in enumerate(sales):
            series[p_id][day] += units
    return series


def on_hand_total(product_id):
    """Machine + drawer + central stock for one product."""
    total = db.CENTRAL_STOCK[product_id]["qty"]
    total += sum(r["qty"] for (m, p), r in db.MACHINE_STOCK.items() if p == product_id)
    total += sum(r["qty"] for (m, p), r in db.DRAWER_STOCK.items() if p == product_id)
    return total


# ------------------------------------------------------------ best sellers
def get_best_sellers(limit=5):
    """Top products by units sold in the last 30 days, with a priority label."""
    turnover_by_product = {p_id: allocation.turnover(s, db.DAYS)
                           for p_id, s in fleet_daily_sales().items()}
    ranked = allocation.rank_products(turnover_by_product)
    return [{"rank": rank, "name": db.PRODUCTS[p_id]["name"], "turnover": units,
             "per_day": units / db.DAYS,
             "priority": allocation.priority_label(rank, len(ranked))}
            for rank, (p_id, units) in enumerate(ranked[:limit], start=1)]


# ------------------------------------------------------------ allocation (O3)
def get_allocation(machine_id):
    """Recommended drawer buffer for each product in one machine."""
    series = {p: s for (m, p), s in db.SALES.items() if m == machine_id}
    turnover_by_product = {p: allocation.turnover(s, db.DAYS) for p, s in series.items()}
    ranked = allocation.rank_products(turnover_by_product)

    desired = {}
    for p_id, sales in series.items():
        wanted = math.ceil(safety_stock.average_daily_demand(sales) * _cfg("BUFFER_DAYS"))
        desired[p_id] = min(wanted, db.DRAWER_STOCK[(machine_id, p_id)]["capacity"])
    plan = allocation.allocate_drawer([p for p, _ in ranked], desired, _cfg("DRAWER_TOTAL_CAPACITY"))

    rows = []
    for rank, (p_id, units) in enumerate(ranked, start=1):
        current = db.DRAWER_STOCK[(machine_id, p_id)]["qty"]
        change = plan[p_id] - current
        if change > 0:
            action, tone = f"Top up by {change}", "primary"
        elif change < 0:
            action, tone = f"Reduce by {-change} (return to central)", "secondary"
        else:
            action, tone = "No change", "success"
        rows.append({"product_id": p_id, "rank": rank, "name": db.PRODUCTS[p_id]["name"], "turnover": units,
                     "priority": allocation.priority_label(rank, len(ranked)),
                     "recommended": plan[p_id], "current": current,
                     "action": action, "tone": tone})
    return {"rows": rows, "capacity": _cfg("DRAWER_TOTAL_CAPACITY"),
            "allocated": sum(plan.values()), "buffer_days": _cfg("BUFFER_DAYS")}


# ------------------------------------------------------------ shopping list (O4)
def build_shopping_list():
    """One consolidated order per supplier, built from all three stock tiers."""
    z, review_days = _cfg("SERVICE_Z"), _cfg("REVIEW_DAYS")
    needs, details = [], {}

    for p_id, series in fleet_daily_sales().items():
        product = db.PRODUCTS[p_id]
        supplier = db.SUPPLIERS[product["supplier_id"]]
        lead = supplier["lead_time_days"]

        avg = safety_stock.average_daily_demand(series)
        std = safety_stock.demand_std_dev(series)
        rop = safety_stock.reorder_point(avg, lead, safety_stock.safety_stock(std, lead, z))
        target = procurement.order_up_to_level(avg, std, lead, review_days, z)
        on_hand = on_hand_total(p_id)
        qty = procurement.order_quantity(target, on_hand, product["case_size"])

        needs.append((supplier["name"], product["name"], qty))
        details[(supplier["name"], product["name"])] = {
            "product": product["name"], "on_hand": on_hand, "reorder_point": round(rop),
            "target": round(target), "qty": qty, "cases": qty // product["case_size"],
            "cost": qty * product["unit_cost"], "urgent": on_hand <= rop}

    groups = []
    for supplier_name, lines in procurement.group_by_supplier(needs).items():
        detail_lines = [details[(supplier_name, product)] for product, _ in lines]
        lead = next(s["lead_time_days"] for s in db.SUPPLIERS.values() if s["name"] == supplier_name)
        groups.append({"supplier": supplier_name, "lead_time": lead, "lines": detail_lines,
                       "total_cost": sum(line["cost"] for line in detail_lines)})
    groups.sort(key=lambda g: g["supplier"])

    n_products = sum(len(g["lines"]) for g in groups)
    return {"groups": groups, "n_products": n_products, "n_suppliers": len(groups),
            "trips_saved": procurement.trips_saved(needs),
            "total_cost": sum(g["total_cost"] for g in groups)}


# ------------------------------------------------------------ KPIs
def get_kpis(alerts, shopping):
    """Numbers for the dashboard cards (feature 7: performance monitoring)."""
    central_value = sum(s["qty"] * db.PRODUCTS[p]["unit_cost"] for p, s in db.CENTRAL_STOCK.items())
    trips, minutes = _cfg("BASELINE_TRIPS_PER_WEEK"), _cfg("MINUTES_PER_TRIP")
    return {
        "machines": len(db.MACHINES),
        "below_threshold": len(alerts),
        "central_value": central_value,
        "trips_saved": shopping["trips_saved"],
        "baseline_trips": trips,
        "minutes_per_trip": minutes,
        "baseline_hours": procurement.monthly_travel_hours_saved(trips, minutes, 1.0),
        "target_hours_saved": procurement.monthly_travel_hours_saved(
            trips, minutes, _cfg("TRIP_REDUCTION_TARGET")),
        "reduction_pct": round(_cfg("TRIP_REDUCTION_TARGET") * 100),
    }
