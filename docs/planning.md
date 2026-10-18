# Net Worth Analyzer — Planning Document

> Status: **Built (M1–M7 complete)** · Last updated: 2026-10-18. See README.md for how to use the program.
>
> This is the original planning document. The working rules for coding now live in `.claude/rules/` and `.claude/CLAUDE.md`. If they differ, the rules win.

---

## 1. Overview

The Net Worth Analyzer is a local Python command-line program. A user gives it one document that lists their finances, and it produces an honest report as an `index.html` page with charts.

**What it does:**

1. Reads a net worth document (PDF, Word, Excel, CSV, text, or JSON).
2. Scans the document for personal information. If it finds any, it stops and tells the user to remove it.
3. Pulls out assets, debts, age, state, credit score, and any history of net worth and income.
4. Analyzes the data:
   - Projects net worth 5, 10, 15, and 20 years out.
   - Ranks the user against people their age (percentile).
   - Compares the user to people in their state.
   - Rates their credit score.
5. Writes a **brutally honest** summary and a ranked list of suggestions.
6. Generates `index.html` with bar graphs, histograms, and other charts.

**Principles:**

- **Local only.** No data leaves the user's computer. No accounts, no uploads, no tracking.
- **No personal information.** Input must be anonymized ("Bank Account 1", "Car 1"). The program refuses anything that looks like sensitive data.
- **Honest.** Bad finances get a bad report and good finances get a good one. The program never softens the facts.

**Usage:**

```bash
python networth.py my_networth.xlsx
# -> writes index.html in the current folder and prints a short summary
python networth.py my_networth.pdf --out report/index.html
python networth.py household.xlsx --return 6 --inflation 3.5 --contribution 1500
# -> custom growth assumptions (see section 6.2.1)
```

Both **single people and couples** are supported. Couples can enter a combined household net worth (see section 3.7).

---

## 2. Tech Stack

| Purpose | Tool |
|---|---|
| Language | Python 3.11+ |
| PDF parsing | `pdfplumber` |
| Word parsing | `python-docx` |
| Excel / CSV parsing | `openpyxl`, `pandas` |
| Text / JSON | Python standard library |
| Data model | `dataclasses` |
| Math / projections | `numpy` (linear regression, CAGR) |
| HTML generation | `jinja2` template → static `index.html` |
| Charts | Chart.js (pinned CDN version, e.g. `chart.js@4.4.1`) |
| Tests | `pytest` |

Dependencies live in `requirements.txt`.

---

## 3. User Input Specification

### 3.1 Supported file types

`.pdf`, `.docx`, `.xlsx`, `.xls`, `.csv`, `.txt`, `.md`, `.json`

Any other type causes an error that lists the supported formats.

### 3.2 Required fields

| Field | Format | Validation |
|---|---|---|
| Household type | `Single` or `Couple` | Defaults to `Single` if missing |
| Age | Integer (for a couple: `Age 1` and `Age 2`) | 16–110 |
| State | 2-letter code or full name (e.g. `TX` or `Texas`) | Must be one of the 50 US states or DC |
| Credit score | Integer (for a couple: `Credit Score 1` and `Credit Score 2`) | 300–850 |
| Assets | Label + dollar value | At least 0 entries; values ≥ 0 |
| Debts | Label + balance (+ optional interest rate) | Values ≥ 0 |

If age, state, or credit score is missing, the CLI **asks the user for it interactively** instead of failing.

### 3.3 Optional fields (improve accuracy)

| Field | Format | Used for |
|---|---|---|
| Net worth history | Year → net worth | Growth trend and projections |
| Income history | Year → annual income | Savings rate, income growth, fallback projections |
| Monthly expenses | Dollar amount | Emergency fund coverage (months) |
| Monthly retirement / investment contributions | Dollar amount | Projections |
| Growth assumptions | `Assumptions` section (see 6.2.1) | Override default projection rates |

### 3.4 Anonymized labeling rules

Every item uses a generic label and a number:

