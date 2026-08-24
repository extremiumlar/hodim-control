from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_TASKS = "📋 Vazifalarim"
BTN_NORM = "📊 Bugungi normam"
BTN_KPI = "💰 Oylik KPI'm"
BTN_PAYROLL = "💵 Mening oyligim"
BTN_PANEL = "📈 Panelim"
BTN_EXCUSED = "🙋 Sababli kun so'rash"
BTN_WORK_LOG = "📝 Ish kundaligi"
# DIQQAT: «E'tiroz» so'zi botda SOTUV kontekstida ham bor (playbook: «🛡 E'tiroz
# bilan ishlash» — MIJOZ e'tirozlari). Bu tugma esa XODIMNING o'z murojaati.
# Matn ataylab farqli («/ Shikoyat» qo'shimchasi bilan) — chalkashmasin.
BTN_APPEAL = "⚖️ E'tiroz / Shikoyat"
# 2026-08-13: e'tiroz/shikoyatga ARIZA qo'shildi va uchalasi bitta hub
# ostiga birlashtirildi — menyuda allaqachon 8-10 tugma bor, yana bittasi
# qo'shilsa xodim adashadi.
# ⚠️ BTN_APPEAL O'CHIRILMAYDI: Telegram klaviaturani xodim qurilmasida
# KESHLAB qo'yadi, ya'ni eski tugmani bosaverishi mumkin. U menyudan
# olib tashlandi, lekin handler ikkala matnni ham ushlaydi.
BTN_REQUESTS = "📮 Murojaatlarim"
BTN_ASSIGN_TASK = "📤 Vazifa berish"
BTN_MY_STATS = "📈 Statistikam"
BTN_GLOBAL_STATS = "📊 Umumiy statistika"
BTN_ATTENDANCE_STATS = "🕐 Davomat statistikasi"
BTN_LEAD_STATS = "🧲 Lidlar statistikasi"
BTN_SCHEDULE = "🗓 Ish jadvali"
BTN_HOURLY_PLAN = "📋 Bugungi rejam"
BTN_HOURLY_PLAN_CONTROL = "📋 Xodim rejasi"
BTN_CHANGE_NORM = "🎯 Norma o'zgartirish"
BTN_TASK_CONTROL = "📋 Vazifalar nazorati"
BTN_CALC_KPI = "💰 Oylik KPI hisoblash"
BTN_REPORT = "📥 Hisobot (Excel)"
BTN_AUDIT = "🧾 Audit jurnali"
BTN_AI_CENTER = "🧠 Sotuv AI markazi"
BTN_CELEBRATION = "🎬 Tabrik videolari"
BTN_MY_DOCS = "📁 Hujjatlarim"
BTN_DOC_UPLOAD = "📎 Hujjat yuklash"
BTN_SET_BUSY = "⏸ Band qilish"
BTN_MARK_EXCUSED = "🙋 Xodim uchun sababli kun"
# Eski alohida tugmalar — endi asosiy menyuda ko'rinmaydi (BTN_AI_CENTER
# ularni almashtirdi), lekin /anketa, /bilim buyruqlari va shu matnli xabar
# hamon ishlaydi (foydalanuvchida eski klaviatura keshi qolgan bo'lishi mumkin).
BTN_ANKETA = "📝 Anketa"
BTN_KNOWLEDGE = "📚 Bilim bazasi"
BTN_SALES_AI = "🤖 Sotuv AI"
BTN_CANCEL = "❌ Bekor qilish"
# Saytga kirishda: push kelmasa kodni sayt sahifasida ko'rsatishga
# o'tish (api/routers/auth.py: app_login_use_screen).
BTN_CODE_NOT_RECEIVED = "📵 Kod kelmadi"
# UX2-W4 (C1): xodim davomatga botdan bir bosishda yetsin — ilgari bot
# «Keldim»ni bosing» der, lekin bosadigan joy BERMASdi.
BTN_CHECKIN = "✅ Keldim / Ketdim"
BTN_HR_ASK = "❓ HR ga savol"
BTN_MY_COURSES = "📚 Darsliklarim"
BTN_MY_PLACE = "🏢 Mening o'rnim"
BTN_COMPANY = "🏛 Kompaniya"
BTN_ONBOARDING = "📋 Birinchi kunlarim"

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}

