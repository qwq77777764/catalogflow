"""Local-only JSON preview output."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import ImportReport


def write_preview(report: ImportReport, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination

