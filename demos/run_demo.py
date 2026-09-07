#!/usr/bin/env python3
"""ThreadForge end-to-end demo (no network) - writes artefacts under output/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from threadforge import agent_tools as tools
from threadforge.generators import default_output_dir


def _banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _show(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def run() -> None:
    fixtures = ROOT / "fixtures"
    out = default_output_dir()
    tools.SESSION.output_dir = out

    _banner("1. INGEST DEXPI fixture (lite)")
    r = tools.ingest_dexpi()
    _show({k: r[k] for k in ("ok", "source", "summary", "maturity", "stages") if k in r})

    _banner("1b. INGEST rich fixture")
    rich = tools.ingest_dexpi(fixtures / "sample_pid_rich.xml")
    _show({
        "ok": rich["ok"],
        "plant": rich["summary"],
        "multi_sheet": rich.get("multi_sheet"),
        "sheets": rich["summary"].get("sheet_count"),
        "instruments": rich["summary"].get("equipment_count"),
    })
    # Re-load lite for rest of classic demo continuity
    tools.ingest_dexpi()

    _banner("2. QUERY graph - selected equipment 120-VEPR-2010")
    q = tools.query_graph(tag_id="120-VEPR-2010")
    _show(q)

    _banner("3. REVISE pipeline LINE-120-P-1001 (service change)")
    rev = tools.revise_pid(
        "pipeline",
        "LINE-120-P-1001",
        {"service": "PROCESS-REV", "metadata": {"revision": "A1"}},
    )
    _show({"change_id": rev["change_id"], "dirty": rev["dirty"], "stages": rev["stages"]})

    _banner("4. PIPELINE stages -> write PCF / ISO / GA under output/")
    tools.run_pipeline_stage("piping")
    tools.run_pipeline_stage("outputs")
    exported = tools.export_artefacts(out)
    pcf_files = list((out / "pcf").glob("*.pcf")) if (out / "pcf").exists() else []
    iso_files = list((out / "iso").glob("*.svg")) if (out / "iso").exists() else []
    ga_files = list((out / "ga").glob("*.svg")) if (out / "ga").exists() else []
    _show({
        "output_dir": str(out),
        "artefact_count": len(exported.get("artefacts", [])),
        "pcf_files": [str(p.name) for p in pcf_files],
        "iso_svg_files": [str(p.name) for p in iso_files],
        "ga_files": [str(p.name) for p in ga_files],
    })

    # Re-revise to dirty again after artefacts exist
    tools.revise_pid(
        "tag",
        "120-VEPR-2010",
        {"engineering": {"equipment_description": "VERTICAL SEPARATOR (REV)"}},
    )
    cas = tools.cascade_rerun()
    _banner("5. CASCADE re-run")
    _show({
        "ok": cas["ok"],
        "change_id": cas.get("change_id"),
        "regenerated_count": len(cas.get("regenerated", [])),
    })

    _banner("6. BUILD test packs + work packages")
    tp = tools.build_test_packs()
    _show({"test_pack_count": tp["count"], "packs": [{"id": p["id"], "tags": p["tags"][:6]} for p in tp["test_packs"]]})
    wp = tools.build_work_packages()
    _show({
        "wp_count": wp["count"],
        "wps": [
            {"id": w["id"], "discipline": w["discipline"], "volume_id": w["volume_id"], "n_tags": len(w["tags"])}
            for w in wp["work_packages"]
        ],
    })

    _banner("7. ATTACH schedule -> co-activity + look-ahead (discipline filter)")
    tools.attach_schedule(fixtures / "sample_schedule.json")
    co = tools.co_activity_check(export_report=True)
    _show({"flagged_count": co["flagged_count"], "volumes": co.get("volumes_involved"), "report": co.get("report_path")})
    la = tools.look_ahead(weeks=3, disciplines=["PIP", "INS", "ELE", "TEL"], export_csv=True)
    _show({
        "window": f"{la['from']} -> {la['to']}",
        "disciplines_filter": la.get("disciplines_filter"),
        "activity_count": la["activity_count"],
        "by_discipline": la["by_discipline"],
        "csv_path": la.get("csv_path"),
        "activities": [a["id"] for a in la["activities"]],
    })

    _banner("8. MATURITY check (IFC export gate)")
    mat = tools.maturity_check(required="IFC", action="export")
    _show(mat)

    _banner("9. DEXPI coverage WALL note")
    cov = tools.dexpi_coverage()
    _show({"supported": cov["supported_elements"][:8], "gap_count": len(cov["gaps"]), "wall": cov["wall"]})

    _banner("DEMO COMPLETE")
    print(f"Artefacts under: {out}")
    print("See WALLS.md for proprietary CAD / full DEXPI limits.")


if __name__ == "__main__":
    run()
