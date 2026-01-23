from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATE_PATH = Path(__file__).resolve().parent / "cleanup_state.json"


def load_last_cleanup() -> Optional[datetime]:
    if not STATE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        raw = data.get("calendar_last_cleanup")
        if not raw:
            return None
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def save_last_cleanup(dt: datetime) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"calendar_last_cleanup": dt.isoformat()}
    STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
