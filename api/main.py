import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings


def _setup_file_logging() -> None:
    """Ilova loglarini FAYLGA yozadi (`logs/api.log`).

    NEGA KERAK (2026-08-11, jonli diagnostikadan): ilgari logging umuman
    sozlanmagan edi — ya'ni `logger.warning(...)` stderr'ga ketardi, cPanel
    Passenger ostida esa stderr HECH QAYERGA saqlanmaydi (`passenger.log`,
    `stderr` fayllari yo'q). Natijada webhook rad etilishi kabi MUHIM
    diagnostik xabarlar butunlay yo'qolardi va "so'rov kelmadimi yoki rad
    etildimi" degan savolga javob topib bo'lmasdi. Apache access log ham
    yordam bermaydi: u kechikib yoziladi (o'lchandi: 200 qaytargan so'rov
    1 daqiqadan keyin ham logda yo'q edi).

    Rotatsiya bilan (5 MB × 3) — jadval/disk shishmasin; loglar katalogi
    `logs/` allaqachon `rotate_logs.sh` qamrovida.
    """
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return  # ikki marta sozlamaymiz (Passenger fork qilsa ham)
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "api.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return  # yozib bo'lmasa (huquq yo'q) — ilova baribir ishlashi kerak
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, os.getenv("API_LOG_LEVEL", "INFO").upper(), logging.INFO))


_setup_file_logging()
from api.routers import (
    admin_override,
    ai_center,
    ai_coach,
    ai_watch,
    anketa,
    attendance,
    audit_logs,
    auth,
    auto_plan,
    bonuses,
    busy_period,
    system_health,
    daily_results,
    excused_days,
    hot_lead,
    hourly_plan,
    idle_watch,
    knowledge,
    lead_events,
    mobilograf,
    monitored_groups,
    norms,
    payroll,
    playbook,
    positions,
    push,
    reports,
    sales_ai,
    stats,
    tasks,
    users,
    uysot_webhook,
    work_schedule,
)

# Interaktiv hujjatlar (/docs, /redoc, /openapi.json) faqat DEBUG rejimida ochiq.
# Productionda ular autentifikatsiyasiz butun endpoint xaritasini — jumladan
# X-Bot-Secret bilan himoyalangan yo'llar va ularning parametrlarini — ko'rsatadi,
# ya'ni hujumchi uchun tayyor qo'llanma bo'lib xizmat qiladi.
app = FastAPI(
    title="Xodimlar KPI/Bonus tizimi API",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    openapi_url="/openapi.json" if settings.debug else None,
)

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
app.include_router(monitored_groups.router)
app.include_router(reports.router)
app.include_router(daily_results.router)
app.include_router(bonuses.router)
app.include_router(audit_logs.router)
app.include_router(positions.router)
app.include_router(stats.router)
app.include_router(work_schedule.router)
app.include_router(payroll.router)
app.include_router(admin_override.router)
app.include_router(hourly_plan.router)
app.include_router(auto_plan.router)
app.include_router(ai_coach.router)
app.include_router(ai_watch.router)
app.include_router(hot_lead.router)
app.include_router(lead_events.router)
app.include_router(busy_period.router)
app.include_router(idle_watch.router)
app.include_router(anketa.router)
app.include_router(ai_center.router)
app.include_router(knowledge.router)
app.include_router(knowledge.public_router)
app.include_router(playbook.router)
app.include_router(sales_ai.router)
app.include_router(push.router)
app.include_router(uysot_webhook.router)
app.include_router(system_health.router)

# cPanel deploy: bot shu API ichida webhook orqali ishlaydi. Faqat yoqilganda
# ulanadi — shunda bot/ paketi import qilinadi (Docker api image'da bot/ yo'q,
# shuning uchun bayroq o'chiq bo'lsa import umuman bo'lmaydi).
if settings.bot_webhook_enabled:
    from api.routers import bot_webhook

    app.include_router(bot_webhook.router)


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
    """Sog'lik tekshiruvi — autentifikatsiyasiz (tashqi kuzatuvchi uchun).

    `cron_age_seconds` — cron oxirgi marta TO'LIQ o'tganidan beri necha soniya
    (`scripts/cron_tick.py` har sikl oxirida `logs/cron_heartbeat` yozadi).
    NEGA MUHIM: tizim qo'riqchisi cron ICHIDA yashaydi, ya'ni cron o'lsa
    qo'riqchi ham o'ladi. Tashqi kuzatuvchi (GitHub Actions,
    `.github/workflows/watchdog.yml`) shu yoshni tekshiradi — server yoki cron
    butunlay o'lsa ham ogohlantirish keladi.

    Maxfiy ma'lumot qaytarmaydi (faqat holat va yosh), shuning uchun ochiq."""
    from datetime import datetime
    from pathlib import Path

    cron_age: int | None = None
    try:
        beat = Path(__file__).resolve().parent.parent / "logs" / "cron_heartbeat"
        if beat.exists():
            last = datetime.fromisoformat(beat.read_text(encoding="utf-8").strip())
            cron_age = int((datetime.now(last.tzinfo) - last).total_seconds())
    except (OSError, ValueError):
        cron_age = None  # heartbeat o'qilmadi — tashqi kuzatuvchi buni "noma'lum" deb ko'radi

    return {"status": "ok", "cron_age_seconds": cron_age}
