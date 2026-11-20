"""R-20: tracker ID. Prefix JU, 8 characters from an alphabet without look-alikes (no 0, O, 1, I, L), then 1 check
character: JU-7K4Q2M9X-R. Never reused, carries no personal information."""
import secrets
from app.models.entities import Case

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 31 characters

def check_char(body: str) -> str:
    total = sum((i + 1) * ALPHABET.index(c) for i, c in enumerate(body))
    return ALPHABET[total % len(ALPHABET)]

def is_valid(tracker_id: str) -> bool:
    try:
        prefix, body, check = tracker_id.split("-")
    except ValueError:
        return False
    return prefix == "JU" and len(body) == 8 and len(check) == 1 and all(c in ALPHABET for c in body + check) and check_char(body) == check

def new_tracker_id(db) -> str:
    while True:
        body = "".join(secrets.choice(ALPHABET) for _ in range(8))
        tid = f"JU-{body}-{check_char(body)}"
        if not db.query(Case.id).filter(Case.tracker_id == tid).first():
            return tid
