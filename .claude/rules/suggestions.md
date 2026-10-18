---
paths:
  - "networth/report.py"
  - "networth/analysis/**"
---

# Suggestions Engine

- Rule-based, in `report.py` (`_suggestions`). Each `Suggestion` has: `key`, `title` (what to do), `reason` (the number that triggered it), `impact` (expected effect in words), `impact_dollars` (or None), `priority`.
- Priority: **1** = protect yourself now (high-interest debt, no emergency fund, shrinking net worth), **2** = important, **3** = optimize.
- Rank by **priority first**, then by `impact_dollars` (None last). Show at most 7. (Priority comes first because protection items like an emergency fund have no dollar figure but matter most.)

## Rules

| Trigger | Suggestion |
|---|---|
| Any debt with interest ≥ 8% | Avalanche payoff (highest rate first). Show yearly interest saved. |
| Emergency fund < 3 months | Build 3–6 months in a high-yield savings account before investing more. |
| No retirement assets | Open a 401(k) (get any employer match) or IRA. Show the 20-year value of $300/month at the expected return. |
| Credit score < 670 | Pay on time, keep card use under 30% (ideally 10%), keep old cards open, check reports for errors. |
| Vehicles > 30% of assets | Stop buying depreciating assets; keep the current car longer. |
| Negative net worth trend | Track spending for 30 days; cut the 3 largest non-essential costs. |
| Savings rate < 10% | Automate savings; target 15–20% of income. |
| Income rising, net worth flat | Lifestyle creep: save at least half of every raise. |
| Cash > 12 months of expenses | Move the extra into investments. |
| Below state median (cost-of-living adjusted) | Focus on income growth: skills, certifications, job changes. |
| Grade A or B, or top 25% for age with no high-interest debt | Optimize: tax-advantaged accounts, max contributions, diversify. (No specific contribution limits unless verified.) |
| Employer stock (label: company stock / employer / RSU / ESPP) ≥ 10% of assets | Sell down below 10% and diversify. |
| Projection contributions come from < 3 years of history or a > 30%/yr past growth rate | Find out actual monthly savings and rerun with `--contribution`. |
| Couple: partner credit gap ≥ 60 points (and neither is below 670) | Improve the lower score before applying for joint loans. If one is below 670, the credit suggestion names that partner instead. |
| Couple: one partner holds > 75% of debt | Make a joint payoff plan for that partner's highest-rate debt. |

Suggestion wording follows `tone.md`.
