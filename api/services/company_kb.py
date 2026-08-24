"""Kompaniya ma'lumoti → bilim bazasi (yangi TZ 3.16 / S-43).

Missiya, qadriyatlar, maqsadlar va tashkiliy tuzilma mavjud bilim
bazasiga (`knowledge_entries`) `verified` holatida yoziladi. Shundan
keyin xodim «Missiyamiz nima?» deb so'rasa, S-29 dagi tayyor taklif
mexanizmi javobni O'ZI topadi va HR umuman bezovta bo'lmaydi.

═══════════════════════════════════════════════════════════════
⚠️ UCH QAT'IY QOIDA
═══════════════════════════════════════════════════════════════
1. YOZUVLAR `audience="hr"`. Bu MAXFIYLIK CHEGARASI (S-29):
   `sales` yozuvlar Sotuv AI promptiga VA tashqi chatbot
   datasetiga (`knowledge.build_dataset`) tushadi, ya'ni MIJOZGA
   ko'rinadi. Tuzilma esa ichki ma'lumot — kim kimga bo'ysunadi,
   qaysi lavozimda nechta odam bor. Buni mijozga chiqarish
   kompaniyaning ichki qurilishini oshkor qilardi.

   Missiya/qadriyatlar o'z-o'zicha sir emas, lekin ular ham `hr`
   qilib qo'yildi: ularni mijoz bazasiga chiqarish — ALOHIDA
   qaror va uni egasi qabul qilishi kerak. Kod jimgina qaror
   qabul qilmaydi.

2. ISH HAQI, BAHO VA SHAXSIY MA'LUMOT BU YOZUVLARGA
   TUSHMAYDI (TZ 3.16 qabul mezoni). Tuzilma matnida FAQAT
   lavozim nomlari va SONLAR bor — xodimlarning ismlari ham
   yozilmaydi: «kim qayerda ishlaydi» degan ro'yxat bilim
   bazasiga tushsa, u keyin AI javoblarida qalqib chiqardi.

3. TAKROR YOZUV YARATILMAYDI. Har band `source` markeri bilan
   belgilanadi va qayta sinxronlashda YANGILANADI. Aks holda
   HR profilni har tahrirlaganda bazada yangi nusxa paydo
   bo'lardi va `suggest` qaysi biri to'g'ri ekanini bilmasdi.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CompanyProfile,
    KnowledgeEntry,
    KnowledgeStatus,
    Position,
    User,
)

#  ⚠️ `source` — YOZUVNI QAYTA TOPISH KALITI. O'zgartirilsa eski
#  yozuvlar «yetim» bo'lib qoladi va yangi nusxa yaratiladi.
SOURCE_PREFIX = "kompaniya:"

CATEGORY = "kompaniya"


#  ⚠️ SAVOL MATNI — MOSLASHTIRISH KALITI, bezak emas. S-29 dagi
#  `suggest` xodimning savolini SHU matn bilan solishtiradi, shuning
#  uchun bu yerda ikki xil aytilish ataylab yoziladi.
#
#  NEGA KERAK: o'zbekcha qo'shimchalar yengil stemmerni chalg'itadi.
#  «missiyamiz» -> `missiy`, «missiyasi» -> `missiya` — bir harf farq
#  qiladi va mos kelmaydi (o'lchab ko'rildi: ball 0.0). Ya'ni xodim
#  «Missiyamiz nima?» deb so'rasa, «Kompaniyamizning missiyasi nima?»
#  degan yozuv TOPILMASDI va savol bekorga HR ga borardi.
#
#  Stemmerning o'ziga tegmadik: uning chegaralari S-28/S-29 da
#  HAQIQIY savol juftlarida o'lchangan va bu yerdagi bitta holat
#  uchun ularni qo'zg'atish boshqa modullardagi moslikni buzardi.
#  Bu yerda esa matn BIZNIKI — ikkala shaklni yozib qo'yish arzon
#  va xavfsiz.
def _band(kalit: str, savol: str, javob: str) -> dict:
    return {"source": f"{SOURCE_PREFIX}{kalit}", "question": savol, "answer": javob}


async def _structure_text(db: AsyncSession) -> str:
    """Tuzilmaning MATNLI tavsifi.

    ⚠️ ISM YO'Q, faqat lavozim va SON. «Kim qayerda ishlaydi»
    ro'yxati bilim bazasiga tushsa, u AI javoblarida qalqib
    chiqardi — bu shaxsiy ma'lumot."""
    lavozimlar = list(
        await db.scalars(
            select(Position).where(Position.is_active.is_(True)).order_by(Position.name)
        )
    )
    if not lavozimlar:
        return ""
    sanoq: dict[int, int] = {}
    for u in await db.scalars(select(User).where(User.is_active.is_(True))):
        if u.position_id:
            sanoq[u.position_id] = sanoq.get(u.position_id, 0) + 1
    nomlar = {p.id: p.name for p in lavozimlar}

    qatorlar = []
    for p in lavozimlar:
        qator = f"• {p.name}"
        ota = nomlar.get(p.parent_position_id) if p.parent_position_id else None
        if ota:
            qator += f" — bo'ysunadi: {ota}"
        n = sanoq.get(p.id, 0)
        if n:
            qator += f" ({n} xodim)"
        qatorlar.append(qator)
    return "Kompaniya lavozimlari va bo'ysunish tartibi:\n" + "\n".join(qatorlar)


