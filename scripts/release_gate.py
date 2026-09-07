#!/usr/bin/env python3
"""Standing gate + optional annotated tag.

`--tag` is refused unless A01–A29 all PASS. A30 is the tag existence check
and is not a prerequisite for creating the tag.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(ROOT))


def _a01_a29() -> tuple[bool, list[str]]:
    proc = subprocess.run(
        [sys.executable, "scripts/acceptance.py"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    sys.stdout.write(out)
    failed: list[str] = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 2 or not parts[0].startswith("A") or parts[1] != "FAIL":
            continue
        aid = parts[0]
        if len(aid) == 3 and aid[1:].isdigit() and 1 <= int(aid[1:]) <= 29:
            failed.append(aid)
    return not failed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="ThreadForge release gate")
    parser.add_argument(
        "--tag",
        help="Create an annotated tag only if A01–A29 PASS",
    )
    args = parser.parse_args()

    run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"])
    run([sys.executable, "-m", "mypy", "--strict", "src"])
    run([sys.executable, "-m", "pytest", "-q"])
    run([sys.executable, "scripts/openapi_diff.py"])

    ok, failed = _a01_a29()
    if args.tag:
        if not ok:
            print(f"refuse tag {args.tag}: A01–A29 not all PASS failed={failed}", flush=True)
            return 1
        subprocess.check_call(
            ["git", "tag", "-a", args.tag, "-m", f"ThreadForge {args.tag}"],
            cwd=str(ROOT),
        )
        print(f"tagged {args.tag}", flush=True)
        return 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
