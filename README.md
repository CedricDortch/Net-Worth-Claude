# Net Worth Analyzer

Give it a document listing what you own and what you owe. It tells you, honestly, how you're doing:

- where you rank among people your age
- how you compare with your state, adjusted for local prices
- what your net worth could be in 5, 10, 15, and 20 years
- a 0–100 health score and an A–F grade
- the specific things to fix first

It prints the report in the terminal and saves a full version with charts as `index.html`.

**It's brutally honest.** Bad finances get a bad report. Good finances get a good one. Every statement is backed by a number.

**It's private.** Everything runs on your computer. Your file is never uploaded anywhere. Files containing personal information (account numbers, SSNs, addresses, names) are rejected before anything else happens.

> This program gives estimates based on public averages and simple models. It is not financial, tax, or legal advice.

---

## Quick start

You need Python 3.11 or newer.

```bash
cd <this folder>
python3 -m venv .venv                         # one time: create a private Python environment
.venv/bin/pip install -r requirements.txt     # one time: install the libraries

.venv/bin/python -m networth samples/sample_input.xlsx --open
```

That analyzes a made-up sample and opens the report in your browser. To analyze your own file:

```bash
.venv/bin/python -m networth my_net_worth.xlsx --age 31 --state Ohio --credit-score 742 --open
```

If you leave out age, state, or credit score, the program asks for them.

---

## 1. Prepare your file

### Supported formats

Excel (`.xlsx`), CSV, Word (`.docx`), PDF (text-based, not scanned), plain text, Markdown, and JSON. Old `.xls` files: open them in Excel and save as `.xlsx`.

### Keep it anonymous

Use generic labels. Numbers and labels only.

| ✅ Do | ❌ Don't |
|---|---|
| `Bank Account 1: $30,000` | `Chase checking #4421-889-0012: $30,000` |
| `Car 1: $2,000` | `2015 Honda Civic, plate ABC-1234` |
| `House 1: $250,000` | `Home at 123 Main St` |
| `Partner 1`, `Partner 2`, `Joint` | Real names |

Allowed: age, state, credit score, dollar amounts, years, interest rates.

If the security check finds personal information, you'll see exactly where, with the value partly hidden:

```text
SECURITY CHECK FAILED — personal information detected.

  [Line 4]   Possible Social Security number: ***-**-6789
  [Cell C6]  Possible account number: *******0012
```

Remove it and run again. Nothing is analyzed or saved until the file is clean.

**Tip:** write large dollar amounts with `$` or commas (`$12,000,000`). A bare long number like `12000000` in text looks like an account number and gets blocked.

### Layout option A: a spreadsheet with sections

Best for a one-time snapshot. Copy `samples/sample_input.csv` or `samples/sample_input.xlsx`.

| Section | Label | Value | InterestRate | Category | Owner |
|---|---|---|---|---|---|
| Profile | Age | 29 | | | |
| Profile | State | TX | | | |
| Profile | Credit Score | 712 | | | |
| Asset | Bank Account 1 | 30000 | | | |
| Asset | 401k 1 | 45000 | | | |
| Debt | Credit Card 1 | 4200 | 24.9 | | |
| History | 2024 | 42000 | | | |
| History | 2025 | 54800 | | | |
| Income | 2025 | 67000 | | | |
| Expenses | Monthly Expenses | 3200 | | | |

Sections: `Profile`, `Asset`, `Debt`, `History` (net worth by year or date), `Income` (by year), `Expenses`, `Assumptions`. `InterestRate`, `Category`, and `Owner` are optional.

### Layout option B: a tracker you update over time

One row per date, one column per account, plus an optional total column. Copy `samples/sample_timeseries.xlsx`.

| Date | Savings Account | Brokerage | Roth IRA | Credit Card | Total Net Worth |
|---|---|---|---|---|---|
| 1/15/2025 | 5000 | 2000 | 1000 | 1500 | 6500 |
| 2/15/2025 | 5200 | 2300 | 1200 | 1200 | 7500 |

