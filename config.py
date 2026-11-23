"""Configuration for the DEV / TEST / PROD environments.

Secrets come from environment variables (see .env.example), never from the code.
"""
import os


def _env_flag(name):
    """True when an environment variable is set to 1 / true / yes."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")

# Optional: if python-dotenv is installed, read a local .env file automatically.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """Settings shared by every environment."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True            # form protection; switched off only in tests

    # ---- database (MySQL through the PyMySQL driver) ----
    # Format: mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE
    # No default on purpose: the login (including the password) only ever comes from .env,
    # never from the code. Without DATABASE_URL the app stops with a clear message.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}  # reconnect if MySQL dropped an idle link

    # ---- supply chain settings used by app/services/analytics_service.py ----
    SERVICE_Z = 1.645              # 95% service level
    REVIEW_DAYS = 7                # Mr Msiza's weekly supplier run
    BUFFER_DAYS = 3                # days of sales we want sitting in a drawer
    SALES_WINDOW_DAYS = 30         # trailing window for turnover and demand (objective O3)

    # ---- logging (see app/logging_setup.py) ----
    LOG_DIR = os.environ.get("LOG_DIR", "logs")
    LOG_RETENTION_DAYS = 14        # daily log files are kept for 14 days

    # ---- login cookie safety ----
    SESSION_COOKIE_HTTPONLY = True     # page scripts cannot read the login cookie
    SESSION_COOKIE_SAMESITE = "Lax"    # other sites cannot send forms with it
    REMEMBER_COOKIE_HTTPONLY = True

    # ---- baseline used for the impact estimate (from the proposal) ----
    BASELINE_TRIPS_PER_WEEK = 2
    MINUTES_PER_TRIP = 60
    TRIP_REDUCTION_TARGET = 0.25   # objective O4: 25% fewer supplier trips


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    CSRF_ENABLED = False
    SECRET_KEY = "test-secret"
    # Tests run on a throwaway in-memory SQLite database by default, so they need no
    # MySQL server. Set TEST_DATABASE_URL to a separate MySQL database to run them
    # against MySQL instead. Never point it at the real database: tests wipe it.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AUTO_CREATE_DB = True          # build + seed a fresh database each time an app is created


class ProductionConfig(Config):
    # No fallbacks: production must provide a real key and database through the environment.
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    # Behind Nginx with HTTPS (the Linux server set-up in deploy/), set BEHIND_HTTPS_PROXY=1:
    # cookies are then only sent over HTTPS, and wsgi.py trusts the proxy's headers.
    # Leave it off when trying production mode on your own PC over plain http.
    BEHIND_HTTPS_PROXY = _env_flag("BEHIND_HTTPS_PROXY")
    SESSION_COOKIE_SECURE = BEHIND_HTTPS_PROXY
    REMEMBER_COOKIE_SECURE = BEHIND_HTTPS_PROXY
    PREFERRED_URL_SCHEME = "https" if BEHIND_HTTPS_PROXY else "http"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def current_config_name():
    """The settings to use, from APP_CONFIG in .env: development (default), testing or production."""
    name = os.environ.get("APP_CONFIG", "development")
    if name not in config_by_name:
        raise RuntimeError(f"APP_CONFIG must be one of: {', '.join(config_by_name)} (it is '{name}').")
    return name
