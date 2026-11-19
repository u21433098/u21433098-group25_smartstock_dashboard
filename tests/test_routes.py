"""Integration tests: pages, login, and the stock-changing forms.

Each test gets a brand-new app (and fresh demo data) from the `app` fixture.
"""
import pytest

from app import create_app
from app.data import seed_data
from app.extensions import db
from app.models import CentralStock, DrawerStock, Machine, MachineStock, Product, Sale

EMAIL, PASSWORD = "msiza@adlers.test", "SmartStock123"


@pytest.fixture
def app():
    """A new app. The testing configuration builds and seeds a fresh database for it."""
    app = create_app("testing")
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": EMAIL, "password": PASSWORD})
    return client


def qty(model, *key):
    """Current quantity of one stock row, read fresh from the database."""
    db.session.expire_all()
    return db.session.get(model, key if len(key) > 1 else key[0]).qty


def total_stock(product_id):
    """Machine + drawer + central units of one product, summed over the whole fleet."""
    db.session.expire_all()
    total = db.session.get(CentralStock, product_id).qty
    for model in (MachineStock, DrawerStock):
        total += db.session.scalar(db.select(db.func.sum(model.qty)).where(model.product_id == product_id))
    return total


# ------------------------------------------------------------------ seed data sanity
def test_seed_data_is_complete_and_consistent(app):
    count = lambda model: db.session.scalar(db.select(db.func.count()).select_from(model))
    assert count(Machine) == 12 and count(Product) == 15
    sold = set(db.session.scalars(db.select(MachineStock.product_id).distinct()))
    assert sold == set(db.session.scalars(db.select(Product.product_id)))  # every product is sold somewhere
    for row in db.session.scalars(db.select(MachineStock)):
        assert db.session.get(DrawerStock, (row.machine_id, row.product_id)) is not None
        days = db.session.scalar(db.select(db.func.count()).select_from(Sale).where(
            Sale.machine_id == row.machine_id, Sale.product_id == row.product_id))
        assert days == seed_data.DAYS


# ------------------------------------------------------------------ login and access
def test_pages_redirect_to_login_when_logged_out(client):
    for url in ("/", "/machines", "/allocation", "/shopping-list", "/alerts", "/central"):
        response = client.get(url)
        assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_login_and_register_pages_load(client):
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_login_with_correct_details_shows_dashboard(client):
    response = client.post("/login", data={"email": EMAIL, "password": PASSWORD}, follow_redirects=True)
    assert response.status_code == 200 and b"SmartStock dashboard" in response.data


def test_login_with_wrong_password_is_rejected(client):
    response = client.post("/login", data={"email": EMAIL, "password": "wrong"})
    assert b"Incorrect email or password" in response.data


def test_login_will_not_redirect_to_another_site(client):
    response = client.post("/login?next=//evil.example", data={"email": EMAIL, "password": PASSWORD})
    assert "evil.example" not in response.headers["Location"]


def test_register_then_login(client):
    client.post("/register", data={"name": "Test User", "email": "new@adlers.test",
                                   "password": "longenough1", "confirm": "longenough1"})
    response = client.post("/login", data={"email": "new@adlers.test", "password": "longenough1"},
                           follow_redirects=True)
    assert b"SmartStock dashboard" in response.data


def test_register_rejects_short_password_and_duplicate_email(client):
    short = client.post("/register", data={"name": "A", "email": "a@b.co", "password": "short", "confirm": "short"})
    assert b"at least 8 characters" in short.data
    dup = client.post("/register", data={"name": "A", "email": EMAIL, "password": "longenough1", "confirm": "longenough1"})
    assert b"already exists" in dup.data


