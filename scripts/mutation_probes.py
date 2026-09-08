#!/usr/bin/env python3
"""Killed-mutation probes for the standing gate.

Each probe introduces a mutation (wrong table value, gapped PCF, auth bypass)
and PASSes only when an independent computed check kills that mutation.
A probe that never exercises a checker is a gate failure.
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RESULTS: list[tuple[str, bool, str]] = []


def _emit(name: str, ok: bool, evidence: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{name} {status} {evidence}")
    RESULTS.append((name, ok, evidence))


def probe_od_mm_mutation() -> tuple[bool, str]:
    """Mutate B36.10 6\" OD; A12-style number must no longer match 168.3."""
    from threadforge import tables as T

    expected = 168.3
    baseline = T.od_mm('6"')
    if abs(baseline - expected) >= 0.05:
        return False, f"baseline od_mm(6)={baseline} want {expected}"
    old = T.NPS_OD_MM[6.0]
    T.NPS_OD_MM[6.0] = old + 10.0
    try:
        mutated = T.od_mm('6"')
    finally:
        T.NPS_OD_MM[6.0] = old
    restored = T.od_mm('6"')
    killed = abs(mutated - expected) >= 0.05
    if not killed:
        return False, f"od_mm mutation survived mutated={mutated}"
    if abs(restored - expected) >= 0.05:
        return False, f"restore failed restored={restored}"
    return True, f"killed od_mm mutant baseline={baseline} mutated={mutated} restored={restored}"


def probe_gapped_pcf_killed() -> tuple[bool, str]:
    """A 500 mm PIPE gap must be rejected by assert_contiguous (computed distance)."""
    from threadforge.pcf_reader import (
        PCFComponent,
        PCFDocument,
        PCFEndPoint,
        PCFParseError,
        assert_contiguous,
    )

    doc = PCFDocument(
        components=[
            PCFComponent(
                kind="PIPE",
                end_points=[
                    PCFEndPoint(0, 0, 0, 100),
                    PCFEndPoint(1000, 0, 0, 100),
                ],
            ),
            PCFComponent(
                kind="PIPE",
                end_points=[
                    PCFEndPoint(1500, 0, 0, 100),
                    PCFEndPoint(2500, 0, 0, 100),
                ],
            ),
        ]
    )
    try:
        assert_contiguous(doc, tol_mm=1.0)
    except PCFParseError as exc:
        msg = str(exc)
        if "500" not in msg and "gap" not in msg.lower():
            return False, f"raised but gap not computed: {exc}"
        return True, f"killed gapped-PCF mutant {exc}"
    return False, "gapped PCF accepted (contiguous mutation survived)"


def probe_tools_auth_mutation() -> tuple[bool, str]:
    """Mutate require_auth to always-allow; unauth /tools must leave 401."""
    from fastapi.testclient import TestClient

    from threadforge import server

    orig = server.require_auth
    os.environ["TF_API_TOKENS"] = "engineer:eng-token:write"
    os.environ["TF_DATA"] = tempfile.mkdtemp()
    baseline = TestClient(server.create_app()).get("/tools").status_code
    if baseline != 401:
        return False, f"baseline tools_unauth={baseline} want 401"

    def mutant(authorization: Optional[str] = None) -> server.Principal:
        return server.Principal(role="engineer", access="write", token="mutant")

    server.require_auth = mutant  # type: ignore[method-assign]
    try:
        mutated = TestClient(server.create_app()).get("/tools").status_code
    finally:
        server.require_auth = orig
    if mutated == 401:
        return False, f"auth mutation survived baseline={baseline} mutated={mutated}"
    return True, f"killed tools_auth mutant baseline={baseline} mutated={mutated}"


PROBES: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("P01_od_mm", probe_od_mm_mutation),
    ("P02_gapped_pcf", probe_gapped_pcf_killed),
    ("P03_tools_auth", probe_tools_auth_mutation),
]


def main() -> int:
    for name, fn in PROBES:
        try:
            ok, evidence = fn()
            _emit(name, ok, evidence)
        except Exception as exc:  # noqa: BLE001
            _emit(name, False, f"exception: {type(exc).__name__}: {exc}")
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"PROBES: {passed}/{len(PROBES)} killed")
    return 0 if passed == len(PROBES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
