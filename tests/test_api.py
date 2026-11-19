"""REST API tests (/api/v1): login, CSRF, every endpoint, validation, errors and roles.

Fixtures (app, api, user_api, admin_api) come from tests/conftest.py.
"""
import logging

import pytest

from app.extensions import db
from app.models import CentralStock, MachineStock, StockMovement
from tests.conftest import ADMIN_EMAIL, PASSWORD, USER_EMAIL, Api

PAGE_KEYS = {"items", "page", "per_page", "total", "pages", "has_prev", "has_next"}


def error_of(response):
    """The {"status", "message", "field"} part of a JSON error response."""
    assert response.is_json, response.data[:200]
    return response.get_json()["error"]


def fresh_qty(model, *key):
    db.session.rollback()   # see what the requests committed
    return db.session.get(model, key if len(key) > 1 else key[0]).qty


# ------------------------------------------------------------------ login and sessions
@pytest.mark.parametrize("path", ["/auth/me", "/dashboard", "/machines", "/machines/1", "/machines/1/allocation",
                                  "/central", "/alerts", "/movements", "/shopping-list", "/users"])
def test_every_data_endpoint_needs_a_login(api, path):
    response = api.get(path)
    assert response.status_code == 401
    assert error_of(response)["message"].startswith("Log in first")


def test_csrf_and_contract_endpoints_work_without_login(api):
    assert len(api.get("/auth/csrf").get_json()["csrf_token"]) == 32
    assert api.get("/openapi.json").status_code == 200


def test_login_returns_the_user_their_permissions_and_a_csrf_token(api):
    response = api.login()
    me = response.get_json()
    assert response.status_code == 200
    assert (me["name"], me["email"], me["role"]) == ("Mr Msiza", USER_EMAIL, "user")
    assert me["permissions"] == ["change_stock", "view"]
    assert me["csrf_token"] == api.csrf


def test_admin_login_has_the_manage_users_permission(api):
    assert "manage_users" in api.login(ADMIN_EMAIL).get_json()["permissions"]


def test_wrong_password_is_401_and_logged(api, caplog):
    with caplog.at_level(logging.WARNING):
        response = api.login(password="wrong-password")
    assert response.status_code == 401 and error_of(response)["message"] == "Incorrect email or password."
    assert "API failed login for msiza@adlers.test" in caplog.text


def test_me_then_logout_ends_the_session(user_api):
    assert user_api.get("/auth/me").get_json()["email"] == USER_EMAIL
    assert user_api.post("/auth/logout").status_code == 204
    assert user_api.get("/auth/me").status_code == 401


def test_login_body_is_validated(api):
    api.csrf = api.get("/auth/csrf").get_json()["csrf_token"]
    assert error_of(api.post("/auth/login", {"email": USER_EMAIL}))["field"] == "password"
    assert error_of(api.post("/auth/login", {"email": 5, "password": "x"}))["field"] == "email"


# ------------------------------------------------------------------ CSRF (switched on for these tests)
@pytest.fixture
def csrf_app(app):
    app.config["CSRF_ENABLED"] = True
    return app


def test_changes_without_the_csrf_header_are_refused(csrf_app):
    client = Api(csrf_app.test_client())
    assert client.login().status_code == 200
    token, client.csrf = client.csrf, None                     # "forget" to send the header
    refused = client.put("/central/1", {"qty": 5})
    assert refused.status_code == 400 and "CSRF" in error_of(refused)["message"]
    client.csrf = "not-the-right-token"
    assert client.put("/central/1", {"qty": 5}).status_code == 400
    assert fresh_qty(CentralStock, 1) != 5
    client.csrf = token
    assert client.put("/central/1", {"qty": 5}).status_code == 200


def test_login_itself_needs_the_csrf_token(csrf_app):
    client = Api(csrf_app.test_client())
    response = client.post("/auth/login", {"email": USER_EMAIL, "password": PASSWORD})
    assert response.status_code == 400
    assert client.login().status_code == 200


