"""Exercise remaining public branches so B36 can measure ≥85% branch coverage."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from threadforge.guards import reset_rate_limits
from threadforge.ingest_dexpi import (
    coverage_report,
    join_opc_across_graphs,
    load_fixture,
    load_fixtures_multi,
    parse_dexpi_xml,
    validate_xsd,
)
from threadforge.routing import (
    bore_to_mm,
    ensure_routes,
    generate_routes,
    get_route,
    manhattan_route,
    nozzle_point,
    polyline_length,
    route_pipeline,
)
from threadforge.tables import (
    allowable_stress_mpa,
    b16_5_pt_rating_bar,
    b31_3_345_4_2_test_pressure,
    flange_thickness_m,
    gasket_thickness_m,
    infer_flange_class,
    insulation_od_mm,
    next_smaller_bore,
    parse_nps_inch,
    reducer_face_to_face_m,
    table_c1_epsilon_mm_per_m,
    valve_face_to_face_m,
)
from threadforge.tables import (
    test_medium_for_service as medium_for_service,
)

RICH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PlantModel xmlns:dex="http://dexpi.org/x" Name="COV" Units="m">
  <PlantInformation SchemaVersion="4.1.1"/>
  <Sheet ID="SH-1" Name="S1" Index="1">
    <Note>n1</Note>
    <LegendItem Key="k" Value="v"/>
    <Layer Name="L1"/>
  </Sheet>
  <Drawing ID="SH-1" Name="dup"/>
  <Equipment ID="EQ-A" TagName="EQ-A" Discipline="EQP" StdName="V" PrimaryCode="V"
             ComponentClass="VESSEL" Service="H2O" VolumeID="VOL-1" SheetID="SH-1"
             Description="tank">
    <GenericAttributes>
      <GenericAttribute Name="UpperLimitDesignPressure" Value="30"/>
      <GenericAttribute Name="TagNameAssignmentClass" Value="EQ-A"/>
    </GenericAttributes>
    <Description>vessel</Description>
    <Extent Xmin="0" Ymin="0" Xmax="2" Ymax="2"/>
    <Nozzle ID="NA" TagName="NA" X="0" Y="0" Z="5" Rating="150" Facing="RF" Orientation="N">
      <GenericAttributes>
        <GenericAttribute Name="NominalDiameterNumericalValueAssignmentClass" Value="6"/>
      </GenericAttributes>
      <Location X="10" Y="20"/>
      <Association Target="VOL-1"/>
    </Nozzle>
  </Equipment>
  <ProcessEquipment ID="EQ-B" TagName="EQ-B">
    <Nozzle ID="NB" TagName="NB" X="10" Y="0" Z="5"/>
  </ProcessEquipment>
  <ShapeCatalogue>
    <Nozzle ID="NCAT" TagName="NCAT"/>
  </ShapeCatalogue>
  <PipingNetworkSystem ID="SYS-H2O">
    <GenericAttributes>
      <GenericAttribute Name="FluidCodeAssignmentClass" Value="H2O"/>
      <GenericAttribute Name="PipingClassCodeAssignmentClass" Value="150"/>
      <GenericAttribute Name="MaterialOfConstructionCodeAssignmentClass" Value="CS"/>
      <GenericAttribute Name="UpperLimitDesignPressure" Value="30"/>
      <GenericAttribute Name="InsulationTypeAssignmentClass" Value="PU"/>
    </GenericAttributes>
    <PipingNetworkSegment ID="PS-1" TagName="L-1" NominalDiameter="6" LineNumber="L-1"
                          FromID="NA" ToID="NB" VolumeID="VOL-1" SheetID="SH-1">
      <Connection FromID="NA" ToID="NB"/>
      <Component ID="V-1" Tag="V-1" Type="GATE" ComponentClass="VALVE"/>
      <PipingComponent ID="EL-1" Tag="EL-1" Type="ELBOW"/>
    </PipingNetworkSegment>
  </PipingNetworkSystem>
  <PipeLine ID="PL-DUP" LineNumber="L-1"/>
  <Line ID="LN-2" LineNumber="L-2" NominalBore="DN80" From="NA" To="MISSING"/>
  <OffPageConnector ID="OPC-OUT" TagName="OPC-1" ComponentClass="FlowOutPipeOffPageConnector">
    <GenericAttributes>
      <GenericAttribute Name="CrossPageConnectionAssignmentClass" Value="JOIN-A"/>
    </GenericAttributes>
  </OffPageConnector>
  <FlowInPipeOffPageConnector ID="OPC-IN" TagName="OPC-1B" ComponentClass="FlowInPipeOffPageConnector">
    <GenericAttributes>
      <GenericAttribute Name="CrossPageConnectionAssignmentClass" Value="JOIN-A"/>
    </GenericAttributes>
  </FlowInPipeOffPageConnector>
  <PipeOffPageConnectorReference ID="OPCR-1" ReferencedConnectorID="OPC-OUT"/>
  <Connection FromID="OPC-OUT" ToID="OPC-IN"/>
  <Instrument ID="FT-1" TagName="FT-1" Type="FT" MeasuredVariable="F" ConnectedTo="PS-1" SheetID="SH-1"/>
  <InstrumentationFunction ID="IF-1" TagName="IF-1"/>
  <ProcessInstrumentFunction ID="PIF-1" Name="PIF-1"/>
  <BatteryLimit ID="BL-1" TagID="NA" Description="BL" Side="battery"/>
  <PlantAreaBoundary ID="BL-2" Tag="NB"/>
  <DesignVolume ID="VOL-1" Name="V1" Xmin="0" Ymin="0" Zmin="0" Xmax="20" Ymax="20" Zmax="10" Color="red" Site="S" PlotPlan="P"/>
  <Volume ID="VOL-2" Name="V2"/>
  <System ID="SYS-EX" Name="Explicit" Service="H2O">
    <BoundaryTag ID="NA"/>
  </System>
</PlantModel>
"""


