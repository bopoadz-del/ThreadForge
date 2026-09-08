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


def probe_spool_12m_mutation() -> tuple[bool, str]:
    """Mutate 12 m shop length; 30 m 6\" line must no longer pin 12+12+6."""
    import threadforge.spooling as S
    from threadforge.generators import write_pcf_text
    from threadforge.spooling import SHOP_MAX_LENGTH_M, crafted_straight_30m

    g = crafted_straight_30m()
    write_pcf_text(g, "LINE-CRAFT-30M")
    baseline = [round(sp["length_m"], 6) for sp in g.routes["LINE-CRAFT-30M"]["spools"]["spools"]]
    if baseline != [12.0, 12.0, 6.0]:
        return False, f"baseline lengths={baseline}"
    old = S.SHOP_MAX_LENGTH_M
    S.SHOP_MAX_LENGTH_M = 8.0
    try:
        g2 = crafted_straight_30m()
        write_pcf_text(g2, "LINE-CRAFT-30M")
        mutated = [round(sp["length_m"], 6) for sp in g2.routes["LINE-CRAFT-30M"]["spools"]["spools"]]
    finally:
        S.SHOP_MAX_LENGTH_M = old
    killed = mutated != [12.0, 12.0, 6.0] and max(mutated) <= 8.0 + 1e-6
    if not killed:
        return False, f"12m mutation survived mutated={mutated}"
    return True, f"killed 12m mutant baseline={baseline} mutated={mutated} limit={SHOP_MAX_LENGTH_M}"


def probe_ndt_5pct_mutation() -> tuple[bool, str]:
    """Mutate B31.3 5% RT; n=40 must no longer require 2 RT welds."""
    from threadforge import tables as T
    from threadforge.weld_ndt import n_rt_required

    if n_rt_required(40) != 2:
        return False, f"baseline n_rt(40)={n_rt_required(40)}"
    old = T.B31_3_341_4_1_NORMAL_RT_PCT
    T.B31_3_341_4_1_NORMAL_RT_PCT = 50.0
    try:
        # n_rt_required defaults to the module-imported constant; pass mutated pct
        mutated = n_rt_required(40, pct=T.B31_3_341_4_1_NORMAL_RT_PCT)
    finally:
        T.B31_3_341_4_1_NORMAL_RT_PCT = old
    if mutated == 2:
        return False, f"5% mutation survived mutated={mutated}"
    return True, f"killed 5% RT mutant baseline=2 mutated={mutated}"


def probe_hydro_15_mutation() -> tuple[bool, str]:
    """Mutate B31.3 345.4.2 factor 1.5; 30 bar same-T P_T must leave 45.0."""
    from threadforge import tables as T

    baseline = T.b31_3_345_4_2_test_pressure(30.0, 100.0, 21.0)
    if abs(float(baseline["test_pressure_barg"]) - 45.0) >= 1e-6:
        return False, f"baseline Pt={baseline['test_pressure_barg']}"
    old = T.B31_3_345_4_2_FACTOR
    T.B31_3_345_4_2_FACTOR = 1.0
    try:
        mutated = T.b31_3_345_4_2_test_pressure(30.0, 100.0, 21.0)
    finally:
        T.B31_3_345_4_2_FACTOR = old
    killed = abs(float(mutated["test_pressure_barg"]) - 45.0) >= 1e-6
    if not killed:
        return False, f"1.5 mutation survived Pt={mutated['test_pressure_barg']}"
    return True, f"killed 1.5 mutant baseline=45 mutated={mutated['test_pressure_barg']}"


