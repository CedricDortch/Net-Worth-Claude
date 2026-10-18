---
paths:
  - "networth/extractor.py"
  - "networth/models.py"
  - "networth/analysis/**"
  - "networth/report.py"
  - "networth/render.py"
  - "networth/templates/**"
---

# Couples / Combined Household

## Input

- `Household Type: Couple` + `Age 1`, `Age 2`, `Credit Score 1`, `Credit Score 2`.
- Partners are always "Partner 1" and "Partner 2". Real names are blocked by the security check.
- Optional `Owner` column per item: `Partner 1`, `Partner 2`, or `Joint`. Missing → `Joint`.
- History and income are combined household totals. `Income 1` / `Income 2` rows are summed per year.
- v1: both partners live in the same state.

```csv
Section,Label,Value,InterestRate,Category,Owner
Profile,Household Type,Couple,,,
Profile,Age 1,34,,,
Profile,Age 2,31,,,
Profile,State,GA,,,
Profile,Credit Score 1,745,,,
Profile,Credit Score 2,668,,,
Asset,Bank Account 1,22000,,,Joint
Asset,401k 1,61000,,,Partner 1
Asset,401k 2,18000,,,Partner 2
Asset,House 1,340000,,,Joint
Debt,Mortgage 1,285000,6.1,,Joint
Debt,Student Loan 1,27000,5.0,,Partner 2
History,2023,71000,,,
History,2024,98000,,,
History,2025,129000,,,
```

## Analysis

| Analysis | Single | Couple |
|---|---|---|
| Net worth | Individual | Combined household + per-partner breakdown by `Owner` |
| Age percentile | User's age | **Older partner's** age bracket (SCF groups households by the head's age); report says so |
| State comparison | Household medians | Household medians |
| Credit score | One score | Each rated separately; the **lower** score is used in the health score and flagged for joint loans |
| Income / savings rate | Individual | Combined household income |
| Suggestions | Individual | Household + partner-specific |

## Reporting

- Call out imbalances honestly: "Partner 2 holds 90% of the household's debt."
- Flag large credit gaps: "Partner 2's credit score of 668 will raise your mortgage rate."
- Projection milestones show both partners' ages ("In 10 years (ages 44 and 41)").
- `index.html` adds a stacked bar of assets and debts by Partner 1 / Partner 2 / Joint. Hide it for single users.
- Every code path that handles `people` must work for both `len(people) == 1` and `== 2`.