- ✅ `Bank Account 1: $30,000`
- ✅ `Car 1: $2,000`
- ✅ `Student Loan 1: $18,000 at 5.5%`
- ✅ `401k 1: $45,000`
- ❌ `Chase checking #4421-889-0012: $30,000`
- ❌ `2015 Honda Civic, plate ABC-1234: $2,000`
- ❌ `Home at 123 Main St: $250,000`

### 3.5 Categories

Items are put into categories by keywords in their label:

| Asset category | Keywords |
|---|---|
| Cash | bank, checking, savings, cash, money market, CD |
| Investments | brokerage, stock, ETF, bond, crypto, investment |
| Retirement | 401k, 403b, IRA, Roth, pension, TSP |
| Real estate | house, home, property, condo, land, rental |
| Vehicles | car, truck, motorcycle, boat, vehicle |
| Other | anything else |

| Debt category | Keywords |
|---|---|
| Mortgage | mortgage, home loan, HELOC |f
| Auto | car loan, auto loan |
| Student | student loan |
| Credit card | credit card, card |
| Personal | personal loan, medical, payday |
| Other | anything else |

A user can also add an explicit `Category` column to override keyword matching.

### 3.6 Sample input template

Spreadsheet / CSV layout (one sheet or sections in a document):

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

Plain-text / Word / PDF layout:

```text
Age: 29
State: Texas
Credit Score: 712

ASSETS
Bank Account 1: $30,000
Car 1: $2,000
401k 1: $45,000

DEBTS
Student Loan 1: $18,000 (5.5%)
Credit Card 1: $4,200 (24.9%)

NET WORTH HISTORY
2021: $8,000
2022: $19,000
...

INCOME HISTORY
2021: $48,000
...
```

Templates `sample_input.xlsx`, `sample_input.csv`, `sample_input.txt`, and a couple version `sample_couple.xlsx` will ship with the project.

### 3.7 Couples / combined household net worth

Couples can enter their finances together as one household.

- Set `Household Type: Couple`.
- Give both ages (`Age 1`, `Age 2`) and both credit scores (`Credit Score 1`, `Credit Score 2`). Partners are called **Partner 1** and **Partner 2**. Real names are not allowed and are caught by the security check.
- Each asset and debt can have an optional `Owner` column: `Partner 1`, `Partner 2`, or `Joint`. Items without an owner count as `Joint`.
- Net worth history and income history are entered as **combined household** totals. Each partner's income can be listed separately if the user wants (`Income 1`, `Income 2`); the program adds them up.
- Couples must live in the same state for v1.

Example (CSV):

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

How couples are analyzed:

| Analysis | Single | Couple |
|---|---|---|
| Net worth | Individual | Combined household (plus a per-partner breakdown from the `Owner` column) |
| Age percentile | User's age | Household compared using the **older partner's age**, which matches how the Federal Reserve survey groups households |
| State comparison | Household medians | Household medians (the state data is already per household) |
| Credit score | One score | Both scores rated separately; the lower score is flagged for joint loans like a mortgage |
| Income / savings rate | Individual | Combined household income |
| Suggestions | Individual | Household suggestions, plus partner-specific ones (e.g. "Partner 2's credit score of 668 will raise your mortgage rate") |

The report is honest about imbalances too, e.g. "Partner 2 holds 90% of the household's debt."

---

## 4. Security and Personal Information Validation

### 4.1 Rule

The PII scan runs **before any parsing into the data model or any analysis**. If it finds anything, the program:

1. Raises `PersonalInformationError` (a custom exception).
2. Prints each problem: what kind of data it is and where it is (line / cell). The value is shown **masked**, e.g. `***-**-1234`.
3. Tells the user to remove the information and run the program again.
4. Exits with a non-zero code. **No report or `index.html` is created** and nothing is saved.

Example output:

```text
SECURITY CHECK FAILED — personal information detected.

  [Line 4]  Possible account number: ****8890
  [Line 9]  Possible street address: "*** Main St"
  [Cell B7] Possible license plate: "***-1234"

Remove this information, use generic labels like "Bank Account 1" or "Car 1",
and run the program again.
```

