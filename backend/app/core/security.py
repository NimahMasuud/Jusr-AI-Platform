from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_access_token(subject: str, role: str, expires_minutes: int | None = None):
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    return jwt.encode({"sub": subject, "role": role, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)

PATIENT_SCOPE = "patient-link"

def create_patient_session_token(link_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.patient_session_minutes)
    return jwt.encode({"sub": link_id, "scope": PATIENT_SCOPE, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)

def patient_session_link_id(token: str | None) -> str | None:
    """Link id from a valid patient session token, else None. Staff access tokens never carry this scope."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except Exception:
        return None
    return payload.get("sub") if payload.get("scope") == PATIENT_SCOPE else None
