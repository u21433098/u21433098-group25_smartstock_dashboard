"""Dashboard (KPIs overview) and the full alerts list."""
from flask import Blueprint, render_template, request
from flask_login import login_required

from app.blueprints._listing import run_listing
from app.services import alert_service, analytics_service, inventory_service

bp = Blueprint("dashboard", __name__)


@bp.before_request
@login_required
def require_login():
    """Every page in this blueprint needs a logged-in user."""


# ---- dashboard page: KPIs, top alerts, order preview, best sellers ----
@bp.route("/")
def index():
    alerts = alert_service.get_alerts()
    shopping = analytics_service.build_shopping_list()       # built once, used twice
    return render_template(
        "dashboard.html",
        kpis=analytics_service.get_kpis(alerts, shopping),
        alerts=alerts[:5], total_alerts=len(alerts),
        shopping=shopping,
        best_sellers=analytics_service.get_best_sellers(5),
        window=analytics_service.sales_window())


# ---- alerts page: filter by tier, severity and machine; paged ----
@bp.route("/alerts")
def all_alerts():
    a = request.args
    filters = {key: a.get(key) or None for key in ("tier", "severity", "machine_id")}
    result, _sort, error = run_listing(alert_service.list_alerts, per_page=20, **filters)
    return render_template("alerts.html", result=result, error=error,
                           filters={} if error else filters,
                           machines=inventory_service.get_machines())
