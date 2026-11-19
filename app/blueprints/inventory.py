"""Machines, the three-tier stock view, the activity log, and the forms that change stock."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import query_args
from app.blueprints._listing import run_listing
from app.services import inventory_service

bp = Blueprint("inventory", __name__)


@bp.before_request
@login_required
def require_login():
    """Every page in this blueprint needs a logged-in user."""


def _to_int(value):
    """Turn form text into a whole number, or None if it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---- machine list page: search by code or location, sort, page ----
@bp.route("/machines")
def machines():
    search = request.args.get("search", "").strip()
    result, sort, error = run_listing(inventory_service.list_machines, per_page=10,
                                      default_sort="code", search=search or None)
    return render_template("machines.html", result=result, sort=sort, error=error,
                           search="" if error else search)


# ---- machine detail page: machine + drawer + central side by side ----
@bp.route("/machines/<int:machine_id>")
def machine_detail(machine_id):
    machine = inventory_service.get_machine(machine_id)
    if machine is None:
        abort(404)
    return render_template(
        "machine_detail.html", machine=machine,
        rows=inventory_service.get_machine_rows(machine_id),
        movements=inventory_service.get_recent_movements(machine_id))


# ---- activity page: the full audit trail of stock changes, filtered and paged ----
@bp.route("/activity")
def activity():
    a = request.args
    filters = {key: a.get(key) or None
               for key in ("machine_id", "product_id", "tier", "date_from", "date_to")}
    result, _sort, error = run_listing(inventory_service.list_movements, per_page=20, **filters)
    return render_template("activity.html", result=result, error=error,
                           filters={} if error else filters,
                           machines=inventory_service.get_machines(),
                           products=sorted(inventory_service.get_central_rows(), key=lambda r: r["name"]))


# ---- form: record a physical count of a machine ----
@bp.route("/machines/<int:machine_id>/count", methods=["POST"])
def set_count(machine_id):
    if inventory_service.get_machine(machine_id) is None:
        abort(404)
    product_id, qty = _to_int(request.form.get("product_id")), _to_int(request.form.get("qty"))
    if product_id is None or qty is None:
        flash("Please choose a product and enter a whole number.", "danger")
    else:
        try:
            inventory_service.set_machine_count(machine_id, product_id, qty, current_user.name)
            flash("Machine count saved.", "success")
        except ValueError as error:
            flash(str(error), "danger")
    return redirect(url_for("inventory.machine_detail", machine_id=machine_id))


# ---- form: log a restock visit ----
@bp.route("/machines/<int:machine_id>/restock", methods=["POST"])
def restock(machine_id):
    if inventory_service.get_machine(machine_id) is None:
        abort(404)
    product_id, units = _to_int(request.form.get("product_id")), _to_int(request.form.get("units"))
    if product_id is None or units is None:
        flash("Please choose a product and enter a whole number.", "danger")
    else:
        try:
            split = inventory_service.restock_visit(machine_id, product_id, units, current_user.name)
            flash(f"Restock saved: {split['to_machine']} into the machine, "
                  f"{split['to_drawer']} into the drawer, "
                  f"{split['to_central']} returned to central storage.", "success")
        except ValueError as error:
            flash(str(error), "danger")
    return redirect(url_for("inventory.machine_detail", machine_id=machine_id))


# ---- central storage page: search, supplier filter, "low stock only", sort, page ----
@bp.route("/central")
def central():
    a = request.args
    filters = {"search": a.get("search", "").strip() or None,
               "supplier_id": a.get("supplier_id") or None,
               "low_only": a.get("low_only") == "1"}
    result, sort, error = run_listing(inventory_service.list_central, per_page=10,
                                      default_sort="name", **filters)
    all_rows = inventory_service.get_central_rows()
    suppliers = sorted({(r["supplier_id"], r["supplier"]) for r in all_rows}, key=lambda s: s[1])
    return render_template("central_storage.html", result=result, sort=sort, error=error,
                           filters={} if error else filters, suppliers=suppliers)


# ---- form: stock take of one central storage product ----
@bp.route("/central/<int:product_id>", methods=["POST"])
def set_central(product_id):
    qty = _to_int(request.form.get("qty"))
    if qty is None:
        flash("Please enter a whole number.", "danger")
    else:
        try:
            inventory_service.set_central_count(product_id, qty, current_user.name)
            flash("Central storage count saved.", "success")
        except ValueError as error:
            flash(str(error), "danger")
    # Go back to the same filtered, sorted page the stock take was made on.
    return redirect(url_for("inventory.central", **query_args()))
