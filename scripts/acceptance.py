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
import time
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


def B10() -> tuple[bool, str]:
    """IFC-in obstacles; 4 lines route with zero AABB penetration (computed)."""
    from threadforge.exporters.ifc_in import (
        attach_ifc_obstacles,
        four_line_ifc_graph,
        load_ifc_obstacles,
        public_rack_path,
        route_ifc_penetrations,
    )
    from threadforge.routing import generate_routes_astar

    path = public_rack_path()
    obs = load_ifc_obstacles(path)
    if obs.get("wall"):
        return False, f"wall={obs['wall']}"
    if int(obs.get("structure_count") or 0) < 7 or int(obs.get("equipment_count") or 0) < 1:
        return False, f"structure={obs.get('structure_count')} equipment={obs.get('equipment_count')}"
    g = four_line_ifc_graph()
    attach_ifc_obstacles(g, path)
    generate_routes_astar(g, grid=0.5)
    routes = list(g.routes.values())
    if len(routes) != 4:
        return False, f"routes={len(routes)}"
    acc = [r.get("accuracy") for r in routes]
    if acc.count("astar") != 4:
        return False, f"accuracy={acc}"
    hits = route_ifc_penetrations(routes, list(obs["aabbs"]), skip_endpoints=True, samples=24)
    ok = hits == 0
    return ok, (
        f"ifc_products={len(obs['products'])} structure={obs['structure_count']} "
        f"equipment={obs['equipment_count']} routes=4 astar=4 penetrations={hits}"
    )


def B11() -> tuple[bool, str]:
    """Rack tiers: documented table; rich pin; A* Z order; no capsule overlap."""
    from threadforge.clash import clash_check, segment_distance
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.rack import (
        DEFAULT_TIER_Z,
        RICH_TIER_PIN,
        median_z_in_rack,
        rack_xy_aabb,
        rich_tier_assignment,
        three_service_rack_graph,
    )
    from threadforge.routing import generate_routes_astar

    docs = (ROOT / "docs" / "rack_tiers.md").read_text(encoding="utf-8")
    if not all(s in docs for s in ("`high`", "`mid`", "`low`", "PROCESS", "UTILITY", "DRAIN")):
        return False, "rack_tiers.md missing required service/tier rows"
    g = load_fixture("sample_pid_rich.xml")
    got = rich_tier_assignment(g)
    if got != RICH_TIER_PIN:
        return False, f"rich_tiers={got} pin={RICH_TIER_PIN}"
    generate_routes_astar(g)
    for lid, tier in RICH_TIER_PIN.items():
        if g.routes[lid].get("rack_tier") != tier:
            return False, f"{lid} rack_tier={g.routes[lid].get('rack_tier')} pin={tier}"
    rg = three_service_rack_graph()
    generate_routes_astar(rg, grid=0.5)
    xy = rack_xy_aabb(rg)
    if xy is None:
        return False, "no rack aabb"
    zp = median_z_in_rack(rg.routes["L-RACK-P"]["points"], xy)
    zu = median_z_in_rack(rg.routes["L-RACK-U"]["points"], xy)
    zd = median_z_in_rack(rg.routes["L-RACK-D"]["points"], xy)
    if zp is None or zu is None or zd is None or not (zp > zu > zd):
        return False, f"tier_z P={zp} U={zu} D={zd}"
    z_ok = (
        abs(zp - DEFAULT_TIER_Z["high"]) <= 1.0
        and abs(zu - DEFAULT_TIER_Z["mid"]) <= 1.0
        and abs(zd - DEFAULT_TIER_Z["low"]) <= 1.0
    )
    if not z_ok:
        return False, f"tier_z_off P={zp} U={zu} D={zd} expect={DEFAULT_TIER_Z}"
    hard = clash_check(rg, routes=list(rg.routes.values()))["hard_count"]
    best = 1e9
    ids = ["L-RACK-P", "L-RACK-U", "L-RACK-D"]
    for i in range(3):
        for j in range(i + 1, 3):
            p1 = [(p["x"], p["y"], p["z"]) for p in rg.routes[ids[i]]["points"]]
            p2 = [(p["x"], p["y"], p["z"]) for p in rg.routes[ids[j]]["points"]]
            for a, b in zip(p1, p1[1:]):
                for c, d in zip(p2, p2[1:]):
                    dist, _, _ = segment_distance(a, b, c, d)
                    best = min(best, dist)
    ok = hard == 0 and best > 0.05
    return ok, f"rich={got} zP={zp} zU={zu} zD={zd} hard={hard} min_sep={best:.4f}"


def B12() -> tuple[bool, str]:
    """MSS SP-58 kinematic types; pinned counts on the rich fixture."""
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import generate_routes_astar
    from threadforge.supports_mss import MSS_TYPE, support_types_kinematic, type_counts

    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    pinned = {
        "LINE-200-P-1001": {"anchor": 2, "guide": 1, "shoe": 0, "spring_hanger": 0},
        "LINE-200-P-1002": {"anchor": 2, "guide": 5, "shoe": 0, "spring_hanger": 1},
        "LINE-210-G-2001": {"anchor": 2, "guide": 2, "shoe": 0, "spring_hanger": 0},
        "LINE-200-D-1010": {"anchor": 2, "guide": 2, "shoe": 0, "spring_hanger": 0},
    }
    got: dict[str, dict[str, int]] = {}
    cited = True
    for lid in pinned:
        sup = g.routes[lid]["supports_mss"]
        got[lid] = type_counts(sup)
        if any(s.get("standard") != "MSS SP-58" or s.get("mss_sp58") not in MSS_TYPE.values() for s in sup):
            cited = False
    # Crafted kinematics (independent of A*).
    shoe = type_counts(support_types_kinematic([(0.0, 0.0, 5.0), (20.0, 0.0, 5.0)], '6"', insulated=True))
    spr = type_counts(support_types_kinematic([(0.0, 0.0, 0.0), (0.0, 0.0, 7.0)], '4"', insulated=False))
    rules_ok = shoe["anchor"] == 2 and shoe["shoe"] >= 1 and shoe["guide"] >= 1 and spr["spring_hanger"] >= 1
    ok = got == pinned and cited and rules_ok
    return ok, f"rich={got} cited={cited} shoe={shoe} spring={spr}"


