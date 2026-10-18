"""Turn raw cell/line text into typed values: money, dates, states, categories.

Validators raise InvalidInputError with a message that explains the valid range.
"""

from __future__ import annotations

import datetime as dt
import re

from networth.constants import STATES
from networth.errors import InvalidInputError
from networth.models import ASSET_CATEGORIES, DEBT_CATEGORIES

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def norm_label(text: str) -> str:
    """'Credit Score (FICO):' -> 'credit score fico'."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}
_MONEY_FULL = re.compile(
    r"^\s*(?P<neg>[-−])?\s*(?P<paren>\()?\s*(?P<neg2>[-−])?\s*\$?\s*(?P<neg3>[-−])?\s*"
    r"(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?P<suf>[kmb])?\s*\)?\s*(?:usd)?\s*$",
    re.IGNORECASE,
)
_MONEY_SEARCH = re.compile(
    r"(?<![\w.])(?P<neg>[-−])?\(?\$?\s?(?P<num>\d[\d,]*(?:\.\d+)?)(?:\s?(?P<suf>[kmb])(?![a-z]))?\)?",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"\(?\s*(?:at\s+)?(\d+(?:\.\d+)?)\s*%\s*(?:apr|interest)?\s*\)?", re.IGNORECASE)
_OWNER = re.compile(r"\(?\s*\b(partner\s*[12]|joint)\b\s*\)?", re.IGNORECASE)


def _to_number(num: str, suffix: str | None, negative: bool) -> float:
    value = float(num.replace(",", "")) * _SUFFIX.get((suffix or "").lower(), 1)
    return -value if negative else value


def parse_money(text: str) -> float | None:
    """A whole cell as money: '$30,000', '30000', '-$22,000', '(1,200)', '45k'. None if not money."""
    m = _MONEY_FULL.match(text)
    if not m:
        return None
    negative = bool(m["neg"] or m["neg2"] or m["neg3"] or (m["paren"] and text.strip().endswith(")")))
    return _to_number(m["num"], m["suf"], negative)


def parse_percent(text: str) -> float | None:
    """'5.5', '5.5%' -> 5.5."""
    text = text.strip().rstrip("%").strip()
    try:
        return float(text)
    except ValueError:
        return None


def split_value_text(text: str) -> tuple[float | None, float | None, str | None]:
    """Free text after a label -> (amount, interest rate, owner).

    '$18,000 (5.5%)' -> (18000, 5.5, None) · '$61,000 (Partner 1)' -> (61000, None, 'partner1')
    """
    rate_match = _PERCENT.search(text)
    rate = float(rate_match.group(1)) if rate_match else None
    owner_match = _OWNER.search(text)
    owner = normalize_owner(owner_match.group(1)) if owner_match else None
    rest = _OWNER.sub(" ", _PERCENT.sub(" ", text))
    money = _MONEY_SEARCH.search(rest)
    amount = _to_number(money["num"], money["suf"], bool(money["neg"])) if money else None
    return amount, rate, owner


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y",
    "%b %d, %Y", "%B %d, %Y", "%b %Y", "%B %Y", "%m/%Y", "%Y-%m",
)


def parse_year(text: str) -> int | None:
    text = text.strip()
    if re.fullmatch(r"(19|20)\d{2}(\.0)?", text):
        return int(float(text))
    return None


def parse_date(text: str) -> dt.date | None:
    """'2025-08-04', '1/03/2025', 'Aug 2025', or a bare year (-> Dec 31 of that year)."""
    text = text.strip()
    year = parse_year(text)
    if year is not None:
        return dt.date(year, 12, 31)
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

_DEBT_WORDS = re.compile(
    r"\b(mortgage|heloc|loans?|credit\s*cards?|cards?|debts?|owed|liabilit(y|ies)|payable|balance\s+due)\b"
)
_ASSET_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("retirement", r"\b(401\s*k|401\s*\(k\)|403\s*b|457|ira|roth|pension|tsp|hsa|retirement)\b"),
    ("cash", r"\b(bank|checking|savings|cash|money\s+market|cd|hysa|emergency\s+fund)\b"),
    ("investments", r"\b(brokerage|stocks?|etfs?|bonds?|crypto|bitcoin|investments?|index\s+funds?|mutual\s+funds?|rsus?|espp)\b"),
    ("real_estate", r"\b(house|home|property|condo|land|rental|real\s+estate)\b"),
    ("vehicles", r"\b(car|truck|motorcycle|boat|vehicle|suv|rv)\b"),
)
_DEBT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("mortgage", r"\b(mortgage|home\s+loan|heloc)\b"),
    ("auto", r"\b(car|auto|vehicle|truck)\s+loan\b"),
    ("student", r"\bstudent\b"),
    ("credit_card", r"\b(credit\s*cards?|cards?)\b"),
    ("personal", r"\b(personal\s+loan|medical|payday)\b"),
)
_CATEGORY_ALIASES = {
    "investment": "investments", "real estate": "real_estate", "realestate": "real_estate",
    "vehicle": "vehicles", "credit card": "credit_card", "creditcard": "credit_card",
}


def is_debt_label(label: str) -> bool:
    return bool(_DEBT_WORDS.search(norm_label(label)))


def categorize_asset(label: str) -> str:
    text = norm_label(label)
    for category, pattern in _ASSET_KEYWORDS:
        if re.search(pattern, text):
            return category
    return "other"


def categorize_debt(label: str) -> str:
    text = norm_label(label)
    for category, pattern in _DEBT_KEYWORDS:
        if re.search(pattern, text):
            return category
    return "other"


def normalize_category(text: str, is_debt: bool) -> str | None:
    """Explicit Category column value -> category, or None if it isn't one we know."""
    key = norm_label(text)
    key = _CATEGORY_ALIASES.get(key, key.replace(" ", "_"))
    allowed = DEBT_CATEGORIES if is_debt else ASSET_CATEGORIES
    return key if key in allowed else None


