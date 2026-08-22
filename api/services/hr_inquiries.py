"""Xodim murojaatlari jurnali — mantiq (yangi TZ 3.29 / S-28).

NEGA KERAK: xodimlar HR ga bir xil savolni qayta-qayta beradi, javoblar
esa HR ning shaxsiy yozishmalarida qolib ketadi. Natijada (a) bir savolga
ikki xodim ikki xil javob oladi, (b) «men so'ragandim, javob bermadingiz»
degan bahsni hal qilib bo'lmaydi, (c) qaysi mavzu ko'p so'ralishi
noma'lum — S-29 shu jurnal ustiga quriladi.

⚠️ AI HUKM CHIQARMAYDI. Bu yerdagi tasniflagich faqat TOIFANI taxmin
qiladi; javobni har doim odam yozadi. HR savoliga («oylik nega kam
tushdi?») avtomat javob bersa, u javob rasmiy pozitsiya sifatida qabul
qilinardi va xato qimmatga tushardi.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    HR_INQUIRY_CATEGORY_LABELS,
    HrInquiry,
    HrInquiryCategory,
    HrInquiryStatus,
    Role,
    User,
)

#  Savolning maksimal uzunligi. Telegram xabari 4096 ta belgi bo'lishi
#  mumkin, lekin murojaat — savol, insho emas; uzun matn HR panelida
#  o'qilmay qoladi.
MAX_QUESTION_LEN = 2000
MAX_ANSWER_LEN = 4000

#  Kalit so'zlar bo'yicha tasnif. Ataylab AI CHAQIRILMAYDI: tasnif
#  xodim savol yozayotgan payt, ya'ni kutish paytida bo'ladi. AI 2-5
#  soniya kutdirardi yoki API tushib qolsa savol UMUMAN yozilmay
#  qolardi — noto'g'ri toifadan ko'ra bu ancha yomon. Toifa xato
#  chiqsa HR bir bosishda to'g'irlaydi va bu hech narsani buzmaydi.
#
#  ⚠️ Kalit so'z SO'Z BOSHIDA turishi shart, lekin OXIRI ochiq. O'zbek
#  tili qo'shimchali: «ta'til» → «ta'tilga», «smena» → «smenam»,
#  «kechik» → «kechikdim». To'liq so'z chegarasi qo'yilsa bularning
#  BIRORTASI topilmasdi. So'z boshi sharti esa «ish» ning «kishi»
#  ichida topilishiga yo'l qo'ymaydi.
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        HrInquiryCategory.salary.value,
        (
            "oylik", "maosh", "ish haqi", "ish haqqi", "avans", "bonus", "premiya",
            "jarima", "ushlanma", "to'lov", "tolov", "kpi", "stavka", "pul",
        ),
    ),
    (
        HrInquiryCategory.vacation.value,
        (
            "ta'til", "tatil", "otpusk", "dam olish", "sababli", "bemor",
            "kasal", "bolnichniy", "ruxsat", "otgul",
        ),
    ),
    (
        HrInquiryCategory.documents.value,
        (
            "hujjat", "ma'lumotnoma", "malumotnoma", "spravka", "shartnoma",
            "buyruq", "nusxa", "pasport", "diplom", "sertifikat", "ariza",
        ),
    ),
    (
        HrInquiryCategory.schedule.value,
        (
            "jadval", "smena", "grafik", "navbatchilik", "kechik", "kelish vaqti",
            "ish vaqti", "soat", "davomat",
        ),
    ),
    (
        HrInquiryCategory.conditions.value,
        (
            "noutbuk", "kompyuter", "telefon", "stol", "kreslo", "jihoz",
            "internet", "ofis", "sharoit", "mol-mulk", "texnika",
            "sim karta", "sim-karta",
        ),
    ),
]


def _variants(word: str) -> tuple[str, ...]:
    """Kalit so'zning tovush o'zgarishli shakllari.

    O'zbekchada unli qo'shimcha oldidan oxirgi `k`→`g`, `q`→`g'` bo'lib
    yumshaydi: «grafik» → «grafigim», «buyruq» → «buyrug'i». So'z boshi
    bo'yicha qidiruv bunday shaklni topa olmaydi, chunki o'zak o'zgargan
    — shuning uchun yumshagan o'zakni ham ro'yxatga qo'shamiz."""
    if word.endswith("k"):
        return (word, word[:-1] + "g")
    if word.endswith("q"):
        return (word, word[:-1] + "g'")
    return (word,)


#  Qidiruv ro'yxati: har bir kalit so'z o'z shakllari bilan yoyiladi.
_EXPANDED: list[tuple[str, tuple[str, ...]]] = [
    (toifa, tuple(v for so in sozlar for v in _variants(so)))
    for toifa, sozlar in _KEYWORDS
]


def classify(text: str) -> str:
    """Savol matnidan toifani taxmin qiladi.

    Hech bir kalit so'z topilmasa `other` — «taxmin qilib» eng yaqin
    toifaga tiqib qo'yilmaydi. Noto'g'ri toifa HR ga savolni yashirib
    qo'yadi (u faqat «Oylik» filtriga qarasa), `other` esa ko'rinib
    turadi va to'g'irlanadi."""
    past = (text or "").lower().replace("ʼ", "'").replace("’", "'").replace("`", "'")
    for toifa, sozlar in _EXPANDED:
        for so in sozlar:
            #  So'z boshi: oldingi belgi harf yoki apostrof bo'lmasin.
            #  `\b` ishlatilmaydi — o'zbek apostrofi (`o'`, `g'`) uchun
            #  u so'z chegarasini noto'g'ri joyga qo'yadi.
            if re.search(rf"(?<![a-z']){re.escape(so)}", past):
                return toifa
    return HrInquiryCategory.other.value