def test_reading_needs_no_csrf_token(csrf_app):
    client = Api(csrf_app.test_client())
    client.login()
    client.csrf = None
    assert client.get("/machines").status_code == 200


def test_web_forms_still_need_their_hidden_token(csrf_app):
    web = csrf_app.test_client()
    assert web.post("/login", data={"email": USER_EMAIL, "password": PASSWORD}).status_code == 400


# ------------------------------------------------------------------ JSON errors everywhere under /api
def test_unknown_api_address_and_wrong_method_answer_in_json(user_api):
    missing = user_api.get("/no-such-thing")
    assert missing.status_code == 404 and "openapi.json" in error_of(missing)["message"]
    wrong = user_api.client.delete("/api/v1/machines")
    assert wrong.status_code == 405 and error_of(wrong)["status"] == 405


@pytest.mark.parametrize("body, field", [
    ({"qty": "12"}, "qty"),            # text, not a number
    ({"qty": 12.5}, "qty"),            # decimal
    ({"qty": True}, "qty"),            # true is not 1
    ({"qty": -1}, "qty"),              # below zero
    ({"quantity": 3}, "quantity"),     # typo in the field name
    ({}, "qty"),                       # missing
])
def test_bad_request_bodies_name_the_field(user_api, body, field):
    response = user_api.put("/central/1", body)
    assert response.status_code == 400 and error_of(response)["field"] == field


def test_body_must_be_a_json_object(user_api):
    not_json = user_api.client.put("/api/v1/central/1", data="qty=5", headers=user_api._headers())
    assert not_json.status_code == 400 and "JSON" in error_of(not_json)["message"]
    a_list = user_api.put("/central/1", [5])
    assert a_list.status_code == 400 and "JSON object" in error_of(a_list)["message"]
    broken = user_api.client.put("/api/v1/central/1", data="{qty:", content_type="application/json",
                                 headers=user_api._headers())
    assert broken.status_code == 400


# ------------------------------------------------------------------ machines
def test_machine_list_is_paged_sorted_and_searchable(user_api):
    first = user_api.get("/machines", per_page=5).get_json()
    assert set(first) == PAGE_KEYS and first["total"] == 12 and len(first["items"]) == 5
    assert first["items"][0] == {"id": 1, "code": "UP-01", "location": "Engineering 1",
                                 "drawer_capacity": 50, "alerts": first["items"][0]["alerts"]}
    third = user_api.get("/machines", per_page=5, page=3).get_json()
    assert [m["code"] for m in third["items"]] == ["UP-11", "UP-12"] and not third["has_next"]
    by_alerts = [m["alerts"] for m in user_api.get("/machines", sort="-alerts", per_page=100).get_json()["items"]]
    assert by_alerts == sorted(by_alerts, reverse=True)
    assert [m["code"] for m in user_api.get("/machines", search="library").get_json()["items"]] == ["UP-02"]


@pytest.mark.parametrize("params, field", [({"sort": "password"}, "sort"), ({"page": "x"}, "page"),
                                           ({"per_page": "500"}, "per_page")])
def test_bad_list_parameters_are_400_with_the_field(user_api, params, field):
    response = user_api.get("/machines", **params)
    assert response.status_code == 400 and error_of(response)["field"] == field


def test_machine_detail_has_all_three_tiers(user_api):
    machine = user_api.get("/machines/3").get_json()
    assert machine["code"] == "UP-03" and len(machine["products"]) == 8
    assert set(machine["products"][0]) == {"product_id", "name", "machine", "drawer", "central"}
    assert error_of(user_api.get("/machines/999"))["status"] == 404


def test_machine_count_changes_stock_and_is_audited(user_api):
    response = user_api.put("/machines/2/stock/1", {"qty": 0})
    assert response.status_code == 200 and response.get_json()["machine"]["qty"] == 0
    assert fresh_qty(MachineStock, 2, 1) == 0
    move = db.session.scalars(db.select(StockMovement).order_by(StockMovement.movement_id.desc())).first()
    assert (move.machine_id, move.tier, move.new_qty, move.user.name) == (2, "Machine", 0, "Mr Msiza")


