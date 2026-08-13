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
BTN_SET_BUSY = "⏸ Band qilish"
BTN_MARK_EXCUSED = "🙋 Xodim uchun sababli kun"
# Eski alohida tugmalar — endi asosiy menyuda ko'rinmaydi (BTN_AI_CENTER
# ularni almashtirdi), lekin /anketa, /bilim buyruqlari va shu matnli xabar
# hamon ishlaydi (foydalanuvchida eski klaviatura keshi qolgan bo'lishi mumkin).
BTN_ANKETA = "📝 Anketa"
BTN_KNOWLEDGE = "📚 Bilim bazasi"
BTN_SALES_AI = "🤖 Sotuv AI"
BTN_CANCEL = "❌ Bekor qilish"
# UX2-W4 (C1): xodim davomatga botdan bir bosishda yetsin — ilgari bot
# «Keldim»ni bosing» der, lekin bosadigan joy BERMASdi.
BTN_CHECKIN = "✅ Keldim / Ketdim"

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
    BTN_SALES_AI, BTN_CHECKIN, BTN_WORK_LOG, BTN_APPEAL,
})

# Lavozimda menu_flags belgilanmagan bo'lsa (yoki xodimga lavozim biriktirilmagan
# bo'lsa) — barcha tugmalar ko'rinadi (orqaga moslik).
DEFAULT_MENU_FLAGS = {"tasks": True, "norm": True, "kpi": True, "excused": True, "payroll": True}


