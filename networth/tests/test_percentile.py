from __future__ import annotations

import pytest

from networth.analysis.percentile import estimate_percentile, rank_by_age, rank_phrase
from conftest import make_profile
from networth.models import Item

BREAKS = {1: -10_000, 10: 0, 25: 10_000, 50: 50_000, 75: 150_000, 90: 400_000, 99: 2_000_000}


@pytest.mark.parametrize(("value", "pct"), [
    (50_000, 50), (30_000, 37.5), (10_000, 25), (150_000, 75), (275_000, 82.5),
    (-50_000, 0.5), (5_000_000, 99.5), (2_000_000, 99.5),
])
def test_interpolation(value: float, pct: float) -> None:
    assert estimate_percentile(value, BREAKS) == pytest.approx(pct)


def test_ties_use_the_highest_matching_breakpoint() -> None:
    assert estimate_percentile(0, {1: 0, 10: 0, 50: 100}) == pytest.approx(10)


@pytest.mark.parametrize(("pct", "phrase"), [
    (75.3, "top 25%"), (50, "top 50%"), (49.4, "bottom 49%"), (99.5, "top 1%"), (0.5, "bottom 1%"),
])
def test_phrase(pct: float, phrase: str) -> None:
    assert rank_phrase(pct) == phrase


def test_rank_by_age_uses_real_data(ref) -> None:
    r = rank_by_age(make_profile([Item("Brokerage 1", 32_820, "investments")], ages=(22,)), ref.age)
    assert r.standard.bracket.key == "under_35"
    assert r.standard.percentile == pytest.approx(50, abs=0.5)
    assert r.standard.gap_to_median == pytest.approx(0, abs=1)
    assert r.fine.bracket.key == "under_25"
    assert r.fine.percentile > r.standard.percentile  # younger peers have less
    assert r.standard.next_tier.percentile == 75


def test_no_fine_bracket_over_35(ref) -> None:
    r = rank_by_age(make_profile(ages=(50,)), ref.age)
    assert r.fine is None and r.standard.bracket.key == "45_54"


def test_couple_uses_older_partner(ref) -> None:
    r = rank_by_age(make_profile(ages=(31, 36), scores=(700, 700)), ref.age)
    assert r.reference_age == 36 and r.standard.bracket.key == "35_44"


def test_top_of_the_scale_has_no_next_tier(ref) -> None:
    r = rank_by_age(make_profile([Item("Brokerage 1", 50_000_000, "investments")]), ref.age)
    assert r.standard.next_tier is None and r.standard.phrase == "top 1%"
