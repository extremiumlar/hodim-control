import hmac
from datetime import datetime, timedelta
from typing import AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status
from jwt import PyJWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.security import decode_access_token
from db.base import async_session
from db.models import LoginAttempt, Role, User


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kirish talab qilinadi")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token yaroqsiz")

    user = await db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Foydalanuvchi topilmadi")
    return user


def require_roles(*roles: str):
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
        return user

    return checker


def is_superadmin(user: User) -> bool:
    """Bosqich 3.5 (Dasturchi rejimi) — YAGONA DARVOZA. Har bir `can_manage_*`/
    matritsa funksiyasi eng boshida shuni tekshiradi va `True` bo'lsa darhol
    ruxsat beradi — cheklov mantig'i tarqoq bo'lib ketmasligi uchun."""
    return user.role == Role.dasturchi.value


# ─────────────────────────────────────────────────────────────
# KO'RINISH QAMROVI — markazlashgan qatlam (TZ 4-qism, S-06)
# ─────────────────────────────────────────────────────────────
# TZ ning istisnosiz qoidasi: «XODIM FAQAT O'ZIGA TEGISHLI MA'LUMOTNI
# KO'RADI». Ilgari bu qoida har endpointda QO'LDA yozilardi
# (`can_view_payroll`, `_visible_users`, `manager_id == actor.id` ...) —
# 10 dan ortiq joyda. Yangi modul qo'shilganda tekshiruvni unutish oson,
# unutilsa esa xato JIM: begona xodim ma'lumoti ko'rinib turaveradi.
#
# ⚠️ 404, 403 EMAS. 403 «yozuv BOR, lekin sizga ruxsat yo'q» degani —
# bu ham ma'lumot (masalan «bunday xodim bor»). TZ 4-qism buni ataylab
# taqiqlaydi.

VIEW_ALL_ROLES = {Role.hr.value, Role.boss.value, Role.dasturchi.value}


async def scoped_user_ids(
    actor: User, db: AsyncSession, *, rop_sees_team: bool = True
) -> set[int] | None:
    """`actor` ko'ra oladigan xodim ID lari. `None` — CHEKLOVSIZ (hammasi).

    Qamrov matritsasi (TZ 4-qism):
      • HR / Boshliq / Dasturchi → hammasi (`None`);
      • ROP → o'zi + jamoasi (bevosita `manager_id` yoki lavozimi
        «ROP boshqaradi» deb belgilangan xodimlar);
      • qolganlar → faqat o'zi.

    `rop_sees_team=False` — ROP bu modulda jamoasini ham KO'RMAYDI (faqat
    o'zini). TZ ba'zi modullarda aynan shuni talab qiladi (masalan kadr
    hujjatlari) — u yerda «rahbar ham begona» hisoblanadi.

    `None` va `{...}` farqi MUHIM: chaqiruvchi `None` ni «filtr qo'yma»
    deb tushunadi. Bo'sh to'plam qaytarilsa hech kim ko'rinmasdi."""
    if actor.role in VIEW_ALL_ROLES:
        return None
    if actor.role == Role.rop.value and rop_sees_team:
        #  ⚠️ QAMROV QOIDASI `api/services/hierarchy.py` DA — YAGONA
        #  MANBA (S-44). Ilgari shu yerda, `norms.can_manage_norms` da
        #  va `payroll.can_view_payroll` da uchta nusxa bor edi.
        #
        #  ⚠️ Endi butun SHOX: rahbarimning rahbari ham jamoani
        #  ko'radi. Ilgari faqat bevosita bo'ysunuvchilar sanalardi va
        #  ikki bo'g'in pastdagi xodim ko'rinmasdi.
        from api.services import hierarchy as _h

        rows = list(
            await db.scalars(
                select(User).where(User.role == Role.employee.value)
            )
        )
        zanjirlar = await _h.chain_map(db, [u.id for u in rows])
        team = {
            u.id
            for u in rows
            if _h.manages_with_chain(actor, u, zanjirlar.get(u.id, set()))
        }
        return team | {actor.id}
    return {actor.id}


