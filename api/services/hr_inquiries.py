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
    KnowledgeEntry,
    KnowledgeStatus,
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


# ═════════════════════════════════════════════════════════════
# S-29 · MUROJAATLAR → BILIM BAZASI HALQASI (TZ 3.29)
#
# Halqa: xodim so'raydi → HR javob beradi → javob bilim bazasiga
# ko'chiriladi → keyingi safar bot tayyor javobni O'ZI taklif qiladi.
#
# ⚠️ Bot javob O'YLAB TOPMAYDI — u HR yozgan va HR tasdiqlagan javobni
# qayta o'ynatadi. S-28 dagi «AI hukm chiqarmaydi» qoidasi kuchida.
#
# ⚠️ VA U JIMGINA JAVOB BERMAYDI, TAKLIF QILADI. Nega: o'zbekcha erkin
# matnni ishonchli solishtirish (qo'shimchalar, so'z tartibi, imlo)
# kichik bazada JUDA qiyin. O'lchab ko'rildi — «Noutbuk qachon
# beriladi» va «Oylik qachon beriladi» BIR XIL ball oldi, chunki ular
# umumiy fe'l bilan bog'langan va farq faqat MAVZU otida edi. Shuning
# uchun javob xodimga «shu savolga tayyor javob bor, to'g'ri keldimi?»
# ko'rinishida ko'rsatiladi va u tasdiqlaydi. Shunda noto'g'ri
# moslikning narxi — bitta ortiqcha bosish, xato RASMIY javob emas.
# Chegarani ham shu sababli past qo'yish mumkin: taklif ko'proq
# hollarda chiqadi va bot ko'proq foyda beradi.
# ═════════════════════════════════════════════════════════════

#  Savolning MAZMUNIGA hissa qo'shmaydigan so'zlar.
_STOP = frozenset({
    "va", "bilan", "uchun", "ham", "yoki", "lekin", "ammo", "shu", "bu",
    "men", "meni", "menga", "mening", "siz", "sizga", "sizning", "ular",
    "qanday", "qanaqa", "qachon", "qayer", "nima", "nechta", "necha", "nega",
    "kim", "qaysi", "mumkin", "bor", "yoq", "kerak", "edi", "iltimos",
    "salom", "deb",
})

#  Uzunidan qisqasiga — «larimizni» «lar» dan oldin kesilsin.
_SUFFIXES = (
    "larimizni", "laringizni", "larimizga", "laringizga",
    "larimiz", "laringiz", "larining", "laridan", "larida", "lariga",
    "larini", "larning", "lardan", "larga", "larda", "larni", "lari",
    "imizni", "ingizni", "imizga", "ingizga", "imiz", "ingiz",
    "iladimi", "adilar", "asizmi", "amanmi", "ayotgan",
    "yotgan", "moqchi", "iladi", "yapti", "sangiz", "arkan", "moqda",
    "gacha", "niki", "ning", "dagi",
    "aman", "asiz", "amiz", "ardi",
    "dan", "gan", "lar", "adi", "ydi", "sam",
    "ga", "da", "ni", "im", "si", "mi",
)


APOSTROFLAR = ("\u02bc", "\u2019", "`", "'")


def _norm(text: str) -> str:
    """Kichik harf, apostrofsiz, tinish belgisiz.

    Apostrof TASHLANADI (almashtirilmaydi): xodimlar «ta'til»,
    «tatil», «taʼtil» deb har xil yozadi va ular bitta so'z bo'lishi
    kerak."""
    past = (text or "").lower()
    for belgi in APOSTROFLAR:
        past = past.replace(belgi, "")
    return re.sub(r"[^a-z0-9\s]+", " ", past)


def _stem(word: str, min_len: int = 4) -> str:
    """Qo'shimchalarni kesadi.

    Ko'pi bilan IKKI marta: o'zbekchada qo'shimchalar zanjirlanadi
    («kitob-lar-imiz-ni»), lekin cheksiz kesish o'zakni yeb qo'yardi.
    `min_len` — o'zak shundan qisqa bo'lib qolsa kesilmaydi."""
    for _ in range(2):
        for s in _SUFFIXES:
            if word.endswith(s) and len(word) - len(s) >= min_len:
                word = word[: -len(s)]
                break
        else:
            break
    return word


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _norm(text).split() if len(w) > 2 and w not in _STOP}


