# SmartStock REST API (v1)

The API gives other programs (a phone app, Postman, a script, a future sensor bridge) the same data and actions
as the web pages. Every address starts with **`/api/v1`**, every request and response body is JSON, and the
full machine-readable contract is in [`openapi.json`](openapi.json). The running app also serves it at
`/api/v1/openapi.json` (open it in Swagger Editor or import it into Postman). A test (`tests/test_openapi.py`)
checks that this contract and the real API never drift apart.

The examples below are real responses recorded from SmartStock running on MySQL with the demo data.

---

## 1. How it works

### Logging in (session + CSRF token)

The API uses the **same login session as the web pages** (Flask-Login), so roles and logouts behave the same.

1. `GET /api/v1/auth/csrf` returns a CSRF token and starts a session (a cookie).
2. `POST /api/v1/auth/login` with your email and password, and the token in the **`X-CSRF-Token`** header.
3. Keep the session cookie. Send `X-CSRF-Token` on **every POST, PUT and PATCH**. Reads (GET) do not need it.

Why the token: it stops another website from making a logged-in browser change stock behind the user's back
(cross-site request forgery). The web forms use the same token in a hidden field.

### Roles

| Role | Who | Can |
|---|---|---|
| `user` | Mr Msiza and anyone helping him restock | Read everything, record counts, log restocks, do stock takes, add and change suppliers, products and machines, change own password |
| `admin` | The developer | Everything above, plus the `/users` endpoints |

Not logged in gives **401**. Logged in but not allowed gives **403**. The role is checked in the services layer as
well as here, so no endpoint can skip it by mistake.

### Lists: paging, sorting, filtering

List endpoints return one page:

```json
{ "items": [ ... ], "page": 1, "per_page": 20, "total": 37, "pages": 2, "has_prev": false, "has_next": true }
```

| Parameter | Meaning |
|---|---|
| `page` | Page number, from 1 (default 1). A page past the end returns an empty `items` list, not an error. |
| `per_page` | Items per page, 1 to 100 (default 20) |
| `sort` | `sort=name` sorts A to Z or low to high; `sort=-name` reverses it. Only the keys listed per endpoint are accepted. |
| filters | Listed per endpoint below |

### Errors

Every error has the same shape. `field` names the parameter or body field that was wrong, when there is one.

```json
{ "error": { "status": 400, "message": "qty must be a whole number.", "field": "qty" } }
```

| Status | When |
|---|---|
| 400 | Invalid input: wrong type, out of range, unknown field, not JSON, bad `sort`/`page`, or a missing/wrong CSRF token |
| 401 | Not logged in, or wrong email or password on login |
| 403 | Your role does not allow this (e.g. a `user` calling `/users`) |
| 404 | The machine, product or user does not exist, the machine does not carry that product, or there is no such API address |
| 405 | That method is not allowed on this address (e.g. `DELETE /machines`) |
| 409 | Conflict: email already used, changing your own role, switching yourself off, removing the last active admin |
| 500 | Unexpected server error (logged in `logs/errors.log` on a production server) |

Request bodies are checked strictly: numbers must be real JSON numbers (`12`, not `"12"`, `12.5` or `true`),
and **unknown fields are rejected**, so a typo such as `"quantity"` instead of `"qty"` is reported instead of ignored.

---

## 2. Endpoint list

