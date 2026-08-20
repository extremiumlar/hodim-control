"""`.docx` shablonini to'ldirish — YANGI KUTUBXONASIZ (yangi TZ 3.3 / S-14).

NEGA KUTUBXONA YO'Q: `python-docx` va shunga o'xshashlar `lxml` ni tortadi,
u esa cPanel'da kompilyatsiya talab qiladi va disk kvotasi tor (1 GB).
`.docx` — oddiy ZIP arxiv, ichida `word/document.xml`. Bizga kerak bo'lgani
shu faylni ochib, belgilarni almashtirib, arxivni qayta yig'ish: `zipfile`
va `re` — ikkalasi ham standart kutubxonada.

⚠️ ASOSIY TUZOQ: WORD BELGINI BO'LIB YUBORADI
──────────────────────────────────────────────
Wordda `{{fish}}` deb yozganingizda fayl ichida u bitta joyda turmasligi
mumkin. Word matnni «run» (`<w:r>`) larga bo'ladi va bo'linish joyi
tasodifiy — imlo tekshiruvi, til belgisi, hatto kursorning qayerda
turgani ta'sir qiladi:

    <w:r><w:t>{{</w:t></w:r><w:r><w:t>fish</w:t></w:r><w:r><w:t>}}</w:t></w:r>

Oddiy `text.replace("{{fish}}", ...)` bunda HECH NARSA topmaydi — shablon
ko'zga to'g'ri ko'rinadi-yu, natija bo'sh chiqadi. Shuning uchun:

  1. har ABZATS (`<w:p>`) ichidagi barcha `<w:t>` matnlari BIRLASHTIRILADI;
  2. belgi birlashgan matnda qidiriladi;
  3. almashtirilgan matn run'larga QAYTA TAQSIMLANADI.

Formatlash saqlanadi: almashtirilgan qiymat belgi BOSHLANGAN run'ning
formatida qoladi (foydalanuvchi aynan shuni kutadi — u belgini o'sha
uslubda yozgan). Belgi qamragan qolgan run'lardan faqat belgi bo'lagi
o'chadi, ularning boshqa matni tegilmaydi.

⚠️ Shablon tayyorlangach BIR MARTA SINASH MAJBURIY (TZ talabi): Word
qanday bo'lganini oldindan bilib bo'lmaydi.
"""
from __future__ import annotations

import io
import re
import zipfile

#  Belgi ko'rinishi: {{nom}}. Nom — harf, raqam, pastki chiziq.
#  Ichida bo'sh joyga yo'l qo'yiladi ({{ nom }}) — Word ba'zan qo'shib
#  yuboradi va foydalanuvchi ham qo'lda yozadi.
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

#  Abzats va matn tegi. `re` ishlatiladi, XML parser emas: parser
#  hujjatni qayta yozganda Word tushunmaydigan nomlar maydoni (namespace)
#  qo'shib yuboradi va fayl ochilmay qoladi. Biz FAQAT matnni tegamiz.
_PARA = re.compile(rb"<w:p[ >].*?</w:p>", re.S)
_TEXT = re.compile(rb"(<w:t\b[^>]*>)(.*?)(</w:t>)", re.S)

#  Belgilar shu fayllarda qidiriladi. Sarlavha/kolontitul ham kerak:
#  shartnoma raqami odatda o'sha yerda turadi.
_TARGETS = re.compile(r"^word/(document|header\d*|footer\d*)\.xml$")


def _escape(value: str) -> str:
    """XML uchun xavfsiz matn.

    ⚠️ Bu SHART: xodim ismida `&` bo'lsa (masalan «Ali & Vali MCHJ»)
    almashtirilgan hujjat XML sifatida buzilib, Word uni «tuzatib
    bo'lmaydi» deb rad etardi."""
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _unescape(value: str) -> str:
    return (
        value.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    )


