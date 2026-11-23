"""Contract tests: docs/openapi.json must match the real API exactly.

1. Every API route in the app is documented, and every documented operation exists.
2. Real responses (successes and errors) match the documented response schemas.
So the contract cannot silently drift away from the code.
"""
import json
import os
import re

import pytest

from tests.conftest import ADMIN_EMAIL, Api

SPEC_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "openapi.json")


@pytest.fixture(scope="module")
def spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ a small schema checker (no extra packages)
def resolve(spec, ref):
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def check(value, schema, spec, where="$"):
    """Fail with a clear message if `value` does not match the OpenAPI `schema`."""
    if "$ref" in schema:
        return check(value, resolve(spec, schema["$ref"]), spec, where)
    for part in schema.get("allOf", []):
        check(value, part, spec, where)
    if value is None:
        assert schema.get("nullable"), f"{where} is null but not nullable"
        return
    kind = schema.get("type")
    if kind == "object":
        assert isinstance(value, dict), f"{where} should be an object"
        missing = set(schema.get("required", [])) - set(value)
        assert not missing, f"{where} is missing {sorted(missing)}"
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(props)
            assert not extra, f"{where} has undocumented fields {sorted(extra)}"
        for key, sub in props.items():
            if key in value:
                check(value[key], sub, spec, f"{where}.{key}")
    elif kind == "array":
        assert isinstance(value, list), f"{where} should be an array"
        if schema.get("items"):
            for i, item in enumerate(value):
                check(item, schema["items"], spec, f"{where}[{i}]")
    elif kind == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), f"{where} should be an integer: {value!r}"
    elif kind == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool), f"{where} should be a number"
    elif kind == "string":
        assert isinstance(value, str), f"{where} should be a string: {value!r}"
    elif kind == "boolean":
        assert isinstance(value, bool), f"{where} should be true/false"
    if "enum" in schema:
        assert value in schema["enum"], f"{where} = {value!r} is not one of {schema['enum']}"


def response_schema(spec, path, method, status):
    documented = spec["paths"][path][method]["responses"]
    assert str(status) in documented, f"{method.upper()} {path} returned {status}, which is not documented"
    response = documented[str(status)]
    if "$ref" in response:
        response = resolve(spec, response["$ref"])
    return response.get("content", {}).get("application/json", {}).get("schema")


def conforms(spec, path, method, response):
    """Assert a real response matches the contract for its status code."""
    schema = response_schema(spec, path, method, response.status_code)
    if schema is None:
        assert not response.data, f"{method.upper()} {path} {response.status_code} should have no body"
    else:
        check(response.get_json(), schema, spec, f"{method.upper()} {path} {response.status_code}")


# ------------------------------------------------------------------ 1. routes and contract list the same operations
def documented_operations(spec):
    return {(method.upper(), path) for path, ops in spec["paths"].items() for method in ops}


def app_operations(app):
    found = set()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1"):
            path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule[len("/api/v1"):])
            found |= {(m, path) for m in rule.methods - {"HEAD", "OPTIONS"}}
    return found


def test_every_route_is_documented_and_every_documented_operation_exists(app, spec):
    assert app_operations(app) == documented_operations(spec)


def test_contract_basics(spec):
    assert spec["openapi"] == "3.0.3" and spec["servers"][0]["url"] == "/api/v1"
    ids = [op["operationId"] for ops in spec["paths"].values() for op in ops.values()]
    assert len(ids) == len(set(ids)), "operationIds must be unique"
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            names = {name for requirement in op["security"] for name in requirement}
            if method != "get" and path not in ("/auth/login",):
                assert "csrfHeader" in names, f"{method.upper()} {path} must document the CSRF header"
            if op["security"] and "sessionCookie" in names:
                assert "401" in op["responses"], f"{method.upper()} {path} must document 401"


def test_contract_is_served_by_the_api(api, spec):
    response = api.get("/openapi.json")
    assert response.status_code == 200 and response.get_json() == spec


# ------------------------------------------------------------------ 2. real responses match the contract
def test_read_endpoints_match_the_contract(user_api, spec):
    for path, url, params in [
        ("/auth/csrf", "/auth/csrf", {}), ("/auth/me", "/auth/me", {}), ("/dashboard", "/dashboard", {}),
        ("/machines", "/machines", {"sort": "-alerts"}), ("/machines/{machine_id}", "/machines/3", {}),
        ("/machines/{machine_id}/allocation", "/machines/3/allocation", {}),
        ("/central", "/central", {"per_page": 100}), ("/alerts", "/alerts", {"per_page": 100}),
        ("/movements", "/movements", {}), ("/shopping-list", "/shopping-list", {}),
    ]:
        conforms(spec, path, "get", user_api.get(url, **params))


