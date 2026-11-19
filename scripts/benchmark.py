"""Scalability benchmark: how fast are SmartStock's pages as the fleet grows?

For each fleet size it builds a fresh database (the 12 demo machines, then copies of
them with their stock and 30 days of sales until there are N machines), logs in, and
times the main pages and API calls inside the app (network time not included).

WARNING: it WIPES the database it is given. Point it at a throwaway test database,
never at the real one.

    python scripts/benchmark.py --database-url mysql+pymysql://smartstock:PASSWORD@localhost:3306/smartstock_test

Options: --sizes 12,50,100,200   --repeats 15   --out docs/impact/benchmark.json
Without --database-url it uses an in-memory SQLite database.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGES = [  # (label, method, url, body)
    ("Dashboard page", "GET", "/", None),
    ("Machines page", "GET", "/machines", None),
    ("Machine detail page", "GET", "/machines/1", None),
    ("Alerts page", "GET", "/alerts", None),
    ("Allocation page", "GET", "/allocation?machine=1", None),
    ("Shopping list page", "GET", "/shopping-list", None),
    ("Activity page", "GET", "/activity", None),
    ("API: list machines", "GET", "/api/v1/machines?per_page=20", None),
    ("API: dashboard", "GET", "/api/v1/dashboard", None),
    ("API: stock take (write)", "PUT", "/api/v1/central/2", {"qty": 50}),
]


def grow_fleet(db, models, target):
    """Add copies of the 12 demo machines (stock and sales included) until there are `target`."""
    Machine, MachineStock, DrawerStock, Sale = models
    base = db.session.scalars(db.select(Machine).order_by(Machine.machine_id)).all()
    for new_id in range(len(base) + 1, target + 1):
        src = base[(new_id - 1) % len(base)]
        db.session.add(Machine(machine_id=new_id, code=f"UP-{new_id:03d}",
                               location=f"{src.location} (copy {(new_id - 1) // len(base)})",
                               drawer_capacity=src.drawer_capacity))
        db.session.flush()
        for model, cols in ((MachineStock, ("product_id", "qty", "capacity", "threshold")),
                            (DrawerStock, ("product_id", "qty", "capacity", "threshold")),
                            (Sale, ("product_id", "sale_date", "qty"))):
            columns = [getattr(model, c) for c in cols]
            select = db.select(db.literal(new_id), *columns).where(model.machine_id == src.machine_id)
            db.session.execute(db.insert(model).from_select(["machine_id", *cols], select))
    db.session.commit()


def time_requests(app, repeats):
    client = app.test_client()
    client.post("/login", data={"email": "msiza@adlers.test", "password": "SmartStock123"})
    results = {}
    for label, method, url, body in PAGES:
        timings = []
        for i in range(repeats + 2):                       # the first 2 runs warm up caches
            start = time.perf_counter()
            response = client.open(url, method=method, json=body)
            elapsed = (time.perf_counter() - start) * 1000
            assert response.status_code == 200, f"{label}: HTTP {response.status_code}"
            if i >= 2:
                timings.append(elapsed)
        timings.sort()
        results[label] = {"median_ms": round(statistics.median(timings), 1),
                          "p95_ms": round(timings[max(0, int(len(timings) * 0.95) - 1)], 1)}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", help="throwaway database to use (it is wiped)")
    parser.add_argument("--sizes", default="12,50,100,200")
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--out", default=os.path.join("docs", "impact", "benchmark.json"))
    args = parser.parse_args()
    if args.database_url:
        os.environ["TEST_DATABASE_URL"] = args.database_url      # read by config.TestingConfig

    from app import create_app
    from app.extensions import db
    from app.models import DrawerStock, Machine, MachineStock, Sale

    import logging
    logging.disable(logging.INFO)                                 # keep the output readable
    sizes = [int(s) for s in args.sizes.split(",")]
    runs = []
    for size in sizes:
        app = create_app("testing")                               # wipes and seeds the 12 demo machines
        app.config["CSRF_ENABLED"] = False
        with app.app_context():
            grow_fleet(db, (Machine, MachineStock, DrawerStock, Sale), size)
            rows = {name: db.session.scalar(db.select(db.func.count()).select_from(model))
                    for name, model in (("machines", Machine), ("machine_stock", MachineStock),
                                        ("sales", Sale))}
            db.session.remove()
        print(f"\n{size} machines ({rows['sales']:,} sales rows)")
        timings = time_requests(app, args.repeats)
        for label, t in timings.items():
            print(f"  {label:<26} median {t['median_ms']:>7.1f} ms   p95 {t['p95_ms']:>7.1f} ms")
        runs.append({"machines": size, "rows": rows, "timings": timings})
        with app.app_context():
            db.engine.dispose()

    with create_app("testing").app_context():
        engine = db.engine
        server = engine.dialect.name
        if server == "mysql":
            server = "MySQL/MariaDB " + db.session.scalar(db.text("SELECT VERSION()"))
    result = {
        "measured_on": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "cpus": os.cpu_count(), "database": server},
        "method": f"In-process Flask test client, {args.repeats} timed runs after 2 warm-up runs per request; "
                  "server time only (no network).",
        "runs": runs,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
