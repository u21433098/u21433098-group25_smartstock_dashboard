"""Admin pages (/admin/users) and the "change my password" page (/account/password)."""
from app.extensions import db
from app.models import User
from tests.conftest import PASSWORD, USER_EMAIL


def user_row(email):
    db.session.rollback()   # see what the requests committed
    return db.session.scalar(db.select(User).where(User.email == email))


def can_log_in(app, email, password=PASSWORD):
    return app.test_client().post("/login", data={"email": email, "password": password}).status_code == 302


# ------------------------------------------------------------------ who may open the page
def test_a_normal_user_gets_403_on_every_admin_address(user_client):
    assert user_client.get("/admin/users").status_code == 403
    for url in ("/admin/users", "/admin/users/1/active", "/admin/users/1/role", "/admin/users/1/password"):
        assert user_client.post(url, data={"active": "0", "role": "admin", "new_password": "x" * 10}).status_code == 403
    assert user_row(USER_EMAIL).is_active and user_row(USER_EMAIL).role == "user"


def test_users_link_only_shows_for_admins(user_client, admin_client):
    assert b'href="/admin/users"' not in user_client.get("/").data
    assert b'href="/admin/users"' in admin_client.get("/").data


def test_admin_page_lists_accounts_and_marks_yourself(admin_client):
    page = admin_client.get("/admin/users")
    assert page.status_code == 200
    assert b"Mr Msiza" in page.data and b"Claudia Aird" in page.data and b">you<" in page.data


# ------------------------------------------------------------------ adding accounts
def test_admin_adds_a_helper_who_can_then_log_in(admin_client, app):
    response = admin_client.post("/admin/users", data={
        "name": "Thabo Helper", "email": "thabo@adlers.test", "role": "user",
        "password": "helper-pass-1", "confirm": "helper-pass-1"}, follow_redirects=True)
    assert b"Account created for Thabo Helper" in response.data
    assert user_row("thabo@adlers.test").role == "user"
    assert can_log_in(app, "thabo@adlers.test", "helper-pass-1")


def test_add_account_errors_keep_what_was_typed(admin_client):
    mismatch = admin_client.post("/admin/users", data={"name": "Typed Name", "email": "t@adlers.test",
                                                       "password": "longenough1", "confirm": "different1"})
    assert mismatch.status_code == 400 and b"do not match" in mismatch.data and b'value="Typed Name"' in mismatch.data
    duplicate = admin_client.post("/admin/users", data={"name": "Copy", "email": USER_EMAIL,
                                                        "password": "longenough1", "confirm": "longenough1"})
    assert duplicate.status_code == 409 and b"already exists" in duplicate.data
    short = admin_client.post("/admin/users", data={"name": "Short", "email": "s@adlers.test",
                                                    "password": "short", "confirm": "short"})
    assert short.status_code == 400 and b"at least 8 characters" in short.data


# ------------------------------------------------------------------ managing accounts
def test_switching_an_account_off_stops_it_logging_in(admin_client, app):
    response = admin_client.post("/admin/users/1/active", data={"active": "0"}, follow_redirects=True)
    assert b"Mr Msiza can no longer log in" in response.data
    assert not can_log_in(app, USER_EMAIL)
    admin_client.post("/admin/users/1/active", data={"active": "1"})
    assert can_log_in(app, USER_EMAIL)


def test_a_switched_off_user_is_logged_out_at_once(admin_client, user_client):
    assert user_client.get("/").status_code == 200
    admin_client.post("/admin/users/1/active", data={"active": "0"})
    assert user_client.get("/").status_code == 302          # bounced to the login page


def test_admin_cannot_lock_themselves_out(admin_client):
    off = admin_client.post("/admin/users/2/active", data={"active": "0"}, follow_redirects=True)
    assert b"cannot switch off your own account" in off.data
    demote = admin_client.post("/admin/users/2/role", data={"role": "user"}, follow_redirects=True)
    assert b"cannot change your own role" in demote.data
    assert user_row("admin@smartstock.test").is_active and user_row("admin@smartstock.test").role == "admin"


def test_admin_changes_a_role_and_resets_a_password(admin_client, app):
    promoted = admin_client.post("/admin/users/1/role", data={"role": "admin"}, follow_redirects=True)
    assert b"Mr Msiza is now an admin" in promoted.data and user_row(USER_EMAIL).role == "admin"
    reset = admin_client.post("/admin/users/1/password", data={"new_password": "reset-pass-123"}, follow_redirects=True)
    assert b"Password changed" in reset.data and can_log_in(app, USER_EMAIL, "reset-pass-123")
    too_short = admin_client.post("/admin/users/1/password", data={"new_password": "short"}, follow_redirects=True)
    assert b"at least 8 characters" in too_short.data


def test_unknown_user_id_shows_a_message(admin_client):
    response = admin_client.post("/admin/users/999/role", data={"role": "user"}, follow_redirects=True)
    assert b"User 999 does not exist" in response.data


# ------------------------------------------------------------------ change my own password
def test_change_own_password(user_client, app):
    assert user_client.get("/account/password").status_code == 200
    wrong = user_client.post("/account/password", data={"current_password": "nope",
                                                         "new_password": "brand-new-1", "confirm": "brand-new-1"})
    assert wrong.status_code == 400 and b"current password is incorrect" in wrong.data
    mismatch = user_client.post("/account/password", data={"current_password": PASSWORD,
                                                            "new_password": "brand-new-1", "confirm": "other-one-1"})
    assert mismatch.status_code == 400 and b"do not match" in mismatch.data
    ok = user_client.post("/account/password", data={"current_password": PASSWORD, "new_password": "brand-new-1",
                                                      "confirm": "brand-new-1"}, follow_redirects=True)
    assert b"Your password has been changed" in ok.data
    assert can_log_in(app, USER_EMAIL, "brand-new-1") and not can_log_in(app, USER_EMAIL, PASSWORD)
