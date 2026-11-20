"""Database setup for SmartStock: SQLAlchemy, Flask-Migrate and the `flask` database commands.

The app factory only needs one call:   init_db(app)
Models and services import `db` from here.
"""
import os

import click
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, event
from sqlalchemy.engine import Engine

# Predictable names for keys, indexes and checks, so migrations can find and
# drop them again (MySQL would otherwise invent names that differ per server).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()


def init_db(app):
    """Attach the database to the app and register the `flask seed` / `flask create-admin` commands.

    With AUTO_CREATE_DB (the testing configuration), a brand-new database is built and
    seeded every time an app is created, so each test starts from the same demo data.
    """
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL must be set in the environment for this configuration.")
    db.init_app(app)
    migrate.init_app(app, db)
    from app import models  # noqa: F401  (registers the tables with SQLAlchemy)
    _register_cli(app)

    if app.config.get("AUTO_CREATE_DB"):
        from app.data import seed_data
        with app.app_context():
            db.drop_all()
            # Also forget any migration stamp left by an earlier run, so the new
            # database really starts un-migrated (create_all does not stamp it).
            db.session.execute(db.text("DROP TABLE IF EXISTS alembic_version"))
            db.session.commit()
            db.create_all()
            seed_data.seed()


@event.listens_for(Engine, "connect")
def _sqlite_enforce_foreign_keys(dbapi_connection, _record):
    """SQLite (used only by the fast tests) ignores foreign keys unless told otherwise.
    Turning them on makes the tests catch the same mistakes MySQL would."""
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _register_cli(app):
    """Extra `flask ...` commands for setting up the database."""

    @app.cli.command("seed")
    @click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
    def seed_command(yes):
        """Wipe all rows and load the synthetic demo data."""
        from app.data import seed_data
        if not yes:
            click.confirm("This deletes ALL rows in the database and loads demo data. Continue?",
                          abort=True)
        seed_data.seed()
        click.echo("Demo data loaded.")

    @app.cli.command("health")
    def health_command():
        """Check the database: reachable, migrations up to date, demo data present.

        Prints one line per check and exits with code 1 if any check fails, so a
        scheduled task or monitoring tool can alert on it.
        """
        problems = 0
        for label, ok, detail in health_checks():
            click.echo(f"[{'OK' if ok else 'FAIL'}] {label}: {detail}")
            problems += not ok
        if problems:
            raise SystemExit(1)

    @app.cli.command("backup")
    @click.option("--keep-days", default=30, show_default=True, help="Delete backups older than this.")
    def backup_command(keep_days):
        """Save a compressed copy of the database in backups/ and delete old backups."""
        from app import backup
        try:
            path, removed = backup.backup(app.config["SQLALCHEMY_DATABASE_URI"], _backup_folder(app),
                                          os.environ.get("MYSQL_BIN"), keep_days)
        except backup.BackupError as error:
            raise click.ClickException(str(error))
        size_kb = max(1, round(os.path.getsize(path) / 1024))
        click.echo(f"Backup saved: {path} ({size_kb} KB). "
                   f"Deleted {removed} backup(s) older than {keep_days} days.")

    @app.cli.command("restore")
    @click.argument("backup_file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
    def restore_command(backup_file, yes):
        """Replace ALL data in the database with a backup file (.sql.gz or .sql)."""
        from app import backup
        if not yes:
            click.confirm(f"This REPLACES ALL DATA in the database with {backup_file}. "
                          "Stop SmartStock first. Continue?", abort=True)
        try:
            backup.restore(app.config["SQLALCHEMY_DATABASE_URI"], backup_file, os.environ.get("MYSQL_BIN"))
        except backup.BackupError as error:
            raise click.ClickException(str(error))
        click.echo(f"Restored from {backup_file}. Run `flask health` to check, then start SmartStock.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin_command(name, email, password):
        """Create an admin account (for the developer)."""
        from app.services import user_service
        try:
            user_service.create_user(name, email, password, role="admin")
        except ValueError as error:
            raise click.ClickException(str(error))
        click.echo(f"Admin account created for {email}.")


def _backup_folder(app):
    """backups/ in the project folder (or BACKUP_DIR from the environment)."""
    return os.environ.get("BACKUP_DIR") or os.path.join(os.path.dirname(app.root_path), "backups")


def health_checks():
    """Run the health checks. Returns [(label, ok, detail), ...]."""
    from alembic.script import ScriptDirectory
    from flask import current_app
    from sqlalchemy import text

    results = []
    try:
        db.session.execute(text("SELECT 1"))
        results.append(("Database connection", True, db.engine.url.render_as_string(hide_password=True)))
    except Exception as error:  # any connection problem is a failed check, not a crash
        return [("Database connection", False, str(error).splitlines()[0])]

    try:
        current = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        db.session.rollback()
        current = None
    migrations = current_app.extensions["migrate"].directory
    head = ScriptDirectory.from_config(migrate.get_config(migrations)).get_current_head()
    results.append(("Migrations", current == head,
                    f"database at {current or 'none'}, latest is {head}"
                    + ("" if current == head else " (run: flask db upgrade)")))

    if current:
        from app.models import Machine, User
        machines = db.session.scalar(db.select(db.func.count()).select_from(Machine))
        admins = db.session.scalar(db.select(db.func.count()).select_from(User)
                                   .where(User.role == "admin", User.is_active.is_(True)))
        results.append(("Data", machines > 0, f"{machines} machines"
                        + ("" if machines else " (run: flask seed --yes)")))
        results.append(("Admin account", admins > 0, f"{admins} active admin(s)"
                        + ("" if admins else " (run: flask create-admin)")))
    return results
