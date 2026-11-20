"""Suggestion storage. In memory, optionally saved to a JSON file.

Replace with Emmanuel's database once the data model exists. Keep the same four methods.
"""
import json
import threading
from pathlib import Path
from typing import Optional
from .models import Suggestion


class SuggestionStore:
    def __init__(self, path: Optional[Path] = None):
        self._items: dict[str, Suggestion] = {}
        self._lock = threading.Lock()
        self._path = Path(path) if path else None
        if self._path and self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                for raw in json.load(f):
                    s = Suggestion(**raw)
                    self._items[s.id] = s

    def _save(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump([s.model_dump(mode="json") for s in self._items.values()], f, indent=2)

    def add(self, s: Suggestion) -> Suggestion:
        with self._lock:
            self._items[s.id] = s
            self._save()
            return s

    def get(self, suggestion_id: str) -> Optional[Suggestion]:
        return self._items.get(suggestion_id)

    def update(self, s: Suggestion) -> Suggestion:
        return self.add(s)

    def list(self, case_id: Optional[str] = None, status: Optional[str] = None,
             helper: Optional[str] = None) -> list[Suggestion]:
        out = list(self._items.values())
        if case_id:
            out = [s for s in out if s.case_id == case_id]
        if status:
            out = [s for s in out if s.status.value == status]
        if helper:
            out = [s for s in out if s.helper.value == helper]
        return sorted(out, key=lambda s: s.created_at)
