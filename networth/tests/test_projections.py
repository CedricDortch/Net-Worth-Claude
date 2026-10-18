from __future__ import annotations

import datetime as dt

import pytest

from networth.analysis.projections import fit_trend, project
from conftest import make_profile
from networth.models import Assumptions, Item

D = dt.date


def yearly(*values: float, start: int = 2021) -> dict[dt.date, float]:
    return {D(start + i, 12, 31): v for i, v in enumerate(values)}


# --- Trend ------------------------------------------------------------------

def test_linear_trend() -> None:
    t = fit_trend(yearly(10_000, 20_000, 30_000, 40_000))
    assert t.slope_per_year == pytest.approx(10_000, rel=1e-3)
    assert t.r2_linear == pytest.approx(1.0)
    assert t.better_fit == "linear"
    assert t.change_total == 30_000


def test_exponential_trend() -> None:
    t = fit_trend(yearly(10_000, 20_000, 40_000, 80_000))
    assert t.cagr == pytest.approx(100, rel=1e-2)
    assert t.better_fit == "exponential"


def test_negative_values_have_no_cagr() -> None:
    t = fit_trend(yearly(-5_000, 0, 5_000))
    assert t.cagr is None and t.better_fit == "linear"


def test_too_little_history() -> None:
    assert fit_trend({}) is None
    assert fit_trend(yearly(1_000)) is None
    assert fit_trend({D(2025, 1, 1): 1, D(2025, 3, 1): 2}) is None  # under 6 months


# --- Pure growth math -------------------------------------------------------

def test_no_contribution_grows_at_return() -> None:
    p = project(make_profile([Item("Brokerage 1", 100_000, "investments")],
                             assumptions=Assumptions(monthly_contribution=0, source={})))
    assert p.contribution_source == "assumption"
    assert p.at(10) == pytest.approx(100_000 * 1.07 ** 10)
    assert p.at(10, "conservative") == pytest.approx(100_000 * 1.04 ** 10)
    assert p.at(10, "optimistic") == pytest.approx(100_000 * 1.10 ** 10)
    assert p.at(10, real=True) == pytest.approx(100_000 * 1.07 ** 10 / 1.03 ** 10)


def test_each_category_grows_at_its_own_rate() -> None:
    p = project(make_profile(
        [Item("Bank Account 1", 1_000, "cash"), Item("House 1", 1_000, "real_estate"),
         Item("Car 1", 1_000, "vehicles"), Item("Art 1", 1_000, "other")],
        assumptions=Assumptions(monthly_contribution=0, source={}),
    ))
    expected = 1_000 * (1.02 ** 5 + 1.03 ** 5 + 0.85 ** 5 + 1)
    assert p.at(5) == pytest.approx(expected)


def test_contributions_pay_highest_rate_debt_first() -> None:
    profile = make_profile(
        [], [Item("Credit Card 1", 1_200, "credit_card", 25.0), Item("Student Loan 1", 10_000, "student", 5.0)],
        assumptions=Assumptions(monthly_contribution=100, source={}),
    )
    p = project(profile)
    # Year 1: $1,200 of payments; the card (25%) gets paid down before the loan.
    one_year_card_only = -(10_000 * 1.05) - max(0.0, 1_200 * 1.25 - 1_200)
    assert p.at(1) > one_year_card_only - 50


def test_negative_trend_goes_down_and_is_not_clamped() -> None:
    p = project(make_profile([Item("Bank Account 1", 5_000, "cash")],
                             history=yearly(20_000, 15_000, 10_000, 5_000)))
    assert p.contribution_source == "history"
    assert p.annual_contribution < 0
    assert p.at(5) < 0 and p.at(20) < p.at(10) < p.at(5)


# --- Contribution sources ---------------------------------------------------

def test_contribution_from_history_removes_market_growth() -> None:
    profile = make_profile([Item("Brokerage 1", 40_000, "investments")],
                           history=yearly(10_000, 20_000, 30_000, 40_000))
    p = project(profile)
    # Mean history balance 25k at 7% = 1,750/year of market growth.
    assert p.market_growth_per_year == pytest.approx(40_000 * 0.07 * 25_000 / 40_000)
    assert p.annual_contribution == pytest.approx(10_000 - 1_750, rel=1e-3)


def test_contribution_from_income_when_no_history() -> None:
    p = project(make_profile(income={2025: 60_000}))
    assert p.contribution_source == "income"
    assert p.annual_contribution == 6_000
    assert any("10%" in n for n in p.notes)


def test_no_data_means_zero_savings_and_a_note() -> None:
    p = project(make_profile())
    assert p.contribution_source == "none" and p.annual_contribution == 0
    assert any("--contribution" in n for n in p.notes)


def test_scenarios_spread_contributions() -> None:
    p = project(make_profile(assumptions=Assumptions(monthly_contribution=1_000, source={})))
    c, e, o = (p.scenarios[n].annual_contribution for n in ("conservative", "expected", "optimistic"))
    assert (c, e, o) == (9_000, 12_000, 15_000)
    assert p.at(20, "conservative") < p.at(20) < p.at(20, "optimistic")


def test_income_growth_raises_contributions_but_is_capped() -> None:
    fast = project(make_profile(income={2021: 40_000, 2025: 100_000},
                                assumptions=Assumptions(monthly_contribution=500, source={})))
    assert fast.contribution_growth == 10.0
    assert any("cap" in n for n in fast.notes)
    flat = project(make_profile(assumptions=Assumptions(monthly_contribution=500, source={})))
    assert fast.at(20) > flat.at(20)


def test_default_path_only_when_assumptions_changed() -> None:
    assert project(make_profile()).default_expected is None
    changed = Assumptions(investment_return=12, source={"investment_return": "cli"})
    p = project(make_profile([Item("Brokerage 1", 100_000, "investments")], assumptions=changed))
    assert p.default_expected is not None
    assert p.default_expected.at(10) < p.at(10)


def test_ages_and_start_date() -> None:
    p = project(make_profile(ages=(34, 31), scores=(745, 668), as_of=None), today=D(2026, 10, 18))
    assert p.ages_at[10] == (44, 41)
    assert p.start_date == D(2026, 10, 18)


def test_debts_without_rate_note() -> None:
    p = project(make_profile(debts=[Item("IOU 1", 100, "other")]))
    assert any("0% interest" in n for n in p.notes)