def B13() -> tuple[bool, str]:
    """B31.3 319.4.1 screen; rich no_design_temp; 200°C line needs U-loop."""
    from threadforge.flexibility import (
        STATUS_NEEDS,
        STATUS_NO_TEMP,
        crafted_hot_line_graph,
        screen_graph,
        thermal_y_mm,
    )
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import generate_routes_astar
    from threadforge.tables import B31_3_319_4_1_K_SI, table_c1_epsilon_mm_per_m

    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    rich = screen_graph(g)
    if not rich or any(s["status"] != STATUS_NO_TEMP for s in rich.values()):
        return False, f"rich={ {k: v['status'] for k, v in rich.items()} }"
    hot = crafted_hot_line_graph(200.0, 10.0)
    scr = screen_graph(hot)["LINE-HOT-200C"]
    cite_ok = "319.4.1" in (scr.get("citation") or "") and "C-1" in (scr.get("citation") or "")
    loop = scr.get("u_loop") or {}
    y_ok = abs(float(scr["Y_mm"]) - thermal_y_mm(200.0, 10.0)) < 1e-6
    eps = table_c1_epsilon_mm_per_m(200.0)
    ratio_fail = scr["status"] == STATUS_NEEDS and (
        scr["ratio"] == "inf" or float(scr["ratio"]) > B31_3_319_4_1_K_SI
    )
    loop_ok = (
        loop.get("kind") == "u_loop"
        and float(loop.get("protrusion_m") or 0) > 0
        and loop.get("proposed_ratio") is not None
        and float(loop["proposed_ratio"]) <= B31_3_319_4_1_K_SI
        and "319.4.1" in (loop.get("formula") or "")
    )
    ok = cite_ok and y_ok and ratio_fail and loop_ok and len(rich) == 4
    return ok, (
        f"rich_status=no_design_temp n={len(rich)} hot={scr['status']} "
        f"Y={scr.get('Y_mm')} eps200={eps:.4f} loop_P={loop.get('protrusion_m')} "
        f"proposed_ratio={loop.get('proposed_ratio')} cite={cite_ok}"
    )


def B14() -> tuple[bool, str]:
    """Clash: structure + insulation OD + 600 mm access; rich+IFC hard 0; crafted ≥1 each."""
    from threadforge.clash import ACCESS_HEMISPHERE_M, ACCESS_RULE, clash_check
    from threadforge.exporters.ifc_in import attach_ifc_obstacles, public_rack_path
    from threadforge.graph import TopologyGraph
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.models import Equipment, Nozzle, Pipeline
    from threadforge.routing import generate_routes_astar

    if ACCESS_HEMISPHERE_M != 0.6 or "PNF0200" not in ACCESS_RULE:
        return False, f"access_rule={ACCESS_RULE} r={ACCESS_HEMISPHERE_M}"
    g = load_fixture("sample_pid_rich.xml")
    attach_ifc_obstacles(g, public_rack_path())
    generate_routes_astar(g)
    rich = clash_check(g)
    if rich["hard_count"] != 0:
        return False, f"rich+ifc hard={rich['hard_count']} {rich.get('hard_by_category')}"

    cg = TopologyGraph()

    def _line(
        lid: str,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        **meta: object,
    ) -> None:
        ea, eb = f"{lid}-A", f"{lid}-B"
        na, nb = f"{ea}-N", f"{eb}-N"
        cg.equipment[ea] = Equipment(id=ea, tag=ea, nozzles=[na])
        cg.equipment[eb] = Equipment(id=eb, tag=eb, nozzles=[nb])
        cg.nozzles[na] = Nozzle(id=na, tag="N", equipment_id=ea, x=a[0], y=a[1], z=a[2])
        cg.nozzles[nb] = Nozzle(id=nb, tag="N", equipment_id=eb, x=b[0], y=b[1], z=b[2])
        cg.pipelines[lid] = Pipeline(
            id=lid, line_number=lid, from_tag=na, to_tag=nb, nominal_bore='6"', metadata=dict(meta)
        )
        cg.routes[lid] = {
            "line_id": lid,
            "line_number": lid,
            "from": na,
            "to": nb,
            "nominal_bore": '6"',
            "geometry_source": "nozzle_xyz",
            "insulation_mm": meta.get("insulation_mm", 0),
            "points": [{"x": a[0], "y": a[1], "z": a[2]}, {"x": b[0], "y": b[1], "z": b[2]}],
        }

    _line("L-STR", (0.0, 0.0, 5.0), (10.0, 0.0, 5.0))
    cg.metadata["structure_aabbs"] = [(4.0, -1.0, 4.0, 6.0, 1.0, 6.0)]
    _line("L-INS-A", (0.0, 5.0, 2.0), (10.0, 5.0, 2.0), insulation_mm=50.0)
    _line("L-INS-B", (0.0, 5.22, 2.0), (10.0, 5.22, 2.0), insulation_mm=50.0)
    _line("L-ACC-V", (0.0, 10.0, 3.0), (4.0, 10.0, 3.0))
    _line("L-ACC-X", (2.0, 10.15, 3.1), (2.0, 12.0, 3.1))
    cg.metadata["access_valves"] = [{"id": "HV-1", "line_id": "L-ACC-V", "xyz": (2.0, 10.0, 3.0)}]
    crafted = clash_check(cg, routes=list(cg.routes.values()))
    by = crafted.get("hard_by_category") or {}
    ok = (
        rich["hard_count"] == 0
        and int(by.get("pipe_vs_structure") or 0) >= 1
        and int(by.get("insulation") or 0) >= 1
        and int(by.get("access") or 0) >= 1
    )
    return ok, f"rich_hard=0 crafted={by} access_m={ACCESS_HEMISPHERE_M}"


