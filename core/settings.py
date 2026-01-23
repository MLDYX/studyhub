from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "settings.json"


class SettingsManager:
    def __init__(self, path: Path = DEFAULT_SETTINGS_PATH) -> None:
        self.path = path
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2, ensure_ascii=False)

    def get_mail_provider(self) -> str:
        mail_settings = self._data.get("mail", {})
        value = mail_settings.get("default_provider", "")
        return str(value) if value else ""

    def set_mail_provider(self, provider_id: str) -> None:
        if provider_id:
            mail_settings = self._data.setdefault("mail", {})
            mail_settings["default_provider"] = provider_id
        else:
            self.clear_mail_provider()
            return
        self._save()

    def clear_mail_provider(self) -> None:
        mail_settings = self._data.get("mail")
        if not mail_settings:
            return
        if "default_provider" in mail_settings:
            del mail_settings["default_provider"]
            if not mail_settings:
                del self._data["mail"]
            self._save()

    # --- calendar -------------------------------------------------------
    def get_calendar_sources(self) -> List[Dict[str, str]]:
        calendar_settings = self._data.get("calendar", {})
        sources_raw = calendar_settings.get("sources", [])
        result: List[Dict[str, str]] = []
        if isinstance(sources_raw, list):
            for entry in sources_raw:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "") or "").strip()
                path = str(entry.get("path", "") or "").strip()
                if not path:
                    continue
                source_type = str(entry.get("type", "file") or "file").strip() or "file"
                result.append({"name": name, "path": path, "type": source_type})
        return result

    def set_calendar_sources(self, sources: List[Dict[str, str]]) -> None:
        cleaned: List[Dict[str, str]] = []
        for entry in sources:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "") or "").strip()
            path = str(entry.get("path", "") or "").strip()
            if not path:
                continue
            source_type = str(entry.get("type", "file") or "file").strip() or "file"
            cleaned.append({"name": name, "path": path, "type": source_type})
        calendar_settings = self._data.setdefault("calendar", {})
        if cleaned:
            calendar_settings["sources"] = cleaned
        else:
            calendar_settings.pop("sources", None)
        if not calendar_settings:
            self._data.pop("calendar", None)
        self._save()

    def add_calendar_source(self, name: str, path: str, *, source_type: str = "file") -> None:
        path = path.strip()
        if not path:
            return
        name = name.strip()
        source_type = source_type.strip() or "file"
        sources = self.get_calendar_sources()
        for entry in sources:
            if entry["path"] == path:
                entry["name"] = name
                entry["type"] = source_type
                self.set_calendar_sources(sources)
                return
        sources.append({"name": name, "path": path, "type": source_type})
        self.set_calendar_sources(sources)

    def remove_calendar_source(self, path: str) -> None:
        target = path.strip()
        if not target:
            return
        sources = [entry for entry in self.get_calendar_sources() if entry["path"] != target]
        self.set_calendar_sources(sources)

    def as_dict(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._data))
