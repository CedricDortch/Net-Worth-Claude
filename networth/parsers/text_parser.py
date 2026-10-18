"""Plain text, Markdown, and JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from networth.parsers.document import Line, ParsedDocument


def read_text(path: Path) -> str:
    """Read text as UTF-8 (with or without BOM), falling back to Latin-1."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_text(path: Path) -> ParsedDocument:
    lines = tuple(
        Line(text, f"Line {i}")
        for i, text in enumerate(read_text(path).splitlines(), start=1)
    )
    return ParsedDocument(source=path, lines=lines)


def parse_json(path: Path) -> ParsedDocument:
    """Flatten JSON into "key: value" lines, located by their path (e.g. assets[0].label)."""
    data = json.loads(read_text(path))
    lines: list[Line] = []
    _flatten(data, "", lines)
    return ParsedDocument(source=path, lines=tuple(lines), data=data)


def _flatten(node: Any, path: str, out: list[Line]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, (dict, list)):
                out.append(Line(str(key), f"Field {child}"))
                _flatten(value, child, out)
            else:
                out.append(Line(f"{key}: {_scalar(value)}", f"Field {child}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _flatten(value, f"{path}[{i}]", out)
    else:
        out.append(Line(_scalar(node), f"Field {path or '(root)'}"))


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
