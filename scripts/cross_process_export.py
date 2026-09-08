#!/usr/bin/env python3
"""Export artefacts in an isolated process (B35 cross-process determinism)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: cross_process_export.py OUT_DIR [FIXTURE]", file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    fixture = sys.argv[2] if len(sys.argv) > 2 else "sample_pid_rich.xml"
    out.mkdir(parents=True, exist_ok=True)
    from threadforge import agent_tools

    agent_tools.SESSION.graph = None
    agent_tools.SESSION.job = None
    agent_tools.SESSION.cascade = None
    agent_tools.SESSION.schedule = None
    agent_tools.ingest_dexpi(path=fixture)
    agent_tools.export_artefacts(output_dir=str(out))
    hashes: dict[str, str] = {}
    for fp in sorted(out.rglob("*")):
        if fp.is_file() and fp.name != "registry.db":
            hashes[str(fp.relative_to(out)).replace("\\", "/")] = hashlib.sha256(fp.read_bytes()).hexdigest()
    print(json.dumps(hashes, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
