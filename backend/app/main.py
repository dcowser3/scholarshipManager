from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_cohort_issues import router as cohort_issues_router
from app.api.routes_imports import router as imports_router
from app.api.routes_rosters import router as rosters_router
from app.api.routes_submissions import router as submissions_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

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