- The latest row is your current snapshot. Every row becomes history.
- Columns named like debts (`Loan`, `Credit Card`, `Mortgage`) are subtracted.
- If your total column doesn't match the sum of the other columns, the report lists the dates so you can fix them.
- Columns of notes are ignored.

### Layout option C: plain text, Word, or PDF

Copy `samples/sample_input.txt`.

```text
Age: 29
State: Texas
Credit Score: 712

ASSETS
Bank Account 1: $30,000
401k 1: $45,000

DEBTS
Credit Card 1: $4,200 (24.9%)

NET WORTH HISTORY
2024: $42,000
2025: $54,800

INCOME HISTORY
2025: $67,000

EXPENSES
Monthly Expenses: $3,200
```

### What makes the report better

| Add this | And you get |
|---|---|
| **Net worth history** (2+ dates, 6+ months apart) | Projections based on your real pace |
| **Income history** | Your savings rate, and whether you're spending your raises |
| **Monthly expenses** | How many months your cash would last in an emergency |
| **Interest rates on debts** | The real yearly cost of your debt, and payoff order |
| **Cash / bank accounts** | Credit for having an emergency fund (none listed counts as $0) |

### Couples

Add `Household Type: Couple`, both ages (`Age 1`, `Age 2`), and both credit scores (`Credit Score 1`, `Credit Score 2`). Optionally mark each item's `Owner` as `Partner 1`, `Partner 2`, or `Joint`. See `samples/sample_couple.xlsx`.

Couples are compared with households in the **older** partner's age group, and the **lower** credit score is the one scored (lenders often use it on joint loans).

---

## 2. Run it

```bash
.venv/bin/python -m networth FILE [options]
```

| Option | What it does |
|---|---|
| `--age 31` | Your age (couples: `--age 34 31`) |
| `--state Ohio` | State name or code (`OH`); "Columbus, Ohio" works too |
| `--credit-score 742` | FICO score (couples: two scores) |
| `--household couple` | `single` or `couple` |
| `--expenses 2500` | Monthly expenses in dollars |
| `--out reports/me.html` | Where to save the HTML report (default: `index.html` in the current folder) |
| `--open` | Open the report in your browser when done |
| `--no-input` | Never ask questions; stop with an error if something's missing |

Command-line values override the file.

### Growth assumptions

Projections use these defaults. You can change them with flags or an `Assumptions` section in your file. Flags win over the file.

| Flag | Default | Allowed |
|---|---|---|
| `--return` | 7% a year on investments | −10 to 20 |
| `--spread` | ±3 points for conservative / optimistic | 0 to 10 |
| `--inflation` | 3% | 0 to 15 |
| `--cash-rate` | 2% on cash | 0 to 10 |
| `--home-growth` | 3% on real estate | −10 to 15 |
| `--car-depreciation` | 15% a year | 0 to 50 |
| `--contribution` | Learned from your history | $0 or more per month |
| `--income-growth` | Learned from your income history | −20 to 30 |

Unrealistic assumptions get challenged in the report. Assuming a 14% return, for example, triggers a warning and a side-by-side comparison with the defaults.

**Recommended:** if you know roughly what you save each month, pass `--contribution`. Without it, savings are estimated from how fast your net worth grew, and a short history during a strong market can overstate them. The report warns you when that's likely.

---

## 3. Read the report

| Section | What it tells you |
|---|---|
| **Grade and verdict** | The overall picture, what's holding your score back, what's working |
| **What you own and owe** | Totals by category, high-interest debt, emergency cash |
| **Where you're headed** | Your history and a 20-year projection with a conservative–optimistic range, in future and today's dollars |
| **You vs. people your age** | Your percentile among households your age (Federal Reserve data) |
| **You vs. your state** | Your state's median, and your rank once prices are accounted for |
| **Credit score** | Your tier, and how you compare with your state and the U.S. |
| **Income and savings** | How much of your income you actually keep |
| **Final summary** | The six parts of your score and how much each counts |
| **What to do next** | Up to 7 actions, most urgent first |