### 4.2 What is allowed

- Age
- State
- Credit score
- Dollar amounts (with `$`, commas, or decimals)
- Years (e.g. `2024`)
- Interest rates / percentages
- Generic labels ("Bank Account 1", "Car 2", "Credit Card 1")

### 4.3 What is blocked (detectors)

| Type | Detection method |
|---|---|
| Social Security number | `###-##-####`, `### ## ####`, or a 9-digit number next to "SSN" / "social" |
| Bank account numbers | 8–17 digit runs not formatted as money; labels like "acct", "account #", "acct no" followed by digits |
| Routing numbers | 9-digit numbers passing the ABA checksum, or next to "routing" |
| Credit / debit card numbers | 13–19 digit runs (with optional spaces/dashes) passing the Luhn check |
| Street addresses | Number + street word (St, Street, Ave, Rd, Blvd, Ln, Dr, Ct, Way, Apt, Suite) and "PO Box" |
| ZIP codes | 5-digit or ZIP+4 next to a state or address |
| Phone numbers | US phone formats `(###) ###-####`, `###-###-####`, `+1 …` |
| Email addresses | Standard email pattern |
| License plates | Plate-like strings next to "plate", "tag", "license" |
| VINs | 17-character VIN pattern (no I, O, Q) |
| Dates of birth | Full dates next to "DOB", "birth", "born" |
| Names | Text after "Name:", "Account holder:", "Owner:" |
| Driver's license / passport | Number next to "license #", "DL", "passport" |

### 4.4 Avoiding false positives

- Numbers formatted as money (`$30,000`, `30,000.00`) are not account numbers.
- 4-digit numbers between 1900 and 2100 in a history section are years.
- The credit score field (300–850) and age are allowed.
- Every detector has tests for both catching real PII and ignoring normal values.

### 4.5 Other security measures

- The program never writes the raw input to disk, logs, or the HTML report.
- `index.html` contains only the anonymized labels and computed numbers.
- No network calls besides loading Chart.js from the CDN when the HTML is opened. (Optionally bundle Chart.js locally for full offline use.)

---

## 5. Architecture and Processing Pipeline

```text
input file
   │
   ▼
parsers/          → raw text + tables
   │
   ▼
security.py       → PII scan  ──(found)──► PersonalInformationError → exit
   │
   ▼
extractor.py      → NetWorthProfile (dataclass)
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

### 5.1 Project layout

```text
Net Worth Claude/
├── Networth.md                 # this plan
├── networth.py                 # CLI entry point
├── requirements.txt
├── parsers/
│   ├── __init__.py             # pick parser by file extension
│   ├── pdf_parser.py
│   ├── docx_parser.py
│   ├── excel_parser.py         # xlsx, xls, csv
│   └── text_parser.py          # txt, md, json
├── security.py                 # PII detectors + PersonalInformationError
├── extractor.py                # raw content → NetWorthProfile
├── models.py                   # dataclasses
├── analysis/
│   ├── totals.py               # net worth, ratios, asset mix
│   ├── projections.py          # 5/10/15/20-year forecasts
│   ├── percentile.py           # rank vs. age group
│   ├── state_compare.py        # rank vs. state
│   ├── credit.py               # credit tier
│   └── score.py                # financial health score + grade
├── report.py                   # summary text + suggestions (tone rules)
├── render.py                   # jinja2 → index.html
├── templates/
│   └── index.html.j2
├── data/
│   ├── age_percentiles.json    # net worth percentiles by age bracket
│   ├── state_data.json         # state medians + cost of living
│   └── credit_averages.json    # national / state average credit scores
├── samples/
│   ├── sample_input.xlsx
│   ├── sample_input.csv
│   └── sample_input.txt
└── tests/
```

### 5.2 Data model

```python
@dataclass
class Item:
    label: str              # "Bank Account 1"
    value: float            # 30000.0
    category: str           # "cash"
    interest_rate: float | None = None   # debts only
    owner: str = "joint"    # "partner1" | "partner2" | "joint" (couples only)