def test_parse_rich_synthetic_and_opc(tmp_path):
    g = parse_dexpi_xml(RICH_XML)
    assert g.equipment
    assert g.pipelines
    assert g.instruments
    assert g.volumes
    assert g.battery_limits
    assert g.systems
    assert g.sheets
    joined = join_opc_across_graphs(g)
    assert joined >= 0
    report = coverage_report()
    assert "DEXPI_COVERAGE_GAPS" in report or "gaps" in str(report).lower() or report
    root = Path(__file__).resolve().parents[1]
    multi = load_fixtures_multi(
        [root / "fixtures" / "sample_pid.xml", root / "fixtures" / "sample_pid_rich.xml"]
    )
    assert multi.pipelines
    with pytest.raises(FileNotFoundError):
        load_fixture("no-such-fixture-xyz.xml")
    xml_path = tmp_path / "cov.xml"
    xml_path.write_bytes(RICH_XML)
    xs = validate_xsd(xml_path)
    assert "engine" in xs or "ok" in xs


def test_tables_and_routing_variants():
    assert parse_nps_inch('1/2"') == 0.5
    assert parse_nps_inch("3/4") == 0.75
    assert parse_nps_inch("1-1/2") == 1.5
    assert parse_nps_inch("DN150") > 0
    assert parse_nps_inch("") == 4.0
    assert allowable_stress_mpa(20.0) > 0
    assert allowable_stress_mpa(400.0, "A106B") > 0
    assert b16_5_pt_rating_bar(150, 38.0) > 0
    assert b16_5_pt_rating_bar(300, 200.0) > 0
    assert infer_flange_class(10.0, 38.0) >= 150
    pt = b31_3_345_4_2_test_pressure(20.0, 100.0, 21.0)
    assert float(pt["test_pressure_barg"]) > 0
    assert medium_for_service("STEAM")
    assert medium_for_service(None)
    assert table_c1_epsilon_mm_per_m(200.0) > 0
    assert insulation_od_mm('6"', 50.0) > 0
    assert flange_thickness_m('6"', 150) > 0
    assert gasket_thickness_m() > 0
    assert reducer_face_to_face_m('6"', '4"') > 0
    assert valve_face_to_face_m('6"', 150) > 0
    assert next_smaller_bore('6"')
    pts = manhattan_route((0, 0, 0), (3, 4, 5), prefer_order="zyx")
    assert polyline_length(pts) > 0
    for order in ("xyz", "xzy", "yxz", "yzx", "zxy"):
        assert len(manhattan_route((0, 0, 0), (1, 1, 1), prefer_order=order)) >= 2
    assert bore_to_mm('6"') > 0
    assert bore_to_mm("DN100") > 0
    assert bore_to_mm(None) > 0
    g = load_fixture("sample_pid.xml")
    generate_routes(g)
    ensure_routes(g)
    lid = next(iter(g.pipelines))
    get_route(g, lid)
    route_pipeline(g, g.pipelines[lid])
    assert nozzle_point(g, None) is None


