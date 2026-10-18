from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from networth import reference_data
from networth.models import Assumptions, Item, NetWorthProfile, Person
from networth.parsers.document import Line, ParsedDocument, Table

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def make_profile(
    assets: list[Item] | None = None,
    debts: list[Item] | None = None,
    *,
    ages: tuple[int, ...] = (29,),
    scores: tuple[int, ...] = (712,),
    state: str = "TX",
    history: dict[dt.date, float] | None = None,
    income: dict[int, float] | None = None,
    expenses: float | None = None,
    assumptions: Assumptions | None = None,
    as_of: dt.date | None = dt.date(2026, 1, 1),
) -> NetWorthProfile:
    """A NetWorthProfile with sensible defaults; override only what a test cares about."""
    return NetWorthProfile(
        household_type="couple" if len(ages) == 2 else "single",
        people=tuple(Person(a, s) for a, s in zip(ages, scores)),
        state=state,
        assets=tuple(assets if assets is not None else [Item("Brokerage 1", 10_000, "investments")]),
        debts=tuple(debts or []),
        net_worth_history=dict(sorted((history or {}).items())),
        income_history=income or {},
        monthly_expenses=expenses,
        assumptions=assumptions or Assumptions(source={}),
        as_of=as_of,
    )


@pytest.fixture(scope="session")
def ref() -> reference_data.ReferenceData:
    return reference_data.load()


def text_doc(*lines: str) -> ParsedDocument:
    return ParsedDocument(
        source=Path("test.txt"),
        lines=tuple(Line(t, f"Line {i}") for i, t in enumerate(lines, start=1)),
    )


def table_doc(*rows: list[str]) -> ParsedDocument:
    return ParsedDocument(source=Path("test.csv"), tables=(Table(rows=tuple(tuple(r) for r in rows)),))


@pytest.fixture
def samples() -> Path:
    return SAMPLES
