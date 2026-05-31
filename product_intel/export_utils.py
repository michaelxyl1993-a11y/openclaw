"""Export helpers for Product Intel outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_json(data: Any, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def save_jsonl(items: list[Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path
