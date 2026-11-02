"""Glue between the database and the pure supply chain models in /models.

The models only take numbers in and give numbers out; this file collects the
numbers from the database, calls the models, and shapes the results for the
templates.

The 30-day sales window ends on the latest date that has sales recorded (not on
today), so a demo database seeded a week ago still shows a full 30 days.
"""
import math
from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models import CentralStock, DrawerStock, Machine, MachineStock, Product, Sale, Supplier
from app.services.errors import NotFoundError
from models import allocation, procurement, safety_stock


def _cfg(key):
    return current_app.config[key]


# ------------------------------------------------------------ sales window
def sales_window():
    """(first_day, last_day, days) of the trailing sales window, or None if no sales exist."""
    last_day = db.session.scalar(db.select(db.func.max(Sale.sale_date)))
    if last_day is None:
        return None
    days = _cfg("SALES_WINDOW_DAYS")
    return last_day - timedelta(days=days - 1), last_day, days


def _daily_series(group_column, where=None):
    """{key: [units sold on each day of the window]} with 0 for days without a sales row."""
    window = sales_window()
    if window is None:
        return {}, _cfg("SALES_WINDOW_DAYS")
    first_day, last_day, days = window
    query = (db.select(group_column, Sale.sale_date, db.func.sum(Sale.qty))
             .where(Sale.sale_date.between(first_day, last_day))
             .group_by(group_column, Sale.sale_date))
    if where is not None:
        query = query.where(where)
    series = {}
    for key, sale_date, units in db.session.execute(query):
        series.setdefault(key, [0] * days)[(sale_date - first_day).days] = int(units)
    return series, days


def fleet_daily_sales():
    """{product_id: [units sold across ALL machines on each day]} for every product."""
    series, days = _daily_series(Sale.product_id)
    for product_id in db.session.scalars(db.select(Product.product_id)):
        series.setdefault(product_id, [0] * days)
    return series, days


def machine_daily_sales(machine_id):
    """{product_id: [units sold on each day]} for the products this machine carries."""
    series, days = _daily_series(Sale.product_id, Sale.machine_id == machine_id)
    carried = db.session.scalars(db.select(MachineStock.product_id)
                                 .where(MachineStock.machine_id == machine_id))
    return {p: series.get(p, [0] * days) for p in carried}, days


def on_hand_by_product():
    """{product_id: machine + drawer + central units}, summed over the whole fleet."""
    totals = {p: q for p, q in db.session.execute(db.select(CentralStock.product_id, CentralStock.qty))}
    for model in (MachineStock, DrawerStock):
        query = db.select(model.product_id, db.func.sum(model.qty)).group_by(model.product_id)
        for product_id, units in db.session.execute(query):
            totals[product_id] = totals.get(product_id, 0) + int(units)
    return totals


def _products():
    return {p.product_id: p for p in db.session.scalars(db.select(Product))}


# ------------------------------------------------------------ best sellers
def get_best_sellers(limit=5):
    """Top products by units sold in the last 30 days, with a priority label."""
    series, days = fleet_daily_sales()
    names = {p_id: p.name for p_id, p in _products().items()}
    ranked = allocation.rank_products({p: allocation.turnover(s, days) for p, s in series.items()})
    return [{"rank": rank, "product_id": p_id, "name": names[p_id], "turnover": units,
             "per_day": units / days,
             "priority": allocation.priority_label(rank, len(ranked))}
            for rank, (p_id, units) in enumerate(ranked[:limit], start=1)]


# ------------------------------------------------------------ allocation (O3)
def get_allocation(machine_id):
    """Recommended drawer buffer for each product in one machine."""
    machine = db.session.get(Machine, machine_id)
    if machine is None:
        raise NotFoundError(f"Machine {machine_id} does not exist.")
    series, days = machine_daily_sales(machine_id)
    drawers = {d.product_id: d for d in db.session.scalars(
        db.select(DrawerStock).where(DrawerStock.machine_id == machine_id))}
    names = {p_id: p.name for p_id, p in _products().items()}

    ranked = allocation.rank_products({p: allocation.turnover(s, days) for p, s in series.items()})
    desired = {}
    for p_id, sales in series.items():
        wanted = math.ceil(safety_stock.average_daily_demand(sales) * _cfg("BUFFER_DAYS"))
        desired[p_id] = min(wanted, drawers[p_id].capacity)
    plan = allocation.allocate_drawer([p for p, _ in ranked], desired, machine.drawer_capacity)

    rows = []
    for rank, (p_id, units) in enumerate(ranked, start=1):
        current = drawers[p_id].qty
        change = plan[p_id] - current
        if change > 0:
            action, tone = f"Top up by {change}", "primary"
        elif change < 0:
            action, tone = f"Reduce by {-change} (return to central)", "secondary"
        else:
            action, tone = "No change", "success"
        rows.append({"product_id": p_id, "rank": rank, "name": names[p_id], "turnover": units,
                     "priority": allocation.priority_label(rank, len(ranked)),
                     "recommended": plan[p_id], "current": current,
                     "action": action, "tone": tone})
    return {"machine_id": machine_id, "rows": rows, "capacity": machine.drawer_capacity,
            "allocated": sum(plan.values()), "buffer_days": _cfg("BUFFER_DAYS")}