def category_label(value: str) -> str:
    return HR_INQUIRY_CATEGORY_LABELS.get(value, value)


async def create(db: AsyncSession, *, user_id: int, question: str) -> HrInquiry:
    """Yangi murojaat. Toifa avtomatik qo'yiladi (`category_auto=True`)."""
    matn = (question or "").strip()
    if not matn:
        raise ValueError("Savol bo'sh")
    matn = matn[:MAX_QUESTION_LEN]
    toifa = classify(matn)
    row = HrInquiry(
        user_id=user_id,
        question=matn,
        category=toifa,
        #  Toifani mashina qo'ydi. HR o'zgartirsa `False` bo'ladi va
        #  S-29 da «tasniflagich qanchalik to'g'ri ishlayapti» degan
        #  savolga javob shu ustundan chiqadi.
        category_auto=True,
        status=HrInquiryStatus.open.value,
    )
    db.add(row)
    await db.flush()
    return row


async def answer(
    db: AsyncSession, *, inquiry: HrInquiry, text: str, actor_id: int
) -> HrInquiry:
    """Javob yozish. Qayta javob berish MUMKIN — HR birinchi javobini
    to'ldirishi yoki tuzatishi odatiy hol; jurnalda oxirgi javob qoladi.
    Javob bergan odam va vaqt har safar yangilanadi."""
    matn = (text or "").strip()
    if not matn:
        raise ValueError("Javob bo'sh")
    inquiry.answer = matn[:MAX_ANSWER_LEN]
    inquiry.answered_by = actor_id
    inquiry.answered_at = datetime.utcnow()
    inquiry.status = HrInquiryStatus.answered.value
    await db.flush()
    return inquiry


async def set_category(
    db: AsyncSession, *, inquiry: HrInquiry, category: str
) -> HrInquiry:
    if category not in {c.value for c in HrInquiryCategory}:
        raise ValueError("Noma'lum toifa")
    inquiry.category = category
    inquiry.category_auto = False
    await db.flush()
    return inquiry


async def close(db: AsyncSession, *, inquiry: HrInquiry) -> HrInquiry:
    """Javobsiz yopish — takroriy yoki ahamiyatsiz savol uchun.

    ⚠️ Javob berilgan murojaat yopilmaydi: `answered` allaqachon yakuniy
    holat va uni `closed` ga o'tkazish javobni jurnalda «bekor qilingan»
    ko'rinishga keltirardi."""
    if inquiry.status == HrInquiryStatus.answered.value:
        raise ValueError("Javob berilgan murojaat allaqachon yakunlangan")
    inquiry.status = HrInquiryStatus.closed.value
    await db.flush()
    return inquiry


async def for_user(db: AsyncSession, user_id: int, limit: int = 50) -> list[HrInquiry]:
    """Xodimning O'Z murojaatlari. Boshqa xodimniki HECH QACHON
    ko'rinmaydi — savollar ko'pincha shaxsiy (oylik, oilaviy sharoit)."""
    return list(
        await db.scalars(
            select(HrInquiry)
            .where(HrInquiry.user_id == user_id)
            .order_by(HrInquiry.created_at.desc())
            .limit(limit)
        )
    )


async def listing(
    db: AsyncSession,
    *,
    status: str | None = None,
    category: str | None = None,
    limit: int = 200,
) -> list[HrInquiry]:
    """HR ro'yxati. JAVOBSIZLAR HAR DOIM BIRINCHI (TZ qabul mezoni) —
    saralash sanaga qarab emas, avval holatga qarab bo'ladi, aks holda
    eski javobsiz savol yangi javoblar tagida ko'milib ketardi."""
    q = select(HrInquiry)
    if status:
        q = q.where(HrInquiry.status == status)
    if category:
        q = q.where(HrInquiry.category == category)
    #  `open` = 0, qolgani = 1 → javobsizlar tepada.
    tartib = case((HrInquiry.status == HrInquiryStatus.open.value, 0), else_=1)
    q = q.order_by(tartib.asc(), HrInquiry.created_at.desc()).limit(limit)
    return list(await db.scalars(q))


async def open_count(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count(HrInquiry.id)).where(
                HrInquiry.status == HrInquiryStatus.open.value
            )
        )
        or 0
    )


async def hr_recipients(db: AsyncSession) -> list[User]:
    """Murojaat kimga boradi.

    HR bo'lsa — HR ga. HR umuman yo'q bo'lsa (kichik kompaniya, HR
    ta'tilda emas — shtatda yo'q) BOSS ga boradi: aks holda savol
    hech kimga yetib bormay, jimgina bazada yotib qolardi."""
    hrlar = list(
        await db.scalars(
            select(User).where(User.role == Role.hr.value, User.is_active.is_(True))
        )
    )
    if hrlar:
        return hrlar
    return list(
        await db.scalars(
            select(User).where(User.role == Role.boss.value, User.is_active.is_(True))
        )
    )