def test_forms_are_rejected_without_a_csrf_token(app):
    app.config["CSRF_ENABLED"] = True
    response = app.test_client().post("/login", data={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 400


# ------------------------------------------------------------------ pages
def test_main_pages_load_when_logged_in(logged_in):
    for url in ("/", "/machines", "/machines/1", "/central", "/allocation", "/allocation?machine=3",
                "/shopping-list", "/alerts"):
        assert logged_in.get(url).status_code == 200, url


def test_unknown_pages_return_404(logged_in):
    assert logged_in.get("/machines/999").status_code == 404
    assert logged_in.get("/allocation?machine=999").status_code == 404
    assert logged_in.get("/no-such-page").status_code == 404


def test_alerts_page_lists_the_seeded_out_of_stock_water(logged_in):
    html = logged_in.get("/alerts").data
    assert b"UP-05" in html and b"Out of stock" in html


def test_shopping_list_is_grouped_by_supplier(logged_in):
    html = logged_in.get("/shopping-list").data
    assert b"Supplier A" in html and b"Trips saved" in html


# ------------------------------------------------------------------ flow 1: count -> alert
def test_machine_count_updates_stock_and_raises_an_alert(logged_in):
    before = len(logged_in.get("/alerts").data)
    logged_in.post("/machines/2/count", data={"product_id": 1, "qty": 0})
    assert qty(MachineStock, 2, 1) == 0
    assert b"UP-02" in logged_in.get("/alerts").data
    assert len(logged_in.get("/alerts").data) > before


def test_machine_count_outside_capacity_is_rejected(logged_in):
    old = qty(MachineStock, 2, 1)
    response = logged_in.post("/machines/2/count", data={"product_id": 1, "qty": 999}, follow_redirects=True)
    assert b"between 0 and" in response.data and qty(MachineStock, 2, 1) == old


def test_machine_count_rejects_text_instead_of_a_number(logged_in):
    response = logged_in.post("/machines/2/count", data={"product_id": 1, "qty": "abc"}, follow_redirects=True)
    assert b"whole number" in response.data


# ------------------------------------------------------------------ flow 2: restock visit
def test_restock_visit_splits_units_across_the_tiers(logged_in):
    before = total_stock(1)
    logged_in.post("/machines/2/restock", data={"product_id": 1, "units": 40})
    assert total_stock(1) == before + 40                      # nothing lost or invented
    assert qty(MachineStock, 2, 1) <= db.session.get(MachineStock, (2, 1)).capacity
    assert qty(DrawerStock, 2, 1) <= db.session.get(DrawerStock, (2, 1)).capacity


def test_restock_is_written_to_the_audit_trail(logged_in):
    logged_in.post("/machines/2/restock", data={"product_id": 1, "units": 5})
    assert b"Restock visit" in logged_in.get("/machines/2").data


def test_central_stock_take_updates_the_pool(logged_in):
    logged_in.post("/central/1", data={"qty": 123})
    assert qty(CentralStock, 1) == 123


# ------------------------------------------------------------------ flow 3: shopping list responds to stock
def test_shopping_list_orders_less_after_a_big_delivery(logged_in):
    from app.services import analytics_service
    with logged_in.application.test_request_context():
        before = analytics_service.build_shopping_list()["total_cost"]
    logged_in.post("/central/1", data={"qty": 5000})
    with logged_in.application.test_request_context():
        after = analytics_service.build_shopping_list()["total_cost"]
    assert after < before


def test_restock_never_overfills_the_drawer(logged_in):
    for product_id in list(db.session.scalars(db.select(DrawerStock.product_id).where(DrawerStock.machine_id == 2))):
        logged_in.post("/machines/2/restock", data={"product_id": product_id, "units": 100})
    db.session.expire_all()
    drawer_total = db.session.scalar(db.select(db.func.sum(DrawerStock.qty)).where(DrawerStock.machine_id == 2))
    assert drawer_total <= 50

def test_allocation_page_with_no_machines_redirects_with_a_message(app, logged_in):
    """Before `flask seed` the database is empty; the page must not crash."""
    db.session.execute(db.delete(Machine))   # their stock and sales go with them (CASCADE)
    db.session.commit()
    response = logged_in.get("/allocation", follow_redirects=True)
    assert response.status_code == 200 and b"No machines are set up yet." in response.data
