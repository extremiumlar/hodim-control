from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import api_client
from bot.keyboards import BTN_CANCEL, cancel_menu, menu_for_user

router = Router(name="start")

ROLE_NAMES = {
    "employee": "Xodim",
    "hr": "HR",
    "rop": "ROP",
    "boss": "Boshliq",
    "dasturchi": "Dasturchi",
}


APP_LOGIN_PREFIX = "applogin_"


class AppLoginFSM(StatesGroup):
    """Ilova kirishini tasdiqlash — foydalanuvchidan JUFTLIK KODI kutiladi."""

    waiting_code = State()


async def _handle_app_login(message: Message, login_token: str, state: FSMContext) -> None:
    """Mobil ilova "Kirish" tugmasi bilan ochilgan deep-link
    (MOBIL_ILOVA_REJASI.md 4.1-band) — oddiy taklif-havola oqimidan alohida,
    chunki bu yerda yangi hisob yaratilmaydi, faqat allaqachon mavjud
    foydalanuvchi ilova sessiyasini tasdiqlaydi.

    XAVFSIZLIK — nega darhol tasdiqlamaymiz: ilgari shu funksiya havola
    ochilishi bilan `confirm_app_login` chaqirardi. `/auth/app-login/start`
    esa autentifikatsiyasiz, ya'ni HUJUMCHI o'zi havola yasab, uni xodimga
    yubora olardi ("tizimga kirish uchun bosing"). Xodim BIR MARTA bosishi
    bilan hujumchi `/auth/app-login/poll` orqali o'sha xodimning 30 kunlik
    JWT'sini olardi — parolsiz, kodsiz.

    Endi ilova ekranida 4 raqamli kod chiqadi va foydalanuvchi uni SHU YERGA
    yozadi. Ilovani ochmagan qurbonning yozadigan narsasi yo'q — hujum
    to'xtaydi. (Variantli tugmalar yetarli emas edi: ilovani ko'rmagan odam
    ham taxmin qilib bosishi mumkin.)"""
    # Kod yetkazishni serverdan so'raymiz: sayt oqimida kod shu chaqiruvda
    # foydalanuvchining MOBIL ILOVASIGA push bilan ketadi (sayt sahifasida
    # ko'rinmaydi — 2026-08-05 talabi), mobil ilova oqimida esa ilova uni
    # allaqachon o'z ekranida ko'rsatib turibdi.
    result = await api_client.request_app_login_code(login_token, message.from_user.id)
    status = result.get("status")

    if status in ("invalid", "no_account"):
        user = await api_client.get_user_by_telegram(message.from_user.id)
        keyboard = menu_for_user(user) if user else None
        if status == "no_account":
            await message.answer(
                "Sizning hisobingiz topilmadi yoki kirish ruxsatingiz yo'q. "
                "Administratorga murojaat qiling.",
                reply_markup=keyboard,
            )
        else:
            await message.answer(
                "Havola yaroqsiz yoki muddati o'tgan. Sayt yoki ilovada "
                "qaytadan urinib ko'ring.",
                reply_markup=keyboard,
            )
        return

    if status == "sent":
        where_line = (
            "📲 <b>4 raqamli kod mobil ilovangizga yuborildi</b> — "
            "bildirishnomani ochib, undagi kodni shu yerga yozing.\n"
            "Kod kelmasa, sayt sahifasidagi «Qaytadan» tugmasini bosing."
        )
    elif status == "screen_fallback":
        where_line = (
            "Mobil ilovangiz topilmadi, shuning uchun <b>4 raqamli kod "
            "sayt sahifasida ko'rsatildi</b> — o'shani shu yerga yozing."
        )
    else:  # screen — mobil ilova oqimi
        where_line = (
            "Kirish ekranida <b>4 raqamli kod</b> ko'rsatilgan — "
            "o'shani shu yerga yozing."
        )

    await state.set_state(AppLoginFSM.waiting_code)
    await state.update_data(app_login_token=login_token)
    await message.answer(
        "🔐 <b>Saytga yoki mobil ilovaga kirish so'ralmoqda.</b>\n\n"
        f"{where_line}\n\n"
        "⚠️ Agar siz o'zingiz kirishni boshlamagan bo'lsangiz, bu havolani "
        "kimdir sizga yuborgan bo'lishi mumkin. Unday holda <b>hech narsa "
        "yozmang</b> va «Bekor qilish»ni bosing.",
        reply_markup=cancel_menu(),
    )


