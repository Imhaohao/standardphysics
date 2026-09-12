"""Shared fixtures for Lane C.

The shop, the rule pack and the ledger are immutable, and building an
occupancy grid is not free, so they are built once for the session. Tests that
need a different layout copy one rather than editing these.

The shipped verification ledger is empty, because a person has to read each
section before its check runs. Tests need the checks to run, so they build
their own ledger and say so in its `verified_by`. Nothing in this directory
writes the shipped one.
"""

from __future__ import annotations

import pytest
from standardphysics_agents import VerificationLedger, load_pack
from standardphysics_fixtures import FixtureMeasurements, build_graph, build_scenario
from standardphysics_pipeline import PipelineMeasurements

TEST_REVIEWER = "test suite, not a person"


@pytest.fixture(scope="session")
def pack():
    return load_pack()


@pytest.fixture(scope="session")
def ledger(pack):
    """Every rule verified, so every check runs."""
    book = VerificationLedger()
    for rule in pack.rules:
        book = book.record(rule, verified_by=TEST_REVIEWER)
    return book


@pytest.fixture(scope="session")
def graph():
    return build_graph()


@pytest.fixture(scope="session")
def scenario():
    return build_scenario()


@pytest.fixture(scope="session")
def stub():
    return FixtureMeasurements()


@pytest.fixture(scope="session")
def pipeline():
    return PipelineMeasurements()


@pytest.fixture(scope="session", params=["stub", "pipeline"])
def measure(request):
    """Both providers, so a check that only works against one is caught."""
    return {"stub": FixtureMeasurements(), "pipeline": PipelineMeasurements()}[
        request.param
    ]