def B15() -> tuple[bool, str]:
    """Hypothesis properties: A* vs random AABB; segment_distance vs brute ±1 mm."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(ROOT / "tests" / "test_hypothesis_geom.py"),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # pytest -q summary like "2 passed in 1.23s"
    m = re.search(r"(\d+) passed", text)
    npass = int(m.group(1)) if m else 0
    failed = proc.returncode != 0
    ok = (not failed) and npass >= 2
    return ok, f"pytest_rc={proc.returncode} passed={npass} tail={text.strip().splitlines()[-1] if text.strip() else '-'}"


def B16() -> tuple[bool, str]:
    """Shop spools ≤12 m / ≤2 t / ISO 668 envelope; field welds; W- ids; pins."""
    from threadforge.generators import write_pcf_text
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.pcf_reader import parse_pcf
    from threadforge.routing import generate_routes_astar
    from threadforge.spooling import (
        ENVELOPE_CITE,
        SHOP_MAX_LENGTH_M,
        SHOP_MAX_MASS_KG,
        crafted_envelope_u,
        crafted_mass_24in,
        crafted_straight_30m,
        limits_ok,
    )
    from threadforge.tables import mass_per_m

    if SHOP_MAX_LENGTH_M != 12.0 or SHOP_MAX_MASS_KG != 2000.0:
        return False, f"limits L={SHOP_MAX_LENGTH_M} M={SHOP_MAX_MASS_KG}"
    if "ISO 668" not in ENVELOPE_CITE or "Table 1" not in ENVELOPE_CITE:
        return False, f"envelope_cite={ENVELOPE_CITE}"

    g30 = crafted_straight_30m()
    write_pcf_text(g30, "LINE-CRAFT-30M")
    r30 = g30.routes["LINE-CRAFT-30M"]["spools"]
    lens = [round(sp["length_m"], 6) for sp in r30["spools"]]
    text30 = write_pcf_text(g30, "LINE-CRAFT-30M")
    doc = parse_pcf(text30)
    spool_ids = {c.attrs.get("SPOOL-IDENTIFIER") for c in doc.components if c.attrs.get("SPOOL-IDENTIFIER")}
    weld_ids = [w["weld_id"] for w in r30["welds"]]
    c30 = (
        limits_ok(r30)
        and r30["spool_count"] == 3
        and lens == [12.0, 12.0, 6.0]
        and r30["field_weld_count"] == 2
        and weld_ids == ["W-CRAFT-30M-1", "W-CRAFT-30M-2"]
        and "S-CRAFT-30M-01" in text30
        and spool_ids >= {"S-CRAFT-30M-01", "S-CRAFT-30M-02", "S-CRAFT-30M-03"}
    )

    genv = crafted_envelope_u()
    write_pcf_text(genv, "LINE-CRAFT-ENV")
    renv = genv.routes["LINE-CRAFT-ENV"]["spools"]
    cenv = limits_ok(renv) and renv["spool_count"] == 2 and renv["field_weld_count"] == 1

    g24 = crafted_mass_24in()
    write_pcf_text(g24, "LINE-CRAFT-24")
    r24 = g24.routes["LINE-CRAFT-24"]["spools"]
    kg_m = mass_per_m('24"', "40")
    cmass = (
        limits_ok(r24)
        and r24["spool_count"] == 2
        and kg_m * 10.0 > 2000.0
        and all(sp["mass_kg"] <= 2000.0 + 1e-3 for sp in r24["spools"])
        and abs(kg_m - 255.425) < 0.01
    )

    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    got: dict[str, dict[str, int]] = {}
    for lid in g.pipelines:
        write_pcf_text(g, lid)
        rep = g.routes[lid]["spools"]
        if not limits_ok(rep):
            return False, f"rich oversize {lid}"
        got[lid] = {
            "spools": int(rep["spool_count"]),
            "welds": int(rep["weld_count"]),
            "field": int(rep["field_weld_count"]),
            "shop": int(rep["shop_weld_count"]),
        }
    pinned = {
        "LINE-200-D-1010": {"spools": 2, "welds": 1, "field": 1, "shop": 0},
        "LINE-200-P-1001": {"spools": 2, "welds": 7, "field": 1, "shop": 6},
        "LINE-200-P-1002": {"spools": 5, "welds": 12, "field": 4, "shop": 8},
        "LINE-210-G-2001": {"spools": 2, "welds": 5, "field": 1, "shop": 4},
    }
    ok = c30 and cenv and cmass and got == pinned
    return ok, f"craft30={lens} env={renv['spool_count']} mass24={r24['spool_count']} rich={got}"


def B17() -> tuple[bool, str]:
    """Iso per spool sheet: n/N, welds, cuts, BOM; dim_sum = spool length."""
    from threadforge.generators import generate_isometric, write_pcf_text
    from threadforge.iso_sheets import dim_sum_mm_from_svg, sheet_iso_svg
    from threadforge.spooling import crafted_straight_30m

    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    art = generate_isometric(g, "LINE-CRAFT-30M")
    sheets = art.payload.get("sheets") or []
    if len(sheets) != 3:
        return False, f"sheets={len(sheets)}"
    ok_dims = True
    for i, sh in enumerate(sheets, start=1):
        want = int(round(float(sh["length_m"]) * 1000))
        if sh.get("dim_sum_mm") != want or sh.get("sheet") != i or sh.get("n_of") != 3:
            ok_dims = False
        if not sh.get("cut_lengths_m") or not sh.get("bom"):
            ok_dims = False
        svg = sheet_iso_svg(
            g.routes["LINE-CRAFT-30M"]["spools"]["spools"][i - 1],
            line_number="CRAFT-30M",
            sheet_n=i,
            sheet_n_of=3,
            welds=[
                w
                for w in g.routes["LINE-CRAFT-30M"]["spools"]["welds"]
                if w["spool_id"] == sh["spool_id"]
            ],
            bom=sh.get("bom"),
        )
        if dim_sum_mm_from_svg(svg) != want or f"sheet {i}/3" not in svg:
            ok_dims = False
        if "NOT FOR CONSTRUCTION" not in svg or sh["spool_id"] not in svg:
            ok_dims = False
        if i < 3 and f"W-CRAFT-30M-{i}" not in svg:
            ok_dims = False
    ok = ok_dims and art.payload.get("sheet_count") == 3 and art.payload.get("iso_angle_deg") == 30
    return ok, f"sheets={len(sheets)} dims={ok_dims} n_of={sheets[0].get('n_of')}"


def B18() -> tuple[bool, str]:
    """Iso + GA PDF; page count = sheet count; pypdf has line + NFC."""
    from threadforge.exporters.pdf import NFC, export_ga_pdf, export_iso_pdf, extract_pdf_text, pdf_page_count
    from threadforge.generators import generate_isometric, write_pcf_text
    from threadforge.spooling import crafted_straight_30m

    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    n_sheets = int((generate_isometric(g, "LINE-CRAFT-30M").payload or {}).get("sheet_count") or 0)
    with tempfile.TemporaryDirectory() as td:
        iso_p = Path(td) / "iso.pdf"
        ga_p = Path(td) / "ga.pdf"
        export_iso_pdf(g, "LINE-CRAFT-30M", iso_p)
        export_ga_pdf(g, ga_p)
        iso_pages = pdf_page_count(iso_p)
        ga_pages = pdf_page_count(ga_p)
        iso_txt = extract_pdf_text(iso_p)
        ga_txt = extract_pdf_text(ga_p)
    ok = (
        iso_pages == n_sheets == 3
        and ga_pages == 1
        and "CRAFT-30M" in iso_txt
        and "CRAFT-30M" in ga_txt
        and NFC in iso_txt
        and NFC in ga_txt
    )
    return ok, f"iso_pages={iso_pages} sheets={n_sheets} ga_pages={ga_pages} nfc=iso+ga"


def B19() -> tuple[bool, str]:
    """IFC4 validate schema+express 0 errors; axis ±0.5%; IfcRelConnectsPorts."""
    try:
        import ifcopenshell
    except ImportError:
        return False, "ifcopenshell missing"
    from threadforge.exporters.ifc import (
        axis_length_m,
        export_ifc4,
        route_length_m,
        unique_port_pairs,
        validate_ifc4,
    )
    from threadforge.generators import write_pcf_text
    from threadforge.spooling import crafted_straight_30m

    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "m.ifc"
        art = export_ifc4(g, path)
        val = validate_ifc4(path, express_rules=True)
        model = ifcopenshell.open(str(path))
        axis = axis_length_m(model)
        route = route_length_m(list(g.routes.values()))
        segs = model.by_type("IfcPipeSegment")
        pairs = unique_port_pairs(model)
    rel_ok = route > 0 and abs(axis - route) / route <= 0.005
    ports_ok = len(segs) >= 2 and len(pairs) == len(segs) - 1
    ok = val["n_errors"] == 0 and rel_ok and ports_ok
    return ok, (
        f"errors={val['n_errors']} axis={axis:.6f} route={route:.6f} "
        f"pairs={len(pairs)} segs={len(segs)} payload_links={art.payload.get('port_links')}"
    )


def B20() -> tuple[bool, str]:
    """Weld map + 5% RT B31.3 341.4.1; csv/xlsx; counts == B16."""
    import csv

    from openpyxl import load_workbook

    from threadforge.generators import write_pcf_text
    from threadforge.spooling import crafted_straight_30m
    from threadforge.tables import B31_3_341_4_1_CITE, B31_3_341_4_1_NORMAL_RT_PCT
    from threadforge.weld_ndt import export_weld_ndt, n_rt_required

    if B31_3_341_4_1_NORMAL_RT_PCT != 5.0 or "341.4.1" not in B31_3_341_4_1_CITE:
        return False, f"pct={B31_3_341_4_1_NORMAL_RT_PCT} cite={B31_3_341_4_1_CITE}"
    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    b16 = int(g.routes["LINE-CRAFT-30M"]["spools"]["weld_count"])
    with tempfile.TemporaryDirectory() as td:
        art = export_weld_ndt(g, Path(td))
        p = art.payload or {}
        csv_p = Path(td) / "weld" / "weld_ndt.csv"
        xlsx_p = Path(td) / "weld" / "weld_ndt.xlsx"
        with csv_p.open(encoding="utf-8") as fh:
            csv_n = sum(1 for _ in csv.DictReader(fh))
        wb = load_workbook(xlsx_p)
        xlsx_n = wb["weld_ndt"].max_row - 1
    ok = (
        p.get("weld_count") == b16 == 2
        and p.get("reconcile") is True
        and p.get("rt_selected") == n_rt_required(2)
        and csv_n == b16
        and xlsx_n == b16
        and "341.4.1" in (p.get("citation") or "")
    )
    return ok, f"b16={b16} map={p.get('weld_count')} rt={p.get('rt_selected')} csv={csv_n} xlsx={xlsx_n}"


def B21() -> tuple[bool, str]:
    """MTO per spool/line/IWP/WP; three-level totals ±0.1 %."""
    from threadforge.generators import build_work_packages, write_pcf_text
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.mto import RECONCILE_TOL, build_mto
    from threadforge.routing import generate_routes_astar
    from threadforge.spooling import crafted_straight_30m

    g30 = crafted_straight_30m()
    write_pcf_text(g30, "LINE-CRAFT-30M")
    p30 = build_mto(g30)
    rec30 = p30["reconcile"]["pipe_m"]
    craft_ok = (
        p30["ok"]
        and abs(rec30["spool"] - 30.0) < 1e-6
        and rec30["spool_vs_line"] <= RECONCILE_TOL
        and rec30["line_vs_iwp"] <= RECONCILE_TOL
        and rec30["line_vs_wp"] <= RECONCILE_TOL
        and len(p30["per_spool"]) == 3
    )
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    build_work_packages(g)
    for lid in g.pipelines:
        write_pcf_text(g, lid)
    pr = build_mto(g)
    rec = pr["reconcile"]
    need = {"pipe_m", "pipe_kg", "fittings_count", "flanges", "bolts", "gaskets", "supports", "paint_m2", "insulation_m2"}
    keys_ok = need.issubset(pr["per_spool"][0]) and need.issubset(pr["per_line"][0])
    rich_ok = (
        pr["ok"]
        and keys_ok
        and rec["pipe_m"]["spool_vs_line"] <= RECONCILE_TOL
        and rec["pipe_m"]["line_vs_iwp"] <= RECONCILE_TOL
        and rec["pipe_kg"]["line_vs_wp"] <= RECONCILE_TOL
    )
    ok = craft_ok and rich_ok
    return ok, (
        f"craft_m={rec30['spool']} rich_ok={rich_ok} "
        f"s_vs_l={rec['pipe_m']['spool_vs_line']:.6f} l_vs_iwp={rec['pipe_m']['line_vs_iwp']:.6f}"
    )


def B22() -> tuple[bool, str]:
    """Hydrotest packs: B31.3 345.4.2 + B16.5 P-T cap; C01 pin; vents/drains."""
    from threadforge.hydrotest import C01_HYDRO_PIN, build_hydrotest_packs, high_low_points
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.tables import (
        B16_5_PT_CITE,
        B31_3_345_4_2_CITE,
        b16_5_pt_rating_bar,
        b31_3_345_4_2_test_pressure,
        infer_flange_class,
    )

    calc60 = b31_3_345_4_2_test_pressure(60.0, 100.0, 21.0)
    calc30 = b31_3_345_4_2_test_pressure(30.0, 100.0, 21.0)
    hot = b31_3_345_4_2_test_pressure(10.0, 316.0, 21.0)
    formula_ok = (
        infer_flange_class(60.0, 100.0) == 400
        and abs(float(calc60["P_T_uncapped_barg"]) - 90.0) < 1e-6
        and abs(float(calc60["test_pressure_barg"]) - 68.1) < 1e-6
        and calc60["capped"] is True
        and abs(b16_5_pt_rating_bar(400, 21.0) - 68.1) < 1e-6
        and infer_flange_class(30.0, 100.0) == 300
        and abs(float(calc30["test_pressure_barg"]) - 45.0) < 1e-6
        and calc30["capped"] is False
        and float(hot["St_over_S"]) > 1.0
        and "345.4.2" in B31_3_345_4_2_CITE
        and "2-1.1" in B16_5_PT_CITE
    )
    profile = [(0.0, 0.0, 5.0), (6.0, 0.0, 9.0), (12.0, 0.0, 3.0)]
    ext = high_low_points(profile)
    geom_ok = {v["z"] for v in ext["vents"]} == {9.0} and {d["z"] for d in ext["drains"]} == {3.0}

    g = load_fixture("C01V04-VER.EX01.xml")
    packs = build_hydrotest_packs(g)
    by = {p.system_id: p for p in packs}
    if set(by) != set(C01_HYDRO_PIN["system_ids"]) or len(packs) != C01_HYDRO_PIN["pack_count"]:
        return False, f"packs={sorted(by)} n={len(packs)}"
    mismatches: list[str] = []
    for sid, pin in C01_HYDRO_PIN.items():
        if sid in {"pack_count", "system_ids"}:
            continue
        if not isinstance(pin, dict):
            continue
        p = by[sid]
        m = p.metadata or {}
        if abs(float(m.get("test_pressure_barg") or -1) - float(pin["test_pressure_barg"])) > 1e-6:
            mismatches.append(f"{sid}:Pt={m.get('test_pressure_barg')}")
        if int(m.get("flange_class") or 0) != int(pin["flange_class"]):
            mismatches.append(f"{sid}:class={m.get('flange_class')}")
        if m.get("test_medium") != pin["test_medium"]:
            mismatches.append(f"{sid}:medium={m.get('test_medium')}")
        if set(pin["vents_z"]) - {float(v["z"]) for v in (m.get("vents") or [])}:
            mismatches.append(f"{sid}:vents")
        if set(pin["drains_z"]) - {float(d["z"]) for d in (m.get("drains") or [])}:
            mismatches.append(f"{sid}:drains")
        if pin.get("capped") is not None and bool(m.get("capped")) != bool(pin["capped"]):
            mismatches.append(f"{sid}:capped")
    blinds = set(by["SYS-MNc"].metadata.get("boundary_stops") or [])
    bound_ok = {"BlindFlange-1", "BlindFlange-2"} <= blinds
    ok = formula_ok and geom_ok and bound_ok and not mismatches
    return ok, (
        f"c01_packs={len(packs)} MNb_Pt={by['SYS-MNb'].metadata.get('test_pressure_barg')} "
        f"class400={calc60['flange_class']} cap={calc60['flange_rating_barg']} "
        f"hot_StS={hot['St_over_S']} blinds={bound_ok} mismatches={mismatches or 'none'}"
    )


def B23() -> tuple[bool, str]:
    """Spec-break validation; crafted 150# into 300# is spec_break_violation."""
    from threadforge.spec_break import crafted_150_into_300, validate_spec_breaks

    crafted = validate_spec_breaks(crafted_150_into_300())
    rating_hits = [
        v
        for v in crafted["spec_break_violations"]
        if v.get("kind") == "spec_break_violation"
        and any("150" in r and "300" in r for r in v.get("reasons") or [])
    ]
    ok = crafted["violation_count"] >= 1 and bool(rating_hits)
    return ok, (
        f"crafted_violations={crafted['violation_count']} "
        f"rating_150_300={len(rating_hits)} kind=spec_break_violation"
    )


