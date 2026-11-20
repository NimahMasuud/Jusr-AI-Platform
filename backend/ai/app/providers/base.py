from dataclasses import dataclass, field
from typing import Any
from ..models import HelperType, Source


class ProviderError(Exception):
    """A provider could not do its job (network, timeout, unusable output)."""


@dataclass
class ProviderResult:
    status: str  # suggested | no_suggestion
    message: str  # plain language, shown on screen
    content: dict[str, Any] = field(default_factory=dict)
    sources: list[Source] = field(default_factory=list)
    completeness: str = "partial"
    notices: list[str] = field(default_factory=list)
    provider: str = ""


HELPER_METHODS = {
    HelperType.document_read: "document_read",
    HelperType.message_draft: "message_draft",
    HelperType.urgency: "urgency",
    HelperType.summary: "summary",
    HelperType.referral_target: "referral_target",
}
