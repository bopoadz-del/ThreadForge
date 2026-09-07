"""D9: true isometric SVG — dimension sum equals route length."""

from __future__ import annotations

import re

from threadforge.generators import _iso_svg, generate_isometric
from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import route_pipeline


def test_iso_dim_sum_equals_route_length():
    g = load_fixture()
    pipe = g.pipelines["LINE-120-P-1001"]
    route = route_pipeline(g, pipe)
    svg = _iso_svg(route, pipe.line_number, bom=[{"tag": "FLG", "type": "FLANGE"}])
    assert "HEURISTIC — NOT FOR CONSTRUCTION" in svg
    assert "north" in svg.lower() or ">N<" in svg or ">N</text>" in svg
    m = re.search(r"dim_sum_mm=(\d+)", svg)
    assert m
    assert int(m.group(1)) == int(round(route["length_m"] * 1000))


def test_iso_package_writes_true_iso(tmp_path):
    g = load_fixture()
    art = generate_isometric(g, "LINE-120-P-1001", output_dir=tmp_path)
    svg = (tmp_path / "iso" / "120-P-1001.iso.svg").read_text(encoding="utf-8")
    assert "HEURISTIC" in svg
    assert art.status == "ready"
