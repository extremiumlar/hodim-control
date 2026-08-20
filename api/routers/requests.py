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
  C — qo'lda:     schedule_change / resignation / other →
                  tizim hech nima yozmaydi, HR ga «keyingi qadam» beriladi.
  D — hujjat:     certificate → ma'lumotnoma AVTOMATIK tayyorlanadi
                  (yangi TZ 3.9 / S-17). Ilgari C guruhda edi.

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
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, scoped_user_ids, require_roles, verify_bot_secret
from api.notify import notify_user
from api.schemas import (
    LeaveBalanceOut,
    RequestActorBot,
    RequestBotCreate,
    RequestCalcOut,
    RequestCreateBase,
    RequestDecide,
    RequestDecideBot,
    RequestInterruptDecide,
    RequestInterruptDecideBot,
    RequestManagerDecide,
    RequestManagerDecideBot,
    RequestMeCreate,
    RequestOut,
    RequestRevoke,
    RequestSlaTick,
)
from api.services.advance import limit_for as advance_limit_for
from api.services.attendance import recompute_attendance
from api.services.push import Category
from api.services.workdays import (
    MAX_RANGE_DAYS,
    calc_range,
    human_summary,
    leave_balance,
    range_days,
    resolve_request_policy,
)
from api.telegram_notify import inline_keyboard, send_file_id
from api.timeutil import today_local
from db.models import (
    PAYROLL_COUNTED_STATUSES,
    CERTIFICATE_PURPOSE_LABELS,
    CertificatePurpose,
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
    PayrollAdjustmentSource,
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

# Ta'til normasi (kun/yil) — balans MASLAHAT sifatida ko'rsatiladi, arizani
# bloklamaydi (ARIZALAR_REJASI.md 3.4). Kelajakda `RequestPolicy` ga
# ko'chirilishi mumkin, hozircha bitta qiymat yetadi.
ANNUAL_LEAVE_DAYS = 21

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
        interrupted_at=item.interrupted_at,
        interrupt_decision=item.interrupt_decision,
    )


async def _to_out_many(items: list[EmployeeRequest], db: AsyncSession) -> list[RequestOut]:
    ids = {i.user_id for i in items}
    names = {
        u.id: u.full_name for u in await db.scalars(select(User).where(User.id.in_(ids or {0})))
    }
    return [_to_out(i, names.get(i.user_id)) for i in items]


async def _needs_boss(db: AsyncSession, item: EmployeeRequest, user: User) -> bool:
    """Chegaradan oshganda Boshliq tasdig'i ham kerakmi (Bosqich 4).

    Ta'tilda ISH KUNLARI bo'yicha o'lchanadi (kalendar kun emas): 10 kunlik
    oraliqning 5 tasi dam olish bo'lsa, u aslida 5 kunlik ta'til."""
    policy = await resolve_request_policy(db, user, item.kind)
    if policy is None:
        return False
    if item.amount is not None and policy.boss_threshold_amount is not None:
        return float(item.amount) > float(policy.boss_threshold_amount)
    if item.start_date and policy.boss_threshold_days is not None:
        days = await range_days(db, user, item.start_date, item.end_date or item.start_date)
        return sum(1 for d in days if d["is_working"]) > policy.boss_threshold_days
    return False


async def _bosses(db: AsyncSession) -> list[User]:
    return list(
        await db.scalars(
            select(User).where(
                User.role == Role.boss.value,
                User.is_active.is_(True),
                User.telegram_id.isnot(None),
            )
        )
    )


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
    if item.kind == RequestKind.certificate.value:
        return await _apply_certificate(db, item, user)
    return _NEXT_STEP.get(item.kind), {}