def _similarity(a: set[str], b: set[str]) -> float:
    """Jaccard o'xshashligi (kesishma / birlashma)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


#  Chegaralar 9 ta haqiqiy savol juftida O'LCHAB tanlangan (test:
#  `test_hr_knowledge_loop` shu juftlarni qo'riqlaydi).
#
#  Hisobotda ikki savolni BITTA qatorga qo'shish uchun kerakli ball.
#  Ataylab BALAND: past chegara turli savollarni birlashtirib, HR ga
#  «bu savol 9 marta berilgan» degan yolg'on son ko'rsatardi. Ortiqcha
#  ajratilgan ikki qator zararsiz, noto'g'ri birlashtirilgani esa yo'q.
#  O'lchov: 5 juftdan 3 tasi birlashdi, NOTO'G'RI birlashgan 0 ta.
_GROUP_MATCH = 0.5

#  Xodimga tayyor javobni TAKLIF QILISH chegarasi. Pastroq, chunki
#  xato taklifning narxi — bitta bosish (yuqoridagi izohga qarang).
#  O'lchov: 5 juftdan 4 tasi topildi, 1 ta ortiqcha taklif
#  («Noutbuk qachon beriladi» va «Oylik qachon beriladi» umumiy fe'l
#  tufayli). Aynan shu ortiqcha holat uchun tasdiq tugmasi bor.
_SUGGEST_MATCH = 0.3


async def frequent(db: AsyncSession, limit: int = 10) -> dict:
    """«Eng ko'p beriladigan savollar» hisoboti (TZ qabul mezoni).

    Ikki kesim qaytadi:
      • `categories` — qaysi toifa necha marta (TZ 1-band);
      • `questions` — o'xshash savollar guruhlangan TOP ro'yxat.

    Guruhlash bazada emas, shu yerda: SQL `group by question` faqat
    HARFMA-HARF bir xil matnni birlashtiradi, xodimlar esa bir savolni
    har xil yozadi («oylik qachon?» / «Oylikni qachon berasiz»)."""
    rows = list(
        await db.scalars(
            select(HrInquiry).order_by(HrInquiry.created_at.desc()).limit(1000)
        )
    )

    toifalar: dict[str, int] = {}
    for r in rows:
        toifalar[r.category] = toifalar.get(r.category, 0) + 1

    guruhlar: list[dict] = []
    for r in rows:
        imzo = _tokens(r.question)
        if not imzo:
            continue
        for g in guruhlar:
            if _similarity(imzo, g["_tokens"]) >= _GROUP_MATCH:
                g["count"] += 1
                if r.answer and not g["answer"]:
                    g["answer"] = r.answer
                    g["answered_id"] = r.id
                if r.knowledge_entry_id:
                    g["in_knowledge"] = True
                break
        else:
            guruhlar.append({
                #  Namuna — eng YANGI savol (ro'yxat sanaga teskari
                #  saralangan): HR bugungi ifodani ko'rsin.
                "sample": r.question,
                "count": 1,
                "category": r.category,
                "category_label": category_label(r.category),
                "answer": r.answer,
                "answered_id": r.id if r.answer else None,
                "in_knowledge": bool(r.knowledge_entry_id),
                #  ⚠️ Guruh imzosi O'SMAYDI (`|=` YO'Q). Har yangi savol
                #  imzoga qo'shilsa, guruh asta-sekin «hamma narsaga
                #  o'xshaydigan» bo'lib, keyingi savollarni bir-biriga
                #  aloqasi yo'q holda yutib yuborardi.
                "_tokens": imzo,
            })

    guruhlar.sort(key=lambda g: (-g["count"], g["sample"]))
    top = []
    for g in guruhlar[:limit]:
        g.pop("_tokens", None)
        top.append(g)
    return {
        "categories": [
            {"category": k, "label": category_label(k), "count": v}
            for k, v in sorted(toifalar.items(), key=lambda kv: -kv[1])
        ],
        "questions": top,
        "total": len(rows),
    }


async def to_knowledge(
    db: AsyncSession, *, inquiry: HrInquiry, actor_id: int
) -> KnowledgeEntry:
    """Javobni bilim bazasiga bir bosishda ko'chiradi (TZ 2-band).

    ⚠️ `audience="hr"` — MAJBURIY. Bu yozuv Sotuv AI promptiga ham,
    TASHQI chatbot datasetiga ham tushmasligi kerak: ichki qoida
    (oylik, jarima, intizom) mijozga ketmasin.

    Darhol `verified`: javobni HR ning o'zi yozgan va shu tugmani ham
    o'zi bosyapti — ikkinchi tasdiq bosqichi ma'nosiz bo'lardi."""
    if not inquiry.answer:
        raise ValueError("Javobsiz murojaatni bilim bazasiga ko'chirib bo'lmaydi")
    if inquiry.knowledge_entry_id:
        mavjud = await db.get(KnowledgeEntry, inquiry.knowledge_entry_id)
        if mavjud is not None:
            #  Tugma qayta bosilsa dublikat yaratilmaydi.
            return mavjud
    entry = KnowledgeEntry(
        kind="single",
        audience="hr",
        category=inquiry.category,
        question=inquiry.question.strip(),
        answer=inquiry.answer.strip(),
        status=KnowledgeStatus.verified.value,
        source="hr_inquiry",
        source_user_id=inquiry.user_id,
        verified_by=actor_id,
        verified_at=datetime.utcnow(),
    )
    db.add(entry)
    await db.flush()
    inquiry.knowledge_entry_id = entry.id
    await db.flush()
    return entry


