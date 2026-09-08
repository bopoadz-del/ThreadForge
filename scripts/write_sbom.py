#!/usr/bin/env python3
"""Write a CycloneDX JSON SBOM from the installed environment (B38)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "sbom.cdx.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "cyclonedx_py",
        "environment",
        "-o",
        str(dest),
        "--of",
        "JSON",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        # fallback module name
        cmd[2] = "cyclonedx_bom"
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    data = json.loads(dest.read_text(encoding="utf-8"))
    comps = data.get("components") or []
    print(json.dumps({"bomFormat": data.get("bomFormat"), "n_components": len(comps), "path": str(dest)}))
    return 0 if data.get("bomFormat") == "CycloneDX" and comps else 1


if __name__ == "__main__":
    raise SystemExit(main())
