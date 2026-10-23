"""Application factory: builds and configures the Flask app."""
import logging
import secrets

from flask import Flask, abort, render_template, request, session
from flask_login import LoginManager, current_user

from app.data import seed_data
from app.services import alert_service, user_service
from config import config_by_name

login_manager = LoginManager()


def create_app(config_name="development"):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY must be set in the environment for this configuration.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Fresh demo data every time an app is created (keeps tests independent).
    seed_data.reset()

    # ---- login handling (Flask-Login) ----
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return user_service.get_user(user_id)

    # ---- CSRF protection for every form (no JavaScript needed) ----
    # Each form carries a hidden token; a POST without the matching token is rejected.
    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_hex(16)
        return session["_csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_post_requests():
        if app.config["CSRF_ENABLED"] and request.method == "POST":
            sent = request.form.get("csrf_token", "").encode()
            expected = session.get("_csrf_token", "").encode()
            if not expected or not secrets.compare_digest(sent, expected):
                abort(400)

    # ---- template helpers ----
    @app.template_filter("rand")
    def rand(value, decimals=0):
        """Format a number as South African rand, e.g. R 4,820."""
        return f"R {value:,.{decimals}f}"

    @app.context_processor
    def inject_alert_count():
        """Number shown on the Alerts badge in the navigation bar."""
        if current_user.is_authenticated:
            return {"alert_count": len(alert_service.get_alerts())}
        return {"alert_count": 0}

    # ---- blueprints (one per feature area) ----
    from app.blueprints import allocation, auth, dashboard, inventory, procurement
    for module in (auth, dashboard, inventory, allocation, procurement):
        app.register_blueprint(module.bp)

    # ---- error pages ----
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("error.html", code=400,
                               message="That request could not be processed. The form may have "
                                       "expired, so please go back and try again."), 400

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("error.html", code=500,
                               message="Something went wrong on our side. Please try again."), 500

    return app
