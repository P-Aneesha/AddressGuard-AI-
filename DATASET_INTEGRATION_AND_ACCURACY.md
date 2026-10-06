# Dataset Integration, Spelling Correction and Accuracy

## Architecture

Raw address
-> AI address understanding
-> deterministic parser/normalizer
-> India Post + LGD + postal-LGD reference checks
-> fuzzy spelling candidates
-> Groq contextual correction assistance
-> human approval
-> complete re-parse/re-validation
-> confidence/risk/decision

## Reference data

1. `data/india_post_pincode.csv`
2. `data/lgd_villages.csv`
3. `data/postal_lgd_mapping.csv`
4. `data/reference_index.sqlite3` is the runtime index built from the three CSV files.

Important: `lgd_villages.csv` does not contain a PIN column, so the system does not claim a direct village-to-PIN proof from LGD alone. PIN evidence comes from the India Post dataset and postal-LGD mapping.

## Spelling correction

- State/district/city/locality: whole-India reference candidates + fuzzy similarity + geographic context.
- Building/street/landmark: generic fuzzy matching plus Groq context when available; these fields are not falsely claimed to be covered by the official village/PIN datasets.
- No correction is silently applied.
- Accepted corrections trigger complete re-validation.

## Accuracy

The evaluation script computes metrics from the labelled dataset. The current deterministic run is measured, not hardcoded. Use:

`python evaluation/run_evaluation.py --no-ai`

Do not present the 34-case result as real-world accuracy. It is accuracy on the supplied labelled evaluation set.
