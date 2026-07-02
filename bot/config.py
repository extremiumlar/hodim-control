import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_SHARED_SECRET = os.getenv("BOT_SHARED_SECRET", "please-change-this-bot-secret")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
TELEGRAM_GROUP_CHAT_ID = int(os.getenv("TELEGRAM_GROUP_CHAT_ID", "0") or "0")