### How the score works

| Part | Weight | Full marks for |
|---|---|---|
| Rank for your age | 30% | Being near the top for your age |
| Net worth trend | 20% | Growing by 15% of a typical income for your age each year |
| Debt load | 20% | Little or no debt, no high-interest debt |
| Emergency fund | 10% | 6+ months of expenses in cash |
| Credit score | 10% | 800+ |
| Rank adjusted for cost of living | 10% | Ranking high for your age at national prices |

Parts without data are left out and their weight is shared by the rest. Grades: A 90+, B 80–89, C 65–79, D 50–64, F below 50.

**About projections:** they assume your recent pace continues. A fast past growth rate is never compounded forward (growing 150% a year from a small start doesn't last). Instead, the model separates what market returns explain from what you saved, and projects your savings forward.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SECURITY CHECK FAILED` | Remove the listed items. If a flagged "account number" is really a dollar amount, add `$` or commas. |
| `'.xyz' files are not supported` | Save as `.xlsx`, `.csv`, `.docx`, `.pdf`, or `.txt`. |
| `has no text layer (it looks like a scanned image)` | Scanned PDFs can't be read. Use the original spreadsheet or type it into a template. |
| `No assets or debts were found` | Check your layout against the samples in `samples/`. |
| Charts don't show in `index.html` | They need an internet connection to load the chart library. All numbers are still in the tables. |
| The report says "No cash listed" but you have savings | Add a cash or bank account line. |

---

## Where the benchmarks come from

| Data | Source |
|---|---|
| Net worth by age | Federal Reserve, 2025 Survey of Consumer Finances (percentiles computed from the public data file) |
| State net worth | U.S. Census Bureau, State-Level Wealth Tables 2024 (SIPP) |
| Cost of living | U.S. Bureau of Economic Analysis, Regional Price Parities 2024 |
| State income | U.S. Census Bureau median household income (via FRED), 2025 |
| Credit score averages | Experian, September 2025 |

The Census Bureau doesn't publish wealth figures for AK, DE, DC, ND, RI, SD, VT, and WY. For those states the report uses national figures adjusted for local prices and says so.

---

## For developers

```bash
.venv/bin/pytest                                   # run the tests
.venv/bin/python -m networth.scripts.make_samples   # rebuild samples/*.xlsx, .docx, .pdf from the .csv/.txt sources
.venv/bin/python -m networth.scripts.build_reference_data --download /tmp/nw-sources   # refresh the benchmark data
```

```text
networth/                all the Python code
├── __main__.py          `python -m networth` entry point
├── cli.py               command line: arguments, prompts, output, exit codes (0 ok, 1 bad input, 2 personal info)
├── parsers/             read each file type into raw lines and tables
├── security.py          personal-information detectors and masking
├── extractor.py         raw content -> NetWorthProfile (section, text, time-series, JSON layouts)
├── normalize.py         money, dates, states, categories, validation
├── assumptions.py       growth assumptions: defaults < file < flags
├── analysis/            totals, projections, percentiles, state, credit, income, score
├── reference_data.py    loads and checks data/*.json
├── report.py            the honest written report and suggestions
├── render.py            index.html (templates/index.html.j2, Chart.js 4.4.1)
├── data/                benchmark data (generated; don't hand-edit)
├── templates/           the HTML report template
├── scripts/             make_samples.py, build_reference_data.py
└── tests/               pytest suite
samples/                 made-up example files, including fake-PII files that must be rejected
docs/planning.md         the original design plan
```

Design rules for contributors (and for Claude Code) live in `.claude/CLAUDE.md` and `.claude/rules/`.

Optional: install `xlrd` to read old `.xls` files directly.

---

## License

[MIT](LICENSE). Free to use, copy, modify, and share, including commercially, as long as the license notice is kept. The benchmark data in `networth/data/` comes from public U.S. government sources and Experian; see "Where the benchmarks come from" above.
