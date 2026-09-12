"""Shared fixtures for Lane C.

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


@pytest.fixture
def pack():
    return load_pack()


@pytest.fixture
def ledger(pack):
    """Every rule verified, so every check runs."""
    book = VerificationLedger()
    for rule in pack.rules:
        book = book.record(rule, verified_by=TEST_REVIEWER)
    return book


@pytest.fixture
def graph():
    return build_graph()


@pytest.fixture
def scenario():
    return build_scenario()


@pytest.fixture
def stub():
    return FixtureMeasurements()


@pytest.fixture
def pipeline():
    return PipelineMeasurements()


@pytest.fixture(params=["stub", "pipeline"])
def measure(request):
    """Both providers, so a check that only works against one is caught."""
    return {"stub": FixtureMeasurements(), "pipeline": PipelineMeasurements()}[
        request.param
    ]
