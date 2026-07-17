from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_TASKS = "📋 Vazifalarim"
BTN_NORM = "📊 Bugungi normam"
BTN_KPI = "💰 Oylik KPI'm"
BTN_PANEL = "📈 Panelim"
BTN_EXCUSED = "🙋 Sababli kun so'rash"
BTN_ASSIGN_TASK = "📤 Vazifa berish"
BTN_MY_STATS = "📈 Statistikam"
BTN_GLOBAL_STATS = "📊 Umumiy statistika"
BTN_LEAD_STATS = "🧲 Lidlar statistikasi"
BTN_SCHEDULE = "🗓 Ish jadvali"
BTN_HOURLY_PLAN = "📋 Bugungi rejam"
BTN_HOURLY_PLAN_CONTROL = "📋 Xodim rejasi"
BTN_CHANGE_NORM = "🎯 Norma o'zgartirish"
BTN_TASK_CONTROL = "📋 Vazifalar nazorati"
BTN_CALC_KPI = "💰 Oylik KPI hisoblash"
BTN_REPORT = "📥 Hisobot (Excel)"
BTN_AUDIT = "🧾 Audit jurnali"
BTN_ANKETA = "📝 Anketa"
BTN_KNOWLEDGE = "📚 Bilim bazasi"
BTN_SALES_AI = "🤖 Sotuv AI"
BTN_CANCEL = "❌ Bekor qilish"

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}

# Lavozimda menu_flags belgilanmagan bo'lsa (yoki xodimga lavozim biriktirilmagan
# bo'lsa) — barcha tugmalar ko'rinadi (orqaga moslik).
DEFAULT_MENU_FLAGS = {"tasks": True, "norm": True, "kpi": True, "excused": True}


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
    if flags.get("tasks"):
        rows.append([KeyboardButton(text=BTN_TASKS)])

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

    # Ish jadvali — barcha xodimlarga (o'zini ko'radi), rahbarlar hammani ko'radi
    rows.append([KeyboardButton(text=BTN_SCHEDULE)])

    # Soatlik reja — kunlik normasi kuzatiladigan (suhbat/tashrif/video) xodimlarga
    has_trackable_metric = bool(
        set(metrics if metrics is not None else ["suhbat", "tashrif"]) & {"suhbat", "tashrif", "video"}
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
        if role in {"rop", "boss", "dasturchi"}:
            # Sotuv AI sinovi — rahbar mijoz savolini yozib javob sifatini tekshiradi
            rows.append([KeyboardButton(text=BTN_SALES_AI)])
        if role in {"boss", "dasturchi"}:
            # KPI qayta hisoblash va audit jurnali — faqat eng yuqori daraja
            rows.append([KeyboardButton(text=BTN_CALC_KPI), KeyboardButton(text=BTN_REPORT)])
            rows.append([KeyboardButton(text=BTN_AUDIT), KeyboardButton(text=BTN_PANEL)])
            # Sotuv bilim bazasi — anketa javoblarini tasdiqlash/boyitish (boss ham).
            # Anketa boshlanishini esa faqat Dasturchi tasdiqlaydi.
            knowledge_row = [KeyboardButton(text=BTN_KNOWLEDGE)]
            if role == "dasturchi":
                knowledge_row.append(KeyboardButton(text=BTN_ANKETA))
            rows.append(knowledge_row)
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
