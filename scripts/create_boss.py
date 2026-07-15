"""Yangi (bo'sh) bazada birinchi rahbarni yaratish — deploy'dagi "tuxum-tovuq"
muammosi: saytga Telegram orqali faqat bazada mavjud foydalanuvchi kira oladi.

Ishlatish (Docker):
  docker compose exec api python scripts/create_boss.py "To'liq Ism" 123456789

Ishlatish (lokal):
  .venv/Scripts/python scripts/create_boss.py "To'liq Ism" 123456789

Telegram ID'ni bilish uchun: Telegram'da @userinfobot ga yozing.
Agar shu telegram_id bilan foydalanuvchi allaqachon bo'lsa — hech narsa
o'zgartirilmaydi (xato bilan chiqadi).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from db.base import async_session  # noqa: E402
from db.models import Role, User  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('Ishlatish: create_boss.py "To\'liq Ism" <telegram_id>')
    full_name = sys.argv[1].strip()
    try:
        telegram_id = int(sys.argv[2])
    except ValueError:
        sys.exit("telegram_id butun son bo'lishi kerak (@userinfobot orqali bilib oling)")

    async with async_session() as db:
        existing = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        if existing:
            sys.exit(f"Bu telegram_id allaqachon mavjud: {existing.full_name} ({existing.role})")
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role=Role.boss.value,
            bot_started=True,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"Boshliq yaratildi: id={user.id}, {user.full_name}, telegram_id={telegram_id}")
        print("Endi saytga shu Telegram akkaunt bilan kirishingiz mumkin.")


if __name__ == "__main__":
    asyncio.run(main())
