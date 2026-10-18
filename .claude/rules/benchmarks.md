---
paths:
  - "networth/analysis/**"
  - "networth/data/**"
---

# Benchmarks: Age Percentile, State, Credit, Income, Health Score

## Reference data rules

- All benchmark numbers live in `data/*.json`, **generated** by `networth/scripts/build_reference_data.py` from the official source files. Never hand-edit them; to refresh, rerun the script with `--download` into a directory outside the project.
- Each file records its source (name, URL) and a `retrieved` date. Load them only through `reference_data.load()`, which validates them and raises `ReferenceDataError` if they're missing or damaged.
- Never invent benchmark numbers. If a value can't be verified from the source, leave it out (null) and flag it; don't guess.
- `tests/test_reference_data.py` pins the SCF medians to the Fed's published figures; update those numbers when the source year changes.

| File | Source | Vintage |
|---|---|---|
| `age_percentiles.json` | Federal Reserve **SCF 2025** summary extract (weighted percentiles computed from the public microdata) | 2025 dollars |
| `state_data.json` | Census SIPP state wealth tables (data year 2024, released 2026-07-15); BEA RPP 2024; Census CPS median household income via FRED (2025) | wealth in 2024 dollars |
| `credit_averages.json` | Experian average FICO Score by state, September 2025 (published 2026-03-30); national 713 | — |

## Age percentile (`analysis/percentile.py`, `data/age_percentiles.json`)

- Brackets: under 35, 35–44, 45–54, 55–64, 65–74, 75+ (`ref.age.bracket_for(age)`), plus **fine brackets** under 25, 25–29, 30–34 (`ref.age.fine_bracket_for(age)`), and all households.
- Breakpoints per bracket: 1, 5, 10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95, 99.
- Interpolate linearly between breakpoints. Below the 1st or above the 99th: report "bottom 1%" / "top 1%" rather than extrapolating.
- Report as "top X%" when at or above the median, "bottom X%" when below.
- Report the gap to the median and to the next tier ("$41,000 more to reach the top 25%").
- Under 35: rank against the standard bracket (the headline), and also show the fine bracket as context. Fine brackets have small samples (under 25: ~80 households), so say they're less precise.
- Couples: use the older partner's bracket (see `couples.md`).

SCF 2025 medians (2025 dollars), for reference:

| Age | Median | Mean |
|---|---|---|
| < 35 | $32,820 | $135,718 |
| 35–44 | $156,000 | $669,312 |
| 45–54 | $254,670 | $1,243,609 |
| 55–64 | $411,340 | $1,871,019 |
| 65–74 | $431,900 | $1,870,917 |
| 75+ | $504,600 | $1,949,715 |
| All | $216,100 | $1,231,997 |

## State comparison (`analysis/state_compare.py`, `data/state_data.json`)

Per state (50 + DC): median and mean household net worth, net worth **distribution** (cumulative % of households below $0, $5K, $10K, $25K, $50K, $100K, $250K, $500K; some bounds missing where Census suppressed sub-ranges), households, median household income, RPP (100 = national).

- Compare net worth to the state median raw and **cost-of-living adjusted** (`adjusted = net_worth × 100 / RPP`).
- Estimate the user's percentile within the state by interpolating the distribution; above $500K report only "above the top ~30%" style bounds (no data beyond $500K).
- Compare against the **national figures in the same file** (SIPP), never against SCF numbers: the two surveys measure wealth differently.
- Census suppresses wealth for AK, DE, DC, ND, RI, SD, VT, WY (and the distribution for NE). For those, use national SIPP figures adjusted by the state's RPP, and say so in the report.
- If income history exists, compare the latest income to the state median household income.
- Output example: "Compared with households in Ohio you are above the median; adjusted for cost of living you rank about the 62nd percentile."

## Credit score (`analysis/credit.py`, `data/credit_averages.json`)

| Tier | Range |
|---|---|
| Poor | 300–579 |
| Fair | 580–669 |
| Good | 670–739 |
| Very Good | 740–799 |
| Exceptional | 800–850 |

- Tiers come from the data file (`ref.credit.tier_for(score)`).
- Compare to the national average (`ref.credit.national_average`, 713) and the state average (`ref.credit.state_average(code)`).
- Explain what the tier means for loan approval and interest rates.
- Couples: rate each score; use the lower in the health score.

## Income analysis (only if income history is given)

- Income CAGR.
- Savings rate per year = Δ net worth ÷ income.
- Flag years where net worth fell while income rose.

## Financial health score (`analysis/score.py`)

| Component | Weight | 0–100 score |
|---|---|---|
| Age percentile | 30% | the standard-bracket percentile |
| Net worth trend | 20% | slope ÷ (15% × median income of the age bracket) = s: s ≥ 1 → 100; 0 ≤ s < 1 → 25 + 75s; s < 0 → max(0, 25 + 25s) |
| Debt load | 20% | no debt → 100; debts/assets 10% → 100 down to 100% → 0, minus min(50, high-interest debt ÷ assets × 200) |
| Emergency fund | 10% | cash = 0 → 0 (even without expenses); months of expenses 0/1/3/6 → 0/25/70/100; unknown expenses → missing |
| Credit score | 10% | 300/580/670/740/800 → 0/20/50/80/100 (lower score for couples) |
| State-adjusted standing | 10% | age percentile of net worth × 100 / RPP (i.e. the age ranking at national prices). The in-state SIPP ranking is all-ages, so it's shown as context but not scored. |

If a component has no data (no usable history, or cash > 0 with unknown expenses), redistribute its weight proportionally across the others and list it as missing in the report. Thresholds live in `constants.py`; weights and labels in `analysis/score.py`.

| Score | Grade |
|---|---|
| 90–100 | A |
| 80–89 | B |
| 65–79 | C |
| 50–64 | D |
| < 50 | F |
