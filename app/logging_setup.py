"""Logging for SmartStock: to the console and to daily log files kept for 14 days.

Call setup_logging() BEFORE create_app() (run.py and wsgi.py do this). Once the root
logger has handlers, the logging.basicConfig() call inside create_app() does nothing,
so these settings win.

Files (in LOG_DIR, default ./logs):
    smartstock.log     everything at INFO and above (logins, stock changes, requests)
    errors.log         WARNING and above only (failed logins, crashes)
Each file is rolled over at midnight; LOG_RETENTION_DAYS old files are kept and older
ones are deleted automatically.
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from config import config_by_name

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MARKER = "_smartstock_handler"   # lets setup_logging() run twice without doubling handlers


def _file_handler(path, level, keep_days):
    handler = TimedRotatingFileHandler(path, when="midnight", backupCount=keep_days, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(FORMAT))
    setattr(handler, _MARKER, True)
    return handler


def setup_logging(config_name="development"):
    """Send logs to the console and to rotating files. Returns the log folder path."""
    config = config_by_name[config_name]
    log_dir = os.path.abspath(config.LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARKER, False)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    setattr(console, _MARKER, True)
    root.addHandler(console)
    root.addHandler(_file_handler(os.path.join(log_dir, "smartstock.log"), logging.INFO,
                                  config.LOG_RETENTION_DAYS))
    root.addHandler(_file_handler(os.path.join(log_dir, "errors.log"), logging.WARNING,
                                  config.LOG_RETENTION_DAYS))
    logging.getLogger(__name__).info("Logging to %s (kept %s days)", log_dir, config.LOG_RETENTION_DAYS)
    return log_dir
