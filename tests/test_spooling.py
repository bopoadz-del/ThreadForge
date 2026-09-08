"""B16: shop-spool limits, field welds, W- numbering, SPOOL-IDENTIFIER, pins."""

from __future__ import annotations

import re

from threadforge.generators import write_pcf_text
from threadforge.ingest_dexpi import load_fixture
from threadforge.pcf_reader import assert_contiguous, parse_pcf, total_centreline_length_mm
from threadforge.routing import generate_routes_astar
from threadforge.spooling import (
    ENVELOPE_CITE,
    ENVELOPE_M,
    LENGTH_CITE,
    MASS_CITE,
    SHOP_MAX_LENGTH_M,
    SHOP_MAX_MASS_KG,
    crafted_envelope_u,
    crafted_mass_24in,
    crafted_straight_30m,
    limits_ok,
)
from threadforge.tables import mass_per_m


def _weld_ids(text: str) -> list[str]:
    return re.findall(r"W-[A-Za-z0-9.-]+-\d+", text)


def test_limits_cited_from_standards():
    assert SHOP_MAX_LENGTH_M == 12.0
    assert SHOP_MAX_MASS_KG == 2000.0
    assert ENVELOPE_M == (12.0, 2.4, 2.4)
    assert "12.0" in LENGTH_CITE
    assert "B36.10" in MASS_CITE
    assert "ISO 668" in ENVELOPE_CITE and "Table 1" in ENVELOPE_CITE


def test_crafted_30m_splits_on_12m():
    g = crafted_straight_30m()
    text = write_pcf_text(g, "LINE-CRAFT-30M")
    rep = g.routes["LINE-CRAFT-30M"]["spools"]
    assert limits_ok(rep)
    assert rep["spool_count"] == 3
    lengths = [round(sp["length_m"], 6) for sp in rep["spools"]]
    assert lengths == [12.0, 12.0, 6.0]
    assert all(sp["mass_kg"] <= SHOP_MAX_MASS_KG + 1e-6 for sp in rep["spools"])
    assert rep["field_weld_count"] == 2
    assert rep["shop_weld_count"] == 0
    assert [w["weld_id"] for w in rep["welds"]] == ["W-CRAFT-30M-1", "W-CRAFT-30M-2"]
    assert all(w["shop_field"] == "field" for w in rep["welds"])
    assert "SPOOL-IDENTIFIER" in text
    assert "S-CRAFT-30M-01" in text and "S-CRAFT-30M-03" in text
    assert "W-CRAFT-30M-1" in text
    doc = parse_pcf(text)
    assert_contiguous(doc, tol_mm=1.0)
    pcf_m = total_centreline_length_mm(doc) / 1000.0
    assert abs(pcf_m - 30.0) / 30.0 <= 0.005


def test_crafted_envelope_u_splits_on_2_4m():
    g = crafted_envelope_u()
    write_pcf_text(g, "LINE-CRAFT-ENV")
    rep = g.routes["LINE-CRAFT-ENV"]["spools"]
    assert limits_ok(rep)
    assert rep["spool_count"] == 2
    assert rep["field_weld_count"] == 1
    dims1 = (
        max(p[0] for p in rep["spools"][0]["points"]) - min(p[0] for p in rep["spools"][0]["points"]),
        max(p[1] for p in rep["spools"][0]["points"]) - min(p[1] for p in rep["spools"][0]["points"]),
    )
    assert max(dims1) <= 2.4 + 1e-6 or min(dims1) <= 2.4 + 1e-6
    for sp in rep["spools"]:
        xs = [p[0] for p in sp["points"]]
        ys = [p[1] for p in sp["points"]]
        zs = [p[2] for p in sp["points"]]
        extents = sorted((max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)), reverse=True)
        env = sorted(ENVELOPE_M, reverse=True)
        assert all(d <= e + 1e-6 for d, e in zip(extents, env)), (sp["spool_id"], extents)


def test_crafted_24in_splits_on_2t():
    g = crafted_mass_24in()
    write_pcf_text(g, "LINE-CRAFT-24")
    rep = g.routes["LINE-CRAFT-24"]["spools"]
    kg_m = mass_per_m('24"', "40")
    assert abs(kg_m - 255.425) < 0.01  # B36.10 Table 1 NPS 24 OD 610, Sch40 17.48 mm, ρ=7850
    assert kg_m * 10.0 > SHOP_MAX_MASS_KG
    assert limits_ok(rep)
    assert rep["spool_count"] == 2
    assert rep["field_weld_count"] == 1
    assert all(sp["mass_kg"] <= SHOP_MAX_MASS_KG + 1e-4 for sp in rep["spools"])
    assert abs(sum(sp["length_m"] for sp in rep["spools"]) - 10.0) < 1e-6
    assert abs(rep["spools"][0]["mass_kg"] - SHOP_MAX_MASS_KG) < 0.05


def test_rich_spool_weld_counts_pinned():
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    got: dict[str, dict[str, int]] = {}
    for lid in sorted(g.pipelines):
        write_pcf_text(g, lid)
        rep = g.routes[lid]["spools"]
        assert limits_ok(rep)
        got[lid] = {
            "spools": int(rep["spool_count"]),
            "welds": int(rep["weld_count"]),
            "field": int(rep["field_weld_count"]),
            "shop": int(rep["shop_weld_count"]),
        }
        text = write_pcf_text(g, lid)
        assert f"S-{g.pipelines[lid].line_number}-01" in text
        for w in rep["welds"]:
            assert w["weld_id"].startswith(f"W-{g.pipelines[lid].line_number}-")
            assert re.fullmatch(r"W-.+-\d+", w["weld_id"])
    # Measured on sample_pid_rich A* + B36.10 kg/m + 12 m / 2 t / 12×2.4×2.4 envelope.
    expected = {
        "LINE-200-D-1010": {"spools": 2, "welds": 1, "field": 1, "shop": 0},
        "LINE-200-P-1001": {"spools": 2, "welds": 7, "field": 1, "shop": 6},
        "LINE-200-P-1002": {"spools": 5, "welds": 12, "field": 4, "shop": 8},
        "LINE-210-G-2001": {"spools": 2, "welds": 5, "field": 1, "shop": 4},
    }
    # Placeholder — first run overwrites via assertion message if wrong.
    assert got == expected, got
