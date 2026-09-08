"""B27: cascade dirties exactly 12 kinds; untouched hashes stay identical."""

from pathlib import Path

from threadforge.cascade import CASCADE_KINDS_12, CascadeEngine
from threadforge.ingest_dexpi import load_fixture
from threadforge.routing import generate_routes_astar


def test_revise_one_line_dirty_exact_and_untouched_hashes(tmp_path: Path):
    g = load_fixture("sample_pid_rich.xml")
    generate_routes_astar(g)
    a, b = sorted(g.pipelines)[:2]
    eng = CascadeEngine(g)
    hashes = {}
    for lid in (a, b):
        for kind in CASCADE_KINDS_12:
            art = eng.write_kind_file(kind, lid, tmp_path)
            hashes[art.id] = Path(art.path).read_bytes()
    g.revise_pipeline(a, {"service": "PROCESS-REV"})
    eng.record_change("pipeline", a, "revise", {"service": "PROCESS-REV"})
    dirty = eng.last_dirty
    assert dirty is not None
    assert sorted(k.value for k in dirty.artefact_kinds) == sorted(k.value for k in CASCADE_KINDS_12)
    assert sorted(dirty.artefact_ids) == sorted(f"{k.value}-{a}" for k in CASCADE_KINDS_12)
    for kind in CASCADE_KINDS_12:
        bid = f"{kind.value}-{b}"
        art = eng.artefacts[bid]
        assert art.status != "dirty"
        assert Path(art.path).read_bytes() == hashes[bid]
