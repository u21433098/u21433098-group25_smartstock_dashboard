"""Shared pytest fixtures for the route, API, admin, page and end-to-end tests.

pytest loads this file automatically. A test file that defines a fixture with the
same name (e.g. its own `app`) uses its own version instead.
"""
import pytest
from flask.testing import FlaskClient

from app import create_app
from app.extensions import db

USER_EMAIL, ADMIN_EMAIL, PASSWORD = "msiza@adlers.test", "admin@smartstock.test", "SmartStock123"


class FreshContextClient(FlaskClient):
    """A test client that gives every request its own app context, like a real server.

    Without this, Flask reuses the test's own app context for each request, so the
    logged-in user (cached by Flask-Login on `g`) and the database session would be
    shared between requests and even between two different clients in one test.
    """

    def open(self, *args, **kwargs):
        with self.application.app_context():
            return super().open(*args, **kwargs)


@pytest.fixture
def app():
    """A new app. The testing configuration builds and seeds a fresh database for it."""
    app = create_app("testing")
    app.test_client_class = FreshContextClient
    with app.app_context():
        yield app
        db.session.remove()


def fresh():
    """End the test's own read transaction, so the next query sees what requests committed.
    (MySQL keeps showing an old snapshot until the transaction ends.)"""
    db.session.rollback()


@pytest.fixture
def client(app):
    return app.test_client()


def _log_in(client, email):
    response = client.post("/login", data={"email": email, "password": PASSWORD})
    assert response.status_code == 302, f"login failed for {email}"
    return client


@pytest.fixture
def user_client(app):
    """Logged in through the web form as Mr Msiza (role: user)."""
    return _log_in(app.test_client(), USER_EMAIL)


@pytest.fixture
def admin_client(app):
    """Logged in through the web form as the admin."""
    return _log_in(app.test_client(), ADMIN_EMAIL)


class Api:
    """Small JSON client for /api/v1 that logs in through the API like a real client would."""

    def __init__(self, client):
        self.client = client
        self.csrf = None

    def login(self, email=USER_EMAIL, password=PASSWORD):
        self.csrf = self.client.get("/api/v1/auth/csrf").get_json()["csrf_token"]
        response = self.post("/auth/login", {"email": email, "password": password})
        if response.status_code == 200:
            self.csrf = response.get_json()["csrf_token"]
        return response

    def _headers(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, path, **params):
        return self.client.get("/api/v1" + path, query_string=params)

    def post(self, path, body=None):
        return self.client.post("/api/v1" + path, json=body, headers=self._headers())

    def put(self, path, body=None):
        return self.client.put("/api/v1" + path, json=body, headers=self._headers())

    def patch(self, path, body=None):
        return self.client.patch("/api/v1" + path, json=body, headers=self._headers())


@pytest.fixture
def api(app):
    """API client, not logged in yet."""
    return Api(app.test_client())


@pytest.fixture
def user_api(app):
    """API client logged in as Mr Msiza (role: user)."""
    client = Api(app.test_client())
    assert client.login().status_code == 200
    return client


@pytest.fixture
def admin_api(app):
    """API client logged in as the admin."""
    client = Api(app.test_client())
    assert client.login(ADMIN_EMAIL).status_code == 200
    return client
