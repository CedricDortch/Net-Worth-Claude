# Net Worth Analyzer

A local Python CLI that reads an anonymized net worth document, rejects any file containing personal information, analyzes the finances (projections, age percentile, state comparison, credit), and writes a brutally honest report to a static `index.html` with Chart.js charts. Supports single people and couples, and user-set growth assumptions.

This is a public repository. User-facing docs are in `README.md`; keep it in sync when flags, layouts, or scoring change. The original design plan is `docs/planning.md`. The detailed, enforceable rules live in `.claude/rules/` and are the source of truth while coding.

## Principles (never break these)

- **Local only.** No data leaves the user's machine. No uploads, accounts, telemetry, or network calls except loading Chart.js in the browser.
- **No personal information.** The PII scan runs before anything else; a hit raises `PersonalInformationError` and nothing is generated. See `rules/security-pii.md`.
- **Nothing personal in the repo.** Real data files and generated reports (`index.html`) never go into this folder's tracked files, tests, samples, or docs. `.gitignore` covers `index.html`, `reports/`, `private/`, and `*_private.*`.
- **Brutally honest.** Bad finances get a bad report, good finances a good one. Every claim is backed by a number. See `rules/tone.md`.
- **Not financial advice.** Every report includes the disclaimer.

## Commands

Run everything from the project root, using the virtual environment in `.venv` (create it with `python3 -m venv .venv`).

```bash
.venv/bin/pip install -r requirements.txt                       # install dependencies
.venv/bin/python -m networth samples/sample_input.xlsx --open   # analyze a file, write index.html, open it
.venv/bin/python -m networth file.csv --age 31 --state OH --credit-score 742 --out reports/mine.html
.venv/bin/python -m networth household.xlsx --return 6 --inflation 3.5 --contribution 1500
.venv/bin/pytest                                                # run all tests
.venv/bin/pytest networth/tests/test_security.py               # run one test file
.venv/bin/python -m networth.scripts.make_samples               # regenerate samples/*.xlsx|docx|pdf
.venv/bin/python -m networth.scripts.build_reference_data --download /tmp/nw-sources   # refresh benchmark data
```

## Tech stack

Python 3.11+ · `pdfplumber` (PDF) · `python-docx` (Word) · `openpyxl` + `pandas` (Excel/CSV) · stdlib (txt/md/json) · `numpy` (regression, CAGR) · `jinja2` (HTML) · Chart.js `4.4.1` pinned from CDN · `pytest`.

## Project layout

All Python lives in the `networth` package. Modules import each other as `from networth.x import ...` / `from networth import x`.

```text
networth/
  __main__.py          `python -m networth` entry point
  cli.py               argparse, prompts, terminal output, exit codes
  errors.py            custom exceptions (exit_code on each)
  constants.py         supported extensions, US states, analysis thresholds
  models.py            dataclasses: Item, Person, Assumptions, NetWorthProfile
  normalize.py         money/date/percent parsing, categories, state names, validators
  assumptions.py       assumption SPECS (flag, label, range) + resolve()
  formatting.py        format_money, format_percent
  parsers/             one parser per format -> ParsedDocument (parsers/document.py)
  security.py          PII detectors, masking, format_findings()
  extractor.py         ParsedDocument -> Extracted -> NetWorthProfile (section, text, time-series, JSON)
  analysis/            totals, projections, percentile, state_compare, credit, income, score; analyze() -> AnalysisResult
  reference_data.py    the one loader for data/*.json (validated dataclasses)
  report.py            build_report(AnalysisResult) -> Report (verdict, findings, sections, suggestions); render_text()
  render.py            jinja2 -> index.html
  templates/           index.html.j2
  data/                age_percentiles.json, state_data.json, credit_averages.json (generated; never hand-edit)
  scripts/             make_samples.py, build_reference_data.py
  tests/               pytest suite (conftest.py has make_profile, ref, samples fixtures)
samples/               made-up example files, incl. FAKE-PII files that must be rejected
docs/planning.md       the original plan
```

Pipeline: `parsers -> security -> extractor -> analysis -> report -> render`. See `rules/architecture.md`.

## Rules index (`.claude/rules/`)

| Rule | Loaded for |
|---|---|
| `security-pii.md` | always |
| `architecture.md` | always |
| `error-handling.md` | always |
| `python-style.md` | `**/*.py` |
| `input-format.md` | parsers, extractor, models, samples |
| `couples.md` | extractor, models, analysis, report, render |
| `projections.md` | analysis, CLI, models |
| `benchmarks.md` | analysis, data |
| `tone.md` | report, templates |
| `suggestions.md` | report, analysis |
| `html-output.md` | render, templates |
| `testing.md` | tests |

## Future ideas

Refresh data when new SCF (2028) / Census / Experian releases come out · OCR for scanned PDFs · compare by income, not just age · Monte Carlo projections · compare reports year over year · web UI · couples living in different states.
