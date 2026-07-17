import httpx

from bot.config import API_BASE_URL, BOT_SHARED_SECRET

HEADERS = {"X-Bot-Secret": BOT_SHARED_SECRET}

_client: httpx.AsyncClient | None = None
_transport: httpx.BaseTransport | None = None
_base_url: str = API_BASE_URL


def use_in_process_transport(app) -> None:
    """cPanel webhook rejimida bot va FastAPI bitta jarayonda ishlaydi — bot API'ga
    haqiqiy tarmoq orqali (HTTPS) murojaat qilsa, so'rov Passenger'ning YAGONA
    ishchi jarayoniga qaytib keladi, u esa allaqachon shu webhook so'rovini
    band — natijada ReadTimeout (o'z-o'ziga tiqilib qolish). Shu funksiya
    ASGITransport bilan API'ga to'g'ridan-to'g'ri (tarmoqsiz) murojaat qilishga
    o'tkazadi. `api/routers/bot_webhook.py` birinchi so'rovda chaqiradi.
    Docker/polling rejimida (bot va API alohida jarayon/konteyner) chaqirilmaydi —
    o'sha yerda haqiqiy HTTP kerak."""
    global _transport, _base_url
    _transport = httpx.ASGITransport(app=app)
    _base_url = "http://in-process"


def _get_client() -> httpx.AsyncClient:
    """Bot butun umri davomida bitta umumiy httpx clientdan foydalanadi (har chaqiruvda
    yangi client/ulanish ochish o'rniga) — connection pooling imkonini beradi."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=_base_url, headers=HEADERS, timeout=10, transport=_transport
        )
    return _client


async def close_client() -> None:
    """Bot to'xtaganda (bot/main.py) chaqiriladi — ochiq ulanishlarni tozalab yopadi."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def telegram_start(telegram_id: int, invite_token: str | None) -> dict:
    resp = await _get_client().post(
        "/users/telegram-start",
        json={"telegram_id": telegram_id, "invite_token": invite_token},
    )
    resp.raise_for_status()
    return resp.json()