async def assert_can_view(
    actor: User, target_user_id: int, db: AsyncSession, *, rop_sees_team: bool = True
) -> None:
    """Begona xodim so'ralsa 404 ko'taradi (topilmagandek).

    Endpointda BITTA qator: `await assert_can_view(actor, user_id, db)`."""
    allowed = await scoped_user_ids(actor, db, rop_sees_team=rop_sees_team)
    if allowed is not None and target_user_id not in allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")


async def require_dasturchi(user: User = Depends(get_current_user)) -> User:
    """`/admin/*` — cheklovsiz boshqaruv endpointlari FAQAT Dasturchi uchun."""
    if not is_superadmin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal faqat Dasturchi uchun")
    return user


async def verify_bot_secret(x_bot_secret: str | None = Header(default=None)) -> None:
    if not x_bot_secret or not hmac.compare_digest(x_bot_secret, settings.bot_shared_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bot autentifikatsiyasi muvaffaqiyatsiz")


def _client_identifier(request: Request) -> str:
    """Rate-limit uchun mijoz manzili.

    XAVFSIZLIK: `X-Forwarded-For` ning BIRINCHI qiymatini olish MUMKIN EMAS.
    nginx uni `$proxy_add_x_forwarded_for` bilan quradi, ya'ni MIJOZ yuborgan
    sarlavhaga o'z qiymatini QO'SHADI:

        mijoz yuboradi:  X-Forwarded-For: 1.2.3.4        (o'ylab topilgan)
        nginx qiladi:    X-Forwarded-For: 1.2.3.4, <haqiqiy IP>

    Ilgari birinchisi olinardi — demak hujumchi har so'rovda tasodifiy qiymat
    yozib, barcha rate-limit cheklovlarini bemalol aylanib o'tardi (va har
    so'rov `LoginAttempt` qatori yaratgani uchun bazani ham shishirardi).

    Shuning uchun OXIRIDAN sanaymiz: `trusted_proxy_count` — bizning
    proxy'larimiz soni, ya'ni oxirgi shuncha qiymatni faqat o'zimiz yozgan
    bo'lishimiz mumkin. Ro'yxat kutilganidan qisqa bo'lsa (mijoz sarlavhani
    umuman yubormagan) — eng chapdagi mavjud qiymat olinadi."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            idx = len(parts) - max(settings.trusted_proxy_count, 1)
            return parts[idx] if idx >= 0 else parts[0]
    return request.client.host if request.client else "unknown"


def rate_limit(endpoint: str, max_attempts: int, window_seconds: int):
    """So'rov chastotasini DB asosida cheklaydigan sliding-window dependency
    fabrikasi. Bu yerda himoyalanadigan endpointlar parol SO'RAMAYDI (Telegram
    Login Widget imzosi yoki tasodifiy bir martalik token) — demak bu
    BRUTE-FORCE HIMOYASI EMAS, faqat DoS/resurs himoyasi (xato konfiguratsiya
    yoki niyatli bombalash API'ni/bazani band qilib qo'ymasin).

    IP `X-Forwarded-For` headeridan olinadi, topilmasa `request.client.host`ga
    tushadi. DIQQAT: production'da (cPanel/nginx) bu header TO'G'RI uzatilishi
    SHART — aks holda barcha so'rovlar bitta manzildan kelayotgandek ko'rinib,
    bitta faol foydalanuvchi hammani bloklab qo'yishi mumkin."""

    async def checker(request: Request, db: AsyncSession = Depends(get_db)) -> None:
        identifier = _client_identifier(request)

        window_start = datetime.utcnow() - timedelta(seconds=window_seconds)
        count = await db.scalar(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.endpoint == endpoint,
                LoginAttempt.identifier == identifier,
                LoginAttempt.created_at >= window_start,
            )
        )
        if count and count >= max_attempts:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Juda ko'p urinish — birozdan keyin qayta urinib ko'ring"
            )

        db.add(LoginAttempt(endpoint=endpoint, identifier=identifier))
        await db.commit()

    return checker
