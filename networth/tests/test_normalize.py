from __future__ import annotations

import datetime as dt

import pytest

from networth.errors import InvalidInputError
from networth.formatting import format_money, format_percent
from networth.normalize import (
    categorize_asset, categorize_debt, is_debt_label, normalize_category, normalize_owner,
    normalize_state, parse_date, parse_money, split_value_text, validate_age,
    validate_credit_score, validate_household, validate_state,
)


@pytest.mark.parametrize(("text", "value"), [
    ("$30,000", 30000), ("30000", 30000), ("30,000.50", 30000.5), ("-$22,000", -22000),
    ("$-22,000", -22000), ("(1,200)", -1200), ("45k", 45000), ("$1.2M", 1_200_000), (" $ 500 ", 500),
])
def test_parse_money(text: str, value: float) -> None:
    assert parse_money(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["", "abc", "Partner 1", "5%", "12/10/2024"])
def test_parse_money_rejects(text: str) -> None:
    assert parse_money(text) is None


@pytest.mark.parametrize(("text", "expected"), [
    ("$18,000 (5.5%)", (18000, 5.5, None)),
    ("$285,000 at 6.1%", (285000, 6.1, None)),
    ("$61,000 (Partner 1)", (61000, None, "partner1")),
    ("$27,000 (5%) (Partner 2)", (27000, 5.0, "partner2")),
    ("about $2,000", (2000, None, None)),
])
def test_split_value_text(text: str, expected: tuple) -> None:
    assert split_value_text(text) == expected


@pytest.mark.parametrize(("text", "date"), [
    ("2025-08-04", dt.date(2025, 8, 4)),
    ("1/03/2025", dt.date(2025, 1, 3)),
    ("12/10/2024", dt.date(2024, 12, 10)),
    ("2021", dt.date(2021, 12, 31)),
    ("Aug 2025", dt.date(2025, 8, 1)),
])
def test_parse_date(text: str, date: dt.date) -> None:
    assert parse_date(text) == date


@pytest.mark.parametrize("text", ["Bank Account 1", "401k 1", "", "Vacation Month"])
def test_parse_date_rejects(text: str) -> None:
    assert parse_date(text) is None


@pytest.mark.parametrize(("label", "category"), [
    ("Bank Account 1", "cash"), ("Savings Account", "cash"), ("401K", "retirement"),
    ("401k 1", "retirement"), ("Roth IRA", "retirement"), ("HSA", "retirement"),
    ("Company Stock", "investments"), ("Personal Stock", "investments"), ("Brokerage 1", "investments"),
    ("House 1", "real_estate"), ("Car 1", "vehicles"), ("Boat 1", "vehicles"), ("Art 1", "other"),
])
def test_categorize_asset(label: str, category: str) -> None:
    assert categorize_asset(label) == category


@pytest.mark.parametrize(("label", "category"), [
    ("Mortgage 1", "mortgage"), ("Car Loan 1", "auto"), ("Student Loan 1", "student"),
    ("Credit Card 1", "credit_card"), ("Medical Bill 1", "personal"), ("IOU 1", "other"),
])
def test_categorize_debt(label: str, category: str) -> None:
    assert categorize_debt(label) == category


def test_is_debt_label() -> None:
    assert is_debt_label("Credit Card 1") and is_debt_label("Car Loan") and is_debt_label("Mortgage")
    assert not is_debt_label("Car 1") and not is_debt_label("Bank Account 1")


def test_normalize_category_and_owner() -> None:
    assert normalize_category("Real Estate", is_debt=False) == "real_estate"
    assert normalize_category("credit card", is_debt=True) == "credit_card"
    assert normalize_category("mortgage", is_debt=False) is None
    assert normalize_owner("Partner 1") == "partner1"
    assert normalize_owner("joint") == "joint"
    assert normalize_owner("Jordan") is None


@pytest.mark.parametrize(("text", "code"), [
    ("OH", "OH"), ("oh", "OH"), ("Ohio", "OH"), ("Columbus, Ohio", "OH"),
    ("columbus ohio", "OH"), ("Columbus, OH", "OH"), ("New York", "NY"), ("Washington DC", "DC"),
    ("West Virginia", "WV"),
])
def test_normalize_state(text: str, code: str) -> None:
    assert normalize_state(text) == code


def test_validators() -> None:
    assert validate_age("27") == 27
    assert validate_credit_score("762") == 762
    assert validate_state("Ohio") == "OH"
    assert validate_household("Married") == "couple"
    for bad, fn in [("15", validate_age), ("24.5", validate_age), ("abc", validate_age),
                    ("900", validate_credit_score), ("Atlantis", validate_state), ("trio", validate_household)]:
        with pytest.raises(InvalidInputError):
            fn(bad)


def test_formatting() -> None:
    assert format_money(30000) == "$30,000"
    assert format_money(-22000) == "-$22,000"
    assert format_money(1_234_567, compact=True) == "$1.2M"
    assert format_money(30_000, compact=True) == "$30K"
    assert format_money(950, compact=True) == "$950"
    assert format_percent(7.0) == "7%"
    assert format_percent(5.5) == "5.5%"
