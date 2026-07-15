from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import (
    ai_coach,
    ai_watch,
    attendance,
    audit_logs,
    auth,
    auto_plan,
    bonuses,
    daily_results,
    excused_days,
    hot_lead,
    hourly_plan,
    mobilograf,
    norms,
    positions,
    reports,
    stats,
    tasks,
    users,
    work_schedule,
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
app.include_router(attendance.router)
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
app.include_router(work_schedule.router)
app.include_router(hourly_plan.router)
app.include_router(auto_plan.router)
app.include_router(ai_coach.router)
app.include_router(ai_watch.router)
app.include_router(hot_lead.router)


@app.get("/")
async def root() -> dict:
    """Brauzerda localhost:8000 ochilganda 404 o'rniga tushunarli holat —
    aks holda backend "ishlamayapti" degan taassurot qoldiradi."""
    return {
        "status": "ok",
        "service": "Xodimlar KPI/Bonus tizimi API",
        "docs": "/docs",
        "eslatma": "Bu backend (API). Sayt: https://localhost:5173",
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
