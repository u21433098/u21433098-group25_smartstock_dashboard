"""SmartStock REST API, version 1 (every URL starts with /api/v1).

The full contract (every endpoint, parameter, request body and response) is in
docs/openapi.json, and a readable list with examples is in docs/api.md.

How it works
- Login uses the same session as the web pages (Flask-Login). An API client first
  calls GET /auth/csrf, then POST /auth/login, and keeps the session cookie.
- Every request that changes something (POST, PUT, PATCH, DELETE) must send the
  CSRF token in the X-CSRF-Token header (checked in app/__init__.py).
- Not logged in -> 401. Logged in but the role is not allowed -> 403.
- Lists are paged: ?page=1&per_page=20 (max 100), sorted with ?sort=key or ?sort=-key,
  and filtered with the parameters listed per endpoint. They return
  {"items": [...], "page", "per_page", "total", "pages", "has_prev", "has_next"}.
- Every error has the same shape: {"error": {"status", "message", "field" (optional)}}.

The routes only translate between HTTP and the services layer (app/services), which
does the checking, the database work and the role rules.
"""
import logging
import os

from flask import Blueprint, current_app, jsonify, request, send_file, session
from flask_login import current_user, login_user, logout_user

from app import schemas
from app.services import alert_service, analytics_service, catalogue_service, inventory_service, user_service
from app.services.errors import NotFoundError, ServiceError

bp = Blueprint("api", __name__, url_prefix="/api/v1")
log = logging.getLogger(__name__)

# Endpoints that work without logging in.
PUBLIC = {"api.csrf", "api.login", "api.openapi"}


# ------------------------------------------------------------------ shared behaviour
@bp.before_request
def require_login():
    if request.endpoint not in PUBLIC and not current_user.is_authenticated:
        return error_response(401, "Log in first: POST /api/v1/auth/login.")


def error_response(status, message, field=None):
    error = {"status": status, "message": message}
    if field:
        error["field"] = field
    return jsonify({"error": error}), status


@bp.errorhandler(ServiceError)
def service_error(error):
    """One handler for every error the services raise (400, 403, 404, 409)."""
    level = logging.WARNING if error.status == 403 else logging.INFO
    log.log(level, "API %s %s -> %s %s", request.method, request.path, error.status, error.message)
    return jsonify({"error": error.to_dict()}), error.status


def _csrf_token():
    """The session's CSRF token (created on first use)."""
    return current_app.jinja_env.globals["csrf_token"]()


def _me():
    return {"id": int(current_user.id), "name": current_user.name, "email": current_user.email,
            "role": current_user.role,
            "permissions": sorted(user_service.ROLE_PERMISSIONS.get(current_user.role, ())),
            "csrf_token": _csrf_token()}


def _stock_row(machine_id, product_id):
    """The three-tier row of one product in one machine, after a change."""
    return next(r for r in inventory_service.get_machine_rows(machine_id) if r["product_id"] == product_id)


# ------------------------------------------------------------------ auth
@bp.get("/auth/csrf")
def csrf():
    """Step 1 for an API client: get a CSRF token (and a session cookie)."""
    return jsonify({"csrf_token": _csrf_token()})


@bp.post("/auth/login")
def login():
    email, password = schemas.login(schemas.json_body())
    user = user_service.verify_credentials(email, password)
    if user is None:
        log.warning("API failed login for %s", email.strip().lower())
        return error_response(401, "Incorrect email or password.")
    login_user(user)
    log.info("API login: %s", user.email)
    return jsonify(_me())


@bp.post("/auth/logout")
def logout():
    logout_user()
    session.pop("_csrf_token", None)
    return "", 204


@bp.get("/auth/me")
def me():
    return jsonify(_me())


@bp.put("/me/password")
def change_my_password():
    current, new = schemas.password_change(schemas.json_body())
    user_service.change_own_password(current_user, current, new)
    return "", 204


# ------------------------------------------------------------------ dashboard
@bp.get("/dashboard")
def dashboard():
    return jsonify(analytics_service.get_dashboard_summary())


# ------------------------------------------------------------------ machines
@bp.get("/machines")
def machines():
    a = request.args
    return jsonify(inventory_service.list_machines(
        search=a.get("search"), sort=a.get("sort"), page=a.get("page"), per_page=a.get("per_page")))


@bp.post("/machines")
def create_machine():
    """Add a machine (it carries no products until POST /machines/{id}/products)."""
    machine = catalogue_service.create_machine(current_user, **schemas.new_machine(schemas.json_body()))
    log.info("API: %s added machine %s", current_user.email, machine["code"])
    return jsonify(machine), 201


@bp.get("/machines/<int:machine_id>")
def machine(machine_id):
    return jsonify(inventory_service.get_machine_detail(machine_id))


@bp.patch("/machines/<int:machine_id>")
def update_machine(machine_id):
    """Change a machine's location or drawer capacity."""
    return jsonify(catalogue_service.update_machine(current_user, machine_id,
                                                    **schemas.machine_update(schemas.json_body())))


@bp.post("/machines/<int:machine_id>/products")
def add_machine_product(machine_id):
    """Start carrying a product in a machine (machine and drawer slots start at 0 units)."""
    row = catalogue_service.add_product_to_machine(current_user, machine_id,
                                                   **schemas.machine_product(schemas.json_body()))
    log.info("API: %s added product %s to machine %s", current_user.email, row["product_id"], machine_id)
    return jsonify(row), 201


@bp.put("/machines/<int:machine_id>/stock/<int:product_id>")
def machine_count(machine_id, product_id):
    """Record a physical count of one product inside a machine."""
    qty = schemas.stock_count(schemas.json_body())
    inventory_service.require_machine(machine_id)
    inventory_service.set_machine_count(machine_id, product_id, qty, current_user.name)
    return jsonify(_stock_row(machine_id, product_id))