# ------------------------------------------------------------ shopping list (O4)
def build_shopping_list():
    """One consolidated order per supplier, built from all three stock tiers."""
    z, review_days = _cfg("SERVICE_Z"), _cfg("REVIEW_DAYS")
    products = _products()
    suppliers = {s.supplier_id: s for s in db.session.scalars(db.select(Supplier))}
    on_hand_all = on_hand_by_product()
    series_by_product, _days = fleet_daily_sales()
    needs, details = [], {}

    for p_id, series in series_by_product.items():
        product = products[p_id]
        supplier = suppliers[product.supplier_id]
        lead = supplier.lead_time_days

        avg = safety_stock.average_daily_demand(series)
        std = safety_stock.demand_std_dev(series)
        rop = safety_stock.reorder_point(avg, lead, safety_stock.safety_stock(std, lead, z))
        target = procurement.order_up_to_level(avg, std, lead, review_days, z)
        on_hand = on_hand_all.get(p_id, 0)
        qty = procurement.order_quantity(target, on_hand, product.case_size)

        needs.append((supplier.name, product.name, qty))
        details[(supplier.name, product.name)] = {
            "product_id": p_id, "product": product.name, "on_hand": on_hand,
            "reorder_point": round(rop), "target": round(target), "qty": qty,
            "cases": qty // product.case_size, "cost": qty * float(product.unit_cost),
            "urgent": on_hand <= rop}

    lead_by_name = {s.name: s.lead_time_days for s in suppliers.values()}
    groups = []
    for supplier_name, lines in procurement.group_by_supplier(needs).items():
        detail_lines = [details[(supplier_name, product)] for product, _ in lines]
        groups.append({"supplier": supplier_name, "lead_time": lead_by_name[supplier_name],
                       "lines": detail_lines,
                       "total_cost": sum(line["cost"] for line in detail_lines)})
    groups.sort(key=lambda g: g["supplier"])

    n_products = sum(len(g["lines"]) for g in groups)
    return {"groups": groups, "n_products": n_products, "n_suppliers": len(groups),
            "trips_saved": procurement.trips_saved(needs),
            "total_cost": sum(g["total_cost"] for g in groups)}


# ------------------------------------------------------------ KPIs
def get_kpis(alerts, shopping):
    """Numbers for the dashboard cards (feature 7: performance monitoring)."""
    central_value = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(CentralStock.qty * Product.unit_cost), 0))
        .join(Product, Product.product_id == CentralStock.product_id))
    trips, minutes = _cfg("BASELINE_TRIPS_PER_WEEK"), _cfg("MINUTES_PER_TRIP")
    return {
        "machines": db.session.scalar(db.select(db.func.count()).select_from(Machine)),
        "below_threshold": len(alerts),
        "central_value": float(central_value),
        "trips_saved": shopping["trips_saved"],
        "baseline_trips": trips,
        "minutes_per_trip": minutes,
        "baseline_hours": procurement.monthly_travel_hours_saved(trips, minutes, 1.0),
        "target_hours_saved": procurement.monthly_travel_hours_saved(
            trips, minutes, _cfg("TRIP_REDUCTION_TARGET")),
        "reduction_pct": round(_cfg("TRIP_REDUCTION_TARGET") * 100),
    }


def get_dashboard_summary(alert_preview=5, best_seller_count=5):
    """Everything the dashboard shows, in one call (KPIs, top alerts, order summary, best sellers)."""
    from app.services import alert_service
    alerts = alert_service.get_alerts()
    shopping = build_shopping_list()
    window = sales_window()
    return {
        "kpis": get_kpis(alerts, shopping),
        "alerts": alerts[:alert_preview], "total_alerts": len(alerts),
        "order": {k: shopping[k] for k in ("n_products", "n_suppliers", "trips_saved", "total_cost")},
        "best_sellers": get_best_sellers(best_seller_count),
        "sales_window": {"first_day": window[0].isoformat(), "last_day": window[1].isoformat(),
                         "days": window[2]} if window else None,
    }
