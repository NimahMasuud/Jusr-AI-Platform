"""R-01: every action is stamped with staff ID, role and time, and cannot be edited afterwards.

There is no update or delete method. Each entry carries a hash of the one before it, so any
change to an old entry breaks the chain and verify() returns False.
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(prev_hash: str, entry_without_hash: dict) -> str:
    payload = json.dumps(entry_without_hash, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Optional[Path] = None, clock: Callable[[], str] = utc_now):
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._path = Path(path) if path else None
        self._clock = clock
        if self._path and self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = [json.loads(line) for line in f if line.strip()]

    def append(self, event_type: str, actor_staff_id: str, actor_role: str,
               case_id: Optional[str], details: Optional[dict[str, Any]] = None) -> dict:
        with self._lock:
            prev_hash = self._entries[-1]["hash"] if self._entries else "GENESIS"
            entry = {
                "seq": len(self._entries) + 1,
                "timestamp": self._clock(),
                "event_type": event_type,
                "actor_staff_id": actor_staff_id,
                "actor_role": actor_role,
                "case_id": case_id,
                "details": details or {},
                "prev_hash": prev_hash,
            }
            entry["hash"] = _hash(prev_hash, entry)
            self._entries.append(entry)
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            return entry

    def list(self, case_id: Optional[str] = None) -> list[dict]:
        return [dict(e) for e in self._entries if case_id is None or e["case_id"] == case_id]

    def verify(self) -> bool:
        prev = "GENESIS"
        for e in self._entries:
            body = {k: v for k, v in e.items() if k != "hash"}
            if e["prev_hash"] != prev or _hash(prev, body) != e["hash"]:
                return False
            prev = e["hash"]
        return True
