"""Markdown table generators for reports."""

from __future__ import annotations

from typing import Sequence


def markdown_table(rows: Sequence[dict[str, object]], columns: Sequence[str]) -> str:
    """Render a list of dicts as a Markdown table."""
    if not rows:
        return ""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"

    def fmt(value: object) -> str:
        if value is None:
            return ""
        return str(value)

    lines = [header, sep]
    for row in rows:
        lines.append("| " + " | ".join(fmt(row.get(c, "")) for c in columns) + " |")
    return "\n".join(lines)
