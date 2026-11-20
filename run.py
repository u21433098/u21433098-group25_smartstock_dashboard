"""Development entry point.  Start the app with:  python run.py

For production use wsgi.py with a real server (see "Deployment" in README.md).
"""
import os

from app import create_app
from app.logging_setup import setup_logging

# APP_CONFIG can be "development" (default), "testing" or "production".
config_name = os.environ.get("APP_CONFIG", "development")
if config_name != "testing":
    setup_logging(config_name)          # console + logs/smartstock.log, kept 14 days
app = create_app(config_name)

if __name__ == "__main__":
    app.run()