def test_machine_count_errors(user_api):
    over = user_api.put("/machines/2/stock/1", {"qty": 21})
    assert over.status_code == 400 and error_of(over)["field"] == "qty"
    assert user_api.put("/machines/999/stock/1", {"qty": 1}).status_code == 404
    not_carried = next(p for p in range(1, 16) if p not in
                       [r["product_id"] for r in user_api.get("/machines/2").get_json()["products"]])
    assert user_api.put(f"/machines/2/stock/{not_carried}", {"qty": 1}).status_code == 404


def test_restock_splits_the_units_and_returns_the_new_levels(user_api):
    before = user_api.get("/machines/2").get_json()["products"]
    row = next(r for r in before if r["product_id"] == 1)
    response = user_api.post("/machines/2/restocks", {"product_id": 1, "units": 40})
    body = response.get_json()
    assert response.status_code == 200
    assert sum(body["split"].values()) == 40
    assert body["stock"]["machine"]["qty"] == row["machine"]["qty"] + body["split"]["to_machine"]
    assert body["stock"]["central"]["qty"] == row["central"]["qty"] + body["split"]["to_central"]


def test_restock_validation(user_api):
    assert error_of(user_api.post("/machines/2/restocks", {"product_id": 1, "units": 0}))["field"] == "units"
    assert error_of(user_api.post("/machines/2/restocks", {"product_id": 1, "units": 5000}))["field"] == "units"
    assert error_of(user_api.post("/machines/2/restocks", {"units": 5}))["field"] == "product_id"
    assert user_api.post("/machines/999/restocks", {"product_id": 1, "units": 5}).status_code == 404


def test_allocation(user_api):
    plan = user_api.get("/machines/4/allocation").get_json()
    assert plan["machine_id"] == 4 and plan["allocated"] <= plan["capacity"]
    assert [r["rank"] for r in plan["rows"]] == list(range(1, len(plan["rows"]) + 1))
    assert user_api.get("/machines/999/allocation").status_code == 404


# ------------------------------------------------------------------ central storage
def test_central_list_filters(user_api):
    low = user_api.get("/central", low_only="true", per_page=100).get_json()["items"]
    assert low and all(r["qty"] <= r["threshold"] for r in low)
    water = user_api.get("/central", supplier_id=3).get_json()["items"]
    assert {r["supplier"] for r in water} == {"Supplier C - Water"}
    assert user_api.get("/central", search="cola").get_json()["items"][0]["name"] == "Coca-Cola 300ml"
    assert user_api.get("/central", supplier_id="abc").status_code == 400


def test_central_stock_take(user_api):
    response = user_api.put("/central/2", {"qty": 33})
    assert response.status_code == 200 and response.get_json()["qty"] == 33
    assert fresh_qty(CentralStock, 2) == 33
    assert user_api.put("/central/999", {"qty": 3}).status_code == 404
    assert error_of(user_api.put("/central/2", {"qty": 6000}))["field"] == "qty"


# ------------------------------------------------------------------ alerts, movements, planning, dashboard
def test_alert_filters(user_api):
    out = user_api.get("/alerts", severity="out", per_page=100).get_json()["items"]
    assert out and all(a["qty"] == 0 for a in out)
    assert {a["tier"] for a in user_api.get("/alerts", tier="Drawer", per_page=100).get_json()["items"]} == {"Drawer"}
    assert user_api.get("/alerts", tier="Car").status_code == 400


