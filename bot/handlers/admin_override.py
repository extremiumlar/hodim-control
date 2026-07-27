"""Dasturchi rejimi (super-admin) — bot buyruqlari. OYLIK_JARIMA_REJASI.md
11.5-band. Backend allaqachon Bosqich 3.5'da tayyor (`api/routers/
admin_override.py`, JWT-himoyalangan); bu yerda faqat yupqa qatlam —
buyruq argumentlarini o'qiydi, sababni FSM orqali so'raydi, so'ng
`bot_admin_token` bilan vaqtinchalik JWT olib mavjud endpointlarni chaqiradi.

Kengroq (web'dagi kabi to'liq: barcha 11 entity, payroll qulflari, tizim
darajasi) boshqaruv uchun sayt `/admin` sahifasi (faqat dasturchi) mavjud —
bot buyruqlari faqat eng tez-tez kerak bo'ladigan 5 tasini (11.5-band
ro'yxati) qamraydi, tez-tez terish uchun."""
import re

import httpx
from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import api_client

router = Router(name="admin_override")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


class OverrideFSM(StatesGroup):
    waiting_reason = State()


async def _require_dasturchi(message: Message) -> bool:
    user = await api_client.get_user_by_telegram(message.from_user.id)
    if not user or user.get("role") != "dasturchi":
        await message.answer("Bu buyruq faqat Dasturchi uchun.")
        return False
    return True


async def _resolve_user(token: str, query: str, message: Message) -> dict | None:
    """Ism bo'yicha (qisman moslik) yoki `#id`/aniq raqam bo'yicha xodimni
    topadi. Bir nechta moslik topilsa — ro'yxatni ko'rsatib, `#ID` bilan
    aniqlashtirishni so'raydi (button-wizard EMAS — Dasturchi buyruqlari
    ataylab matn-asosli, tez terish uchun)."""
    query = query.strip()
    if query.lstrip("#").isdigit():
        uid = int(query.lstrip("#"))
        users = await api_client.admin_search_users(token, "")
        match = next((u for u in users if u["id"] == uid), None)
        if match:
            return match
        await message.answer(f"#{uid} bo'yicha xodim topilmadi.")
        return None

    matches = await api_client.admin_search_users(token, query)
    if not matches:
        await message.answer(f"«{query}» bo'yicha xodim topilmadi.")
        return None
    if len(matches) > 1:
        names = "\n".join(f"  #{u['id']} — {u['full_name']} ({u['role']})" for u in matches[:8])
        await message.answer(
            f"Bir nechta xodim topildi, aniqroq yozing yoki #ID ishlating:\n{names}"
        )
        return None
    return matches[0]


@router.message(Command("norm_set"))
async def cmd_norm_set(message: Message, state: FSMContext) -> None:
    if not await _require_dasturchi(message):
        return
    await state.clear()
    tokens = (message.text or "").split()[1:]
    if len(tokens) < 3:
        await message.answer(
            "Foydalanish: /norm_set <xodim> <metrika> <qiymat>\n"
            "Masalan: /norm_set Aziz Karimov suhbat 40\n"
            "Cheklovsiz — HAR QANDAY rol va metrikaga (11.3-band)."
        )
        return
    value_str, metric = tokens[-1], tokens[-2]
    name_query = " ".join(tokens[:-2])
    if not re.match(r"^-?\d+$", value_str):
        await message.answer("Qiymat butun son bo'lishi kerak.")
        return

    token = await api_client.bot_admin_token(message.from_user.id)
    if not token:
        await message.answer("Ruxsat berilmadi (faqat Dasturchi).")
        return
    target = await _resolve_user(token, name_query, message)
    if target is None:
        return

    await state.update_data(
        action="norm_set", user_id=target["id"], user_name=target["full_name"],
        metric=metric, value=int(value_str),
    )
    await state.set_state(OverrideFSM.waiting_reason)
    await message.answer(f"{target['full_name']} — {metric} = {value_str}. Sababni yozing (kamida 5 belgi):")


@router.message(Command("norm_del"))
async def cmd_norm_del(message: Message, state: FSMContext) -> None:
    if not await _require_dasturchi(message):
        return
    await state.clear()
    tokens = (message.text or "").split()[1:]
    if len(tokens) < 2:
        await message.answer(
            "Foydalanish: /norm_del <xodim> <metrika>\nMasalan: /norm_del Aziz Karimov suhbat\n"
            "(shu xodimning shu metrika bo'yicha BARCHA faol yozuvlarini tozalaydi)"
        )
        return
    metric = tokens[-1]
    name_query = " ".join(tokens[:-1])

    token = await api_client.bot_admin_token(message.from_user.id)
    if not token:
        await message.answer("Ruxsat berilmadi (faqat Dasturchi).")
        return
    target = await _resolve_user(token, name_query, message)
    if target is None:
        return

    await state.update_data(
        action="norm_del", user_id=target["id"], user_name=target["full_name"], metric=metric
    )
    await state.set_state(OverrideFSM.waiting_reason)
    await message.answer(
        f"{target['full_name']} — {metric} metrikasi BUTUNLAY tozalanadi. Sababni yozing:"
    )


