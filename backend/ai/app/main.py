from typing import Optional
from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .audit import AuditLog
from .auth import get_actor
from .config import Settings, load_json
from .errors import ApiError
from .models import (Actor, DecisionRequest, DocumentReadRequest, HelperResponse, HelperType,
                     MessageDraftRequest, ReferralTargetRequest, Suggestion, SummaryRequest,
                     UrgencyRequest)
from .providers.base import ProviderError
from .providers.rules import RuleProvider
from .service import HelperService
from .store import SuggestionStore
from .backend_client import BackendClient
from .submit import SubmitResponse, SubmitService
from .verify import camelize


def build_provider(settings: Settings, rules: RuleProvider):
    """Rules unless a model is configured. If a model cannot be set up, fall back to rules."""
    from .providers import llm
    try:
        if settings.provider == "anthropic" and settings.anthropic_api_key:
            return llm.AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model,
                                         settings.llm_timeout_seconds, rules, settings.simulated_mode)
        if settings.provider == "openai_compatible":
            return llm.OpenAICompatibleProvider(settings.llm_base_url, settings.llm_model, settings.llm_api_key,
                                                settings.llm_timeout_seconds, rules, settings.simulated_mode)
    except ProviderError:
        pass
    return rules


def create_app(settings: Optional[Settings] = None, provider=None, backend_client=None) -> FastAPI:
    settings = settings or Settings.from_env()
    rules = RuleProvider(load_json(settings.config_dir, "urgency_criteria.json"),
                         load_json(settings.config_dir, "routing_table.json"), settings.simulated_mode)
    provider = provider or build_provider(settings, rules)
    d = settings.data_dir
    audit = AuditLog(d / "audit.jsonl" if d else None)
    store = SuggestionStore(d / "suggestions.json" if d else None)
    service = HelperService(provider, rules, store, audit,
                            load_json(settings.config_dir, "approver_roles.json"), settings.simulated_mode)

    if backend_client is None and settings.backend_url and settings.ai_service_email and settings.ai_service_password:
        backend_client = BackendClient(settings.backend_url, settings.ai_service_email, settings.ai_service_password)
    facility_ids = load_json(settings.config_dir, "facility_ids.json")
    submitter = SubmitService(service, backend_client, facility_ids, getattr(provider, "label", "rules"), rules, audit)

    app = FastAPI(title="Jusr AI: AI helper service", version="0.2.0")
    app.state.service, app.state.audit, app.state.store = service, audit, store
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=ApiError(
            422, "INVALID_REQUEST", "Some required information is missing or in the wrong form.",
            {"fields": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]}).body())

    @app.get("/health")
    def health():
        return {"status": "ok", "provider": getattr(provider, "name", "?"), "simulated": settings.simulated_mode,
                "backendConfigured": backend_client is not None}

    p = "/ai/v1"

    @app.post(f"{p}/suggestions/document-read", response_model=HelperResponse)
    def document_read(req: DocumentReadRequest, actor: Actor = Depends(get_actor)):
        return service.request(HelperType.document_read, req, actor)

    @app.post(f"{p}/suggestions/message-draft", response_model=HelperResponse)
    def message_draft(req: MessageDraftRequest, actor: Actor = Depends(get_actor)):
        return service.request(HelperType.message_draft, req, actor)

    @app.post(f"{p}/suggestions/urgency", response_model=HelperResponse)
    def urgency(req: UrgencyRequest, actor: Actor = Depends(get_actor)):
        return service.request(HelperType.urgency, req, actor)

    @app.post(f"{p}/suggestions/summary", response_model=HelperResponse)
    def summary(req: SummaryRequest, actor: Actor = Depends(get_actor)):
        return service.request(HelperType.summary, req, actor)

    @app.post(f"{p}/suggestions/referral-target", response_model=HelperResponse)
    def referral_target(req: ReferralTargetRequest, actor: Actor = Depends(get_actor)):
        return service.request(HelperType.referral_target, req, actor)

    # ---- backend mode: run the helper, then send the result to the backend as a PENDING suggestion ----
    @app.post(f"{p}/submit/intake", response_model=SubmitResponse)
    def submit_intake(req: DocumentReadRequest, actor: Actor = Depends(get_actor)):
        return submitter.submit(HelperType.document_read, req, actor)

    @app.post(f"{p}/submit/urgency", response_model=SubmitResponse)
    def submit_urgency(req: UrgencyRequest, actor: Actor = Depends(get_actor)):
        return submitter.submit(HelperType.urgency, req, actor)

    @app.post(f"{p}/submit/message-draft", response_model=SubmitResponse)
    def submit_message(req: MessageDraftRequest, actor: Actor = Depends(get_actor)):
        return submitter.submit(HelperType.message_draft, req, actor)

    @app.post(f"{p}/submit/summary", response_model=SubmitResponse)
    def submit_summary(req: SummaryRequest, actor: Actor = Depends(get_actor)):
        return submitter.submit(HelperType.summary, req, actor)

    @app.post(f"{p}/submit/referral-target", response_model=SubmitResponse)
    def submit_referral(req: ReferralTargetRequest, actor: Actor = Depends(get_actor)):
        return submitter.submit(HelperType.referral_target, req, actor)

    @app.get(f"{p}/suggestions", response_model=list[Suggestion])
    def list_suggestions(case_id: Optional[str] = Query(None, alias="caseId"), status: Optional[str] = None,
                         helper: Optional[str] = None, actor: Actor = Depends(get_actor)):
        return store.list(case_id, status, helper)

    @app.get(f"{p}/suggestions/{{suggestion_id}}", response_model=Suggestion)
    def get_suggestion(suggestion_id: str, actor: Actor = Depends(get_actor)):
        s = store.get(suggestion_id)
        if s is None:
            raise ApiError(404, "SUGGESTION_NOT_FOUND", "That suggestion could not be found.")
        return s

    @app.post(f"{p}/suggestions/{{suggestion_id}}/decision", response_model=Suggestion)
    def decide(suggestion_id: str, body: DecisionRequest, actor: Actor = Depends(get_actor)):
        return service.decide(suggestion_id, body.decision, body.edited_content, body.note, actor)

    @app.get(f"{p}/audit")
    def get_audit(case_id: Optional[str] = Query(None, alias="caseId"), actor: Actor = Depends(get_actor)):
        return {"entries": camelize(audit.list(case_id)), "chainValid": audit.verify()}

    return app


app = create_app()
