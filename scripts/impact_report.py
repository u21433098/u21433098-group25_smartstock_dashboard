"""Compute the impact numbers and draw the charts for the impact report (SmartStock_Impact_Report.docx).

Every "with SmartStock" number comes from the app itself, run on the synthetic demo
data (an in-memory database, so nothing real is touched). Baseline numbers come from
the proposal. Assumptions are listed in ASSUMPTIONS and printed in the report.

    pip install matplotlib            (only needed for this script)
    python scripts/benchmark.py ...   (first, for the scalability chart; see that file)
    python scripts/impact_report.py

Writes docs/impact/metrics.json and docs/impact/*.png.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib                                    # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle   # noqa: E402

OUT = os.path.join("docs", "impact")
WEEKS_PER_MONTH = 52 / 12

ASSUMPTIONS = {
    "baseline_trips_per_week": 2,          # proposal, section 2
    "minutes_per_trip": 60,                # proposal, section 2
    "o4_target_reduction": 0.25,           # proposal, objective O4
    "km_per_trip": 15,                     # ASSUMED round trip café -> supplier -> café (not measured)
    "litres_per_100km": 8.0,               # ASSUMED small delivery car / bakkie (not measured)
    "kg_co2e_per_litre_petrol": 2.345,     # UK Government GHG conversion factors 2023 (BEIS/Defra)
}

# ---- chart style (validated reference palette; see the dataviz notes in the report) ----
SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
BASELINE_GRAY = MUTED


# ------------------------------------------------------------------ numbers from the app
def compute_metrics():
    os.environ.pop("TEST_DATABASE_URL", None)        # always the in-memory demo database
    from app import create_app
    from app.extensions import db
    from app.models import CentralStock, DrawerStock, Machine, StockMovement
    from app.services import alert_service, analytics_service

    app = create_app("testing")                      # fresh, seeded demo data
    with app.test_request_context():
        alerts = alert_service.get_alerts()
        shopping = analytics_service.build_shopping_list()
        by_tier = {t: sum(1 for a in alerts if a["tier"] == t) for t in ("Machine", "Drawer", "Central")}

        drawers = {(d.machine_id, d.product_id): d.qty for d in db.session.scalars(db.select(DrawerStock))}
        central = {c.product_id: c.qty for c in db.session.scalars(db.select(CentralStock))}
        machine_alerts = [a for a in alerts if a["tier"] == "Machine"]
        fix_from_drawer = sum(1 for a in machine_alerts if drawers.get((a["machine_id"], a["product_id"]), 0) > 0)
        fix_from_central = sum(1 for a in machine_alerts if central.get(a["product_id"], 0) > 0)

        machines = db.session.scalar(db.select(db.func.count()).select_from(Machine))
        drawer_rows = len(drawers)
        allocations = sum(1 for m in range(1, machines + 1) if analytics_service.get_allocation(m)["rows"])
        movements = db.session.scalar(db.select(db.func.count()).select_from(StockMovement))

    trips_before, trips_after = shopping["n_products"], shopping["n_suppliers"]
    reduction = shopping["trips_saved"] / trips_before if trips_before else 0.0
    a = ASSUMPTIONS
    hours_before = a["baseline_trips_per_week"] * a["minutes_per_trip"] / 60 * WEEKS_PER_MONTH
    trips_saved_month = a["baseline_trips_per_week"] * WEEKS_PER_MONTH * reduction
    litres = trips_saved_month * a["km_per_trip"] * a["litres_per_100km"] / 100

    return {
        "machines": machines,
        "tiers_tracked": {"before": 1, "after": 3},
        "paper_records_digitised": {"drawer_slots": drawer_rows, "central_products": len(central),
                                    "total": drawer_rows + len(central)},
        "views_for_one_machine": {"before": 3, "after": 1},
        "alerts_by_tier": by_tier,
        "alerts_visible": {"before": by_tier["Machine"], "after": sum(by_tier.values())},
        "machine_shortages": {"total": len(machine_alerts), "fixable_from_drawer": fix_from_drawer,
                              "fixable_from_central": fix_from_central},
        "order_cycle": {"products_to_order": trips_before, "suppliers": trips_after,
                        "trips_before": trips_before, "trips_after": trips_after,
                        "trips_saved": shopping["trips_saved"], "reduction": round(reduction, 3)},
        "driving_hours_per_month": {"before": round(hours_before, 1),
                                    "o4_target": round(hours_before * (1 - a["o4_target_reduction"]), 1),
                                    "demo_order": round(hours_before * (1 - reduction), 1),
                                    "saved_demo_order": round(hours_before * reduction, 1)},
        "fuel_and_co2_per_month": {"trips_saved": round(trips_saved_month, 1),
                                   "km_saved": round(trips_saved_month * a["km_per_trip"], 0),
                                   "litres_saved": round(litres, 1),
                                   "kg_co2e_saved": round(litres * a["kg_co2e_per_litre_petrol"], 1)},
        "allocation_rankings": {"machines_with_ranking": allocations, "of": machines},
        "audit_trail_rows_on_fresh_demo": movements,
        "assumptions": ASSUMPTIONS,
    }


# ------------------------------------------------------------------ chart helpers
def style(ax, title=None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK_2, labelsize=10, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)          # solid hairline grid
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, loc="left", fontsize=11, color=INK, pad=16)


def rounded_bar(ax, x, height, width, color, radius_px=4):
    """A bar with 4px rounded data-end and a square base (anchored to the baseline)."""
    if height <= 0:
        return
    fig = ax.figure
    fig.canvas.draw()
    bbox = ax.get_window_extent()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    px_per_x = bbox.width / (x1 - x0)
    px_per_y = bbox.height / (y1 - y0)
    r_x = radius_px / px_per_x
    r_y = radius_px / px_per_y
    r_y = min(r_y, height / 2)
    patch = FancyBboxPatch((x - width / 2, 0), width, height,
                           boxstyle=f"round,pad=0,rounding_size={r_x}",
                           mutation_aspect=r_y / r_x, facecolor=color, edgecolor="none", zorder=3)
    ax.add_patch(patch)
    ax.add_patch(Rectangle((x - width / 2, 0), width, height - r_y, facecolor=color, edgecolor="none", zorder=3))


def new_figure(width, height):
    fig = plt.figure(figsize=(width, height), dpi=150, facecolor=SURFACE)
    plt.rcParams["font.family"] = "DejaVu Sans"
    return fig


def legend_patches(ax, items):
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=c, label=l) for l, c in items], frameon=False, fontsize=10,
              loc="upper left", bbox_to_anchor=(0, -0.12), ncol=len(items), labelcolor=INK_2)


# ------------------------------------------------------------------ chart 1: before / after, small multiples
def chart_before_after(m):
    panels = [  # (title, which way is better, before, after)
        ("Supplier trips\nper order", "fewer is better", m["order_cycle"]["trips_before"], m["order_cycle"]["trips_after"]),
        ("Low-stock alerts\nyou can see", "more is better", m["alerts_visible"]["before"], m["alerts_visible"]["after"]),
        ("Stock tiers\ntracked digitally", "more is better", m["tiers_tracked"]["before"], m["tiers_tracked"]["after"]),
        ("Screens to see\none machine", "fewer is better", m["views_for_one_machine"]["before"], m["views_for_one_machine"]["after"]),
    ]
    fig = new_figure(10, 4.0)
    axes = fig.subplots(1, len(panels))
    for ax, (title, better, before, after) in zip(axes, panels):
        top = max(before, after) * 1.25
        ax.set_xlim(-0.6, 1.6)
        ax.set_ylim(0, top)
        style(ax, title)
        ax.text(0, 1.0, better, transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")
        for x, value, color in ((0, before, BASELINE_GRAY), (1, after, BLUE)):
            rounded_bar(ax, x, value, 0.62, color)
            ax.text(x, value + top * 0.03, f"{value:g}", ha="center", va="bottom", fontsize=11, color=INK)
        ax.set_xticks([0, 1], ["Before", "SmartStock"])
        ax.set_yticks([])
    legend_patches(axes[0], [("Before (paper + Moma)", BASELINE_GRAY), ("With SmartStock (demo data)", BLUE)])
    fig.tight_layout(w_pad=3)
    fig.subplots_adjust(bottom=0.22, top=0.78)
    path = os.path.join(OUT, "before_after.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ------------------------------------------------------------------ chart 2: driving hours a month
def chart_driving_hours(m):
    h = m["driving_hours_per_month"]
    fig = new_figure(6.4, 3.6)
    ax = fig.subplots()
    top = h["before"] * 1.25
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylim(0, top)
    style(ax, "Supplier driving, hours per month")
    for x, value, color in ((0, h["before"], BASELINE_GRAY), (1, h["demo_order"], BLUE)):
        rounded_bar(ax, x, value, 0.55, color)
        ax.text(x, value + top * 0.03, f"{value:.1f} h", ha="center", va="bottom", fontsize=11, color=INK)
    ax.axhline(h["o4_target"], color=INK_2, linewidth=1, zorder=4)
    ax.text(1.55, h["o4_target"] + top * 0.02, f"O4 target: {h['o4_target']:.1f} h (25% fewer trips)",
            ha="right", va="bottom", fontsize=9, color=INK_2)
    ax.set_xticks([0, 1], ["Before\n(proposal baseline)", f"SmartStock\n({m['order_cycle']['reduction']:.0%} fewer trips)"])
    ax.set_ylabel("hours", color=INK_2, fontsize=10)
    fig.tight_layout()
    path = os.path.join(OUT, "driving_hours.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ------------------------------------------------------------------ chart 3: alerts by tier
def chart_alerts_by_tier(m):
    tiers = m["alerts_by_tier"]
    fig = new_figure(6.4, 3.4)
    ax = fig.subplots()
    names = list(tiers)
    top = max(tiers.values()) * 1.3
    ax.set_xlim(-0.6, len(names) - 0.4)
    ax.set_ylim(0, top)
    style(ax, "Low-stock alerts on the demo data, by tier")
    for x, name in enumerate(names):
        color = BASELINE_GRAY if name == "Machine" else BLUE
        rounded_bar(ax, x, tiers[name], 0.55, color)
        ax.text(x, tiers[name] + top * 0.03, str(tiers[name]), ha="center", va="bottom", fontsize=11, color=INK)
    ax.set_xticks(range(len(names)), ["Machine", "Drawer buffer", "Central storage"])
    ax.set_yticks([])
    legend_patches(ax, [("Already visible in Moma", BASELINE_GRAY), ("Only visible in SmartStock", BLUE)])
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.27)
    path = os.path.join(OUT, "alerts_by_tier.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ------------------------------------------------------------------ chart 4: scalability
def chart_scalability(bench):
    series = [("Dashboard page", BLUE), ("Shopping list page", ORANGE), ("Machines page", AQUA),
              ("Machine detail page", YELLOW)]
    sizes = [run["machines"] for run in bench["runs"]]
    fig = new_figure(8, 4.2)
    ax = fig.subplots()
    style(ax, "Server time per page as the fleet grows (median of 15 runs, MySQL)")
    top = max(run["timings"][s]["median_ms"] for run in bench["runs"] for s, _ in series) * 1.15
    for label, color in series:
        values = [run["timings"][label]["median_ms"] for run in bench["runs"]]
        ax.plot(sizes, values, color=color, linewidth=2, marker="o", markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label, zorder=3)
        ax.text(sizes[-1] + 6, values[-1], f"{label.replace(' page', '')}  {values[-1]:.0f} ms",
                va="center", fontsize=9, color=INK_2)
    ax.set_xlim(0, sizes[-1] * 1.33)
    ax.set_ylim(0, top)
    ax.set_xticks(sizes)
    ax.set_xlabel("vending machines in the database", color=INK_2, fontsize=10)
    ax.set_ylabel("milliseconds", color=INK_2, fontsize=10)
    ax.legend(frameon=False, fontsize=9, loc="upper left", labelcolor=INK_2)
    fig.tight_layout()
    path = os.path.join(OUT, "scalability.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    metrics = compute_metrics()
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics, indent=2))
    for path in (chart_before_after(metrics), chart_driving_hours(metrics), chart_alerts_by_tier(metrics)):
        print("saved", path)
    bench_path = os.path.join(OUT, "benchmark.json")
    if os.path.exists(bench_path):
        with open(bench_path, encoding="utf-8") as f:
            print("saved", chart_scalability(json.load(f)))
    else:
        print("No docs/impact/benchmark.json yet: run scripts/benchmark.py for the scalability chart.")


if __name__ == "__main__":
    main()
