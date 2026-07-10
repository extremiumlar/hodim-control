import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import (
    BTN_AUDIT,
    BTN_CALC_KPI,
    BTN_GLOBAL_STATS,
    BTN_MY_STATS,
    BTN_REPORT,
    BTN_TASK_CONTROL,
    MANAGER_ROLES,
)

# Ko'rsatish uchun — hisoblash backendda (today_local) qilinadi, bu faqat format
TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

REPORT_PERIODS = {"today": "Bugun", "week": "Shu hafta", "month": "Shu oy"}

# Audit jurnalidagi eng ko'p uchraydigan amallar uchun o'zbekcha yorliqlar;
# ro'yxatda yo'q amal xom ko'rinishida chiqadi.
AUDIT_ACTION_LABELS = {
    "task_created": "vazifa berdi",
    "task_bulk_created": "ommaviy vazifa berdi",
    "task_completed": "vazifani bajardi",
    "norm_changed": "norma o'zgartirdi",
    "daily_result_manual_set": "kunlik natija kiritdi",
    "daily_result_crm_webhook": "CRM natija yozdi",
    "mobilograf_confirmed": "video tasdiqladi",
    "mobilograf_unconfirmed": "video tasdig'ini bekor qildi",
    "mobilograf_manual_set": "video sonini qo'lda kiritdi",
    "excused_day_decided": "sababli kun qarorini berdi",
    "bonus_calculated": "bonus hisoblandi",
    "user_created": "foydalanuvchi yaratdi",
    "user_deactivated": "foydalanuvchini o'chirdi",
    "user_activated": "foydalanuvchini tikladi",
    "user_deleted": "foydalanuvchini butunlay o'chirdi",
    "user_force_deleted": "foydalanuvchini majburiy o'chirdi",
    "user_role_changed": "rolni o'zgartirdi",
    "user_position_changed": "lavozimni o'zgartirdi",
    "user_account_reset": "akkauntni qayta bog'ladi",
    "telegram_account_transferred": "Telegram akkaunt ko'chirildi",
    "crm_external_id_changed": "CRM ID o'zgartirdi",
    "position_created": "lavozim yaratdi",
    "position_updated": "lavozimni o'zgartirdi",
}

router = Router(name="stats")

METRIC_MONTH_LABELS = {"suhbat": "Suhbatlar", "tashrif": "Tashriflar", "video": "Videolar"}


@router.message(F.text == BTN_MY_STATS)
async def show_my_stats(message: Message, state: FSMContext) -> None:
    """Har bir xodim o'z statistikasini oladi: bugungi holat, oylik jami,
    vazifalar bajarilishi va sababli kunlar."""
    # Asosiy menyu tugmasi har doim avvalgi FSM oqimini (masalan chala qolgan
    # norma o'zgartirish) tozalaydi — holat "osilib qolmasligi" uchun.
    await state.clear()
    stats = await api_client.my_stats(message.from_user.id)

    lines = [f"📈 <b>Statistikangiz</b> ({stats['period']})"]

    today_rows = stats.get("today") or []
    if today_rows:
        lines.append("")
        lines.append("<b>Bugun:</b>")
        for m in today_rows:
            norm_part = f"/{m['norm']}" if m.get("norm") is not None else ""
            lines.append(f"  {m['label']}: {m['value']}{norm_part}")

    week_totals = stats.get("week_totals") or {}
    if week_totals:
        lines.append("")
        lines.append("<b>Shu haftada jami:</b>")
        for key, total in week_totals.items():
            lines.append(f"  {METRIC_MONTH_LABELS.get(key, key)}: {total}")

    month_totals = stats.get("month_totals") or {}
    if month_totals:
        lines.append("")
        lines.append("<b>Shu oyda jami:</b>")
        for key, total in month_totals.items():
            lines.append(f"  {METRIC_MONTH_LABELS.get(key, key)}: {total}")

    lines.append("")
    lines.append(f"<b>Vazifalar (shu oy):</b> {stats['tasks_done']}/{stats['tasks_total']} bajarildi")
    if stats.get("excused_days"):
        lines.append(f"<b>Sababli kunlar:</b> {stats['excused_days']} kun")

    await message.answer("\n".join(lines))


