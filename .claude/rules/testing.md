---
paths:
  - "networth/tests/**"
---

# Testing

- `pytest`. One test file per module (`tests/test_security.py`, `tests/test_projections.py`, …). Shared fixtures in `tests/conftest.py`: `make_profile(...)` builds a `NetWorthProfile` with defaults (override only what the test is about), `ref` is the loaded reference data, `samples` is the samples folder.
- Build test inputs with fixtures/factories, not by reading the real samples, except in parser and end-to-end tests.
- Use `tmp_path` for any output; tests never write into the project folder.
- Interactive prompts are injected (`prompt_fn`) or disabled (`--no-input`) so tests never block.
- Run `pytest` after every change; a milestone is not done until its tests pass.

## Required coverage

**Security (highest priority)**
- Each detector catches real examples: SSN, account numbers, routing numbers, Luhn-valid cards, addresses, ZIPs, phones, emails, VINs, plates, DOB, names.
- Each detector ignores safe values: `$30,000`, `2024`, credit score `712`, `Bank Account 1`, `Partner 1`.
- End-to-end: a file with an account number raises `PersonalInformationError`, exits 2, and creates **no** `index.html`.
- Masking: the printed message never contains the full PII value.

**Parsers**
- The same data in PDF, DOCX, XLSX, CSV, and TXT produces an identical `NetWorthProfile`.

**Analysis**
- Projection math with known inputs/outputs; negative trends go down; zero and negative net worth handled.
- Percentile interpolation at breakpoints, between them, below 10th, above 99th.
- Cost-of-living adjustment.
- Credit tier boundaries: 579/580, 669/670, 739/740, 799/800.
- Score/grade boundaries; weight redistribution when data is missing.

**Couples**
- Combined totals, per-partner breakdown, older-partner bracket, lower credit score used, missing partner fields prompted.

**Assumptions**
- CLI > file > default precedence; sources recorded.
- Out-of-range and non-numeric values rejected.
- Unrealistic values trigger the honesty check and the side-by-side default projection.

**Tone**
- A bad profile produces D/F verdict language; a strong profile produces A/B.

**End-to-end**
- Each sample produces `index.html` containing every expected chart canvas and no raw input text beyond labels.
