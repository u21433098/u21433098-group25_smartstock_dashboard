"""Service tests: paging, sorting, filtering, error types and roles.

These test the functions the API routes call, without going through HTTP.
"""
import json
from datetime import date, timedelta

import pytest

from app import create_app
from app.data import seed_data
from app.extensions import db
from app.services import alert_service, analytics_service, inventory_service, user_service
from app.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        seed_data.seed(today=date(2026, 10, 1))
        yield app
        db.session.remove()


@pytest.fixture
def admin(app):
    return user_service.verify_credentials("admin@smartstock.test", seed_data.DEMO_PASSWORD)


@pytest.fixture
def msiza(app):
    return user_service.verify_credentials("msiza@adlers.test", seed_data.DEMO_PASSWORD)


# ------------------------------------------------------------------ paging
def test_page_envelope_has_the_paging_fields(app):
    result = inventory_service.list_machines(page="2", per_page="5")
    assert [m["code"] for m in result["items"]] == ["UP-06", "UP-07", "UP-08", "UP-09", "UP-10"]
    assert (result["page"], result["per_page"], result["total"], result["pages"]) == (2, 5, 12, 3)
    assert result["has_prev"] and result["has_next"]


def test_a_page_past_the_end_is_empty_not_an_error(app):
    result = inventory_service.list_machines(page="9", per_page="5")
    assert result["items"] == [] and result["total"] == 12


@pytest.mark.parametrize("page, per_page, field", [("abc", None, "page"), ("0", None, "page"),
                                                   (None, "101", "per_page"), (None, "0", "per_page")])
def test_bad_paging_values_are_rejected_with_the_field_name(app, page, per_page, field):
    with pytest.raises(ValidationError) as error:
        inventory_service.list_machines(page=page, per_page=per_page)
    assert error.value.field == field and error.value.status == 400


# ------------------------------------------------------------------ sorting and filtering
def test_machines_sort_by_alerts_descending(app):
    counts = [m["alerts"] for m in inventory_service.list_machines(sort="-alerts", per_page="100")["items"]]
    assert counts == sorted(counts, reverse=True) and counts[0] > 0


def test_unknown_sort_key_is_rejected(app):
    with pytest.raises(ValidationError) as error:
        inventory_service.list_machines(sort="password_hash")
    assert error.value.field == "sort"


def test_machine_search_matches_code_or_location(app):
    assert [m["code"] for m in inventory_service.list_machines(search="library")["items"]] == ["UP-02"]
    assert [m["code"] for m in inventory_service.list_machines(search="up-1")["items"]] == ["UP-10", "UP-11", "UP-12"]


def test_central_filters(app):
    low = inventory_service.list_central(low_only=True, per_page="100")["items"]
    assert low and all(r["qty"] <= r["threshold"] for r in low)
    water = inventory_service.list_central(supplier_id="3")["items"]
    assert {r["supplier"] for r in water} == {"Supplier C - Water"}
    by_value = [r["value"] for r in inventory_service.list_central(sort="-value", per_page="100")["items"]]
    assert by_value == sorted(by_value, reverse=True)


def test_alert_filters(app):
    machine_only = alert_service.list_alerts(tier="Machine", per_page="100")["items"]
    assert machine_only and {a["tier"] for a in machine_only} == {"Machine"}
    out = alert_service.list_alerts(severity="out", per_page="100")["items"]
    assert out and all(a["qty"] == 0 for a in out)
    assert all(a["machine_id"] == 5 for a in alert_service.list_alerts(machine_id="5")["items"])
    with pytest.raises(ValidationError):
        alert_service.list_alerts(tier="Car")


