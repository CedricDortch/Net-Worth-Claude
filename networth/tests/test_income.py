from __future__ import annotations

import datetime as dt

import pytest

from networth.analysis.income import analyze_income
from conftest import make_profile


def test_no_income() -> None:
    assert analyze_income(make_profile()) is None


def test_savings_rate_from_year_end_values() -> None:
    history = {dt.date(2023, 6, 1): 1, dt.date(2023, 12, 1): 10_000, dt.date(2024, 12, 1): 20_000,
               dt.date(2025, 12, 1): 26_000}
    r = analyze_income(make_profile(history=history, income={2024: 50_000, 2025: 60_000}))
    assert r.net_worth_change == {2024: 10_000, 2025: 6_000}
    assert r.savings_rate == {2024: 20.0, 2025: 10.0}
    assert r.average_savings_rate == pytest.approx(16_000 / 110_000 * 100)
    assert r.income_cagr == pytest.approx(20.0)


def test_spent_the_raise() -> None:
    history = {dt.date(2024, 12, 31): 20_000, dt.date(2025, 12, 31): 15_000}
    r = analyze_income(make_profile(history=history, income={2024: 50_000, 2025: 70_000}))
    assert r.spent_the_raise == (2025,)
    assert r.savings_rate[2025] < 0


def test_income_without_history() -> None:
    r = analyze_income(make_profile(income={2025: 60_000}))
    assert r.savings_rate == {} and r.average_savings_rate is None and r.income_cagr is None
