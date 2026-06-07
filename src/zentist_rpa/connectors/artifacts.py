from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any


class ArtifactConnector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(
        self, *, business_date: date, portal: str, item_key: str, suffix: str, content: str
    ) -> Path:
        path = self._path(business_date, portal, item_key, suffix)
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(
        self,
        *,
        business_date: date,
        portal: str,
        item_key: str,
        suffix: str,
        payload: dict[str, Any],
    ) -> Path:
        path = self._path(business_date, portal, item_key, suffix)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def _path(self, business_date: date, portal: str, item_key: str, suffix: str) -> Path:
        folder = self.root / business_date.isoformat() / self._safe(portal)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{self._safe(item_key)}_{self._safe(suffix)}"

    @staticmethod
    def _safe(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "item"
