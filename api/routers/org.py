"""Tashkiliy tuzilma — API (yangi TZ 3.16 / S-40).

⚠️ SERVER FAQAT MA'LUMOT BERADI (S-40 qabul mezoni). Sxema RASMI
serverda yaratilmaydi: rasm chizish Passenger ishchisini band qilardi
va konkurentlik = 1 bo'lgani uchun butun sayt kutib turardi. Brauzer
`nodes` + `parent_id` dan o'zi chizadi.

⚠️ Marshrut tartibi: so'zli yo'llar `/{position_id}` dan OLDIN
(S-28 da jonli uchragan tuzoq).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.services import org as svc
from sqlalchemy import select

from db.models import Position, Role, User

router = APIRouter(prefix="/org", tags=["org"])

#  ⚠️ BOT ENDPOINTLARI UCHUN SIR QO'RIQCHISI — MAJBURIY. Bu yo'llar
#  xodimni `telegram_id` bo'yicha topadi, ya'ni JWT yo'q. Sir
#  tekshirilmasa istalgan kishi begona `telegram_id` yuborib o'sha
#  xodimning yo'riqnomasini o'qiy va uning NOMIDAN «tanishdim»
#  bosib qo'ya olardi — tanishuv esa HUQUQIY qayd.
#  (Aynan shu qo'riqchi `courses`/`hr_inquiries`/`employee_documents`
#  da 17 ta yo'lda unutilgan edi — `77fd2d6`.)
_BOT_SIR = [Depends(verify_bot_secret)]

#  TAHRIRLASH — HR/Boshliq/Dasturchi.
_EDIT = (Role.hr.value, Role.boss.value, Role.dasturchi.value)


class ParentIn(BaseModel):
    parent_position_id: int | None = None


class DescriptionIn(BaseModel):
    purpose: str | None = None
    duties: list[str] = []
    rights: list[str] = []
    responsibility: list[str] = []
    requirements: list[str] = []
    effective_from: date | None = None


class ProfileIn(BaseModel):
    mission: str | None = None
    values: list[str] | None = None
    goals: list[str] | None = None


# ─────────────────────────────────────────────────────────────
# SO'ZLI MARSHRUTLAR
# ─────────────────────────────────────────────────────────────


#  «Bo'shliqlar» bo'limini KO'RISH — rahbarlar (ROP ham).
_VIEW_GAPS = (
    Role.hr.value,
    Role.boss.value,
    Role.dasturchi.value,
    Role.rop.value,
)


def _rahbarmi(user: User) -> bool:
    return user.role in _VIEW_GAPS


@router.get("/chart")
async def org_chart(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Sxema ma'lumoti — tugunlar, o'rinlar va bo'shliqlar.

    ⚠️ Rasm QAYTARILMAYDI, faqat ma'lumot. Chizishni brauzer
    qiladi (TZ 3.16).

    ⚠️ SXEMA HAMMAGA OCHIQ (TZ 3.16 / S-41 qabul mezoni) — xodim
    kompaniya qanday qurilganini va kimga bo'ysunishini bilishi
    kerak. Tugunlarda ISH HAQI ham, BAHO ham YO'Q.

    ⚠️ Lekin `gaps` — KADR REJALASHTIRISH ma'lumoti (yo'riqnomasiz
    lavozimlar, rahbari belgilanmagan xodimlar), u faqat rahbarga
    boradi.

    S-40 da butun endpoint rahbarga yopilgandi — bu TZ ga ZID edi.
    To'g'ri chegara endpoint emas, AYNAN SHU BO'LIM."""
    return await svc.chart(db, with_gaps=_rahbarmi(user))


