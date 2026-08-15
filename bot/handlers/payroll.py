"""Bot — payroll (oylik ish haqi). Bosqich 5, OYLIK_JARIMA_REJASI.md 5.2-band.

Ikkita ko'rinish:
- "💵 Mening oyligim" — oxirgi TASDIQLANGAN payslip (xodim/HR/ROP/Dasturchi;
  Boshliq payroll'ga kirmaydi, PAYROLL_TRACKED_ROLES bilan bir xil qamrov).
- Shu xabar ostidagi «🕐 Kechikishlarim» inline tugmasi — joriy (hali
  yakunlanmagan) oy uchun JONLI hisoblangan limit holati.

Proaktiv ogohlantirish (limitdan 1 kun qolganda / limit tugaganda darhol)
ATAYLAB shu yerda YO'Q — Bosqich 6 (avtomatika, kunlik scheduler jobi)ga
tegishli: bot faqat SO'RALGANDA javob beradi (pull), avtomatik push alohida
jarayon."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client
from bot.keyboards import BTN_PAYROLL

router = Router(name="payroll")


def _fmt_money(n: float) -> str:
    return f"{round(n):,}".replace(",", " ") + " so'm"


def _payslip_text(data: dict) -> str:
    lines = [f"💵 <b>{data['period']} oyi uchun oyligingiz</b>", ""]
    lines.append(f"Asosiy oylik: {_fmt_money(data['base_amount'])}")
    # Manfiy bo'lishi mumkin (2026-08-15): oy bo'yicha kam ishlangan vaqt
    # ortiqchasidan ko'p chiqsa — u holda bu ushlanma, "+" belgisi yolg'on
    # bo'lardi.
    if data.get("overtime_amount"):
        ot = data["overtime_amount"]
        if ot > 0:
            lines.append(f"Qo'shimcha ish: +{_fmt_money(ot)}")
        else:
            lines.append(f"Kam ishlangan vaqt: −{_fmt_money(abs(ot))}")
    if data.get("bonus_amount"):
        lines.append(f"Bonus: +{_fmt_money(data['bonus_amount'])}")
    if data.get("fine_amount"):
        lines.append(f"Kechikish jarimasi: −{_fmt_money(data['fine_amount'])}")
    if data.get("absent_deduction"):
        lines.append(f"Kelmagan kun ushlanmasi: −{_fmt_money(data['absent_deduction'])}")
    # Avans va qo'lda kiritilgan qo'shimcha/ushlanmalar (2026-08-13). Bular
    # ILGARI KO'RSATILMASDI — `Jami` qatorlar yig'indisiga to'g'ri kelmasdi.
    if data.get("adjustments_plus"):
        lines.append(f"Qo'shimcha: +{_fmt_money(data['adjustments_plus'])}")
    if data.get("advance_amount"):
        lines.append(f"Avans (olingan): −{_fmt_money(data['advance_amount'])}")
    if data.get("adjustments_minus"):
        lines.append(f"Ushlanma: −{_fmt_money(data['adjustments_minus'])}")
    lines.append("")
    lines.append(f"<b>Jami: {_fmt_money(data['net'])}</b>")
    if data.get("approved_at"):
        lines.append(f"\n<i>Tasdiqlangan: {data['approved_at'][:10]}</i>")
    return "\n".join(lines)


def _late_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🕐 Kechikishlarim", callback_data="payroll_late_status")]]
    )


@router.message(F.text == BTN_PAYROLL)
async def show_my_payslip(message: Message, state: FSMContext) -> None:
    await state.clear()
    data = await api_client.my_payslip(message.from_user.id)
    if not data.get("calculated"):
        await message.answer(
            "Hali tasdiqlangan oyligingiz yo'q. Oy oxirida HR/Boshliq hisoblab tasdiqlagach shu yerda ko'rinadi.",
            reply_markup=_late_status_keyboard(),
        )
        return
    await message.answer(_payslip_text(data), reply_markup=_late_status_keyboard())


@router.callback_query(F.data == "payroll_late_status")
async def show_late_status(callback: CallbackQuery) -> None:
    await callback.answer()
    data = await api_client.my_payroll_late_status(callback.from_user.id)
    if data.get("free_limit_minutes") is None:
        await callback.message.answer(
            "Kechikish jarimasi qoidasi hali sozlanmagan — hozircha kechikish uchun jarima yo'q."
        )
        return

    used = data["used_minutes"]
    limit = data["free_limit_minutes"]
    remaining = data.get("remaining_minutes") or 0
    lines = [f"🕐 <b>{data['period']} oyi — kechikish holati</b>", "", f"Ishlatilgan: {used} / {limit} daqiqa"]
    if remaining > 0:
        lines.append(f"Yana {remaining} daqiqa bepul kechikish qoldi.")
    else:
        lines.append("Limit tugagan — shu kundan keyingi har bir kechikkan kunga jarima yoziladi.")
        fined = data.get("fined_days_so_far", 0)
        if fined:
            lines.append(f"Bu oy allaqachon <b>{fined}</b> kun jarimalandi.")
    await callback.message.answer("\n".join(lines))
