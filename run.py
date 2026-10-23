"""Entry point.  Start the app with:  python run.py"""
import os

from app import create_app

# APP_CONFIG can be "development" (default), "testing" or "production".
app = create_app(os.environ.get("APP_CONFIG", "development"))

if __name__ == "__main__":
    app.run()
