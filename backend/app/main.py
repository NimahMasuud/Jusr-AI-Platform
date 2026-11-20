import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.api.v1.endpoints import patient_portal
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.scheduler import run_forever

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(run_forever()) if settings.scheduler_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()

app = FastAPI(title="Jusr AI API", version="1.0.0", openapi_url="/api/v1/openapi.json", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(patient_portal.router, prefix="/p", tags=["Patient Secure Link"])
# The patient portal frontend calls /api/p/...; serve the same secure-link routes there.
app.include_router(patient_portal.router, prefix="/api/p", include_in_schema=False)
app.include_router(api_router, prefix="/api/v1")
# The frontend register uses unversioned /api/... paths; serve the same routes there.
app.include_router(api_router, prefix="/api", include_in_schema=False)

@app.get("/health")
def health():
    return {"status": "ok"}
