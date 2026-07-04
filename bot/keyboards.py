from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_TASKS = "📋 Vazifalarim"
BTN_NORM = "📊 Bugungi normam"
BTN_KPI = "💰 Oylik KPI'm"
BTN_PANEL = "📈 Panelim"
BTN_EXCUSED = "🙋 Sababli kun so'rash"
BTN_ASSIGN_TASK = "📤 Vazifa berish"
BTN_MY_STATS = "📈 Statistikam"
BTN_GLOBAL_STATS = "📊 Umumiy statistika"
BTN_CANCEL = "❌ Bekor qilish"

MANAGER_ROLES = {"hr", "rop", "boss", "dasturchi"}

# Lavozimda menu_flags belgilanmagan bo'lsa (yoki xodimga lavozim biriktirilmagan
# bo'lsa) — barcha tugmalar ko'rinadi (orqaga moslik).
DEFAULT_MENU_FLAGS = {"tasks": True, "norm": True, "kpi": True, "excused": True}


def main_menu(role: str, menu_flags: dict | None = None) -> ReplyKeyboardMarkup:
    """Asosiy menyu — xodimning lavozimiga (`menu_flags`) qarab moslashadi.

    "📈 Statistikam" har doim ko'rinadi (har bir xodim o'z statistikasini olishi
    mumkin); rahbar rollarga qo'shimcha boshqaruv tugmalari chiqadi."""
    flags = {**DEFAULT_MENU_FLAGS, **(menu_flags or {})}

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

    if role in MANAGER_ROLES:
        rows.append([KeyboardButton(text=BTN_ASSIGN_TASK), KeyboardButton(text=BTN_GLOBAL_STATS)])
        rows.append([KeyboardButton(text=BTN_PANEL)])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def menu_for_user(user: dict | None) -> ReplyKeyboardMarkup:
    """API'dan kelgan foydalanuvchi lug'atidan (position.menu_flags bilan) menyu
    quradi — barcha handlerlar uchun umumiy yordamchi."""
    role = user.get("role", "employee") if user else "employee"
    position = (user or {}).get("position") or {}
    return main_menu(role, position.get("menu_flags"))


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)