def _fill_paragraph(para: bytes, values: dict[str, str], used: set[str]) -> bytes:
    """Bitta abzatsdagi belgilarni almashtiradi (run'larga bo'linganini ham)."""
    parts = list(_TEXT.finditer(para))
    if not parts:
        return para

    matnlar = [_unescape(m.group(2).decode("utf-8")) for m in parts]
    birlashgan = "".join(matnlar)
    if "{{" not in birlashgan:
        return para

    topilgan = list(PLACEHOLDER.finditer(birlashgan))
    if not topilgan:
        return para

    #  Har run'ning birlashgan matndagi chegarasi.
    chegara: list[tuple[int, int]] = []
    pos = 0
    for t in matnlar:
        chegara.append((pos, pos + len(t)))
        pos += len(t)

    yangi = list(matnlar)
    #  TESKARI tartibda: yuqori indeksdagi o'zgarish pastdagi
    #  koordinatalarni buzmasin.
    for m in reversed(topilgan):
        nom = m.group(1)
        if nom not in values:
            #  Noma'lum belgi TEGILMAYDI — shablon xatosi ko'rinib tursin,
            #  jimgina bo'sh joyga aylanib ketmasin.
            continue
        used.add(nom)
        qiymat = values[nom]
        boshi, oxiri = m.start(), m.end()
        for i, (rs, re_) in enumerate(chegara):
            if re_ <= boshi or rs >= oxiri:
                continue
            lo = max(boshi, rs) - rs
            hi = min(oxiri, re_) - rs
            #  Qiymat belgi BOSHLANGAN run'ga tushadi — formatlash o'sha
            #  yerdan olinadi. Qolgan run'lardan faqat bo'lak o'chadi.
            qoyiladi = qiymat if rs <= boshi < re_ else ""
            yangi[i] = yangi[i][:lo] + qoyiladi + yangi[i][hi:]

    if yangi == matnlar:
        return para

    #  Qayta yig'ish — teskari tartibda, tayanch indekslar buzilmasin.
    out = bytearray(para)
    for i in range(len(parts) - 1, -1, -1):
        if yangi[i] == matnlar[i]:
            continue
        m = parts[i]
        ochuvchi = m.group(1)
        #  Bo'sh joy saqlanishi kerak: `xml:space` bo'lmasa Word
        #  boshidagi/oxiridagi probelni tashlab yuboradi va so'zlar
        #  bir-biriga yopishib qoladi.
        if b"xml:space" not in ochuvchi:
            ochuvchi = ochuvchi[:-1] + b' xml:space="preserve">'
        almash = ochuvchi + _escape(yangi[i]).encode("utf-8") + m.group(3)
        out[m.start() : m.end()] = almash
    return bytes(out)


def find_placeholders(template: bytes) -> list[str]:
    """Shablondagi belgilar ro'yxati — HR qaysi maydonlarni to'ldirishi
    kerakligini oldindan bilsin (va shablon yuklanganda tekshirilsin)."""
    nomlar: list[str] = []
    korilgan: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(template)) as zf:
        for item in zf.namelist():
            if not _TARGETS.match(item):
                continue
            xml = zf.read(item)
            for para in _PARA.finditer(xml):
                matn = "".join(
                    _unescape(m.group(2).decode("utf-8"))
                    for m in _TEXT.finditer(para.group(0))
                )
                for m in PLACEHOLDER.finditer(matn):
                    if m.group(1) not in korilgan:
                        korilgan.add(m.group(1))
                        nomlar.append(m.group(1))
    return nomlar


def render(template: bytes, values: dict[str, str]) -> tuple[bytes, list[str]]:
    """Shablonni to'ldiradi.

    Qaytaradi: (yangi `.docx` baytlari, TO'LDIRILMAGAN belgilar ro'yxati).

    To'ldirilmaganlar RO'YXATI qaytariladi, xato ko'tarilmaydi: HR bitta
    maydonni unutgani uchun butun hujjat tayyorlanmay qolishi yomonroq —
    u hujjatni ko'rib, qo'lda to'ldira oladi. Lekin bilishi SHART."""
    barcha = find_placeholders(template)
    used: set[str] = set()

    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template)) as src:
        #  ⚠️ Arxiv QAYTA yig'iladi, o'zgartirilmaydi: `zipfile` mavjud
        #  arxivdagi yozuvni joyida almashtira olmaydi (eskisi ichida
        #  qolib, Word ba'zan o'shani o'qiydi).
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if _TARGETS.match(item.filename):
                    data = _PARA.sub(
                        lambda mm: _fill_paragraph(mm.group(0), values, used), data
                    )
                #  `ZipInfo` nusxasi — sana va tashqi atributlar saqlansin.
                dst.writestr(item, data)

    qolgan = [n for n in barcha if n not in used]
    return buf.getvalue(), qolgan
