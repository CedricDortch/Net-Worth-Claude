"""Shared display formatting. Round only here, never in calculations."""

from __future__ import annotations


def format_money(value: float, compact: bool = False) -> str:
    """$30,000 · -$22,000 · compact: $30K, $1.2M."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    if compact:
        for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if v >= limit:
                text = f"{v / limit:.1f}".rstrip("0").rstrip(".")
                return f"{sign}${text}{suffix}"
    return f"{sign}${v:,.0f}"


def format_percent(value: float) -> str:
    """7.0 -> 7% · 5.5 -> 5.5%."""
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"