def B24() -> tuple[bool, str]:
    """IWP release constraints; look-ahead lists only released IWPs."""
    from threadforge.iwp_release import IWP_RELEASE_PIN, apply_iwp_release, crafted_release_graph
    from threadforge.schedule_4d import Schedule4D

    g = crafted_release_graph()
    summary = apply_iwp_release(g)
    pin_ok = (
        summary["released"] == IWP_RELEASE_PIN["released"]
        and summary["blocked"] == IWP_RELEASE_PIN["blocked"]
        and summary["released_count"] == 1
        and summary["iwp_count"] == 5
    )
    sch = Schedule4D(g)
    sch.set_schedule_date("2027-03-03")
    la = sch.look_ahead(weeks=3, from_date="2027-03-03", released_only=True)
    ids = [w["id"] for w in la["work_packages"]]
    ok = pin_ok and ids == ["IWP-REL-1"] and all(w.get("release_ready") for w in la["work_packages"])
    return ok, f"released={summary['released']} look_ahead={ids} pin_ok={pin_ok}"


def B25() -> tuple[bool, str]:
    """XER TASK/TASKPRED + MSPDI (vendored XSD); reparsed tasks == IWPs."""
    from threadforge.exporters.schedule_io import (
        export_mspdi,
        export_xer,
        parse_mspdi,
        parse_xer,
        validate_mspdi,
    )
    from threadforge.iwp_release import apply_iwp_release, crafted_release_graph
    from threadforge.schedule_4d import Schedule4D

    g = crafted_release_graph()
    apply_iwp_release(g)
    sch = Schedule4D(g)
    la = sch.look_ahead(weeks=3, from_date="2027-03-03", released_only=False)
    iwp_n = sum(1 for w in la["work_packages"] if w.get("wp_type") == "IWP")
    with tempfile.TemporaryDirectory() as td:
        xer_p = Path(td) / "la.xer"
        xml_p = Path(td) / "la.xml"
        export_xer(la, xer_p)
        export_mspdi(la, xml_p)
        xer = parse_xer(xer_p)
        msp = parse_mspdi(xml_p)
        val = validate_mspdi(xml_p)
        text = xer_p.read_text(encoding="utf-8")
    tables = set(xer)
    ok = (
        iwp_n == 5
        and len(xer.get("TASK") or []) == iwp_n
        and msp["task_count"] == iwp_n
        and val["ok"] is True
        and val["n_errors"] == 0
        and val["engine"] == "xmlschema"
        and "%T\tTASK" in text
        and "%T\tTASKPRED" in text
        and "TASKPRED" in tables
    )
    return ok, (
        f"iwps={iwp_n} xer_tasks={len(xer.get('TASK') or [])} "
        f"mspdi_tasks={msp['task_count']} xsd_errors={val['n_errors']} tables={sorted(tables)}"
    )


