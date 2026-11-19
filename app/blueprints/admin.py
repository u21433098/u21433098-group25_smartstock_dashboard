"""Admin pages: manage the accounts of Mr Msiza and his helpers.

Only admins can open anything here. The check happens twice: admin_only() below
returns 403 for everyone else, and every user_service function checks the role
again itself, so a forgotten check here can never let a normal user in.

There is no public registration: an admin adds each account on this page.
"""
import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.services import user_service
from app.services.errors import ServiceError, ValidationError

bp = Blueprint("admin", __name__, url_prefix="/admin")
log = logging.getLogger(__name__)


@bp.before_request
@login_required
def admin_only():
    if not user_service.can(current_user, "manage_users"):
        log.warning("Non-admin %s tried to open %s", current_user.email, request.path)
        abort(403)


def _back():
    """Return to the users page, keeping the page number the admin was on."""
    return redirect(url_for("admin.users", page=request.args.get("page") or None))


# ---- list of accounts + "add an account" form ----
@bp.route("/users")
def users():
    try:
        result = user_service.list_users(current_user, page=request.args.get("page"), per_page="20")
    except ValidationError as error:
        flash(error.message, "danger")
        result = user_service.list_users(current_user)
    return render_template("admin_users.html", result=result, form=request.args)


@bp.route("/users", methods=["POST"])
def add_user():
    form = request.form
    if form.get("password", "") != form.get("confirm", ""):
        flash("The two passwords do not match.", "danger")
        return render_template("admin_users.html", result=user_service.list_users(current_user),
                               form=form), 400
    try:
        user = user_service.admin_create_user(current_user, form.get("name", ""), form.get("email", ""),
                                              form.get("password", ""), form.get("role", "user"))
    except ServiceError as error:
        flash(error.message, "danger")
        return render_template("admin_users.html", result=user_service.list_users(current_user),
                               form=form), error.status
    log.info("%s added account %s (%s)", current_user.email, user["email"], user["role"])
    flash(f"Account created for {user['name']}. Give them their email and password to log in.", "success")
    return redirect(url_for("admin.users"))


# ---- switch an account on or off ----
@bp.route("/users/<int:user_id>/active", methods=["POST"])
def set_active(user_id):
    active = request.form.get("active") == "1"
    try:
        user = user_service.set_active(current_user, user_id, active)
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        log.info("%s switched %s %s", current_user.email, user["email"], "on" if active else "off")
        flash(f"{user['name']} can {'now' if active else 'no longer'} log in.", "success")
    return _back()


# ---- change an account's role ----
@bp.route("/users/<int:user_id>/role", methods=["POST"])
def set_role(user_id):
    try:
        user = user_service.set_role(current_user, user_id, request.form.get("role", ""))
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        log.info("%s made %s an %s", current_user.email, user["email"], user["role"])
        flash(f"{user['name']} is now {'an admin' if user['role'] == 'admin' else 'a user'}.", "success")
    return _back()


# ---- set a new password for someone who forgot theirs ----
@bp.route("/users/<int:user_id>/password", methods=["POST"])
def reset_password(user_id):
    try:
        user_service.reset_password(current_user, user_id, request.form.get("new_password", ""))
    except ServiceError as error:
        flash(error.message, "danger")
    else:
        log.info("%s reset the password of user %s", current_user.email, user_id)
        flash("Password changed. Give the new password to the account holder.", "success")
    return _back()
