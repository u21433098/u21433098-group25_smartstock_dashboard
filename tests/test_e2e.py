"""End-to-end flows: the real jobs Mr Msiza does, start to finish, through the web pages.

Each test follows one flow the way a person would click through it, and checks what
they would see on screen at each step. docs/e2e_flows.md describes the same flows
with screenshots.

Flow 1  Low-stock alert -> restock visit -> alert cleared            (O2, O3, alerts)
Flow 2  Shopping list -> supplier delivery -> stock take -> shorter list (O4)
Flow 3  Drawer allocation -> follow the recommendation              (O3)
Flow 4  Admin adds a helper -> helper works -> admin switches them off (roles)
Flow 5  An outside program does a restock through the JSON API       (API)
"""
import re

from tests.conftest import PASSWORD, Api


def has_water(html):
    """Plain 'Water 500ml' (not 'Flavoured Water 500ml'), even with an 'Urgent' badge after it."""
    return re.search(r">Water 500ml[\s<]", html) is not None


def text(response):
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def row_containing(html, *needles):
    """The first table row (<tr>...</tr>) that contains every needle, or None."""
    for row in re.findall(r"<tr>.*?</tr>", html, flags=re.S):
        if all(n in row for n in needles):
            return row
    return None


# ------------------------------------------------------------------ flow 1
def test_flow_1_alert_to_restock_visit(user_client):
    # 1. The dashboard warns that UP-01 is low on Coca-Cola.
    dashboard = text(user_client.get("/"))
    assert row_containing(dashboard, "Coca-Cola 300ml", "Machine: UP-01", "Low")

    # 2. The alerts page, filtered to UP-01, shows the machine slot at 4 (threshold 5).
    alerts = text(user_client.get("/alerts?machine_id=1"))
    assert row_containing(alerts, "Coca-Cola 300ml", "<td>Machine</td>", ">4<")

    # 3. He opens UP-01: machine, drawer and central stock side by side.
    machine = text(user_client.get("/machines/1"))
    assert row_containing(machine, "Coca-Cola 300ml", "4 / 20")

    # 4. He logs the visit: 30 cans brought.
    done = text(user_client.post("/machines/1/restock", data={"product_id": 1, "units": 30}, follow_redirects=True))
    split = re.search(r"Restock saved: (\d+) into the machine, (\d+) into the drawer, (\d+) returned", done)
    to_machine, to_drawer, to_central = map(int, split.groups())
    assert (to_machine, to_machine + to_drawer + to_central) == (16, 30)    # machine filled to 20 first
    assert row_containing(done, "Coca-Cola 300ml", "20 / 20")

    # 5. The alert is gone, and UP-01 now has one alert fewer on the machine list.
    assert not row_containing(text(user_client.get("/alerts?machine_id=1")), "Coca-Cola 300ml", "<td>Machine</td>")
    assert row_containing(text(user_client.get("/machines")), "UP-01", "1 low")

    # 6. The activity log shows every part of the visit, by him.
    log = text(user_client.get("/activity?machine_id=1"))
    for note in ("Restock visit", "Returned after restock visit"):
        assert row_containing(log, "Coca-Cola 300ml", note, "Mr Msiza")


# ------------------------------------------------------------------ flow 2
def test_flow_2_shopping_list_to_stock_take(user_client):
    # 1. The shopping list has one order per supplier; water comes from Supplier C.
    before = text(user_client.get("/shopping-list"))
    assert "Supplier C - Water" in before and has_water(before)
    trips_before = before.count('class="card mb-3')

    # 2. Central storage, filtered to the water supplier and low stock, shows the low water.
    central = text(user_client.get("/central?supplier_id=3&low_only=1"))
    assert has_water(central)

    # 3. After the supplier run he does a stock take of the delivery: 250 bottles.
    saved = text(user_client.post("/central/13?supplier_id=3&low_only=1", data={"qty": 250}, follow_redirects=True))
    assert "Central storage count saved" in saved
    assert not has_water(saved)                                 # no longer low, so filtered out

    # 4. Water drops off the shopping list, so the Supplier C trip is no longer needed.
    after = text(user_client.get("/shopping-list"))
    assert not has_water(after) and "Supplier C - Water" not in after
    assert after.count('class="card mb-3') == trips_before - 1

    # 5. The central-storage water alert is cleared.
    assert not row_containing(text(user_client.get("/alerts?tier=Central")), "<td>Water 500ml</td>")


