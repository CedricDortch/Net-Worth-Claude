"""The one loader for benchmark data in data/*.json (built by networth/scripts/build_reference_data.py).

Analysis code gets every benchmark number from here; none are hard-coded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from networth.constants import STATES
from networth.errors import ReferenceDataError

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    retrieved: str

    def citation(self) -> str:
        return f"{self.name}. {self.url} (retrieved {self.retrieved})"


# ---------------------------------------------------------------------------
# Age percentiles
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgeBracket:
    key: str
    label: str
    min_age: int
    max_age: int | None
    percentiles: dict[int, float]   # percentile (1-99) -> net worth in dollars
    mean: float
    median_income: float
    sample_households: int

    @property
    def median(self) -> float:
        return self.percentiles[50]

    def contains(self, age: int) -> bool:
        return age >= self.min_age and (self.max_age is None or age <= self.max_age)


@dataclass(frozen=True)
class AgeData:
    source: Source
    dollars: str
    brackets: tuple[AgeBracket, ...]        # standard Fed brackets: under 35 ... 75+
    fine_brackets: tuple[AgeBracket, ...]   # under 25, 25-29, 30-34 (smaller samples)
    all_households: AgeBracket

    def bracket_for(self, age: int) -> AgeBracket:
        return next(b for b in self.brackets if b.contains(age))

    def fine_bracket_for(self, age: int) -> AgeBracket | None:
        return next((b for b in self.fine_brackets if b.contains(age)), None)


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StateInfo:
    code: str
    name: str
    median_net_worth: float | None        # None = suppressed by Census
    mean_net_worth: float | None
    distribution: dict[float, float] | None   # dollar bound -> cumulative % of households below it
    households_thousands: float | None
    median_household_income: float
    income_year: int
    rpp: float                            # cost of living, United States = 100

    @property
    def has_wealth_data(self) -> bool:
        return self.median_net_worth is not None


@dataclass(frozen=True)
class StateData:
    sources: tuple[Source, ...]
    national: StateInfo
    states: dict[str, StateInfo]

    def get(self, code: str) -> StateInfo:
        return self.states[code]


# ---------------------------------------------------------------------------
# Credit
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreditTier:
    name: str
    min: int
    max: int


@dataclass(frozen=True)
class CreditData:
    source: Source
    latest_year: int
    national: dict[int, int]            # year -> average FICO
    states: dict[str, dict[int, int]]   # code -> year -> average FICO
    tiers: tuple[CreditTier, ...]

    @property
    def national_average(self) -> int:
        return self.national[self.latest_year]

    def state_average(self, code: str) -> int:
        return self.states[code][self.latest_year]

    def tier_for(self, score: int) -> CreditTier:
        return next(t for t in self.tiers if t.min <= score <= t.max)


@dataclass(frozen=True)
class ReferenceData:
    age: AgeData
    states: StateData
    credit: CreditData

    @property
    def sources(self) -> tuple[Source, ...]:
        return (self.age.source, *self.states.sources, self.credit.source)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _read(data_dir: Path, name: str) -> dict[str, Any]:
    path = data_dir / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReferenceDataError(
            f"Benchmark file {name} is missing. Rebuild it with: python -m networth.scripts.build_reference_data"
        ) from None
    except json.JSONDecodeError:
        raise ReferenceDataError(f"Benchmark file {name} is damaged. Rebuild it with "
                                 "python -m networth.scripts.build_reference_data") from None


def _bracket(raw: dict[str, Any]) -> AgeBracket:
    return AgeBracket(
        key=raw["key"], label=raw["label"], min_age=raw["min_age"], max_age=raw["max_age"],
        percentiles={int(p): float(v) for p, v in raw["percentiles"].items()},
        mean=float(raw["mean"]), median_income=float(raw["median_income"]),
        sample_households=int(raw["sample_households"]),
    )


def _state(code: str, raw: dict[str, Any]) -> StateInfo:
    dist = raw["net_worth_distribution"]
    return StateInfo(
        code=code, name=raw["name"],
        median_net_worth=raw["median_net_worth"], mean_net_worth=raw["mean_net_worth"],
        distribution={float(b): float(v) for b, v in dist.items()} if dist else None,
        households_thousands=raw["households_thousands"],
        median_household_income=float(raw["median_household_income"]),
        income_year=int(raw["income_year"]), rpp=float(raw["rpp"]),
    )


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ReferenceDataError(f"Benchmark data failed a check: {message}. "
                                 "Rebuild with: python -m networth.scripts.build_reference_data")


@lru_cache(maxsize=4)
def load(data_dir: Path = DATA_DIR) -> ReferenceData:
    try:
        age_raw = _read(data_dir, "age_percentiles.json")
        state_raw = _read(data_dir, "state_data.json")
        credit_raw = _read(data_dir, "credit_averages.json")

        age = AgeData(
            source=Source(age_raw["source"]["name"], age_raw["source"]["url"], age_raw["retrieved"]),
            dollars=age_raw["dollars"],
            brackets=tuple(_bracket(b) for b in age_raw["brackets"]),
            fine_brackets=tuple(_bracket(b) for b in age_raw["fine_brackets"]),
            all_households=_bracket(age_raw["all"]),
        )
        states = StateData(
            sources=tuple(Source(s["name"], s["url"], state_raw["retrieved"]) for s in state_raw["sources"]),
            national=_state("US", state_raw["national"]),
            states={code: _state(code, raw) for code, raw in state_raw["states"].items()},
        )
        credit = CreditData(
            source=Source(credit_raw["source"]["name"], credit_raw["source"]["url"], credit_raw["retrieved"]),
            latest_year=int(credit_raw["latest_year"]),
            national={int(y): int(v) for y, v in credit_raw["national"].items()},
            states={code: {int(y): int(v) for y, v in years.items()}
                    for code, years in credit_raw["states"].items()},
            tiers=tuple(CreditTier(t["name"], t["min"], t["max"]) for t in credit_raw["tiers"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceDataError(f"Benchmark data has an unexpected format ({type(exc).__name__}: {exc}). "
                                 "Rebuild with: python -m networth.scripts.build_reference_data") from None

    _check(set(states.states) == set(STATES), "state_data.json must cover all 50 states + DC")
    _check(set(credit.states) == set(STATES), "credit_averages.json must cover all 50 states + DC")
    _check(credit.latest_year in credit.national, "national credit average missing for the latest year")
    for b in (*age.brackets, *age.fine_brackets, age.all_households):
        values = [b.percentiles[p] for p in sorted(b.percentiles)]
        _check(values == sorted(values) and 50 in b.percentiles, f"percentiles for {b.label} must rise")
    for age_ in range(16, 111):
        _check(sum(b.contains(age_) for b in age.brackets) == 1, f"exactly one age bracket must contain {age_}")
    return ReferenceData(age=age, states=states, credit=credit)
