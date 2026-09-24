"""The textbook claim for each detector pattern type, read from `docs/patterns-research.md`.

Part A's catalogue tables give the shape and trigger; Part C's confirmation matrix gives the
conventional confirmation claims ("hypotheses to test"). The encyclopedia shows these BESIDE the
measured numbers — convention on one side, what actually happened on the other.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "patterns-research.md"

# detector type -> (Part A row name, Part C section heading prefix)
_MAP = {
    "double top": ("Double top / bottom", "Double top / bottom"),
    "double bottom": ("Double top / bottom", "Double top / bottom"),
    "head and shoulders": ("Head & shoulders", "Head & shoulders"),
    "inverse head and shoulders": ("Inverse head & shoulders", "Head & shoulders"),
    "ascending triangle": ("Ascending triangle", "Ascending / descending / symmetrical triangles"),
    "descending triangle": ("Descending triangle", "Ascending / descending / symmetrical triangles"),
    "symmetric triangle": ("Symmetrical triangle", "Ascending / descending / symmetrical triangles"),
    "sideways channel": ("Rectangle (range)", "Rectangles / channels"),
    "ascending channel": ("Channel", "Rectangles / channels"),
    "descending channel": ("Channel", "Rectangles / channels"),
}


def _clean(md: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", md).replace("←", "—").strip()


def textbook_claim(pattern_type: str, doc: Path = DOC) -> dict | None:
    """{shape, trigger, claims: [..], source} for a detector type, or None if unknown / doc missing."""
    if pattern_type not in _MAP:
        return None
    try:
        text = doc.read_text(encoding="utf-8")
    except OSError:
        return None
    row_name, section = _MAP[pattern_type]
    shape = trigger = None
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and _clean(cells[0]).startswith(row_name):
            shape, trigger = _clean(cells[1]), _clean(cells[2])
            break
    claims: list[str] = []
    m = re.search(rf"^### {re.escape(section)}.*?$(.*?)(?=^### |^## |\Z)", text, re.M | re.S)
    if m:
        for line in m.group(1).splitlines():
            if line.startswith("- "):
                claims.append(_clean(line[2:]))
            elif line.startswith("  ") and claims:            # wrapped bullet continuation
                claims[-1] += " " + _clean(line)
    return {"shape": shape, "trigger": trigger, "claims": claims,
            "source": "docs/patterns-research.md (Parts A and C — convention, 'hypotheses to test')"}
