"""PCF / ISO / GA / routes exporters write real artefacts."""

from pathlib import Path

from threadforge.generators import (
    export_all_piping_artefacts,
    generate_ga,
    generate_isometric,
    generate_pcf,
    generate_quantities,
    write_ga_svg,
    write_pcf_text,
)
from threadforge.routing import generate_routes, manhattan_route, route_pipeline


def test_manhattan_route_orthogonal():
    pts = manhattan_route((0, 0, 0), (10, 5, 2), prefer_order="xyz")
    assert pts[0] == (0, 0, 0)
    assert pts[-1] == (10, 5, 2)
    # Each step changes only one axis
    for a, b in zip(pts, pts[1:]):
        diffs = sum(1 for i in range(3) if abs(a[i] - b[i]) > 1e-9)
        assert diffs == 1


def test_route_pipeline_has_length(graph):
    pipe = next(iter(graph.pipelines.values()))
    route = route_pipeline(graph, pipe)
    assert route["length_m"] >= 0
    assert len(route["points"]) >= 2
    assert "limits" in route
    assert route.get("geometry_source") in {"nozzle_xyz", "fabricated"}


def test_pcf_text_contains_keywords(graph, tmp_path):
    lid = next(iter(graph.pipelines))
    text = write_pcf_text(graph, lid)
    assert "PIPELINE-REFERENCE" in text
    assert "END-POINT" in text
    assert "PIPE" in text
    assert "ISOGEN-FILES" not in text
    from threadforge.pcf_reader import assert_contiguous, parse_pcf
    assert_contiguous(parse_pcf(text))
    art = generate_pcf(graph, lid, output_dir=tmp_path)
    assert art.status == "ready"
    path = Path(art.path)
    assert path.is_file()
    assert path.suffix == ".pcf"
    body = path.read_text(encoding="utf-8")
    assert body.splitlines()[0].startswith("===") or "PIPELINE-REFERENCE" in body


def test_isometric_json_and_svg(graph, tmp_path):
    lid = next(iter(graph.pipelines))
    art = generate_isometric(graph, lid, output_dir=tmp_path)
    assert art.status == "ready"
    files = art.payload.get("files") or {}
    assert Path(files["json"]).exists()
    svg = Path(files["svg"])
    assert svg.exists()
    content = svg.read_text(encoding="utf-8")
    assert content.lstrip().startswith("<svg")
    assert "HEURISTIC" in content or "ISO" in content
    assert content.count("<circle") >= 1 or "path" in content


def test_ga_svg_volumes(graph, tmp_path):
    svg = write_ga_svg(graph)
    assert svg.lstrip().startswith("<svg")
    assert "VOL-A" in svg
    art = generate_ga(graph, output_dir=tmp_path)
    assert art.status == "ready"
    assert Path(art.path).exists()


def test_quantities_have_heuristic_length(graph):
    art = generate_quantities(graph)
    assert art.status == "ready"
    for row in art.payload["rows"]:
        assert row["length_m"] is not None
        assert row["geometry_source"] in {"nozzle_xyz", "fabricated"}


def test_export_all_writes_tree(graph, tmp_path):
    result = export_all_piping_artefacts(graph, tmp_path)
    assert (tmp_path / "pcf").is_dir()
    assert (tmp_path / "iso").is_dir()
    assert (tmp_path / "ga" / "plot_plan.svg").exists()
    assert (tmp_path / "routes" / "routes.json").exists()
    assert len(result["artefacts"]) >= 5


def test_routes_artefact_ready(graph):
    art = generate_routes(graph)
    assert art.status == "ready"
    assert art.payload["total_length_m"] >= 0
    assert len(art.payload["routes"]) == len(graph.pipelines)
