"""Login, register and logout pages."""
import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.services import user_service

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


# ---- register page ----
@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        form["name"] = request.form.get("name", "")
        form["email"] = request.form.get("email", "")
        password = request.form.get("password", "")
        if password != request.form.get("confirm", ""):
            flash("The two passwords do not match.", "danger")
        else:
            try:
                user_service.create_user(form["name"], form["email"], password)
            except ValueError as error:
                flash(str(error), "danger")
            else:
                flash("Account created. Please log in.", "success")
                return redirect(url_for("auth.login"))
    return render_template("register.html", form=form)


# ---- logout (POST only, so a stray link cannot log you out) ----
@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
