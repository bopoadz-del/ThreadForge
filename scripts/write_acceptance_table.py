#!/usr/bin/env python3
"""Write a markdown acceptance table by running the harness (B40 asset)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "acceptance.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "acceptance.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    body = proc.stdout or ""
    lines = ["# ThreadForge v2.0.0 acceptance", "", "```", body.rstrip(), "```", ""]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest} bytes={dest.stat().st_size} rc={proc.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
