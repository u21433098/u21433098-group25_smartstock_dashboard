"""Unit tests for models/safety_stock.py. Expected values were worked out by hand."""
import math

import pytest

from models.safety_stock import (
    average_daily_demand, demand_std_dev, reorder_point, safety_stock,
)

# Worked example: mean = 10; squared deviations = 0+4+4+0+0 = 8;
# sample variance = 8/4 = 2; std dev = sqrt(2) = 1.4142
DEMAND = [10, 12, 8, 10, 10]


def test_average_daily_demand():
    assert average_daily_demand(DEMAND) == 10


def test_average_rejects_empty_list():
    with pytest.raises(ValueError):
        average_daily_demand([])


def test_negative_sales_are_rejected():
    with pytest.raises(ValueError):
        average_daily_demand([5, -1, 3])


def test_std_dev_matches_hand_calculation():
    assert demand_std_dev(DEMAND) == pytest.approx(math.sqrt(2))


def test_std_dev_needs_two_days():
    with pytest.raises(ValueError):
        demand_std_dev([7])


def test_safety_stock_matches_hand_calculation():
    # 1.645 * 1.4142 * sqrt(4) = 4.6528
    assert safety_stock(math.sqrt(2), 4) == pytest.approx(4.6528, abs=1e-3)


def test_safety_stock_is_zero_for_constant_demand():
    assert safety_stock(0, 4) == 0


def test_reorder_point_matches_hand_calculation():
    # 10 * 4 + 4.6528 = 44.6528
    ss = safety_stock(math.sqrt(2), 4)
    assert reorder_point(10, 4, ss) == pytest.approx(44.6528, abs=1e-3)


def test_reorder_point_with_zero_demand_is_zero():
    assert reorder_point(0, 5, 0) == 0
