"""B17: one iso sheet per spool — n/N, welds, cuts, BOM, dim_sum = spool length."""

from __future__ import annotations

from threadforge.generators import generate_isometric, write_pcf_text
from threadforge.iso_sheets import dim_sum_mm_from_svg, sheet_iso_svg, spool_bom
from threadforge.spooling import crafted_straight_30m


def test_iso_sheet_dim_sum_equals_spool_length():
    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    art = generate_isometric(g, "LINE-CRAFT-30M")
    sheets = art.payload["sheets"]
    assert art.payload["sheet_count"] == 3
    assert len(sheets) == 3
    for i, sh in enumerate(sheets, start=1):
        assert sh["sheet"] == i
        assert sh["n_of"] == 3
        assert sh["spool_id"] == f"S-CRAFT-30M-{i:02d}"
        assert sh["cut_lengths_m"]
        assert sh["bom"]
        assert any(b.get("type") == "PIPE" for b in sh["bom"])
        want = int(round(float(sh["length_m"]) * 1000))
        assert sh["dim_sum_mm"] == want
        svg = sheet_iso_svg(
            {
                "spool_id": sh["spool_id"],
                "length_m": sh["length_m"],
                "axis_points": g.routes["LINE-CRAFT-30M"]["spools"]["spools"][i - 1]["axis_points"],
                "cut_lengths_m": sh["cut_lengths_m"],
                "fittings": [],
            },
            line_number="CRAFT-30M",
            sheet_n=i,
            sheet_n_of=3,
            welds=[w for w in g.routes["LINE-CRAFT-30M"]["spools"]["welds"] if w["spool_id"] == sh["spool_id"]],
            bom=spool_bom(g.routes["LINE-CRAFT-30M"]["spools"]["spools"][i - 1]),
        )
        assert f"sheet {i}/3" in svg
        assert sh["spool_id"] in svg
        assert "NOT FOR CONSTRUCTION" in svg
        assert "cut_lengths_mm=" in svg
        assert "BOM sheet" in svg
        assert dim_sum_mm_from_svg(svg) == want
        if i < 3:
            assert f"W-CRAFT-30M-{i}" in svg
            assert "weld-field" in svg or "W-CRAFT-30M" in svg
