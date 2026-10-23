"""
Reproducible AddressGuard research evaluation.

Run from the project root:

    python evaluation/run_evaluation.py

Deterministic evaluation without LLM:

    python evaluation/run_evaluation.py --no-ai

The script calculates all reported metrics from the labelled dataset and
the actual pipeline execution.

Important:
- No performance number is hardcoded.
- Human correction acceptance is NOT fabricated.
- Correction precision/accuracy and recall use different denominators.
- The oracle-style after-correction experiment is clearly separated from
  human-in-the-loop acceptance.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from config import Config
from services.pipeline_orchestrator import run_pipeline


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUSES = [
    "VERIFIED",
    "NEEDS CUSTOMER CONFIRMATION",
    "VALIDATION WARNING",
    "VALIDATION FAILED",
]


# ---------------------------------------------------------------------------
# Generic metric helpers
# ---------------------------------------------------------------------------

def _safe_div(a, b):
    if not b:
        return 0.0

    return round(a / b, 4)


def _mean(values):
    return (
        round(statistics.mean(values), 4)
        if values
        else 0.0
    )


def _median(values):
    return (
        round(statistics.median(values), 4)
        if values
        else 0.0
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _cfg(no_ai=False):
    """
    Build an evaluation-only configuration.

    The normal application Config object is not modified.
    """

    class EvaluationConfig:
        GROQ_API_KEY = (
            ""
            if no_ai
            else Config.GROQ_API_KEY
        )

        GROQ_BASE_URL = Config.GROQ_BASE_URL
        GROQ_MODEL = Config.GROQ_MODEL
        GROQ_TIMEOUT_SECONDS = Config.GROQ_TIMEOUT_SECONDS

        GEOCODING_ENABLED = Config.GEOCODING_ENABLED
        GEOCODING_URL = Config.GEOCODING_URL
        GEOCODING_TIMEOUT_SECONDS = Config.GEOCODING_TIMEOUT_SECONDS

    return EvaluationConfig


# ---------------------------------------------------------------------------
# Classification metrics
# ---------------------------------------------------------------------------

def _build_confusion_matrix(records):
    """
    Build expected x predicted confusion matrix.
    """
    matrix = {
        expected: {
            predicted: 0
            for predicted in STATUSES
        }
        for expected in STATUSES
    }

    for record in records:
        expected = record.get("expected_status")
        predicted = record.get("predicted_status")

        if (
            expected in matrix
            and predicted in matrix[expected]
        ):
            matrix[expected][predicted] += 1

    return matrix


def _classification_metrics(records):
    """
    Calculate:

    - accuracy
    - macro precision
    - macro recall
    - macro F1
    - confusion matrix

    Every value is calculated from the supplied records.
    """
    matrix = _build_confusion_matrix(records)

    precisions = []
    recalls = []
    f1_scores = []

    for label in STATUSES:
        true_positive = matrix[label][label]

        false_positive = sum(
            matrix[expected][label]
            for expected in STATUSES
            if expected != label
        )

        false_negative = sum(
            matrix[label][predicted]
            for predicted in STATUSES
            if predicted != label
        )

        precision = _safe_div(
            true_positive,
            true_positive + false_positive,
        )

        recall = _safe_div(
            true_positive,
            true_positive + false_negative,
        )

        f1 = _safe_div(
            2 * precision * recall,
            precision + recall,
        )

        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)

    total = len(records)

    correct = sum(
        record["expected_status"]
        == record["predicted_status"]
        for record in records
    )

    return {
        "accuracy": _safe_div(correct, total),
        "precision_macro": (
            round(statistics.mean(precisions), 4)
            if precisions
            else 0.0
        ),
        "recall_macro": (
            round(statistics.mean(recalls), 4)
            if recalls
            else 0.0
        ),
        "f1_macro": (
            round(statistics.mean(f1_scores), 4)
            if f1_scores
            else 0.0
        ),
        "confusion_matrix": matrix,
    }


# ---------------------------------------------------------------------------
# Correction metrics
# ---------------------------------------------------------------------------

def _normalize_correction(item):
    """
    Convert a correction object into a comparable tuple.

    Comparison intentionally ignores case and punctuation differences in
    field text, while preserving the actual semantic field.
    """
    return (
        str(item.get("field", "")).strip().lower(),
        str(item.get("original", "")).strip().lower(),
        str(item.get("suggested", "")).strip().lower(),
    )


def _correction_metrics(records):
    """
    Calculate correction performance honestly.

    Precision:
        correct generated suggestions / all generated suggestions

    Recall:
        correct generated suggestions / all expected corrections

    These are different measurements.

    Example:
        7 correct suggestions
        7 generated suggestions
        23 expected corrections

    gives:

        precision = 7 / 7  = 100%
        recall    = 7 / 23 = 30.43%

    A static dataset cannot measure human acceptance.
    """

    suggestion_count = 0
    expected_total = 0
    correct = 0
    incorrect = 0

    per_case = []

    for record in records:
        expected = {
            _normalize_correction(item)
            for item in record.get(
                "expected_corrections",
                [],
            )
        }

        predicted = {
            _normalize_correction(item)
            for item in record.get(
                "predicted_corrections",
                [],
            )
        }

        case_correct = expected & predicted
        case_incorrect = predicted - expected
        case_missing = expected - predicted

        suggestion_count += len(predicted)
        expected_total += len(expected)

        correct += len(case_correct)
        incorrect += len(case_incorrect)

        per_case.append({
            "id": record["id"],
            "expected": len(expected),
            "generated": len(predicted),
            "correct": len(case_correct),
            "incorrect": len(case_incorrect),
            "missing": len(case_missing),
        })

    return {
        "suggestions": suggestion_count,
        "expected_corrections": expected_total,
        "correct_suggestions": correct,
        "incorrect_suggestions": incorrect,

        # Precision-style correction accuracy:
        # How many generated suggestions were actually correct?
        "correction_accuracy": _safe_div(
            correct,
            suggestion_count,
        ),

        # Recall:
        # How many expected corrections were generated?
        "correction_recall": _safe_div(
            correct,
            expected_total,
        ),

        # Explicitly calculate correction F1 as well.
        "correction_f1": _safe_div(
            2
            * _safe_div(correct, suggestion_count)
            * _safe_div(correct, expected_total),
            _safe_div(correct, suggestion_count)
            + _safe_div(correct, expected_total),
        ),

        "acceptance_rate": None,

        "acceptance_rate_status": (
            "NOT_MEASURED — requires recorded human review decisions"
        ),

        "per_case": per_case,
    }


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def _baseline_status(raw):
    """
    Simple non-AddressGuard baseline.

    This is intentionally basic:
    - phone presence
    - PIN presence
    - basic address-structure keywords

    It is not presented as a production address validator.
    """
    import re

    text = str(raw or "")

    pin = re.search(
        r"\b\d{6}\b",
        text,
    )

    phone = re.search(
        r"\b[6-9]\d{9}\b",
        text,
    )

    lower = text.lower()

    structure = any(
        keyword in lower
        for keyword in [
            "road",
            "street",
            "lane",
            "h.no",
            "house",
            "flat",
            "apartment",
            "cross",
        ]
    )

    if len(text.split()) < 4 and not structure:
        return "VALIDATION FAILED"

    if not pin or not phone:
        return "NEEDS CUSTOMER CONFIRMATION"

    if not structure:
        return "NEEDS CUSTOMER CONFIRMATION"

    return "VERIFIED"


# ---------------------------------------------------------------------------
# Oracle-style controlled correction experiment
# ---------------------------------------------------------------------------

def _replace_expected_correction(
    text,
    original,
    suggested,
):
    """
    Replace an expected correction while being tolerant of casing.

    This is used ONLY for the controlled labelled experiment.
    It does not represent a human acceptance action.
    """
    import re

    text = str(text or "")
    original = str(original or "").strip()
    suggested = str(suggested or "").strip()

    if not original or not suggested:
        return text

    if original in text:
        return text.replace(
            original,
            suggested,
        )

    pattern = re.escape(original)

    return re.sub(
        pattern,
        suggested,
        text,
        flags=re.IGNORECASE,
    )

    import re

    return re.sub(
        pattern,
        suggested,
        text,
        flags=re.IGNORECASE,
    )


def _oracle_corrected_input(
    raw,
    expected_corrections,
):
    """
    Apply labelled expected corrections for the controlled
    'after expected correction' experiment.

    This is NOT a human acceptance experiment.

    It answers:

        How does the pipeline classify the case when the known
        ground-truth replacements are supplied?
    """
    corrected = str(raw or "")

    for item in expected_corrections or []:
        original = str(
            item.get("original", "")
        ).strip()

        suggested = str(
            item.get("suggested", "")
        ).strip()

        if not original or not suggested:
            continue

        corrected = _replace_expected_correction(
            corrected,
            original,
            suggested,
        )

    return corrected


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

def _run_case(case, cfg):
    start = time.perf_counter()

    result = run_pipeline(
        case["input"],
        cfg,
        accepted=[],
        resolved=[],
    )

    elapsed_ms = (
        time.perf_counter() - start
    ) * 1000

    return result, elapsed_ms


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--no-ai",
        action="store_true",
        help=(
            "Disable LLM extraction/correction for a "
            "deterministic evaluation"
        ),
    )

    args = parser.parse_args()

    dataset_path = (
        ROOT
        / "evaluation"
        / "evaluation_dataset.json"
    )

    output_path = (
        ROOT
        / "evaluation"
        / "evaluation_results.json"
    )

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Evaluation dataset not found: {dataset_path}"
        )

    dataset = json.loads(
        dataset_path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(dataset, list):
        raise ValueError(
            "evaluation_dataset.json must contain a JSON list."
        )

    cfg = _cfg(args.no_ai)

    records = []
    timings = []

    # ---------------------------------------------------------------
    # Main classification evaluation
    # ---------------------------------------------------------------

    for case in dataset:
        try:
            result, elapsed_ms = _run_case(
                case,
                cfg,
            )

            timings.append(elapsed_ms)

            records.append({
                "id": case["id"],
                "category": case["category"],
                "expected_status": case["expected_status"],
                "predicted_status": result["decision"],
                "confidence": result["confidence"],
                "risk": result["risk_level"],
                "corrections": len(
                    result.get(
                        "corrections",
                        [],
                    )
                ),
                "predicted_corrections": result.get(
                    "corrections",
                    [],
                ),
                "expected_corrections": case.get(
                    "expected_corrections",
                    [],
                ),
                "validation_time_ms": round(
                    elapsed_ms,
                    3,
                ),
                "error": None,
            })

        except Exception as exc:
            records.append({
                "id": case["id"],
                "category": case["category"],
                "expected_status": case["expected_status"],
                "predicted_status": "ERROR",
                "confidence": None,
                "risk": None,
                "corrections": 0,
                "predicted_corrections": [],
                "expected_corrections": case.get(
                    "expected_corrections",
                    [],
                ),
                "validation_time_ms": 0,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            })

    valid_records = [
        record
        for record in records
        if record["predicted_status"] != "ERROR"
    ]

    failed_records = [
        record
        for record in records
        if record["predicted_status"] == "ERROR"
    ]

    # ---------------------------------------------------------------
    # Classification metrics
    # ---------------------------------------------------------------

    if valid_records:
        metrics = _classification_metrics(
            valid_records
        )
    else:
        metrics = {
            "accuracy": 0.0,
            "precision_macro": 0.0,
            "recall_macro": 0.0,
            "f1_macro": 0.0,
            "confusion_matrix": {},
        }

    # ---------------------------------------------------------------
    # Correction metrics
    # ---------------------------------------------------------------

    correction_metrics = _correction_metrics(
        valid_records
    )

    # ---------------------------------------------------------------
    # Per-category metrics
    # ---------------------------------------------------------------

    category_metrics = {}

    categories = sorted(
        {
            record["category"]
            for record in valid_records
        }
    )

    for category in categories:
        group = [
            record
            for record in valid_records
            if record["category"] == category
        ]

        correct = sum(
            record["expected_status"]
            == record["predicted_status"]
            for record in group
        )

        category_metrics[category] = {
            "count": len(group),
            "correct": correct,
            "incorrect": len(group) - correct,
            "accuracy": _safe_div(
                correct,
                len(group),
            ),
        }

    # ---------------------------------------------------------------
    # Baseline comparison
    # ---------------------------------------------------------------

    dataset_by_id = {
        case["id"]: case
        for case in dataset
    }

    baseline_records = []

    for record in valid_records:
        source_case = dataset_by_id.get(
            record["id"]
        )

        if not source_case:
            continue

        baseline_prediction = _baseline_status(
            source_case["input"]
        )

        baseline_records.append({
            "id": record["id"],
            "expected_status": record["expected_status"],
            "baseline_status": baseline_prediction,
            "correct": (
                record["expected_status"]
                == baseline_prediction
            ),
        })

    baseline_correct = sum(
        record["correct"]
        for record in baseline_records
    )

    baseline_accuracy = _safe_div(
        baseline_correct,
        len(baseline_records),
    )

    # ---------------------------------------------------------------
    # Controlled after-expected-correction experiment
    # ---------------------------------------------------------------

    after_records = []
    after_timings = []

    for case in dataset:
        expected_corrections = case.get(
            "expected_corrections",
            [],
        )

        if not expected_corrections:
            continue

        corrected_input = _oracle_corrected_input(
            case["input"],
            expected_corrections,
        )

        try:
            start = time.perf_counter()

            after_result = run_pipeline(
                corrected_input,
                cfg,
                accepted=[],
                resolved=[],
            )

            elapsed = (
                time.perf_counter() - start
            ) * 1000

            after_timings.append(elapsed)

            predicted_status = (
                after_result["decision"]
            )

            after_records.append({
                "id": case["id"],
                "expected_status": case["expected_status"],
                "expected_status_after_correction": case.get(
                    "expected_status_after_correction",
                    case["expected_status"],
                ),
                "predicted_status": predicted_status,
                "correct": (
                    predicted_status
                    == case.get(
                        "expected_status_after_correction",
                        case["expected_status"],
                    )
                ),
                "validation_time_ms": round(
                    elapsed,
                    3,
                ),
                "error": None,
            })

        except Exception as exc:
            after_records.append({
                "id": case["id"],
                "expected_status": case["expected_status"],
                "predicted_status": "ERROR",
                "correct": False,
                "validation_time_ms": 0,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
            })

    after_valid = [
        record
        for record in after_records
        if record["predicted_status"] != "ERROR"
    ]

    after_correct = sum(
        record["correct"]
        for record in after_valid
    )

    after_accuracy = _safe_div(
        after_correct,
        len(after_valid),
    )

    # ---------------------------------------------------------------
    # Error analysis
    # ---------------------------------------------------------------

    classification_errors = [
        {
            "id": record["id"],
            "category": record["category"],
            "expected": record["expected_status"],
            "predicted": record["predicted_status"],
            "confidence": record["confidence"],
            "risk": record["risk"],
        }
        for record in valid_records
        if (
            record["expected_status"]
            != record["predicted_status"]
        )
    ]

    false_positives = [
        record["id"]
        for record in valid_records
        if (
            record["expected_status"]
            != record["predicted_status"]
            and record["predicted_status"]
            == "VERIFIED"
        )
    ]

    false_negatives = [
        record["id"]
        for record in valid_records
        if (
            record["expected_status"]
            == "VERIFIED"
            and record["predicted_status"]
            != "VERIFIED"
        )
    ]

    # ---------------------------------------------------------------
    # Final results
    # ---------------------------------------------------------------

    results = {
        "status": (
            "MEASURED"
            if valid_records
            else "NOT_MEASURED"
        ),

        "dataset_size": len(dataset),

        "successful_runs": len(
            valid_records
        ),

        "failed_runs": len(
            failed_records
        ),

        "experimental_setup": {
            "ai_enabled": (
                not args.no_ai
                and bool(Config.GROQ_API_KEY)
            ),
            "model": (
                Config.GROQ_MODEL
                if not args.no_ai
                else "disabled"
            ),
            "geocoding_enabled": (
                Config.GEOCODING_ENABLED
            ),
            "dataset": dataset_path.name,
        },

        "metrics": metrics,

        "per_category": category_metrics,

        "correction_metrics": correction_metrics,

        "before_correction_accuracy": (
            metrics["accuracy"]
        ),

        "after_expected_correction_accuracy": (
            after_accuracy
        ),

        "after_expected_correction_note": (
            "Controlled experiment: labelled expected corrections were "
            "applied before re-validation and compared with the labelled "
            "expected post-correction status. This is not a human "
            "acceptance-rate measurement."
        ),

        "after_expected_correction_cases": len(
            after_valid
        ),

        "after_expected_correction_average_time_ms": (
            _mean(after_timings)
        ),

        "baseline": {
            "description": (
                "Basic format + PIN/phone "
                "presence rules"
            ),
            "accuracy": baseline_accuracy,
            "same_dataset": True,
            "cases_evaluated": len(
                baseline_records
            ),
        },

        "average_validation_time_ms": _mean(
            timings
        ),

        "median_validation_time_ms": _median(
            timings
        ),

        "false_positives": false_positives,

        "false_negatives": false_negatives,

        "classification_errors": (
            classification_errors
        ),

        "records": records,

        "failed_records": failed_records,

        "limitations": [
            (
                "The labelled dataset is a research "
                "test set, not a census of Indian addresses."
            ),
            (
                "Reference geographic data is representative "
                "and not exhaustive."
            ),
            (
                "AI-enabled results depend on the configured "
                "model and prompt version."
            ),
            (
                "External geocoding is optional and may "
                "be unavailable."
            ),
            (
                "Confidence is an evidence score and is "
                "not statistical accuracy."
            ),
            (
                "Human correction acceptance rate is not "
                "measured without recorded human review decisions."
            ),
            (
                "After-correction accuracy is an oracle-style "
                "controlled experiment using labelled expected "
                "corrections."
            ),
        ],
    }

    # ---------------------------------------------------------------
    # Save machine-readable results
    # ---------------------------------------------------------------

    output_path.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------
    # Console summary
    # ---------------------------------------------------------------

    console_summary = {
        "status": results["status"],
        "dataset_size": results["dataset_size"],
        "successful_runs": results["successful_runs"],
        "failed_runs": results["failed_runs"],

        "accuracy": metrics["accuracy"],
        "precision_macro": metrics["precision_macro"],
        "recall_macro": metrics["recall_macro"],
        "f1_macro": metrics["f1_macro"],

        "correction_accuracy": (
            correction_metrics[
                "correction_accuracy"
            ]
        ),

        "correction_recall": (
            correction_metrics[
                "correction_recall"
            ]
        ),

        "correction_f1": (
            correction_metrics[
                "correction_f1"
            ]
        ),

        "correction_acceptance_rate": (
            "NOT_MEASURED"
        ),

        "before_correction_accuracy": (
            results[
                "before_correction_accuracy"
            ]
        ),

        "after_expected_correction_accuracy": (
            results[
                "after_expected_correction_accuracy"
            ]
        ),

        "average_validation_time_ms": (
            results[
                "average_validation_time_ms"
            ]
        ),

        "median_validation_time_ms": (
            results[
                "median_validation_time_ms"
            ]
        ),

        "classification_errors": len(
            classification_errors
        ),

        "output": str(
            output_path
        ),
    }

    print(
        json.dumps(
            console_summary,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()