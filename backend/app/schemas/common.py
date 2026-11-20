from pydantic import BaseModel, ConfigDict
from typing import Any

class Meta(BaseModel):
    requestId: str | None = None

class SuccessEnvelope(BaseModel):
    success: bool = True
    data: Any
    meta: Meta = Meta()

class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}

class ErrorEnvelope(BaseModel):
    success: bool = False
    error: ErrorBody
    meta: Meta = Meta()

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
