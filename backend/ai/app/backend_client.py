"""Talks to the Jusr AI backend as the AI_SERVICE user.

The backend decides what happens next. This client can only SUBMIT suggestions
(POST /api/v1/ai/suggestions). It has no call that changes a status, owner, urgency or closure (R-08, R-15).
Plain urllib, so it adds no dependency.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class BackendError(Exception):
    def __init__(self, status: int, message: str, code: Optional[str] = None):
        self.status, self.message, self.code = status, message, code
        super().__init__(message)


class BackendClient:
    def __init__(self, base_url: str, email: str, password: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.email, self.password, self.timeout = email, password, timeout
        self._token: Optional[str] = None

    # ---- low level ----
    def _call(self, method: str, path: str, body: Optional[bytes] = None, content_type: Optional[str] = None,
              auth: bool = True) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if auth:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(self.base_url + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "ignore")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            detail = data.get("detail") if isinstance(data.get("detail"), dict) else {}
            err = data.get("error") or detail or {}
            message = err.get("message") if isinstance(err, dict) else None
            if not message and isinstance(data.get("detail"), str):
                message = data["detail"]
            raise BackendError(exc.code, message or f"The backend refused the request ({exc.code}).",
                               err.get("code") if isinstance(err, dict) else None) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendError(0, "The backend could not be reached.") from exc

    def login(self) -> None:
        form = urllib.parse.urlencode({"username": self.email, "password": self.password}).encode()
        data = self._call("POST", "/api/v1/auth/login", form, "application/x-www-form-urlencoded", auth=False)
        self._token = data["data"]["accessToken"]

    # ---- the one thing this service may do ----
    def submit_suggestion(self, kind: str, payload: dict, case_id: Optional[str] = None,
                          model: Optional[str] = None, confidence: Optional[float] = None) -> dict[str, Any]:
        body = {"kind": kind, "payload": payload}
        if case_id:
            body["caseId"] = case_id
        if model:
            body["model"] = model[:80]
        if confidence is not None:
            body["confidence"] = confidence
        raw = json.dumps(body).encode()
        if self._token is None:
            self.login()
        try:
            data = self._call("POST", "/api/v1/ai/suggestions", raw, "application/json")
        except BackendError as exc:
            if exc.status != 401:
                raise
            self.login()  # token expired: sign in once more
            data = self._call("POST", "/api/v1/ai/suggestions", raw, "application/json")
        return data.get("data", data)

    # ---- read-only facility lookup, so referral suggestions use real IDs ----
    def list_facilities(self) -> list[dict[str, Any]]:
        if self._token is None:
            self.login()
        try:
            data = self._call("GET", "/api/v1/ai/suggestions/facilities")
        except BackendError as exc:
            if exc.status != 401:
                raise
            self.login()
            data = self._call("GET", "/api/v1/ai/suggestions/facilities")
        return data.get("data", data)
