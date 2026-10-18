---
paths:
  - "networth/parsers/**"
  - "networth/extractor.py"
  - "networth/models.py"
  - "samples/**"
---

# Input Format

## Supported file types

`.pdf`, `.docx`, `.xlsx`, `.xls`, `.csv`, `.txt`, `.md`, `.json`. Anything else raises `UnsupportedFileError` listing these.

## Required fields

| Field | Format | Validation |
|---|---|---|
| Household type | `Single` or `Couple` | Default `Single` |
| Age | Integer (couple: `Age 1`, `Age 2`) | 16–110 |
| State | 2-letter code or full name (`TX` / `Texas`) | 50 states + DC; normalize to 2-letter code |
| Credit score | Integer (couple: `Credit Score 1`, `Credit Score 2`) | 300–850 |
| Assets | Label + dollar value | Values ≥ 0 |
| Debts | Label + balance (+ optional interest rate) | Values ≥ 0 |

Missing age / state / credit score → prompt (see `error-handling.md`). They can also be passed as CLI flags, which override the file: `--age 31`, `--state Ohio`, `--credit-score 742`, `--household couple`, couples `--age 34 31 --credit-score 745 668`, and `--expenses 2500`. State accepts a code, a name, or "City, State" (only the state is kept).

## Optional fields

| Field | Format | Used for |
|---|---|---|
| Net worth history | Year → net worth | Trend and projections |
| Income history | Year → annual income (couple: may give `Income 1` / `Income 2`, summed) | Savings rate, income growth, fallback projection |
| Monthly expenses | Dollars | Emergency fund months |
| Monthly contributions | Dollars | Projections |
| Assumptions | `Assumptions` section | Override projection rates (see `projections.md`) |

## Labels

Every item uses a generic label + number. Real identifiers are rejected by the security check.

- ✅ `Bank Account 1: $30,000` · `Car 1: $2,000` · `Student Loan 1: $18,000 at 5.5%` · `401k 1: $45,000`
- ❌ `Chase checking #4421-889-0012` · `2015 Honda Civic, plate ABC-1234` · `Home at 123 Main St`

## Categories (keyword match on label, case-insensitive)

An explicit `Category` column always overrides keywords.

| Asset category | Keywords |
|---|---|
| cash | bank, checking, savings, cash, money market, CD |
| investments | brokerage, stock, ETF, bond, crypto, investment |
| retirement | 401k, 403b, 457, IRA, Roth, pension, TSP, HSA |
| real_estate | house, home, property, condo, land, rental |
| vehicles | car, truck, motorcycle, boat, vehicle |
| other | anything else |

| Debt category | Keywords |
|---|---|
| mortgage | mortgage, home loan, HELOC |
| auto | car loan, auto loan |
| student | student loan |
| credit_card | credit card, card |
| personal | personal loan, medical, payday |
| other | anything else |

Check debt keywords before asset keywords for debt rows ("car loan" is auto debt, not a vehicle asset).

## Tabular layout (xlsx / csv)

Columns: `Section, Label, Value, InterestRate, Category, Owner`. Sections: `Profile`, `Asset`, `Debt`, `History`, `Income`, `Expenses`, `Assumptions`. Header matching is case-insensitive; `InterestRate`, `Category`, `Owner` are optional.

```csv
Section,Label,Value,InterestRate,Category
Profile,Age,29,,
Profile,State,TX,,
Profile,Credit Score,712,,
Asset,Bank Account 1,30000,,
Asset,Car 1,2000,,
Asset,401k 1,45000,,
Debt,Student Loan 1,18000,5.5,
Debt,Credit Card 1,4200,24.9,
History,2021,8000,,
History,2022,19000,,
History,2023,31000,,
History,2024,42000,,
History,2025,54800,,
Income,2021,48000,,
Income,2022,52000,,
Income,2023,58000,,
Income,2024,63000,,
Income,2025,67000,,
Expenses,Monthly Expenses,3200,,
```

A table with `Label` + `Value` headers but no `Section` column is also accepted; rows are routed by label (profile keys, years → history, debt keywords → debts, otherwise assets).

## Time-series layout (xlsx / csv / docx tables)

A common personal tracker: one row per date, one column per account, optional total column.

```csv
Date,Savings Account,Brokerage,Roth IRA,Credit Card,Total Net Worth,
1/15/2025,5000,2000,1000,1500,6500,
3/15/2025,5400,2100,1400,900,8000,Market dip
```

- Detected when the first header is Date/Year/Month/As of/Period, or most first-column values are dates.
- Dates may be real Excel dates or text (`12/10/2024`, `2025-08-04`, `Aug 2025`, `2025`). Rows are sorted by date.
- Columns with debt keywords are debts; others are assets (categorized by keyword).
- A column with "total" or "net worth" in its header is the total. Its values become `net_worth_history`; without one, history = assets − debts per row. Rows where the total ≠ the column sum are listed in a note with dates and differences.
- The **latest** row gives the current items and `as_of`. Empty or $0 cells in that row are skipped.
- Columns without a header or with mostly text (notes like "Vacation Month") are ignored.
- A dated table with no total column and no column that looks like an account or debt (e.g. a weight log on another sheet of the same workbook) is ignored entirely, with a note naming the sheet and columns.

## Text layout (txt / md / docx / pdf)

`Key: value` profile lines, then headed sections (`ASSETS`, `DEBTS`, `NET WORTH HISTORY`, `INCOME HISTORY`, `ASSUMPTIONS`), headings case-insensitive. Debt interest rate in parentheses.

```text
Age: 29
State: Texas
Credit Score: 712

ASSETS
Bank Account 1: $30,000
Car 1: $2,000

DEBTS
Student Loan 1: $18,000 (5.5%)
Credit Card 1: $4,200 (24.9%)

NET WORTH HISTORY
2021: $8,000
2022: $19,000
```

Markdown headings (`#`) and bullets (`-`, `*`) are fine. Headings: ASSETS, DEBTS/LIABILITIES, NET WORTH HISTORY, INCOME HISTORY, EXPENSES, ASSUMPTIONS, PROFILE. Lines under EXPENSES (other than "Monthly Expenses") are summed. Without headings, lines are routed by label. Values may be written `$30,000`, `30000`, `45k`, `$1.2M`; owners as `(Partner 1)`.

## JSON

Same keys as the section layout: `age`, `state`, `credit_score`, `household_type`, `ages: [34, 31]`, `credit_scores: [...]`, `assets`/`debts` (lists of `{label, value, interest_rate, category, owner}`), `net_worth_history` / `income_history` (`{"2025": 54800}` or lists of `{date, value}`), `monthly_expenses`, `assumptions` (`{"Investment Return": 6}`).

## Samples

`samples/` holds `sample_input.{csv,txt,xlsx,docx,pdf,json}` (identical data — tests compare them), `sample_couple.{csv,xlsx}`, `sample_timeseries.{csv,xlsx}`, and `sample_with_pii.{txt,csv,xlsx}` (FAKE PII, must fail the check). Edit the csv/txt sources, then run `.venv/bin/python -m networth.scripts.make_samples` to regenerate xlsx/docx/pdf. Clean samples must pass the security check.
