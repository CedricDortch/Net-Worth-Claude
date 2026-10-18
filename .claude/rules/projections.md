---
paths:
  - "networth/analysis/**"
  - "networth/cli.py"
  - "networth/models.py"
  - "networth/extractor.py"
---

# Snapshot, Projections, and Growth Assumptions

## Current snapshot (`analysis/totals.py`)

- Total assets, total debts, **net worth = assets − debts**
- Debt-to-asset ratio (handle zero assets without dividing by zero)
- Liquid net worth = cash + investments − credit card debt
- Asset mix and debt mix by category (% of total)
- Weighted average debt interest rate
- High-interest debt total (rate ≥ 8%, constant in `constants.py`)
- Emergency fund months = cash ÷ monthly expenses (None if expenses unknown)
- Depreciating asset share = vehicles ÷ total assets

## Projections: 5, 10, 15, 20 years (`analysis/projections.py`)

**Model:** simulate month by month from the current snapshot. Investments + retirement grow at the scenario return, cash at `cash_rate`, real estate at `home_appreciation`, vehicles lose `vehicle_depreciation`, "other" is flat. Debts accrue their own rate (0% if missing, with a note). The monthly contribution pays debts highest-rate first, then is invested; a negative contribution drains cash, then investments, then becomes new debt.

**Where the contribution comes from (first that applies):**
1. `--contribution` / file assumption (`contribution_source = "assumption"`).
2. History (2+ points spanning ≥ 6 months): fit a linear trend ($/year) and an exponential fit (CAGR). Contribution = linear slope − the market growth the expected assumptions explain (today's balances × rates, scaled to the average history balance). `"history"`.
   - **Never extrapolate the historical CAGR.** Compounding a fast start from a small base (e.g. 150%/year) is fantasy. CAGR and both R² values are reported as facts about the past only.
   - When the trend is fast, the report should say that markets may have beaten the assumed return, so real savings may be lower, and suggest `--contribution`.
3. Income only: latest income × `DEFAULT_SAVINGS_RATE` (10%), with a note. `"income"`.
4. Nothing: $0, with a note pointing to `--contribution`. `"none"`.

Contributions grow yearly by `income_growth` (assumption), else income-history CAGR capped at `MAX_DERIVED_INCOME_GROWTH` (10%, with a note if capped), else 0.

**Three scenarios:**

| Scenario | Investment return | Contributions |
|---|---|---|
| Conservative | return − spread | contribution − 25% of its size |
| Expected | return | contribution |
| Optimistic | return + spread | contribution + 25% of its size |

- **Negative trends project downward.** Never clamp a projection at zero.
- When any assumption isn't a default, also compute `default_expected` (the expected path at default assumptions) for the "your vs. default" comparison.
- Output both nominal and inflation-adjusted values.
- Include the user's age at each milestone (both ages for couples).

## Custom growth assumptions

Precedence: **CLI flag > input file `Assumptions` section > default.** Record each value's source in `Assumptions.source`.

| Flag | File label | Meaning | Default | Allowed range |
|---|---|---|---|---|
| `--return` | Investment Return | Expected yearly return (%) | 7 | −10 to 20 |
| `--spread` | Scenario Spread | ± points for conservative/optimistic | 3 | 0 to 10 |
| `--inflation` | Inflation | Yearly inflation (%) | 3 | 0 to 15 |
| `--cash-rate` | Cash Rate | Yearly interest on cash (%) | 2 | 0 to 10 |
| `--home-growth` | Home Growth | Real estate appreciation (%) | 3 | −10 to 15 |
| `--car-depreciation` | Car Depreciation | Vehicle depreciation (%) | 15 | 0 to 50 |
| `--contribution` | Monthly Contribution | Monthly savings ($) | trend | ≥ 0 |
| `--income-growth` | Income Growth | Yearly income growth (%) | from history | −20 to 30 |

- Out of range or non-numeric → `InvalidAssumptionError` showing the range, exit 1.
- The report always lists every assumption used and its source.

## Honesty check on assumptions

If an assumption is unrealistic, the report says so **and** shows the default-assumption projection next to the user's:

| Condition | Message idea |
|---|---|
| Return > 10% | "You assumed 14% a year. The long-run stock market average is closer to 7–10%. Here is what happens at 7%." |
| Contribution > 2× historical average savings | "You assumed you'll save $3,000 a month. Your history shows about $900. Here are both." |
| Inflation < 1% | "Zero inflation is not realistic. Your future dollars will buy less." |
| Home growth > 6% or car depreciation < 5% | Explain the typical range and show defaults |

When assumptions differ from defaults, `index.html` shows both a "your assumptions" line and a "default assumptions" line.