@bp.post("/machines/<int:machine_id>/restocks")
def machine_restock(machine_id):
    """Log a restock visit: units fill the machine, then the drawer, the rest goes back to central."""
    product_id, units = schemas.restock(schemas.json_body())
    inventory_service.require_machine(machine_id)
    split = inventory_service.restock_visit(machine_id, product_id, units, current_user.name)
    return jsonify({"split": split, "stock": _stock_row(machine_id, product_id)})


@bp.get("/machines/<int:machine_id>/allocation")
def machine_allocation(machine_id):
    return jsonify(analytics_service.get_allocation(machine_id))


# ------------------------------------------------------------------ products and suppliers
@bp.get("/products")
def products():
    a = request.args
    return jsonify(catalogue_service.list_products(
        search=a.get("search"), supplier_id=a.get("supplier_id"), sort=a.get("sort"),
        page=a.get("page"), per_page=a.get("per_page")))


@bp.post("/products")
def create_product():
    """Add a product; its central storage row starts at 0 units."""
    product = catalogue_service.create_product(current_user, **schemas.new_product(schemas.json_body()))
    log.info("API: %s added product %s", current_user.email, product["name"])
    return jsonify(product), 201


@bp.get("/products/<int:product_id>")
def product(product_id):
    return jsonify(catalogue_service.get_product(product_id))


@bp.patch("/products/<int:product_id>")
def update_product(product_id):
    return jsonify(catalogue_service.update_product(current_user, product_id,
                                                    **schemas.product_update(schemas.json_body())))


@bp.get("/suppliers")
def suppliers():
    a = request.args
    return jsonify(catalogue_service.list_suppliers(page=a.get("page"), per_page=a.get("per_page")))


@bp.post("/suppliers")
def create_supplier():
    supplier = catalogue_service.create_supplier(current_user, **schemas.new_supplier(schemas.json_body()))
    log.info("API: %s added supplier %s", current_user.email, supplier["name"])
    return jsonify(supplier), 201


@bp.get("/suppliers/<int:supplier_id>")
def supplier(supplier_id):
    return jsonify(catalogue_service.get_supplier(supplier_id))


@bp.patch("/suppliers/<int:supplier_id>")
def update_supplier(supplier_id):
    return jsonify(catalogue_service.update_supplier(current_user, supplier_id,
                                                     **schemas.supplier_update(schemas.json_body())))


# ------------------------------------------------------------------ central storage
@bp.get("/central")
def central():
    a = request.args
    low_only = a.get("low_only", "").lower() in ("1", "true", "yes")
    return jsonify(inventory_service.list_central(
        search=a.get("search"), supplier_id=a.get("supplier_id"), low_only=low_only,
        sort=a.get("sort"), page=a.get("page"), per_page=a.get("per_page")))


@bp.put("/central/<int:product_id>")
def central_count(product_id):
    """Record a stock take of one product in central storage."""
    qty = schemas.stock_count(schemas.json_body())
    inventory_service.set_central_count(product_id, qty, current_user.name)
    return jsonify(next(r for r in inventory_service.get_central_rows() if r["product_id"] == product_id))


# ------------------------------------------------------------------ alerts, audit trail, planning
@bp.get("/alerts")
def alerts():
    a = request.args
    return jsonify(alert_service.list_alerts(
        tier=a.get("tier"), severity=a.get("severity"), machine_id=a.get("machine_id"),
        page=a.get("page"), per_page=a.get("per_page")))


@bp.get("/movements")
def movements():
    a = request.args
    return jsonify(inventory_service.list_movements(
        machine_id=a.get("machine_id"), product_id=a.get("product_id"), tier=a.get("tier"),
        date_from=a.get("date_from"), date_to=a.get("date_to"),
        page=a.get("page"), per_page=a.get("per_page")))


@bp.get("/shopping-list")
def shopping_list():
    return jsonify(analytics_service.build_shopping_list())


# ------------------------------------------------------------------ users (admin only; the services check the role)
@bp.get("/users")
def users():
    a = request.args
    return jsonify(user_service.list_users(current_user, page=a.get("page"), per_page=a.get("per_page")))


@bp.post("/users")
def create_user():
    fields = schemas.new_user(schemas.json_body())
    user = user_service.admin_create_user(current_user, **fields)
    log.info("API: %s created account %s (%s)", current_user.email, user["email"], user["role"])
    return jsonify(user), 201


@bp.get("/users/<int:user_id>")
def user(user_id):
    return jsonify(user_service.get_user_detail(current_user, user_id))


@bp.patch("/users/<int:user_id>")
def update_user(user_id):
    role, is_active = schemas.user_update(schemas.json_body())
    user = None
    if role is not None:
        user = user_service.set_role(current_user, user_id, role)
    if is_active is not None:
        user = user_service.set_active(current_user, user_id, is_active)
    log.info("API: %s updated user %s (role=%s, is_active=%s)", current_user.email, user_id, role, is_active)
    return jsonify(user)


@bp.put("/users/<int:user_id>/password")
def reset_user_password(user_id):
    user_service.reset_password(current_user, user_id, schemas.password_reset(schemas.json_body()))
    log.info("API: %s reset the password of user %s", current_user.email, user_id)
    return "", 204


# ------------------------------------------------------------------ the contract itself
@bp.get("/openapi.json")
def openapi():
    """The OpenAPI 3 contract (docs/openapi.json), for Swagger UI or Postman."""
    path = os.path.join(os.path.dirname(current_app.root_path), "docs", "openapi.json")
    if not os.path.exists(path):
        raise NotFoundError("The API contract file docs/openapi.json is missing.")
    return send_file(path, mimetype="application/json")