@dataclass
class Person:
    age: int
    credit_score: int

@dataclass
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

@dataclass
class NetWorthProfile:
    household_type: str     # "single" | "couple"
    people: list[Person]    # 1 for single, 2 for couple
    state: str              # normalized 2-letter code
    assets: list[Item]
    debts: list[Item]
    net_worth_history: dict[int, float]   # year -> household net worth
    income_history: dict[int, float]      # year -> household income
    monthly_expenses: float | None
    assumptions: Assumptions
```

---

## 6. Analysis and Insights

### 6.1 Current snapshot

- Total assets, total debts, **net worth** = assets − debts
- Debt-to-asset ratio
- Liquid net worth (cash + investments − credit card debt)
- Asset mix by category (percent of total)
- Debt mix by category; weighted average interest rate
- High-interest debt total (rate ≥ 8%)
- Emergency fund coverage = cash ÷ monthly expenses (months)
- Depreciating asset share (vehicles ÷ total assets)

### 6.2 Projections: 5, 10, 15, 20 years

**With history (2+ years):**

- Compute annual net worth change with linear regression and compound annual growth rate (CAGR).
- Pick the method that fits better (CAGR is unreliable when net worth is near zero or negative, so use linear in that case).
- Project forward using that trend.

**Without history:**

- Use income × an estimated savings rate (from income history, or a default) plus investment growth on current investable assets.

**Three scenarios:**

| Scenario | Investment return | Contributions |
|---|---|---|
| Conservative | 4% / year | Trend − 25% |
| Expected | 7% / year | Current trend |
| Optimistic | 10% / year | Trend + 25% |

Rules:

- Vehicles depreciate (~15% / year); real estate grows ~3% / year; cash grows ~2%.
- Debts are paid down according to the trend, or grow if the trend is negative.
- **If the trend is negative, the projection shows net worth going down.** No sugarcoating.
- Show both nominal dollars and inflation-adjusted dollars (3% inflation).
- Show the age the user will be at each milestone (e.g. "At 49: $1.2M expected"). For couples, show both partners' ages.
- All rates above are **defaults**. Users can change them (see 6.2.1).

#### 6.2.1 Custom growth assumptions

Users can set their own assumptions in two ways. CLI flags win over the file, and the file wins over the defaults.

**1. In the input file** (an `Assumptions` section):

```csv
Section,Label,Value
Assumptions,Investment Return,6
Assumptions,Inflation,3.5
Assumptions,Monthly Contribution,1500
```

**2. With CLI flags:**

| Flag | Meaning | Default | Allowed range |
|---|---|---|---|
| `--return` | Expected yearly investment return (%) | 7 | −10 to 20 |
| `--spread` | ± points for conservative / optimistic scenarios | 3 | 0 to 10 |
| `--inflation` | Yearly inflation (%) | 3 | 0 to 15 |
| `--cash-rate` | Yearly interest on cash (%) | 2 | 0 to 10 |
| `--home-growth` | Yearly real estate appreciation (%) | 3 | −10 to 15 |
| `--car-depreciation` | Yearly vehicle depreciation (%) | 15 | 0 to 50 |
| `--contribution` | Monthly amount saved / invested ($) | trend | ≥ 0 |
| `--income-growth` | Yearly income growth (%) | from history | −20 to 30 |

Rules:

- Values outside the allowed range are rejected with an error that shows the range.
- The report always lists **which assumptions were used and where each came from** (default, file, or CLI).
- **Honesty check:** if an assumption is unrealistic, the report says so and **also shows the projection using the defaults** next to it. Examples:
  - Return above 10%: "You assumed 14% a year. The long-run stock market average is closer to 7–10%. Here is what happens at 7%."
  - Contribution much higher than the user's history shows: "You assumed you'll save $3,000 a month. Your history shows about $900. Here are both."
  - Inflation of 0%: "Zero inflation is not realistic. Your future dollars will buy less."
- The projection chart shows a "your assumptions" line and a "default assumptions" line when they differ.

### 6.3 Percentile vs. people the same age

- Reference data: Federal Reserve **Survey of Consumer Finances (SCF) 2022**, net worth by age of household head.
- Age brackets: under 35, 35–44, 45–54, 55–64, 65–74, 75+.
- Store percentile breakpoints (10th, 25th, 50th, 75th, 90th, 95th, 99th) per bracket in `data/age_percentiles.json`, with the source cited in the file.
- Interpolate between breakpoints to estimate the user's percentile.
- Report as: "You are in the **top 18%** for ages 35–44" or "You are in the **bottom 30%**".
- Also report how far they are from the median and from the next tier (e.g. "$41,000 more to reach the top 25%").
- **Couples:** the combined household net worth is compared with households in the **older partner's** age bracket, because the SCF data is per household and grouped by the age of the household head. The report says this clearly.

Reference medians (SCF 2022, to verify against the source during the build):

| Age | Median net worth | Mean net worth |
|---|---|---|
| < 35 | $39,000 | $183,500 |
| 35–44 | $135,600 | $549,600 |
| 45–54 | $247,200 | $975,800 |
| 55–64 | $364,500 | $1,566,900 |
| 65–74 | $409,900 | $1,794,600 |
| 75+ | $335,600 | $1,624,100 |

### 6.4 State comparison

- `data/state_data.json` holds, per state:
  - median household net worth (Census SIPP data)
  - median household income (Census ACS)
  - cost-of-living index (e.g. BEA Regional Price Parities, where 100 = national average)
- Compare the user's net worth to the state median, both as raw dollars and **adjusted for cost of living**.
  - Example: $100K in Mississippi (RPP ~87) goes further than $100K in California (RPP ~112).
- If income history is given, compare the latest income to the state median income.
- Output: "Compared with people in Texas you are **above average**; adjusted for cost of living you rank about the 62nd percentile."

### 6.5 Credit score

| Tier | Range |
|---|---|
| Poor | 300–579 |
| Fair | 580–669 |
| Good | 670–739 |
| Very Good | 740–799 |
| Exceptional | 800–850 |

- Compare to the national average (~715) and the state average from `data/credit_averages.json`.
- Explain what the tier means in practice (loan approval, interest rates).
- **Couples:** each partner's score is rated separately. For the health score, use the **lower** score, since lenders often use the lower score on joint loans. Flag big gaps between the two scores.

### 6.6 Income analysis (if income history is given)

- Income growth per year (CAGR)
- Savings rate = change in net worth ÷ income for each year
- Flag years where net worth went down even though income went up

### 6.7 Financial health score (0–100) and grade

| Component | Weight |
|---|---|
| Age percentile | 30% |
| Net worth trend | 20% |
| Debt-to-asset ratio and high-interest debt | 20% |
| Emergency fund coverage | 10% |
| Credit score | 10% |
| State-adjusted standing | 10% |

| Score | Grade |
|---|---|
| 90–100 | A |
| 80–89 | B |
| 65–79 | C |
| 50–64 | D |
| < 50 | F |

---

## 7. Tone Rules: Brutally Honest

The report says what the numbers say. Language templates depend on the grade and on specific findings.

**Rules:**

1. Every statement is backed by a number.
2. No fake positivity. A bad result is called bad.
3. No insults about the person. Criticize the finances, not the user.
4. Good results get clear, direct praise. No hedging.
5. The summary starts with the verdict, then the reasons.

**Example statements by grade:**

| Grade | Example |
|---|---|
| A | "You are in the top 8% for your age. Your finances are strong. Keep doing exactly what you are doing." |
| B | "You are well above the median for your age. One or two fixes would put you in the top tier." |
| C | "You are average. Average is not a plan. At your current pace you will have $310K at 60, which is below the median for that age." |
| D | "You are behind. You are in the bottom 35% for your age and your debt is growing faster than your assets." |
| F | "Your finances are in serious trouble. Your net worth is −$22,000 and has gone down for 3 years in a row. If nothing changes, you will be $60,000 in the hole in 10 years." |

**Example specific findings:**

- "You are paying 24.9% interest on $4,200 of credit card debt. That costs you about $1,050 a year for nothing."
- "Your car is 40% of your net worth and it loses value every year."
- "You have 0.8 months of expenses in cash. One emergency puts you into debt."
- "Your income went up 40% in 4 years but your net worth barely moved. You are spending your raises."

---

## 8. Suggestions Engine

Rule-based suggestions, ranked by estimated dollar impact. Show the top 5–7.

| Trigger | Suggestion |
|---|---|
| Any debt with interest ≥ 8% | Pay it off with the avalanche method (highest rate first). Show the yearly interest saved. |
| Emergency fund < 3 months | Build a 3–6 month emergency fund in a high-yield savings account before investing more. |
| No retirement assets | Open a 401(k) (get any employer match) or an IRA. Show the 20-year value of $300/month. |
| Credit score < 670 | Pay on time, keep credit card use under 30% (ideally under 10%), don't close old cards, check reports for errors. |
| Vehicles > 30% of assets | Stop buying depreciating assets; drive the current car longer. |
| Negative net worth trend | Track spending for 30 days; cut the 3 largest non-essential costs. |
| Savings rate < 10% | Automate savings; target 15–20% of income. |
| Income rising but net worth flat | Lifestyle creep: save at least half of every raise. |
| Too much idle cash (> 12 months of expenses) | Move the extra into investments. |
| Below state median (cost-of-living adjusted) | Focus on income growth: skills, certifications, job changes. |
| Strong position (grade A/B) | Optimize: tax-advantaged accounts, max out contributions, diversify. |

Each suggestion includes **what to do**, **why** (the number that triggered it), and **the expected impact** in dollars when possible.

---

## 9. Output: `index.html`

A single static page generated from `templates/index.html.j2`. It opens in any browser.

### 9.1 Page sections

1. **Header:** "Your Net Worth Report", date generated, disclaimer.
2. **KPI tiles:** net worth, grade (A–F), age percentile ("Top 18%"), credit tier, debt-to-asset ratio.
3. **Verdict:** one or two honest paragraphs.
4. **Breakdown:** assets and debts.
5. **History and projections.**
6. **Age comparison.**
7. **State comparison.**
8. **Credit score.**
9. **Income and savings rate** (if data was given).
10. **Final summary.**
11. **Suggestions** (ranked list).
12. **Footer:** data sources, "not financial advice" disclaimer.

### 9.2 Charts

| Chart | Type | Shows |
|---|---|---|
| Assets vs. debts | Grouped bar | Totals by category |
| Asset mix | Doughnut | Share of each asset category |
| Net worth over time | Line | History (solid) + 3 projection scenarios (dashed) to 20 years |
| Projection milestones | Bar | Expected net worth at 5, 10, 15, 20 years (with conservative / optimistic as error range) |
| Age comparison | Histogram / bar | Net worth at the 10th–99th percentiles for the user's age bracket, with a bar or line marking the user |
| Median by age | Bar | Median net worth for every age bracket, user's bracket highlighted, user's value marked |
| State comparison | Grouped bar | User vs. state median vs. national median (raw and cost-of-living adjusted) |
| Credit score | Horizontal bar | Tier ranges with a marker at the user's score and the averages |
| Income vs. net worth change | Bar + line | Yearly income and yearly net worth change; savings rate line |
| Score breakdown | Horizontal bar | Each component of the health score |
| Partner breakdown (couples) | Stacked bar | Assets and debts owned by Partner 1, Partner 2, and Joint |
| Your vs. default assumptions | Line | Shown only when custom assumptions differ from the defaults |

The page also has an **Assumptions used** table listing every rate and where it came from (default, file, or CLI).

### 9.3 Design

- Clean, readable layout. Mobile-friendly (works at phone width).
- Light and dark mode.
- Colors: green = good, amber = warning, red = bad. Used consistently across tiles and charts.
- Chart.js loaded from a pinned CDN version.
- All data embedded in the page as JSON; no external data requests.

---

## 10. Error Handling

| Situation | Behavior |
|---|---|
| Personal information found | `PersonalInformationError`, list masked findings, ask user to remove and retry, exit code 2 |
| Unsupported file type | List supported types, exit code 1 |
| File unreadable / corrupted / password-protected | Clear message, exit code 1 |
| Scanned PDF with no text | Ask the user to provide a text-based file (no OCR in v1) |
| Missing age / state / credit score | Prompt for it in the terminal |
| Invalid value (credit score 900, age −3, unknown state) | Explain the valid range and prompt again |
| No assets and no debts found | Explain the expected format and point to the sample templates |
| Only one year of history | Skip trend-based projection; use the income-based fallback and say so |
| Couple with only one age or credit score | Prompt for the missing partner's value |
| `Owner` value that isn't Partner 1 / Partner 2 / Joint | Explain the allowed values (real names are caught by the security check first) |
| Growth assumption out of range or not a number | Show the allowed range and exit code 1 |

---

## 11. Testing Plan

- **Security tests (most important):**
  - Each detector catches real examples (SSN, account numbers, Luhn-valid cards, addresses, phones, emails, VINs, plates, DOB).
  - Each detector ignores safe values (`$30,000`, `2024`, credit score `712`, `Bank Account 1`).
  - End-to-end: a file with an account number raises `PersonalInformationError` and produces **no** `index.html`.
- **Parser tests:** the same sample data in PDF, DOCX, XLSX, CSV, and TXT all produce the same `NetWorthProfile`.
- **Analysis tests:**
  - Projection math (known inputs → known outputs), negative trends, zero/negative net worth.
  - Percentile interpolation at and between breakpoints, below the 10th and above the 99th.
  - Cost-of-living adjustment.
  - Credit tiers at boundaries (579, 580, 669, 670…).
  - Score and grade boundaries.
- **Tone tests:** a bad profile gets grade D/F language; a strong profile gets A/B language.
- **Couples tests:** combined totals, per-partner breakdown, older-partner age bracket, lower credit score used, missing partner fields prompted.
- **Assumptions tests:** CLI overrides file, file overrides defaults; out-of-range values rejected; unrealistic values trigger the honesty check and the side-by-side default projection.
- **End-to-end:** run on each sample file; `index.html` exists, contains all chart canvases, and contains no raw input text beyond labels.

---

## 12. Build Milestones

| # | Milestone | Done when |
|---|---|---|
| M1 | Parsers + PII security check | Every format reads into text; PII files are rejected with masked messages |
| M2 | Extraction + data model | Sample files (single and couple) produce a correct `NetWorthProfile`; missing fields are prompted; assumptions are read from the file and CLI |
| M3 | Reference data | `age_percentiles.json`, `state_data.json`, `credit_averages.json` filled in with cited sources |
| M4 | Analysis | Totals, projections, percentile, state, credit, score all work and are tested |
| M5 | Report text | Honest summary and ranked suggestions generated from the analysis |
| M6 | HTML + charts | `index.html` shows all sections and charts, works on mobile, light/dark |
| M7 | Tests + samples + README | Full test suite passes; sample files and usage instructions included |

---

## 13. Future Ideas and Open Questions

- Update SCF data when the 2025 survey is published (expected late 2026 / 2027).
- Optional OCR for scanned PDFs.
- Compare against people with similar income, not just age.
- Monte Carlo simulation for projections instead of three fixed scenarios.
- Track multiple reports over time (compare this year's report with last year's).
- Optional web interface (Flask) later.
- Couples living in different states.

**Decided:**

- ✅ Couples can enter a combined household net worth (section 3.7).
- ✅ Users can set their own growth assumptions (section 6.2.1).

---

## Disclaimer

This program gives estimates based on public averages and simple models. It is not financial, tax, or legal advice.
