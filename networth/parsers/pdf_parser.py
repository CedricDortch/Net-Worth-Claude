"""PDF: text lines per page. Scanned PDFs (no text layer) are rejected; no OCR in v1."""

from __future__ import annotations

from pathlib import Path

from networth.errors import UnreadableFileError
from networth.parsers.document import Line, ParsedDocument


def parse_pdf(path: Path) -> ParsedDocument:
    import pdfplumber

    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines.extend(
                Line(t, f"Page {page_no}, Line {i}")
                for i, t in enumerate(text.splitlines(), start=1)
            )

    if not any(line.text.strip() for line in lines):
        raise UnreadableFileError(
            f"{path.name} has no text layer (it looks like a scanned image). "
            "Provide a text-based PDF, a Word or Excel file, or a .txt file."
        )
    return ParsedDocument(source=path, lines=tuple(lines))