# ------------------------------------------------------------------ flow 3
def test_flow_3_follow_the_drawer_recommendation(user_client):
    # 1. The allocation page for UP-04 recommends topping up the water in the drawer.
    plan = text(user_client.get("/allocation?machine=4"))
    water = row_containing(plan, "Water 500ml")
    assert "Top up by 8" in water

    # 2. He brings 40 bottles: the machine is filled first, then the drawer up to the recommendation.
    text(user_client.post("/machines/4/restock", data={"product_id": 13, "units": 40}, follow_redirects=True))

    # 3. The recommendation is now met.
    assert "No change" in row_containing(text(user_client.get("/allocation?machine=4")), "Water 500ml")


# ------------------------------------------------------------------ flow 4
def test_flow_4_admin_onboards_and_offboards_a_helper(admin_client, app):
    # 1. The admin adds an account for a helper.
    added = text(admin_client.post("/admin/users", data={
        "name": "Thabo Helper", "email": "thabo@adlers.test", "role": "user",
        "password": "helper-pass-1", "confirm": "helper-pass-1"}, follow_redirects=True))
    assert "Account created for Thabo Helper" in added
    helper_id = re.search(r'/admin/users/(\d+)/active', row_containing(added, "Thabo Helper")).group(1)

    # 2. The helper logs in, sees no Users page, and records a count at UP-02.
    helper = app.test_client()
    assert helper.post("/login", data={"email": "thabo@adlers.test", "password": "helper-pass-1"}).status_code == 302
    assert 'href="/admin/users"' not in text(helper.get("/"))
    assert helper.get("/admin/users").status_code == 403
    text(helper.post("/machines/2/count", data={"product_id": 1, "qty": 9}, follow_redirects=True))

    # 3. The admin sees the helper's change in the activity log.
    assert row_containing(text(admin_client.get("/activity?machine_id=2")), "Manual count", "Thabo Helper")

    # 4. The helper stops helping: the admin switches the account off.
    text(admin_client.post(f"/admin/users/{helper_id}/active", data={"active": "0"}, follow_redirects=True))
    assert helper.get("/").status_code == 302                                    # logged out at once
    assert app.test_client().post("/login", data={"email": "thabo@adlers.test",
                                                  "password": "helper-pass-1"}).status_code == 200  # login refused

    # 5. Their history stays in the activity log.
    assert row_containing(text(admin_client.get("/activity?machine_id=2")), "Manual count", "Thabo Helper")


# ------------------------------------------------------------------ flow 5
def test_flow_5_outside_program_restocks_through_the_api(app):
    robot = Api(app.test_client())
    assert robot.login().status_code == 200

    # 1. Find the most urgent machine alert.
    alert = robot.get("/alerts", tier="Machine", severity="out").get_json()["items"][0]
    assert (alert["location"], alert["product"], alert["qty"]) == ("UP-05", "Water 500ml", 0)

    # 2. Log the restock for it.
    result = robot.post(f"/machines/{alert['machine_id']}/restocks", {"product_id": alert["product_id"], "units": 24})
    assert result.status_code == 200 and result.get_json()["stock"]["machine"]["qty"] > 0

    # 3. The alert is gone, and the change is in the audit trail under the API user's name.
    remaining = robot.get("/alerts", machine_id=alert["machine_id"], per_page=100).get_json()["items"]
    assert not [a for a in remaining if a["product_id"] == alert["product_id"] and a["tier"] == "Machine"]
    latest = robot.get("/movements", machine_id=alert["machine_id"]).get_json()["items"]
    assert latest and latest[-1]["user"] == "Mr Msiza" and latest[-1]["note"] == "Restock visit"

    # 4. The same change shows up on the web page a person would look at.
    web = app.test_client()
    web.post("/login", data={"email": "msiza@adlers.test", "password": PASSWORD})
    assert row_containing(text(web.get(f"/activity?machine_id={alert['machine_id']}")), "Restock visit", "Water 500ml")
