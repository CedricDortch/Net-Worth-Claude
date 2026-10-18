"""Checks on the benchmark data in data/*.json and its loader."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from networth import reference_data
from networth.constants import STATES
from networth.errors import ReferenceDataError


# --- Age percentiles (SCF 2025) ---------------------------------------------

# Medians published by the Federal Reserve for the 2025 SCF. Our percentiles come from the
# disclosure-limited public file, so allow a small tolerance.
PUBLISHED_MEDIANS = {"under_35": 33_000, "45_54": 253_700, "55_64": 411_900,
                     "65_74": 431_900, "75_plus": 504_600}


@pytest.mark.parametrize(("key", "published"), PUBLISHED_MEDIANS.items())
def test_medians_match_fed_publication(ref: reference_data.ReferenceData, key: str, published: int) -> None:
    bracket = next(b for b in ref.age.brackets if b.key == key)
    assert bracket.median == pytest.approx(published, rel=0.015)


def test_all_households_median(ref: reference_data.ReferenceData) -> None:
    assert ref.age.all_households.median == pytest.approx(215_900, rel=0.01)


def test_every_age_has_one_bracket(ref: reference_data.ReferenceData) -> None:
    assert ref.age.bracket_for(24).key == "under_35"
    assert ref.age.bracket_for(35).key == "35_44"
    assert ref.age.bracket_for(80).key == "75_plus"
    assert ref.age.fine_bracket_for(24).key == "under_25"
    assert ref.age.fine_bracket_for(40) is None


def test_percentiles_rise_and_cover_the_tails(ref: reference_data.ReferenceData) -> None:
    for b in (*ref.age.brackets, *ref.age.fine_brackets):
        values = [b.percentiles[p] for p in sorted(b.percentiles)]
        assert values == sorted(values)
        assert {1, 10, 25, 50, 75, 90, 99} <= set(b.percentiles)
        assert b.sample_households > 50


# --- States -----------------------------------------------------------------

def test_all_states_present(ref: reference_data.ReferenceData) -> None:
    assert set(ref.states.states) == set(STATES)


def test_rpp_and_income_are_plausible(ref: reference_data.ReferenceData) -> None:
    assert ref.states.national.rpp == 100
    for s in ref.states.states.values():
        assert 80 < s.rpp < 120
        assert 40_000 < s.median_household_income < 150_000


def test_distribution_is_cumulative_and_matches_median(ref: reference_data.ReferenceData) -> None:
    for s in [ref.states.national, *ref.states.states.values()]:
        if s.distribution is None:
            continue
        bounds = sorted(s.distribution)
        shares = [s.distribution[b] for b in bounds]
        assert shares == sorted(shares) and 0 < shares[0] and shares[-1] <= 100
        if s.median_net_worth is not None:
            # The median must sit between the bounds where the distribution crosses 50%.
            below = max((b for b in bounds if s.distribution[b] < 50), default=0)
            above = min((b for b in bounds if s.distribution[b] > 50), default=float("inf"))
            assert below <= s.median_net_worth <= above, s.code


def test_michigan(ref: reference_data.ReferenceData) -> None:
    mi = ref.states.get("MI")
    assert mi.name == "Michigan" and mi.has_wealth_data
    assert mi.rpp < 100  # cheaper than the national average


def test_suppressed_states_are_flagged(ref: reference_data.ReferenceData) -> None:
    assert not ref.states.get("AK").has_wealth_data


# --- Credit -----------------------------------------------------------------

def test_credit(ref: reference_data.ReferenceData) -> None:
    assert ref.credit.national_average == 713
    assert ref.credit.state_average("MI") == 717
    assert all(600 < years[ref.credit.latest_year] < 800 for years in ref.credit.states.values())


@pytest.mark.parametrize(("score", "tier"), [
    (300, "Poor"), (579, "Poor"), (580, "Fair"), (669, "Fair"), (670, "Good"), (739, "Good"),
    (740, "Very Good"), (760, "Very Good"), (799, "Very Good"), (800, "Exceptional"), (850, "Exceptional"),
])
def test_credit_tiers(ref: reference_data.ReferenceData, score: int, tier: str) -> None:
    assert ref.credit.tier_for(score).name == tier


# --- Sources and loader -----------------------------------------------------

def test_every_source_is_cited(ref: reference_data.ReferenceData) -> None:
    assert len(ref.sources) == 5
    for s in ref.sources:
        assert s.name and s.url.startswith("https://") and s.retrieved


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ReferenceDataError, match="missing"):
        reference_data.load(tmp_path)


def test_damaged_file_raises(tmp_path: Path) -> None:
    for f in reference_data.DATA_DIR.glob("*.json"):
        shutil.copy(f, tmp_path / f.name)
    data = json.loads((tmp_path / "state_data.json").read_text())
    del data["states"]["MI"]
    (tmp_path / "state_data.json").write_text(json.dumps(data))
    with pytest.raises(ReferenceDataError, match="50 states"):
        reference_data.load(tmp_path)