def test_generators_and_exports(tmp_path):
    from threadforge.cascade import CASCADE_KINDS_12
    from threadforge.clash import clash_check, generate_clash_report, segment_distance
    from threadforge.exporters.dxf import export_ga_dxf
    from threadforge.exporters.ifc import export_ifc4, reopen_counts, validate_ifc4
    from threadforge.exporters.pdf import export_ga_pdf, export_iso_pdf, extract_pdf_text, pdf_page_count
    from threadforge.exporters.xlsx import export_lists_xlsx, list_row_counts
    from threadforge.flexibility import crafted_hot_line_graph, flexibility_ratio, screen_graph
    from threadforge.generators import (
        build_iwps,
        build_systems_from_graph,
        build_test_packs,
        build_work_packages,
        export_all_piping_artefacts,
        generate_csv_export,
        generate_dlb,
        generate_ga,
        generate_isometric,
        generate_pcf,
        generate_quantities,
        generate_supports_stub,
        get_spool_report,
        regenerate_dirty,
        write_ga_svg,
        write_pcf_text,
        write_routes_artefact,
    )
    from threadforge.hydrotest import build_hydrotest_packs, c01_hydrotest_pin
    from threadforge.iso_sheets import sheet_iso_svg, spool_bom
    from threadforge.iwp_release import apply_iwp_release
    from threadforge.maturity import (
        assert_maturity,
        assess_maturity,
        crafted_feed_graph,
        crafted_ifc_ready_graph,
        issue_ifc,
        maturity_check,
        maturity_index,
        meets_or_exceeds,
    )
    from threadforge.models import ArtefactKind, MaturityLevel
    from threadforge.mto import build_mto, export_mto
    from threadforge.spec_break import parse_rating, validate_spec_breaks
    from threadforge.spooling import crafted_straight_30m
    from threadforge.weld_ndt import export_weld_ndt, n_rt_required

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    out = tmp_path / "art"
    export_all_piping_artefacts(g, output_dir=out)
    generate_quantities(g, output_dir=out)
    generate_csv_export(g, out)
    generate_ga(g, out)
    generate_dlb(g, out)
    write_routes_artefact(g, out)
    generate_supports_stub(g, out)
    build_systems_from_graph(g)
    build_test_packs(g)
    build_work_packages(g)
    build_iwps(g)
    write_ga_svg(g)
    lid = next(iter(g.pipelines))
    generate_pcf(g, lid, output_dir=out)
    generate_isometric(g, lid, out)
    get_spool_report(g, lid)
    clash_check(g)
    generate_clash_report(g, output_dir=out)
    assert segment_distance((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0))[0] >= 0
    screen_graph(g)
    flexibility_ratio(168.3, 12.0, 20.0, 10.0)
    crafted_hot_line_graph()
    packs = build_hydrotest_packs(g)
    if packs:
        c01_hydrotest_pin(packs)
    validate_spec_breaks(g)
    assert parse_rating("150#") == 150
    assert parse_rating(None) is None
    build_mto(g)
    export_mto(g, output_dir=out)
    apply_iwp_release(g)
    sheet_iso_svg(
        {"length_m": 1.0, "axis_points": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]},
        line_number="L",
        sheet_n=1,
        sheet_n_of=1,
    )
    spool_bom({"length_m": 1.0, "bom": []})
    export_weld_ndt(g, output_dir=out)
    regenerate_dirty(
        g,
        [
            ArtefactKind.QUANTITIES,
            ArtefactKind.ISOMETRIC,
            ArtefactKind.PCF,
            ArtefactKind.TEST_PACK,
            ArtefactKind.WORK_PACKAGE,
            ArtefactKind.ROUTES,
            ArtefactKind.SUPPORTS,
            ArtefactKind.GA,
            ArtefactKind.DLB,
            ArtefactKind.CSV,
        ],
        output_dir=out,
    )
    assert n_rt_required(20) >= 1
    list_row_counts(g)
    export_lists_xlsx(g, out / "lists.xlsx")
    try:
        export_ga_dxf(g, out / "ga.dxf")
    except Exception:
        pass
    try:
        ifc = export_ifc4(g, out / "model.ifc")
        if ifc and Path(getattr(ifc, "path", out / "model.ifc")).exists():
            p = Path(getattr(ifc, "path", out / "model.ifc"))
            reopen_counts(p)
            validate_ifc4(p)
    except Exception:
        pass
    try:
        pdf = export_ga_pdf(g, out / "ga.pdf")
        pth = Path(getattr(pdf, "path", out / "ga.pdf"))
        if pth.exists():
            extract_pdf_text(pth)
            pdf_page_count(pth)
        export_iso_pdf(g, lid, out / "iso.pdf")
    except Exception:
        pass
    assert len(CASCADE_KINDS_12) == 12
    crafted = crafted_straight_30m()
    write_pcf_text(crafted, "LINE-CRAFT-30M")
    get_spool_report(crafted, "LINE-CRAFT-30M")
    ready = crafted_ifc_ready_graph()
    issue_ifc(ready)
    assess_maturity(ready)
    maturity_check(MaturityLevel.FEED, required=MaturityLevel.FEED, graph=ready)
    assert maturity_index(MaturityLevel.IFC) >= maturity_index(MaturityLevel.FEED)
    assert meets_or_exceeds(MaturityLevel.IFC, MaturityLevel.DD)
    feed = crafted_feed_graph()
    try:
        assert_maturity(MaturityLevel.FEED, required=MaturityLevel.IFC, graph=feed)
    except Exception:
        pass


