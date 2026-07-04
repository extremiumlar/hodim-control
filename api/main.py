from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import (
    audit_logs,
    auth,
    bonuses,
    daily_results,
    excused_days,
    mobilograf,
    norms,
    positions,
    reports,
    stats,
    tasks,
    users,
)

app = FastAPI(title="Xodimlar KPI/Bonus tizimi API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(excused_days.router)
app.include_router(norms.router)
app.include_router(mobilograf.router)
app.include_router(reports.router)
app.include_router(daily_results.router)
app.include_router(bonuses.router)
app.include_router(audit_logs.router)
app.include_router(positions.router)
app.include_router(stats.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
