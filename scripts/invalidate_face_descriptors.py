"""BIR MARTALIK skript — BUG_FIX_PROMPT.md Savol A, 4-variant: mavjud barcha yuz
deskriptorlarini bekor qiladi (ular eski, buzuq `captureForRegister()` o'rtachalash
xatosi bilan yozilgan — 6/6 juftlik bir-biriga o'xshab qolgan, ya'ni Face ID amalda
hech kimni ajratmagan).

Bajarilgandan keyin: ta'sirlangan xodimlar keyingi check-in urinishida "avval
yuzingizni ro'yxatdan o'tkazing" xabarini ko'radi va ENDI TUZATILGAN (o'rtachalash
yo'q, eng yaxshi freym) kod bilan qayta ro'yxatdan o'tadi. Har biri AuditLog'ga
`action=\"face_invalidated_bulk\"` bilan yoziladi — kim, qachon, nima sababdan.

Ishga tushirish (loyiha ildizidan):
    .venv/Scripts/python.exe scripts/invalidate_face_descriptors.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.base import async_session
from db.models import AuditLog, User


async def main() -> None:
    async with async_session() as db:
        users = list(await db.scalars(select(User).where(User.face_descriptor.isnot(None))))
        if not users:
            print("Bekor qilinadigan deskriptor topilmadi — hech narsa qilinmadi.")
            return
        print(f"{len(users)} ta xodimning yuzi bekor qilinadi:")
        for u in users:
            print(f"  - {u.full_name} (id={u.id}, ro'yxatdan o'tgan: {u.face_registered_at})")
            db.add(
                AuditLog(
                    actor_id=None,
                    action="face_invalidated_bulk",
                    target_user_id=u.id,
                    before={"had_face": True, "registered_at": u.face_registered_at.isoformat() if u.face_registered_at else None},
                    after={"reason": "captureForRegister o'rtachalash bugi — barcha yuzlar bir-biriga o'xshab qolgan (6/6 juftlik). Qayta ro'yxatdan o'tish kerak."},
                )
            )
            u.face_descriptor = None
            u.face_registered_at = None
        await db.commit()
        print(f"\n{len(users)} ta xodimning yuzi bekor qilindi. Ular endi yangi (tuzatilgan) kod bilan qayta ro'yxatdan o'tishi kerak.")


if __name__ == "__main__":
    asyncio.run(main())
