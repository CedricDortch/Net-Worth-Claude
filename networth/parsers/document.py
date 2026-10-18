"""Raw parser output. Parsers only fill these in; they never interpret the content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Line:
    """One line of free text and where it came from (e.g. "Line 4", "Page 1, Line 3")."""

    text: str
    location: str


@dataclass(frozen=True)
class Table:
    """A grid of cell text. `rows` keeps empty rows so row numbers match the source."""

    rows: tuple[tuple[str, ...], ...]
    location_prefix: str = ""  # e.g. "Sheet 'Assets', " or "Table 1, "

    def cell_location(self, row: int, col: int) -> str:
        """Location of a 0-based cell, spreadsheet style: "Cell B7"."""
        return f"{self.location_prefix}Cell {column_letter(col)}{row + 1}"


@dataclass(frozen=True)
class ParsedDocument:
    source: Path
    lines: tuple[Line, ...] = ()
    tables: tuple[Table, ...] = ()
    data: Any = None  # the decoded object for JSON input; lines hold its flattened text

    @property
    def is_empty(self) -> bool:
        has_lines = any(line.text.strip() for line in self.lines)
        has_cells = any(cell.strip() for t in self.tables for row in t.rows for cell in row)
        return not (has_lines or has_cells)


def column_letter(col: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
