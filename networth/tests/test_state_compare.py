from __future__ import annotations

import pytest

from networth.analysis.state_compare import compare_state, rank_in_distribution
from conftest import make_profile
from networth.models import Item

DIST = {0.0: 10.0, 25_000.0: 25.0, 100_000.0: 40.0, 500_000.0: 70.0}


@pytest.mark.parametrize(("value", "pct", "bound"), [
    (-1_000, 10, "upper"), (0, 10, "upper"), (12_500, 17.5, "exact"), (100_000, 40, "exact"),
    (300_000, 55, "exact"), (500_000, 70, "lower"), (2_000_000, 70, "lower"),
])
def test_rank_in_distribution(value: float, pct: float, bound: str) -> None:
    r = rank_in_distribution(value, DIST)
    assert r.percentile == pytest.approx(pct) and r.bound == bound


def test_phrases() -> None:
    assert rank_in_distribution(-5, DIST).phrase == "bottom 10%"
    assert rank_in_distribution(2_000_000, DIST).phrase == "top 30% or higher"
    assert rank_in_distribution(300_000, DIST).phrase == "top 45%"


def test_ohio(ref) -> None:
    oh = ref.states.get("OH")
    s = compare_state(make_profile([Item("Brokerage 1", 120_000, "investments")], state="OH", ages=(27,)), ref)
    assert not s.used_national_fallback
    assert s.state_median == oh.median_net_worth
    assert s.adjusted_net_worth == pytest.approx(120_000 * 100 / oh.rpp)
    assert s.adjusted_net_worth > 120_000  # Ohio is cheaper than average
    assert s.in_state.bound == "exact"
    assert s.adjusted_age_rank.standard.percentile > 0
    assert any("all ages" in n for n in s.notes)


def test_suppressed_state_falls_back_to_national(ref) -> None:
    ak = ref.states.get("AK")
    s = compare_state(make_profile(state="AK"), ref)
    assert s.used_national_fallback
    assert s.state_median == pytest.approx(ref.states.national.median_net_worth * ak.rpp / 100)
    assert s.in_state is not None
    assert any("doesn't publish" in n for n in s.notes)


def test_income_comparison(ref) -> None:
    s = compare_state(make_profile(state="MI", income={2024: 50_000, 2025: 76_800}), ref)
    assert s.latest_income == 76_800
    assert s.income_vs_state == pytest.approx(76_800 / ref.states.get("MI").median_household_income)
    assert compare_state(make_profile(state="MI"), ref).income_vs_state is None
