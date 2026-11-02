"""Database setup for SmartStock: SQLAlchemy, Flask-Migrate and the `flask` database commands.

The app factory only needs one call:   init_db(app)
Models and services import `db` from here.
"""
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
