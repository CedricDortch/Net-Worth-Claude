"""Pick a parser by file extension and return raw content as a ParsedDocument."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from networth.constants import SUPPORTED_EXTENSIONS
from networth.errors import NetWorthError, UnreadableFileError, UnsupportedFileError
from networth.parsers.docx_parser import parse_docx
from networth.parsers.document import Line, ParsedDocument, Table
from networth.parsers.excel_parser import parse_csv, parse_xls, parse_xlsx
from networth.parsers.pdf_parser import parse_pdf
from networth.parsers.text_parser import parse_json, parse_text

__all__ = ["Line", "ParsedDocument", "Table", "parse_file"]

_PARSERS: dict[str, Callable[[Path], ParsedDocument]] = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".xlsx": parse_xlsx,
    ".xls": parse_xls,
    ".csv": parse_csv,
    ".txt": parse_text,
    ".md": parse_text,
    ".json": parse_json,
}
assert set(_PARSERS) == set(SUPPORTED_EXTENSIONS)


def parse_file(path: Path) -> ParsedDocument:
    """Read any supported file. Raises UnsupportedFileError or UnreadableFileError."""
    path = Path(path)
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise UnsupportedFileError(
            f"'{path.suffix or path.name}' files are not supported. "
            f"Use one of: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if not path.is_file():
        raise UnreadableFileError(f"File not found: {path}")

    try:
        doc = parser(path)
    except NetWorthError:
        raise
    except Exception as exc:  # library errors: corrupted, password-protected, etc.
        # Only the exception type is shown; library messages can quote file content.
        raise UnreadableFileError(
            f"Could not read {path.name} ({type(exc).__name__}). The file may be "
            "corrupted or password-protected. Save an unlocked copy and try again."
        ) from None

    if doc.is_empty:
        raise UnreadableFileError(f"{path.name} has no readable content.")
    return doc
