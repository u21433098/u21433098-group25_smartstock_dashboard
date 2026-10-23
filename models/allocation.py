"""Drawer / central-storage allocation logic (objective O3).

PURE PYTHON: no Flask, no database.

Rule used (kept deliberately simple and auditable):
  1. Rank products by turnover (units sold in the trailing window).
  2. Give each product its desired drawer buffer, fastest sellers first, until
     the drawer's total capacity runs out ("greedy by turnover").
  3. Whatever does not fit stays in central storage.

Ties in turnover are broken by product id (ascending) so results are repeatable.
"""


def turnover(daily_sales, window=30):
    """Total units sold in the last `window` days."""
    if window < 1:
        raise ValueError("window must be at least 1 day.")
    return sum(daily_sales[-window:])


def rank_products(turnover_by_product):
    """Return [(product_id, turnover), ...] sorted fastest seller first."""
    return sorted(turnover_by_product.items(), key=lambda item: (-item[1], item[0]))


def priority_label(rank, total):
    """Label a rank as High / Medium / Low (top third, middle third, bottom third).

    Integer arithmetic avoids floating point surprises at the boundaries.
    """
    if total < 1 or rank < 1 or rank > total:
        raise ValueError("rank must be between 1 and total.")
    if rank * 3 <= total:
        return "High"
    if rank * 3 <= 2 * total:
        return "Medium"
    return "Low"


def allocate_drawer(ranked_products, desired_buffer, drawer_capacity):
    """Share limited drawer space between products, fastest sellers first.

    ranked_products : product ids, fastest seller first
    desired_buffer  : {product_id: units we would like in the drawer}
    drawer_capacity : total units the drawer can hold
    Returns {product_id: units allocated to the drawer}.
    """
    if drawer_capacity < 0:
        raise ValueError("drawer_capacity must not be negative.")
    remaining = drawer_capacity
    allocation = {}
    for product_id in ranked_products:
        wanted = max(0, desired_buffer.get(product_id, 0))
        given = min(wanted, remaining)
        allocation[product_id] = given
        remaining -= given
    return allocation


def split_restock(units_brought, machine_space, drawer_space):
    """Split a restock between machine, drawer and central storage.

    Mirrors Mr Msiza's routine: fill the machine first, top up the drawer with
    what is left, and return any remainder to central storage.
    Returns (to_machine, to_drawer, to_central).
    """
    if units_brought < 0 or machine_space < 0 or drawer_space < 0:
        raise ValueError("Inputs must not be negative.")
    to_machine = min(units_brought, machine_space)
    left_over = units_brought - to_machine
    to_drawer = min(left_over, drawer_space)
    to_central = left_over - to_drawer
    return to_machine, to_drawer, to_central
