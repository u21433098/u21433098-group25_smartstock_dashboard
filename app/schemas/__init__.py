"""Request-body schemas for the REST API: read and check the JSON a client sends.

Each schema function takes the parsed JSON body and returns clean Python values,
or raises ValidationError (from app/services/errors.py) naming the bad field. The
API's error handler turns that into the standard 400 JSON error, e.g.

    {"error": {"status": 400, "message": "qty must be a whole number.", "field": "qty"}}

Rules shared by every schema:
- The body must be a JSON object ({...}); anything else is a 400.
- Unknown fields are rejected, so a typo such as "quantity" instead of "qty" is
  reported instead of silently ignored.
- Whole numbers must be real JSON numbers (12), not text ("12") or decimals (12.5).
"""
from flask import request

from app.services.errors import ValidationError

MAX_TEXT = 255


# ------------------------------------------------------------------ helpers
def json_body():
    """The request's JSON object. Rejects a missing, broken or non-object body."""
    if not request.is_json:
        raise ValidationError("Send the request body as JSON (Content-Type: application/json).")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("The request body must be a JSON object, e.g. {\"qty\": 12}.")
    return body


def _only(body, allowed):
    unknown = sorted(set(body) - set(allowed))
    if unknown:
        raise ValidationError(f"Unknown field: {unknown[0]}. Allowed fields: {', '.join(allowed)}.", unknown[0])


def _int(body, field, minimum=None, maximum=None, required=True):
    if field not in body:
        if required:
            raise ValidationError(f"{field} is required.", field)
        return None
    value = body[field]
    # bool is a subclass of int in Python, so True would otherwise count as 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be a whole number.", field)
    if minimum is not None and value < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.", field)
    if maximum is not None and value > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.", field)
    return value


def _text(body, field, required=True, max_length=MAX_TEXT):
    if field not in body:
        if required:
            raise ValidationError(f"{field} is required.", field)
        return None
    value = body[field]
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.", field)
    if len(value) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters.", field)
    return value


def _bool(body, field):
    if field not in body:
        return None
    if not isinstance(body[field], bool):
        raise ValidationError(f"{field} must be true or false.", field)
    return body[field]


# ------------------------------------------------------------------ one schema per request body
def login(body):
    """POST /auth/login  {"email": "...", "password": "..."}"""
    _only(body, ("email", "password"))
    return _text(body, "email"), _text(body, "password")


def stock_count(body):
    """PUT /machines/{id}/stock/{product_id} and PUT /central/{product_id}  {"qty": 12}"""
    _only(body, ("qty",))
    return _int(body, "qty", minimum=0)


def restock(body):
    """POST /machines/{id}/restocks  {"product_id": 1, "units": 30}"""
    _only(body, ("product_id", "units"))
    return _int(body, "product_id", minimum=1), _int(body, "units", minimum=1)


def new_user(body):
    """POST /users  {"name", "email", "password", "role" (optional, default "user")}"""
    _only(body, ("name", "email", "password", "role"))
    return {"name": _text(body, "name", max_length=100), "email": _text(body, "email"),
            "password": _text(body, "password"), "role": _text(body, "role", required=False) or "user"}


def user_update(body):
    """PATCH /users/{id}  {"role": "admin"|"user", "is_active": true|false} (at least one)"""
    _only(body, ("role", "is_active"))
    role, is_active = _text(body, "role", required=False), _bool(body, "is_active")
    if role is None and is_active is None:
        raise ValidationError("Send role and/or is_active.")
    return role, is_active


def password_reset(body):
    """PUT /users/{id}/password  {"new_password": "..."}"""
    _only(body, ("new_password",))
    return _text(body, "new_password")


def password_change(body):
    """PUT /me/password  {"current_password": "...", "new_password": "..."}"""
    _only(body, ("current_password", "new_password"))
    return _text(body, "current_password"), _text(body, "new_password")


# ------------------------------------------------------------------ catalogue: suppliers, products, machines
def _number(body, field, required=True):
    """A JSON number (int or decimal), e.g. a price in rand."""
    if field not in body:
        if required:
            raise ValidationError(f"{field} is required.", field)
        return None
    value = body[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a number, e.g. 9.50.", field)
    return value


def _at_least_one(values, fields):
    if all(v is None for v in values):
        raise ValidationError(f"Send at least one of: {', '.join(fields)}.")


def new_supplier(body):
    """POST /suppliers  {"name": "...", "lead_time_days": 2}"""
    _only(body, ("name", "lead_time_days"))
    return {"name": _text(body, "name", max_length=100),
            "lead_time_days": _int(body, "lead_time_days", minimum=0, maximum=365)}


def supplier_update(body):
    """PATCH /suppliers/{id}  {"name"?, "lead_time_days"?}"""
    fields = ("name", "lead_time_days")
    _only(body, fields)
    values = {"name": _text(body, "name", required=False, max_length=100),
              "lead_time_days": _int(body, "lead_time_days", minimum=0, maximum=365, required=False)}
    _at_least_one(values.values(), fields)
    return values


def new_product(body):
    """POST /products  {"name", "supplier_id", "unit_cost", "case_size", "central_threshold"?}"""
    _only(body, ("name", "supplier_id", "unit_cost", "case_size", "central_threshold"))
    values = {"name": _text(body, "name", max_length=100),
              "supplier_id": _int(body, "supplier_id", minimum=1),
              "unit_cost": _number(body, "unit_cost"),
              "case_size": _int(body, "case_size", minimum=1, maximum=1000)}
    threshold = _int(body, "central_threshold", minimum=0, maximum=5000, required=False)
    if threshold is not None:
        values["central_threshold"] = threshold
    return values


def product_update(body):
    """PATCH /products/{id}  {"name"?, "supplier_id"?, "unit_cost"?, "case_size"?}"""
    fields = ("name", "supplier_id", "unit_cost", "case_size")
    _only(body, fields)
    values = {"name": _text(body, "name", required=False, max_length=100),
              "supplier_id": _int(body, "supplier_id", minimum=1, required=False),
              "unit_cost": _number(body, "unit_cost", required=False),
              "case_size": _int(body, "case_size", minimum=1, maximum=1000, required=False)}
    _at_least_one(values.values(), fields)
    return values


def new_machine(body):
    """POST /machines  {"code": "UP-13", "location": "...", "drawer_capacity"?: 50}"""
    _only(body, ("code", "location", "drawer_capacity"))
    values = {"code": _text(body, "code", max_length=20), "location": _text(body, "location", max_length=100)}
    capacity = _int(body, "drawer_capacity", minimum=0, maximum=1000, required=False)
    if capacity is not None:
        values["drawer_capacity"] = capacity
    return values


def machine_update(body):
    """PATCH /machines/{id}  {"location"?, "drawer_capacity"?}"""
    fields = ("location", "drawer_capacity")
    _only(body, fields)
    values = {"location": _text(body, "location", required=False, max_length=100),
              "drawer_capacity": _int(body, "drawer_capacity", minimum=0, maximum=1000, required=False)}
    _at_least_one(values.values(), fields)
    return values


def machine_product(body):
    """POST /machines/{id}/products  {"product_id", "capacity"?, "threshold"?, "drawer_capacity"?, "drawer_threshold"?}"""
    optional = ("capacity", "threshold", "drawer_capacity", "drawer_threshold")
    _only(body, ("product_id",) + optional)
    values = {"product_id": _int(body, "product_id", minimum=1)}
    for field in optional:
        value = _int(body, field, minimum=0, maximum=1000, required=False)
        if value is not None:
            values[field] = value
    return values
