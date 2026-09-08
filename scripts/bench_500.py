#!/usr/bin/env python3
"""Time ingest+route+PCF for a 500-line synthetic plant (B39)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def write_synthetic(path: Path, n: int = 500) -> Path:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<PlantModel Name="SYN-500" Units="m">',
        '<PlantInformation SchemaVersion="4.1.1"/>',
        '<Equipment ID="EQ-A" TagName="EQ-A"><Nozzle ID="NA" TagName="NA" X="0" Y="0" Z="5"/></Equipment>',
        '<Equipment ID="EQ-B" TagName="EQ-B"><Nozzle ID="NB" TagName="NB" X="20" Y="0" Z="5"/></Equipment>',
    ]
    for i in range(1, n + 1):
        y = (i % 50) * 2.0
        lid = f"PS-{i:04d}"
        n1 = f"N-{i:04d}A"
        n2 = f"N-{i:04d}B"
        parts.append(
            f'<Equipment ID="E-{i:04d}A" TagName="E-{i:04d}A">'
            f'<Nozzle ID="{n1}" TagName="{n1}" X="0" Y="{y}" Z="5"/></Equipment>'
        )
        parts.append(
            f'<Equipment ID="E-{i:04d}B" TagName="E-{i:04d}B">'
            f'<Nozzle ID="{n2}" TagName="{n2}" X="10" Y="{y}" Z="5"/></Equipment>'
        )
        parts.append(
            f'<PipingNetworkSegment ID="{lid}" TagName="L-{i:04d}" '
            f'NominalDiameter="6" LineNumber="L-{i:04d}">'
            f'<Connection FromID="{n1}" ToID="{n2}"/>'
            f"</PipingNetworkSegment>"
        )
    parts.append("</PlantModel>")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def main() -> int:
    out_json = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "bench.json"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    out_json.parent.mkdir(parents=True, exist_ok=True)
    xml = Path("/tmp/tf_syn_500.xml")
    write_synthetic(xml, n)
    from threadforge.generators import generate_pcf, generate_quantities
    from threadforge.ingest_dexpi import parse_dexpi_xml
    from threadforge.routing import ensure_routes

    t0 = time.perf_counter()
    g = parse_dexpi_xml(xml)
    ensure_routes(g)
    n_lines = len(g.pipelines)
    with_routes = sum(1 for lid in g.pipelines if g.routes.get(lid))
    dest = Path("/tmp/tf_syn_500_out")
    dest.mkdir(exist_ok=True)
    for lid in list(g.pipelines)[:n]:
        generate_pcf(g, lid, output_dir=dest)
    qty = generate_quantities(g)
    elapsed = time.perf_counter() - t0
    payload = {
        "n_lines": n_lines,
        "routes": with_routes,
        "qty_rows": len((qty.payload or {}).get("rows") or []),
        "duration_s": round(elapsed, 3),
        "limit_s": 120.0,
        "fixture": str(xml),
    }
    out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if n_lines == n and elapsed < 120.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
