from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_TASKS = "📋 Vazifalarim"
BTN_NORM = "📊 Bugungi normam"
BTN_KPI = "💰 Oylik KPI'm"
BTN_PANEL = "📈 Panelim"
BTN_EXCUSED = "🙋 Sababli kun so'rash"
BTN_CANCEL = "❌ Bekor qilish"


def main_menu(role: str) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_TASKS)],
        [KeyboardButton(text=BTN_NORM), KeyboardButton(text=BTN_KPI)],
        [KeyboardButton(text=BTN_EXCUSED)],
    ]
    if role in {"hr", "rop", "boss"}:
        rows.append([KeyboardButton(text=BTN_PANEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)
