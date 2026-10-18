from __future__ import annotations

import pytest

from networth import assumptions
from networth.errors import InvalidAssumptionError


def test_defaults() -> None:
    a = assumptions.resolve({}, {})
    assert a.investment_return == 7.0 and a.inflation == 3.0 and a.monthly_contribution is None
    assert set(a.source.values()) == {"default"}


def test_cli_beats_file_beats_default() -> None:
    a = assumptions.resolve(
        {"investment_return": "6", "inflation": "3.5%"},
        {"investment_return": "8", "inflation": None},
    )
    assert a.investment_return == 8 and a.source["investment_return"] == "cli"
    assert a.inflation == 3.5 and a.source["inflation"] == "file"
    assert a.cash_rate == 2.0 and a.source["cash_rate"] == "default"


def test_contribution_accepts_dollars() -> None:
    a = assumptions.resolve({"monthly_contribution": "$1,500"}, {})
    assert a.monthly_contribution == 1500


@pytest.mark.parametrize(("field", "value"), [
    ("investment_return", "25"), ("investment_return", "-11"), ("inflation", "16"),
    ("scenario_spread", "11"), ("vehicle_depreciation", "60"), ("monthly_contribution", "-5"),
    ("income_growth", "31"),
])
def test_out_of_range(field: str, value: str) -> None:
    with pytest.raises(InvalidAssumptionError, match="out of range"):
        assumptions.resolve({}, {field: value})


def test_not_a_number_names_the_flag() -> None:
    with pytest.raises(InvalidAssumptionError, match=r"--return.*number"):
        assumptions.resolve({}, {"investment_return": "lots"})


def test_label_aliases() -> None:
    assert assumptions.spec_for_label("Expected Return").field == "investment_return"
    assert assumptions.spec_for_label("monthly savings").field == "monthly_contribution"
    assert assumptions.spec_for_label("nope") is None