@router.message(Command("att_fix"))
async def cmd_att_fix(message: Message, state: FSMContext) -> None:
    if not await _require_dasturchi(message):
        return
    await state.clear()
    tokens = (message.text or "").split()[1:]
    if len(tokens) < 3:
        await message.answer(
            "Foydalanish: /att_fix <xodim> <YYYY-MM-DD> <HH:MM>\n"
            "Masalan: /att_fix Aziz Karimov 2026-07-20 09:15\n"
            "(shu kunga kelish vaqtini qo'lda belgilaydi/tuzatadi)"
        )
        return
    time_str, date_str = tokens[-1], tokens[-2]
    name_query = " ".join(tokens[:-2])
    if not _DATE_RE.match(date_str):
        await message.answer("Sana YYYY-MM-DD ko'rinishida bo'lishi kerak (masalan 2026-07-20).")
        return
    if not _TIME_RE.match(time_str):
        await message.answer("Vaqt HH:MM ko'rinishida bo'lishi kerak (masalan 09:15).")
        return

    token = await api_client.bot_admin_token(message.from_user.id)
    if not token:
        await message.answer("Ruxsat berilmadi (faqat Dasturchi).")
        return
    target = await _resolve_user(token, name_query, message)
    if target is None:
        return

    await state.update_data(
        action="att_fix", user_id=target["id"], user_name=target["full_name"],
        date=date_str, check_in=time_str,
    )
    await state.set_state(OverrideFSM.waiting_reason)
    await message.answer(
        f"{target['full_name']} — {date_str} kuni kelish vaqti {time_str}ga tuziladi. Sababni yozing:"
    )


@router.message(Command("unlock"))
async def cmd_unlock(message: Message, state: FSMContext) -> None:
    if not await _require_dasturchi(message):
        return
    await state.clear()
    tokens = (message.text or "").split()[1:]
    if len(tokens) != 1 or not _PERIOD_RE.match(tokens[0]):
        await message.answer("Foydalanish: /unlock <YYYY-MM>\nMasalan: /unlock 2026-07")
        return

    await state.update_data(action="unlock", period=tokens[0])
    await state.set_state(OverrideFSM.waiting_reason)
    await message.answer(f"«{tokens[0]}» davrining qulfi ochiladi. Sababni yozing:")


@router.message(Command("undo"))
async def cmd_undo(message: Message, state: FSMContext) -> None:
    if not await _require_dasturchi(message):
        return
    await state.clear()
    tokens = (message.text or "").split()[1:]
    if len(tokens) != 1 or not tokens[0].isdigit():
        await message.answer(
            "Foydalanish: /undo <norma ID>\n"
            "Eslatma: bu buyruq FAQAT norma yozuvlarini tiklaydi (11.3-band, asosiy talab). "
            "Boshqa jadvallar (davomat, vazifa va h.k.) uchun saytdagi «Dasturchi rejimi» "
            "sahifasi (Yozuvlar tabi) dan foydalaning."
        )
        return

    await state.update_data(action="undo", record_id=int(tokens[0]))
    await state.set_state(OverrideFSM.waiting_reason)
    await message.answer(f"Norma #{tokens[0]} tiklanadi. Sababni yozing:")


@router.message(StateFilter(OverrideFSM.waiting_reason))
async def handle_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if len(reason) < 5:
        await message.answer("Sabab kamida 5 belgi bo'lishi kerak. Qayta yozing:")
        return

    data = await state.get_data()
    action = data.get("action")
    await state.clear()

    token = await api_client.bot_admin_token(message.from_user.id)
    if not token:
        await message.answer("Ruxsat berilmadi (faqat Dasturchi).")
        return

    try:
        if action == "norm_set":
            await api_client.admin_set_norm(token, data["user_id"], data["metric"], data["value"], reason)
            await message.answer(f"✅ {data['user_name']} — {data['metric']} = {data['value']} belgilandi.")
        elif action == "norm_del":
            result = await api_client.admin_clear_metric(token, data["user_id"], data["metric"], reason)
            await message.answer(
                f"✅ {data['user_name']} — {data['metric']} tozalandi ({result['cleared']} yozuv)."
            )
        elif action == "att_fix":
            await api_client.admin_fix_attendance(token, data["user_id"], data["date"], data["check_in"], reason)
            await message.answer(f"✅ {data['user_name']} — {data['date']} kuni {data['check_in']}ga tuzatildi.")
        elif action == "unlock":
            await api_client.admin_unlock_payroll(token, data["period"], reason)
            await message.answer(f"✅ «{data['period']}» davrining qulfi ochildi.")
        elif action == "undo":
            await api_client.admin_restore_record(token, "norm", data["record_id"], reason)
            await message.answer(f"✅ Norma #{data['record_id']} tiklandi.")
        else:
            await message.answer("Noma'lum amal — qaytadan buyruq yuboring.")
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        try:
            detail = e.response.json().get("detail", detail)
        except Exception:
            pass
        await message.answer(f"❌ Xatolik: {detail}")
