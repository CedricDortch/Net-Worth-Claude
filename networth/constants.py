"""Project-wide constants."""

SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".txt", ".md", ".json",
)

# 50 states + DC: 2-letter code -> full name.
STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# --- Analysis thresholds -----------------------------------------------------
HIGH_INTEREST_RATE = 8.0          # % APR; debts at or above this are "high interest"
DEFAULT_SAVINGS_RATE = 10.0       # % of income, when there is no history to learn from
PROJECTION_YEARS = (5, 10, 15, 20)
CONTRIBUTION_SPREAD = 0.25        # conservative / optimistic contributions = trend ∓ 25%
MIN_TREND_YEARS = 0.5             # history must span at least this long to estimate a trend
MAX_DERIVED_INCOME_GROWTH = 10.0  # % per year; cap on income growth learned from history
SAVINGS_BENCHMARK_RATE = 0.15     # saving 15% of a typical income for your age = full trend score
PERCENTILE_TIERS = (25, 50, 75, 90, 95, 99)