async def suggest(
    db: AsyncSession, question: str
) -> tuple[KnowledgeEntry | None, float]:
    """Bilim bazasidan tayyor javob TAKLIF qiladi (TZ 3-band).

    AI CHAQIRILMAYDI: xodim javobni kutib turibdi va API tushib qolsa
    savol berish umuman ishlamay qolardi.

    Faqat `audience="hr"` yozuvlar — sotuv bazasidagi mijozga
    mo'ljallangan javob xodimga berilmasin.

    Qaytaradi: (yozuv, ball). Yozuv `None` bo'lsa mos javob yo'q."""
    imzo = _tokens(question)
    if not imzo:
        return None, 0.0
    nomzodlar = list(
        await db.scalars(
            select(KnowledgeEntry).where(
                KnowledgeEntry.audience == "hr",
                KnowledgeEntry.status == KnowledgeStatus.verified.value,
                #  Qayta ko'rish kutayotgan yozuv TAKLIF QILINMAYDI —
                #  u eskirgan bo'lishi mumkin deb belgilangan.
                KnowledgeEntry.needs_recheck.is_(False),
            )
        )
    )
    eng_yaxshi, eng_ball = None, 0.0
    for e in nomzodlar:
        ball = _similarity(imzo, _tokens(e.question))
        if ball > eng_ball:
            eng_yaxshi, eng_ball = e, ball
    if eng_ball < _SUGGEST_MATCH:
        return None, eng_ball
    return eng_yaxshi, eng_ball


async def accept_suggestion(
    db: AsyncSession, *, inquiry: HrInquiry, entry: KnowledgeEntry
) -> HrInquiry:
    """Xodim taklif qilingan javobni QABUL QILDI — murojaat yopiladi
    va HR umuman bezovta qilinmaydi.

    `auto_answered=True` bilan belgilanadi: HR bilim bazasi qanchalik
    ish berayotganini ko'rishi kerak, va takroriy savollar hisobotida
    bu savol ham sanalishi kerak — aks holda «bu savol endi
    berilmayapti» degan noto'g'ri xulosa chiqardi."""
    inquiry.answer = entry.answer
    inquiry.answered_at = datetime.utcnow()
    inquiry.status = HrInquiryStatus.answered.value
    inquiry.auto_answered = True
    inquiry.knowledge_entry_id = entry.id
    #  `answered_by` ATAYLAB bo'sh: javobni bu safar odam yozmadi.
    #  Kim yozganini bilish kerak bo'lsa `knowledge_entry_id` orqali
    #  asl yozuvning `verified_by` siga borish mumkin.
    await db.flush()
    return inquiry