@router.message(F.text == BTN_TASK_CONTROL)
async def show_task_control(message: Message, state: FSMContext) -> None:
    """Rahbarlar uchun: bugun berilgan vazifalar — kim bajardi, kim hali yo'q.
    ROP faqat o'z jamoasini ko'radi (qamrov backendda cheklanadi)."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    tasks = await api_client.tasks_overview(message.from_user.id)
    if not tasks:
        await message.answer("Bugun berilgan vazifalar yo'q.")
        return

    done = [t for t in tasks if t["status"] == "done"]
    pending = [t for t in tasks if t["status"] != "done"]

    def _lines(items: list[dict]) -> list[str]:
        return [f"  • {i['assigned_to_name']} — {html.escape(i['title'])}" for i in items[:30]]

    lines = [f"📋 <b>Bugungi vazifalar</b> ({len(done)}/{len(tasks)} bajarildi)"]
    if done:
        lines.append("")
        lines.append("✅ <b>Bajarilgan:</b>")
        lines.extend(_lines(done))
    if pending:
        lines.append("")
        lines.append("🕓 <b>Bajarilmagan:</b>")
        lines.extend(_lines(pending))
    await message.answer("\n".join(lines))


@router.message(F.text == BTN_CALC_KPI)
async def calc_monthly_kpi(message: Message, state: FSMContext) -> None:
    """Faqat Boshliq/Dasturchi: joriy oy KPI/bonusini barcha xodimlar uchun
    darhol qayta hisoblaydi (oy oxirini kutmasdan). Har bir xodimga bot orqali
    "bonus hisoblandi" xabari ketadi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"boss", "dasturchi"}:
        return

    result = await api_client.trigger_bonus_calculation()
    await message.answer(
        f"💰 KPI/bonus <b>{result['period']}</b> davri uchun {result['calculated']} xodimga "
        "qayta hisoblandi.\nTafsilotlar saytdagi xodim profillarida (Bonus tarixi)."
    )


@router.message(F.text == BTN_REPORT)
async def choose_report_period(message: Message, state: FSMContext) -> None:
    """Excel hisobot davri tanlovi — davr chegaralari backendda Toshkent
    sanasi bilan hisoblanadi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"report:{key}")]
        for key, label in REPORT_PERIODS.items()
    ]
    await message.answer(
        "Qaysi davr uchun hisobot?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("report:"))
async def send_report(callback: CallbackQuery) -> None:
    period = callback.data.split(":")[1]
    if period not in REPORT_PERIODS:
        await callback.answer("Noma'lum davr.", show_alert=True)
        return

    await callback.answer("Hisobot tayyorlanmoqda...")
    result = await api_client.download_report(callback.from_user.id, period)
    if result is None:
        await callback.message.answer("Bu amal uchun ruxsatingiz yo'q.")
        return

    content, filename = result
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=f"📥 Hisobot — {REPORT_PERIODS[period].lower()}",
    )


@router.message(F.text == BTN_AUDIT)
async def show_audit_logs(message: Message, state: FSMContext) -> None:
    """Oxirgi 15 ta audit yozuvi — faqat Boshliq/Dasturchi (to'liq jurnal saytda)."""
    await state.clear()
    logs = await api_client.audit_logs(message.from_user.id, limit=15)
    if logs is None:
        return
    if not logs:
        await message.answer("Audit jurnali hozircha bo'sh.")
        return

    lines = ["🧾 <b>Oxirgi amallar:</b>"]
    for log in logs:
        # created_at bazada naive-UTC — ko'rsatish uchun Toshkentga o'giramiz
        at = (
            datetime.fromisoformat(log["created_at"])
            .replace(tzinfo=timezone.utc)
            .astimezone(TASHKENT_TZ)
        )
        actor = log.get("actor_name") or "Tizim"
        action = AUDIT_ACTION_LABELS.get(log["action"], log["action"])
        target = f" → {log['target_name']}" if log.get("target_name") else ""
        lines.append(f"• {at:%d.%m %H:%M} — {html.escape(actor)} {action}{html.escape(target)}")
    lines.append("")
    lines.append("To'liq jurnal (filtrlar bilan): saytdagi \"Audit\" bo'limida.")
    await message.answer("\n".join(lines))


async def send_global_stats(message: Message, *, to_group: bool) -> None:
    """Kunlik yagona digestni (vazifa + qo'ng'iroq/lid/tashrif + AI xulosa — BITTA
    xabar) yuboradi — "📊 Umumiy statistika" tugmasi (shaxsiy chatga) va guruhdagi
    /statistika buyrug'i (sozlangan guruhga) uchun umumiy qism; farq faqat nishon
    chat va xato-xabar formatida."""
    chat_id = None if to_group else message.chat.id
    respond = message.reply if to_group else message.answer

    # Digest bir necha soniya olishi mumkin (CRM + AI xulosa) — foydalanuvchi
    # "jim qoldi, ishlamadi" deb o'ylamasligi uchun darhol "yozmoqda" belgisi.
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:  # noqa: BLE001 — chat action bezak, xatosi oqimni to'xtatmasin
        pass

    result = await api_client.trigger_daily_digest(chat_id=chat_id)
    if not result.get("sent"):
        reason = result.get("reason") or "ma'lumot topilmadi"
        await respond(
            f"Kunlik digestni yuborib bo'lmadi: {reason}"
            if to_group
            else f"Kunlik digestni tayyorlab bo'lmadi: {reason}"
        )


@router.message(F.text == BTN_GLOBAL_STATS)
async def show_global_stats(message: Message, state: FSMContext) -> None:
    """Umumiy statistika — faqat HR/ROP/Boshliq/Dasturchi. Kunlik xulosa va
    qo'ng'iroqlar statistikasi so'ralgan chatning o'ziga yuboriladi."""
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in MANAGER_ROLES:
        return

    await send_global_stats(message, to_group=False)