def B26() -> tuple[bool, str]:
    """4D co-activity + craft + crane/laydown; pinned on sample_schedule.json."""
    from threadforge.generators import build_work_packages
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.schedule_4d import SAMPLE_4D_PIN, Schedule4D

    g = load_fixture()
    build_work_packages(g)
    sch = Schedule4D(g)
    sch.load_json(ROOT / "fixtures" / "sample_schedule.json")
    sch.attach_to_work_packages()
    by = sch.conflicts_by_day()
    pin_days_ok = all(by["days"].get(d) == SAMPLE_4D_PIN["days"][d] for d in SAMPLE_4D_PIN["days"])
    ok = (
        by["hard_count"] == SAMPLE_4D_PIN["hard_count"]
        and by["soft_count"] == SAMPLE_4D_PIN["soft_count"]
        and by["craft_count"] == SAMPLE_4D_PIN["craft_count"]
        and by["crane_count"] == SAMPLE_4D_PIN["crane_count"]
        and by["laydown_count"] == SAMPLE_4D_PIN["laydown_count"]
        and pin_days_ok
        and {"VOL-CRANE", "VOL-LAYDOWN"} <= set(sch.zones)
    )
    return ok, (
        f"hard={by['hard_count']} soft={by['soft_count']} craft={by['craft_count']} "
        f"crane={by['crane_count']} laydown={by['laydown_count']} days_pin={pin_days_ok}"
    )


