"""Dashboard (KPIs overview) and the full alerts list."""
from flask import Blueprint, render_template
from flask_login import login_required

from app.services import alert_service, analytics_service

bp = Blueprint("dashboard", __name__)


@bp.before_request
@login_required
def require_login():
    """Every page in this blueprint needs a logged-in user."""


# ---- dashboard page ----
@bp.route("/")
def index():
    alerts = alert_service.get_alerts()
    shopping = analytics_service.build_shopping_list()
    return render_template(
        "dashboard.html",
        kpis=analytics_service.get_kpis(alerts, shopping),
        alerts=alerts[:5], total_alerts=len(alerts),
        shopping=shopping,
        best_sellers=analytics_service.get_best_sellers(5))


# ---- alerts page ----
@bp.route("/alerts")
def all_alerts():
    return render_template("alerts.html", alerts=alert_service.get_alerts())
