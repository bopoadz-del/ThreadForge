#!/usr/bin/env python3
"""ThreadForge acceptance harness — A01–A30 (v1) and B01–B40 (v2).

Prints one line per check and tallies:
  ACCEPTANCE: N/30 PASS
  ACCEPTANCE: K/40 PASS
Exit 0 iff all 30 A-lines and all 40 B-lines PASS.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RESULTS: list[tuple[str, bool, str]] = []


def _emit(aid: str, ok: bool, evidence: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{aid} {status} {evidence}")
    RESULTS.append((aid, ok, evidence))


def _safe(aid: str, fn: Callable[[], tuple[bool, str]]) -> None:
    try:
        ok, evidence = fn()
        _emit(aid, ok, evidence)
    except Exception as exc:  # noqa: BLE001
        _emit(aid, False, f"exception: {type(exc).__name__}: {exc}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_parent_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD^"],
        cwd=str(ROOT),
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _dir_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for fp in sorted(root.rglob("*")):
        if fp.is_file() and fp.name != "registry.db":
            out[str(fp.relative_to(root))] = _sha(fp)
    return out


def A01() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import validate_xsd

    path = ROOT / "fixtures/public/dexpi13/pids/C01V04-VER.EX01.xml"
    r = validate_xsd(path)
    ok = (
        r.get("status") == "validated"
        and r.get("ok") is True
        and r.get("engine") == "xmlschema"
        and len(r.get("errors") or []) == 0
        and "4.1.1" in str(r.get("xsd", ""))
    )
    return ok, f"status={r.get('status')} engine={r.get('engine')} errors={len(r.get('errors') or [])}"


def A02() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import load_fixture

    g = load_fixture("C01V04-VER.EX01.xml")
    sized = [n for n in g.nozzles.values() if n.size]
    nums = {p.line_number for p in g.pipelines.values()}
    dn_ok = all(bool(p.nominal_bore) for p in g.pipelines.values())
    ok = (
        len(g.pipelines) == 23
        and len(g.equipment) == 21
        and len(g.nozzles) == 21
        and len(sized) >= 19
        and len(g.instruments) == 6
        and any(n.isdigit() for n in nums)
        and dn_ok
    )
    return ok, (
        f"seg={len(g.pipelines)} eq={len(g.equipment)} nz={len(g.nozzles)} "
        f"sized={len(sized)} pif={len(g.instruments)} dn_ok={dn_ok}"
    )


def A03() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import load_fixtures_multi

    c08 = ROOT / "fixtures/public/dexpi13/pids/c08"
    xmls = sorted(c08.glob("*.xml")) if c08.is_dir() else []
    if len(xmls) < 2:
        return False, f"C08 xml count={len(xmls)} (need ≥2 under pids/c08/)"
    g = load_fixtures_multi(xmls)
    joins = [
        e
        for e in g.from_tos.values()
        if e.metadata.get("opc_cross_file") or e.connection_type == "opc_cross_page"
    ]
    pinned = int(g.metadata.get("opc_join_count") or len(joins))
    ok = pinned >= 1 and len(joins) == pinned
    return ok, f"xmls={len(xmls)} joins={len(joins)} pinned={pinned}"


def A04() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import DEXPI_COVERAGE_GAPS, load_fixture, load_fixtures_multi

    names = [
        "C01V04-VER.EX01.xml",
        "C03V04-VER.EX02.xml",
        "E06V01-VER.EX01.xml",
        "P01V01-VER.EX01.xml",
        "P02V01-VER.EX01.xml",
    ]
    errors: list[str] = []
    for n in names:
        try:
            load_fixture(n)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{n}:{exc}")
    c08 = ROOT / "fixtures/public/dexpi13/pids/c08"
    xmls = sorted(c08.glob("*.xml")) if c08.is_dir() else []
    if xmls:
        try:
            load_fixtures_multi(xmls)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"c08:{exc}")
    else:
        errors.append("c08:missing")
    gaps = len(DEXPI_COVERAGE_GAPS)
    ok = not errors and gaps <= 6
    return ok, f"errors={errors or 'none'} gaps={gaps}"


def A05() -> tuple[bool, str]:
    from threadforge.generators import generate_pcf
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.maturity import maturity_check
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid.xml")
    ensure_routes(g)
    fabricated_lines = [
        lid
        for lid, r in (g.routes or {}).items()
        if r.get("geometry_source") == "fabricated" or r.get("fabricated")
    ]
    flagged = 0
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for lid in fabricated_lines:
            a = generate_pcf(g, lid, output_dir=out)
            if (a.payload or {}).get("geometry_source") == "fabricated" or "FABRICATED" in (a.message or ""):
                flagged += 1
            elif a.path and "FABRICATED" in Path(a.path).read_text(encoding="utf-8", errors="replace"):
                flagged += 1
            elif (g.routes.get(lid) or {}).get("geometry_source") == "fabricated":
                # artefact must carry flag in payload
                if (a.payload or {}).get("geometry_source") != "fabricated":
                    # force fail unless payload set
                    pass
                else:
                    flagged += 1
    from threadforge.maturity import assess_maturity
    from threadforge.models import MaturityLevel
    level = assess_maturity(g)
    # assess_maturity may return dict
    if isinstance(level, dict):
        cur = MaturityLevel.FEED if "L1" in str(level.get("maturity")) or "L2" in str(level.get("maturity")) else MaturityLevel.IFC
        # map L3 etc.
        mat = str(level.get("maturity", ""))
        if "L5" in mat or "IFC" in mat:
            cur = MaturityLevel.IFC
        elif "L4" in mat:
            cur = MaturityLevel.DETAILED
        else:
            cur = MaturityLevel.FEED
    else:
        cur = getattr(level, "level", level)
    gate = maturity_check(cur, required=MaturityLevel.IFC, action="export_ifc", graph=g)
    refuses_ifc = not gate.get("allowed", True)
    # Also require fabricated geometry_source on PCF payload
    with tempfile.TemporaryDirectory() as td2:
        for lid in fabricated_lines:
            a = generate_pcf(g, lid, output_dir=Path(td2))
            payload = a.payload or {}
            if payload.get("geometry_source") != "fabricated":
                # stamp expected field for honesty — generators should set it
                return False, f"pcf payload missing fabricated for {lid} keys={list(payload)[:8]}"
            flagged += 1
    ok = bool(fabricated_lines) and refuses_ifc and flagged >= 1
    return ok, f"fabricated_lines={fabricated_lines} flagged={flagged} refuses_ifc={refuses_ifc}"


def A06() -> tuple[bool, str]:
    from threadforge.exporters.ifc import export_ifc4
    from threadforge.generators import generate_isometric, generate_pcf, generate_quantities
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    qty = {r["line_id"]: float(r["length_m"]) for r in (generate_quantities(g).payload or {}).get("rows", [])}
    mismatches = []
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        ifc = export_ifc4(g, out / "m.ifc")
        import re as _re

        import ifcopenshell

        f = ifcopenshell.open(str(ifc.path))
        length_re = _re.compile(r"LENGTH_M=([0-9.]+)")
        ifc_by_line: dict[str, float] = {}
        for s in f.by_type("IfcPipeSegment"):
            desc = s.Description or ""
            mlen = length_re.search(desc)
            mline = _re.search(r"LINE=([^;]+)", desc)
            if mlen and mline:
                ifc_by_line[mline.group(1)] = ifc_by_line.get(mline.group(1), 0.0) + float(mlen.group(1))
        for lid, route in g.routes.items():
            rl = float(route["length_m"])
            ql = qty.get(lid)
            if ql is None or abs(ql - rl) > 0.001:
                mismatches.append(f"{lid}:qty={ql} route={rl}")
            a = generate_pcf(g, lid, output_dir=out)
            pr = float((a.payload or {}).get("route_length_m") or -1)
            if abs(pr - rl) > 0.001:
                mismatches.append(f"{lid}:pcf_payload={pr} route={rl}")
            iso = generate_isometric(g, lid, output_dir=out)
            iso_len = float(((iso.payload or {}).get("route") or {}).get("length_m") or -1)
            if abs(iso_len - rl) > 0.001:
                mismatches.append(f"{lid}:iso={iso_len} route={rl}")
            # IFC axis within 0.5%
            line_no = g.pipelines[lid].line_number
            il = ifc_by_line.get(line_no)
            if il is None or abs(il - rl) / max(rl, 1e-6) > 0.005:
                mismatches.append(f"{lid}:ifc={il} route={rl}")
    ok = not mismatches
    return ok, f"mismatches={mismatches or 'none'} lines={len(g.routes)}"


def A07() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    bends = []
    clears = True
    for lid, r in g.routes.items():
        b = r.get("bend_count")
        if b is None:
            pts = r.get("points") or []
            b = max(0, len(pts) - 2)
        bends.append(b)
        if r.get("collides_equipment"):
            clears = False
    # Require explicit clearance metadata + monotonic drains from router
    has_clear_meta = all(
        r.get("clearance_ok") is True or r.get("equipment_clearance_mm") is not None
        for r in g.routes.values()
    )
    drains = all(r.get("drains_monotonic") is True for r in g.routes.values())
    ok = clears and has_clear_meta and drains and (max(bends) if bends else 0) <= 4
    return ok, f"max_bends={max(bends) if bends else None} clears={clears} clear_meta={has_clear_meta} drains={drains}"


def A08() -> tuple[bool, str]:
    from threadforge.clash import generate_clash_report
    from threadforge.generators import export_all_piping_artefacts
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    with tempfile.TemporaryDirectory() as td:
        export_all_piping_artefacts(g, output_dir=Path(td))
    ensure_routes(g)
    rep_art = generate_clash_report(g)
    rep = rep_art.payload if hasattr(rep_art, "payload") else rep_art
    hard = rep.get("hard_count", -1)
    g2 = load_fixture("sample_pid_rich.xml")
    ensure_routes(g2)
    lids = list(g2.routes.keys())
    if len(lids) >= 2:
        g2.routes[lids[0]]["points"] = [
            {"x": 0, "y": 0, "z": 5},
            {"x": 10, "y": 0, "z": 5},
        ]
        g2.routes[lids[1]]["points"] = [
            {"x": 5, "y": -5, "z": 5},
            {"x": 5, "y": 5, "z": 5},
        ]
        # also set radii for clash capsules if needed
        for lid in lids[:2]:
            g2.routes[lid]["nominal_bore"] = g2.pipelines[lid].nominal_bore
    rep3 = generate_clash_report(g2)
    rep3p = rep3.payload if hasattr(rep3, "payload") else rep3
    crafted_hard = rep3p.get("hard_count", 0)
    excluded = "excluded_fabricated" in rep3p and "skipped_shared_connection_pairs" in rep3p
    ok = hard == 0 and crafted_hard >= 1 and excluded
    return ok, f"rich_hard={hard} crafted_hard={crafted_hard} excluded_keys={excluded}"


def A09() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes, support_placeholders_engineered

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    pinned = {}
    types_ok = True
    for lid, pipe in g.pipelines.items():
        r = g.routes[lid]
        pts = [(p["x"], p["y"], p["z"]) for p in r["points"]]
        supports = support_placeholders_engineered(pts, pipe.nominal_bore)
        pinned[lid] = len(supports)
        kinds = {s.get("type") for s in supports}
        if "near_nozzle" not in kinds:
            types_ok = False
        if len(pts) > 2 and "near_bend" not in kinds:
            types_ok = False
    expected = {"LINE-200-P-1001": 6, "LINE-200-P-1002": 15, "LINE-210-G-2001": 8, "LINE-200-D-1010": 7}
    ok = pinned == expected and types_ok
    return ok, f"supports_per_line={pinned} expected={expected} types_ok={types_ok}"


def A10() -> tuple[bool, str]:
    from threadforge.generators import generate_pcf
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.pcf_reader import assert_contiguous, parse_pcf
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        problems = []
        n = 0
        for lid in g.pipelines:
            a = generate_pcf(g, lid, output_dir=out)
            n += 1
            path = Path(a.path) if a.path else None
            if path is None or not path.exists():
                problems.append(f"{lid}:missing")
                continue
            doc = parse_pcf(path)
            try:
                assert_contiguous(doc, tol_mm=1.0)
            except TypeError:
                assert_contiguous(doc)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{lid}:contig:{exc}")
            text = path.read_text(encoding="utf-8", errors="replace")
            if "FLANGE" in text and "GASKET" not in text:
                problems.append(f"{lid}:flange_without_gasket")
        ok = not problems and n > 0
        return ok, f"problems={problems or 'none'} files={n}"


def A11() -> tuple[bool, str]:
    """Independent PCF parser (not pcf_reader)."""
    try:
        from threadforge.pcf_strict import parse_pcf_strict
    except ImportError:
        return False, "pcf_strict module missing"
    from threadforge.generators import generate_pcf
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        parsed = 0
        for lid in g.pipelines:
            a = generate_pcf(g, lid, output_dir=out)
            doc = parse_pcf_strict(Path(a.path))
            if not doc.get("components"):
                return False, f"no components in {a.path}"
            parsed += 1
        return parsed > 0, f"parsed={parsed}"


def A12() -> tuple[bool, str]:
    from threadforge import tables as T

    checks = []
    checks.append(abs(T.od_mm('6"') - 168.3) < 0.05)
    checks.append(abs(T.mass_per_m('6"', "40") - 28.26) / 28.26 <= 0.01)
    tf = T.FLANGE_THICKNESS_MM_CL150
    checks.append(tf.get(4.0) == 23.9)
    checks.append(tf.get(5.0) == 23.9)
    checks.append(tf.get(6.0) == 25.4)
    checks.append(tf.get(8.0) == 28.4)
    doc = (T.FLANGE_THICKNESS_MM_CL150 and T.flange_thickness_m.__doc__) or ""
    cited = "B16.5" in (doc or "") and "Table" in (doc or "")
    # 5-inch key may need adding
    ok = all(checks) and cited and 5.0 in tf
    return ok, f"checks={checks} cited={cited} keys={sorted(tf)}"


def A13() -> tuple[bool, str]:
    from threadforge.generators import generate_isometric
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        svg_ok = bom_ok = nfc = False
        for lid in g.pipelines:
            a = generate_isometric(g, lid, output_dir=out)
            payload = a.payload or {}
            if payload.get("projection") == "30deg" or payload.get("iso_angle_deg") == 30:
                svg_ok = True
            if payload.get("bom"):
                bom_ok = True
            for path in out.rglob("*.svg"):
                txt = path.read_text(encoding="utf-8", errors="replace")
                if "NOT FOR CONSTRUCTION" in txt:
                    nfc = True
                if "north" in txt.lower():
                    svg_ok = True
        ok = svg_ok and bom_ok and nfc
        return ok, f"svg30={svg_ok} bom={bom_ok} nfc={nfc}"


def A14() -> tuple[bool, str]:
    try:
        import ifcopenshell
    except ImportError:
        return False, "ifcopenshell missing"
    from threadforge.exporters.ifc import export_ifc4
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    with tempfile.TemporaryDirectory() as td:
        art = export_ifc4(g, Path(td) / "model.ifc")
        path = Path(art.path)
        if not path.exists():
            return False, "ifc not written"
        f = ifcopenshell.open(str(path))
        segs = f.by_type("IfcPipeSegment")
        fits = f.by_type("IfcPipeFitting")
        has_pset = any("BORE=" in ((s.Description) or "") for s in segs)
        ok = len(segs) >= 1 and has_pset
        return ok, f"segments={len(segs)} fittings={len(fits)} pset={has_pset}"


def A15() -> tuple[bool, str]:
    try:
        import ezdxf
    except ImportError:
        return False, "ezdxf missing"
    from threadforge.exporters.dxf import export_ga_dxf
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ga.dxf"
        art = export_ga_dxf(g, path)
        doc = ezdxf.readfile(str(path))
        layers = [l.dxf.name for l in doc.layers]
        msp = doc.modelspace()
        count = len(list(msp))
        has_vol = any(l.startswith("VOL_") for l in layers)
        has_disc = any(l in layers for l in ("PIP", "EQP", "INS"))
        ok = count == 21 and has_vol and has_disc and "ISO" in layers
        return ok, f"entities={count} layers={layers} has_vol={has_vol} has_disc={has_disc} art={art.status}"


def A16() -> tuple[bool, str]:
    from threadforge.generators import generate_quantities
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    qty = generate_quantities(g)
    rows = qty.payload.get("rows") or []
    need = {"length_m", "weight_kg", "bolts", "gaskets", "surface_m2", "insulation_m2"}
    ok_rows = all(need.issubset(set(r.keys())) for r in rows) if rows else False
    # reconcile with PCF component counts when present
    recon = all(r.get("pcf_component_count") is not None for r in rows) if rows else False
    ok = ok_rows and recon
    return ok, f"rows={len(rows)} keys_ok={ok_rows} recon={recon}"


def A17() -> tuple[bool, str]:
    from threadforge.generators import build_test_packs
    from threadforge.ingest_dexpi import load_fixture

    g = load_fixture("C01V04-VER.EX01.xml")
    packs = build_test_packs(g)
    with_p = [p for p in packs if p.metadata.get("test_pressure_barg") is not None]
    ok = bool(packs) and len(with_p) >= 1
    return ok, f"packs={len(packs)} with_pressure={len(with_p)} sample={packs[0].metadata if packs else None}"


def A18() -> tuple[bool, str]:
    from threadforge.generators import build_work_packages
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.models import WPType

    g = load_fixture("sample_pid_rich.xml")
    wps = build_work_packages(g)
    iwps = [w for w in wps if w.wp_type == WPType.IWP]
    ok_size = all(len(w.tags) <= 25 for w in iwps) if iwps else False
    ok_qty = all("kg" in (w.quantity_measure or "") and "m" in (w.quantity_measure or "") for w in iwps)
    ok_crew = all((w.metadata or {}).get("crew_hours") is not None for w in iwps)
    ok = bool(iwps) and ok_size and ok_qty and ok_crew
    return ok, f"total={len(wps)} iwps={len(iwps)} size_ok={ok_size} qty_ok={ok_qty} crew_ok={ok_crew}"


def A19() -> tuple[bool, str]:
    from threadforge.generators import build_work_packages
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.schedule_4d import Schedule4D

    g = load_fixture("sample_pid.xml")  # schedule WP ids target VOL-A/B/C
    build_work_packages(g)
    sch = Schedule4D(g)
    sch.load_json(ROOT / "fixtures/sample_schedule.json")
    sch.attach_to_work_packages()
    rep = sch.co_activity_check()
    if hasattr(rep, "payload"):
        rep = rep.payload
    soft = rep.get("soft_count", rep.get("adjacent_count"))
    hard = rep.get("hard_count", rep.get("same_volume_count"))
    ok = soft is not None and hard is not None and hard >= 1
    return ok, f"hard={hard} soft={soft} keys={sorted(rep)[:8]}"


def A20() -> tuple[bool, str]:
    from threadforge.cascade import CascadeEngine
    from threadforge.generators import export_all_piping_artefacts
    from threadforge.ingest_dexpi import load_fixture

    g = load_fixture("sample_pid_rich.xml")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        export_all_piping_artefacts(g, output_dir=out)
        eng = CascadeEngine(g)
        for pth in out.rglob("*.pcf"):
            from threadforge.models import ArtefactDescriptor, ArtefactKind
            art = ArtefactDescriptor(
                id=f"ART-{pth.name}",
                kind=ArtefactKind.PCF,
                status="ready",
                path=str(pth),
                related_lines=[next(iter(g.pipelines))],
            )
            eng.register_artefact(art)
        lid = next(iter(g.pipelines))
        eng.record_change("pipeline", lid, action="revise", details={"nominal_bore": "DN100"})
        dirty = eng.dirty_summary()
        ok = bool(dirty.get("dirty"))
        return ok, f"dirty={dirty} line={lid}"


def A21() -> tuple[bool, str]:
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.maturity import assess_maturity
    from threadforge.routing import ensure_routes

    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    m = assess_maturity(g)
    reasons = m.get("reasons") if isinstance(m, dict) else getattr(m, "reasons", None)
    ok = isinstance(reasons, dict) and "fabricated_count" in reasons and "unmatched_opc_count" in reasons
    return ok, f"level={m.get('maturity') if isinstance(m, dict) else m} reasons={reasons}"


def A22() -> tuple[bool, str]:
    try:
        from fastapi.testclient import TestClient

        from threadforge.server import create_app
    except Exception as exc:  # noqa: BLE001
        return False, f"import:{exc}"
    os.environ["TF_API_TOKENS"] = "engineer:eng-token:write,reviewer:rev-token:read"
    os.environ["TF_DATA"] = tempfile.mkdtemp()
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer eng-token"}
    unknown = client.post("/tools/no_such_tool", headers=headers, json={})
    typed = client.post("/jobs", headers=headers, json={"fixture": 123})
    first = client.post(
        "/jobs",
        headers=headers,
        json={"fixture": "sample_pid.xml", "job_key": "A22-dup"},
    )
    dup = client.post(
        "/jobs",
        headers=headers,
        json={"fixture": "sample_pid.xml", "job_key": "A22-dup"},
    )
    openapi = ROOT / "openapi.json"
    ok = (
        unknown.status_code == 404
        and typed.status_code == 422
        and first.status_code == 202
        and dup.status_code == 409
        and openapi.exists()
    )
    return ok, (
        f"unknown={unknown.status_code} typed={typed.status_code} "
        f"first={first.status_code} dup={dup.status_code} openapi={openapi.exists()}"
    )


def A23() -> tuple[bool, str]:
    try:
        from fastapi.testclient import TestClient

        from threadforge import agent_tools
        from threadforge.mcp_server import call_tool
        from threadforge.server import create_app
    except Exception as exc:  # noqa: BLE001
        return False, f"import:{exc}"
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        mcp_dir = base / "mcp"
        http_dir = base / "http"
        mcp_dir.mkdir()
        http_dir.mkdir()
        agent_tools.SESSION.graph = None
        agent_tools.SESSION.job = None
        agent_tools.SESSION.cascade = None
        agent_tools.SESSION.schedule = None
        call_tool("ingest_dexpi", {"path": "sample_pid_rich.xml"})
        call_tool("export_artefacts", {"output_dir": str(mcp_dir)})
        mcp_hashes = _dir_hashes(mcp_dir)

        agent_tools.SESSION.graph = None
        agent_tools.SESSION.job = None
        agent_tools.SESSION.cascade = None
        agent_tools.SESSION.schedule = None
        prev_tokens = os.environ.pop("TF_API_TOKENS", None)
        os.environ["TF_DATA"] = str(base / "data")
        try:
            client = TestClient(create_app())
            ingested = client.post("/tools/ingest_dexpi", json={"path": "sample_pid_rich.xml"})
            exported = client.post("/tools/export_artefacts", json={"output_dir": str(http_dir)})
        finally:
            if prev_tokens is not None:
                os.environ["TF_API_TOKENS"] = prev_tokens
        if ingested.status_code != 200 or exported.status_code != 200:
            return False, f"http ingest={ingested.status_code} export={exported.status_code}"
        http_hashes = exported.json().get("artefact_hashes") or _dir_hashes(http_dir)
        http_hashes = {k.replace("\\", "/"): v for k, v in http_hashes.items()}
        mcp_hashes = {k.replace("\\", "/"): v for k, v in mcp_hashes.items()}
        common = set(mcp_hashes) & set(http_hashes)
        if not common:
            return False, f"no common artefacts mcp={len(mcp_hashes)} http={len(http_hashes)}"
        mismatches = [k for k in sorted(common) if mcp_hashes[k] != http_hashes[k]]
        ok = not mismatches
        return ok, f"common={len(common)} mismatches={mismatches[:5] or 'none'}"


def A24() -> tuple[bool, str]:
    try:
        from fastapi.testclient import TestClient

        from threadforge.server import create_app
    except Exception as exc:  # noqa: BLE001
        return False, f"import:{exc}"
    os.environ["TF_API_TOKENS"] = "engineer:eng-token:write,reviewer:rev-token:read"
    app = create_app()
    client = TestClient(app)
    h = client.get("/health")
    p = client.get("/tools")
    ok = h.status_code == 200 and p.status_code == 401
    return ok, f"health={h.status_code} tools={p.status_code}"


def A25() -> tuple[bool, str]:
    try:
        from fastapi.testclient import TestClient

        from threadforge.server import create_app
    except Exception as exc:  # noqa: BLE001
        return False, f"import:{exc}"
    os.environ.setdefault("TF_API_TOKENS", "engineer:eng-token:write,reviewer:rev-token:read")
    os.environ["TF_DATA"] = tempfile.mkdtemp()
    app = create_app()
    client = TestClient(app)
    headers = {"Authorization": "Bearer eng-token"}
    r = client.post("/jobs", headers=headers, json={"fixture": "sample_pid.xml"})
    ok = r.status_code in (202, 200) and ("job" in r.text.lower() or "id" in r.text.lower())
    return ok, f"status={r.status_code} body={r.text[:120]}"


def A26() -> tuple[bool, str]:
    try:
        from fastapi.testclient import TestClient

        from threadforge.server import create_app
    except Exception as exc:  # noqa: BLE001
        return False, f"import:{exc}"
    app = create_app()
    client = TestClient(app)
    r = client.get("/health")
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    # fail-closed fields
    need = {"status", "data_dir_writable", "registry_schema", "fixture_shas"}
    ok = r.status_code == 200 and (need.issubset(body.keys()) or body.get("fail_closed") is True)
    return ok, f"keys={list(body)[:10]}"


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64,}$")
_REQUIRED_CI_JOBS = ("test", "docker", "acceptance", "probes", "publish")


def _docker_health_five() -> tuple[bool, str]:
    """HEAD^ docker evidence: five live fields. File presence / old status is not enough."""
    ev = ROOT / "artifacts/ci/docker_health.json"
    if not ev.is_file():
        return False, "missing artifacts/ci/docker_health.json"
    try:
        data = json.loads(ev.read_text(encoding="utf-8"))
        parent = _git_parent_sha()
    except Exception as exc:  # noqa: BLE001
        return False, f"evidence:{type(exc).__name__}: {exc}"
    named = data.get("sha") or data.get("parent_sha") or data.get("git_sha")
    if named != parent:
        return False, f"evidence_sha={named} parent={parent} (HEAD evidence must name parent sha)"
    health_status = data.get("health_status")
    health_body = data.get("health_body")
    unauth = data.get("tools_unauth_status")
    auth = data.get("tools_auth_status")
    digest = str(data.get("image_digest") or "")
    body_ok = False
    if isinstance(health_body, dict):
        body_ok = bool(health_body) and "status" in health_body
    elif isinstance(health_body, str):
        body_ok = len(health_body.strip()) > 2
    digest_ok = bool(_DIGEST_RE.match(digest))
    ok = health_status == 200 and body_ok and unauth == 401 and auth == 200 and digest_ok
    return ok, (
        f"sha={named} health_status={health_status} health_body={'yes' if body_ok else 'no'} "
        f"tools_unauth_status={unauth} tools_auth_status={auth} image_digest={digest or '-'}"
    )


def _ci_parent_success() -> tuple[bool, str]:
    """HEAD^ Actions run must conclude success with required jobs.

    Token or network absent → FAIL (never PASS). Committed ci_run.json is not a PASS path.
    ``status=completed`` is not ``conclusion=success``.
    """
    try:
        parent = _git_parent_sha()
    except Exception as exc:  # noqa: BLE001
        return False, f"parent_sha:{type(exc).__name__}: {exc}"
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        return False, "token absent"
    repo = os.environ.get("GITHUB_REPOSITORY", "bopoadz-del/ThreadForge")
    url = f"https://api.github.com/repos/{repo}/actions/runs?head_sha={parent}&per_page=20"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "threadforge-acceptance",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"network absent/failed: {type(exc).__name__}: {exc}"
    runs = payload.get("workflow_runs") or []
    details: list[str] = []
    for run in runs:
        conclusion = str(run.get("conclusion") or "").lower()
        run_id = run.get("id")
        jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=50"
        try:
            req2 = urllib.request.Request(jobs_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=15) as resp:
                jobs_payload = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return False, f"network absent/failed jobs: {type(exc).__name__}: {exc}"
        job_map: dict[str, str] = {}
        for job in jobs_payload.get("jobs") or []:
            job_map[str(job.get("name") or "")] = str(job.get("conclusion") or "").lower()
        missing = [name for name in _REQUIRED_CI_JOBS if job_map.get(name) != "success"]
        details.append(f"run={run_id} conclusion={conclusion} jobs={job_map} missing={missing}")
        if conclusion == "success" and not missing:
            return True, (
                f"actions_api run={run_id} sha={parent} conclusion=success "
                f"jobs={list(_REQUIRED_CI_JOBS)}"
            )
    return False, (
        f"no successful run with jobs {list(_REQUIRED_CI_JOBS)} for parent={parent} "
        f"n={len(runs)} {details[:2] or 'no-runs'}"
    )


def A27() -> tuple[bool, str]:
    """B03: docker_health.json for HEAD^ must carry five live fields."""
    return _docker_health_five()


def A28() -> tuple[bool, str]:
    """B02: Actions conclusion==success for HEAD^ with required jobs; token/network required."""
    return _ci_parent_success()


def A29() -> tuple[bool, str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    walls = (ROOT / "WALLS.md").read_text(encoding="utf-8")
    system = (ROOT / "agent/SYSTEM.md").read_text(encoding="utf-8")
    changelog = ROOT / "CHANGELOG.md"
    regen = "AUTO-GENERATED" in readme and "acceptance.py" in readme
    tools_mapped = "A01" in system or "acceptance" in system.lower()
    ok = changelog.exists() and regen and "NWD" in walls and tools_mapped
    return ok, f"changelog={changelog.exists()} regen={regen} tools_mapped={tools_mapped}"


def A30() -> tuple[bool, str]:
    """v1.0.1 must exist locally and on origin at the same peeled commit sha."""
    try:
        local = subprocess.check_output(
            ["git", "tag", "-l", "v1.0.1"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        remote = subprocess.check_output(
            ["git", "ls-remote", "--tags", "origin", "refs/tags/v1.0.1*"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception as exc:  # noqa: BLE001
        return False, f"git:{type(exc).__name__}: {exc}"
    has_local = any(tag == "v1.0.1" for tag in local.split())
    has_remote = "refs/tags/v1.0.1" in remote
    local_sha = ""
    remote_sha = ""
    if has_local:
        try:
            local_sha = subprocess.check_output(
                ["git", "rev-parse", "v1.0.1^{commit}"],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except Exception as exc:  # noqa: BLE001
            return False, f"local_sha:{type(exc).__name__}: {exc}"
    peeled = ""
    lightweight = ""
    for line in remote.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref.endswith("^{}"):
            peeled = sha
        elif ref.endswith("refs/tags/v1.0.1"):
            lightweight = sha
    remote_sha = peeled or lightweight
    match = bool(local_sha and remote_sha and local_sha == remote_sha)
    ok = has_local and has_remote and match
    remote_word = "match" if match else ("mismatch" if (has_local and has_remote) else str(has_remote))
    return ok, f"tag=v1.0.1 remote={remote_word} local_sha={local_sha or '-'} remote_sha={remote_sha or '-'}"


def B01() -> tuple[bool, str]:
    """main is the only origin head; v1.0.0 / v1.0.1 (and v2.0.0 if present) sit on it."""
    try:
        raw = subprocess.check_output(
            ["git", "ls-remote", "--heads", "origin"],
            cwd=str(ROOT),
            text=True,
            timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"ls-remote heads failed: {type(exc).__name__}: {exc}"
    refs = [line.split()[1] for line in raw.splitlines() if len(line.split()) == 2]
    if refs != ["refs/heads/main"]:
        return False, f"heads={refs} count={len(refs)} want=[refs/heads/main]"
    try:
        main_line = subprocess.check_output(
            ["git", "ls-remote", "origin", "refs/heads/main"],
            cwd=str(ROOT),
            text=True,
            timeout=20,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"ls-remote main failed: {type(exc).__name__}: {exc}"
    main_sha = main_line.split()[0] if main_line else ""
    if not main_sha:
        return False, "origin/main sha empty"
    tag_bits: list[str] = []
    for tag in ("v1.0.0", "v1.0.1"):
        try:
            remote = subprocess.check_output(
                ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}*"],
                cwd=str(ROOT),
                text=True,
                timeout=20,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            return False, f"ls-remote {tag} failed: {type(exc).__name__}: {exc}"
        peeled = ""
        lightweight = ""
        for line in remote.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            sha, ref = parts
            if ref.endswith("^{}"):
                peeled = sha
            elif ref.endswith(f"refs/tags/{tag}"):
                lightweight = sha
        tag_sha = peeled or lightweight
        if not tag_sha:
            return False, f"tag {tag} missing on origin"
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tag_sha, main_sha],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if anc.returncode != 0:
            return False, f"{tag}={tag_sha} not ancestor of main={main_sha}"
        tag_bits.append(f"{tag}={tag_sha[:12]}")
    try:
        v2_raw = subprocess.check_output(
            ["git", "ls-remote", "--tags", "origin", "refs/tags/v2.0.0*"],
            cwd=str(ROOT),
            text=True,
            timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"ls-remote v2.0.0 failed: {type(exc).__name__}: {exc}"
    v2_note = "v2.0.0=absent"
    if any(line.split()[-1].endswith("refs/tags/v2.0.0") for line in v2_raw.splitlines() if line.split()):
        peeled = ""
        lightweight = ""
        for line in v2_raw.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            sha, ref = parts
            if ref.endswith("^{}"):
                peeled = sha
            elif ref.endswith("refs/tags/v2.0.0"):
                lightweight = sha
        v2_sha = peeled or lightweight
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", v2_sha, main_sha],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if anc.returncode != 0:
            return False, f"v2.0.0={v2_sha} not ancestor of main={main_sha}"
        v2_note = f"v2.0.0={v2_sha[:12]}"
    return True, f"heads=1 main={main_sha} tags={','.join(tag_bits)} {v2_note}"


def B02() -> tuple[bool, str]:
    return _ci_parent_success()


def B03() -> tuple[bool, str]:
    return _docker_health_five()


def B05() -> tuple[bool, str]:
    """Vendor TrainingTestCases example PIDs: ingest every file; counts match pins.json."""
    from threadforge.dexpi_public import entity_counts, file_sha256, load_pins, vendor_xmls
    from threadforge.ingest_dexpi import parse_dexpi_xml

    xmls = vendor_xmls()
    pins = load_pins()["counts"]
    if len(xmls) != len(pins):
        return False, f"xmls={len(xmls)} pins={len(pins)}"
    exceptions: list[str] = []
    mismatches: list[str] = []
    for path in xmls:
        try:
            graph = parse_dexpi_xml(path)
        except Exception as exc:  # noqa: BLE001
            exceptions.append(f"{path.name}:{type(exc).__name__}")
            continue
        got = entity_counts(graph)
        exp = pins.get(path.name)
        if exp is None:
            mismatches.append(f"{path.name}:unpinned")
            continue
        if file_sha256(path) != exp.get("sha256"):
            mismatches.append(f"{path.name}:sha")
        for key in ("pipelines", "equipment", "nozzles", "instruments"):
            if int(got[key]) != int(exp[key]):
                mismatches.append(f"{path.name}:{key}={got[key]} want={exp[key]}")
    ok = not exceptions and not mismatches and len(xmls) >= 30
    return ok, (
        f"files={len(xmls)} exceptions={exceptions or 'none'} "
        f"mismatches={mismatches[:6] or 'none'}"
    )


def B06() -> tuple[bool, str]:
    """Each vendor PID validates via xmlschema; known_deltas only if documented per file."""
    from threadforge.dexpi_public import file_known_deltas, vendor_xmls
    from threadforge.ingest_dexpi import validate_xsd

    xmls = vendor_xmls()
    bad: list[str] = []
    validated = 0
    documented_invalid = 0
    for path in xmls:
        result = validate_xsd(path)
        documented = file_known_deltas(path.name)
        engine = result.get("engine")
        deltas = result.get("known_deltas") or []
        if engine != "xmlschema":
            bad.append(f"{path.name}:engine={engine}")
            continue
        if documented:
            if result.get("ok") is True or list(deltas) != documented:
                bad.append(f"{path.name}:documented_delta_mismatch ok={result.get('ok')}")
            else:
                documented_invalid += 1
            continue
        if (
            result.get("ok") is True
            and result.get("status") == "validated"
            and not deltas
            and len(result.get("errors") or []) == 0
        ):
            validated += 1
        else:
            bad.append(f"{path.name}:status={result.get('status')} deltas={deltas[:1]}")
    ok = not bad and (validated + documented_invalid) == len(xmls) and len(xmls) >= 30
    return ok, f"validated={validated} documented_invalid={documented_invalid} bad={bad[:5] or 'none'}"


_PINNED_VENDOR_ONLY = [
    {"name": "AVEVA ComponentClass URI dictionary", "vendor": "AVEVA"},
    {"name": "Hexagon Smart P&ID ComponentClass URI dictionary", "vendor": "Hexagon"},
    {"name": "Autodesk Plant 3D ComponentClass URI dictionary", "vendor": "Autodesk"},
]


def B07() -> tuple[bool, str]:
    """DEXPI_COVERAGE_GAPS empty; 1.3 core parsed; vendor gaps pinned with vendor names."""
    from threadforge.ingest_dexpi import (
        DEXPI_COVERAGE_GAPS,
        VENDOR_ONLY_GAPS,
        coverage_report,
        load_fixture,
    )

    cov = coverage_report()
    if DEXPI_COVERAGE_GAPS != [] or cov["gaps"] != []:
        return False, f"gaps={DEXPI_COVERAGE_GAPS}"
    if VENDOR_ONLY_GAPS != _PINNED_VENDOR_ONLY or cov.get("vendor_only_gaps") != _PINNED_VENDOR_ONLY:
        return False, f"vendor_only={VENDOR_ONLY_GAPS}"
    need = (
        "PipingComponent subtypes",
        "InstrumentationLoop",
        "SignalLine",
        "ActuatingSystem",
        "InlineComponent",
        "PipeTee",
        "PipeCross",
        "PropertyBreak",
        "SpecBreak",
        "Insulation",
        "Tracing",
    )
    missing = [n for n in need if n not in cov["supported_elements"]]
    g = load_fixture("C01V04-VER.EX01.xml")
    g3 = load_fixture("C03V04-VER.EX02.xml")
    tees = sum(1 for c in g.piping_components.values() if c.get("component_class") == "PipeTee")
    ok = (
        not missing
        and tees >= 1
        and bool(g.instrumentation_loops)
        and bool(g.signal_lines)
        and bool(g.actuating_systems)
        and bool(g.inline_components)
        and int(g3.metadata.get("insulation_count") or 0) >= 1
        and int(g3.metadata.get("tracing_count") or 0) >= 1
    )
    return ok, (
        f"tees={tees} loops={len(g.instrumentation_loops)} signals={len(g.signal_lines)} "
        f"acts={len(g.actuating_systems)} inline={len(g.inline_components)} "
        f"insul={g3.metadata.get('insulation_count')} trace={g3.metadata.get('tracing_count')} "
        f"missing={missing or 'none'}"
    )


def B08() -> tuple[bool, str]:
    """C03 Equinor branch count pinned; C01 branch routes start at tee stub, not nozzle."""
    from threadforge.dexpi_public import load_pins
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import fitting_stub_xyz, nozzle_point, route_pipeline

    pins = load_pins()["counts"]
    g3 = load_fixture("C03V04-VER.EX02.xml")
    pinned = int(pins["C03V04-VER.EX02.xml"]["branches"])
    computed = int(g3.metadata.get("branch_count") or 0)
    if computed != pinned:
        return False, f"C03 branch_count={computed} pin={pinned}"
    g = load_fixture("C01V04-VER.EX01.xml")
    c01_pin = int(pins["C01V04-VER.EX01.xml"]["branches"])
    if int(g.metadata.get("branch_count") or 0) != c01_pin:
        return False, f"C01 branch_count={g.metadata.get('branch_count')} pin={c01_pin}"
    checked = 0
    for pipe in g.pipelines.values():
        if not pipe.metadata.get("branch_route"):
            continue
        if pipe.from_tag not in g.branches and pipe.to_tag not in g.branches:
            continue
        route = route_pipeline(g, pipe)
        fitting = pipe.from_tag if pipe.from_tag in g.branches else pipe.to_tag
        stub = fitting_stub_xyz(g, fitting)
        if stub is None:
            return False, f"{pipe.id}:no stub"
        start = (route["points"][0]["x"], route["points"][0]["y"], route["points"][0]["z"])
        if start != stub or route.get("geometry_source") != "tee_stub":
            return False, f"{pipe.id}:start={start} stub={stub} src={route.get('geometry_source')}"
        for nid in g.nozzles:
            npt = nozzle_point(g, nid)
            if npt is not None and start == npt:
                return False, f"{pipe.id}:start matches nozzle {nid}"
        checked += 1
    ok = checked >= 1 and computed == pinned
    return ok, f"C03_branches={computed} C01_branch_routes={checked} pin_c03={pinned}"


def B09() -> tuple[bool, str]:
    """C01 line/valve/instrument/tie-in xlsx row counts pinned; columns match docs/exports.md."""
    import tempfile

    from openpyxl import load_workbook

    from threadforge.dexpi_public import load_pins
    from threadforge.exporters.xlsx import (
        INSTRUMENT_COLUMNS,
        LINE_COLUMNS,
        TIEIN_COLUMNS,
        VALVE_COLUMNS,
        export_lists_xlsx,
        list_row_counts,
    )
    from threadforge.ingest_dexpi import load_fixture

    g = load_fixture("C01V04-VER.EX01.xml")
    pinned = load_pins()["counts"]["C01V04-VER.EX01.xml"]["xlsx"]
    computed = list_row_counts(g)
    if computed != pinned:
        return False, f"counts={computed} pin={pinned}"
    docs = (ROOT / "docs" / "exports.md").read_text(encoding="utf-8")
    expect = {
        "lines": LINE_COLUMNS,
        "valves": VALVE_COLUMNS,
        "instruments": INSTRUMENT_COLUMNS,
        "tie_ins": TIEIN_COLUMNS,
    }
    missing_docs = [c for cols in expect.values() for c in cols if f"`{c}`" not in docs]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lists.xlsx"
        export_lists_xlsx(g, path)
        wb = load_workbook(path)
        sheet_rows: dict[str, int] = {}
        for sheet, cols in expect.items():
            ws = wb[sheet]
            header = [c.value for c in ws[1]]
            if header != cols:
                return False, f"{sheet} header={header} want={cols}"
            sheet_rows[sheet] = sum(
                1
                for row in ws.iter_rows(min_row=2)
                if any(c.value not in (None, "") for c in row)
            )
        if sheet_rows != pinned:
            return False, f"xlsx_rows={sheet_rows} pin={pinned}"
    ok = not missing_docs
    return ok, f"xlsx={sheet_rows} docs_missing={missing_docs or 'none'}"


def _b_unstarted(bid: str) -> Callable[[], tuple[bool, str]]:
    def _fn() -> tuple[bool, str]:
        ev_dir = ROOT / "artifacts" / "ci"
        matches = sorted(ev_dir.glob(f"{bid.lower()}*.json")) if ev_dir.is_dir() else []
        return False, (
            f"{bid} not in M0; M1–M7 not started; "
            f"evidence_files={len(matches)} (no remote/process PASS evidence)"
        )

    _fn.__name__ = bid
    return _fn


CHECKS = [
    ("A01", A01),
    ("A02", A02),
    ("A03", A03),
    ("A04", A04),
    ("A05", A05),
    ("A06", A06),
    ("A07", A07),
    ("A08", A08),
    ("A09", A09),
    ("A10", A10),
    ("A11", A11),
    ("A12", A12),
    ("A13", A13),
    ("A14", A14),
    ("A15", A15),
    ("A16", A16),
    ("A17", A17),
    ("A18", A18),
    ("A19", A19),
    ("A20", A20),
    ("A21", A21),
    ("A22", A22),
    ("A23", A23),
    ("A24", A24),
    ("A25", A25),
    ("A26", A26),
    ("A27", A27),
    ("A28", A28),
    ("A29", A29),
    ("A30", A30),
]

_B_IMPL: dict[str, Callable[[], tuple[bool, str]]] = {
    "B01": B01,
    "B02": B02,
    "B03": B03,
    "B05": B05,
    "B06": B06,
    "B07": B07,
    "B08": B08,
    "B09": B09,
}

B_CHECKS: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    (f"B{n:02d}", _B_IMPL[f"B{n:02d}"] if f"B{n:02d}" in _B_IMPL else _b_unstarted(f"B{n:02d}"))
    for n in range(1, 41)
]


def main() -> int:
    for aid, fn in CHECKS:
        _safe(aid, fn)
    for bid, fn in B_CHECKS:
        _safe(bid, fn)
    a_pass = sum(1 for aid, ok, _ in RESULTS if aid.startswith("A") and ok)
    b_pass = sum(1 for aid, ok, _ in RESULTS if aid.startswith("B") and ok)
    print(f"ACCEPTANCE: {a_pass}/30 PASS")
    print(f"ACCEPTANCE: {b_pass}/40 PASS")
    return 0 if a_pass == 30 and b_pass == 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
