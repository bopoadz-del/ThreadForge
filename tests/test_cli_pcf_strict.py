"""Cover CLI subcommands and independent pcf_strict parser (B36)."""
from __future__ import annotations

from threadforge.cli import main
from threadforge.generators import write_pcf_text
from threadforge.ingest_dexpi import load_fixture
from threadforge.pcf_strict import PCF_KEYWORDS, assert_pcf_strict, parse_pcf_strict
from threadforge.routing import ensure_routes


def test_cli_tools_and_ingest(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["tools"]) == 0
    out = capsys.readouterr().out
    assert "ingest_dexpi" in out
    assert main(["ingest", "--path", "sample_pid.xml"]) == 0
    assert main(["query", "--summary"]) == 0
    assert main(["test-packs"]) == 0
    assert main(["work-packages"]) == 0
    assert main(["look-ahead", "--weeks", "2"]) == 0
    assert main(["co-activity"]) == 0
    assert main(["maturity", "--required", "FEED"]) == 0
    assert main(["pipeline", "--stage", "outputs"]) == 0


def test_cli_revise_cascade(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["ingest", "--path", "sample_pid_rich.xml"]) == 0
    rc = main(["revise", "pipeline", "LINE-200-P-1001", "--set", "service", "REV"])
    assert rc == 0
    assert main(["cascade"]) == 0


def test_pcf_strict_contiguous(tmp_path):
    g = load_fixture("sample_pid_rich.xml")
    ensure_routes(g)
    text = write_pcf_text(g, "LINE-200-P-1001")
    path = tmp_path / "a.pcf"
    path.write_text(text, encoding="utf-8")
    doc = parse_pcf_strict(path)
    assert "PIPE" in PCF_KEYWORDS
    assert doc["components"]
    assert "PIPE" in doc["keywords_seen"]
    assert_pcf_strict(path)


def test_pcf_strict_gap_not_contiguous(tmp_path):
    path = tmp_path / "gap.pcf"
    path.write_text(
        "PIPELINE-REFERENCE GAP\n"
        "PIPE\nEND-POINT 0 0 0 100\nEND-POINT 1000 0 0 100\n"
        "PIPE\nEND-POINT 2000 0 0 100\nEND-POINT 3000 0 0 100\n",
        encoding="utf-8",
    )
    doc = parse_pcf_strict(path)
    assert doc["contiguous"] is False
    try:
        assert_pcf_strict(path)
        raise AssertionError("expected gap")
    except ValueError as exc:
        assert "non-contiguous" in str(exc)
