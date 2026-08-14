"""Arizalar — xodimning KELAJAKKA qaratilgan so'rovlari (ARIZALAR_REJASI.md).

`Appeal` (e'tiroz/shikoyat) dan TUB FARQI: u ataylab hech narsani
hisoblamaydi, bu esa tasdiqlanganda REAL o'zgarish yozadi. Turlari
oqibatiga qarab uch guruhga bo'linadi (modulning markaziy g'oyasi):

  A — davomatga:  vacation / unpaid / sick  → oraliqdagi har ISH kuniga
                  `ExcusedDay(approved)`. Shundan keyin davomat, jarima,
                  eslatma va digest AVTOMATIK to'g'ri ishlaydi — bitta qator
                  ham yangi hisob kodi yozilmaydi.
  B — pulga:      advance  → `PayrollAdjustment(category='advance',
                  status='pending')` → Boshliq tasdiqlaydi (mavjud oqim).
  C — qo'lda:     certificate / schedule_change / resignation / other →
                  tizim hech nima yozmaydi, HR ga «keyingi qadam» beriladi.

QAYTARISH: yozilgan qatorlar `source_request_id` bilan arizaga bog'lanadi,
bekor qilinganda aynan shular topib qaytariladi.

IKKI MARTA MATERIALIZATSIYAGA QARSHI (eng xavfli holat — pulga tegadi):
  1. holat o'tishi idempotent: `status not in OPEN` bo'lsa 400;
  2. `ExcusedDay` da UNIQUE(user_id, date) — takror yozuv `IntegrityError`;
  3. hammasi BITTA tranzaksiyada — yarim ta'til yozilib qolmaydi.
`SELECT ... FOR UPDATE` ATAYLAB ishlatilmaydi: SQLite (lokal dev) uni
umuman qo'llab-quvvatlamaydi (`OperationalError: near "for"`), ya'ni kafolat
faqat productionda ko'r-ko'rona yashardi va testlar yozib bo'lmasdi.
"""
import html
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.notify import notify_user
from api.schemas import (
    RequestActorBot,
    RequestBotCreate,
    RequestCalcOut,
    RequestCreateBase,
    RequestDecide,
    RequestDecideBot,
    RequestMeCreate,
    RequestOut,
    RequestRevoke,
    RequestSlaTick,
)
from api.services.attendance import recompute_attendance
from api.services.push import Category
from api.services.workdays import MAX_RANGE_DAYS, calc_range, human_summary, range_days
from api.telegram_notify import inline_keyboard, send_file_id
from api.timeutil import today_local
from db.models import (
    LEAVE_KINDS,
    MONEY_KINDS,
    REQUEST_OPEN_STATUSES,
    UNPAID_KINDS,
    Attendance,
    AuditLog,
    EmployeeRequest,
    ExcusedDay,
    ExcusedStatus,
    PayrollAdjustment,
    PayrollAdjustmentCategory,
    PayrollAdjustmentKind,
    PayrollAdjustmentStatus,
    PayrollPeriod,
    RequestKind,
    RequestStatus,
    Role,
    User,
)

router = APIRouter(prefix="/requests", tags=["requests"])

# Ariza ko'radigan/hal qiladigan rollar. ROP ataylab yo'q (Bosqich 4 da
# unga ALOHIDA «oldindan tasdiq» bosqichi beriladi, hal qilish emas).
MANAGE_ROLES = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

# Bir xodimda bir vaqtda ochiq ariza soni — e'tirozdagi 5 dan kamroq,
# chunki ariza og'irroq (real o'zgarish yozadi).
MAX_OPEN_PER_USER = 3

SLA_REMIND_DAYS = 3
SLA_ESCALATE_DAYS = 5

_KIND_LABELS = {
    RequestKind.vacation.value: "Mehnat ta'tili",
    RequestKind.unpaid.value: "O'z hisobidan ta'til",
    RequestKind.sick.value: "Kasallik",
    RequestKind.advance.value: "Avans",
    RequestKind.certificate.value: "Ma'lumotnoma",
    RequestKind.schedule_change.value: "Ish jadvalini o'zgartirish",
    RequestKind.resignation.value: "Ishdan bo'shash",
    RequestKind.other.value: "Boshqa",
}

