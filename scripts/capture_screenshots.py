"""Walk through SmartStock in a real browser and save the screenshots used in docs/.

This doubles as a browser check of the end-to-end flows: if a page or a step breaks,
the script stops with an error instead of saving a screenshot.

One-time setup (not needed to run SmartStock itself):
    pip install playwright
    playwright install chromium

Run (with the app running in another terminal, on freshly seeded demo data):
    flask seed --yes
    python run.py                                   (other terminal)
    python scripts/capture_screenshots.py

Options:
    --base-url URL        default http://127.0.0.1:5000
    --out FOLDER          default docs/screenshots
    --bootstrap-css FILE  serve Bootstrap's CSS from this file instead of the CDN (for offline machines)
"""
import argparse
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

USER = ("msiza@adlers.test", "SmartStock123")
ADMIN = ("admin@smartstock.test", "SmartStock123")
CDN = re.compile(r"https://cdn\.jsdelivr\.net/npm/bootstrap@.*\.css")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--out", default=os.path.join("docs", "screenshots"))
    parser.add_argument("--bootstrap-css")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    base = args.base_url.rstrip("/")
    saved = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_page(width=1280, height=800):
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
            if args.bootstrap_css:
                css = open(args.bootstrap_css, encoding="utf-8").read()
                context.route(CDN, lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            return context.new_page()

        def shot(page, name, full_page=True):
            path = os.path.join(args.out, f"{name}.png")
            page.screenshot(path=path, full_page=full_page)
            saved.append(path)
            print("saved", path)

        def log_in(page, who):
            page.goto(f"{base}/login")
            page.get_by_label("Email").fill(who[0])
            page.get_by_label("Password").fill(who[1])
            page.get_by_role("button", name="Log in").click()
            expect(page.get_by_role("heading", level=1)).to_have_text("SmartStock dashboard")

        page = new_page()

        # ---------- logging in
        page.goto(f"{base}/login")
        shot(page, "01_login", full_page=False)
        log_in(page, USER)
        shot(page, "02_dashboard")

        # ---------- flow 1: alert -> restock visit -> alert cleared
        page.goto(f"{base}/alerts?machine_id=1")
        shot(page, "03_flow1_alerts_up01")
        page.goto(f"{base}/machines/1")
        shot(page, "04_flow1_machine_up01_before")
        page.get_by_label("Product").first.select_option(label="Coca-Cola 300ml")
        page.get_by_label("Units brought").fill("30")
        page.get_by_role("button", name="Save restock").click()
        expect(page.get_by_role("status")).to_contain_text("Restock saved")
        shot(page, "05_flow1_restock_saved")
        page.goto(f"{base}/activity?machine_id=1")
        shot(page, "06_flow1_activity_log")

        # ---------- flow 2: shopping list -> delivery -> stock take
        page.goto(f"{base}/shopping-list")
        shot(page, "07_flow2_shopping_list_before")
        page.goto(f"{base}/central?supplier_id=3&low_only=1")
        shot(page, "08_flow2_central_low_water")
        page.get_by_label("New count for Water 500ml", exact=True).fill("250")
        page.get_by_label("New count for Water 500ml", exact=True).press("Enter")
        expect(page.get_by_role("status")).to_contain_text("Central storage count saved")
        page.goto(f"{base}/shopping-list")
        shot(page, "09_flow2_shopping_list_after")

        # ---------- flow 3: drawer allocation
        page.goto(f"{base}/allocation?machine=4")
        shot(page, "10_flow3_allocation_up04")

        # ---------- lists: sorting, filtering, paging, empty and error states
        page.goto(f"{base}/machines?sort=-alerts")
        shot(page, "11_machines_sorted_by_alerts")
        page.goto(f"{base}/central?sort=-value")
        shot(page, "12_central_sorted_by_value")
        page.goto(f"{base}/machines?search=Mars")
        shot(page, "13_empty_state_no_match", full_page=False)
        page.goto(f"{base}/machines?sort=password")
        shot(page, "14_error_state_bad_sort", full_page=False)
        page.goto(f"{base}/no-such-page")
        shot(page, "15_error_404", full_page=False)

        # ---------- flow 4: admin manages accounts
        admin = new_page()
        log_in(admin, ADMIN)
        admin.goto(f"{base}/admin/users")
        admin.get_by_label("Full name").fill("Thabo Helper")
        admin.get_by_label("Email").fill("thabo@adlers.test")
        admin.get_by_label("Password", exact=True).fill("helper-pass-1")
        admin.get_by_label("Confirm password").fill("helper-pass-1")
        admin.get_by_role("button", name="Add account").click()
        expect(admin.get_by_role("status")).to_contain_text("Account created for Thabo Helper")
        shot(admin, "16_flow4_admin_users")
        page.goto(f"{base}/admin/users")                       # Mr Msiza is not an admin
        shot(page, "17_flow4_user_gets_403", full_page=False)

        # ---------- phone size
        phone = new_page(390, 844)
        log_in(phone, USER)
        shot(phone, "18_phone_dashboard", full_page=False)
        phone.goto(f"{base}/machines/1")
        shot(phone, "19_phone_machine_detail", full_page=False)

        browser.close()

    print(f"\n{len(saved)} screenshots saved in {args.out}")


if __name__ == "__main__":
    sys.exit(main())