@router.message(StateFilter(AppLoginFSM.waiting_code), F.text == BTN_CANCEL)
async def cancel_app_login(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    await message.answer(
        "Bekor qilindi. Kirish tasdiqlanmadi.",
        reply_markup=menu_for_user(user) if user else None,
    )


@router.message(StateFilter(AppLoginFSM.waiting_code), F.text)
async def receive_app_login_code(message: Message, state: FSMContext) -> None:
    """Foydalanuvchi yozgan kodni serverga uzatadi.

    Handler `start.router`da va HOLAT bilan filtrlangan: `bot/setup.py`da bu
    router eng birinchi ulanadi, ya'ni oxiridagi "erkin matn" ushlagichlari
    (anketa javobi, AI sabab matni) bu xabarni tortib olmaydi."""
    data = await state.get_data()
    login_token = data.get("app_login_token")
    if not login_token:
        await state.clear()
        await message.answer("Sessiya topilmadi. Ilovada qaytadan urinib ko'ring.")
        return

    code = (message.text or "").strip()
    result = await api_client.confirm_app_login(login_token, message.from_user.id, code)
    status = result.get("status")

    if status == "wrong_code":
        # Holat SAQLANADI — foydalanuvchi qayta urinib ko'rsin. Urinishlar
        # serverda sanaladi va chegaraga yetganda token o'zi kuyadi.
        left = result.get("attempts_left")
        await message.answer(
            f"❌ Kod noto'g'ri. Yana {left} ta urinish qoldi.\n"
            "Kirish ekranidagi (sayt yoki ilova) 4 raqamli kodni tekshirib qayta yozing."
        )
        return

    await state.clear()
    user = await api_client.get_user_by_telegram(message.from_user.id)
    keyboard = menu_for_user(user) if user else None

    if status == "ok":
        await message.answer(
            "✅ Kirish tasdiqlandi. Sayt sahifasiga yoki ilovaga qayting.", reply_markup=keyboard
        )
    elif status == "no_account":
        await message.answer(
            "Sizning hisobingiz topilmadi yoki kirish ruxsatingiz yo'q. "
            "Administratorga murojaat qiling.",
            reply_markup=keyboard,
        )
    else:
        await message.answer(
            "Havola yaroqsiz yoki muddati o'tgan (yoki kod juda ko'p marta "
            "noto'g'ri kiritildi). Sayt yoki ilovada qaytadan urinib ko'ring.",
            reply_markup=keyboard,
        )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext) -> None:
    invite_token = command.args or None

    if invite_token and invite_token.startswith(APP_LOGIN_PREFIX):
        await _handle_app_login(message, invite_token[len(APP_LOGIN_PREFIX):], state)
        return

    # Boshqa har qanday /start chala qolgan ilova-kirish oqimini tozalaydi,
    # aks holda foydalanuvchi kod kutish holatida "osilib" qolardi.
    await state.clear()

    result = await api_client.telegram_start(message.from_user.id, invite_token)

    if result["status"] == "invalid_token":
        await message.answer("Havola yaroqsiz yoki muddati o'tgan. Administratorga murojaat qiling.")
        return

    if result["status"] == "token_expired":
        await message.answer("Taklif havolasi muddati o'tgan — HR/Boshliqdan yangisini so'rang.")
        return

    if result["status"] == "no_account":
        await message.answer("Ma'lumotlaringiz hali tizimga kiritilmagan, administratorga murojaat qiling.")
        return

    user = result["user"]
    role_name = ROLE_NAMES.get(user["role"], user["role"])
    position = user.get("position") or {}
    position_line = f"\nLavozim: <b>{position['name']}</b>" if position.get("name") else ""
    await message.answer(
        f"Assalomu alaykum, {user['full_name']}!\n"
        f"Siz tizimga <b>{role_name}</b> sifatida ulandingiz.{position_line}",
        reply_markup=menu_for_user(user),
    )