# C guruh — tizim hech nima yozmaydi, HR qo'lda bajaradi. Qaror qabul
# qilinganda shu matn qaytariladi (Appeal'dagi `next_step` naqshi).
_NEXT_STEP = {
    RequestKind.certificate.value: (
        "Ma'lumotnomani tayyorlab, xodimga bering. Tizim hujjat yaratmaydi."
    ),
    RequestKind.schedule_change.value: (
        "«Ish jadvali» bo'limidan xodimning jadvalini o'zgartiring — "
        "tizim buni avtomatik qilmaydi (variantlar ko'p, xato xavfi yuqori)."
    ),
    RequestKind.resignation.value: (
        "Kadrlar jarayonini boshlang. Tizimda xodimni faqat oxirgi ish kunidan "
        "keyin «faolsiz» qiling — aks holda oylik hisobi buziladi."
    ),
    RequestKind.other.value: "Kelishilgan ishni bajaring — tizim hech nima yozmadi.",
}


def _to_out(item: EmployeeRequest, full_name: str | None, working_days: int | None = None) -> RequestOut:
    return RequestOut(
        id=item.id,
        user_id=item.user_id,
        user_full_name=full_name,
        kind=item.kind,
        start_date=item.start_date,
        end_date=item.end_date,
        amount=float(item.amount) if item.amount is not None else None,
        payload=item.payload,
        reason=item.reason,
        file_id=item.file_id,
        file_type=item.file_type,
        status=item.status,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        decision_note=item.decision_note,
        applied_at=item.applied_at,
        created_at=item.created_at,
        working_days=working_days,
    )


async def _to_out_many(items: list[EmployeeRequest], db: AsyncSession) -> list[RequestOut]:
    ids = {i.user_id for i in items}
    names = {
        u.id: u.full_name for u in await db.scalars(select(User).where(User.id.in_(ids or {0})))
    }
    return [_to_out(i, names.get(i.user_id)) for i in items]


