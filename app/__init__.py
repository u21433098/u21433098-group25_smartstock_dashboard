"""Application factory: builds and configures the Flask app."""
import logging
import os
import secrets

from flask import Flask, abort, jsonify, render_template, request, session, url_for
from flask_login import LoginManager, current_user

from app.extensions import db, init_db
from app.services import alert_service, user_service
from config import config_by_name, current_config_name

login_manager = LoginManager()

# The pages and the stylesheet live at the top of the project (templates/ and static/),
# as in the course's recommended structure, next to app.py.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config_name=None):
    """Build the app. Without a config name it uses APP_CONFIG from .env (default: development),
    which is how the `flask` command calls it (FLASK_APP=app:create_app)."""
    config_name = config_name or current_config_name()
    app = Flask(__name__,
                template_folder=os.path.join(PROJECT_ROOT, "templates"),
                static_folder=os.path.join(PROJECT_ROOT, "static"))
    app.config.from_object(config_by_name[config_name])
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY must be set in the environment for this configuration.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Database (MySQL): tables, migrations and the `flask seed` / `flask create-admin` commands.
    # In the testing configuration this also builds a fresh, seeded test database.
    init_db(app)

    # ---- login handling (Flask-Login) ----
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return user_service.get_user(user_id)

    # ---- CSRF protection for every change (no JavaScript needed) ----
    # Web forms carry the token in a hidden field; API clients send it in the
    # X-CSRF-Token header. A change without the matching token is rejected.
    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(16)
        return session["_csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_changes():
        if not app.config["CSRF_ENABLED"] or request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        if _is_api():
            sent = request.headers.get("X-CSRF-Token", "")
        else:
            sent = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(sent.encode(), expected.encode()):
            if _is_api():
                return _json_error(400, "Missing or wrong CSRF token. Get one from GET /api/v1/auth/csrf "
                                        "and send it in the X-CSRF-Token header.")
            abort(400)
        return None

    # ---- template helpers ----
    @app.template_filter("rand")
    def rand(value, decimals=0):
        """Format a number as South African rand, e.g. R 4,820."""
        return f"R {value:,.{decimals}f}"

    app.jinja_env.globals["query_args"] = query_args

    @app.template_global()
    def url_with(**changes):
        """This page's address with some query values changed, e.g. url_with(page=2).

        Keeps the other filters, so sorting or paging never loses the search.
        A value of None removes that parameter.
        """
        args = query_args()
        args.update(changes)
        args = {k: v for k, v in args.items() if v not in (None, "")}
        return url_for(request.endpoint, **(request.view_args or {}), **args)

    @app.context_processor
    def inject_alert_count():
        """Number shown on the Alerts badge in the navigation bar."""
        if current_user.is_authenticated:
            return {"alert_count": len(alert_service.get_alerts())}
        return {"alert_count": 0}

    # ---- blueprints (one per feature area) ----
    from app.blueprints import admin, allocation, api, auth, dashboard, inventory, procurement
    for module in (auth, dashboard, inventory, allocation, procurement, admin, api):
        app.register_blueprint(module.bp)

    # ---- error pages (HTML), or JSON errors for /api/... addresses ----
    @app.errorhandler(400)
    def bad_request(_error):
        if _is_api():
            return _json_error(400, "The request could not be understood.")
        return render_template("error.html", code=400,
                               message="That request could not be processed. The form may have "
                                       "expired, so please go back and try again."), 400

    @app.errorhandler(403)
    def forbidden(_error):
        if _is_api():
            return _json_error(403, "You do not have permission to do that.")
        return render_template("error.html", code=403,
                               message="Only an admin can open that page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        if _is_api():
            return _json_error(404, "There is no such API address. See /api/v1/openapi.json.")
        return render_template("404.html"), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        if _is_api():
            return _json_error(405, f"{request.method} is not allowed on this address.")
        return render_template("error.html", code=405,
                               message="That page cannot be used that way."), 405

    @app.errorhandler(500)
    def server_error(error):
        # Undo any half-finished database change, and record what went wrong (with the
        # stack trace) in logs/errors.log. The visitor only sees a short, friendly message.
        db.session.rollback()
        app.logger.error("Server error on %s %s: %s", request.method, request.path,
                         getattr(error, "original_exception", error), exc_info=True)
        if _is_api():
            return _json_error(500, "Something went wrong on our side. Please try again.")
        return render_template("error.html", code=500,
                               message="Something went wrong on our side. Please try again."), 500

    return app


def query_args():
    """The address's query values (?search=...&page=2), safe to pass on to url_for().

    Names starting with "_" are dropped: url_for() treats _external, _anchor, _scheme and
    _method as instructions, so passing them on would let a crafted link change where
    the page's own links and redirects point.
    """
    return {k: v for k, v in request.args.to_dict().items() if not k.startswith("_")}


def _is_api():
    """True for requests to the JSON API (they get JSON errors, not HTML pages)."""
    return request.path.startswith("/api/")


def _json_error(status, message):
    return jsonify({"error": {"status": status, "message": message}}), status