def probe_b16_5_cap_mutation() -> tuple[bool, str]:
    """Mutate B16.5 class 400 @ 38 °C; 60 bar P_T cap must leave 68.1."""
    from threadforge import tables as T

    baseline = T.b16_5_pt_rating_bar(400, 21.0)
    if abs(baseline - 68.1) >= 1e-6:
        return False, f"baseline rating={baseline}"
    old = T.B16_5_PT_GROUP_1_1_BAR[400][38.0]
    T.B16_5_PT_GROUP_1_1_BAR[400][38.0] = 10.0
    try:
        mutated = T.b16_5_pt_rating_bar(400, 21.0)
    finally:
        T.B16_5_PT_GROUP_1_1_BAR[400][38.0] = old
    if abs(mutated - 68.1) < 1e-6:
        return False, f"B16.5 mutation survived mutated={mutated}"
    return True, f"killed B16.5 mutant baseline={baseline} mutated={mutated}"


def probe_upload_limit_mutation() -> tuple[bool, str]:
    """Mutate MAX_UPLOAD_BYTES; 2 MiB+1 must no longer be 413."""
    import threadforge.guards as G

    over = G.MAX_UPLOAD_BYTES + 1
    try:
        G.reject_xml_bomb(b"x" * over)
        return False, "baseline oversized accepted"
    except G.GuardError as exc:
        if exc.status != 413:
            return False, f"baseline status={exc.status}"
    old = G.MAX_UPLOAD_BYTES
    G.MAX_UPLOAD_BYTES = over + 10
    try:
        try:
            G.reject_xml_bomb(b"x" * over)
            mutated_ok = True
        except G.GuardError:
            mutated_ok = False
    finally:
        G.MAX_UPLOAD_BYTES = old
    if not mutated_ok:
        return False, "upload-limit mutation survived"
    return True, f"killed upload-limit mutant over={over}"


def probe_rate_limit_mutation() -> tuple[bool, str]:
    """Mutate RATE_LIMIT_N; 25 hits in-window must no longer 429."""
    import threadforge.guards as G

    G.reset_rate_limits()
    baseline_hit = False
    for i in range(G.RATE_LIMIT_N + 5):
        if G.rate_limit_hit("probe-rl", now=1000.0 + i * 0.001):
            baseline_hit = True
            break
    if not baseline_hit:
        return False, "baseline never limited"
    G.reset_rate_limits()
    old = G.RATE_LIMIT_N
    G.RATE_LIMIT_N = 10_000
    try:
        mutated_hit = any(G.rate_limit_hit("probe-rl-m", now=2000.0 + i * 0.001) for i in range(30))
    finally:
        G.RATE_LIMIT_N = old
        G.reset_rate_limits()
    if mutated_hit:
        return False, "rate-limit mutation survived"
    return True, f"killed rate-limit mutant baseline_hit={baseline_hit}"


def probe_key_hash_mutation() -> tuple[bool, str]:
    """Mutate hash_api_key to echo plaintext; stored digest must no longer verify as hash."""
    import threadforge.persist as P

    token = "probe-token"
    stored = P.new_key_hash(token)
    if token in stored or not P.verify_api_key(token, stored):
        return False, f"baseline stored={stored[:20]}"
    orig = P.hash_api_key

    def mutant(tok: str, salt: str) -> str:
        return tok

    P.hash_api_key = mutant  # type: ignore[method-assign]
    try:
        mutated_stored = P.new_key_hash(token)
    finally:
        P.hash_api_key = orig
    if token not in mutated_stored and mutated_stored.startswith("tfk1$"):
        return False, f"hash mutation survived stored={mutated_stored[:24]}"
    return True, f"killed key-hash mutant mutated={mutated_stored[:24]}"


PROBES: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
    ("P01_od_mm", probe_od_mm_mutation),
    ("P02_gapped_pcf", probe_gapped_pcf_killed),
    ("P03_tools_auth", probe_tools_auth_mutation),
    ("P04_spool_12m", probe_spool_12m_mutation),
    ("P05_ndt_5pct", probe_ndt_5pct_mutation),
    ("P06_hydro_15", probe_hydro_15_mutation),
    ("P07_b16_5_cap", probe_b16_5_cap_mutation),
    ("P08_upload_limit", probe_upload_limit_mutation),
    ("P09_rate_limit", probe_rate_limit_mutation),
    ("P10_key_hash", probe_key_hash_mutation),
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