def B27() -> tuple[bool, str]:
    """Revise one line → dirty set exact; untouched hashes identical for all 12 kinds."""
    from threadforge.cascade import CASCADE_KINDS_12, CascadeEngine
    from threadforge.ingest_dexpi import load_fixture
    from threadforge.routing import generate_routes_astar

    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    lids = sorted(g.pipelines)
    if len(lids) < 2:
        return False, "need ≥2 lines"
    a, b = lids[0], lids[1]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        eng = CascadeEngine(g)
        hashes: dict[str, str] = {}
        for lid in (a, b):
            for kind in CASCADE_KINDS_12:
                art = eng.write_kind_file(kind, lid, root)
                if not art.path:
                    return False, f"no path {kind.value}/{lid}"
                hashes[art.id] = _sha(Path(art.path))
        dirty_want = sorted(f"{k.value}-{a}" for k in CASCADE_KINDS_12)
        g.revise_pipeline(a, {"service": "PROCESS-REV"})
        event = eng.record_change("pipeline", a, "revise", {"service": "PROCESS-REV"})
        dirty = eng.last_dirty
        got_ids = sorted(dirty.artefact_ids) if dirty else []
        kinds_got = sorted(k.value for k in (dirty.artefact_kinds if dirty else []))
        kinds_want = sorted(k.value for k in CASCADE_KINDS_12)
        if got_ids != dirty_want or kinds_got != kinds_want:
            return False, f"dirty_ids={got_ids} want={dirty_want} kinds={kinds_got}"
        unchanged = []
        for kind in CASCADE_KINDS_12:
            bid = f"{kind.value}-{b}"
            art = eng.artefacts[bid]
            new_h = _sha(Path(art.path)) if art.path else ""
            if new_h != hashes[bid]:
                return False, f"hash drift {bid}"
            if art.status == "dirty":
                return False, f"untouched marked dirty {bid}"
            unchanged.append(kind.value)
        ok = event is not None and len(unchanged) == 12
        return ok, f"dirty={len(got_ids)} kinds=12 untouched_hash_ok={unchanged}"