async def _recipients(db: AsyncSession) -> list[User]:
    """Ariza kimga boradi: HR, yo'q bo'lsa Boshliq (excused_days naqshi —
    murojaat hech kimga bormay qolmasin)."""
    users = list(
        await db.scalars(
            select(User).where(
                User.role == Role.hr.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )
    if not users:
        users = list(
            await db.scalars(
                select(User).where(
                    User.role == Role.boss.value,
                    User.is_active.is_(True),
                    User.telegram_id.isnot(None),
                )
            )
        )
    return users


def _header(item: EmployeeRequest, author: str, extra: str = "") -> str:
    lines = [f"📄 <b>Ariza — {_KIND_LABELS.get(item.kind, item.kind)}</b>", f"Kimdan: {author}"]
    if item.start_date and item.end_date:
        lines.append(f"Muddat: {item.start_date} — {item.end_date}")
    if item.amount is not None:
        lines.append(f"Summa: {float(item.amount):,.0f}".replace(",", " "))
    if extra:
        lines.append(extra)
    lines.append("")
    lines.append(html.escape(item.reason))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Materializatsiya — ariza tasdiqlanganda REAL yozuvlar
# ─────────────────────────────────────────────────────────────


async def _apply(db: AsyncSession, item: EmployeeRequest, user: User) -> tuple[str | None, dict]:
    """Tasdiqlangan arizani tizimga yozadi. Qaytadi: (next_step, info).

    ⚠️ Chaqiruvchi TRANZAKSIYANI o'zi yakunlaydi (`commit`) — bu funksiya
    faqat `db.add`/`flush` qiladi, ya'ni bir necha kun yozilayotganda yarmida
    uzilib qolish holati bo'lmaydi."""
    if item.kind in LEAVE_KINDS:
        return None, await _apply_leave(db, item, user)
    if item.kind in MONEY_KINDS:
        return None, await _apply_advance(db, item, user)
    return _NEXT_STEP.get(item.kind), {}


async def _apply_leave(db: AsyncSession, item: EmployeeRequest, user: User) -> dict:
    """Oraliqdagi har ISH kuniga `ExcusedDay(approved)`.

    Dam olish kunlariga yozilmaydi — ular allaqachon ishlanmaydi va yozuv
    faqat shovqin qo'shardi (davomat kalendarida «sababli» bo'lib chiqardi).

    Mavjud sababli kun bo'lsa (xodim o'zi so'rab olgan) — TEGILMAYDI, chunki
    UNIQUE(user_id, date) baribir ruxsat bermaydi va eski yozuvni arizaga
    «o'g'irlab» qo'yish noto'g'ri bo'lardi (bekor qilinganda begona yozuv
    o'chib ketardi)."""
    days = await range_days(db, user, item.start_date, item.end_date)
    working = [d["date"] for d in days if d["is_working"]]

    existing = {
        e.date
        for e in await db.scalars(
            select(ExcusedDay).where(
                ExcusedDay.user_id == user.id,
                ExcusedDay.date >= item.start_date,
                ExcusedDay.date <= item.end_date,
            )
        )
    }

    is_paid = item.kind not in UNPAID_KINDS
    created = 0
    for day in working:
        if day in existing:
            continue
        db.add(
            ExcusedDay(
                user_id=user.id,
                date=day,
                reason=f"{_KIND_LABELS.get(item.kind, item.kind)} (ariza #{item.id})",
                status=ExcusedStatus.approved.value,
                decided_by=item.decided_by,
                decided_at=datetime.utcnow(),
                is_paid=is_paid,
                source_request_id=item.id,
            )
        )
        created += 1
    await db.flush()

    # Davomat yozuvi bor kunlarni qayta hisoblash — kun endi «sababli»,
    # ya'ni kechikish/jarima o'z-o'zidan tushadi.
    if working:
        atts = list(
            await db.scalars(
                select(Attendance).where(
                    Attendance.user_id == user.id,
                    Attendance.date >= item.start_date,
                    Attendance.date <= item.end_date,
                )
            )
        )
        for att in atts:
            await recompute_attendance(db, att, user)

    return {"excused_created": created, "working_days": len(working), "skipped": len(existing)}


async def _apply_advance(db: AsyncSession, item: EmployeeRequest, user: User) -> dict:
    """Avans → `PayrollAdjustment(pending)`. Boshliq tasdig'igacha oylikka
    KIRMAYDI — mavjud avans oqimi (payroll.py) o'z ishini davom ettiradi.

    Davr QULFLANGAN bo'lsa rad etiladi: qulflangan davrga yozuv qo'shilsa u
    hech qachon hisobga kirmasdi va «avans berildi-yu payslipda yo'q» degan
    chalkashlik chiqardi."""
    period = today_local().strftime("%Y-%m")
    period_row = await db.scalar(select(PayrollPeriod).where(PayrollPeriod.period == period))
    if period_row is not None and period_row.locked:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{period} davri qulflangan — avans hisobga kirmaydi. "
            "Avval Dasturchi davrni ochishi kerak.",
        )

    db.add(
        PayrollAdjustment(
            user_id=user.id,
            period=period,
            kind=PayrollAdjustmentKind.minus.value,
            category=PayrollAdjustmentCategory.advance.value,
            status=PayrollAdjustmentStatus.pending.value,
            amount=item.amount,
            reason=f"Ariza #{item.id}: {item.reason[:200]}",
            issued_on=today_local(),
            created_by=item.decided_by or user.id,
            source_request_id=item.id,
        )
    )
    await db.flush()
    return {"period": period, "amount": float(item.amount)}


async def _revert(db: AsyncSession, item: EmployeeRequest, user: User) -> dict:
    """Materializatsiyani QAYTARISH (`source_request_id` bo'yicha).

    - `ExcusedDay` → `rejected` (o'chirilmaydi: tarix qoladi va «nega bu kun
      sababli edi» savoliga javob bo'ladi) + davomatni qayta hisoblash
    - `PayrollAdjustment` → `pending` bo'lsa o'chiriladi; `approved` bo'lsa
      TEGILMAYDI (pul allaqachon berilgan bo'lishi mumkin) va chaqiruvchiga
      ogohlantirish qaytariladi
    """
    info: dict = {}

    excused = list(
        await db.scalars(select(ExcusedDay).where(ExcusedDay.source_request_id == item.id))
    )
    for e in excused:
        e.status = ExcusedStatus.rejected.value
    await db.flush()
    info["excused_reverted"] = len(excused)

    if excused:
        dates = [e.date for e in excused]
        atts = list(
            await db.scalars(
                select(Attendance).where(
                    Attendance.user_id == user.id, Attendance.date.in_(dates)
                )
            )
        )
        for att in atts:
            await recompute_attendance(db, att, user)

    adjustments = list(
        await db.scalars(
            select(PayrollAdjustment).where(PayrollAdjustment.source_request_id == item.id)
        )
    )
    removed, kept = 0, 0
    for adj in adjustments:
        if adj.status == PayrollAdjustmentStatus.approved.value:
            kept += 1
            continue
        await db.delete(adj)
        removed += 1
    info["advance_removed"] = removed
    if kept:
        info["warning"] = (
            f"{kept} ta avans allaqachon TASDIQLANGAN — u avtomatik qaytarilmadi. "
            "Kerak bo'lsa «Ish haqi» bo'limidan qo'lda o'chiring."
        )
    return info


# ─────────────────────────────────────────────────────────────
# Yaratish
# ─────────────────────────────────────────────────────────────


async def _create(db: AsyncSession, user: User, payload: RequestCreateBase) -> RequestOut:
    open_count = len(
        list(
            await db.scalars(
                select(EmployeeRequest).where(
                    EmployeeRequest.user_id == user.id,
                    EmployeeRequest.status.in_(REQUEST_OPEN_STATUSES),
                )
            )
        )
    )
    if open_count >= MAX_OPEN_PER_USER:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Sizda {open_count} ta ko'rib chiqilmagan ariza bor. "
            "Avval ular hal bo'lsin.",
        )

    working_days = None
    if payload.kind in LEAVE_KINDS:
        if (payload.end_date - payload.start_date).days + 1 > MAX_RANGE_DAYS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oraliq juda uzun")
        calc = await calc_range(db, user, payload.start_date, payload.end_date)
        working_days = calc["working_days"]
        if working_days == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Tanlangan oraliqda ish kuni yo'q (hammasi dam olish kuni).",
            )
        # To'qnashuv — BLOKLAMAYDI, chunki qisman ustma-ust tushish normal
        # (masalan bir kun kasallik, keyin ta'til). Faqat HR ko'rsin.
        if calc["conflict_dates"]:
            payload.payload = {
                **(payload.payload or {}),
                "conflict_dates": [d.isoformat() for d in calc["conflict_dates"]],
            }

    item = EmployeeRequest(
        user_id=user.id,
        kind=payload.kind,
        start_date=payload.start_date,
        end_date=payload.end_date,
        amount=payload.amount,
        payload=payload.payload,
        reason=payload.reason.strip(),
        file_id=payload.file_id,
        file_type=payload.file_type,
        # ⭐ Bosqich 4 uchun tarix: kim tasdiqlashi kerak edi.
        manager_id_at_creation=user.manager_id,
    )
    db.add(item)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=user.id,
            action="request_created",
            target_user_id=user.id,
            before=None,
            after={
                "id": item.id,
                "kind": item.kind,
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "end_date": item.end_date.isoformat() if item.end_date else None,
                "amount": float(item.amount) if item.amount is not None else None,
            },
        )
    )
    await db.commit()
    await db.refresh(item)

    extra = f"Ish kunlari: {working_days}" if working_days is not None else ""
    keyboard = inline_keyboard(
        [[("✅ Hal qilish", f"request_decide:{item.id}")]]
    )
    for rec in await _recipients(db):
        await notify_user(
            db, rec, Category.APPEALS, _header(item, user.full_name, extra),
            reply_markup=keyboard, force_telegram=True, data={"path": "/requests"},
        )
        if item.file_id and rec.telegram_id:
            await send_file_id(
                rec.telegram_id, item.file_id, item.file_type or "document",
                caption=f"📎 Ariza #{item.id} ilovasi",
            )

    return _to_out(item, user.full_name, working_days)


