"""Every validation finishes within the time budget, even when services hang."""
import threading
import time
from types import SimpleNamespace
from unittest import mock

from services import pipeline_orchestrator as po
from services.address_parser import parse_address

ADDRESS = "Ravi Kumar, 9876543210, Flat 302, Sai Residency, Hitech City Road, Madhapur, Hyderabad, Telangana 500081"


def test_validation_finishes_within_budget_when_services_hang():
    budget = 8.0  # the production budget is 20 s; a shorter one keeps the test quick
    cfg = SimpleNamespace(GROQ_API_KEY="key", GROQ_BASE_URL="", GROQ_MODEL="m", GROQ_TIMEOUT_SECONDS=15,
                          GEOCODING_ENABLED=True, VALIDATION_TIME_BUDGET_SECONDS=budget)
    release = threading.Event()
    timeouts = {}

    def slow_ai(raw, key, base, model, timeout):
        timeouts["extraction"] = timeout
        release.wait(timeout)  # a slow model uses its whole time slice, then the client gives up
        return parse_address(raw), {"source": "fallback", "model": None, "status": "Fallback", "error": "timeout"}

    def hang(*args, **kwargs):
        release.wait(60)  # a stuck connection that ignores its own timeout
        return ([], {"source": "ai"}) if len(args) > 2 else {"status": "CONFIRMED"}

    with mock.patch.object(po, "extract_with_ai", slow_ai), \
            mock.patch.object(po, "generate_ai_corrections", hang), \
            mock.patch.object(po, "verify_geocoding", hang):
        started = time.monotonic()
        result = po.run_pipeline(ADDRESS, cfg)
        elapsed = time.monotonic() - started
    release.set()  # let the abandoned background calls finish

    assert elapsed < budget - 1  # network calls stop NETWORK_RESERVE_SECONDS early
    assert timeouts["extraction"] <= (budget - po.NETWORK_RESERVE_SECONDS) / 2 + 0.1
    assert {"external geocoding", "AI spelling review"} <= set(result["skipped_for_time"])
    assert result["decision"] == "VERIFIED"  # the built-in checks still decide
    stage = next(s for s in result["pipeline"] if s["stage"] == "Processing Time")
    assert "left out to stay within the limit" in stage["details"]


def test_normal_validation_reports_its_time():
    cfg = SimpleNamespace(GROQ_API_KEY="", GROQ_BASE_URL="", GROQ_MODEL="m", GROQ_TIMEOUT_SECONDS=15)
    result = po.run_pipeline(ADDRESS, cfg)
    assert result["time_budget_seconds"] == po.DEFAULT_TIME_BUDGET_SECONDS
    assert 0 < result["processing_time_ms"] < 20000 and result["skipped_for_time"] == []
