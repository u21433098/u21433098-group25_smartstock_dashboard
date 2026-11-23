"""SmartStock main application file.  Start the app with:  python app.py

Development only (Flask's built-in server, with debug pages). For production use wsgi.py
with a real server (see "Deployment" in README.md).

The `flask` command (flask seed, flask health, flask backup, ...) builds the same app
through the factory: FLASK_APP=app:create_app in .env.
"""
from app import create_app            # the app/ package (create_app reads APP_CONFIG from .env)
from app.logging_setup import setup_logging
from config import current_config_name

config_name = current_config_name()   # "development" (default), "testing" or "production"
if config_name != "testing":
    setup_logging(config_name)        # console + logs/smartstock.log, kept 14 days
app = create_app(config_name)

if __name__ == "__main__":
    app.run()