| Method | Address | Who | What | Success |
|---|---|---|---|---|
| GET | `/auth/csrf` | anyone | Get a CSRF token and a session | 200 |
| POST | `/auth/login` | anyone | Log in | 200 |
| POST | `/auth/logout` | logged in | Log out | 204 |
| GET | `/auth/me` | logged in | Who am I, my permissions, my CSRF token | 200 |
| PUT | `/me/password` | logged in | Change my password | 204 |
| GET | `/dashboard` | logged in | KPIs, top 5 alerts, order summary, best sellers, sales window | 200 |
| GET | `/machines` | logged in | List machines with their alert count | 200 |
| POST | `/machines` | logged in | Add a machine | 201 |
| GET | `/machines/{machine_id}` | logged in | One machine: all three stock tiers per product (O2) | 200 |
| PATCH | `/machines/{machine_id}` | logged in | Change a machine's location or drawer capacity | 200 |
| POST | `/machines/{machine_id}/products` | logged in | Start carrying a product in a machine (slots start at 0 units) | 201 |
| PUT | `/machines/{machine_id}/stock/{product_id}` | logged in | Record a machine count | 200 |
| POST | `/machines/{machine_id}/restocks` | logged in | Log a restock visit (machine, then drawer, rest to central) | 200 |
| GET | `/machines/{machine_id}/allocation` | logged in | Drawer allocation ranking (O3) | 200 |
| GET | `/central` | logged in | List central storage | 200 |
| PUT | `/central/{product_id}` | logged in | Record a central stock take | 200 |
| GET | `/alerts` | logged in | Low-stock alerts in all tiers | 200 |
| GET | `/movements` | logged in | Audit trail of every stock change | 200 |
| GET | `/shopping-list` | logged in | One order per supplier (O4) | 200 |
| GET | `/products` | logged in | List products with supplier, cost and central stock | 200 |
| POST | `/products` | logged in | Add a product (its central storage row starts at 0) | 201 |
| GET | `/products/{product_id}` | logged in | One product | 200 |
| PATCH | `/products/{product_id}` | logged in | Change a product's name, supplier, cost or case size | 200 |
| GET | `/suppliers` | logged in | List suppliers | 200 |
| POST | `/suppliers` | logged in | Add a supplier | 201 |
| GET | `/suppliers/{supplier_id}` | logged in | One supplier | 200 |
| PATCH | `/suppliers/{supplier_id}` | logged in | Change a supplier's name or lead time | 200 |
| GET | `/users` | admin | List accounts | 200 |
| POST | `/users` | admin | Add an account | 201 |
| GET | `/users/{user_id}` | admin | One account | 200 |
| PATCH | `/users/{user_id}` | admin | Change role and/or switch an account on or off | 200 |
| PUT | `/users/{user_id}/password` | admin | Set a new password for an account | 204 |
| GET | `/openapi.json` | anyone | This contract | 200 |

### Filters and sort keys per list

| Endpoint | Filters | Sort keys (default first) |
|---|---|---|
| `GET /machines` | `search` (text in code or location) | `code`, `location`, `alerts` |
| `GET /central` | `search` (product name), `supplier_id`, `low_only=true` | `name`, `supplier`, `qty`, `value` |
| `GET /alerts` | `tier` (`Machine`, `Drawer`, `Central`), `severity` (`out`, `low`), `machine_id` | fixed: out of stock first, then by tier |
| `GET /movements` | `machine_id`, `product_id`, `tier`, `date_from`, `date_to` (YYYY-MM-DD) | fixed: newest first |
| `GET /products` | `search` (product name), `supplier_id` | `name`, `supplier`, `unit_cost`, `central_qty` |
| `GET /suppliers` | none | fixed: by name |
| `GET /users` | none | fixed: by name |

---

## 3. Examples

The examples use the demo login `msiza@adlers.test` / `SmartStock123` and the app running locally.

### PowerShell (Windows)

```powershell
$api = "http://127.0.0.1:5000/api/v1"
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession        # keeps the session cookie

# 1-2: token, then log in
$token = (Invoke-RestMethod "$api/auth/csrf" -WebSession $s).csrf_token
$login = @{ email = "msiza@adlers.test"; password = "SmartStock123" } | ConvertTo-Json
Invoke-RestMethod "$api/auth/login" -Method Post -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $token } -Body $login

# read: machines with the most alerts first
(Invoke-RestMethod "$api/machines?sort=-alerts&per_page=5" -WebSession $s).items | Format-Table

# change: log a restock visit at machine 3
Invoke-RestMethod "$api/machines/3/restocks" -Method Post -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $token } -Body '{"product_id": 1, "units": 30}'
```

### curl (Linux, macOS, or `curl.exe` on Windows)

