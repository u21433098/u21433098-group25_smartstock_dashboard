"""Operations tests: logging, the health check, production settings and the WSGI entry point.

The backup/restore scripts in deploy/ call mysqldump and mysql directly, so they are
checked by hand against MySQL (see "Backups" in README.md), not here.
"""
import importlib
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

import pytest
from flask_migrate import stamp

import config
from app import config_by_name, create_app
from app.extensions import db, health_checks
from app.logging_setup import _MARKER, setup_logging

# The settings classes the app really uses. (Patch these, not config.X: the HTTPS test
# reloads the config module, which makes new classes the app never sees.)
DEV, PROD = config_by_name["development"], config_by_name["production"]


@pytest.fixture
def app():
    app = create_app("testing")      # fresh database built with create_all (no migration stamp)
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def clean_logging():
    """Remove the handlers setup_logging() adds, so one test's log files never leak into another."""
    yield
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARKER, False)]:
        root.removeHandler(handler)
        handler.close()


# ------------------------------------------------------------------ logging
def test_logs_go_to_daily_files_kept_14_days(tmp_path, monkeypatch, clean_logging):
    monkeypatch.setattr(DEV, "LOG_DIR", str(tmp_path / "logs"))
    setup_logging("development")
    files = [h for h in logging.getLogger().handlers if isinstance(h, TimedRotatingFileHandler)]
    assert {h.baseFilename.split("/")[-1].split("\\")[-1] for h in files} == {"smartstock.log", "errors.log"}
    assert all(h.when == "MIDNIGHT" and h.backupCount == 14 for h in files)

    logging.getLogger("test").warning("something went wrong")
    logging.getLogger("test").info("normal event")
    for h in files:
        h.flush()
    assert "normal event" in (tmp_path / "logs" / "smartstock.log").read_text()
    errors = (tmp_path / "logs" / "errors.log").read_text()
    assert "something went wrong" in errors and "normal event" not in errors


def test_setting_up_logging_twice_does_not_double_the_lines(tmp_path, monkeypatch, clean_logging):
    monkeypatch.setattr(DEV, "LOG_DIR", str(tmp_path))
    setup_logging("development")
    setup_logging("development")
    ours = [h for h in logging.getLogger().handlers if getattr(h, _MARKER, False)]
    assert len(ours) == 3          # console + smartstock.log + errors.log


# ------------------------------------------------------------------ health check
def test_health_check_flags_a_database_that_was_not_migrated(app):
    checks = {label: ok for label, ok, _detail in health_checks()}
    assert checks["Database connection"] is True
    assert checks["Migrations"] is False


def test_health_check_passes_on_a_migrated_seeded_database(app):
    stamp()                         # record that the database is at the latest migration
    results = health_checks()
    assert all(ok for _label, ok, _detail in results), results
    assert {label for label, _ok, _detail in results} == {
        "Database connection", "Migrations", "Data", "Admin account"}


def test_flask_health_command_exit_code(app):
    runner = app.test_cli_runner()
    failing = runner.invoke(args=["health"])
    assert failing.exit_code == 1 and "[FAIL] Migrations" in failing.output
    stamp()
    passing = runner.invoke(args=["health"])
    assert passing.exit_code == 0 and "[FAIL]" not in passing.output