def B28() -> tuple[bool, str]:
    """FEED→DD→IFC from data gates; IFC refuses unless all six are green."""
    from threadforge.maturity import (
        crafted_feed_graph,
        crafted_ifc_ready_graph,
        issue_ifc,
        ladder_from_gates,
    )

    ready = issue_ifc(crafted_ifc_ready_graph())
    feed = issue_ifc(crafted_feed_graph())
    dd_gates = {
        "fabricated_count": 0,
        "unmatched_opc_count": 0,
        "spec_break_violations": 0,
        "clash_hard": 0,
        "flex_screen_pass": False,
        "design_pressure_present": True,
    }
    ok = (
        ready["allowed"] is True
        and ready["ladder"] == "IFC"
        and ready["reasons"]["fabricated_count"] == 0
        and ready["reasons"]["unmatched_opc_count"] == 0
        and ready["reasons"]["spec_break_violations"] == 0
        and ready["reasons"]["clash_hard"] == 0
        and ready["reasons"]["flex_screen_pass"] is True
        and ready["reasons"]["design_pressure_present"] is True
        and feed["allowed"] is False
        and feed["ladder"] == "FEED"
        and ladder_from_gates(dd_gates) == "DD"
        and "Refused" in (feed["message"] or "")
    )
    return ok, (
        f"ifc_allowed={ready['allowed']} feed_allowed={feed['allowed']} "
        f"feed_ladder={feed['ladder']} dd={ladder_from_gates(dd_gates)} "
        f"failed={feed.get('failed')}"
    )


def B29() -> tuple[bool, str]:
    """Alembic head identical on SQLite and Postgres (revision + tables)."""
    from threadforge.persist import REQUIRED_TABLES, SCHEMA_REVISION, SCHEMA_VERSION, migrate_both

    with tempfile.TemporaryDirectory() as td:
        both = migrate_both(Path(td) / "reg.db")
    sq, pg = both["sqlite"], both["postgres"]
    missing_sq = [t for t in REQUIRED_TABLES if t not in sq["tables"]]
    missing_pg = [t for t in REQUIRED_TABLES if t not in pg["tables"]]
    ok = (
        sq["revision"] == pg["revision"] == SCHEMA_REVISION
        and sq["schema_version"] == pg["schema_version"] == SCHEMA_VERSION
        and not missing_sq
        and not missing_pg
    )
    return ok, (
        f"rev={sq['revision']}/{pg['revision']} ver={sq['schema_version']}/{pg['schema_version']} "
        f"missing_sq={missing_sq or 'none'} missing_pg={missing_pg or 'none'}"
    )


def B30() -> tuple[bool, str]:
    """3 roles, hashed keys (not plaintext), append-only audit ledger."""
    from threadforge.persist import (
        ROLES,
        audit_mutation_blocked,
        migrate_both,
        new_key_hash,
        seed_hashed_keys,
        sqlite_url,
        verify_api_key,
    )
    from threadforge.server import create_app

    token = "secret-engineer-token"
    stored = new_key_hash(token)
    hash_ok = token not in stored and verify_api_key(token, stored)
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "reg.db"
        both = migrate_both(db)
        url = sqlite_url(db)
        hashes = seed_hashed_keys(
            url,
            [
                ("admin", "admin", "adm-x"),
                ("engineer", "write", "eng-x"),
                ("reviewer", "read", "rev-x"),
            ],
        )
        blocked = audit_mutation_blocked(url)
        os.environ["TF_DATA"] = str(Path(td) / "data")
        os.environ["TF_API_TOKENS"] = "admin:adm-x:admin,engineer:eng-x:write,reviewer:rev-x:read"
        os.environ.pop("TF_DATABASE_URL", None)
        from fastapi.testclient import TestClient

        from threadforge.guards import reset_rate_limits

        reset_rate_limits()
        client = TestClient(create_app())
        rev = client.post("/jobs", headers={"Authorization": "Bearer rev-x"}, json={"fixture": "sample_pid.xml"})
        eng = client.post("/jobs", headers={"Authorization": "Bearer eng-x"}, json={"fixture": "sample_pid.xml"})
    ok = (
        hash_ok
        and set(ROLES) == {"admin", "engineer", "reviewer"}
        and all(t not in h for h in hashes for t in ("adm-x", "eng-x", "rev-x"))
        and blocked["update"]
        and blocked["delete"]
        and rev.status_code == 403
        and eng.status_code == 202
        and both["postgres"]["revision"] == both["sqlite"]["revision"]
    )
    return ok, (
        f"roles={list(ROLES)} hashed={hash_ok} audit_blocked={blocked} "
        f"reviewer={rev.status_code} engineer={eng.status_code}"
    )


def B31() -> tuple[bool, str]:
    """GET artefact ETag + If-None-Match 304; sha256 matches body."""
    from fastapi.testclient import TestClient

    from threadforge.guards import reset_rate_limits
    from threadforge.server import create_app

    reset_rate_limits()
    with tempfile.TemporaryDirectory() as td:
        os.environ["TF_DATA"] = td
        os.environ["TF_API_TOKENS"] = "engineer:eng-token:write"
        os.environ.pop("TF_DATABASE_URL", None)
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer eng-token"}
        created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid_rich.xml"})
        if created.status_code != 202:
            return False, f"create={created.status_code}"
        job_id = created.json()["id"]
        state = ""
        for _ in range(200):
            body = client.get(f"/jobs/{job_id}", headers=headers).json()
            state = str(body.get("state") or "")
            if state in {"done", "error"}:
                break
            time.sleep(0.1)
        first = client.get(f"/jobs/{job_id}/artefacts/pcf", headers=headers)
        digest = first.headers.get("x-content-sha256") or ""
        etag = first.headers.get("etag") or ""
        body_sha = hashlib.sha256(first.content).hexdigest() if first.content else ""
        second = client.get(
            f"/jobs/{job_id}/artefacts/pcf",
            headers={**headers, "If-None-Match": etag},
        )
    ok = (
        state == "done"
        and first.status_code == 200
        and second.status_code == 304
        and digest == body_sha
        and etag.strip('"') == digest
        and len(digest) == 64
    )
    return ok, f"state={state} get={first.status_code} inm={second.status_code} sha_match={digest == body_sha}"