# UX2-W4 (C3): FSM holatida turgan foydalanuvchi menyu tugmasini bossa, tugma
# matni "sabab" sifatida HR'ga ketib qolardi. Har bir matn-kutuvchi handler
# `~F.text.in_(ALL_MENU_BUTTONS)` filtri bilan himoyalanadi.
ALL_MENU_BUTTONS = frozenset({
    BTN_TASKS, BTN_NORM, BTN_KPI, BTN_PAYROLL, BTN_PANEL, BTN_EXCUSED,
    BTN_ASSIGN_TASK, BTN_MY_STATS, BTN_GLOBAL_STATS, BTN_ATTENDANCE_STATS,
    BTN_LEAD_STATS, BTN_SCHEDULE, BTN_HOURLY_PLAN, BTN_HOURLY_PLAN_CONTROL,
    BTN_CHANGE_NORM, BTN_TASK_CONTROL, BTN_CALC_KPI, BTN_REPORT, BTN_AUDIT,
    BTN_AI_CENTER, BTN_SET_BUSY, BTN_MARK_EXCUSED, BTN_ANKETA, BTN_KNOWLEDGE,
    BTN_SALES_AI, BTN_CHECKIN, BTN_WORK_LOG, BTN_APPEAL, BTN_REQUESTS,
    BTN_CELEBRATION, BTN_HR_ASK, BTN_MY_COURSES, BTN_MY_PLACE, BTN_COMPANY,
    BTN_ONBOARDING,
    #  Hujjat tugmalari ro'yxatdan TUSHIB QOLGAN edi: FSM matn kutayotgan
    #  paytda «📁 Hujjatlarim» bosilsa, tugma matni javob sifatida
    #  yozilardi. Ro'yxatning butun mazmuni shu holatni to'sish.
    BTN_MY_DOCS, BTN_DOC_UPLOAD,
})



def main_menu(rows: list[list[str]] | None) -> ReplyKeyboardMarkup:
    """Serverdan kelgan tugma qatorlarini klaviaturaga aylantiradi.

    ⚠️ ILGARI bu funksiya menyuni O'ZI qurardi: rol, `menu_flags` va
    lavozim ko'rsatkichlari bo'yicha ~20 ta shart. AYNAN o'sha shartlar
    saytda ham (ikki joyda) takrorlanardi va muvofiqlik inson e'tiboriga
    qolgan edi. Endi qoida bitta joyda — `api/services/sections.py` —
    va bot faqat CHIZADI (TZ 2.6 / S-05b).

    `rows` bo'sh yoki `None` bo'lsa (API javob bermadi yoki eski versiya)
    — MINIMAL zaxira klaviatura. Ataylab to'liq ro'yxat EMAS: aks holda
    bu yerda ikkinchi manba paydo bo'lib, tuzatilgan muammo qaytardi."""
    if not rows:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_CHECKIN)]], resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


def menu_for_user(user: dict | None) -> ReplyKeyboardMarkup:
    """API javobidagi tayyor menyudan klaviatura — barcha handlerlar uchun.

    `bot_menu` maydonini `GET /users/by-telegram/{id}` qaytaradi. Bot
    foydalanuvchini menyu chizishdan oldin baribir oladi, ya'ni QO'SHIMCHA
    so'rov yo'q va menyu HAR DOIM yangi (kesh eskirishi mumkin emas —
    rol o'zgarsa keyingi javobda darhol aks etadi)."""
    return main_menu((user or {}).get("bot_menu"))


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def app_login_menu(show_not_received: bool) -> ReplyKeyboardMarkup:
    """Saytga kirish paytidagi klaviatura.

    «Kod kelmadi» FAQAT push yo'lida ko'rsatiladi — kod allaqachon
    ekranda bo'lsa bu tugma chalkashtirardi."""
    rows = [[KeyboardButton(text=BTN_CANCEL)]]
    if show_not_received:
        rows.insert(0, [KeyboardButton(text=BTN_CODE_NOT_RECEIVED)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
