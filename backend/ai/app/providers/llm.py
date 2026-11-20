"""Optional AI model providers. NOT TESTED AGAINST A REAL MODEL (the checks on their output are).

  - AnthropicProvider: Anthropic's API (needs a key).
  - OpenAICompatibleProvider: any server with an OpenAI-style /chat/completions endpoint, for example
    Ollama running Qwen 2.5 (free, open source, runs on your machine), LM Studio or vLLM.

Used only for: reading free-text documents, drafting/translating messages, summarising.
Urgency and referral targets always go to the rule provider.

Every output is checked before it is used:
  - document fields must carry an exact quote found in the document
  - summary lines must cite real event IDs
Anything that fails the check is dropped and reported.
"""
import json
import re
import urllib.error
import urllib.request
from typing import Optional
from ..models import (DocumentReadRequest, MessageDraftRequest, ReferralTargetRequest,
                      Source, SummaryRequest, UrgencyRequest)
from ..verify import event_ids_exist, quote_in_text
from .base import ProviderError, ProviderResult
from .rules import LABELS, REQUIRED_FIELDS, SIMULATED_NOTICE, RuleProvider


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError("The AI model returned something that could not be read.") from exc


class LLMProvider:
    """Shared logic. A subclass only supplies _ask(system, user) -> text."""
    name = "llm"
    label = "llm"

    def __init__(self, rules: RuleProvider, simulated: bool = True):
        self._rules = rules
        self._simulated = simulated

    def _ask(self, system: str, user: str) -> str:
        raise NotImplementedError

    def document_read(self, req: DocumentReadRequest) -> ProviderResult:
        system = ("You extract fields from a SIMULATED referral letter or lab report. Use only text that appears "
                  "in the document. Never guess. Return JSON only: "
                  '{"fields":[{"name":"...","value":"...","quote":"exact text copied from the document"}]}. '
                  f"Allowed names: {sorted(set(LABELS.values()))}. Leave out any field the document does not state.")
        data = _parse_json(self._ask(system, req.document_text))
        fields, sources, dropped = {}, [], 0
        for f in data.get("fields", []):
            name, value, quote = f.get("name"), f.get("value"), f.get("quote", "")
            if name in set(LABELS.values()) and value and quote_in_text(quote, req.document_text) \
                    and name not in fields:
                fields[name] = value
                sources.append(Source(kind="document", ref=req.document_id, quote=quote))
            else:
                dropped += 1
        if not fields:
            return ProviderResult("no_suggestion",
                                  "No case details could be confirmed in this document. Please enter them by hand.",
                                  provider=self.name)
        notices = [f"{dropped} item(s) were dropped because their quote was not found in the document."] if dropped else []
        missing = sorted(REQUIRED_FIELDS - set(fields))
        if missing:
            notices.append(f"Not found in the document: {', '.join(missing)}.")
        return ProviderResult("suggested", "Case details read from the document. Please check each one.",
                              {"fields": fields}, sources, "complete" if not missing else "partial",
                              notices, self.name)

    def message_draft(self, req: MessageDraftRequest) -> ProviderResult:
        system = ("Write a short message to a patient in plain, simple words. Do not diagnose, do not give "
                  "medical advice, and do not add any fact that is not in the input. Include the next step, the "
                  "contact, and a request to confirm receipt. "
                  f"Write in this language: {req.language}. Return JSON only: {{\"text\":\"...\"}}.")
        user = json.dumps(req.model_dump())
        text = _parse_json(self._ask(system, user)).get("text", "").strip()
        if not text:
            raise ProviderError("The AI model returned an empty message.")
        if self._simulated and SIMULATED_NOTICE not in text:
            text += f"\n\n{SIMULATED_NOTICE}"
        return ProviderResult("suggested", "A draft message is ready. A coordinator must approve it before it is sent.",
                              {"language": req.language, "text": text, "requested_language": req.language,
                               "needs_translation_review": req.language.lower() != "en"},
                              [Source(kind="input", ref="message_request")], "complete",
                              ["AI-written or translated text must be checked by a person before sending."],
                              self.name)

    def summary(self, req: SummaryRequest) -> ProviderResult:
        if not req.events:
            return self._rules.summary(req)
        system = ("Summarise a case timeline for the next clinician. Use only the events given. Return JSON only: "
                  '{"bullets":[{"text":"...","sources":["event ids"]}]}. Every bullet must cite at least one event id.')
        data = _parse_json(self._ask(system, json.dumps([e.model_dump() for e in req.events])))
        valid = {e.event_id for e in req.events}
        bullets = [b for b in data.get("bullets", []) if event_ids_exist(b.get("sources", []), valid)]
        dropped = len(data.get("bullets", [])) - len(bullets)
        if not bullets:
            raise ProviderError("The summary had no lines that cite real events.")
        cited = sorted({i for b in bullets for i in b["sources"]})
        notices = [f"{dropped} summary line(s) were dropped because they cited no real event."] if dropped else []
        return ProviderResult("suggested", "A case summary is ready. Each line links to its source event.",
                              {"bullets": bullets}, [Source(kind="event", ref=i) for i in cited],
                              "complete", notices, self.name)

    # Clinician-written rules decide these. No model involved.
    def urgency(self, req: UrgencyRequest) -> ProviderResult:
        return self._rules.urgency(req)

    def referral_target(self, req: ReferralTargetRequest) -> ProviderResult:
        return self._rules.referral_target(req)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: float, rules: RuleProvider, simulated: bool = True):
        super().__init__(rules, simulated)
        try:
            import anthropic  # installed only if you use this provider
        except ImportError as exc:
            raise ProviderError("The 'anthropic' package is not installed.") from exc
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._model = model
        self.label = f"anthropic:{model}"

    def _ask(self, system: str, user: str) -> str:
        try:
            resp = self._client.messages.create(model=self._model, max_tokens=1200, system=system,
                                                messages=[{"role": "user", "content": user}])
        except Exception as exc:  # network, timeout, auth, rate limit
            raise ProviderError(f"The AI model could not be reached: {type(exc).__name__}") from exc
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class OpenAICompatibleProvider(LLMProvider):
    """For Ollama (Qwen 2.5 and others), LM Studio, vLLM. Plain urllib, no extra package."""
    name = "openai_compatible"

    def __init__(self, base_url: str, model: str, api_key: Optional[str], timeout: float,
                 rules: RuleProvider, simulated: bool = True):
        super().__init__(rules, simulated)
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model, self._key, self._timeout = model, api_key, timeout
        self.label = f"openai_compatible:{model}"

    def _ask(self, system: str, user: str) -> str:
        body = json.dumps({"model": self._model, "temperature": 0, "stream": False,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        req = urllib.request.Request(self._url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"The AI model could not be reached or answered badly: {type(exc).__name__}") from exc
