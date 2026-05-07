from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_cohort_issues import router as cohort_issues_router
from app.api.routes_imports import router as imports_router
from app.api.routes_rosters import router as rosters_router
from app.api.routes_submissions import router as submissions_router
from app.core.config import settings
from app.services.email_poller import EmailDemoPoller

app = FastAPI(title=settings.app_name)
email_demo_poller = EmailDemoPoller()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(cohort_issues_router, prefix="/api")
app.include_router(imports_router, prefix="/api")
app.include_router(rosters_router, prefix="/api")
app.include_router(submissions_router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def startup() -> None:
    if settings.email_poll_enabled:
        email_demo_poller.start()


@app.on_event("shutdown")
def shutdown() -> None:
    email_demo_poller.stop()
