"""
AddressGuard AI — 1,000-case stress evaluation.

Default:
    python evaluation/run_1000_stress.py

The default run is deterministic:
- AI disabled
- external geocoding disabled
- live postal fallback disabled
- local India Post/LGD/reference index remains enabled

Optional:
    python evaluation/run_1000_stress.py --ai

The 1,000 cases are deterministic variants derived from the project's
34 labelled seed cases. This is a stress test, NOT 1,000 independent
real-world addresses. Metrics are calculated from actual pipeline outputs.
"""
import argparse
import json
import os
import statistics
import logging
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--ai", action="store_true", help="Enable Groq AI for the 1,000 cases.")
args = parser.parse_args()
logging.disable(logging.CRITICAL)
logging.getLogger().setLevel(logging.ERROR)

os.environ["GEOCODING_ENABLED"] = "false"
os.environ["LIVE_POSTAL_API_ENABLED"] = "false"
if not args.ai:
    os.environ["GROQ_API_KEY"] = ""

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from services.pipeline_orchestrator import run_pipeline

DATASET = Path(__file__).with_name("stress_dataset_1000.json")
OUTPUT = Path(__file__).with_name("stress_results_1000.json")

STATUSES = [
    "VERIFIED",
    "NEEDS CUSTOMER CONFIRMATION",
    "SUSPICIOUS",
    "FAKE ADDRESS",
]


def safe_div(a, b):
    return round(a / b, 4) if b else 0.0


def metrics(records):
    matrix = {e: {p: 0 for p in STATUSES} for e in STATUSES}
    for r in records:
        e, p = r["expected_status"], r["predicted_status"]
        if e in matrix and p in matrix[e]:
            matrix[e][p] += 1

    precisions, recalls, f1s = [], [], []
    for label in STATUSES:
        tp = matrix[label][label]
        fp = sum(matrix[e][label] for e in STATUSES if e != label)
        fn = sum(matrix[label][p] for p in STATUSES if p != label)
        pr = safe_div(tp, tp + fp)
        rc = safe_div(tp, tp + fn)
        f1 = safe_div(2 * pr * rc, pr + rc)
        precisions.append(pr)
        recalls.append(rc)
        f1s.append(f1)

    correct = sum(r["expected_status"] == r["predicted_status"] for r in records)
    return {
        "accuracy": safe_div(correct, len(records)),
        "precision_macro": round(statistics.mean(precisions), 4),
        "recall_macro": round(statistics.mean(recalls), 4),
        "f1_macro": round(statistics.mean(f1s), 4),
        "confusion_matrix": matrix,
    }



def correction_metrics(records):
    labelled = [r for r in records if r.get("expected_corrections") is not None]
    if not labelled:
        return {"labelled_cases": 0, "exact_case_match": 0.0, "field_precision": 0.0, "field_recall": 0.0}
    exact = 0
    tp = fp = fn = 0
    for r in labelled:
        expected = {(str(c.get("field", "")).lower(), str(c.get("original", "")).strip().lower(), str(c.get("suggested", "")).strip().lower()) for c in (r.get("expected_corrections") or [])}
        actual = {(str(c.get("field", "")).lower(), str(c.get("original", "")).strip().lower(), str(c.get("suggested", "")).strip().lower()) for c in (r.get("actual_corrections") or [])}
        if expected == actual:
            exact += 1
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
    return {
        "labelled_cases": len(labelled),
        "exact_case_match": safe_div(exact, len(labelled)),
        "field_precision": safe_div(tp, tp + fp),
        "field_recall": safe_div(tp, tp + fn),
    }

def main():
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    records = []
    failures = []

    for case in cases:
        started = time.perf_counter()
        result = run_pipeline(
            case["input"],
            Config,
            accepted=[],
            resolved=[],
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

        predicted = result.get("decision", "")
        record = {
            "id": case["id"],
            "source_case_id": case["source_case_id"],
            "category": case["category"],
            "variant": case["variant"],
            "expected_status": case["expected_status"],
            "predicted_status": predicted,
            "confidence": result.get("confidence"),
            "risk_level": result.get("risk_level"),
            "correction_count": len(result.get("corrections") or []),
            "expected_corrections": case.get("expected_corrections", []),
            "actual_corrections": result.get("corrections") or [],
            "elapsed_ms": elapsed_ms,
        }
        records.append(record)

        if predicted != case["expected_status"]:
            failures.append({
                **record,
                "input": case["input"],
            })

    by_category = {}
    for category in sorted({r["category"] for r in records}):
        rows = [r for r in records if r["category"] == category]
        by_category[category] = {
            "count": len(rows),
            "correct": sum(r["expected_status"] == r["predicted_status"] for r in rows),
            "accuracy": safe_div(
                sum(r["expected_status"] == r["predicted_status"] for r in rows),
                len(rows),
            ),
        }

    output = {
        "status": "MEASURED",
        "dataset_size": len(records),
        "experimental_setup": {
            "ai_enabled": bool(args.ai),
            "geocoding_enabled": False,
            "live_postal_fallback_enabled": False,
            "seed_dataset_size": 34,
            "description": (
                "Deterministic stress variants derived from the 34 labelled seed cases; "
                "not 1,000 independent real-world addresses."
            ),
        },
        "metrics": metrics(records),
        "correction_metrics": correction_metrics(records),
        "timing_ms": {
            "average": round(statistics.mean(r["elapsed_ms"] for r in records), 3),
            "median": round(statistics.median(r["elapsed_ms"] for r in records), 3),
            "min": min(r["elapsed_ms"] for r in records),
            "max": max(r["elapsed_ms"] for r in records),
        },
        "by_category": by_category,
        "failed_cases": failures,
    }

    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Dataset: {len(records)}")
    print(f"Accuracy: {output['metrics']['accuracy'] * 100:.2f}%")
    print(f"Macro Precision: {output['metrics']['precision_macro'] * 100:.2f}%")
    print(f"Macro Recall: {output['metrics']['recall_macro'] * 100:.2f}%")
    print(f"Macro F1: {output['metrics']['f1_macro'] * 100:.2f}%")
    print(f"Average pipeline time: {output['timing_ms']['average']} ms")
    print(f"Correction exact-case match: {output['correction_metrics']['exact_case_match'] * 100:.2f}%")
    print(f"Correction field precision: {output['correction_metrics']['field_precision'] * 100:.2f}%")
    print(f"Correction field recall: {output['correction_metrics']['field_recall'] * 100:.2f}%")
    print(f"Failures: {len(failures)}")
    print(f"Results: {OUTPUT}")


if __name__ == "__main__":
    main()
