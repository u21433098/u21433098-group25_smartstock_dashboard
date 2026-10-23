"""Configuration for the DEV / TEST / PROD environments.

Secrets come from environment variables (see .env.example), never from the code.
"""
import os

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

    # ---- supply chain settings used by app/services/analytics_service.py ----
    SERVICE_Z = 1.645              # 95% service level
    REVIEW_DAYS = 7                # Mr Msiza's weekly supplier run
    BUFFER_DAYS = 3                # days of sales we want sitting in a drawer
    DRAWER_TOTAL_CAPACITY = 50     # units one machine's drawer can hold in total

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


class ProductionConfig(Config):
    # No fallback: production must provide a real key through the environment.
    SECRET_KEY = os.environ.get("SECRET_KEY")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
