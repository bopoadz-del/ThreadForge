"""D5: IFC4 + DXF optional exporters."""

from __future__ import annotations

from pathlib import Path

import pytest

from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import generate_routes

pytest.importorskip("ifcopenshell")
pytest.importorskip("ezdxf")

from threadforge.exporters.dxf import export_ga_dxf, export_iso_dxf
from threadforge.exporters.ifc import export_ifc4, reopen_counts


def test_ifc4_reopen_counts(tmp_path):
    g = load_fixture("sample_pid_rich.xml")
    routes = generate_routes(g).payload["routes"]
    # Count PIPE-equivalent segments in routes
    pipe_segs = sum(max(0, len(r["points"]) - 1) for r in routes)
    route_len = sum(r["length_m"] for r in routes)
    art = export_ifc4(g, tmp_path / "model.ifc", routes=routes)
    assert art.status == "ready"
    counts = reopen_counts(Path(art.path))
    assert counts["IfcPipeSegment"] == art.payload["segment_count"]
    assert counts["IfcPipeSegment"] == pipe_segs
    assert abs(counts["total_length_m"] - route_len) / max(route_len, 1e-9) <= 0.005
    assert counts["IfcPipeFitting"] == art.payload["fitting_count"]


def test_dxf_ga_entity_count(tmp_path):
    g = load_fixture("sample_pid_rich.xml")
    art = export_ga_dxf(g, tmp_path / "ga.dxf")
    assert art.status == "ready"
    import ezdxf
    doc = ezdxf.readfile(art.path)
    assert len(list(doc.modelspace())) == art.payload["entity_count"]
    assert art.payload["entity_count"] >= 1


def test_dxf_iso(tmp_path):
    g = load_fixture("sample_pid_rich.xml")
    lid = next(iter(g.pipelines))
    art = export_iso_dxf(g, lid, tmp_path / "iso.dxf")
    assert art.status == "ready"
    import ezdxf
    doc = ezdxf.readfile(art.path)
    assert len(list(doc.modelspace())) >= 1
