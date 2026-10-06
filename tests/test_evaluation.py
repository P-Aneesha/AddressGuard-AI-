import json
from pathlib import Path


def test_evaluation_dataset_is_labelled_and_nonempty():
    path = Path(__file__).resolve().parents[1] / "evaluation" / "evaluation_dataset.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) >= 20
    assert all(item.get("id") and item.get("category") and item.get("expected_status") for item in data)
    assert all(item["expected_status"] in {
        "VERIFIED", "NEEDS CUSTOMER CONFIRMATION", "SUSPICIOUS", "FAKE ADDRESS"
    } for item in data)