```bash
API=http://127.0.0.1:5000/api/v1
TOKEN=$(curl -s -c jar.txt -b jar.txt $API/auth/csrf | python -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")
curl -s -c jar.txt -b jar.txt -X POST $API/auth/login -H "Content-Type: application/json" \
     -H "X-CSRF-Token: $TOKEN" -d '{"email": "msiza@adlers.test", "password": "SmartStock123"}'
curl -s -b jar.txt "$API/machines?sort=-alerts&per_page=2"
curl -s -b jar.txt -X POST $API/machines/3/restocks -H "Content-Type: application/json" \
     -H "X-CSRF-Token: $TOKEN" -d '{"product_id": 1, "units": 30}'
```

### `POST /auth/login`

Request: `{"email": "msiza@adlers.test", "password": "SmartStock123"}`

```json
{
  "id": 1, "name": "Mr Msiza", "email": "msiza@adlers.test", "role": "user",
  "permissions": ["change_stock", "view"],
  "csrf_token": "f95b152b5e6119fc5149d5f08ffdc502"
}
```

### `GET /machines?sort=-alerts&per_page=2`

```json
{
  "items": [
    { "id": 1, "code": "UP-01", "location": "Engineering 1", "drawer_capacity": 50, "alerts": 2 },
    { "id": 3, "code": "UP-03", "location": "Law Building", "drawer_capacity": 50, "alerts": 1 }
  ],
  "page": 1, "per_page": 2, "total": 12, "pages": 6, "has_prev": false, "has_next": true
}
```

### `PUT /machines/3/stock/1` (record a machine count)

Request: `{"qty": 4}`. Response: the product's three tiers after the change.

```json
{
  "product_id": 1, "name": "Coca-Cola 300ml",
  "machine": { "qty": 4,  "capacity": 20,   "threshold": 5 },
  "drawer":  { "qty": 3,  "capacity": 12,   "threshold": 2 },
  "central": { "qty": 60, "capacity": null, "threshold": 20 }
}
```

### `POST /machines/3/restocks` (log a restock visit)

Request: `{"product_id": 1, "units": 30}`. The 30 units are **taken out of central storage** (60 cans). They fill
the machine (8), top the drawer up to its recommendation (9), and the rest goes back to central storage (13).
So central storage only goes down by what was used: 60 - 8 - 9 = 43. Each tier's change is a row in the audit trail.

```json
{
  "split": { "to_machine": 8, "to_drawer": 9, "to_central": 13 },
  "stock": {
    "product_id": 1, "name": "Coca-Cola 300ml",
    "machine": { "qty": 20, "capacity": 20,   "threshold": 5 },
    "drawer":  { "qty": 12, "capacity": 12,   "threshold": 2 },
    "central": { "qty": 43, "capacity": null, "threshold": 20 }
  }
}
```

A visit cannot take more than central storage holds. Asking for 24 bottles of water when central storage has 10
gives a `400`, and nothing changes; record the supplier delivery first (`PUT /central/13`):

```json
{ "error": { "status": 400, "field": "units",
             "message": "Central storage only holds 10 of this product, so 24 cannot be taken. Record the supplier delivery on the Central storage page first." } }
```

### `GET /movements?machine_id=3&per_page=2` (audit trail)

```json
{
  "items": [
    { "id": 3, "time": "2026-11-23 07:13", "created_at": "2026-11-23T07:13:14",
      "machine_id": 3, "machine": "UP-03", "product_id": 1, "product": "Coca-Cola 300ml",
      "tier": "Central", "old": 60, "new": 43, "change": -17,
      "user": "Mr Msiza", "note": "Restock visit: 30 taken, 13 returned" },
    { "id": 2, "time": "2026-11-23 07:13", "created_at": "2026-11-23T07:13:14",
      "machine_id": 3, "machine": "UP-03", "product_id": 1, "product": "Coca-Cola 300ml",
      "tier": "Drawer", "old": 3, "new": 12, "change": 9,
      "user": "Mr Msiza", "note": "Restock visit" }
  ],
  "page": 1, "per_page": 2, "total": 3, "pages": 2, "has_prev": false, "has_next": true
}
```

### `GET /alerts?severity=out&per_page=1`

