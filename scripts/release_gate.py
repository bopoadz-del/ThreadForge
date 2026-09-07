#!/usr/bin/env python3
"""Release gate: ruff + mypy + pytest + acceptance (subset when deps thin)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(ROOT))


def main() -> int:
    run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
    run([sys.executable, "-m", "mypy", "--strict", "src"])
    run([sys.executable, "-m", "pytest", "-q"])
    run([sys.executable, "scripts/acceptance.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
