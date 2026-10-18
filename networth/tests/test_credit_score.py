"""Credit assessment (analysis/credit.py) and the health score (analysis/score.py)."""

from __future__ import annotations

import datetime as dt

import pytest

from networth import analysis
from networth.analysis.credit import assess_credit
from networth.analysis.score import credit_score_points, debt_score, emergency_score, grade_for, piecewise, trend_score
from networth.analysis.projections import fit_trend
from networth.analysis.totals import compute_totals
from conftest import make_profile
from networth.models import Item


# --- Credit -----------------------------------------------------------------

def test_single_credit(ref) -> None:
    c = assess_credit(make_profile(scores=(762,), state="OH"), ref.credit)
    (p,) = c.people
    assert p.tier.name == "Very Good" and p.next_tier.name == "Exceptional" and p.points_to_next_tier == 38
    assert p.vs_national == 762 - 713 and p.vs_state == 762 - 713
    assert c.scoring_score == 762 and c.gap is None


def test_couple_uses_lower_score(ref) -> None:
    c = assess_credit(make_profile(ages=(34, 31), scores=(745, 668), state="GA"), ref.credit)
    assert c.scoring_score == 668 and c.gap == 77
    assert c.people[1].tier.name == "Fair"


def test_top_tier_has_no_next(ref) -> None:
    (p,) = assess_credit(make_profile(scores=(820,)), ref.credit).people
    assert p.next_tier is None and p.points_to_next_tier is None


# --- Score pieces -----------------------------------------------------------

def test_piecewise_and_grades() -> None:
    assert piecewise(2, [(0, 0), (4, 100)]) == 50
    assert piecewise(-1, [(0, 0), (4, 100)]) == 0 and piecewise(9, [(0, 0), (4, 100)]) == 100
    assert [grade_for(s) for s in (95, 90, 89.9, 80, 79.9, 65, 64.9, 50, 49.9, 0)] == \
        ["A", "A", "B", "B", "C", "C", "D", "D", "F", "F"]


@pytest.mark.parametrize(("score", "points"), [(300, 0), (580, 20), (670, 50), (740, 80), (800, 100), (850, 100)])
def test_credit_points(score: int, points: float) -> None:
    assert credit_score_points(score) == points


def test_trend_score() -> None:
    def history(slope: float):
        return fit_trend({dt.date(2021 + i, 12, 31): 50_000 + slope * i for i in range(4)})
    assert trend_score(None, 60_000)[0] is None
    # Dates a year apart aren't exactly 365.25 days, hence the small tolerance.
    assert trend_score(history(9_000), 60_000)[0] == pytest.approx(100, abs=0.1)    # 15% of 60k
    assert trend_score(history(4_500), 60_000)[0] == pytest.approx(62.5, abs=0.1)
    assert trend_score(history(0), 60_000)[0] == pytest.approx(25, abs=0.1)
    assert trend_score(history(-20_000), 60_000)[0] == 0


def test_debt_score() -> None:
    assert debt_score(compute_totals(make_profile()))[0] == 100
    assert debt_score(compute_totals(make_profile([], [Item("Credit Card 1", 1, "credit_card")])))[0] == 0
    mortgage = compute_totals(make_profile([Item("House 1", 100_000, "real_estate")],
                                           [Item("Mortgage 1", 55_000, "mortgage", 6.0)]))
    assert debt_score(mortgage)[0] == pytest.approx(50)
    card = compute_totals(make_profile([Item("House 1", 100_000, "real_estate")],
                                       [Item("Mortgage 1", 55_000, "mortgage", 6.0),
                                        Item("Credit Card 1", 10_000, "credit_card", 25.0)]))
    assert debt_score(card)[0] < 30


def test_emergency_score() -> None:
    cash = [Item("Bank Account 1", 9_000, "cash")]
    assert emergency_score(compute_totals(make_profile()))[0] == 0              # no cash at all
    assert emergency_score(compute_totals(make_profile(cash)))[0] is None       # expenses unknown
    assert emergency_score(compute_totals(make_profile(cash, expenses=3_000)))[0] == 70
    assert emergency_score(compute_totals(make_profile(cash, expenses=1_000)))[0] == 100


# --- Whole score ------------------------------------------------------------

def test_missing_components_are_redistributed(ref) -> None:
    r = analysis.analyze(make_profile([Item("Bank Account 1", 5_000, "cash")]), ref)
    s = r.score
    assert set(s.missing) == {"Net worth trend", "Emergency fund"}
    assert sum(c.weight for c in s.components) == pytest.approx(100)
    assert next(c for c in s.components if c.key == "age_percentile").weight == pytest.approx(30 * 100 / 70)


def test_strong_and_weak_profiles(ref) -> None:
    strong = analysis.analyze(make_profile(
        [Item("Bank Account 1", 40_000, "cash"), Item("Brokerage 1", 900_000, "investments")],
        ages=(30,), scores=(820,), expenses=4_000,
        history={dt.date(2022 + i, 12, 31): 500_000 + 110_000 * i for i in range(4)},
    ), ref).score
    weak = analysis.analyze(make_profile(
        [Item("Car 1", 8_000, "vehicles")],
        [Item("Credit Card 1", 15_000, "credit_card", 27.0), Item("Car Loan 1", 20_000, "auto", 9.0)],
        ages=(40,), scores=(590,), expenses=3_000,
        history={dt.date(2022 + i, 12, 31): -10_000 - 5_000 * i for i in range(4)},
    ), ref).score
    assert strong.grade == "A" and strong.score >= 90
    assert weak.grade == "F" and weak.score < 30


def test_analyze_sample_end_to_end(ref, samples) -> None:
    from networth import extractor
    from networth.models import Assumptions, Person
    from networth.parsers import parse_file
    ex = extractor.extract(parse_file(samples / "sample_input.csv"))
    profile = extractor.build_profile(ex, household_type="single", people=[Person(29, 712)], state="TX",
                                      monthly_expenses=ex.monthly_expenses, assumptions=Assumptions(source={}))
    r = analysis.analyze(profile, ref)
    assert r.totals.net_worth == 54_800
    assert r.income.average_savings_rate == pytest.approx(19.5, abs=0.1)
    assert r.projections.contribution_source == "history"
    assert 0 <= r.score.score <= 100 and r.score.grade in "ABCDF"