def main_menu(
    role: str, menu_flags: dict | None = None, metrics: list | None = None
) -> ReplyKeyboardMarkup:
    """Asosiy menyu — xodimning lavozimiga (`menu_flags`) qarab moslashadi.

    "📈 Statistikam" har doim ko'rinadi (har bir xodim o'z statistikasini olishi
    mumkin); rahbar rollarga qo'shimcha boshqaruv tugmalari chiqadi.

    "🧲 Lidlar statistikasi" — rahbar rollarga hamda sotuv operatorlariga (lavozim
    ko'rsatkichlarida suhbat/tashrif borlarga; lavozim biriktirilmagan bo'lsa —
    backend defaulti bilan mos ravishda ko'rinadi). Haqiqiy ruxsat backendda
    tekshiriladi — tugma faqat qulaylik."""
    flags = {**DEFAULT_MENU_FLAGS, **(menu_flags or {})}
    # Backend metrics_for() bilan bir xil default: lavozim yo'q — suhbat+tashrif
    sales_metrics = {"suhbat", "tashrif"} & set(metrics if metrics is not None else ["suhbat", "tashrif"])
    show_lead_stats = role in MANAGER_ROLES or bool(sales_metrics)

    rows: list[list[KeyboardButton]] = []

    # UX2-C1: davomat kuzatiladigan har kimga (Boshliqdan tashqari) —
    # «Keldim/Ketdim» sahifasiga to'g'ridan-to'g'ri yo'l. Eng tepada, chunki
    # bu kuniga 2 marta bosiladigan eng muhim tugma.
    if role != "boss":
        rows.append([KeyboardButton(text=BTN_CHECKIN)])

    if flags.get("tasks"):
        rows.append([KeyboardButton(text=BTN_TASKS)])

    # Ish kundaligi — Boshliqdan tashqari hammaga (BTN_PAYROLL bilan bir xil
    # qamrov: xodim ham, HR/ROP/Dasturchi ham o'z kundaligini yuritadi).
    # Kuniga bir necha marta bosiladi, shuning uchun tepada.
    if role != "boss":
        rows.append([KeyboardButton(text=BTN_WORK_LOG)])

    metrics_row = []
    if flags.get("norm"):
        metrics_row.append(KeyboardButton(text=BTN_NORM))
    if flags.get("kpi"):
        metrics_row.append(KeyboardButton(text=BTN_KPI))
    if metrics_row:
        rows.append(metrics_row)

    stats_row = [KeyboardButton(text=BTN_MY_STATS)]
    if flags.get("excused"):
        stats_row.append(KeyboardButton(text=BTN_EXCUSED))
    rows.append(stats_row)

    # E'tiroz/Shikoyat — Boshliqdan tashqari hammaga (u qabul qiluvchi tomon).
    # Sababli kun qatoridan keyin: ikkalasi ham «murojaat» turkumidagi
    # tugmalar, xodim ularni yonma-yon izlaydi.
    if role != "boss":
        rows.append([KeyboardButton(text=BTN_APPEAL)])

    # Ish jadvali — barcha xodimlarga (o'zini ko'radi), rahbarlar hammani ko'radi
    rows.append([KeyboardButton(text=BTN_SCHEDULE)])

    # Oylik — Boshliqdan tashqari hamma (davomat/payroll bilan bir xil qamrov,
    # ATTENDANCE_TRACKED_ROLES/PAYROLL_TRACKED_ROLES): xodim ham, HR/ROP/
    # Dasturchi ham o'z oyligini shu yerdan ko'radi.
    if flags.get("payroll") and role != "boss":
        rows.append([KeyboardButton(text=BTN_PAYROLL)])

    # Soatlik reja — kunlik normasi kuzatiladigan (suhbat/tashrif/video) xodimlarga
    has_trackable_metric = bool(
        set(metrics if metrics is not None else ["suhbat", "tashrif"])
        & {"suhbat", "tashrif", "oddiy_video", "dumaloq_video"}
    )
    if role not in MANAGER_ROLES and has_trackable_metric:
        rows.append([KeyboardButton(text=BTN_HOURLY_PLAN)])

    if show_lead_stats and role not in MANAGER_ROLES:
        rows.append([KeyboardButton(text=BTN_LEAD_STATS)])

    # Sotuv AI — sotuv xodimlariga YORDAMCHI (mijoz savoliga rasmiy javob varianti)
    if role not in MANAGER_ROLES and bool(sales_metrics):
        rows.append([KeyboardButton(text=BTN_SALES_AI)])

    if role in MANAGER_ROLES:
        rows.append([KeyboardButton(text=BTN_ASSIGN_TASK), KeyboardButton(text=BTN_CHANGE_NORM)])
        rows.append([KeyboardButton(text=BTN_TASK_CONTROL), KeyboardButton(text=BTN_GLOBAL_STATS)])
        rows.append([KeyboardButton(text=BTN_LEAD_STATS), KeyboardButton(text=BTN_HOURLY_PLAN_CONTROL)])
        # Davomat (kelib-ketish) — kim nechada keldi/kechikdi statistikasi
        rows.append([KeyboardButton(text=BTN_ATTENDANCE_STATS)])
        if role in {"hr", "boss", "dasturchi"}:
            # Xodim o'zi bot ishlata olmagan holatda (masalan kasal) HR/Boshliq
            # uning nomidan sababli kunni to'g'ridan-to'g'ri belgilaydi
            # (decide_excused_day bilan bir xil qamrov — ROP bu yerda ham yo'q).
            rows.append([KeyboardButton(text=BTN_MARK_EXCUSED)])
        if role in {"rop", "boss", "dasturchi"}:
            # Sotuv AI sinovi — rahbar mijoz savolini yozib javob sifatini tekshiradi
            rows.append([KeyboardButton(text=BTN_SALES_AI)])
        if role in {"boss", "dasturchi"}:
            # KPI qayta hisoblash va audit jurnali — faqat eng yuqori daraja
            rows.append([KeyboardButton(text=BTN_CALC_KPI), KeyboardButton(text=BTN_REPORT)])
            rows.append([KeyboardButton(text=BTN_AUDIT), KeyboardButton(text=BTN_PANEL)])
            # Operatorni vaqtincha "band" (yig'ilish/vazifa) deb belgilash —
            # shu vaqt davomida real-vaqtli harakatsizlik ogohlantirishi kelmaydi
            rows.append([KeyboardButton(text=BTN_SET_BUSY)])
            # Anketa + Bilim bazasi + Sotuv playbook — YAGONA dashboard orqali
            # (ilgari ikkita alohida tugma edi; anketani boshlashni faqat
            # Dasturchi qila oladi, backend shu cheklovni saqlaydi).
            rows.append([KeyboardButton(text=BTN_AI_CENTER)])
        else:
            rows.append([KeyboardButton(text=BTN_REPORT), KeyboardButton(text=BTN_PANEL)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_for_user(user: dict | None) -> ReplyKeyboardMarkup:
    """API'dan kelgan foydalanuvchi lug'atidan (position.menu_flags bilan) menyu
    quradi — barcha handlerlar uchun umumiy yordamchi."""
    role = user.get("role", "employee") if user else "employee"
    position = (user or {}).get("position") or {}
    return main_menu(role, position.get("menu_flags"), position.get("metrics"))


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)
