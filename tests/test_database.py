"""Database tests: constraints, keys, indexes and the sales window.

These prove the rules are enforced by MySQL itself, not only by the Python code.
Run against MySQL with TEST_DATABASE_URL set (see .env.example); by default they
run on in-memory SQLite, which enforces the same keys and checks.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError, OperationalError

from app import create_app
from app.data import seed_data
from app.extensions import db
from app.models import (CentralStock, DrawerStock, Machine, MachineStock, Sale, StockMovement,
                        Supplier, User)
from app.services import analytics_service, inventory_service


@pytest.fixture
def app():
    """A new app (the testing config builds a fresh database), re-seeded on a fixed date."""
    app = create_app("testing")
    with app.app_context():
        seed_data.seed(today=date(2026, 10, 1))
        yield app
        db.session.remove()


def _fails(change):
    """True if the database refuses the change.

    MySQL reports a broken CHECK constraint as an OperationalError and a broken
    key as an IntegrityError, so both count as "refused".
    """
    try:
        change()
        db.session.commit()
    except (IntegrityError, OperationalError):
        db.session.rollback()
        return True
    return False


# ------------------------------------------------------------------ CHECK constraints
def test_stock_cannot_go_negative_or_above_capacity(app):
    row = db.session.get(MachineStock, (1, 1))
    assert _fails(lambda: setattr(row, "qty", -1))
    row = db.session.get(MachineStock, (1, 1))
    assert _fails(lambda: setattr(row, "qty", row.capacity + 1))
    drawer = db.session.get(DrawerStock, (1, 1))
    assert _fails(lambda: setattr(drawer, "qty", drawer.capacity + 1))
    central = db.session.get(CentralStock, 1)
    assert _fails(lambda: setattr(central, "qty", -5))


def test_role_and_tier_must_be_known_values(app):
    assert _fails(lambda: db.session.add(User(name="X", email="x@y.co", password_hash="h", role="boss")))
    assert _fails(lambda: db.session.add(
        StockMovement(product_id=1, tier="Car", old_qty=0, new_qty=1, note="")))


# ------------------------------------------------------------------ UNIQUE and FOREIGN KEYS
def test_emails_and_machine_codes_are_unique(app):
    assert _fails(lambda: db.session.add(
        User(name="Copy", email="msiza@adlers.test", password_hash="h", role="user")))
    assert _fails(lambda: db.session.add(Machine(code="UP-01", location="Somewhere")))


def test_only_one_sales_total_per_machine_product_and_day(app):
    existing = db.session.scalars(db.select(Sale).limit(1)).first()
    assert _fails(lambda: db.session.add(Sale(machine_id=existing.machine_id, product_id=existing.product_id,
                                              sale_date=existing.sale_date, qty=1)))


def test_stock_must_point_at_a_real_machine_and_product(app):
    assert _fails(lambda: db.session.add(MachineStock(machine_id=999, product_id=1, qty=0, capacity=5, threshold=1)))
    assert _fails(lambda: db.session.add(MachineStock(machine_id=1, product_id=999, qty=0, capacity=5, threshold=1)))


def test_a_supplier_with_products_cannot_be_deleted(app):
    assert _fails(lambda: db.session.delete(db.session.get(Supplier, 1)))


def test_removing_a_machine_removes_its_stock_and_sales(app):
    db.session.execute(db.delete(Machine).where(Machine.machine_id == 12))
    db.session.commit()
    for model in (MachineStock, DrawerStock, Sale):
        left = db.session.scalar(db.select(db.func.count()).select_from(model).where(model.machine_id == 12))
        assert left == 0


# ------------------------------------------------------------------ schema shape
def test_every_table_has_audit_timestamps(app):
    inspector = inspect(db.engine)
    for table in inspector.get_table_names():
        if table == "alembic_version":
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert "created_at" in columns, table
        if table != "stock_movements":          # audit rows are never edited
            assert "updated_at" in columns, table


def test_lookup_indexes_exist(app):
    inspector = inspect(db.engine)
    def indexed(table):
        return [tuple(i["column_names"]) for i in inspector.get_indexes(table)] + \
               [tuple(u["column_names"]) for u in inspector.get_unique_constraints(table)]
    assert ("product_id", "machine_id") in indexed("machine_stock")
    assert ("product_id", "sale_date") in indexed("sales")
    assert ("machine_id", "product_id", "sale_date") in indexed("sales")
    assert ("machine_id", "created_at") in indexed("stock_movements")


# ------------------------------------------------------------------ behaviour that relies on the database
def test_sales_window_ends_on_the_latest_sale_not_today(app):
    first, last, days = analytics_service.sales_window()
    assert last == date(2026, 9, 30) and days == 30
    assert first == last - timedelta(days=29)
    series, _ = analytics_service.fleet_daily_sales()
    assert all(len(s) == 30 for s in series.values())


def test_a_rejected_change_leaves_no_audit_row(app):
    before = db.session.scalar(db.select(db.func.count()).select_from(StockMovement))
    with pytest.raises(ValueError):
        inventory_service.set_machine_count(1, 1, 999, "Mr Msiza")
    after = db.session.scalar(db.select(db.func.count()).select_from(StockMovement))
    assert before == after


def test_a_saved_change_is_audited_with_the_user(app):
    inventory_service.set_central_count(2, 33, "Mr Msiza")
    move = db.session.scalars(db.select(StockMovement).order_by(StockMovement.movement_id.desc())).first()
    assert (move.tier, move.old_qty, move.new_qty, move.user.name) == ("Central", 70, 33, "Mr Msiza")


def test_seeding_twice_gives_the_same_data(app):
    first = [(r.machine_id, r.product_id, r.qty) for r in db.session.scalars(db.select(MachineStock))]
    seed_data.seed(today=date(2026, 10, 1))
    second = [(r.machine_id, r.product_id, r.qty) for r in db.session.scalars(db.select(MachineStock))]
    assert sorted(first) == sorted(second)
