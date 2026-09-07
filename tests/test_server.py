"""D10: FastAPI tools + deterministic export hashes."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from threadforge.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from threadforge import agent_tools

    monkeypatch.setenv("TF_DATA", str(tmp_path))
    agent_tools.SESSION.output_dir = tmp_path
    # re-bind data_dir
    app = create_app()
    return TestClient(app)


def test_tools_list(client):
    r = client.get("/tools")
    assert r.status_code == 200
    names = r.json()
    assert "ingest_dexpi" in names
    assert "export_artefacts" in names
    assert "clash_check" in names


def test_export_hashes_stable_across_two_runs(client, tmp_path):
    r1 = client.post("/tools/ingest_dexpi", json={"path": "sample_pid_rich.xml"})
    assert r1.status_code == 200
    e1 = client.post("/tools/export_artefacts", json={})
    assert e1.status_code == 200
    h1 = e1.json()["artefact_hashes"]
    assert h1

    # second export into same dir should yield identical hashes for stable artefacts
    e2 = client.post("/tools/export_artefacts", json={})
    assert e2.status_code == 200
    h2 = e2.json()["artefact_hashes"]
    # Compare overlapping keys (PCF/iso content deterministic)
    common = set(h1) & set(h2)
    assert common
    for k in common:
        if k.endswith((".pcf", ".svg", ".json", ".csv")):
            assert h1[k] == h2[k], k


def test_registry_db_created(client, tmp_path):
    client.post("/tools/ingest_dexpi", json={})
    client.post("/tools/export_artefacts", json={})
    assert (tmp_path / "registry.db").exists() or list(tmp_path.rglob("registry.db"))
