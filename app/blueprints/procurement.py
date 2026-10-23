"""Consolidated supplier shopping list (objective O4)."""
from flask import Blueprint, render_template
from flask_login import login_required

from app.services import analytics_service

bp = Blueprint("procurement", __name__)


@bp.before_request
@login_required
def require_login():
    """Every page in this blueprint needs a logged-in user."""


# ---- shopping list page ----
@bp.route("/shopping-list")
def shopping_list():
    return render_template("shopping_list.html", shopping=analytics_service.build_shopping_list())
