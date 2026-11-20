"""PLACEHOLDER demo login.

Emmanuel decides the real token (staff ID, role, specialty, facility, authorised-to-close).
Until then the caller sends these headers. When the real token exists, change only this file.
"""
from typing import Optional
from fastapi import Header
from .errors import ApiError
from .models import Actor, Role


def get_actor(
    x_staff_id: Optional[str] = Header(default=None),
    x_role: Optional[str] = Header(default=None),
    x_specialty: Optional[str] = Header(default=None),
    x_facility: Optional[str] = Header(default=None),
) -> Actor:
    if not x_staff_id or not x_role:
        raise ApiError(401, "NOT_SIGNED_IN", "You are not signed in. Please sign in and try again.")
    try:
        role = Role(x_role)
    except ValueError:
        raise ApiError(401, "UNKNOWN_ROLE", "Your role is not recognised. Please sign in again.")
    return Actor(staff_id=x_staff_id, role=role, specialty=x_specialty, facility=x_facility)