async def get_user_by_telegram(telegram_id: int) -> dict | None:
    resp = await _get_client().get(f"/users/by-telegram/{telegram_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def get_group_post_time(telegram_id: int) -> dict:
    resp = await _get_client().get(f"/stats/lead-stages/group-time/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def set_group_post_time(telegram_id: int, hour: int, minute: int) -> dict | None:
    """Guruhga yuborish vaqtini o'zgartirish (faqat Boshliq). Ruxsat yo'q — None."""
    resp = await _get_client().post(
        "/stats/lead-stages/group-time",
        params={"telegram_id": telegram_id, "hour": hour, "minute": minute},
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def list_my_tasks(telegram_id: int) -> list[dict]:
    resp = await _get_client().get(f"/tasks/my/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def complete_task(task_id: int, telegram_id: int) -> dict:
    resp = await _get_client().post(f"/tasks/{task_id}/complete", json={"telegram_id": telegram_id})
    resp.raise_for_status()
    return resp.json()


async def create_excused_day(telegram_id: int, reason: str) -> dict:
    """Sana yuborilmaydi — backend bugungi (Toshkent) sanani o'zi aniqlaydi,
    shunda bot serverining mahalliy vaqti kun chegarasiga ta'sir qilmaydi."""
    resp = await _get_client().post(
        "/excused-days",
        json={"telegram_id": telegram_id, "reason": reason},
    )
    resp.raise_for_status()
    return resp.json()


async def decide_excused_day(item_id: int, decider_telegram_id: int, decision: str) -> dict:
    resp = await _get_client().post(
        f"/excused-days/{item_id}/decide",
        json={"decider_telegram_id": decider_telegram_id, "decision": decision},
    )
    resp.raise_for_status()
    return resp.json()


async def norm_targets(telegram_id: int) -> list[dict]:
    """Aktyor norma belgilay oladigan xodimlar (matritsa: ROP — jamoasi, HR —
    o'ziga biriktirilgan lavozimlar, Boshliq/Dasturchi — hamma)."""
    resp = await _get_client().get(f"/norms/norm-targets/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def my_stats(telegram_id: int) -> dict:
    resp = await _get_client().get(f"/stats/my/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def update_norm(changer_telegram_id: int, target_user_id: int, metric_type: str, value: int) -> dict:
    resp = await _get_client().post(
        "/norms/bot-update",
        json={
            "changer_telegram_id": changer_telegram_id,
            "target_user_id": target_user_id,
            "metric_type": metric_type,
            "value": value,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def create_mobilograf_video(telegram_id: int, telegram_message_id: int, group_chat_id: int) -> dict:
    resp = await _get_client().post(
        "/mobilograf-videos",
        json={
            "telegram_id": telegram_id,
            "telegram_message_id": telegram_message_id,
            "group_chat_id": group_chat_id,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def react_mobilograf_video(
    group_chat_id: int, telegram_message_id: int, reactor_telegram_id: int, action: str
) -> dict | None:
    resp = await _get_client().post(
        "/mobilograf-videos/react",
        json={
            "group_chat_id": group_chat_id,
            "telegram_message_id": telegram_message_id,
            "reactor_telegram_id": reactor_telegram_id,
            "action": action,
        },
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def today_daily_result(telegram_id: int) -> dict:
    resp = await _get_client().get(f"/daily-results/today/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def my_latest_bonus(telegram_id: int) -> dict:
    resp = await _get_client().get(f"/bonuses/my/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def assignable_users(telegram_id: int) -> list[dict]:
    resp = await _get_client().get(f"/tasks/assignable-users/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def bot_create_task(assigner_telegram_id: int, assigned_to: int, title: str) -> dict:
    resp = await _get_client().post(
        "/tasks/bot-create",
        json={
            "assigner_telegram_id": assigner_telegram_id,
            "assigned_to": assigned_to,
            "title": title,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def bot_create_bulk_tasks(
    assigner_telegram_id: int,
    target_type: str,
    title: str,
    target_roles: list[str] | None = None,
    position_id: int | None = None,
) -> dict:
    """Ommaviy vazifa (faqat Boshliq/Dasturchi): barcha xodimlarga, rol bo'yicha
    (ROP/HR/ikkalasi) yoki lavozim bo'yicha."""
    resp = await _get_client().post(
        "/tasks/bot-bulk-create",
        json={
            "assigner_telegram_id": assigner_telegram_id,
            "target_type": target_type,
            "target_roles": target_roles,
            "position_id": position_id,
            "title": title,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def list_positions() -> list[dict]:
    """Faol lavozimlar — ommaviy vazifa oqimidagi "Lavozim: X" tugmalari uchun."""
    resp = await _get_client().get("/positions/for-bot")
    resp.raise_for_status()
    return resp.json()


async def download_report(telegram_id: int, period: str) -> tuple[bytes, str] | None:
    """Excel hisobotni yuklab oladi. period: today | week | month.
    Qaytaradi: (fayl_bayti, fayl_nomi) yoki ruxsat bo'lmasa None."""
    resp = await _get_client().get(f"/reports/export-bot/{telegram_id}", params={"period": period})
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    disposition = resp.headers.get("content-disposition", "")
    filename = disposition.split('filename="')[-1].rstrip('"') if 'filename="' in disposition else "hisobot.xlsx"
    return resp.content, filename


async def audit_logs(telegram_id: int, limit: int = 15) -> list[dict] | None:
    """Oxirgi audit yozuvlari (faqat Boshliq/Dasturchi); ruxsat bo'lmasa None."""
    resp = await _get_client().get(f"/audit-logs/for-bot/{telegram_id}", params={"limit": limit})
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def tasks_overview(telegram_id: int) -> list[dict]:
    """Bugungi barcha vazifalar (rahbar qamrovida) — kim bajardi/bajarmadi."""
    resp = await _get_client().get(f"/tasks/overview/{telegram_id}")
    resp.raise_for_status()
    return resp.json()


async def trigger_bonus_calculation(period: str | None = None) -> dict:
    """Joriy oy (yoki berilgan davr) uchun barcha xodimlar bonusini qayta hisoblaydi."""
    resp = await _get_client().post("/bonuses/calculate-monthly", json={"period": period})
    resp.raise_for_status()
    return resp.json()


async def trigger_daily_digest(chat_id: int | None = None) -> dict:
    """Kunlik yagona digest (vazifa + qo'ng'iroq/lid/tashrif + AI xulosa — bitta xabar).
    `chat_id` berilmasa sozlangan umumiy guruhga yuboriladi. Digest AI xulosani ham
    kutishi mumkinligi uchun timeout kengaytirilgan."""
    resp = await _get_client().post(
        "/reports/daily-digest", json={"chat_id": chat_id}, timeout=90
    )
    resp.raise_for_status()
    return resp.json()


async def trigger_monthly_digest(chat_id: int | None = None) -> dict:
    """Oylik yakun digesti (joriy oy vs o'tgan oy, bonus bilan). `chat_id` berilsa
    o'sha chatga, berilmasa sozlangan guruh(lar)ga yuboriladi."""
    resp = await _get_client().post(
        "/reports/monthly-digest", json={"chat_id": chat_id}, timeout=90
    )
    resp.raise_for_status()
    return resp.json()


async def lead_stage_month(telegram_id: int, month: str | None = None) -> dict | None:
    """Oylik lidlar statistikasi (CRM bosqichlari kesimida). Ma'lumot bazadagi fon
    snapshotdan tez o'qiladi. Ruxsat bo'lmasa None."""
    resp = await _get_client().get(
        f"/stats/lead-stages/{telegram_id}",
        params={"month": month} if month else None,
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def lead_stage_day(telegram_id: int, day: str, responsible_id: int | None = None) -> dict | None:
    """Bir kunning bosqich-kesimidagi lid statistikasi (day — ISO sana). `responsible_id`
    berilsa — faqat o'sha operator; berilmasa — tashkilot jami + operatorlar ro'yxati.
    Ruxsat bo'lmasa None (faqat rahbarlar)."""
    resp = await _get_client().get(
        f"/stats/lead-stages/{telegram_id}/day/{day}",
        params={"responsible_id": responsible_id} if responsible_id is not None else None,
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def my_lead_stage_month(telegram_id: int, month: str | None = None) -> dict | None:
    """Xodimning O'Z oylik lid/qo'ng'iroq statistikasi. 403 (ruxsat yo'q) yoki
    400 (CRM ID sozlanmagan) bo'lsa — mos xabar bilan (None, sabab)."""
    resp = await _get_client().get(
        f"/stats/lead-stages/{telegram_id}/me",
        params={"month": month} if month else None,
    )
    if resp.status_code in (400, 403):
        return None
    resp.raise_for_status()
    return resp.json()


async def my_lead_stage_day(telegram_id: int, day: str) -> dict | None:
    """Xodimning O'Z kunlik statistikasi (gaplashilgan + lid bosqichlari)."""
    resp = await _get_client().get(f"/stats/lead-stages/{telegram_id}/me/day/{day}")
    if resp.status_code in (400, 403):
        return None
    resp.raise_for_status()
    return resp.json()


async def my_hourly_plan(telegram_id: int) -> dict | None:
    """Xodimning bugungi soatma-soat rejasi + progressi (hozirgi holatga qarab)."""
    resp = await _get_client().get(f"/hourly-plan/{telegram_id}/me")
    if resp.status_code in (400, 403, 404):
        return None
    resp.raise_for_status()
    return resp.json()


async def employee_hourly_plan(telegram_id: int, user_id: int) -> dict | None:
    """Rahbar uchun: bitta xodimning bugungi soatma-soat rejasi (norma boshqarish
    doirasi bilan bir xil)."""
    resp = await _get_client().get(f"/hourly-plan/{telegram_id}/employee/{user_id}")
    if resp.status_code in (400, 403, 404):
        return None
    resp.raise_for_status()
    return resp.json()


async def my_work_week(telegram_id: int, start: str | None = None) -> dict | None:
    """Xodimning O'Z haftalik ish jadvali (start — hafta ichidagi istalgan sana)."""
    resp = await _get_client().get(
        f"/work-schedule/{telegram_id}/me/week", params={"start": start} if start else None
    )
    if resp.status_code in (400, 403, 404):
        return None
    resp.raise_for_status()
    return resp.json()


async def all_work_week(telegram_id: int, start: str | None = None) -> list[dict] | None:
    """Rahbar uchun: barcha faol xodimlarning haftalik ish jadvali."""
    resp = await _get_client().get(
        f"/work-schedule/{telegram_id}/all/week", params={"start": start} if start else None
    )
    if resp.status_code in (400, 403, 404):
        return None
    resp.raise_for_status()
    return resp.json()


async def post_shortfall_reason(telegram_id: int, day: str, hour: int, code: str) -> dict:
    """Operator AI sabab tugmasi javobini API'ga yozadi; {"label": ...} qaytaradi.
    (Eski tugmali xabarlar uchun orqaga moslik — yangi oqim erkin matn.)"""
    resp = await _get_client().post(
        "/ai-watch/reason",
        json={"telegram_id": telegram_id, "date": day, "hour": hour, "code": code},
    )
    resp.raise_for_status()
    return resp.json()


async def post_reason_verify(telegram_id: int, reason_id: int, approve: bool) -> dict | None:
    """Rahbar (ROP/Boshliq) operator sababini tasdiqlaydi/rad etadi. Ruxsat yo'q — None.
    Qaytaradi: {"already": bool, "verified": bool, "label": ...}."""
    resp = await _get_client().post(
        "/ai-watch/reason-verify",
        json={"telegram_id": telegram_id, "reason_id": reason_id, "approve": approve},
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def post_shortfall_reason_text(telegram_id: int, text: str) -> dict:
    """Operator yozgan erkin matnli sababni API'ga yuboradi. API'da AI tasnif +
    CRM/fakt tekshiruvi ketma-ket ishlaydi — jonli o'lchov: Gemini rate-limit
    retry'lari + to'liq CRM skan bilan ~75s ko'rilgan, shuning uchun timeout bu
    chaqiruvga alohida keng (180s). Qaytaradi:
    {"handled": bool, "reply": str, ...} — handled=false bo'lsa bot jim qoladi."""
    resp = await _get_client().post(
        "/ai-watch/reason-text",
        json={"telegram_id": telegram_id, "text": text},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


async def get_ai_config(telegram_id: int) -> dict | None:
    """Operator AI sozlamalari (rahbar uchun). Ruxsat yo'q — None."""
    resp = await _get_client().get(f"/ai-watch/config/{telegram_id}")
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def set_ai_config(telegram_id: int, **fields) -> dict | None:
    """AI sozlamasini o'zgartirish (faqat boss/dasturchi). Ruxsat yo'q — None."""
    resp = await _get_client().post(f"/ai-watch/config/{telegram_id}", json=fields)
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def anketa_overview(telegram_id: int) -> dict | None:
    """Anketa holati (taqsimot + sessiya). Faqat Dasturchi — ruxsat yo'q bo'lsa None."""
    resp = await _get_client().get(f"/anketa/overview/{telegram_id}")
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def anketa_schedule(telegram_id: int, scheduled_at: str | None) -> dict:
    """Sessiya yaratish. scheduled_at — Toshkent vaqti "YYYY-MM-DDTHH:MM" yoki None
    (darhol boshlash). 400 xatolar (faol sessiya bor, xodim topilmadi...) chaqiruvchida
    HTTPStatusError sifatida ushlanadi — detail foydalanuvchiga ko'rsatiladi."""
    resp = await _get_client().post(
        "/anketa/schedule",
        json={"telegram_id": telegram_id, "scheduled_at": scheduled_at},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


async def anketa_cancel(telegram_id: int) -> dict:
    resp = await _get_client().post("/anketa/cancel", json={"telegram_id": telegram_id}, timeout=60)
    resp.raise_for_status()
    return resp.json()


async def anketa_answer(telegram_id: int, text: str) -> dict:
    """Xodim matnini anketa javobi sifatida sinab ko'radi.
    {"handled": false} — anketa kutilmayotgan edi (bot boshqa oqimlarga o'tkazadi)."""
    resp = await _get_client().post(
        "/anketa/answer", json={"telegram_id": telegram_id, "text": text}, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


async def anketa_results(telegram_id: int) -> dict | None:
    """Oxirgi sessiya javoblari (.txt fayl uchun). Ruxsat yo'q — None, sessiya yo'q — 404."""
    resp = await _get_client().get(f"/anketa/results/{telegram_id}", timeout=60)
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def knowledge_overview(telegram_id: int) -> dict | None:
    """Bilim bazasi holati. Faqat Boshliq/Dasturchi — ruxsat yo'q bo'lsa None."""
    resp = await _get_client().get(f"/knowledge/overview/{telegram_id}")
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def knowledge_ingest(telegram_id: int) -> dict:
    """Anketa javoblaridan draft'lar yaratadi (tez, AI'siz — AI ishlovi cron'da).
    400 — yangi ma'lumot yo'q (chaqiruvchi detail'ni ko'rsatadi)."""
    resp = await _get_client().post(
        "/knowledge/ingest", json={"telegram_id": telegram_id}, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


async def knowledge_review_next(telegram_id: int, after_id: int = 0) -> dict | None:
    resp = await _get_client().get(
        f"/knowledge/review-next/{telegram_id}", params={"after_id": after_id}
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def knowledge_decide(
    telegram_id: int, entry_id: int, action: str, answer: str | None = None
) -> dict:
    resp = await _get_client().post(
        "/knowledge/decide",
        json={"telegram_id": telegram_id, "entry_id": entry_id, "action": action, "answer": answer},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def knowledge_add(
    telegram_id: int, question: str, answer: str, category: str, date_sensitive: bool
) -> dict:
    resp = await _get_client().post(
        "/knowledge/add",
        json={
            "telegram_id": telegram_id,
            "question": question,
            "answer": answer,
            "category": category,
            "date_sensitive": date_sensitive,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def knowledge_export(telegram_id: int) -> dict | None:
    resp = await _get_client().get(f"/knowledge/export/{telegram_id}", timeout=60)
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def playbook_overview(telegram_id: int) -> dict | None:
    """Sotuv playbook holati. Faqat Boshliq/Dasturchi — ruxsat yo'q bo'lsa None."""
    resp = await _get_client().get(f"/playbook/overview/{telegram_id}")
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def playbook_build(telegram_id: int) -> dict:
    """Playbook qurishni boshlaydi (haqiqiy AI ishi cron tick'da boradi).
    400 — allaqachon qurilmoqda / anketa yo'q / AI o'chiq."""
    resp = await _get_client().post(
        "/playbook/build", json={"telegram_id": telegram_id}, timeout=60
    )
    resp.raise_for_status()
    return resp.json()


async def playbook_review_next(telegram_id: int, after_id: int = 0) -> dict | None:
    resp = await _get_client().get(
        f"/playbook/review-next/{telegram_id}", params={"after_id": after_id}
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def playbook_decide(telegram_id: int, entry_id: int, action: str) -> dict:
    resp = await _get_client().post(
        "/playbook/decide",
        json={"telegram_id": telegram_id, "entry_id": entry_id, "action": action},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


async def playbook_export(telegram_id: int) -> dict | None:
    resp = await _get_client().get(f"/playbook/export/{telegram_id}", timeout=60)
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()


async def claim_hot_lead(telegram_id: int, hot_lead_id: int) -> dict | None:
    """Operator issiq lidni qabul qildi (✅ tugmasi). Boshqa operatorga tayinlangan
    bo'lsa — None (bot ogohlantiradi)."""
    resp = await _get_client().post(
        "/hot-lead/claim",
        json={"telegram_id": telegram_id, "hot_lead_id": hot_lead_id},
    )
    if resp.status_code == 403:
        return None
    resp.raise_for_status()
    return resp.json()
