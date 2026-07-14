import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_SHARED_SECRET = os.getenv("BOT_SHARED_SECRET", "please-change-this-bot-secret")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
TELEGRAM_GROUP_CHAT_ID = int(os.getenv("TELEGRAM_GROUP_CHAT_ID", "0") or "0")


def _parse_group_ids(raw: str) -> list[int]:
    """Vergul bilan ajratilgan guruh ID'larini ro'yxatga o'giradi (noto'g'ri/bo'sh
    qismlarni tashlab)."""
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


# Qo'shimcha statistika guruh(lar)i — kunlik digest shu guruh(lar)ga ham tushadi;
# /statistika buyrug'i bu guruh(lar)da ham ishlaydi. Vergul bilan bir nechta.
TELEGRAM_STATS_GROUP_CHAT_IDS = _parse_group_ids(os.getenv("TELEGRAM_STATS_GROUP_CHAT_ID", ""))
