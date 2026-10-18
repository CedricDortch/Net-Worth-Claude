---
paths:
  - "**/*.py"
---

# Python Style

- Python 3.11+. Use type hints everywhere, including return types. Use `X | None`, not `Optional[X]`.
- Use `@dataclass` for data containers; prefer `frozen=True` for analysis results.
- Money is `float` dollars internally; round only when displaying. Format display values with one helper (`format_money`) so output is consistent (`$30,000`, `-$22,000`, `$1.2M`).
- Percentages are stored as percent numbers (`7.0` means 7%), matching CLI flags. Convert to fractions inside the math only.
- No magic numbers in analysis code: defaults go in `Assumptions`, thresholds (e.g. high-interest ≥ 8%) go in a `constants.py`, benchmark data goes in `data/*.json`.
- Small, pure functions. Analysis functions take inputs and return results; no globals, no I/O.
- Use `pathlib.Path`, not string paths.
- Use the `logging` module, not `print`, outside `networth/cli.py`. Never log input content.
- Keep dependencies to those in `requirements.txt`; ask before adding a new one.
- Docstrings: one line for simple functions; explain the formula for any financial calculation.