def normalize_owner(text: str) -> str | None:
    key = norm_label(text).replace(" ", "")
    return {"partner1": "partner1", "partner2": "partner2", "joint": "joint"}.get(key)


# ---------------------------------------------------------------------------
# Validators (raise InvalidInputError)
# ---------------------------------------------------------------------------

_STATE_BY_NAME = {name.lower(): code for code, name in STATES.items()}
_STATE_BY_NAME.update({"washington dc": "DC", "washington d c": "DC", "d c": "DC"})


def normalize_state(text: str) -> str | None:
    """'OH', 'ohio', 'Columbus, Ohio', 'Columbus, OH' -> 'OH'."""
    raw = text.strip()
    if raw.upper() in STATES:
        return raw.upper()
    words = norm_label(raw)
    if words in _STATE_BY_NAME:
        return _STATE_BY_NAME[words]
    for name in sorted(_STATE_BY_NAME, key=len, reverse=True):
        if words.endswith(" " + name):
            return _STATE_BY_NAME[name]
    tokens = re.split(r"[\s,]+", raw)
    if len(tokens) > 1 and tokens[-1].upper() in STATES:
        return tokens[-1].upper()
    return None


def _whole_number(raw: str | int | float) -> int | None:
    try:
        value = float(str(raw).strip())
    except ValueError:
        return None
    return int(value) if value.is_integer() else None


def validate_age(raw: str | int | float, who: str = "Age") -> int:
    age = _whole_number(raw)
    if age is None or not 16 <= age <= 110:
        raise InvalidInputError(f"{who} must be a whole number from 16 to 110.")
    return age


def validate_credit_score(raw: str | int | float, who: str = "Credit score") -> int:
    score = _whole_number(raw)
    if score is None or not 300 <= score <= 850:
        raise InvalidInputError(f"{who} must be a whole number from 300 to 850 (the FICO range).")
    return score


def validate_state(raw: str) -> str:
    code = normalize_state(str(raw))
    if code is None:
        raise InvalidInputError("State must be a US state name or 2-letter code (e.g. Ohio or OH).")
    return code


def validate_household(raw: str) -> str:
    key = norm_label(str(raw))
    if key in {"single", "individual", "one", "1"}:
        return "single"
    if key in {"couple", "married", "joint", "household", "two", "2"}:
        return "couple"
    raise InvalidInputError("Household type must be 'Single' or 'Couple'.")


def validate_expenses(raw: str | float) -> float:
    value = raw if isinstance(raw, (int, float)) else parse_money(str(raw))
    if value is None or value < 0:
        raise InvalidInputError("Monthly expenses must be a dollar amount of $0 or more.")
    return float(value)
