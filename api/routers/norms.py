from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, is_superadmin, require_roles, verify_bot_secret
from api.timeutil import today_local
from api.schemas import NormBotUpdate, NormCreate, NormOut, TeamNormRow, UserOut
from db.models import AuditLog, Norm, Role, User

router = APIRouter(prefix="/norms", tags=["norms"])

# Barcha qo'llab-quvvatlanadigan ko'rsatkichlar. "oddiy_video"/"dumaloq_video" —
# mobilograf kabi lavozimlar uchun: kunlik tasdiqlangan videolar soni (turi bo'yicha
# alohida — MobilografVideo.video_type dan hisoblanadi).
METRIC_LABELS = {
    "suhbat": "Suhbatlar soni",
    "tashrif": "Tashriflar soni",
    "oddiy_video": "Oddiy videolar soni",
    "dumaloq_video": "Dumaloq (doira) videolar soni",
}

# Norma/hisob metrikasi kalitidan MobilografVideo.video_type qiymatiga moslash.
VIDEO_METRIC_TYPES = {"oddiy_video": "oddiy", "dumaloq_video": "dumaloq"}


def metrics_for(user: User) -> list[str]:
    """Xodim lavozimiga BIRIKTIRILGAN ko'rsatkichlar (boshqa hech qanaqasi emas).

    QOIDA (2026-08-14, egasining talabi): ko'rsatkich FAQAT lavozimga ataylab
    biriktirilgan bo'lsa chiqadi. Lavozim yo'q yoki lavozimda ko'rsatkich
    sozlanmagan bo'lsa — BO'SH ro'yxat.

    NEGA STANDART TO'PLAM OLIB TASHLANDI: ilgari lavozimi yo'q yoki ko'rsatkichi
    sozlanmagan xodimga avtomatik "Suhbatlar soni"+"Tashriflar soni" berilardi.
    Natijada mansabi butunlay boshqa xodimlarda (bugalter, kassir, prorab
    yordamchisi, hali lavozimi belgilanmaganlar) sotuvga oid ko'rsatkichlar
    chiqib turardi — ular bu ish bilan shug'ullanmaydi.

    XAVFSIZLIK: jonli bazada (2026-08-14) lavozim ro'yxatida yo'q ko'rsatkich
    uchun qo'yilgan norma TOPILMADI (0 qator), ya'ni bu o'zgarish hech kimning
    mavjud normasini ko'rinmas qilib qo'ymaydi."""
    position = user.position
    if position is None or position.metrics is None:
        return []
    return [m for m in position.metrics if m in METRIC_LABELS]


def is_orphan_employee(target: User) -> bool:
    """"Yetim" xodim: na bevosita rahbari (manager_id), na boshqaruvchi-rol
    biriktirilgan lavozimi bor — uni ROP scope ham, lavozim matritsasi ham qamrab
    olmaydi. Bunday xodimlarni zaxira sifatida HR boshqaradi (aks holda faqat
    Boshliq/Dasturchi ko'rar edi)."""
    position = target.position
    return target.manager_id is None and not (position and position.managed_by_roles)


def can_manage_norms(actor: User, target: User) -> bool:
    """Norma belgilash matritsasi (vazifa matritsasi bilan bir xil mantiq):
    Boshliq/Dasturchi — barcha xodimlarga; ROP — o'z jamoasiga (manager_id) yoki
    lavozimi "ROP boshqaradi" deb belgilangan xodimlarga; HR — lavozimi
    "HR boshqaradi" deb belgilangan xodimlarga, hamda zaxira sifatida "yetim"
    (rahbarsiz va boshqaruvchi-rolsiz) xodimlarga.

    Bosqich 3.5 (Dasturchi rejimi): superadmin `target.role != employee`
    tekshiruvidan HAM OLDIN — Dasturchi HR/ROP/Boss'ga ham norma qo'ya oladi
    (11.4-band QAROR). Odatdagi (Dasturchi bo'lmagan) yo'l o'zgarmagan."""
    if is_superadmin(actor):
        return True
    if target.role != Role.employee.value or not target.is_active:
        return False
    if actor.role in {Role.boss.value, Role.dasturchi.value}:
        return True
    if actor.role == Role.rop.value:
        if target.manager_id == actor.id:
            return True
        position = target.position
        return bool(position and position.managed_by_roles and Role.rop.value in position.managed_by_roles)
    if actor.role == Role.hr.value:
        position = target.position
        if position and position.managed_by_roles and Role.hr.value in position.managed_by_roles:
            return True
        return is_orphan_employee(target)
    return False


async def _current_value(db: AsyncSession, user_id: int, metric_type: str) -> int | None:
    norm = await db.scalar(
        select(Norm)
        .where(Norm.user_id == user_id, Norm.metric_type == metric_type, Norm.deleted_at.is_(None))
        .order_by(Norm.effective_from.desc(), Norm.created_at.desc())
        .limit(1)
    )
    return norm.value if norm else None


