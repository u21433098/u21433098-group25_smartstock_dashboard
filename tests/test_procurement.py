"""Unit tests for models/procurement.py."""
import pytest

from models.procurement import (
    eoq, group_by_supplier, monthly_travel_hours_saved, order_quantity,
    order_up_to_level, trips_saved,
)


def test_order_up_to_level_matches_hand_calculation():
    # d=10, s=2, L=2, R=7 -> 10*9 + 1.645*2*sqrt(9) = 90 + 9.87 = 99.87
    assert order_up_to_level(10, 2, 2, 7) == pytest.approx(99.87, abs=1e-2)


def test_order_quantity_rounds_up_to_whole_cases():
    # shortfall 70, case 24 -> 3 cases -> 72
    assert order_quantity(100, 30, 24) == 72


def test_order_quantity_exact_multiple_is_not_rounded_further():
    assert order_quantity(100, 52, 24) == 48


def test_order_quantity_is_zero_when_stock_is_above_target():
    assert order_quantity(100, 130, 24) == 0


def test_order_quantity_rejects_bad_case_size():
    with pytest.raises(ValueError):
        order_quantity(100, 0, 0)


NEEDS = [
    ("Supplier A", "Coca-Cola", 24), ("Supplier A", "Fanta", 12),
    ("Supplier B", "Chips", 20), ("Supplier B", "Bar One", 18),
    ("Supplier C", "Water", 30), ("Supplier C", "Sprite", 0),
]


def test_group_by_supplier_drops_zero_lines_and_sorts_largest_first():
    grouped = group_by_supplier(NEEDS)
    assert list(grouped) == ["Supplier A", "Supplier B", "Supplier C"]
    assert grouped["Supplier A"] == [("Coca-Cola", 24), ("Fanta", 12)]
    assert grouped["Supplier C"] == [("Water", 30)]


def test_trips_saved_is_products_minus_suppliers():
    # 5 products to order, 3 suppliers to visit -> 2 trips saved
    assert trips_saved(NEEDS) == 2


def test_trips_saved_is_zero_with_nothing_to_order():
    assert trips_saved([("A", "x", 0)]) == 0


def test_eoq_matches_hand_calculation():
    # sqrt(2 * 1200 * 50 / 2) = sqrt(60000) = 244.95
    assert eoq(1200, 50, 2) == pytest.approx(244.95, abs=1e-2)


def test_eoq_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        eoq(0, 50, 2)


def test_monthly_travel_hours_baseline_and_saving():
    # 2 trips x 60 min = 2 h/week = 8.67 h/month; a 25% cut saves 2.17 h/month
    assert monthly_travel_hours_saved(2, 60, 1.0) == pytest.approx(8.667, abs=1e-3)
    assert monthly_travel_hours_saved(2, 60, 0.25) == pytest.approx(2.167, abs=1e-3)
