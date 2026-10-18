from __future__ import annotations

import datetime as dt

import pytest

from networth import analysis
from networth import report
from conftest import make_profile
from networth.models import Assumptions, Item

D = dt.date


def build(profile, ref) -> report.Report:
    return report.build_report(analysis.analyze(profile, ref))


@pytest.fixture
def weak(ref) -> report.Report:
    return build(make_profile(
        [Item("Bank Account 1", 400, "cash"), Item("Car 1", 14_000, "vehicles")],
        [Item("Credit Card 1", 9_800, "credit_card", 27.9), Item("Car Loan 1", 16_500, "auto", 11.2)],
        ages=(38,), scores=(601,), state="OH", expenses=3_900,
        history={D(2022 + i, 12, 31): -4_000 - 3_500 * i for i in range(4)},
        income={2022: 52_000, 2023: 55_000, 2024: 58_000, 2025: 61_000},
    ), ref)


@pytest.fixture
def strong(ref) -> report.Report:
    return build(make_profile(
        [Item("Bank Account 1", 40_000, "cash"), Item("Brokerage 1", 600_000, "investments"),
         Item("401k 1", 300_000, "retirement")],
        ages=(30,), scores=(815,), expenses=4_000,
        history={D(2022 + i, 12, 31): 500_000 + 140_000 * i for i in range(4)},
    ), ref)


# --- Tone -------------------------------------------------------------------

def test_bad_finances_get_blunt_language(weak: report.Report) -> None:
    assert weak.grade == "F"
    assert weak.headline.startswith("Your finances are in serious trouble.")
    assert "in the hole in 10 years" in weak.headline
    text = report.render_text(weak)
    for phrase in ["for nothing", "spending your raises", "One emergency puts you into debt",
                   "lose value every year", "spending more than you earn"]:
        assert phrase in text
    assert not any(f.severity == "good" for f in weak.findings if "credit" in f.text)


def test_good_finances_get_direct_praise(strong: report.Report) -> None:
    assert strong.grade == "A"
    assert strong.headline.startswith("Your finances are strong.")
    assert "Keep doing exactly what you're doing." in strong.headline
    assert all(f.severity != "bad" for f in strong.findings)


def test_every_sentence_has_a_number_or_label(weak: report.Report) -> None:
    for f in weak.findings:
        assert any(ch.isdigit() for ch in f.text) or "no " in f.text.lower(), f.text


def test_criticizes_finances_not_the_person(weak: report.Report) -> None:
    text = report.render_text(weak).lower()
    for insult in ["stupid", "lazy", "irresponsible", "idiot", "pathetic", "failure"]:
        assert insult not in text


@pytest.mark.parametrize("net_worth", [300_000, 120_000, 60_000])
def test_low_grade_headline_never_contradicts_the_rank(ref, net_worth: float) -> None:
    # Age 40, house fully mortgaged, no cash: low grades even when net worth is fine for the age.
    r = analysis.analyze(make_profile(
        [Item("House 1", net_worth * 2, "real_estate"), Item("401k 1", net_worth, "retirement")],
        [Item("Mortgage 1", net_worth * 2, "mortgage", 6.0)],
        ages=(40,), scores=(720,), state="MI",
        history={D(2022 + i, 12, 31): net_worth * (0.7 + 0.1 * i) for i in range(4)},
    ), ref)
    rep = report.build_report(r)
    assert rep.grade in "DF"
    assert r.age_rank.standard.phrase in rep.headline
    if r.age_rank.standard.percentile >= 50:
        assert "You are behind" not in rep.headline and "behind the median" not in rep.headline
    else:
        assert "behind the median" in rep.headline


@pytest.mark.parametrize(("net_worth", "start"), [
    (135_000, "You're ahead of most people your age (top "),
    (45_000, "You're average for your age"),
])
def test_c_headlines(ref, net_worth: float, start: str) -> None:
    rep = build(make_profile([Item("Bank Account 1", 1, "cash"), Item("Brokerage 1", net_worth, "investments")],
                             ages=(27,), scores=(762,), state="OH", expenses=4_000,
                             history={D(2024, 12, 1): net_worth / 3, D(2026, 10, 1): net_worth}), ref)
    assert rep.grade == "C"
    assert rep.headline.startswith(start)


# --- Content ----------------------------------------------------------------

def test_sections_and_disclaimer(strong: report.Report) -> None:
    assert set(strong.sections) == set(report.SECTION_TITLES)
    assert strong.disclaimer == report.DISCLAIMER
    text = report.render_text(strong)
    assert text.rstrip().endswith("It is not financial, tax, or legal advice.")
    for title in report.SECTION_TITLES.values():
        assert title.upper() in text


