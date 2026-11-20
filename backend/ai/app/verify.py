"""Checks that stop the AI from inventing things.

Every extracted field must come with an exact quote that really appears in the document.
Every summary line must point at an event that really exists.
Anything that fails is dropped, and the drop is reported.
"""
import re
from typing import Iterable


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_in_text(quote: str, text: str) -> bool:
    return bool(quote) and _norm(quote) in _norm(text)


def event_ids_exist(ids: Iterable[str], valid_ids: set[str]) -> bool:
    ids = list(ids)
    return bool(ids) and all(i in valid_ids for i in ids)


def camelize(value):
    """snake_case keys to camelCase, deep, so every JSON key in the API looks the same."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            parts = str(k).split("_")
            out[parts[0] + "".join(w.capitalize() for w in parts[1:])] = camelize(v)
        return out
    if isinstance(value, list):
        return [camelize(v) for v in value]
    return value