async def build_entries(db: AsyncSession) -> list[dict]:
    """Yoziladigan bandlar. Bo'sh maydon uchun band YARATILMAYDI.

    ⚠️ Bo'sh maydonga band yaratish ZARARLI bo'lardi: xodim
    «Missiyamiz nima?» deb so'raganda bazadan BO'SH javob
    qaytardi va u «javob berildi» deb yopilardi. Kiritilmagan
    ma'lumot uchun javob YO'Q bo'lishi kerak — shunda savol HR ga
    boradi va `unknown` sifatida qayd etiladi (TZ 3.16)."""
    profil = await db.scalar(select(CompanyProfile).where(CompanyProfile.id == 1))
    bandlar: list[dict] = []

    if profil is not None and (profil.mission or "").strip():
        bandlar.append(
            _band("missiya", "Missiyamiz nima? (kompaniyaning missiyasi)", profil.mission.strip())
        )
    if profil is not None and (profil.values or []):
        bandlar.append(
            _band(
                "qadriyatlar",
                "Qadriyatlarimiz qanday? (kompaniyaning qadriyatlari)",
                "\n".join(f"• {v}" for v in profil.values),
            )
        )
    if profil is not None and (profil.goals or []):
        bandlar.append(
            _band(
                "maqsadlar",
                "Maqsadlarimiz nima? (kompaniyaning maqsadlari)",
                "\n".join(f"• {g}" for g in profil.goals),
            )
        )

    tuzilma = await _structure_text(db)
    if tuzilma:
        bandlar.append(_band("tuzilma", "Tuzilmamiz qanday? (kompaniya tuzilmasi, lavozimlar)", tuzilma))
    return bandlar


async def sync(db: AsyncSession) -> dict:
    """Bandlarni bazaga yozadi/yangilaydi. Chaqiruvchi COMMIT qiladi.

    ⚠️ ESKIRGAN BAND O'CHIRILADI: HR missiyani bo'shatsa, eski
    javob bazada qolib, xodimga hamon eski matn taklif qilinardi."""
    bandlar = await build_entries(db)
    kutilgan = {b["source"]: b for b in bandlar}

    mavjud = {
        e.source: e
        for e in await db.scalars(
            select(KnowledgeEntry).where(KnowledgeEntry.source.like(f"{SOURCE_PREFIX}%"))
        )
    }

    yaratildi = yangilandi = ochirildi = 0
    for source, band in kutilgan.items():
        e = mavjud.get(source)
        if e is None:
            db.add(
                KnowledgeEntry(
                    kind="single",
                    audience="hr",
                    category=CATEGORY,
                    question=band["question"],
                    answer=band["answer"],
                    #  Qo'lda kiritilgan yozuv kabi DARHOL verified:
                    #  manba HR ning o'zi to'ldirgan profil, ya'ni
                    #  tasdiqlashning ikkinchi bosqichi ortiqcha.
                    status=KnowledgeStatus.verified.value,
                    source=source,
                )
            )
            yaratildi += 1
        elif e.answer != band["answer"] or e.question != band["question"]:
            e.question = band["question"]
            e.answer = band["answer"]
            e.status = KnowledgeStatus.verified.value
            e.audience = "hr"
            #  Matn yangilandi — «qayta ko'rish» bayrog'i olib
            #  tashlanadi, aks holda yangi javob taklif qilinmasdi.
            e.needs_recheck = False
            yangilandi += 1

    for source, e in mavjud.items():
        if source not in kutilgan:
            await db.delete(e)
            ochirildi += 1

    await db.flush()
    return {
        "ok": True,
        "created": yaratildi,
        "updated": yangilandi,
        "deleted": ochirildi,
        "total": len(kutilgan),
    }