@router.get("/my-place")
async def my_place(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """«Mening o'rnim»: rahbarim → men → menga bo'ysunadiganlar.

    Mobil ekranda sxema o'rniga shu ko'rsatiladi (S-40 qabul
    mezoni) — kichik ekranda butun daraxtni chizib bo'lmaydi."""
    return await svc.my_place(db, user)


class BotIn(BaseModel):
    telegram_id: int


#  ⚠️ BOT MARSHRUTLARI `/positions/{position_id}` DAN OLDIN. S-28 da
#  jonli uchragan tuzoq: `/bot/...` `/{id}` shaklidagi naqshga tushib
#  ketardi va bot 422 olardi.
async def _bot_user(db: AsyncSession, telegram_id: int) -> User:
    u = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return u


@router.get("/bot/my-place", dependencies=_BOT_SIR)
async def bot_my_place(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    return await svc.my_place(db, await _bot_user(db, telegram_id))


@router.post("/bot/acknowledge", dependencies=_BOT_SIR)
async def bot_acknowledge(
    payload: BotIn, db: AsyncSession = Depends(get_db)
) -> dict:
    """Botda «✅ Tanishdim» — sayt bilan BITTA mantiq."""
    return await _acknowledge(db, await _bot_user(db, payload.telegram_id))


@router.post("/my-place/acknowledge")
async def acknowledge_instruction(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    """Xodim O'Z lavozimi yo'riqnomasi bilan tanishdi (S-20 qaydi)."""
    return await _acknowledge(db, user)


async def _acknowledge(db: AsyncSession, user: User) -> dict:
    """Sayt va bot uchun YAGONA mantiq.

    ⚠️ Ikki adapter, bitta mantiq (loyiha naqshi): xodim botda
    tanishsa saytda ham tanishgan bo'lib turishi SHART, aks holda
    ikki joyda ikki xil holat paydo bo'lardi."""
    try:
        return await svc.acknowledge_instruction(db, user)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.get("/profile")
async def read_profile(
    _user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    p = await svc.get_profile(db)
    out = {
        "mission": p.mission,
        "values": p.values or [],
        "goals": p.goals or [],
        "updated_at": p.updated_at,
    }
    await db.commit()  # `get_profile` yangi qator yaratgan bo'lishi mumkin
    return out


@router.put("/profile")
async def write_profile(
    payload: ProfileIn,
    actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    p = await svc.update_profile(
        db,
        mission=payload.mission,
        values=payload.values,
        goals=payload.goals,
        actor_id=actor.id,
    )
    out = {"mission": p.mission, "values": p.values or [], "goals": p.goals or []}
    await db.commit()
    return out


# ─────────────────────────────────────────────────────────────
# LAVOZIM (id bilan)
# ─────────────────────────────────────────────────────────────


@router.get("/positions/{position_id}")
async def position_detail(
    position_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lavozim: kim ishlaydi, nechta o'rin, joriy yo'riqnoma.

    ⚠️ XODIM FAQAT O'Z LAVOZIMI yo'riqnomasini KO'RADI (TZ 3.16 /
    S-41 qabul mezoni). Begona lavozimda `description: null` qoladi,
    faqat `has_description` ko'rinadi.

    Lavozim NOMI va tarkibi yashirilmaydi — ular sxemada turibdi va
    TZ sxemani hammaga ochiq deydi. Yashiriladigan narsa — MATN:
    yo'riqnomada aniq bir odamning majburiyatlari va unga qo'yilgan
    talablar yozilgan."""
    ozi = _rahbarmi(user) or user.position_id == position_id
    res = await svc.position_detail(db, position_id, with_description=ozi)
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    return res


@router.put("/positions/{position_id}/parent")
async def set_parent(
    position_id: int,
    payload: ParentIn,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ota lavozimni belgilash.

    ⚠️ HALQA to'siladi (`org.assert_no_cycle`) — faqat o'ziga
    bo'ysunish emas, uzun aylana ham."""
    pos = await db.get(Position, position_id)
    if pos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    try:
        await svc.set_parent(db, position=pos, parent_id=payload.parent_position_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    await db.commit()
    return {"ok": True, "parent_position_id": payload.parent_position_id}


@router.get("/positions/{position_id}/descriptions")
async def list_descriptions(
    position_id: int,
    _actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """BARCHA versiyalar — eskisi ham qoladi va ko'rinadi."""
    return [
        {
            "id": j.id,
            "version": j.version,
            "purpose": j.purpose,
            "duties": j.duties or [],
            "rights": j.rights or [],
            "responsibility": j.responsibility or [],
            "requirements": j.requirements or [],
            "effective_from": j.effective_from,
            "created_at": j.created_at,
        }
        for j in await svc.versions(db, position_id)
    ]


@router.post("/positions/{position_id}/descriptions", status_code=status.HTTP_201_CREATED)
async def add_description(
    position_id: int,
    payload: DescriptionIn,
    actor: User = Depends(require_roles(*_EDIT)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """YANGI versiya qo'shadi.

    ⚠️ TAHRIRLASH ENDPOINTI YO'Q va bo'lmaydi (S-39 qoidasi):
    yo'riqnoma huquqiy hujjat, xodim «tanishdim» degan matn
    o'zgarmasligi kerak."""
    pos = await db.get(Position, position_id)
    if pos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lavozim topilmadi")
    j = await svc.add_version(
        db,
        position_id=position_id,
        purpose=payload.purpose,
        duties=payload.duties,
        rights=payload.rights,
        responsibility=payload.responsibility,
        requirements=payload.requirements,
        effective_from=payload.effective_from,
        created_by=actor.id,
    )
    out = {"id": j.id, "version": j.version, "effective_from": j.effective_from}
    await db.commit()
    return out