def test_movements_follow_the_changes_made_through_the_api(user_api):
    user_api.put("/central/1", {"qty": 10})
    user_api.post("/machines/3/restocks", {"product_id": 1, "units": 5})
    everything = user_api.get("/movements").get_json()
    assert everything["total"] >= 2 and everything["items"][0]["user"] == "Mr Msiza"
    central_only = user_api.get("/movements", tier="Central").get_json()["items"]
    assert central_only and {m["tier"] for m in central_only} == {"Central"}
    assert all(m["machine_id"] == 3 for m in user_api.get("/movements", machine_id=3).get_json()["items"])
    bad = user_api.get("/movements", date_from="2026-10-05", date_to="2026-10-01")
    assert bad.status_code == 400 and error_of(bad)["field"] == "date_from"


def test_shopping_list_and_dashboard(user_api):
    shopping = user_api.get("/shopping-list").get_json()
    assert {"groups", "n_products", "n_suppliers", "trips_saved", "total_cost"} <= set(shopping)
    assert all(g["lines"] for g in shopping["groups"])
    summary = user_api.get("/dashboard").get_json()
    assert summary["kpis"]["machines"] == 12 and summary["sales_window"]["days"] == 30
    assert summary["total_alerts"] >= len(summary["alerts"])


# ------------------------------------------------------------------ users and roles
@pytest.mark.parametrize("call", [
    lambda c: c.get("/users"),
    lambda c: c.post("/users", {"name": "X", "email": "x@adlers.test", "password": "longenough1"}),
    lambda c: c.patch("/users/2", {"is_active": False}),
    lambda c: c.put("/users/2/password", {"new_password": "longenough1"}),
])
def test_a_user_cannot_manage_accounts(user_api, call):
    response = call(user_api)
    assert response.status_code == 403 and error_of(response)["status"] == 403


def test_admin_lists_and_creates_accounts(admin_api):
    listed = admin_api.get("/users").get_json()
    assert {u["email"] for u in listed["items"]} == {USER_EMAIL, ADMIN_EMAIL}
    created = admin_api.post("/users", {"name": "Thabo", "email": "thabo@adlers.test", "password": "longenough1"})
    assert created.status_code == 201
    assert created.get_json()["role"] == "user" and created.get_json()["is_active"] is True
    duplicate = admin_api.post("/users", {"name": "Copy", "email": "thabo@adlers.test", "password": "longenough1"})
    assert duplicate.status_code == 409 and error_of(duplicate)["field"] == "email"
    short = admin_api.post("/users", {"name": "Short", "email": "s@adlers.test", "password": "short"})
    assert short.status_code == 400 and error_of(short)["field"] == "password"


def test_admin_switches_an_account_off_and_on(admin_api, app):
    off = admin_api.patch("/users/1", {"is_active": False})
    assert off.status_code == 200 and off.get_json()["is_active"] is False
    assert Api(app.test_client()).login().status_code == 401          # Msiza can no longer log in
    admin_api.patch("/users/1", {"is_active": True})
    assert Api(app.test_client()).login().status_code == 200


def test_admin_changes_a_role_but_not_their_own(admin_api):
    assert admin_api.patch("/users/1", {"role": "admin"}).get_json()["role"] == "admin"
    own = admin_api.patch("/users/2", {"role": "user"})
    assert own.status_code == 409
    assert error_of(admin_api.patch("/users/1", {"role": "boss"}))["field"] == "role"
    assert error_of(admin_api.patch("/users/1", {}))["status"] == 400
    assert admin_api.patch("/users/999", {"role": "user"}).status_code == 404


def test_admin_resets_a_password(admin_api, app):
    assert admin_api.put("/users/1/password", {"new_password": "fresh-password-1"}).status_code == 204
    assert Api(app.test_client()).login(password="fresh-password-1").status_code == 200


def test_anyone_can_change_their_own_password(user_api, app):
    wrong = user_api.put("/me/password", {"current_password": "nope", "new_password": "another-pass-1"})
    assert wrong.status_code == 400 and error_of(wrong)["field"] == "current_password"
    ok = user_api.put("/me/password", {"current_password": PASSWORD, "new_password": "another-pass-1"})
    assert ok.status_code == 204
    assert Api(app.test_client()).login(password="another-pass-1").status_code == 200
