"""Allocation recommendations: what belongs in the drawer (objective O3)."""
from flask import Blueprint, abort, render_template, request
from flask_login import login_required

from app.services import analytics_service, inventory_service

bp = Blueprint("allocation", __name__)


@bp.before_request
@login_required
def require_login():
    """Every page in this blueprint needs a logged-in user."""


# ---- allocation page (choose a machine with ?machine=ID) ----
@bp.route("/allocation")
def view():
    machines = inventory_service.get_machines()
    machine_id = request.args.get("machine", default=machines[0]["id"], type=int)
    machine = inventory_service.get_machine(machine_id)
    if machine is None:
        abort(404)
    return render_template("allocation.html", machines=machines, machine=machine,
                           plan=analytics_service.get_allocation(machine_id))
