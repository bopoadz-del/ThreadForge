"""Vendored DEXPI 1.3 TrainingTestCases helpers (offline; no network).

B05: official example P&IDs under ``fixtures/public/dexpi13/pids/`` with
sha256 + entity-count pins. C08 capability fixtures are excluded (not upstream XML).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from threadforge.graph import TopologyGraph

ROOT = Path(__file__).resolve().parents[2]
DEXPI13 = ROOT / "fixtures" / "public" / "dexpi13"
PINS_PATH = DEXPI13 / "pins.json"
KNOWN_DELTAS_PATH = DEXPI13 / "known_deltas.json"
PIDS_DIR = DEXPI13 / "pids"


def vendor_xmls() -> list[Path]:
    """Official TrainingTestCases example P&IDs (not C08 capability fixtures)."""
    if not PIDS_DIR.is_dir():
        return []
    return sorted(p for p in PIDS_DIR.glob("*.xml") if p.is_file())


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entity_counts(graph: TopologyGraph) -> dict[str, int]:
    """Computed per-file counts used by pins.json / B05."""
    return {
        "pipelines": len(graph.pipelines),
        "equipment": len(graph.equipment),
        "nozzles": len(graph.nozzles),
        "instruments": len(graph.instruments),
    }


def load_pins() -> dict[str, Any]:
    data = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "counts" not in data:
        raise ValueError(f"pins.json missing counts: {PINS_PATH}")
    return data


def load_known_deltas() -> dict[str, list[str]]:
    if not KNOWN_DELTAS_PATH.is_file():
        return {}
    data = json.loads(KNOWN_DELTAS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("known_deltas.json must be an object")
    out: dict[str, list[str]] = {}
    for name, deltas in data.items():
        if name.startswith("_"):
            continue
        if not isinstance(deltas, list) or not all(isinstance(x, str) for x in deltas):
            raise ValueError(f"known_deltas[{name!r}] must be a list of strings")
        out[str(name)] = [str(x) for x in deltas]
    return out


def file_known_deltas(filename: str) -> list[str]:
    return list(load_known_deltas().get(filename, []))
