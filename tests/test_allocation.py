"""Unit tests for models/allocation.py."""
import pytest

from models.allocation import (
    allocate_drawer, priority_label, rank_products, split_restock, turnover,
)


def test_turnover_uses_only_the_trailing_window():
    assert turnover([1, 2, 3, 4, 5], window=3) == 12  # 3 + 4 + 5


def test_turnover_with_short_history_uses_all_days():
    assert turnover([4, 6], window=30) == 10


def test_rank_products_fastest_first_with_ties_broken_by_id():
    ranked = rank_products({1: 50, 2: 80, 3: 80})
    assert ranked == [(2, 80), (3, 80), (1, 50)]


def test_priority_labels_split_into_thirds():
    assert priority_label(1, 9) == "High"
    assert priority_label(3, 9) == "High"
    assert priority_label(4, 9) == "Medium"
    assert priority_label(6, 9) == "Medium"
    assert priority_label(7, 9) == "Low"


def test_priority_label_rejects_bad_rank():
    with pytest.raises(ValueError):
        priority_label(10, 9)


def test_allocate_drawer_gives_fast_sellers_priority():
    plan = allocate_drawer([2, 3, 1], {1: 10, 2: 10, 3: 10}, drawer_capacity=25)
    assert plan == {2: 10, 3: 10, 1: 5}


def test_allocate_drawer_never_exceeds_capacity():
    plan = allocate_drawer([1, 2, 3], {1: 50, 2: 50, 3: 50}, drawer_capacity=40)
    assert sum(plan.values()) == 40
    assert plan[1] == 40 and plan[3] == 0


def test_allocate_drawer_ignores_negative_requests():
    assert allocate_drawer([1], {1: -5}, 10) == {1: 0}


def test_split_restock_fills_machine_then_drawer_then_central():
    assert split_restock(30, machine_space=12, drawer_space=10) == (12, 10, 8)


def test_split_restock_small_delivery_all_goes_to_machine():
    assert split_restock(5, machine_space=12, drawer_space=10) == (5, 0, 0)


def test_split_restock_full_machine_goes_to_drawer():
    assert split_restock(8, machine_space=0, drawer_space=10) == (0, 8, 0)