# ─────────────────────────────────────────────────────────────
# Xodim — bot adapterlari
# ─────────────────────────────────────────────────────────────


@router.post("/bot", response_model=RequestOut, dependencies=[Depends(verify_bot_secret)])
async def create_request_bot(payload: RequestBotCreate, db: AsyncSession = Depends(get_db)) -> RequestOut:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _create(db, user, payload)


@router.get(
    "/bot/my/{telegram_id}", response_model=list[RequestOut],
    dependencies=[Depends(verify_bot_secret)],
)
async def my_requests_bot(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[RequestOut]:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    items = list(
        await db.scalars(
            select(EmployeeRequest)
            .where(EmployeeRequest.user_id == user.id)
            .order_by(EmployeeRequest.created_at.desc())
            .limit(10)
        )
    )
    return [_to_out(i, user.full_name) for i in items]


@router.get(
    "/bot/calc/{telegram_id}", response_model=RequestCalcOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def calc_bot(
    telegram_id: int,
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> RequestCalcOut:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    return await _calc(db, user, start, end)


# ─────────────────────────────────────────────────────────────
# Xodim — web/JWT
# ─────────────────────────────────────────────────────────────


async def _calc(db: AsyncSession, user: User, start: str, end: str) -> RequestCalcOut:
    from datetime import date as _date

    try:
        s, e = _date.fromisoformat(start), _date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sana formati noto'g'ri (YYYY-MM-DD)")
    if e < s:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tugash sanasi boshidan oldin")
    if (e - s).days + 1 > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Oraliq juda uzun")
    calc = await calc_range(db, user, s, e)
    return RequestCalcOut(**calc, summary=human_summary(calc))


@router.get("/me/calc", response_model=RequestCalcOut)
async def calc_me(
    start: str = Query(...),
    end: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestCalcOut:
    """Ariza yuborishdan OLDIN: «10 kundan 8 tasi ish kuni»."""
    return await _calc(db, user, start, end)


@router.post("/me", response_model=RequestOut)
async def create_my_request(
    payload: RequestMeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestOut:
    return await _create(db, user, payload)


@router.get("/me", response_model=list[RequestOut])
async def list_my_requests(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[RequestOut]:
    items = list(
        await db.scalars(
            select(EmployeeRequest)
            .where(EmployeeRequest.user_id == user.id)
            .order_by(EmployeeRequest.created_at.desc())
            .limit(50)
        )
    )
    return [_to_out(i, user.full_name) for i in items]


async def _cancel(db: AsyncSession, item: EmployeeRequest, user: User) -> RequestOut:
    """Xodim O'ZI qaytarib oladi — faqat qaror chiqmagan bo'lsa.
    Tasdiqlangandan keyin faqat HR `revoke` qila oladi (yozuvlar qaytariladi)."""
    if item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    if item.status not in REQUEST_OPEN_STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu arizani qaytarib bo'lmaydi — u allaqachon hal qilingan.",
        )
    item.status = RequestStatus.cancelled.value
    db.add(
        AuditLog(
            actor_id=user.id, action="request_cancelled", target_user_id=user.id,
            before={"status": RequestStatus.pending.value}, after={"id": item.id},
        )
    )
    await db.commit()
    await db.refresh(item)
    return _to_out(item, user.full_name)


@router.post("/{item_id}/cancel", response_model=RequestOut)
async def cancel_my_request(
    item_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RequestOut:
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _cancel(db, item, user)


@router.post("/{item_id}/cancel/bot", response_model=RequestOut, dependencies=[Depends(verify_bot_secret)])
async def cancel_my_request_bot(
    item_id: int, payload: RequestActorBot, db: AsyncSession = Depends(get_db)
) -> RequestOut:
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _cancel(db, item, user)


# ─────────────────────────────────────────────────────────────
# Rahbar
# ─────────────────────────────────────────────────────────────


@router.get("", response_model=list[RequestOut])
async def list_requests(
    status_filter: str | None = None,
    kind: str | None = None,
    _actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[RequestOut]:
    query = select(EmployeeRequest).order_by(EmployeeRequest.created_at.desc())
    if status_filter:
        query = query.where(EmployeeRequest.status == status_filter)
    if kind:
        query = query.where(EmployeeRequest.kind == kind)
    return await _to_out_many(list(await db.scalars(query)), db)


async def _decide(
    db: AsyncSession, item: EmployeeRequest, actor: User, decision: str, note: str
) -> dict:
    # 1-himoya: idempotent holat o'tishi (ikki marta materializatsiyaga
    # qarshi ASOSIY to'siq — pulga tegadigan xato shu yerda to'xtaydi).
    if item.status not in REQUEST_OPEN_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu ariza allaqachon hal qilingan")

    target = await db.get(User, item.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    before_status = item.status
    item.status = decision
    item.decided_by = actor.id
    item.decided_at = datetime.utcnow()
    item.decision_note = note.strip()

    next_step, info = None, {}
    if decision == RequestStatus.approved.value:
        try:
            next_step, info = await _apply(db, item, target)
        except IntegrityError:
            # 2-himoya: UNIQUE(user_id, date) — parallel tasdiq yoki takroriy
            # yozuv. Tranzaksiya butunlay qaytariladi, yarim ta'til qolmaydi.
            await db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Bu kunlar uchun sababli kun allaqachon mavjud — arizani qayta tekshiring.",
            )
        item.applied_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="request_decided",
            target_user_id=item.user_id,
            before={"status": before_status},
            after={"id": item.id, "kind": item.kind, "status": item.status, "applied": info},
        )
    )
    # 3-himoya: hammasi BITTA commit — yozuvlar yo to'liq, yo umuman yo'q.
    await db.commit()
    await db.refresh(item)

    verdict = "✅ Arizangiz TASDIQLANDI" if decision == RequestStatus.approved.value else "❌ Arizangiz rad etildi"
    await notify_user(
        db, target, Category.DECISIONS,
        f"{verdict}\n{_KIND_LABELS.get(item.kind, item.kind)}\nIzoh: {html.escape(item.decision_note or '')}",
        data={"path": "/me/requests"},
    )

    out = _to_out(item, target.full_name)
    return {"request": out.model_dump(mode="json"), "next_step": next_step, "applied": info}


@router.post("/{item_id}/decide")
async def decide_request(
    item_id: int,
    payload: RequestDecide,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _decide(db, item, actor, payload.decision, payload.note)


@router.post("/{item_id}/decide/bot", dependencies=[Depends(verify_bot_secret)])
async def decide_request_bot(
    item_id: int, payload: RequestDecideBot, db: AsyncSession = Depends(get_db)
) -> dict:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not actor or not actor.is_active or actor.role not in MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _decide(db, item, actor, payload.decision, payload.note)


@router.post("/{item_id}/revoke")
async def revoke_request(
    item_id: int,
    payload: RequestRevoke,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tasdiqlangan arizani BEKOR qilish — yozilgan qatorlar qaytariladi.

    Nega kerak: ta'til tasdiqlangach reja o'zgarishi mumkin. Iz
    (`source_request_id`) bo'lmasa HR o'sha 10 ta sababli kunni qo'lda
    qidirardi va albatta bittasini unutardi."""
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    if item.status != RequestStatus.approved.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Faqat TASDIQLANGAN arizani bekor qilish mumkin"
        )

    target = await db.get(User, item.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    info = await _revert(db, item, target)
    item.status = RequestStatus.revoked.value
    item.decision_note = f"{item.decision_note or ''}\n[Bekor qilindi] {payload.reason.strip()}".strip()

    db.add(
        AuditLog(
            actor_id=actor.id, action="request_revoked", target_user_id=item.user_id,
            before={"status": RequestStatus.approved.value},
            after={"id": item.id, "reason": payload.reason.strip(), "reverted": info},
        )
    )
    await db.commit()
    await db.refresh(item)

    await notify_user(
        db, target, Category.DECISIONS,
        f"↩️ Tasdiqlangan arizangiz bekor qilindi ({_KIND_LABELS.get(item.kind, item.kind)}).\n"
        f"Sabab: {html.escape(payload.reason.strip())}",
        data={"path": "/me/requests"},
    )

    out = _to_out(item, target.full_name)
    return {"request": out.model_dump(mode="json"), "reverted": info}


# ─────────────────────────────────────────────────────────────
# SLA (scheduler)
# ─────────────────────────────────────────────────────────────


@router.post("/sla-tick", dependencies=[Depends(verify_bot_secret)])
async def requests_sla_tick(payload: RequestSlaTick, db: AsyncSession = Depends(get_db)) -> dict:
    """Javobsiz arizalar: 3 kunda HR ga eslatma, 5 kunda Boshliqqa eskalatsiya.

    Mantiq `api/services/cron_jobs.py` da — cPanel cron uni SAYTGA so'rov
    yubormasdan, o'z jarayonida bajaradi (SAYT_QOTISHI_TAHLIL.md 4b). Bu
    endpoint Docker/scheduler rejimi va qo'lda `dry_run` tekshiruvi uchun."""
    from api.services.cron_jobs import requests_sla_tick as _tick

    return await _tick(db, dry_run=payload.dry_run)
