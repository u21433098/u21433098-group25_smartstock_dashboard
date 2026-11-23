"""Production entry point, used by a production web server instead of `python app.py`.

Windows (or any OS), with Waitress:
    waitress-serve --listen=127.0.0.1:8000 wsgi:app
Linux server, with Gunicorn behind Nginx (see deploy/):
    gunicorn -c deploy/gunicorn.conf.py wsgi:app

Settings come from the environment / .env file (see .env.example). Production refuses
to start without SECRET_KEY and DATABASE_URL.
"""
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.logging_setup import setup_logging

setup_logging("production")
app = create_app("production")

if app.config.get("BEHIND_HTTPS_PROXY"):
    # Nginx passes the real visitor address and "https" in X-Forwarded-* headers.
    # Trust exactly one proxy, so visitors cannot fake these headers themselves.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
