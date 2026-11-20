from typing import Any, Optional


class ApiError(Exception):
    """One error shape for the whole service, with a plain-language reason."""

    def __init__(self, status_code: int, code: str, message: str, details: Optional[dict[str, Any]] = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def body(self) -> dict:
        return {"success": False, "error": {"code": self.code, "message": self.message, "details": self.details}}
