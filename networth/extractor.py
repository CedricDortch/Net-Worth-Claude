"""Raw ParsedDocument -> NetWorthProfile.

Two steps:
1. `extract(doc)` reads everything it can into `Extracted` (all fields optional).
   Three layouts are understood, in tables or text:
   - Section rows:  Section | Label | Value | InterestRate | Category | Owner
   - Headed text:   "ASSETS" then "Bank Account 1: $30,000"
   - Time series:   Date | Account A | Account B | ... | Total   (one row per date)
   JSON uses the same keys as the section layout.
2. `build_profile(...)` takes the validated profile fields (from the file, CLI, or
   prompts — the CLI decides) and returns a NetWorthProfile, with notes about
   anything missing.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from networth import assumptions as assumptions_mod
from networth.errors import InvalidInputError
from networth.formatting import format_money
from networth.models import Assumptions, Item, NetWorthProfile, Person
from networth.normalize import (
    categorize_asset, categorize_debt, is_debt_label, norm_label, normalize_category,
    normalize_owner, parse_date, parse_money, parse_percent, parse_year, split_value_text,
)
from networth.parsers.document import ParsedDocument, Table


@dataclass
class Extracted:
    """Everything read from the file. Profile fields stay raw text until validated."""

    household_type: str | None = None
    ages: dict[int, str] = field(default_factory=dict)            # partner number (1/2) -> raw
    credit_scores: dict[int, str] = field(default_factory=dict)
    state: str | None = None
    assets: list[Item] = field(default_factory=list)
    debts: list[Item] = field(default_factory=list)
    net_worth_history: dict[dt.date, float] = field(default_factory=dict)
    income_history: dict[int, float] = field(default_factory=dict)
    monthly_expenses: float | None = None
    assumptions: dict[str, str | float] = field(default_factory=dict)  # field name -> raw
    as_of: dt.date | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Routing one (section, label, value) row
# ---------------------------------------------------------------------------

_SECTIONS = {
    "profile": "profile", "about": "profile", "about me": "profile",
    "asset": "asset", "assets": "asset",
    "debt": "debt", "debts": "debt", "liability": "debt", "liabilities": "debt",
    "history": "history", "net worth history": "history", "networth history": "history",
    "net worth": "history",
    "income": "income", "income history": "income",
    "expenses": "expenses", "expense": "expenses", "monthly expenses": "expenses",
    "assumptions": "assumptions", "assumption": "assumptions", "growth assumptions": "assumptions",
}

_PROFILE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?:partner ([12]) )?age(?: ([12]))?$"), "age"),
    (re.compile(r"^(?:partner ([12]) )?(?:fico )?credit score(?: ([12]))?(?: fico)?$"), "credit"),
    (re.compile(r"^(?:state|state of residence|home state)$"), "state"),
    (re.compile(r"^household(?: type)?$"), "household"),
    (re.compile(r"^monthly expenses?$"), "expenses"),
)


def _profile_field(label: str) -> tuple[str, int] | None:
    key = norm_label(label)
    for pattern, name in _PROFILE_PATTERNS:
        m = pattern.match(key)
        if m:
            partner = next((int(g) for g in m.groups() if g), 1)
            return name, partner
    return None


@dataclass(frozen=True)
class _Row:
    label: str
    value: str
    location: str
    rate: str = ""
    category: str = ""
    owner: str = ""


def _route(ex: Extracted, section: str | None, row: _Row) -> None:
    label, value = row.label.strip(), row.value.strip()
    if not label:
        return

    profile = _profile_field(label)
    if profile and section in (None, "profile", "expenses"):
        name, partner = profile
        if name == "age":
            ex.ages[partner] = value
        elif name == "credit":
            ex.credit_scores[partner] = value
        elif name == "state":
            ex.state = value
        elif name == "household":
            ex.household_type = value
        elif name == "expenses":
            amount = parse_money(value) if value else None
            if amount is None:
                amount, _, _ = split_value_text(value)
            if amount is not None:
                ex.monthly_expenses = amount
        return

    spec = assumptions_mod.spec_for_label(label)
    if section == "assumptions" or (spec and section in (None, "profile")):
        if spec is None:
            ex.notes.append(f"Ignored unknown assumption '{label}' ({row.location}).")
        else:
            ex.assumptions[spec.field] = value
        return

    if section == "profile":
        ex.notes.append(f"Ignored profile field '{label}' ({row.location}).")
        return

    amount, text_rate, text_owner = _amount_rate_owner(row)

    if section == "history" or (section is None and parse_date(label) and amount is not None):
        when = parse_date(label)
        if when is None or amount is None:
            ex.notes.append(f"Skipped history row '{label}' ({row.location}): needs a date or year and an amount.")
        else:
            ex.net_worth_history[when] = amount
        return

    if section == "income":
        year = parse_year(label) or (parse_date(label).year if parse_date(label) else None)
        if year is None or amount is None:
            ex.notes.append(f"Skipped income row '{label}' ({row.location}): needs a year and an amount.")
        else:
            ex.income_history[year] = ex.income_history.get(year, 0.0) + amount  # partners are summed
        return

    if section == "expenses":
        if amount is not None:
            ex.monthly_expenses = (ex.monthly_expenses or 0.0) + amount
        return

    if amount is None:
        ex.notes.append(f"Skipped '{label}' ({row.location}): no dollar amount found.")
        return

    is_debt = section == "debt" or (section is None and is_debt_label(label))
    _add_item(ex, label, amount, is_debt, row.location,
              rate=text_rate if text_rate is not None else (parse_percent(row.rate) if row.rate else None),
              category=row.category, owner=row.owner or text_owner or "")


def _amount_rate_owner(row: _Row) -> tuple[float | None, float | None, str | None]:
    amount = parse_money(row.value) if row.value else None
    if amount is not None:
        return amount, None, None
    return split_value_text(row.value)


def _add_item(ex: Extracted, label: str, amount: float, is_debt: bool, location: str,
              rate: float | None = None, category: str = "", owner: str = "") -> None:
    if amount < 0:
        if is_debt:
            amount = -amount  # "-$4,200" under debts means a $4,200 balance
        else:
            raise InvalidInputError(
                f"'{label}' ({location}) has a negative value. Asset values must be $0 or more; "
                "list money you owe under DEBTS instead."
            )

    chosen = normalize_category(category, is_debt) if category else None
    if category and chosen is None:
        ex.notes.append(f"Unknown category '{category}' for '{label}'; guessed from the label instead.")
    if chosen is None:
        chosen = categorize_debt(label) if is_debt else categorize_asset(label)

    owner_key = normalize_owner(owner) if owner else "joint"
    if owner_key is None:
        raise InvalidInputError(
            f"Owner for '{label}' ({location}) must be Partner 1, Partner 2, or Joint."
        )

    item = Item(label=label, value=amount, category=chosen,
                interest_rate=rate if is_debt else None, owner=owner_key)
    (ex.debts if is_debt else ex.assets).append(item)


# ---------------------------------------------------------------------------
# Text lines
# ---------------------------------------------------------------------------

_BULLET = re.compile(r"^\s*(?:[-*•]+|#+)\s*")


def _section_heading(text: str) -> str | None:
    key = norm_label(_BULLET.sub("", text).rstrip(":"))
    return _SECTIONS.get(key)


def _from_lines(ex: Extracted, lines: Iterable[tuple[str, str]]) -> None:
    section: str | None = None
    for text, location in lines:
        stripped = _BULLET.sub("", text).strip()
        if not stripped:
            continue
        label, sep, value = stripped.partition(":")
        if not sep or not value.strip():
            heading = _section_heading(stripped)
            if heading:
                section = heading
            continue
        _route(ex, section, _Row(label.strip(), value.strip(), location))


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

_LABEL_HEADERS = {"label", "item", "name", "account", "description", "asset", "field"}
_VALUE_HEADERS = {"value", "amount", "balance", "worth", "current value"}
_RATE_HEADERS = {"interestrate", "interest rate", "rate", "apr", "interest"}
_DATE_HEADERS = {"date", "year", "month", "as of", "period", "asof"}
_NOTE_HEADERS = {"note", "notes", "comment", "comments", "memo"}


def _header_row(table: Table) -> int | None:
    return next((i for i, r in enumerate(table.rows) if any(c.strip() for c in r)), None)


def _from_table(ex: Extracted, table: Table) -> None:
    first = _header_row(table)
    if first is None:
        return
    headers = [norm_label(c) for c in table.rows[first]]

    if "section" in headers or (set(headers) & _LABEL_HEADERS and set(headers) & _VALUE_HEADERS):
        _item_table(ex, table, first, headers)
    elif _looks_like_time_series(table, first, headers):
        _time_series_table(ex, table, first, headers)
    else:
        # No header: treat column A as labels and column B as values, from the top.
        rows = [
            _Row(r[0], r[1], table.cell_location(i, 1))
            for i, r in enumerate(table.rows) if len(r) >= 2
        ]
        if not rows:
            ex.notes.append(f"Could not understand a table starting at {table.cell_location(first, 0)}.")
        for row in rows:
            _route(ex, None, row)


def _col(headers: list[str], names: set[str]) -> int | None:
    return next((i for i, h in enumerate(headers) if h in names), None)


def _item_table(ex: Extracted, table: Table, first: int, headers: list[str]) -> None:
    c_section = _col(headers, {"section", "type", "kind"})
    c_label = _col(headers, _LABEL_HEADERS)
    c_value = _col(headers, _VALUE_HEADERS)
    c_rate = _col(headers, _RATE_HEADERS)
    c_category = _col(headers, {"category"})
    c_owner = _col(headers, {"owner"})
    if c_label is None:
        c_label = 1 if c_section == 0 else 0
    if c_value is None:
        c_value = c_label + 1

    def cell(row: tuple[str, ...], c: int | None) -> str:
        return row[c].strip() if c is not None and c < len(row) else ""

    for r in range(first + 1, len(table.rows)):
        row = table.rows[r]
        if not any(c.strip() for c in row):
            continue
        raw_section = cell(row, c_section)
        section = _SECTIONS.get(norm_label(raw_section)) if raw_section else None
        if raw_section and section is None:
            ex.notes.append(f"Unknown section '{raw_section}' ({table.cell_location(r, c_section or 0)}); "
                            "guessed from the label.")
        _route(ex, section, _Row(
            label=cell(row, c_label), value=cell(row, c_value),
            location=table.cell_location(r, c_value),
            rate=cell(row, c_rate), category=cell(row, c_category), owner=cell(row, c_owner),
        ))


def _looks_like_time_series(table: Table, first: int, headers: list[str]) -> bool:
    if headers and headers[0] in _DATE_HEADERS:
        return True
    body = [r for r in table.rows[first + 1:] if r and r[0].strip()]
    dated = sum(parse_date(r[0]) is not None for r in body)
    return bool(body) and dated >= max(2, len(body) // 2)


def _is_total(header: str) -> bool:
    return "total" in header.split() or header.replace(" ", "") in {"networth", "net"}


def _time_series_table(ex: Extracted, table: Table, first: int, headers: list[str]) -> None:
    raw_headers = [c.strip() for c in table.rows[first]]
    date_col = _col(headers, _DATE_HEADERS)
    date_col = 0 if date_col is None else date_col

    total_cols = [i for i, h in enumerate(headers) if i != date_col and _is_total(h)]
    net_col = next((i for i in total_cols if "net" in headers[i].replace(" ", "")), None)
    if net_col is None and len(total_cols) == 1 and not is_debt_label(headers[total_cols[0]]) \
            and "asset" not in headers[total_cols[0]]:
        net_col = total_cols[0]

    body = list(range(first + 1, len(table.rows)))
    item_cols = []
    for c, h in enumerate(headers):
        if c == date_col or c in total_cols or not h or h in _NOTE_HEADERS:
            continue
        values = [table.rows[r][c] for r in body if c < len(table.rows[r]) and table.rows[r][c].strip()]
        if values and sum(parse_money(v) is not None for v in values) >= len(values) / 2:
            item_cols.append(c)

    if not item_cols and net_col is None:
        ex.notes.append("Found a date column but no number columns to read.")
        return

    # A dated sheet with no total and no column that looks like an account or debt
    # (e.g. a weight log in the same workbook) isn't net worth data. Don't guess.
    if not total_cols and all(categorize_asset(raw_headers[c]) == "other" and not is_debt_label(headers[c])
                              for c in item_cols):
        where = table.location_prefix.rstrip(", ") or "A table"
        ex.notes.append(f"Ignored {where}: its columns ({', '.join(raw_headers[c] for c in item_cols)}) "
                        "don't look like accounts or debts. Label them like 'Bank Account 1' or add a "
                        "Total column if they should count.")
        return

    dated_rows: list[tuple[dt.date, int]] = []
    for r in body:
        row = table.rows[r]
        when = parse_date(row[date_col]) if date_col < len(row) else None
        if when is None:
            if any(c.strip() for c in row):
                ex.notes.append(f"Skipped row {r + 1}: no date in {table.cell_location(r, date_col)}.")
            continue
        dated_rows.append((when, r))
    if not dated_rows:
        return
    dated_rows.sort()

    def money(r: int, c: int) -> float:
        row = table.rows[r]
        value = parse_money(row[c]) if c < len(row) and row[c].strip() else None
        return value or 0.0

    debt_cols = {c for c in item_cols if is_debt_label(headers[c])}
    mismatches: list[str] = []
    for when, r in dated_rows:
        computed = sum(abs(money(r, c)) * (-1 if c in debt_cols else 1) for c in item_cols)
        if net_col is not None and table.rows[r][net_col].strip():
            stated = money(r, net_col)
            if item_cols and abs(stated - computed) > 1:
                diff = stated - computed
                mismatches.append(f"{when.isoformat()} ({'+' if diff > 0 else '-'}{format_money(abs(diff))})")
            ex.net_worth_history[when] = stated
        else:
            ex.net_worth_history[when] = computed
    if mismatches:
        shown = ", ".join(mismatches[:5]) + (f" and {len(mismatches) - 5} more" if len(mismatches) > 5 else "")
        ex.notes.append(
            f"The '{raw_headers[net_col]}' column doesn't equal the sum of the other columns on: {shown}. "
            "History uses your total column; current assets use the latest row's columns."
        )

    latest_date, latest = dated_rows[-1]
    ex.as_of = latest_date
    for c in item_cols:
        value = money(latest, c)
        if value:
            _add_item(ex, raw_headers[c], value, c in debt_cols, table.cell_location(latest, c))


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def _from_json(ex: Extracted, data: Any) -> None:
    if not isinstance(data, dict):
        ex.notes.append("JSON input must be an object with keys like age, state, assets, debts.")
        return
    for key, value in data.items():
        nkey = norm_label(str(key))
        section = _SECTIONS.get(nkey)
        if nkey in {"ages", "credit scores"} and isinstance(value, list):
            target = ex.ages if nkey == "ages" else ex.credit_scores
            for i, v in enumerate(value[:2], start=1):
                target[i] = str(v)
        elif isinstance(value, list):
            for i, entry in enumerate(value):
                loc = f"Field {key}[{i}]"
                if isinstance(entry, dict):
                    e = {norm_label(str(k)): v for k, v in entry.items()}
                    label = e.get("label") or e.get("name") or e.get("date") or e.get("year") or ""
                    _route(ex, section, _Row(
                        str(label), _json_text(e.get("value", e.get("amount", ""))), loc,
                        rate=_json_text(e.get("interest rate", e.get("rate", ""))),
                        category=_json_text(e.get("category", "")), owner=_json_text(e.get("owner", "")),
                    ))
        elif isinstance(value, dict):
            for k, v in value.items():
                _route(ex, section, _Row(str(k), _json_text(v), f"Field {key}.{k}"))
        else:
            _route(ex, None, _Row(str(key), _json_text(value), f"Field {key}"))


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(doc: ParsedDocument) -> Extracted:
    ex = Extracted()
    if doc.data is not None:
        _from_json(ex, doc.data)
    else:
        _from_lines(ex, ((line.text, line.location) for line in doc.lines))
    for table in doc.tables:
        _from_table(ex, table)
    return ex


def build_profile(
    ex: Extracted,
    *,
    household_type: str,
    people: list[Person],
    state: str,
    monthly_expenses: float | None,
    assumptions: Assumptions,
) -> NetWorthProfile:
    """Final checks + notes. Profile fields must already be validated."""
    expected = 2 if household_type == "couple" else 1
    if len(people) != expected:
        raise InvalidInputError(f"A {household_type} household needs {expected} age/credit score pair(s).")
    if not ex.assets and not ex.debts:
        raise InvalidInputError(
            "No assets or debts were found. See the examples in the samples/ folder for the expected layout."
        )

    notes = list(ex.notes)
    if not ex.debts:
        notes.append("No debts were found. If you have any (loans, credit cards, car loan), add them. "
                     "The analysis assumes you owe $0.")
    if not any(i.category == "cash" for i in ex.assets):
        notes.append("No cash or bank accounts were found. Your emergency fund will count as $0.")
    if monthly_expenses is None:
        notes.append("Monthly expenses not given, so emergency fund coverage can't be measured. "
                     "Add them to the file or use --expenses.")
    if not ex.income_history:
        notes.append("No income history, so savings rate can't be measured.")
    if len(ex.net_worth_history) < 2:
        notes.append("Fewer than 2 net worth history points; projections will use the income-based fallback.")
    if household_type == "single" and any(i.owner != "joint" for i in (*ex.assets, *ex.debts)):
        notes.append("Owner values are ignored for a single household.")

    history = dict(sorted(ex.net_worth_history.items()))
    profile = NetWorthProfile(
        household_type=household_type,
        people=tuple(people),
        state=state,
        assets=tuple(ex.assets),
        debts=tuple(ex.debts),
        net_worth_history=history,
        income_history=dict(sorted(ex.income_history.items())),
        monthly_expenses=monthly_expenses,
        assumptions=assumptions,
        as_of=ex.as_of,
        notes=tuple(notes),
    )
    if history and ex.as_of is None:
        last_date, last_value = next(reversed(history.items()))
        if abs(last_value - profile.net_worth) > max(1.0, 0.05 * abs(profile.net_worth)):
            notes.append(
                f"Your latest history value ({format_money(last_value)}, {last_date.year}) differs from "
                f"your current assets minus debts ({format_money(profile.net_worth)})."
            )
            profile = replace(profile, notes=tuple(notes))
    return profile
