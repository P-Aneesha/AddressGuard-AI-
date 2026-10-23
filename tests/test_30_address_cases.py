"""Runs the 30 documented address cases through the real API.

The same cases and harness produce the recorded report via
`python evaluation/run_30_cases.py`.
"""
import os

os.environ["GROQ_API_KEY"] = ""  # deterministic parser unless a case injects a Groq fault

import pytest

from evaluation.address_cases_30 import CASES, make_client, run_case


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    return make_client(tmp_path_factory.mktemp("cases") / "cases.db")


def test_suite_has_thirty_unique_cases():
    ids = [c["id"] for c in CASES]
    assert len(ids) == 30
    assert len(set(ids)) == 30


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_address_case(api, case):
    app, client = api
    result = run_case(case, app, client)
    assert result["passed"], f"{case['id']} ({case['category']}): {result['failures']} | actual={result['actual']}"