def B32() -> tuple[bool, str]:
    """SSE job events: queued then running/done on text/event-stream."""
    from fastapi.testclient import TestClient

    from threadforge.guards import reset_rate_limits
    from threadforge.server import create_app

    reset_rate_limits()
    with tempfile.TemporaryDirectory() as td:
        os.environ["TF_DATA"] = td
        os.environ["TF_API_TOKENS"] = "engineer:eng-token:write"
        os.environ.pop("TF_DATABASE_URL", None)
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer eng-token"}
        created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid.xml"})
        job_id = created.json().get("id")
        ctype = ""
        text = ""
        with client.stream("GET", f"/jobs/{job_id}/events", headers=headers) as resp:
            ctype = resp.headers.get("content-type") or ""
            text = "".join(resp.iter_text())
    names = [line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("event:")]
    ok = (
        created.status_code == 202
        and ctype.startswith("text/event-stream")
        and "queued" in names
        and ("done" in names or "error" in names)
    )
    return ok, f"ctype={ctype.split(';')[0]} events={names}"


def B33() -> tuple[bool, str]:
    """MCP resource threadforge://job/{id}/{kind} sha256 == HTTP artefact GET."""
    from fastapi.testclient import TestClient

    from threadforge.guards import reset_rate_limits
    from threadforge.mcp_server import read_resource, resource_uri
    from threadforge.server import create_app

    reset_rate_limits()
    with tempfile.TemporaryDirectory() as td:
        os.environ["TF_DATA"] = td
        os.environ["TF_API_TOKENS"] = "engineer:eng-token:write"
        os.environ.pop("TF_DATABASE_URL", None)
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer eng-token"}
        created = client.post("/jobs", headers=headers, json={"fixture": "sample_pid_rich.xml"})
        job_id = created.json()["id"]
        for _ in range(200):
            if client.get(f"/jobs/{job_id}", headers=headers).json().get("state") == "done":
                break
            time.sleep(0.1)
        http = client.get(f"/jobs/{job_id}/artefacts/pcf", headers=headers)
        uri = resource_uri(job_id, "pcf")
        mcp = read_resource(uri)
    ok = (
        http.status_code == 200
        and uri == f"threadforge://job/{job_id}/pcf"
        and mcp["sha256"] == http.headers.get("x-content-sha256")
        and mcp["blob"] == http.content
        and mcp["sha256"] == hashlib.sha256(http.content).hexdigest()
    )
    return ok, f"uri={uri} http={http.headers.get('x-content-sha256')} mcp={mcp.get('sha256')}"


def B34() -> tuple[bool, str]:
    """Upload oversize 413, XML-bomb 400, rate-limit 429."""
    from fastapi.testclient import TestClient

    from threadforge.guards import MAX_UPLOAD_BYTES, reset_rate_limits
    from threadforge.ingest_dexpi import parse_dexpi_xml
    from threadforge.server import create_app

    bomb = (
        b'<?xml version="1.0"?>\n<!DOCTYPE lolz [\n'
        b'<!ENTITY lol "lol">\n<!ENTITY lol2 "&lol;&lol;">\n]>\n<lolz>&lol2;</lolz>'
    )
    bomb_status = 0
    try:
        parse_dexpi_xml(bomb)
    except Exception as exc:  # noqa: BLE001
        bomb_status = int(getattr(exc, "status", 0) or 0)
    reset_rate_limits()
    with tempfile.TemporaryDirectory() as td:
        os.environ["TF_DATA"] = td
        os.environ["TF_API_TOKENS"] = "engineer:eng-token:write"
        os.environ.pop("TF_DATABASE_URL", None)
        client = TestClient(create_app())
        headers = {"Authorization": "Bearer eng-token"}
        big = client.post("/upload", headers=headers, content=b"x" * (MAX_UPLOAD_BYTES + 8))
        bomb_http = client.post("/upload", headers=headers, content=bomb)
        codes = [client.get("/tools", headers=headers).status_code for _ in range(25)]
    ok = (
        bomb_status == 400
        and big.status_code == 413
        and bomb_http.status_code == 400
        and 429 in codes
    )
    return ok, (
        f"bomb_parse={bomb_status} upload_big={big.status_code} "
        f"upload_bomb={bomb_http.status_code} tools_codes={sorted(set(codes))}"
    )


def B35() -> tuple[bool, str]:
    """Two OS processes export identical sha256 maps."""
    script = ROOT / "scripts" / "cross_process_export.py"
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a"
        b = Path(td) / "b"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        r1 = subprocess.run(
            [sys.executable, str(script), str(a)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        r2 = subprocess.run(
            [sys.executable, str(script), str(b)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        if r1.returncode != 0 or r2.returncode != 0:
            return False, f"rc={r1.returncode}/{r2.returncode} e1={r1.stderr[-200:]} e2={r2.stderr[-200:]}"
        h1 = json.loads(r1.stdout.strip().splitlines()[-1])
        h2 = json.loads(r2.stdout.strip().splitlines()[-1])
    common = set(h1) & set(h2)
    mismatches = [k for k in sorted(common) if h1[k] != h2[k]]
    ok = bool(common) and not mismatches and len(h1) == len(h2)
    return ok, f"files={len(common)} mismatches={mismatches[:4] or 'none'}"


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
    "B10": B10,
    "B11": B11,
    "B12": B12,
    "B13": B13,
    "B14": B14,
    "B15": B15,
    "B16": B16,
    "B17": B17,
    "B18": B18,
    "B19": B19,
    "B20": B20,
    "B21": B21,
    "B22": B22,
    "B23": B23,
    "B24": B24,
    "B25": B25,
    "B26": B26,
    "B27": B27,
    "B28": B28,
    "B29": B29,
    "B30": B30,
    "B31": B31,
    "B32": B32,
    "B33": B33,
    "B34": B34,
    "B35": B35,
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