async def _apply_certificate(
    db: AsyncSession, item: EmployeeRequest, user: User
) -> tuple[str | None, dict]:
    """Ma'lumotnoma (yangi TZ 3.9 / S-17) — ilgari «C guruh» edi.

    Tasdiqlangan zahoti hujjat AVTOMATIK tayyorlanadi: raqam beriladi,
    generatsiya navbatga qo'yiladi, tayyor fayl xodimga boradi va kadr
    arxiviga yoziladi.

    Maqsad va «o'rtacha oylik kerakmi» — arizaning `payload` ida
    (xodim so'raganda tanlaydi). Bo'lmasa «boshqa», oyliksiz: o'rtacha
    oylik MAXFIY, so'ralmagan bo'lsa yozilmaydi (TZ qabul mezoni).

    ⚠️ Shablon yuklanmagan bo'lsa ariza BLOKLANMAYDI: raqam beriladi,
    arxivda iz qoladi, HR ga «shablon yo'q» deb aytiladi. Aks holda
    xodimning arizasi HR ning sozlamasi tufayli osilib qolardi."""
    from api.services import certificates as cert_svc

    payload = item.payload or {}
    maqsad = payload.get("purpose") or CertificatePurpose.other.value
    if maqsad not in CERTIFICATE_PURPOSE_LABELS:
        maqsad = CertificatePurpose.other.value
    oylik_kerak = bool(payload.get("include_salary"))

    cert, tmpl = await cert_svc.issue(
        db,
        user=user,
        purpose=maqsad,
        include_salary=oylik_kerak,
        today=today_local(),
        issued_by=item.decided_by,
        request_id=item.id,
    )
    info = {
        "certificate_id": cert.id,
        "number": cert.number,
        "purpose": maqsad,
        "include_salary": oylik_kerak,
    }
    if tmpl is None:
        return (
            f"Ma'lumotnoma raqami berildi: {cert.number}. "
            "Lekin «reference» turidagi hujjat shabloni yuklanmagan — "
            "hujjatni qo'lda tayyorlang yoki shablonni «Hujjat shablonlari» "
            "bo'limiga yuklang.",
            info,
        )
    return (
        f"Ma'lumotnoma {cert.number} tayyorlanmoqda — bir daqiqada "
        "xodimning Telegram'iga boradi va kadr arxiviga yoziladi.",
        info,
    )


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

    # ── Chegara tekshiruvi (Avans TZ A-03) ──
    # HR sahifasi bilan AYNAN bir xil qoida — aks holda chegarani ariza
    # yo'li bilan chetlab o'tish mumkin bo'lardi.
    #
    # Bu yerda «istisno» yo'li ATAYLAB yo'q: ariza tasdig'i oynasida sabab
    # so'raydigan maydon yo'q, izsiz istisno esa qoidani ma'nosiz qiladi.
    # Chindan ham chegaradan oshiq berish kerak bo'lsa — Boshliq «Ish haqi
    # → Avans» sahifasidan sabab bilan kiritadi.
    limit_info = await advance_limit_for(db, user, period=period)
    if float(item.amount) > limit_info.limit:
        if limit_info.limit <= 0:
            sabab = limit_info.reason or "chegara 0"
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Bu xodimga hozir avans berib bo'lmaydi ({sabab}). Ariza tasdiqlanmadi.",
            )
        # Raqam ALOHIDA formatlanadi: `.replace(",", " ")` ni butun matnga
        # qo'llash matndagi vergullarni ham yeb qo'yardi.
        ruxsat = f"{limit_info.limit:,.0f}".replace(",", " ")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"So'ralgan summa avans chegarasidan oshdi — ruxsat etilgan: {ruxsat} so'm. "
            "Chegaradan oshiq berish kerak bo'lsa, Boshliq «Ish haqi → Avans» "
            "sahifasidan sabab bilan kiritadi.",
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
            # HR ro'yxatida «ariza orqali» ko'rinsin — o'sha avansni qo'lda
            # takror kiritmasin (Avans TZ A-01).
            source=PayrollAdjustmentSource.request.value,
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
        # `issued` ham saqlanadi (A-04): pul allaqachon QO'LGA berilgan,
        # uni ariza bekor qilinganida jimgina o'chirish — yo'qolgan pul.
        if adj.status in PAYROLL_COUNTED_STATUSES:
            kept += 1
            continue
        await db.delete(adj)
        removed += 1
    info["advance_removed"] = removed
    if kept:
        info["warning"] = (
            f"{kept} ta avans allaqachon TASDIQLANGAN yoki TO'LANGAN — u avtomatik qaytarilmadi. "
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

    # ── Zanjir (Bosqich 4): avval BEVOSITA RAHBAR ──
    # Nega: ta'tilda birinchi «ha» aynan rahbardan kelishi kerak — u
    # jamoaning ish yukini biladi. Xodimda `manager_id` bo'lmasa yoki qoida
    # o'chirilgan bo'lsa bosqich o'tkazib yuboriladi (avvalgi xatti-harakat).
    policy = await resolve_request_policy(db, user, item.kind)
    manager = await db.get(User, user.manager_id) if user.manager_id else None
    to_manager = (
        policy is not None
        and policy.requires_manager
        and manager is not None
        and manager.is_active
        and manager.telegram_id is not None
    )

    if to_manager:
        await notify_user(
            db, manager, Category.APPEALS,
            _header(item, user.full_name, extra) + "\n\n<i>Sizning tasdig'ingiz kutilmoqda.</i>",
            reply_markup=inline_keyboard(
                [[("✅ Tasdiqlayman", f"request_mgr:{item.id}:1"),
                  ("❌ Rad etaman", f"request_mgr:{item.id}:0")]]
            ),
            force_telegram=True, data={"path": "/requests"},
        )
        if item.file_id and manager.telegram_id:
            await send_file_id(
                manager.telegram_id, item.file_id, item.file_type or "document",
                caption=f"📎 Ariza #{item.id} ilovasi",
            )
    else:
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


async def _manager_decide(
    db: AsyncSession, item: EmployeeRequest, actor: User, approve: bool, note: str
) -> RequestOut:
    """Bevosita rahbar (ROP) bosqichi — YAKUNIY qaror EMAS.

    Tasdiqlasa ariza HR ga o'tadi (`manager_ok`); rad etsa shu yerda
    to'xtaydi va HR ni umuman bezovta qilmaydi."""
    if item.status != RequestStatus.pending.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu ariza allaqachon ko'rib chiqilgan")
    # Faqat O'SHA xodimning rahbari (yoki boss/dasturchi — ular hamma joyda
    # o'tadi). ROP boshqa jamoaning arizasiga tegolmasin.
    target = await db.get(User, item.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    if actor.role not in (Role.boss.value, Role.dasturchi.value) and target.manager_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu ariza sizning jamoangizdan emas")

    item.manager_decided_by = actor.id
    item.manager_decided_at = datetime.utcnow()
    item.manager_note = note.strip() or None
    item.status = RequestStatus.manager_ok.value if approve else RequestStatus.rejected.value
    if not approve:
        item.decided_by = actor.id
        item.decided_at = datetime.utcnow()
        item.decision_note = f"[Rahbar rad etdi] {note.strip()}"

    db.add(
        AuditLog(
            actor_id=actor.id, action="request_manager_decided", target_user_id=item.user_id,
            before={"status": RequestStatus.pending.value},
            after={"id": item.id, "approve": approve, "status": item.status},
        )
    )
    await db.commit()
    await db.refresh(item)

    if approve:
        # Endi HR navbati — xabar zanjir bosqichini ham ko'rsatadi.
        head = _header(item, target.full_name, f"✅ Rahbar tasdiqladi: {actor.full_name}")
        for rec in await _recipients(db):
            await notify_user(
                db, rec, Category.APPEALS, head,
                reply_markup=inline_keyboard([[("✅ Hal qilish", f"request_decide:{item.id}")]]),
                force_telegram=True, data={"path": "/requests"},
            )
    else:
        await notify_user(
            db, target, Category.DECISIONS,
            f"❌ Arizangizni bevosita rahbaringiz rad etdi.\n"
            f"{_KIND_LABELS.get(item.kind, item.kind)}\nIzoh: {html.escape(item.manager_note or '')}",
            data={"path": "/me/requests"},
        )
    return _to_out(item, target.full_name)


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
    actor: User = Depends(require_roles(*MANAGE_ROLES, Role.rop.value)),
    db: AsyncSession = Depends(get_db),
) -> list[RequestOut]:
    """ROP ham ko'radi, lekin FAQAT o'z jamoasini — zanjirning rahbar
    qadami botdagina qolib ketmasin (Bosqich 4). Yakuniy qaror baribir
    unga berilmaydi: `decide` da `MANAGE_ROLES` tekshiriladi."""
    query = select(EmployeeRequest).order_by(EmployeeRequest.created_at.desc())
    if status_filter:
        query = query.where(EmployeeRequest.status == status_filter)
    if kind:
        query = query.where(EmployeeRequest.kind == kind)
    # S-06: markazlashgan qamrov.
    allowed = await scoped_user_ids(actor, db)
    if allowed is not None:
        query = query.where(EmployeeRequest.user_id.in_(allowed))
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
    # ── Boshliq chegarasi (Bosqich 4) ──
    # HR tasdiqlaganda ariza chegaradan oshgan bo'lsa, u DARHOL tasdiqlanmaydi:
    # `hr_ok` holatiga o'tadi va Boshliq navbati keladi. Boshliqning o'zi
    # (yoki Dasturchi) tasdiqlasa — yakuniy.
    if (
        decision == RequestStatus.approved.value
        and actor.role == Role.hr.value
        and item.status != RequestStatus.hr_ok.value
        and await _needs_boss(db, item, target)
    ):
        item.status = RequestStatus.hr_ok.value
        item.decided_by = actor.id
        item.decided_at = datetime.utcnow()
        item.decision_note = note.strip()
        db.add(
            AuditLog(
                actor_id=actor.id, action="request_hr_approved", target_user_id=item.user_id,
                before={"status": before_status},
                after={"id": item.id, "status": item.status},
            )
        )
        await db.commit()
        await db.refresh(item)

        head = _header(item, target.full_name, f"✅ HR tasdiqladi: {actor.full_name}")
        for boss in await _bosses(db):
            await notify_user(
                db, boss, Category.APPEALS,
                head + "\n\n<i>Chegaradan oshgan — yakuniy tasdiq sizda.</i>",
                reply_markup=inline_keyboard([[("✅ Hal qilish", f"request_decide:{item.id}")]]),
                force_telegram=True, data={"path": "/requests"},
            )
        out = _to_out(item, target.full_name)
        return {
            "request": out.model_dump(mode="json"),
            "next_step": "Chegaradan oshgan — yakuniy tasdiq Boshliqda. Xabar yuborildi.",
            "applied": {},
        }

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


@router.post("/{item_id}/manager-decide", response_model=RequestOut)
async def manager_decide_request(
    item_id: int,
    payload: RequestManagerDecide,
    actor: User = Depends(
        require_roles(Role.rop.value, Role.hr.value, Role.boss.value, Role.dasturchi.value)
    ),
    db: AsyncSession = Depends(get_db),
) -> RequestOut:
    """Bevosita rahbar bosqichi (Bosqich 4). ROP shu yerda qatnashadi —
    yakuniy qarorda esa yo'q (`MANAGE_ROLES`)."""
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _manager_decide(db, item, actor, payload.approve, payload.note)


@router.post("/{item_id}/manager-decide/bot", response_model=RequestOut, dependencies=[Depends(verify_bot_secret)])
async def manager_decide_request_bot(
    item_id: int, payload: RequestManagerDecideBot, db: AsyncSession = Depends(get_db)
) -> RequestOut:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    allowed = (Role.rop.value, Role.hr.value, Role.boss.value, Role.dasturchi.value)
    if not actor or not actor.is_active or actor.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _manager_decide(db, item, actor, payload.approve, payload.note)


@router.get("/me/balance", response_model=LeaveBalanceOut)
async def my_leave_balance(
    year: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveBalanceOut:
    """Ta'til balansi — MASLAHAT (arizani bloklamaydi, 3.4-band)."""
    y = year or today_local().year
    return LeaveBalanceOut(**await leave_balance(db, user, y, ANNUAL_LEAVE_DAYS))


@router.get("/balance/{user_id}", response_model=LeaveBalanceOut)
async def user_leave_balance(
    user_id: int,
    year: int | None = None,
    _actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> LeaveBalanceOut:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")
    y = year or today_local().year
    return LeaveBalanceOut(**await leave_balance(db, target, y, ANNUAL_LEAVE_DAYS))


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
# «Ishdagi ta'tilchi» (Bosqich 5)
# ─────────────────────────────────────────────────────────────


async def note_interruption(db: AsyncSession, user: User, day: date) -> EmployeeRequest | None:
    """Ta'til vaqtida ishga kelish faktini qayd etadi va HR dan QAROR so'raydi.

    NEGA OGOHLANTIRISH YETARLI EMAS (3.6/2.1): xodim ta'tildan chaqirib
    olinsa, qolgan kunlar tizimda «sababli» bo'lib turaveradi — bu oylikda
    va davomatda faqat oy oxirida bilinadi. Shuning uchun tizim HR ga aniq
    savol beradi: ta'til qisqartirilsinmi yoki davom etsinmi.

    NEGA `TaskModel` EMAS: u xodimga beriladigan ish topshirig'i va vazifa
    statistikasi/muddat nazoratiga kiradi — tizim xabarlari u yerga tushsa
    HR ning «bajarilmagan vazifalar» raqami buzilardi. O'rniga arizada iz
    (`interrupted_at`) + inline tugmali xabar + rahbar sahifasidagi badge.

    Chaqiriladi: `perform_check_in` dan keyin (davomat oqimini BLOKLAMAYDI).
    Iz `interrupted_at` bilan bir marta — har kelishda qayta so'ralmaydi."""
    item = await db.scalar(
        select(EmployeeRequest).where(
            EmployeeRequest.user_id == user.id,
            EmployeeRequest.status == RequestStatus.approved.value,
            EmployeeRequest.kind.in_(LEAVE_KINDS),
            EmployeeRequest.start_date <= day,
            EmployeeRequest.end_date >= day,
            EmployeeRequest.interrupted_at.is_(None),
        )
    )
    if item is None:
        return None

    item.interrupted_at = datetime.utcnow()
    item.interrupt_decision = "pending"
    db.add(
        AuditLog(
            actor_id=user.id, action="request_interrupted", target_user_id=user.id,
            before=None, after={"id": item.id, "date": day.isoformat()},
        )
    )
    await db.commit()
    await db.refresh(item)

    kb = inline_keyboard(
        [[("✂️ Qisqartirish", f"request_interrupt:{item.id}:cut"),
          ("▶️ Davom etsin", f"request_interrupt:{item.id}:keep")]]
    )
    for rec in await _recipients(db):
        await notify_user(
            db, rec, Category.APPEALS,
            f"🏖 <b>Ta'tildagi xodim ishga keldi</b>\n"
            f"{user.full_name} — {item.start_date} — {item.end_date}\n\n"
            f"Ta'tilning qolgan kunlari bekor qilinsinmi?",
            reply_markup=kb, force_telegram=True, data={"path": "/requests"},
        )
    return item


async def _resolve_interruption(
    db: AsyncSession, item: EmployeeRequest, actor: User, cut: bool
) -> dict:
    """HR qarori: ta'tilni QISQARTIRISH yoki davom ettirish.

    Qisqartirishda BUGUNDAN keyingi sababli kunlar `rejected` qilinadi va
    o'sha kunlar davomati qayta hisoblanadi. O'tgan kunlarga TEGILMAYDI —
    ular allaqachon ta'til edi."""
    if item.interrupt_decision != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu holat allaqachon hal qilingan")

    target = await db.get(User, item.user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Xodim topilmadi")

    info: dict = {}
    if cut:
        today = today_local()
        # Payroll qulfi — ta'tilni qisqartirish oylikka tegadi (sababli
        # kunlar kamayadi). Qulflangan davrda o'zgartirish jimgina
        # yo'qolardi, shuning uchun rad etamiz.
        period_row = await db.scalar(
            select(PayrollPeriod).where(PayrollPeriod.period == today.strftime("%Y-%m"))
        )
        if period_row is not None and period_row.locked:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Joriy davr qulflangan — qisqartirish oylikka kirmaydi. "
                "Avval Dasturchi davrni ochishi kerak.",
            )

        rows = list(
            await db.scalars(
                select(ExcusedDay).where(
                    ExcusedDay.source_request_id == item.id,
                    ExcusedDay.date >= today,
                    ExcusedDay.status == ExcusedStatus.approved.value,
                )
            )
        )
        for e in rows:
            e.status = ExcusedStatus.rejected.value
        await db.flush()
        if rows:
            atts = list(
                await db.scalars(
                    select(Attendance).where(
                        Attendance.user_id == target.id,
                        Attendance.date.in_([e.date for e in rows]),
                    )
                )
            )
            for att in atts:
                await recompute_attendance(db, att, target)
        # Ta'til oxiri kechagi kunga suriladi (tarixda ko'rinib tursin).
        item.end_date = today - timedelta(days=1)
        info = {"excused_cancelled": len(rows), "new_end_date": item.end_date.isoformat()}

    item.interrupt_decision = "shortened" if cut else "continued"
    db.add(
        AuditLog(
            actor_id=actor.id, action="request_interrupt_decided", target_user_id=item.user_id,
            before={"decision": "pending"},
            after={"id": item.id, "decision": item.interrupt_decision, **info},
        )
    )
    await db.commit()
    await db.refresh(item)

    text = (
        f"✂️ Ta'tilingiz qisqartirildi — {info.get('new_end_date')} gacha."
        if cut
        else "▶️ Ta'tilingiz davom etadi (ishga kelganingiz qayd etildi)."
    )
    await notify_user(db, target, Category.DECISIONS, text, data={"path": "/me/requests"})

    out = _to_out(item, target.full_name)
    return {"request": out.model_dump(mode="json"), "applied": info}


@router.post("/{item_id}/interrupt")
async def decide_interruption(
    item_id: int,
    payload: RequestInterruptDecide,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _resolve_interruption(db, item, actor, payload.cut)


@router.post("/{item_id}/interrupt/bot", dependencies=[Depends(verify_bot_secret)])
async def decide_interruption_bot(
    item_id: int, payload: RequestInterruptDecideBot, db: AsyncSession = Depends(get_db)
) -> dict:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not actor or not actor.is_active or actor.role not in MANAGE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")
    item = await db.get(EmployeeRequest, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ariza topilmadi")
    return await _resolve_interruption(db, item, actor, payload.cut)


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
