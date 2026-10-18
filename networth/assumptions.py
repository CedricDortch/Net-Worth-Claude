"""Growth assumptions: defaults < input file < CLI flags."""

from __future__ import annotations

from dataclasses import dataclass, fields

from networth.errors import InvalidAssumptionError
from networth.models import Assumptions
from networth.normalize import norm_label, parse_money


@dataclass(frozen=True)
class AssumptionSpec:
    field: str
    flag: str
    label: str              # how it's written in the input file
    low: float
    high: float | None      # None = no upper limit
    unit: str               # "%" or "$"
    aliases: tuple[str, ...] = ()

    def describe_range(self) -> str:
        if self.high is None:
            return f"${self.low:,.0f} or more" if self.unit == "$" else f"{self.low:g}% or more"
        return f"{self.low:g} to {self.high:g}" + (" (percent)" if self.unit == "%" else " (dollars)")


SPECS: tuple[AssumptionSpec, ...] = (
    AssumptionSpec("investment_return", "--return", "Investment Return", -10, 20, "%", ("return", "expected return")),
    AssumptionSpec("scenario_spread", "--spread", "Scenario Spread", 0, 10, "%", ("spread",)),
    AssumptionSpec("inflation", "--inflation", "Inflation", 0, 15, "%", ("inflation rate",)),
    AssumptionSpec("cash_rate", "--cash-rate", "Cash Rate", 0, 10, "%", ("cash interest", "savings rate")),
    AssumptionSpec("home_appreciation", "--home-growth", "Home Growth", -10, 15, "%", ("home appreciation",)),
    AssumptionSpec("vehicle_depreciation", "--car-depreciation", "Car Depreciation", 0, 50, "%", ("vehicle depreciation",)),
    AssumptionSpec("monthly_contribution", "--contribution", "Monthly Contribution", 0, None, "$",
                   ("monthly contributions", "monthly savings", "contribution")),
    AssumptionSpec("income_growth", "--income-growth", "Income Growth", -20, 30, "%", ()),
)

_BY_LABEL = {norm_label(a): s for s in SPECS for a in (s.label, *s.aliases)}


def spec_for_label(label: str) -> AssumptionSpec | None:
    return _BY_LABEL.get(norm_label(label))


def _parse(spec: AssumptionSpec, raw: str | float, where: str) -> float:
    if isinstance(raw, (int, float)):
        value: float | None = float(raw)
    else:
        text = str(raw).strip().rstrip("%").strip()
        value = parse_money(text)
    name = f"{spec.label} ({spec.flag})" if where == "cli" else spec.label
    if value is None:
        raise InvalidAssumptionError(f"{name} must be a number: {spec.describe_range()}.")
    if value < spec.low or (spec.high is not None and value > spec.high):
        raise InvalidAssumptionError(f"{name} is out of range. Allowed: {spec.describe_range()}.")
    return value


def resolve(file_values: dict[str, str | float], cli_values: dict[str, str | float | None]) -> Assumptions:
    """Build Assumptions. Keys of both dicts are field names. Records each value's source."""
    values: dict[str, float | None] = {}
    source: dict[str, str] = {}
    for spec in SPECS:
        cli = cli_values.get(spec.field)
        if cli is not None:
            values[spec.field] = _parse(spec, cli, "cli")
            source[spec.field] = "cli"
        elif spec.field in file_values:
            values[spec.field] = _parse(spec, file_values[spec.field], "file")
            source[spec.field] = "file"
        else:
            source[spec.field] = "default"
    known = {f.name for f in fields(Assumptions)}
    return Assumptions(**{k: v for k, v in values.items() if k in known}, source=source)
