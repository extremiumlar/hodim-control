"""Birinchi `boss` foydalanuvchisini qo'lda yaratish uchun CLI skript.

Ishlatilishi (loyiha ildizidan):
    python -m db.seed <telegram_id> <to'liq ism>

Masalan:
    python -m db.seed 123456789 "Aziz Aliyev"
"""

import asyncio
import sys

from sqlalchemy import select

from db.base import async_session
from db.models import Role, User


async def seed_boss(telegram_id: int, full_name: str) -> None:
    async with async_session() as session:
        existing = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if existing:
            print(f"Foydalanuvchi allaqachon mavjud: {existing.full_name} ({existing.role})")
            return

        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role=Role.boss.value,
            bot_started=False,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"'{full_name}' boss sifatida yaratildi (telegram_id={telegram_id}).")


def main() -> None:
    if len(sys.argv) < 3:
        print('Ishlatilishi: python -m db.seed <telegram_id> "<to\'liq ism>"')
        sys.exit(1)

    telegram_id = int(sys.argv[1])
    full_name = sys.argv[2]
    asyncio.run(seed_boss(telegram_id, full_name))


if __name__ == "__main__":
    main()
