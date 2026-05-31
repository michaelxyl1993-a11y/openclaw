"""CSV loader for Product Intel candidate products."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .input_adapter import normalize_product_rows


def load_raw_csv_rows(path: str | Path) -> list[dict[str, Any]]:
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def load_products_from_csv(path: str | Path, source: str = "auto") -> list[dict[str, Any]]:
    return normalize_product_rows(load_raw_csv_rows(path), source=source)
