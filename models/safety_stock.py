"""Safety stock and reorder point calculations.

PURE PYTHON: this module imports nothing from Flask or the data layer, so it can
be tested on its own (see tests/test_safety_stock.py).

Formulas (standard textbook inventory theory; see Barros et al. 2021 and
Goncalves et al. 2020 in the proposal references):

    average daily demand      d  = mean(daily sales)
    demand std deviation      s  = sample standard deviation of daily sales
    safety stock              SS = z * s * sqrt(L)
    reorder point             ROP = d * L + SS

where L is the supplier lead time in days and z is the service-level factor
(1.645 gives a 95% service level).

Assumptions: daily demand is roughly normal, independent from day to day, and
the supplier lead time is fixed.
"""
import math
import statistics

Z_95 = 1.645  # z-value for a 95% cycle service level


def _check_sales(daily_sales, minimum):
    """Shared input validation for the demand functions."""
    if len(daily_sales) < minimum:
        raise ValueError(f"At least {minimum} day(s) of sales data are required.")
    if any(day < 0 for day in daily_sales):
        raise ValueError("Daily sales cannot be negative.")


def average_daily_demand(daily_sales):
    """Return the mean daily demand (units/day) from a list of daily sales."""
    _check_sales(daily_sales, 1)
    return sum(daily_sales) / len(daily_sales)


def demand_std_dev(daily_sales):
    """Return the SAMPLE standard deviation of daily demand (units/day)."""
    _check_sales(daily_sales, 2)  # a standard deviation needs at least two points
    return statistics.stdev(daily_sales)


def safety_stock(std_dev, lead_time_days, z=Z_95):
    """Return safety stock in units: SS = z * std_dev * sqrt(lead_time_days)."""
    if std_dev < 0 or lead_time_days < 0 or z < 0:
        raise ValueError("std_dev, lead_time_days and z must not be negative.")
    return z * std_dev * math.sqrt(lead_time_days)


def reorder_point(avg_demand, lead_time_days, safety_stock_units):
    """Return the reorder point in units: ROP = avg_demand * lead_time + SS.

    When total stock on hand drops to this level, an order should be placed.
    """
    if avg_demand < 0 or lead_time_days < 0 or safety_stock_units < 0:
        raise ValueError("Inputs must not be negative.")
    return avg_demand * lead_time_days + safety_stock_units
