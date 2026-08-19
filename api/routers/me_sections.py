"""`GET /me/sections` — foydalanuvchi ko'radigan bo'limlar (TZ 2.6, S-04).

Mijozlar (sayt yon paneli, xodim kabineti tab-bari, bot klaviaturasi va
mobil ilova) menyuni SHU javobdan quradi. Ro'yxatning o'zi
`api/services/sections.py` da — yagona manba.

NEGA ALOHIDA ROUTER: `users.py` allaqachon katta va bu endpoint mantiqan
navigatsiyaga tegishli, foydalanuvchi ma'lumotiga emas.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user
from api.services.sections import sections_for
from db.models import User

router = APIRouter(prefix="/me", tags=["me"])


class SectionOut(BaseModel):
    key: str
    label: str
    path: str
    icon: str
    order: int
    audience: str
    group: str
    bot_button: str | None = None
    exact: bool = False


@router.get("/sections", response_model=list[SectionOut])
async def my_sections(user: User = Depends(get_current_user)) -> list[SectionOut]:
    """Menyu bandlari — tartiblangan.

    ⚠️ Bu RUXSAT ro'yxati EMAS, navigatsiya ro'yxati. Bo'limni yashirish
    qulaylik uchun; haqiqiy tekshiruv har endpointning o'zida."""
    return [
        SectionOut(
            key=s.key,
            label=s.label,
            path=s.path,
            icon=s.icon,
            order=s.order,
            audience=s.audience,
            group=s.group,
            bot_button=s.bot_button,
            exact=s.exact,
        )
        for s in sections_for(user)
    ]
