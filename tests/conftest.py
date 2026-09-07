"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from threadforge import agent_tools
from threadforge.generators import build_work_packages
from threadforge.ingest_dexpi import load_fixture


@pytest.fixture(autouse=True)
def _reset_session():
    agent_tools.SESSION.graph = None
    agent_tools.SESSION.job = None
    agent_tools.SESSION.cascade = None
    agent_tools.SESSION.schedule = None
    agent_tools.SESSION.test_packs = []
    yield
    agent_tools.SESSION.graph = None
    agent_tools.SESSION.job = None
    agent_tools.SESSION.cascade = None
    agent_tools.SESSION.schedule = None
    agent_tools.SESSION.test_packs = []


@pytest.fixture
def graph():
    return load_fixture()


@pytest.fixture
def graph_with_wps(graph):
    build_work_packages(graph)
    return graph


@pytest.fixture
def fixtures_dir():
    return ROOT / "fixtures"
