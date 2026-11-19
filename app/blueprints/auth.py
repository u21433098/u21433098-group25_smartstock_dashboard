"""Login, logout and "change my password" pages.

There is no public registration page: SmartStock is only used by Mr Msiza and the
people helping him, so an admin adds each account (see app/blueprints/admin.py).
"""
import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.services import user_service
from app.services.errors import ServiceError

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


def _is_safe_next(target):
    """Only follow redirects to pages inside this site (blocks open redirects)."""
    return bool(target) and target.startswith("/") and not target.startswith("//") and "\\" not in target


# ---- login page ----
@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = user_service.verify_credentials(email, request.form.get("password", ""))
        if user:
            login_user(user)
            log.info("Login: %s", user.email)
            target = request.args.get("next")
            return redirect(target if _is_safe_next(target) else url_for("dashboard.index"))
        log.warning("Failed login for %s", email)
        flash("Incorrect email or password.", "danger")
    return render_template("login.html", email=email)


# ---- change my own password (any logged-in user) ----
@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        new = request.form.get("new_password", "")
        if new != request.form.get("confirm", ""):
            flash("The two new passwords do not match.", "danger")
            return render_template("account_password.html"), 400
        try:
            user_service.change_own_password(current_user, request.form.get("current_password", ""), new)
        except ServiceError as error:
            flash(error.message, "danger")
            return render_template("account_password.html"), error.status
        log.info("Password changed: %s", current_user.email)
        flash("Your password has been changed.", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("account_password.html")


# ---- logout (POST only, so a stray link cannot log you out) ----
@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
