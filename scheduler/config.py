import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_SHARED_SECRET = os.getenv("BOT_SHARED_SECRET", "please-change-this-bot-secret")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")
