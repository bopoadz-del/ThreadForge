"""B19: IFC4 schema+express validate, axis ±0.5 %, IfcRelConnectsPorts."""

from __future__ import annotations

import ifcopenshell

from threadforge.exporters.ifc import (
    axis_length_m,
    export_ifc4,
    route_length_m,
    unique_port_pairs,
    validate_ifc4,
)
from threadforge.spooling import crafted_straight_30m


def test_ifc4_validate_axis_ports(tmp_path):
    g = crafted_straight_30m()
    from threadforge.generators import write_pcf_text

    write_pcf_text(g, "LINE-CRAFT-30M")
    path = tmp_path / "craft.ifc"
    art = export_ifc4(g, path)
    assert path.is_file()
    v = validate_ifc4(path, express_rules=True)
    assert v["n_errors"] == 0, v["errors"]
    model = ifcopenshell.open(str(path))
    axis = axis_length_m(model)
    route = route_length_m(list(g.routes.values()))
    assert route > 0
    assert abs(axis - route) / route <= 0.005, f"axis={axis} route={route}"
    segs = model.by_type("IfcPipeSegment")
    pairs = unique_port_pairs(model)
    assert len(segs) >= 2
    assert len(pairs) == len(segs) - 1
    assert art.payload["port_links"] == len(pairs)