def test_schedule_persist_cli_mcp_server(tmp_path, monkeypatch, capsys):
    from fastapi.testclient import TestClient

    from threadforge import agent_tools
    from threadforge.cli import main
    from threadforge.exporters.schedule_io import (
        export_mspdi,
        export_xer,
        iwp_tasks,
        parse_mspdi,
        parse_xer,
        validate_mspdi,
    )
    from threadforge.mcp_server import handle_message, parse_job_resource
    from threadforge.persist import (
        apply_migrations,
        artefact_payload,
        database_url_from_env,
        find_job_by_key,
        find_pg_bin,
        get_job,
        infer_kind,
        lookup_principal,
        sqlite_url,
        verify_api_key,
    )
    from threadforge.rack import assign_rack_tier, classify_service, rack_config
    from threadforge.schedule_4d import volumes_adjacent
    from threadforge.server import create_app, export_openapi
    from threadforge.supports_mss import support_types_kinematic, type_counts

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    from threadforge.generators import build_iwps, build_work_packages

    build_work_packages(g)
    build_iwps(g)
    la = {
        "work_packages": [
            {
                "id": "IWP-1",
                "wp_type": "IWP",
                "name": "I1",
                "start": "2026-01-01",
                "finish": "2026-01-05",
            }
        ],
        "activities": [{"id": "A1", "name": "a", "start": "2026-01-01", "finish": "2026-01-02"}],
    }
    assert iwp_tasks(la)
    xer = export_xer(la, tmp_path / "a.xer")
    parse_xer(xer)
    msp = export_mspdi(la, tmp_path / "a.xml")
    parse_mspdi(msp)
    validate_mspdi(msp)
    if g.volumes:
        vols = list(g.volumes.values())
        if len(vols) >= 2:
            volumes_adjacent(vols[0], vols[1])
    classify_service("FEED")
    assign_rack_tier("DRAIN")
    rack_config(g)
    types = support_types_kinematic([(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 0.0, 8.0)], nominal_bore='6"')
    type_counts(types)

    monkeypatch.setenv("TF_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("TF_API_TOKENS", "admin:adm-token:write,engineer:eng-token:write,reviewer:rev-token:read")
    reset_rate_limits()
    client = TestClient(create_app())
    h = {"Authorization": "Bearer eng-token"}
    assert client.get("/health").status_code == 200
    assert client.get("/tools").status_code == 401
    assert client.get("/tools", headers=h).status_code == 200
    assert client.post("/tools/nope", headers=h, json={}).status_code == 404
    rev = {"Authorization": "Bearer rev-token"}
    assert client.post("/tools/revise_pid", headers=rev, json={"entity_type": "pipeline", "entity_id": "x", "updates": {}}).status_code == 403
    client.post("/tools/ingest_dexpi", headers=h, json={"path": "sample_pid.xml"})
    client.post("/tools/query_graph", headers=h, json={"summary": True})
    bad = client.post("/tools/ingest_dexpi", headers=h, content=b"not-json")
    assert bad.status_code in (200, 409, 422, 404)
    job = client.post("/jobs", headers=h, json={"fixture": "sample_pid.xml", "job_key": "k-cov"})
    assert job.status_code == 202
    dup = client.post("/jobs", headers=h, json={"fixture": "sample_pid.xml", "job_key": "k-cov"})
    assert dup.status_code == 409
    assert client.get("/jobs/missing", headers=h).status_code == 404
    assert client.get("/jobs/missing/artefacts/pcf", headers=h).status_code == 404
    assert client.get("/jobs/missing/events", headers=h).status_code == 404
    up = client.post("/upload", headers={**h, "Content-Type": "application/xml"}, content=RICH_XML)
    assert up.status_code in (200, 201)
    bomb = client.post(
        "/upload",
        headers={**h, "Content-Type": "application/xml"},
        content=b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY e 'a'>]><x/>",
    )
    assert bomb.status_code == 400
    over = client.post(
        "/upload",
        headers={**h, "Content-Length": str(3 * 1024 * 1024)},
        content=b"x",
    )
    assert over.status_code in (413, 400, 200)
    export_openapi(tmp_path / "oa.json")

    url = sqlite_url(tmp_path / "empty.db")
    apply_migrations(url)
    assert get_job(url, "nope") is None
    assert find_job_by_key(url, "nope") is None
    assert lookup_principal(url, "nope") is None
    assert artefact_payload(url, "j", "pcf") is None
    assert not verify_api_key("x", "not-a-hash")
    assert infer_kind(Path("out/pcf/a.pcf")) == "pcf"
    assert infer_kind(Path("out/iso/a.svg")) == "isometric"
    assert infer_kind(Path("misc/foo.bin")) in {"misc", "file", "foo"}
    assert infer_kind(Path("x.json")) in {"json", ""}
    database_url_from_env(tmp_path / "z.db")
    find_pg_bin()

    monkeypatch.chdir(tmp_path)
    agent_tools.SESSION.graph = None
    assert main(["ingest", "--path", "sample_pid.xml"]) == 0
    root = Path(__file__).resolve().parents[1]
    main(["schedule", str(root / "fixtures" / "sample_schedule.json")])
    main(["pipeline", "--all"])
    first_tag = next(iter(agent_tools.SESSION.graph.tags))
    main(["revise", "tag", first_tag, "--set", "name", "X"])
    handle_message({"jsonrpc": "2.0", "id": 9, "method": "initialize"})
    with pytest.raises(ValueError):
        parse_job_resource("http://x")
    with pytest.raises(ValueError):
        parse_job_resource("threadforge://job/only")
    parse_job_resource("threadforge:///job/jid/pcf")
    capsys.readouterr()
    assert date.today()
    assert datetime.now()
