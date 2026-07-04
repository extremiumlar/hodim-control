import html

from aiogram import F, Router
from aiogram.types import Message

from bot import api_client
from bot.config import FRONTEND_URL
from bot.keyboards import BTN_KPI, BTN_NORM, BTN_PANEL, BTN_TASKS

router = Router(name="menu")

STATUS_EMOJI = {"pending": "🕓", "done": "✅", "overdue": "⏰", "cancelled": "🚫"}


@router.message(F.text == BTN_TASKS)
async def show_tasks(message: Message) -> None:
    tasks = await api_client.list_my_tasks(message.from_user.id)
    if not tasks:
        await message.answer("Hozircha sizga biriktirilgan vazifa yo'q.")
        return

    lines = []
    for task in tasks:
        emoji = STATUS_EMOJI.get(task["status"], "•")
        deadline = f" (muddat: {task['deadline'][:16].replace('T', ' ')})" if task.get("deadline") else ""
        lines.append(f"{emoji} {html.escape(task['title'])}{deadline}")
    await message.answer("<b>Vazifalaringiz:</b>\n" + "\n".join(lines))


@router.message(F.text == BTN_NORM)
async def show_norm(message: Message) -> None:
    today = await api_client.today_daily_result(message.from_user.id)

    suhbat_norm = today["suhbat_norm"]
    tashrif_norm = today["tashrif_norm"]

    if suhbat_norm is None and tashrif_norm is None:
        await message.answer("Sizga hali norma belgilanmagan — ROP bilan bog'laning.")
        return

    lines = ["<b>Bugungi normang:</b>"]
    if suhbat_norm is not None:
        lines.append(f"Suhbatlar: {today['conversations_count']}/{suhbat_norm}")
    if tashrif_norm is not None:
        lines.append(f"Tashriflar: {today['visits_count']}/{tashrif_norm}")
    await message.answer("\n".join(lines))


@router.message(F.text == BTN_KPI)
async def show_kpi(message: Message) -> None:
    bonus = await api_client.my_latest_bonus(message.from_user.id)

    if not bonus["calculated"]:
        await message.answer(
            "Joriy oy uchun KPI/bonus hali hisoblanmagan — oy oxirida avtomatik hisoblanadi."
        )
        return

    await message.answer(
        f"💰 So'nggi hisoblangan davr: <b>{bonus['period']}</b>.\n"
        "Bonus tafsiloti uchun saytga kiring (Panelim tugmasi)."
    )


@router.message(F.text == BTN_PANEL)
async def show_panel(message: Message) -> None:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user["role"] not in {"hr", "rop", "boss", "dasturchi"}:
        return
    await message.answer(f"Boshqaruv paneli: {FRONTEND_URL}")
