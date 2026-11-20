from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.api.v1.deps import current_user
from app.models.entities import User

router = APIRouter()


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(user.id, user.role.value)

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "data": {
            "accessToken": token,
            "tokenType": "bearer"
        },
        "meta": {}
    }


@router.get("/me")
def me(user=Depends(current_user)):
    return {"success": True, "data": {"id": user.id, "email": user.email, "displayName": user.display_name, "role": user.role.value, "facilityId": user.facility_id, "specialty": user.specialty, "authorisedToClose": user.authorised_to_close}, "meta": {}}