def test_write_endpoints_match_the_contract(user_api, spec):
    conforms(spec, "/machines/{machine_id}/stock/{product_id}", "put", user_api.put("/machines/2/stock/1", {"qty": 3}))
    conforms(spec, "/machines/{machine_id}/restocks", "post",
             user_api.post("/machines/2/restocks", {"product_id": 1, "units": 30}))
    conforms(spec, "/central/{product_id}", "put", user_api.put("/central/1", {"qty": 40}))
    conforms(spec, "/movements", "get", user_api.get("/movements", per_page=100))   # now with real rows
    conforms(spec, "/me/password", "put",
             user_api.put("/me/password", {"current_password": "SmartStock123", "new_password": "new-password-1"}))
    conforms(spec, "/auth/logout", "post", user_api.post("/auth/logout"))


def test_admin_endpoints_match_the_contract(admin_api, spec):
    conforms(spec, "/users", "get", admin_api.get("/users"))
    created = admin_api.post("/users", {"name": "Thabo", "email": "thabo@adlers.test", "password": "longenough1"})
    conforms(spec, "/users", "post", created)
    user_id = created.get_json()["id"]
    conforms(spec, "/users/{user_id}", "patch", admin_api.patch(f"/users/{user_id}", {"is_active": False}))
    conforms(spec, "/users/{user_id}/password", "put",
             admin_api.put(f"/users/{user_id}/password", {"new_password": "longenough2"}))


def test_error_responses_match_the_contract(api, user_api, admin_api, spec):
    conforms(spec, "/machines", "get", api.get("/machines"))                                     # 401
    conforms(spec, "/machines", "get", user_api.get("/machines", sort="nope"))                   # 400
    conforms(spec, "/machines/{machine_id}", "get", user_api.get("/machines/999"))               # 404
    conforms(spec, "/central/{product_id}", "put", user_api.put("/central/1", {"qty": "x"}))     # 400
    conforms(spec, "/users", "get", user_api.get("/users"))                                      # 403
    conforms(spec, "/users", "post", admin_api.post("/users", {"name": "Copy", "email": "msiza@adlers.test",
                                                               "password": "longenough1"}))      # 409
    conforms(spec, "/users/{user_id}", "patch", admin_api.patch("/users/2", {"role": "user"}))    # 409 own role
    login = Api(admin_api.client.application.test_client())
    login.csrf = login.get("/auth/csrf").get_json()["csrf_token"]
    conforms(spec, "/auth/login", "post", login.post("/auth/login", {"email": ADMIN_EMAIL, "password": "wrong"}))  # 401


def test_catalogue_endpoints_match_the_contract(user_api, admin_api, spec):
    created = user_api.post("/suppliers", {"name": "Supplier D - Dairy", "lead_time_days": 2})
    conforms(spec, "/suppliers", "post", created)
    sid = created.get_json()["id"]
    conforms(spec, "/suppliers", "get", user_api.get("/suppliers"))
    conforms(spec, "/suppliers/{supplier_id}", "get", user_api.get(f"/suppliers/{sid}"))
    conforms(spec, "/suppliers/{supplier_id}", "patch", user_api.patch(f"/suppliers/{sid}", {"lead_time_days": 3}))
    product = user_api.post("/products", {"name": "Yoghurt 175g", "supplier_id": sid, "unit_cost": 11.5, "case_size": 12})
    conforms(spec, "/products", "post", product)
    pid = product.get_json()["id"]
    conforms(spec, "/products", "get", user_api.get("/products", per_page=100))
    conforms(spec, "/products/{product_id}", "get", user_api.get(f"/products/{pid}"))
    conforms(spec, "/products/{product_id}", "patch", user_api.patch(f"/products/{pid}", {"unit_cost": 12}))
    machine = user_api.post("/machines", {"code": "UP-13", "location": "Engineering 3"})
    conforms(spec, "/machines", "post", machine)
    mid = machine.get_json()["id"]
    conforms(spec, "/machines/{machine_id}", "patch", user_api.patch(f"/machines/{mid}", {"location": "Eng 3"}))
    conforms(spec, "/machines/{machine_id}/products", "post", user_api.post(f"/machines/{mid}/products", {"product_id": pid}))
    conforms(spec, "/machines/{machine_id}/products", "post", user_api.post(f"/machines/{mid}/products", {"product_id": pid}))  # 409
    conforms(spec, "/products", "post", user_api.post("/products", {"name": "Yoghurt 175g", "supplier_id": sid,
                                                                     "unit_cost": 1, "case_size": 1}))         # 409
    conforms(spec, "/users/{user_id}", "get", admin_api.get("/users/1"))
    conforms(spec, "/users/{user_id}", "get", user_api.get("/users/1"))                                         # 403