async def _create_norm(db: AsyncSession, actor: User, target_user: User, metric_type: str, value: int) -> Norm:
    before = await _current_value(db, target_user.id, metric_type)

    norm = Norm(
        user_id=target_user.id,
        metric_type=metric_type,
        value=value,
        changed_by=actor.id,
        effective_from=today_local(),
    )
    db.add(norm)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="norm_changed",
            target_user_id=target_user.id,
            before={"metric_type": metric_type, "value": before},
            after={"metric_type": metric_type, "value": value},
        )
    )
    await db.commit()
    await db.refresh(norm)
    return norm


def _validate_metric(target: User, metric_type: str, actor: User | None = None) -> None:
    """Lavozim metrika cheklovi. Bosqich 3.5: Dasturchi bu cheklovdan HAM
    o'tkaziladi (11.4-band QAROR) — masalan sinov uchun lavozimida yo'q
    ko'rsatkichga vaqtincha norma qo'yish kerak bo'lganda. Odatdagi yo'lda
    `actor=None` — o'zgarish yo'q."""
    if actor is not None and is_superadmin(actor):
        return
    allowed = metrics_for(target)
    if not allowed:
        # Ilgari bu holatda "Mavjud: " deb BO'SH ro'yxat bilan xabar chiqardi —
        # foydalanuvchi nima qilishini bilmasdi. Endi aniq yo'l ko'rsatiladi.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu xodimning lavozimiga ko'rsatkich biriktirilmagan — avval "
            "«Lavozimlar» bo'limidan lavozimga ko'rsatkich qo'shing "
            "(yoki xodimga lavozim belgilang).",
        )
    if metric_type not in allowed:
        labels = ", ".join(METRIC_LABELS.get(m, m) for m in allowed)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Bu xodimning lavozimi uchun bunday ko'rsatkich kuzatilmaydi. Mavjud: {labels}",
        )


@router.get("/team", response_model=list[TeamNormRow])
async def team_norms(
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[TeamNormRow]:
    # Doiradan-tashqari import: api.routers.stats o'zi api.routers.norms'dan
    # METRIC_LABELS/metrics_for'ni import qiladi — modul darajasida import qilinsa
    # dumaloq (circular) import xatosiga olib keladi.
    from api.routers.stats import today_metric_rows

    query = select(User).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
    if actor.role == Role.rop.value:
        query = query.where(User.manager_id == actor.id)
    employees = list(await db.scalars(query.order_by(User.full_name)))

    rows = []
    for emp in employees:
        rows.append(
            TeamNormRow(
                user_id=emp.id,
                full_name=emp.full_name,
                position_name=emp.position.name if emp.position else None,
                can_edit=can_manage_norms(actor, emp),
                # Bugungi haqiqiy (CRM/qo'lda) qiymat + norma — shu API orqali
                # normani "tekshirish" imkonini beradi (bot bilan bir xil manba).
                metrics=await today_metric_rows(db, emp),
            )
        )
    return rows


@router.get(
    "/norm-targets/{telegram_id}", response_model=list[UserOut], dependencies=[Depends(verify_bot_secret)]
)
async def norm_targets(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[User]:
    """Bot `/norma_ozgartir` oqimi uchun: aktyor norma belgilay oladigan xodimlar."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or not actor.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    employees = list(
        await db.scalars(
            select(User)
            .where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
            .order_by(User.full_name)
        )
    )
    return [e for e in employees if can_manage_norms(actor, e)]


@router.post("", response_model=NormOut)
async def create_norm(
    payload: NormCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> Norm:
    target = await db.get(User, payload.user_id)
    # Bosqich 3.5 QAROR: Dasturchi xodim bo'lmaganlarga (hr/rop/boss) ham
    # norma qo'ya oladi — role tekshiruvi superadmin uchun o'tkazib yuboriladi.
    if not target or (target.role != Role.employee.value and not is_superadmin(actor)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimga norma belgilash huquqingiz yo'q")
    _validate_metric(target, payload.metric_type, actor)

    return await _create_norm(db, actor, target, payload.metric_type, payload.value)


@router.post("/bot-update", response_model=NormOut, dependencies=[Depends(verify_bot_secret)])
async def bot_update_norm(payload: NormBotUpdate, db: AsyncSession = Depends(get_db)) -> Norm:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.changer_telegram_id))
    if not actor or not actor.is_active or actor.role not in {Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    target = await db.get(User, payload.target_user_id)
    if not target or (target.role != Role.employee.value and not is_superadmin(actor)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")
    if not can_manage_norms(actor, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu xodimga norma belgilash huquqingiz yo'q")
    _validate_metric(target, payload.metric_type, actor)

    return await _create_norm(db, actor, target, payload.metric_type, payload.value)
