"""Muddat eslatmalari — yadro (yangi TZ 3.5 / S-12).

MUAMMO
──────
Sinov muddati, shartnoma muddati, tibbiy ko'rik, TX instruktaji — bularning
hammasi HR ning boshida va qog'oz kalendarida. Unutilsa oqibati huquqiy:
sinov muddati o'tib ketgan xodimni «sinovdan o'tmadi» deb bo'shatib
bo'lmaydi, muddati tugagan shartnoma esa avtomatik uzaytirilgan hisoblanadi.

IKKI XIL MUDDAT, BITTA RO'YXAT
──────────────────────────────
1. QO'LDA kiritilgani — HR sanani o'zi belgilaydi (tibbiy ko'rik, kurs).
2. HISOBLANADIGANI — sanasi boshqa joyda allaqachon bor:
      • sinov muddati  = `users.hire_date` + `probation_days`
      • hujjat muddati = `employee_documents.expires_at`

⚠️ HISOBLANADIGAN SANA JADVALGA YOZILMAYDI. Aks holda hujjatdagi sana
o'zgarganda nusxasi eskirib qolardi va tizim ikki xil muddat ko'rsatardi.
TZ buni aniq taqiqlaydi: «ikkita manba bo'lmasin». Jadvalda ular uchun
faqat «eslatma yuborildi» izi turadi va u ham faqat kerak bo'lganda
yaratiladi.

⚠️ `>=` SEMANTIKASI. Ro'yxatda PASTKI chegara yo'q: muddati o'tib ketgan
band ham yopilmaguncha ro'yxatda qoladi. Aks holda cron bir kun ishlamay
qolsa (server o'chgan, kvota to'lgan) o'sha kunga tushgan muddat abadiy
o'tkazib yuborilardi — bu modulning butun mazmunini yo'q qiladi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    DEADLINE_KIND_LABELS,
    Deadline,
    DeadlineConfig,
    DeadlineKind,
    DeadlineStatus,
    EmployeeDocument,
    User,
)

#  Hisoblanadigan muddat qaysi hujjat turidan chiqadi.
#  Shartnoma alohida turga aylanadi — u eng muhimi va xabarda
#  «Hujjat muddati» emas, «Shartnoma muddati» deb ko'rinishi kerak.
_DOC_KIND = {"contract": DeadlineKind.contract.value}


@dataclass(frozen=True)
class DeadlineItem:
    """Ro'yxatdagi bitta band — qo'lda kiritilgani ham, hisoblangani ham.

    `key` — barqaror belgi (`manual:12`, `document:5`, `probation:7`).
    S-13 shu kalit bo'yicha «bu bandga bugun eslatdikmi?» deb tekshiradi."""

    key: str
    user_id: int
    user_name: str
    kind: str
    kind_label: str
    due_date: date
    days_left: int
    responsible_role: str | None
    note: str | None
    #  Qo'lda kiritilgan band uchun `deadlines.id`. Hisoblangan bandda
    #  qator BO'LMASLIGI mumkin — birinchi eslatmagacha yaratilmaydi.
    row_id: int | None
    source_kind: str | None
    source_id: int | None
    reminded_at: date | None

    @property
    def is_overdue(self) -> bool:
        return self.days_left < 0


async def get_config(db: AsyncSession) -> DeadlineConfig:
    """Sozlama qatori — yo'q bo'lsa yaratiladi (`id=1`)."""
    cfg = await db.get(DeadlineConfig, 1)
    if cfg is None:
        cfg = DeadlineConfig(id=1)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


