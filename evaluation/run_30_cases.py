"""Execute the 30-case address suite and record the genuine results.

Run from the project root:

    python evaluation/run_30_cases.py

Writes evaluation/test_30_cases_results.json and evaluation/TEST_30_CASES.md.
Nothing is hardcoded: every row is the outcome of an actual API call.
"""
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["GROQ_API_KEY"] = ""
# Importing app builds it against DATABASE_URL; point that at a throwaway file
# so the runner never touches (or depends on) the real database.
_RUN_DIR = tempfile.mkdtemp(prefix="addressguard-30cases-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_RUN_DIR, "import.db").replace("\\", "/")
os.environ["ADDRESSGUARD_TEST_ALLOW_SQLITE"] = "1"

from evaluation.address_cases_30 import CASES, make_client, run_case  # noqa: E402


def _short(text, limit=90):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        app, client = make_client(Path(tmp) / "cases.db")
        results = [run_case(case, app, client) for case in CASES]
        # Release the SQLite file before the temporary directory is removed.
        from models import db
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    passed = sum(1 for r in results if r["passed"])
    times = [r["time_ms"] for r in results]
    summary = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "time_ms": {
            "mean": round(statistics.mean(times), 1),
            "median": round(statistics.median(times), 1),
            "max": max(times),
        },
        "setup": "Flask test client, temporary SQLite database, Groq disabled except in F03, "
                 "external geocoding disabled except in F04, live postal API as configured in .env",
    }
    out_json = ROOT / "evaluation" / "test_30_cases_results.json"
    out_json.write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# AddressGuard AI — 30 Address Test Cases",
        "",
        f"Executed {summary['executed_at_utc']} (UTC). **{passed}/{len(results)} passed**, "
        f"{summary['failed']} failed. Time per case: mean {summary['time_ms']['mean']} ms, "
        f"median {summary['time_ms']['median']} ms, max {summary['time_ms']['max']} ms.",
        "",
        f"Setup: {summary['setup']}.",
        "",
        "| ID | Category | Input | Expected | Actual | Result | Explanation | Time (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        exp = r["expected"]
        expected = f"HTTP {exp['status']}"
        for key in ("decision", "decision_in", "not_decision", "error_type"):
            if key in exp:
                label = {"decision_in": "one of", "not_decision": "not", "error_type": "error"}.get(key, "")
                expected += f", {label + ' ' if label else ''}{exp[key]}"
        act = r["actual"]
        actual = f"HTTP {act['http_status']}"
        if act["decision"]:
            actual += f", {act['decision']} ({act['confidence']}%, risk {act['risk_level']}, rule {act['rule']})"
        if act["error"]:
            actual += f", error: {act['error']}"
        verdict = "PASS" if r["passed"] else "FAIL: " + "; ".join(r["failures"])
        lines.append(
            f"| {r['id']} | {_cell(r['category'])} | {_cell(_short(r['input']))} | {_cell(expected)} | "
            f"{_cell(actual)} | {_cell(verdict)} | {_cell(r['explanation'])} | {r['time_ms']} |"
        )
    (ROOT / "evaluation" / "TEST_30_CASES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{passed}/{len(results)} passed")
    for r in results:
        if not r["passed"]:
            print(f"  FAIL {r['id']}: {r['failures']}")
    print(f"Results: {out_json}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