def test_movement_filters_and_newest_first(app):
    inventory_service.set_central_count(1, 10, "Mr Msiza")
    inventory_service.set_machine_count(2, 1, 3, "Mr Msiza")
    inventory_service.restock_visit(2, 1, 5, "Mr Msiza")
    everything = inventory_service.list_movements()
    assert everything["total"] >= 3
    ids = [m["id"] for m in everything["items"]]
    assert ids == sorted(ids, reverse=True)
    assert {m["tier"] for m in inventory_service.list_movements(tier="Central")["items"]} == {"Central"}
    assert all(m["machine_id"] == 2 for m in inventory_service.list_movements(machine_id="2")["items"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert inventory_service.list_movements(date_from=tomorrow)["total"] == 0


def test_movement_date_range_must_be_valid(app):
    with pytest.raises(ValidationError) as error:
        inventory_service.list_movements(date_from="2026-10-05", date_to="2026-10-01")
    assert error.value.field == "date_from"
    with pytest.raises(ValidationError):
        inventory_service.list_movements(date_from="05/10/2026")


# ------------------------------------------------------------------ errors
def test_unknown_things_raise_not_found(app):
    for call in (lambda: inventory_service.get_machine_detail(999),
                 lambda: analytics_service.get_allocation(999),
                 lambda: inventory_service.set_central_count(999, 1, "Mr Msiza"),
                 lambda: inventory_service.restock_visit(1, 999, 5, "Mr Msiza")):
        with pytest.raises(NotFoundError) as error:
            call()
        assert error.value.status == 404


def test_service_errors_are_still_value_errors(app):
    """Existing routes catch ValueError; the new error types must not break them."""
    with pytest.raises(ValueError, match="between 0 and"):
        inventory_service.set_machine_count(1, 1, 999, "Mr Msiza")
    assert ValidationError("x", "qty").to_dict() == {"status": 400, "message": "x", "field": "qty"}


def test_every_api_result_can_be_turned_into_json(app, admin):
    results = [inventory_service.list_machines(), inventory_service.get_machine_detail(1),
               inventory_service.list_central(), inventory_service.list_movements(),
               alert_service.list_alerts(), analytics_service.get_allocation(1),
               analytics_service.build_shopping_list(), analytics_service.get_dashboard_summary(),
               user_service.list_users(admin)]
    for result in results:
        json.dumps(result)


def test_dashboard_summary(app):
    summary = analytics_service.get_dashboard_summary()
    assert summary["kpis"]["machines"] == 12
    assert summary["total_alerts"] >= len(summary["alerts"])
    assert summary["sales_window"] == {"first_day": "2026-09-01", "last_day": "2026-09-30", "days": 30}


# ------------------------------------------------------------------ roles
def test_role_permissions(admin, msiza):
    assert user_service.can(admin, "manage_users") and user_service.can(admin, "change_stock")
    assert user_service.can(msiza, "change_stock") and user_service.can(msiza, "view")
    assert not user_service.can(msiza, "manage_users")
    assert not user_service.can(None, "view")


def test_a_user_cannot_manage_accounts(msiza):
    for call in (lambda: user_service.list_users(msiza),
                 lambda: user_service.admin_create_user(msiza, "Helper", "h@adlers.test", "longenough1"),
                 lambda: user_service.set_active(msiza, 2, False),
                 lambda: user_service.set_role(msiza, 1, "admin"),
                 lambda: user_service.reset_password(msiza, 2, "longenough1")):
        with pytest.raises(PermissionDenied) as error:
            call()
        assert error.value.status == 403


def test_admin_adds_a_helper_who_can_then_log_in(admin):
    created = user_service.admin_create_user(admin, "Thabo", "Thabo@Adlers.test", "longenough1")
    assert created["role"] == "user" and created["email"] == "thabo@adlers.test"
    assert user_service.verify_credentials("thabo@adlers.test", "longenough1").name == "Thabo"
    with pytest.raises(ConflictError) as error:
        user_service.admin_create_user(admin, "Copy", "thabo@adlers.test", "longenough1")
    assert error.value.status == 409


def test_a_switched_off_account_cannot_log_in(admin, msiza):
    user_service.set_active(admin, int(msiza.id), False)
    assert user_service.verify_credentials("msiza@adlers.test", seed_data.DEMO_PASSWORD) is None
    assert user_service.get_user(msiza.id) is None
    user_service.set_active(admin, int(msiza.id), True)
    assert user_service.verify_credentials("msiza@adlers.test", seed_data.DEMO_PASSWORD) is not None


def test_admin_cannot_lock_themselves_out(admin):
    with pytest.raises(ConflictError):
        user_service.set_active(admin, int(admin.id), False)
    with pytest.raises(ConflictError):
        user_service.set_role(admin, int(admin.id), "user")


def test_at_least_one_active_admin_always_remains(app, admin):
    other = user_service.admin_create_user(admin, "Second Admin", "second@smartstock.test", "longenough1", "admin")
    second = user_service.verify_credentials("second@smartstock.test", "longenough1")
    user_service.set_role(second, int(admin.id), "user")       # the first admin is demoted...
    with pytest.raises(ConflictError, match="at least one active admin"):
        user_service.set_active(admin, other["id"], False)     # ...so their stale session cannot remove the last one


def test_passwords_can_be_reset_and_changed(admin, msiza):
    user_service.reset_password(admin, int(msiza.id), "brand-new-pass")
    assert user_service.verify_credentials("msiza@adlers.test", "brand-new-pass")
    with pytest.raises(ValidationError) as error:
        user_service.change_own_password(msiza, "wrong", "another-pass")
    assert error.value.field == "current_password"
    user_service.change_own_password(msiza, "brand-new-pass", "another-pass")
    assert user_service.verify_credentials("msiza@adlers.test", "another-pass")
    with pytest.raises(ValidationError):
        user_service.reset_password(admin, int(msiza.id), "short")
