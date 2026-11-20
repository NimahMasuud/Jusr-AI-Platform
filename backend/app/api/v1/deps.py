from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User
from app.core.permissions import CLINICAL_ROLES, role_values
from app.models.entities import Role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or unknown user")
    return user

def require_roles(*roles):
    def checker(user=Depends(current_user)):
        if user.role.value not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

clinical_user = require_roles(*role_values(CLINICAL_ROLES))
# The general worklist and case list are not for receiving clinicians; they use /urgent-cases and /referrals.
worklist_user = require_roles(*role_values(CLINICAL_ROLES - {Role.RECEIVING_CLINICIAN}))
