"""Run the messy-address evaluation set through the real API and record results.

    python evaluation/messy_addresses.py   # (re)build the dataset
    python evaluation/run_messy_250.py      # run it

Writes evaluation/messy_250_results.json and evaluation/MESSY_250_REPORT.md.
Groq and external geocoding are disabled so the run is reproducible; the
temporary SQLite database keeps it away from the real PostgreSQL database.
"""
import json
import os
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["GROQ_API_KEY"] = ""
_RUN_DIR = tempfile.mkdtemp(prefix="addressguard-messy-")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_RUN_DIR, "import.db").replace("\\", "/")
os.environ["ADDRESSGUARD_TEST_ALLOW_SQLITE"] = "1"

from evaluation.address_cases_30 import make_client  # noqa: E402
from evaluation.messy_addresses import DATASET, VERIFIED, build  # noqa: E402

LABELS = ["VERIFIED", "NEEDS CUSTOMER CONFIRMATION", "VALIDATION WARNING", "VALIDATION FAILED"]


def _run_case(client, case):
    start = time.perf_counter()
    response = client.post("/api/validate", json={"raw_address": case["input"]})
    elapsed = round((time.perf_counter() - start) * 1000, 1)
    body = response.get_json(silent=True) or {}
    decision = body.get("decision") or f"HTTP {response.status_code}"
    if response.status_code == 400 and body.get("error_type") == "INPUT_ERROR":
        decision = "VALIDATION FAILED"  # rejected as not an address before the pipeline
    failures = []
    if decision not in case["expect_decision_in"]:
        failures.append(f"expected {' or '.join(case['expect_decision_in'])}, got {decision}")
    suggested = {c.get("field"): c.get("suggested") for c in body.get("corrections") or []}
    for field, value in (case.get("expect_correction") or {}).items():
        if str(suggested.get(field, "")).lower() != value.lower():
            failures.append(f"expected {field} correction to {value}, got {suggested.get(field) or 'none'}")
    explain = body.get("explainability") or {}
    return {
        "id": case["id"], "category": case["category"], "input": case["input"],
        "expected": case["expect_decision_in"], "decision": decision, "confidence": body.get("confidence"),
        "rule": explain.get("decision_rule"), "reasons": (explain.get("decision_reasons") or [])[:4],
        "corrections": suggested, "passed": not failures, "failures": failures, "time_ms": elapsed,
    }


def main():
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASET
    tag = dataset.stem.replace("messy_250_", "").replace("dataset", "")
    cases = json.loads(dataset.read_text(encoding="utf-8"))["cases"] if dataset.exists() else build()
    with tempfile.TemporaryDirectory() as tmp:
        app, client = make_client(Path(tmp) / "messy.db")
        results = [_run_case(client, case) for case in cases]
        from models import db
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    passed = sum(r["passed"] for r in results)
    should_not_verify = [r for r in results if VERIFIED not in r["expected"]]
    false_verified = [r for r in should_not_verify if r["decision"] == VERIFIED]
    good = [r for r in results if r["expected"] == [VERIFIED]]
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    matrix = Counter((r["expected"][0] if len(r["expected"]) == 1 else " or ".join(r["expected"]), r["decision"])
                     for r in results)
    times = [r["time_ms"] for r in results]
    summary = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(results), "passed": passed, "accuracy_pct": round(100 * passed / len(results), 1),
        "false_verified": len(false_verified), "should_not_verify": len(should_not_verify),
        "good_addresses_verified": sum(r["decision"] == VERIFIED for r in good), "good_addresses": len(good),
        "time_ms": {"mean": round(statistics.mean(times), 1), "median": round(statistics.median(times), 1),
                    "max": max(times)},
        "per_category": {cat: {"passed": sum(r["passed"] for r in rs), "total": len(rs)} for cat, rs in by_cat.items()},
    }
    out = ROOT / "evaluation" / f"messy_250_{tag + '_' if tag else ''}results.json"
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# AddressGuard AI: 250 messy addresses{' (' + tag + ' set)' if tag else ''}",
        "",
        f"Executed {summary['executed_at_utc']} (UTC). **{passed}/{len(results)} passed "
        f"({summary['accuracy_pct']}%)**.",
        "",
        "**What this dataset is:** generated, not real customer data. Every locality, PIN, city and state is a real "
        "India Post delivery office in one of 25 cities; names, phones, flats and streets are synthetic. Each address "
        "is then written the way people type them (typos, no punctuation, WhatsApp layout, missing parts, wrong "
        "PINs). Expected decisions are fixed by construction before the run. Groq AI and external geocoding were "
        "off, so this measures the deterministic engine.",
        "",
        "## Key safety numbers",
        "",
        f"- Addresses that should NOT be verified but were marked VERIFIED: **{len(false_verified)} of "
        f"{len(should_not_verify)}**",
        f"- Correct addresses that reached VERIFIED: **{summary['good_addresses_verified']} of {len(good)}**",
        f"- Time per address: mean {summary['time_ms']['mean']} ms, median {summary['time_ms']['median']} ms, "
        f"max {summary['time_ms']['max']} ms",
        "",
        "## By category",
        "",
        "| Category | Passed |",
        "|---|---|",
        *[f"| {cat} | {v['passed']}/{v['total']} |" for cat, v in summary["per_category"].items()],
        "",
        "## Expected vs actual decision",
        "",
        "| Expected | " + " | ".join(LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
        *[f"| {exp} | " + " | ".join(str(matrix.get((exp, lab), 0)) for lab in LABELS) + " |"
          for exp in dict.fromkeys(k[0] for k in matrix)],
        "",
        "## Every failure",
        "",
        "| ID | Category | Input | Got | Why it failed | Engine's reasons |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r["passed"]:
            cell = lambda s: str(s).replace("|", "\\|").replace("\n", " / ")  # noqa: E731
            lines.append(f"| {r['id']} | {cell(r['category'])} | {cell(r['input'])} | {cell(r['decision'])} "
                         f"({r['confidence']}%) | {cell('; '.join(r['failures']))} | {cell('; '.join(r['reasons']))} |")
    (ROOT / "evaluation" / f"MESSY_250_{tag.upper() + '_' if tag else ''}REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{passed}/{len(results)} passed ({summary['accuracy_pct']}%), false VERIFIED: {len(false_verified)}")
    for cat, v in summary["per_category"].items():
        print(f"  {v['passed']:>3}/{v['total']:<3} {cat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
