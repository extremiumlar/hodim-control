"""Ma'lumotnoma (spravka) generatsiyasi (yangi TZ 3.9 / S-17).

MUAMMO
──────
`certificate` ariza turi «C guruh»da edi: tizim hech nima yozmasdi, HR ga
«ma'lumotnomani o'zingiz tayyorlang» deb aytilardi. Amalda bu HR ning eng
tez-tez takrorlanadigan qo'l mehnati — oyiga o'nlab marta bir xil matn,
faqat ism va sana o'zgaradi. Endi ariza tasdiqlanishi bilan hujjat
S-14 mexanizmi orqali AVTOMATIK tayyorlanadi.

⚠️ HUJJAT RAQAMI TAKRORLANMAYDI (TZ qabul mezoni). Raqam rasmiy rekvizit:
ikkita hujjat bir xil raqam bilan chiqsa tashqi tashkilot ularni qalbaki
deb hisoblaydi. Unikallik BAZA darajasida (`certificates.number` UNIQUE);
kod darajasidagi «eng kattasi + 1» parallel tasdiqda ikkita bir xil raqam
berishi mumkin, shuning uchun `IntegrityError` da qayta uriniladi.

⚠️ O'RTACHA OYLIK FAQAT SO'RALGANDA (TZ qabul mezoni). Bu maxfiy
ma'lumot: bankka kerak, bog'chaga esa umuman kerak emas. So'ralmagan
bo'lsa hisoblanmaydi ham, hujjatga yozilmaydi ham.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CERTIFICATE_PURPOSE_LABELS,
    Certificate,
    DocumentTemplate,
    Payslip,
    Position,
    SalaryRate,
    User,
)

#  O'rtacha oylik necha oy bo'yicha hisoblanadi. Banklar odatda 6 oy
#  so'raydi; kamroq ishlagan xodimda bor oylar bo'yicha o'rtacha olinadi.
AVG_MONTHS = 6

#  Shablonda ishlatiladigan belgilar — HR shablon yozishdan oldin ko'radi.
CERTIFICATE_PLACEHOLDERS: dict[str, str] = {
    "raqam": "Hujjat raqami",
    "sana": "Berilgan sana",
    "fish": "Xodim F.I.Sh.",
    "lavozim": "Lavozimi",
    "ishga_qabul_sanasi": "Ishga qabul sanasi",
    "shartnoma_turi": "Shartnoma turi",
    "maqsad": "Maqsadi (bank / viza / bog'cha)",
    "ortacha_oylik": "O'rtacha oylik (faqat so'ralganda)",
    "ortacha_oylik_sozda": "O'rtacha oylik, bo'sh joy bilan",
}


async def next_number(db: AsyncSession, today: date) -> str:
    """Keyingi raqam: `2026/0001`. Yil boshida hisob qaytadan boshlanadi
    — rasmiy hujjat yuritishda odatiy amaliyot."""
    boshi = f"{today.year}/"
    oxirgi = await db.scalar(
        select(func.max(Certificate.number)).where(Certificate.number.like(f"{boshi}%"))
    )
    keyingi = 1
    if oxirgi:
        try:
            keyingi = int(str(oxirgi).split("/", 1)[1]) + 1
        except (IndexError, ValueError):
            keyingi = 1
    return f"{boshi}{keyingi:04d}"


async def average_salary(db: AsyncSession, user_id: int, today: date) -> Decimal | None:
    """Oxirgi `AVG_MONTHS` oylik payslip'lar bo'yicha o'rtacha SOF oylik.

    Payslip bo'lmasa (yangi xodim, oylik hali hisoblanmagan) amaldagi
    STAVKA qaytariladi — «ma'lumot yo'q» deb bo'sh qoldirish yomonroq,
    chunki bank uchun ma'lumotnoma shusiz umuman ma'nosiz."""
    chegara = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    boshlanish = chegara
    for _ in range(AVG_MONTHS - 1):
        boshlanish = (boshlanish - timedelta(days=1)).replace(day=1)

    qatorlar = list(
        await db.scalars(
            select(Payslip).where(
                Payslip.user_id == user_id,
                Payslip.period >= boshlanish.strftime("%Y-%m"),
                Payslip.period <= chegara.strftime("%Y-%m"),
            )
        )
    )
    if qatorlar:
        jami = sum(Decimal(str(p.net or 0)) for p in qatorlar)
        return (jami / len(qatorlar)).quantize(Decimal("1"))

    stavka = await db.scalar(
        select(SalaryRate)
        .where(
            SalaryRate.user_id == user_id,
            SalaryRate.deleted_at.is_(None),
            SalaryRate.effective_from <= today,
        )
        .order_by(SalaryRate.effective_from.desc())
        .limit(1)
    )
    return Decimal(str(stavka.amount)) if stavka is not None else None


async def build_values(
    db: AsyncSession,
    user: User,
    *,
    number: str,
    purpose: str,
    today: date,
    avg: Decimal | None,
) -> dict[str, str]:
    """Shablonga uzatiladigan qiymatlar.

    ⚠️ `ortacha_oylik` so'ralmagan bo'lsa BO'SH satr — shablonda belgi
    qolib ketmasin, lekin raqam ham chiqmasin."""
    lavozim = ""
    if user.position_id:
        pos = await db.get(Position, user.position_id)
        lavozim = pos.name if pos else ""

    return {
        "raqam": number,
        "sana": today.isoformat(),
        "fish": user.full_name,
        "lavozim": lavozim,
        "ishga_qabul_sanasi": user.hire_date.isoformat() if user.hire_date else "",
        #  Shartnoma turi hozir alohida maydonda yo'q — muddatsiz mehnat
        #  shartnomasi standart holat. Maydon paydo bo'lsa shu yer o'zgaradi.
        "shartnoma_turi": "Muddatsiz mehnat shartnomasi",
        "maqsad": CERTIFICATE_PURPOSE_LABELS.get(purpose, purpose),
        "ortacha_oylik": str(int(avg)) if avg is not None else "",
        "ortacha_oylik_sozda": f"{int(avg):,}".replace(",", " ") if avg is not None else "",
    }


async def find_template(db: AsyncSession, purpose: str) -> DocumentTemplate | None:
    """Maqsadga mos shablon.

    HAR MAQSADGA ALOHIDA shablon (TZ): nomida maqsad kaliti bo'lsa o'sha
    olinadi, aks holda umumiy `reference` shabloni. Topilmasa `None` —
    chaqiruvchi arizani BLOKLAMAYDI, faqat HR ga aytadi."""
    rows = list(
        await db.scalars(
            select(DocumentTemplate).where(
                DocumentTemplate.kind == "reference",
                DocumentTemplate.is_active.is_(True),
            )
        )
    )
    if not rows:
        return None
    for t in rows:
        if purpose in (t.name or "").lower():
            return t
    return rows[0]


async def issue(
    db: AsyncSession,
    *,
    user: User,
    purpose: str,
    include_salary: bool,
    today: date,
    issued_by: int | None,
    request_id: int | None = None,
) -> tuple[Certificate, DocumentTemplate | None]:
    """Ma'lumotnomani ro'yxatga oladi va (shablon bo'lsa) generatsiyani
    NAVBATGA qo'yadi.

    ⚠️ Chaqiruvchi COMMIT qiladi — ariza tasdig'i bilan bitta tranzaksiyada
    bo'lishi kerak: yarim holat (ariza tasdiqlangan, ma'lumotnoma yo'q)
    paydo bo'lmasin.

    Raqam UNIKAL: `IntegrityError` da qayta uriniladi (parallel tasdiq)."""
    from api.services.background_jobs import enqueue

    avg = await average_salary(db, user.id, today) if include_salary else None
    tmpl = await find_template(db, purpose)

    #  Raqamni bandlash — UNIQUE cheklovga urilsa keyingisini olamiz.
    #  5 urinish yetarli: real hayotda bir vaqtda ikkitadan ko'p
    #  ma'lumotnoma tasdiqlanmaydi.
    cert: Certificate | None = None
    for _ in range(5):
        raqam = await next_number(db, today)
        nomzod = Certificate(
            user_id=user.id,
            request_id=request_id,
            purpose=purpose,
            number=raqam,
            include_salary=include_salary,
            avg_salary=avg,
            template_id=tmpl.id if tmpl else None,
            issued_at=today,
            issued_by=issued_by,
        )
        db.add(nomzod)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue
        cert = nomzod
        break
    if cert is None:
        raise RuntimeError("Ma'lumotnoma raqamini bandlab bo'lmadi")

    if tmpl is not None:
        values = await build_values(
            db, user, number=cert.number, purpose=purpose, today=today, avg=avg
        )
        await enqueue(
            db,
            "document_render",
            {
                "template_id": tmpl.id,
                "values": values,
                "filename": f"malumotnoma_{cert.number.replace('/', '-')}",
                #  Ilgak shu kalitni ko'rib hujjatni kadr arxiviga yozadi.
                "certificate_id": cert.id,
            },
            #  Fayl XODIMNING o'ziga boradi — u so'ragan.
            user.id,
        )
    return cert, tmpl
