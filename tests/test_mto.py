"""B21: MTO per spool/line/IWP/WP; three-level totals ±0.1 %."""

from __future__ import annotations

from threadforge.generators import build_work_packages, write_pcf_text
from threadforge.ingest_dexpi import load_fixture
from threadforge.mto import RECONCILE_TOL, build_mto
from threadforge.routing import generate_routes_astar
from threadforge.spooling import crafted_straight_30m
from threadforge.supports_mss import support_types_kinematic


def test_crafted_mto_three_level_reconcile():
    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    g.routes["LINE-CRAFT-30M"]["supports_mss"] = support_types_kinematic(
        [(0.0, 0.0, 5.0), (30.0, 0.0, 5.0)], '6"', insulated=False
    )
    payload = build_mto(g)
    assert payload["ok"] is True
    assert payload["tol"] == 0.001
    rec = payload["reconcile"]
    assert rec["pipe_m"]["spool_vs_line"] <= RECONCILE_TOL
    assert rec["pipe_m"]["line_vs_iwp"] <= RECONCILE_TOL
    assert rec["pipe_m"]["line_vs_wp"] <= RECONCILE_TOL
    assert rec["pipe_kg"]["spool_vs_line"] <= RECONCILE_TOL
    assert abs(rec["pipe_m"]["spool"] - 30.0) < 1e-6
    kg = rec["pipe_kg"]["spool"]
    assert kg > 800.0  # 6" Sch40 ≈ 28.26 kg/m × 30 m
    keys = {"pipe_m", "pipe_kg", "fittings_count", "flanges", "bolts", "gaskets", "supports", "paint_m2", "insulation_m2"}
    assert keys.issubset(payload["per_spool"][0])
    assert keys.issubset(payload["per_line"][0])
    assert payload["per_iwp"]
    assert payload["per_wp"]
    assert len(payload["per_spool"]) == 3


def test_rich_mto_reconcile():
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    build_work_packages(g)
    for lid in g.pipelines:
        write_pcf_text(g, lid)
    payload = build_mto(g)
    assert payload["ok"] is True
    rec = payload["reconcile"]
    assert rec["pipe_m"]["spool_vs_line"] <= RECONCILE_TOL
    assert rec["pipe_m"]["line_vs_iwp"] <= RECONCILE_TOL
    assert rec["pipe_kg"]["line_vs_wp"] <= RECONCILE_TOL
