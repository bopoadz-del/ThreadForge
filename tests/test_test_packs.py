"""Test pack membership from system boundaries."""

from threadforge.generators import build_test_packs
from threadforge.ingest_dexpi import load_fixture


def test_test_pack_membership():
    g = load_fixture()
    packs = build_test_packs(g)
    assert len(packs) == 2
    by_id = {p.id: p for p in packs}

    tp_proc = by_id["TP-SYS-PROCESS-120"]
    assert "120-VEPR-2010" in tp_proc.tags
    # Expanded via connectivity / nozzles
    assert "120-VEPR-2010-N1" in tp_proc.tags or "120-VEPR-2010" in tp_proc.metadata["boundary"]

    tp_lpg = by_id["TP-SYS-LPG-124"]
    assert "124-PKSA-0500" in tp_lpg.tags
    assert "124-LPNP-2508" in tp_lpg.tags
    # Component on boundary should be included
    assert "124-LPWP-2505-BlindFlange" in tp_lpg.tags