async def create(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    due_date: date,
    responsible_role: str | None = None,
    note: str | None = None,
    created_by: int | None = None,
) -> Deadline:
    """QO'LDA kiritilgan muddat. Hisoblanadigan turlar bu yerdan
    o'tmaydi — ular manbasidan chiqadi (chaqiruvchi tekshiradi)."""
    row = Deadline(
        user_id=user_id,
        kind=kind,
        due_date=due_date,
        responsible_role=responsible_role,
        note=note,
        created_by=created_by,
        status=DeadlineStatus.open.value,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def close(db: AsyncSession, deadline_id: int, *, cancelled: bool = False) -> bool:
    """Muddatni yopish — ro'yxatdan chiqadi va eslatma kelmaydi."""
    row = await db.get(Deadline, deadline_id)
    if row is None or row.status != DeadlineStatus.open.value:
        return False
    row.status = (
        DeadlineStatus.cancelled.value if cancelled else DeadlineStatus.done.value
    )
    await db.commit()
    return True


async def close_by_key(db: AsyncSession, key: str, *, cancelled: bool = True) -> bool:
    """Bandni KALIT bo'yicha yopish.

    NEGA KERAK: hisoblanadigan bandda (`document:5`, `probation:7`) iz
    qatori faqat birinchi eslatmadan keyin paydo bo'ladi. HR bandni
    eslatma kelishidan OLDIN yopmoqchi bo'lsa yopadigan qator yo'q edi
    — panelda tugma bosilardi-yu, hech narsa o'zgarmasdi. Bu yerda
    yopiq iz qatori DARHOL yaratiladi."""
    tur, _, xom = key.partition(":")
    if not xom.isdigit():
        return False
    obyekt_id = int(xom)

    if tur == "manual":
        return await close(db, obyekt_id, cancelled=cancelled)
    if tur not in ("document", "probation"):
        return False

    mavjud = await db.scalar(
        select(Deadline).where(
            Deadline.source_kind == tur, Deadline.source_id == obyekt_id
        )
    )
    if mavjud is not None:
        return await close(db, mavjud.id, cancelled=cancelled)

    #  Iz qatori hali yo'q — DARHOL yopiq holatda yaratamiz.
    #  `due_date` ATAYLAB bo'sh: sana manbada qoladi.
    if tur == "probation":
        user_id, kind = obyekt_id, DeadlineKind.probation.value
    else:
        doc = await db.get(EmployeeDocument, obyekt_id)
        if doc is None:
            return False
        user_id = doc.user_id
        kind = _DOC_KIND.get(doc.doc_type, DeadlineKind.document.value)

    db.add(
        Deadline(
            user_id=user_id, kind=kind, due_date=None,
            source_kind=tur, source_id=obyekt_id,
            status=(
                DeadlineStatus.cancelled.value if cancelled else DeadlineStatus.done.value
            ),
        )
    )
    await db.commit()
    return True


async def _traces(db: AsyncSession) -> dict[tuple[str, int], Deadline]:
    """Hisoblanadigan muddatlarning «eslatma izi» qatorlari.

    Kalit — `(source_kind, source_id)`. Yopilgan izlar ham keladi: ular
    bandni ro'yxatdan CHIQARADI (HR «bu muddat menga kerak emas» degan
    bo'lsa, hisoblanadigan bo'lgani uchun u qayta paydo bo'lmasligi kerak)."""
    rows = await db.scalars(
        select(Deadline).where(Deadline.source_kind.isnot(None))
    )
    return {(r.source_kind, r.source_id): r for r in rows if r.source_id is not None}


async def upcoming(db: AsyncSession, days: int | None = None) -> list[DeadlineItem]:
    """Yaqinlashayotgan (va O'TIB KETGAN) muddatlar — sanasi bo'yicha.

    `days` — necha kun oldindan. `None` bo'lsa sozlamadagi qiymat.

    PASTKI CHEGARA YO'Q (yuqoridagi `>=` izohiga qarang): o'tib ketgan
    muddat yopilmaguncha ro'yxatda qoladi."""
    cfg = await get_config(db)
    ufq = date.today() + timedelta(days=cfg.remind_days if days is None else days)

    users = {
        u.id: u
        for u in await db.scalars(select(User).where(User.is_active.is_(True)))
    }
    izlar = await _traces(db)
    bugun = date.today()
    out: list[DeadlineItem] = []

    def _qosh(
        key: str, user: User, kind: str, due: date, *,
        role: str | None, note: str | None, row: Deadline | None,
        source_kind: str | None, source_id: int | None,
    ) -> None:
        if due > ufq:
            return
        out.append(
            DeadlineItem(
                key=key,
                user_id=user.id,
                user_name=user.full_name,
                kind=kind,
                kind_label=DEADLINE_KIND_LABELS.get(kind, kind),
                due_date=due,
                days_left=(due - bugun).days,
                responsible_role=role,
                note=note,
                row_id=row.id if row is not None else None,
                source_kind=source_kind,
                source_id=source_id,
                reminded_at=row.reminded_at if row is not None else None,
            )
        )

    # ── 1) QO'LDA kiritilganlar ──
    qollar = await db.scalars(
        select(Deadline).where(
            Deadline.source_kind.is_(None),
            Deadline.status == DeadlineStatus.open.value,
            Deadline.due_date.isnot(None),
        )
    )
    for row in qollar:
        user = users.get(row.user_id)
        if user is None:  # xodim faolsizlangan — eslatma kerak emas
            continue
        _qosh(f"manual:{row.id}", user, row.kind, row.due_date,
              role=row.responsible_role, note=row.note, row=row,
              source_kind=None, source_id=None)

    # ── 2) HISOBLANADIGAN: sinov muddati ──
    for user in users.values():
        if not user.hire_date:
            continue
        iz = izlar.get(("probation", user.id))
        if iz is not None and iz.status != DeadlineStatus.open.value:
            continue
        _qosh(
            f"probation:{user.id}", user, DeadlineKind.probation.value,
            user.hire_date + timedelta(days=cfg.probation_days),
            role=iz.responsible_role if iz else None,
            note=iz.note if iz else None, row=iz,
            source_kind="probation", source_id=user.id,
        )

    # ── 3) HISOBLANADIGAN: hujjat muddatlari ──
    docs = await db.scalars(
        select(EmployeeDocument).where(
            EmployeeDocument.deleted_at.is_(None),
            EmployeeDocument.expires_at.isnot(None),
        )
    )
    for doc in docs:
        user = users.get(doc.user_id)
        if user is None:
            continue
        iz = izlar.get(("document", doc.id))
        if iz is not None and iz.status != DeadlineStatus.open.value:
            continue
        _qosh(
            f"document:{doc.id}", user,
            _DOC_KIND.get(doc.doc_type, DeadlineKind.document.value),
            doc.expires_at,
            role=iz.responsible_role if iz else None,
            note=iz.note if iz else doc.name, row=iz,
            source_kind="document", source_id=doc.id,
        )

    # Eng shoshilinchi (o'tib ketgan) birinchi.
    out.sort(key=lambda i: (i.due_date, i.user_name))
    return out


async def mark_reminded(db: AsyncSession, items: list[DeadlineItem], day: date) -> int:
    """«Bu bandlar bo'yicha bugun eslatildi» deb belgilaydi.

    Hisoblanadigan bandda qator hali bo'lmasligi mumkin — SHU YERDA
    yaratiladi. Ya'ni iz qatori faqat haqiqatan eslatma ketganda paydo
    bo'ladi, bo'sh jadval o'smaydi."""
    n = 0
    for item in items:
        row = await db.get(Deadline, item.row_id) if item.row_id else None
        if row is None:
            row = Deadline(
                user_id=item.user_id,
                kind=item.kind,
                #  ⚠️ `due_date` ATAYLAB yozilmaydi — sana manbada qoladi.
                due_date=None,
                source_kind=item.source_kind,
                source_id=item.source_id,
                status=DeadlineStatus.open.value,
            )
            db.add(row)
        row.reminded_at = day
        n += 1
    if n:
        await db.commit()
    return n
