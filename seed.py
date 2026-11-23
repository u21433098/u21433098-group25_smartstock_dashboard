"""Load the synthetic demo data into the database in .env.

    python seed.py            asks first, because it wipes every row
    python seed.py --yes      no question (same as `flask seed --yes`)

The tables must exist first (`flask db upgrade`, or `flask setup --yes`, which does both).
The demo data itself is defined in app/data/seed_data.py.
"""
import sys

from app import create_app
from app.data import seed_data


def main():
    if "--yes" not in sys.argv:
        answer = input("This deletes ALL rows and loads the demo data. Continue? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return 1
    app = create_app()
    with app.app_context():
        seed_data.seed()
    print("Demo data loaded. Log in as msiza@adlers.test or admin@smartstock.test (password SmartStock123).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