def test_no_cash_is_called_out(ref) -> None:
    rep = build(make_profile([Item("Brokerage 1", 120_000, "investments")], ages=(27,), scores=(762,), state="OH"),
                ref)
    assert any("no cash listed at all" in f.text for f in rep.findings)
    assert rep.suggestions[0].key == "emergency_fund"
    assert "emergency fund" in " ".join(rep.verdict)


def test_short_history_warns_projection_may_be_optimistic(ref) -> None:
    rep = build(make_profile([Item("Brokerage 1", 120_000, "investments")],
                             history={D(2025, 1, 1): 30_000, D(2026, 10, 1): 120_000}), ref)
    text = " ".join(rep.sections["projections"])
    assert "too optimistic" in text and "--contribution" in text
    assert "not used for the forecast" in text
    assert any(s.key == "real_savings" for s in rep.suggestions)


def test_points_to_next_grade(ref) -> None:
    rep = build(make_profile([Item("Brokerage 1", 135_000, "investments")], ages=(27,), scores=(762,), state="OH",
                             history={D(2024, 12, 1): 30_000, D(2026, 10, 1): 135_000}), ref)
    assert rep.grade == "C" and 75 <= rep.score < 80
    assert f"You're {80 - rep.score:.1f} points from a B." in rep.verdict


# --- Suggestions ------------------------------------------------------------

def test_suggestions_are_ranked_and_capped(weak: report.Report) -> None:
    keys = [s.key for s in weak.suggestions]
    assert len(keys) <= 7
    assert [s.priority for s in weak.suggestions] == sorted(s.priority for s in weak.suggestions)
    assert "high_interest" in keys and "emergency_fund" in keys and "credit" in keys
    hi = next(s for s in weak.suggestions if s.key == "high_interest")
    assert hi.impact_dollars == pytest.approx(9_800 * 0.279 + 16_500 * 0.112)
    assert "Credit Card 1 is at 27.9%" in hi.reason


def test_each_suggestion_explains_itself(weak: report.Report) -> None:
    for s in weak.suggestions:
        assert s.title and s.reason and s.impact


def test_strong_profile_gets_optimize_not_fixes(strong: report.Report) -> None:
    keys = {s.key for s in strong.suggestions}
    assert "optimize" in keys
    assert not keys & {"high_interest", "emergency_fund", "negative_trend", "credit"}


def test_idle_cash(ref) -> None:
    rep = build(make_profile([Item("Bank Account 1", 100_000, "cash")], expenses=4_000), ref)
    idle = next(s for s in rep.suggestions if s.key == "idle_cash")
    assert idle.impact_dollars == pytest.approx((100_000 - 24_000) * 0.05)


def test_couple_suggestions(ref) -> None:
    rep = build(make_profile(
        [Item("House 1", 340_000, "real_estate")],
        [Item("Student Loan 1", 27_000, "student", 5.0, owner="partner2")],
        ages=(34, 31), scores=(745, 668), state="GA",
    ), ref)
    credit = next(s for s in rep.suggestions if s.key == "credit")
    assert "Partner 2's" in credit.title and "joint loan" in credit.title
    assert "couple_credit" not in {s.key for s in rep.suggestions}
    assert any("Partner 2 holds 100%" in f.text for f in rep.findings)


# --- Assumption honesty check ------------------------------------------------

def test_unrealistic_assumptions_are_challenged(ref) -> None:
    a = Assumptions(investment_return=14, inflation=0, monthly_contribution=3_000,
                    source={"investment_return": "cli", "inflation": "cli", "monthly_contribution": "cli"})
    rep = build(make_profile([Item("Brokerage 1", 50_000, "investments")], assumptions=a,
                             history={D(2022 + i, 12, 31): 20_000 + 10_000 * i for i in range(4)}), ref)
    fields = {w.field for w in rep.assumption_warnings}
    assert fields == {"investment_return", "inflation", "monthly_contribution"}
    assert rep.assumption_comparison.startswith("In 20 years:")
    assert "ASSUMPTION CHECK" in report.render_text(rep)


def test_reasonable_assumptions_pass(ref) -> None:
    a = Assumptions(investment_return=6, source={"investment_return": "cli"})
    rep = build(make_profile(assumptions=a), ref)
    assert rep.assumption_warnings == ()
    assert rep.assumption_comparison is not None  # still show yours vs. defaults
    assert any("Investment Return: 6% (cli)" in s for s in rep.sections["assumptions"])


def test_defaults_show_no_check(strong: report.Report) -> None:
    assert strong.assumption_warnings == () and strong.assumption_comparison is None