# ------------------------------------------------------------------ production settings
def test_production_refuses_to_start_without_secrets(monkeypatch):
    monkeypatch.setattr(PROD, "SECRET_KEY", None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")
    monkeypatch.setattr(PROD, "SECRET_KEY", "a-real-key")
    monkeypatch.setattr(PROD, "SQLALCHEMY_DATABASE_URI", None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app("production")


def test_https_flag_makes_cookies_secure(monkeypatch):
    monkeypatch.setenv("BEHIND_HTTPS_PROXY", "1")
    secure = importlib.reload(config).ProductionConfig
    assert secure.SESSION_COOKIE_SECURE and secure.REMEMBER_COOKIE_SECURE
    assert secure.PREFERRED_URL_SCHEME == "https"
    monkeypatch.delenv("BEHIND_HTTPS_PROXY")
    plain = importlib.reload(config).ProductionConfig
    assert not plain.SESSION_COOKIE_SECURE
    assert plain.SESSION_COOKIE_HTTPONLY and plain.SESSION_COOKIE_SAMESITE == "Lax"
    importlib.reload(config)


def test_wsgi_entry_point_trusts_the_proxy_only_when_told_to(tmp_path, monkeypatch, clean_logging):
    from werkzeug.middleware.proxy_fix import ProxyFix
    monkeypatch.setattr(PROD, "SECRET_KEY", "a-real-key")
    monkeypatch.setattr(PROD, "SQLALCHEMY_DATABASE_URI", "sqlite://")
    monkeypatch.setattr(PROD, "LOG_DIR", str(tmp_path))

    for behind_proxy in (True, False):
        monkeypatch.setattr(PROD, "BEHIND_HTTPS_PROXY", behind_proxy)
        sys.modules.pop("wsgi", None)
        wsgi = importlib.import_module("wsgi")
        assert wsgi.app.config["DEBUG"] is False
        assert isinstance(wsgi.app.wsgi_app, ProxyFix) is behind_proxy
    sys.modules.pop("wsgi", None)


# ------------------------------------------------------------------ backups (flask backup / flask restore)
from app import backup as backup_module          # noqa: E402


def test_old_backups_are_deleted_and_nothing_else(tmp_path):
    old, new = tmp_path / "smartstock_2020-01-01_000000.sql.gz", tmp_path / "smartstock_2026-11-19_020000.sql.gz"
    unfinished, other = tmp_path / "smartstock_2020-01-01_000000.sql.gz.part", tmp_path / "notes.sql.gz"
    for path in (old, new, unfinished, other):
        path.write_bytes(b"x")
    forty_days_ago = backup_module.time.time() - 40 * 86400
    for path in (old, unfinished, other):
        os.utime(path, (forty_days_ago, forty_days_ago))
    assert backup_module.prune(str(tmp_path), keep_days=30) == 1
    assert not old.exists() and new.exists() and unfinished.exists() and other.exists()


def test_the_password_goes_in_a_temporary_file_that_is_removed(tmp_path):
    login = backup_module._Login('mysql+pymysql://smartstock:pa%22ss%5Cword@db.example:3307/smartstock')
    with login as option:
        path = option.split("=", 1)[1]
        settings = open(path, encoding="utf-8").read()
    assert option.startswith("--defaults-extra-file=")
    assert 'password="pa\\"ss\\\\word"' in settings and "port=3307" in settings
    assert not os.path.exists(path)


def test_backups_need_mysql_and_say_what_is_wrong(app, tmp_path, monkeypatch):
    with pytest.raises(backup_module.BackupError, match="MySQL database"):
        backup_module._Login("sqlite://")
    with pytest.raises(backup_module.BackupError, match="MYSQL_BIN"):
        backup_module.find_tool("mysqldump", mysql_bin=str(tmp_path))
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
        result = app.test_cli_runner().invoke(args=["backup"])
        assert result.exit_code == 1 and "MySQL database" in result.output


def _mysql_tools_available(app):
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql"):
        return False
    try:
        backup_module.find_tool("mysqldump", os.environ.get("MYSQL_BIN"))
        backup_module.find_tool("mysql", os.environ.get("MYSQL_BIN"))
        return True
    except backup_module.BackupError:
        return False


def test_backup_and_restore_round_trip_on_mysql(app, tmp_path, monkeypatch):
    """Runs when the tests use MySQL (TEST_DATABASE_URL) and mysqldump is installed."""
    if not _mysql_tools_available(app):
        pytest.skip("needs TEST_DATABASE_URL pointing at MySQL, and mysqldump/mysql installed")
    from app.models import CentralStock
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    runner = app.test_cli_runner()

    saved = runner.invoke(args=["backup"])
    assert saved.exit_code == 0, saved.output
    files = list(tmp_path.glob("smartstock_*.sql.gz"))
    assert len(files) == 1 and files[0].stat().st_size > 1000

    db.session.get(CentralStock, 13).qty = 999                    # damage the data
    db.session.commit()
    refused = runner.invoke(args=["restore", str(files[0])], input="n\n")
    assert refused.exit_code == 1 and "Aborted" in refused.output
    restored = runner.invoke(args=["restore", str(files[0]), "--yes"])
    assert restored.exit_code == 0, restored.output
    db.session.rollback()
    assert db.session.get(CentralStock, 13).qty == 10              # back to the backed-up value
