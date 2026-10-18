# Architecture

## Pipeline

```text
input file
   │
   ▼
parsers/          → raw text + tables
   │
   ▼
security.py       → PII scan ──(found)──► PersonalInformationError → exit 2
   │
   ▼
extractor.py      → NetWorthProfile
   │
   ▼
analysis/         → totals, projections, percentile, state, credit, score
   │
   ▼
report.py         → honest summary text + suggestions
   │
   ▼
render.py + templates/index.html.j2 → index.html
```

## Module boundaries

- `parsers/__init__.py` picks a parser by file extension. Parsers only return raw content (`ParsedDocument`: lines of text + list of tables with cell locations). No interpretation.
- `security.py` only reads `ParsedDocument`. It never modifies it.
- `extractor.py` works in two steps: `extract(doc)` reads everything into `Extracted` (all optional, profile fields still raw text); `build_profile(...)` takes validated profile fields and returns `NetWorthProfile` plus notes about missing data.
- `normalize.py` holds value parsing (money, dates, percents), categorization keywords, state normalization, and validators that raise `InvalidInputError`.
- `assumptions.py` holds `SPECS` (flag, file label, range for each assumption) and `resolve()` (defaults < file < CLI, sources recorded).
- `formatting.py` holds `format_money` / `format_percent`; all display formatting goes through it.
- `analysis/` modules are **pure functions**: take a `NetWorthProfile` (and reference data), return result dataclasses. No I/O, no printing, no prompts.
- `report.py` turns analysis results into text and suggestions. All wording lives here, not in `analysis/`.
- `render.py` is the only module that writes `index.html`. All chart data is embedded in the page as JSON.
- `networth/cli.py` is the only module that handles argv, interactive prompts, printing to the terminal, and exit codes. Profile fields resolve as **CLI flag > file > prompt**; an invalid value from the file or CLI is re-asked when prompting is allowed.
- Reference data is loaded from `data/*.json` through one loader; never hard-code benchmark numbers in analysis code.

## Data model (`models.py`)

```python
@dataclass(frozen=True)
class Item:
    label: str              # "Bank Account 1"
    value: float            # 30000.0 (debts: positive balance)
    category: str           # "cash"
    interest_rate: float | None = None   # debts only, percent
    owner: str = "joint"    # "partner1" | "partner2" | "joint" (couples only)

@dataclass(frozen=True)
class Person:
    age: int
    credit_score: int

@dataclass(frozen=True)
class Assumptions:
    investment_return: float = 7.0      # % per year, expected scenario
    scenario_spread: float = 3.0        # ± points for conservative / optimistic
    inflation: float = 3.0
    cash_rate: float = 2.0
    home_appreciation: float = 3.0
    vehicle_depreciation: float = 15.0
    monthly_contribution: float | None = None   # None = use the trend
    income_growth: float | None = None          # None = use income history
    source: dict[str, str] = field(default_factory=dict)  # field -> "default" | "file" | "cli"

@dataclass(frozen=True)
class NetWorthProfile:
    household_type: str     # "single" | "couple"
    people: tuple[Person, ...]   # 1 for single, 2 for couple
    state: str              # normalized 2-letter code
    assets: tuple[Item, ...]
    debts: tuple[Item, ...]
    net_worth_history: dict[date, float]  # date -> household net worth, sorted (a bare year = Dec 31)
    income_history: dict[int, float]      # year -> household income
    monthly_expenses: float | None
    assumptions: Assumptions
    as_of: date | None = None             # current snapshot date (latest time-series row)
    notes: tuple[str, ...] = ()           # how the file was read / what's missing
    # properties: total_assets, total_debts, net_worth
```

History is keyed by **date**, not year, so monthly trackers keep every point.

Change this model in `models.py` first, then update dependents; keep this rule in sync.
