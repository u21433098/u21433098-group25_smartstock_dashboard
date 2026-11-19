"""List pages wired to the services: search, filters, sorting, paging, and the empty and error states.

Everything is server-side (no JavaScript): each filter, sort and page is part of the address.
"""
import re

from app.extensions import db
from app.models import CentralStock, Machine


def rows(html, marker):
    """How many times `marker` appears in the page (one per table row)."""
    return html.count(marker)


# ------------------------------------------------------------------ machines
def test_machines_page_is_paged_ten_at_a_time(user_client):
    first = user_client.get("/machines").get_data(as_text=True)
    assert "Showing 1&ndash;10 of 12" in first and rows(first, "Open UP-") == 10
    assert 'href="/machines?page=2"' in first and 'aria-current="page">1<' in first
    second = user_client.get("/machines?page=2").get_data(as_text=True)
    assert "Showing 11&ndash;12 of 12" in second and "Open UP-12" in second and "Open UP-01" not in second


def test_machines_sort_links_flip_direction_and_set_aria_sort(user_client):
    page = user_client.get("/machines").get_data(as_text=True)
    assert 'aria-sort="ascending"' in page                       # default: by code, A to Z
    assert 'href="/machines?sort=-code"' in page                 # clicking it again flips the order
    flipped = user_client.get("/machines?sort=-code").get_data(as_text=True)
    assert 'aria-sort="descending"' in flipped
    assert flipped.index("Open UP-12") < flipped.index("Open UP-11")


def test_sorting_keeps_the_search_and_paging_keeps_both(user_client):
    page = user_client.get("/machines?search=up-1&sort=location").get_data(as_text=True)
    assert "search=up-1" in page.split('aria-sort="ascending"')[1].split("</th>")[0]
    assert rows(page, "Open UP-") == 3


def test_machine_search_and_its_empty_state(user_client):
    found = user_client.get("/machines?search=Library").get_data(as_text=True)
    assert "Open UP-02" in found and rows(found, "Open UP-") == 1
    nothing = user_client.get("/machines?search=Mars").get_data(as_text=True)
    assert "No machines match &#34;Mars&#34;" in nothing and "Clear the filters" in nothing


def test_bad_values_in_the_address_show_a_warning_not_an_error_page(user_client):
    for url in ("/machines?sort=password", "/machines?page=abc", "/central?supplier_id=x",
                "/alerts?tier=Car", "/activity?date_from=yesterday"):
        response = user_client.get(url)
        assert response.status_code == 200, url
        assert b"Showing the unfiltered list instead" in response.data, url


def test_empty_database_shows_empty_states(user_client):
    db.session.execute(db.delete(Machine))
    db.session.commit()
    assert b"No machines have been set up yet" in user_client.get("/machines").data
    assert b"No stock changes recorded yet" in user_client.get("/activity").data


# ------------------------------------------------------------------ central storage
def test_central_filters_and_sorting(user_client):
    water = user_client.get("/central?supplier_id=3").get_data(as_text=True)
    assert "Water 500ml" in water and "Coca-Cola" not in water
    low = user_client.get("/central?low_only=1").get_data(as_text=True)
    assert "Water 500ml" in low and "Fanta" not in low            # water is 10 (low), Fanta 70 (fine)
    by_qty = user_client.get("/central?sort=-qty").get_data(as_text=True)    # most stock first
    assert by_qty.index("Fanta 300ml") < by_qty.index("Coca-Cola 300ml") < by_qty.index("Sprite 300ml")
    assert b"No products match these filters" in user_client.get("/central?search=caviar").data


def test_stock_take_returns_to_the_same_filtered_page(user_client):
    response = user_client.post("/central/13?supplier_id=3&sort=-qty", data={"qty": 44})
    assert response.status_code == 302
    assert "supplier_id=3" in response.headers["Location"] and "sort=-qty" in response.headers["Location"]
    db.session.rollback()   # see what the request committed
    assert db.session.get(CentralStock, 13).qty == 44


# ------------------------------------------------------------------ alerts
def test_alert_filters(user_client):
    out = user_client.get("/alerts?severity=out").get_data(as_text=True)
    assert "Out of stock" in out and ">Low<" not in out
    drawer = user_client.get("/alerts?tier=Drawer").get_data(as_text=True)
    tiers = set(re.findall(r"<td>(Machine|Drawer|Central)</td>", drawer))
    assert tiers == {"Drawer"}
    assert b"No alerts match these filters" in user_client.get("/alerts?tier=Central&machine_id=1").data


def test_central_alert_links_to_a_filtered_central_page(user_client):
    page = user_client.get("/alerts?tier=Central").get_data(as_text=True)
    assert "/central?search=" in page


# ------------------------------------------------------------------ activity log
def test_activity_page_shows_changes_with_filters(user_client):
    user_client.post("/machines/3/count", data={"product_id": 1, "qty": 2})
    user_client.post("/central/2", data={"qty": 40})
    everything = user_client.get("/activity").get_data(as_text=True)
    assert "Manual count" in everything and "Stock take" in everything and "Mr Msiza" in everything
    machine_only = user_client.get("/activity?machine_id=3").get_data(as_text=True)
    assert "Manual count" in machine_only and "Stock take" not in machine_only
    central_only = user_client.get("/activity?tier=Central").get_data(as_text=True)
    assert "Stock take" in central_only and "Manual count" not in central_only
    future = user_client.get("/activity?date_from=2099-01-01").get_data(as_text=True)
    assert "No stock changes match these filters" in future


def test_machine_page_links_to_its_full_activity(user_client):
    assert b'href="/activity?machine_id=4"' in user_client.get("/machines/4").data


# ------------------------------------------------------------------ dashboard
def test_dashboard_kpis_link_to_their_pages_and_show_the_sales_window(user_client):
    page = user_client.get("/").get_data(as_text=True)
    for target in ("/machines", "/alerts", "/central", "/shopping-list"):
        assert f'class="stretched-link kpi-link" href="{target}"' in page
    assert re.search(r"Sales data: \d\d \w{3} to \d\d \w{3} \d{4} \(30 days\)", page)


# ------------------------------------------------------------------ accessibility basics
def test_every_page_has_one_h1_labelled_inputs_and_a_skip_link(user_client, admin_client):
    for client, url in [(user_client, u) for u in ("/", "/machines", "/machines/1", "/central", "/allocation",
                                                   "/shopping-list", "/alerts", "/activity", "/account/password")] + \
                       [(admin_client, "/admin/users")]:
        html = client.get(url).get_data(as_text=True)
        assert html.count("<h1") == 1, url
        assert 'href="#main"' in html, url
        for input_id in re.findall(r'<(?:input|select)[^>]*\bid="([^"]+)"', html):
            assert f'for="{input_id}"' in html, f"{url}: #{input_id} has no label"


def test_crafted_address_cannot_change_where_links_and_redirects_point(user_client):
    """url_for() options such as _external and _anchor must never be taken from the address."""
    html = user_client.get("/machines?_external=1&_anchor=x&_scheme=javascript&search=up").get_data(as_text=True)
    links = re.findall(r'class="(?:sort-link[^"]*|page-link)"[^>]*href="([^"]+)"', html)
    assert links and all(link.startswith("/machines?") and "#" not in link for link in links)
    response = user_client.post("/central/1?_external=1&_anchor=x&supplier_id=1", data={"qty": 5})
    assert response.headers["Location"] == "/central?supplier_id=1"
