"""Procurement logic: order quantities and the consolidated supplier list (O4).

PURE PYTHON: no Flask, no database.

Policy: periodic review. Every `review_days` (the weekly supplier run) stock is
topped up to an order-up-to level:

    U = d * (L + R) + z * s * sqrt(L + R)

with d = average daily demand, s = demand std deviation, L = supplier lead time
and R = review period, both in days. The order is the shortfall (U - on hand),
rounded UP to whole cases.
"""
import math

from models.safety_stock import safety_stock


def order_up_to_level(avg_demand, std_dev, lead_time_days, review_days, z=1.645):
    """Order-up-to level U for a periodic-review policy (units)."""
    protection_interval = lead_time_days + review_days
    return avg_demand * protection_interval + safety_stock(std_dev, protection_interval, z)


def order_quantity(target_level, on_hand_total, case_size):
    """Units to order: shortfall rounded UP to whole cases, never negative.

    on_hand_total = machine + drawer + central stock for the product.
    """
    if case_size <= 0:
        raise ValueError("case_size must be positive.")
    shortfall = target_level - on_hand_total
    if shortfall <= 0:
        return 0
    return math.ceil(shortfall / case_size) * case_size


def group_by_supplier(needs):
    """Group order lines by supplier.

    needs: list of (supplier, product, quantity) tuples.
    Returns {supplier: [(product, quantity), ...]} with zero-quantity lines
    removed and each supplier's lines sorted by quantity (largest first).
    """
    grouped = {}
    for supplier, product, quantity in needs:
        if quantity > 0:
            grouped.setdefault(supplier, []).append((product, quantity))
    for lines in grouped.values():
        lines.sort(key=lambda line: (-line[1], line[0]))
    return grouped


def trips_saved(needs):
    """Supplier trips saved by ordering once per supplier instead of per product.

    Before: one trip for every product that needs ordering.
    After : one trip for every supplier that has something to order.
    """
    lines = [(supplier, product) for supplier, product, quantity in needs if quantity > 0]
    return len(lines) - len({supplier for supplier, _ in lines})


def eoq(annual_demand, order_cost, holding_cost):
    """Economic order quantity: sqrt(2 * D * S / H)."""
    if annual_demand <= 0 or order_cost <= 0 or holding_cost <= 0:
        raise ValueError("annual_demand, order_cost and holding_cost must be positive.")
    return math.sqrt(2 * annual_demand * order_cost / holding_cost)


def monthly_travel_hours_saved(trips_per_week, minutes_per_trip, reduction):
    """Hours of driving saved per month if trips fall by `reduction` (0 to 1).

    52 weeks / 12 months = 4.33 weeks per month.
    Example: 2 trips x 60 min = 2 h/week = 8.67 h/month; a 25% cut saves 2.17 h.
    """
    if trips_per_week < 0 or minutes_per_trip < 0 or not 0 <= reduction <= 1:
        raise ValueError("Inputs out of range.")
    hours_per_month = trips_per_week * minutes_per_trip / 60 * 52 / 12
    return hours_per_month * reduction
