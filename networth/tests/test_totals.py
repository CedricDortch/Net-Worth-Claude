from __future__ import annotations

import pytest

from networth.analysis.totals import compute_totals
from conftest import make_profile
from networth.models import Item


def test_snapshot() -> None:
    t = compute_totals(make_profile(
        [Item("Bank Account 1", 30_000, "cash"), Item("Car 1", 2_000, "vehicles"),
         Item("401k 1", 45_000, "retirement"), Item("Brokerage 1", 3_000, "investments")],
        [Item("Student Loan 1", 18_000, "student", 5.5), Item("Credit Card 1", 4_200, "credit_card", 24.9)],
        expenses=3_000,
    ))
    assert t.total_assets == 80_000 and t.total_debts == 22_200 and t.net_worth == 57_800
    assert t.debt_to_asset == pytest.approx(22_200 / 80_000)
    assert t.liquid_net_worth == 30_000 + 3_000 - 4_200
    assert t.asset_mix["retirement"] == pytest.approx(56.25)
    assert t.debt_mix["credit_card"] == pytest.approx(4_200 / 22_200 * 100)
    assert t.weighted_debt_rate == pytest.approx((18_000 * 5.5 + 4_200 * 24.9) / 22_200)
    assert t.high_interest_debt == 4_200
    assert t.yearly_interest_cost == pytest.approx(18_000 * 0.055 + 4_200 * 0.249)
    assert t.emergency_fund_months == 10
    assert t.depreciating_share == pytest.approx(2.5)
    assert t.by_owner == {}


def test_no_assets_no_division_by_zero() -> None:
    t = compute_totals(make_profile([], [Item("Credit Card 1", 500, "credit_card")]))
    assert t.debt_to_asset is None and t.depreciating_share is None and t.net_worth == -500


def test_unknown_expenses_and_rates() -> None:
    t = compute_totals(make_profile(debts=[Item("IOU 1", 100, "other")]))
    assert t.emergency_fund_months is None
    assert t.weighted_debt_rate is None and t.yearly_interest_cost == 0


def test_couple_owner_breakdown() -> None:
    t = compute_totals(make_profile(
        [Item("401k 1", 60_000, "retirement", owner="partner1"), Item("House 1", 300_000, "real_estate")],
        [Item("Student Loan 1", 27_000, "student", owner="partner2")],
        ages=(34, 31), scores=(745, 668),
    ))
    assert t.by_owner == {"partner1": (60_000, 0), "partner2": (0, 27_000), "joint": (300_000, 0)}
