"""One JSON line per ticket, one file per run. No ticket text and no payment details."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.config import ROOT
from agent.redact import assert_clean, mask


class Logbook:
    def __init__(self, prefix: str = "run", folder: Path = ROOT / "logs") -> None:
        self.run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{prefix}-{self.run_id}.jsonl"

    def write(self, record: dict) -> None:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = json.dumps({"ts": stamp, "run_id": self.run_id, **record}, ensure_ascii=False)
        line = mask(line)[0]  # every value goes through the mask before it is written
        assert_clean(line)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