```json
{
  "items": [
    { "tier": "Machine", "location": "UP-05", "machine_id": 5, "product_id": 13, "product": "Water 500ml",
      "qty": 0, "threshold": 5, "severity": "Out of stock", "tone": "danger" }
  ],
  "page": 1, "per_page": 1, "total": 2, "pages": 2, "has_prev": false, "has_next": true
}
```

### `GET /central?low_only=true&sort=qty&per_page=1`

```json
{
  "items": [
    { "product_id": 13, "name": "Water 500ml", "supplier_id": 3, "supplier": "Supplier C - Water",
      "unit_cost": 5.0, "qty": 10, "threshold": 20, "value": 50.0 }
  ],
  "page": 1, "per_page": 1, "total": 5, "pages": 5, "has_prev": false, "has_next": true
}
```

### Errors (real responses)

`PUT /central/1` with `{"qty": "lots"}` gives **400**:

```json
{ "error": { "status": 400, "message": "qty must be a whole number.", "field": "qty" } }
```

The same request **without the `X-CSRF-Token` header** gives **400**:

```json
{ "error": { "status": 400, "message": "Missing or wrong CSRF token. Get one from GET /api/v1/auth/csrf and send it in the X-CSRF-Token header." } }
```

`GET /users` as Mr Msiza (role `user`) gives **403**:

```json
{ "error": { "status": 403, "message": "You do not have permission to do that." } }
```

---

### Adding to the catalogue: supplier, product, machine (real responses)

```powershell
$h = @{ "X-CSRF-Token" = $token }
Invoke-RestMethod "$api/suppliers" -Method Post -WebSession $s -ContentType "application/json" -Headers $h `
    -Body '{"name": "Supplier D - Dairy", "lead_time_days": 2}'                                # 201
Invoke-RestMethod "$api/products" -Method Post -WebSession $s -ContentType "application/json" -Headers $h `
    -Body '{"name": "Yoghurt 175g", "supplier_id": 4, "unit_cost": 11.5, "case_size": 12}'      # 201
Invoke-RestMethod "$api/machines" -Method Post -WebSession $s -ContentType "application/json" -Headers $h `
    -Body '{"code": "UP-13", "location": "Engineering 3"}'                                      # 201
Invoke-RestMethod "$api/machines/13/products" -Method Post -WebSession $s -ContentType "application/json" -Headers $h `
    -Body '{"product_id": 16}'                                                                  # 201
Invoke-RestMethod "$api/products/16" -Method Patch -WebSession $s -ContentType "application/json" -Headers $h `
    -Body '{"unit_cost": 12.25}'                                                                # 200
```

`POST /products` response:

```json
{ "id": 16, "name": "Yoghurt 175g", "supplier_id": 4, "supplier": "Supplier D - Dairy", "unit_cost": 11.5,
  "case_size": 12, "central_qty": 0, "central_threshold": 20, "machines": 0 }
```

Adding a product name or machine code that already exists gives **409**, e.g.
`{"error": {"status": 409, "message": "A product called 'Yoghurt 175g' already exists.", "field": "name"}}`.

---

## 4. Admin examples

```powershell
# add an account for a helper (admin session and token as above)
$new = @{ name = "Thabo Helper"; email = "thabo@adlers.test"; password = "helper-pass-1" } | ConvertTo-Json
Invoke-RestMethod "$api/users" -Method Post -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $token } -Body $new                         # 201 Created

# switch the account off when they stop helping (their history stays in the audit trail)
Invoke-RestMethod "$api/users/3" -Method Patch -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRF-Token" = $token } -Body '{"is_active": false}'
```

---

## 5. Where things live in the code

| Part | File |
|---|---|
| Routes (HTTP in and out only) | `app/blueprints/api.py` |
| Request body checks | `app/schemas/__init__.py` |
| CSRF header check, JSON 404/405/500 | `app/__init__.py` |
| Business rules, database, role checks | `app/services/` |
| Contract | `docs/openapi.json` |
| Tests | `tests/test_api.py` (behaviour), `tests/test_openapi.py` (contract matches code) |
