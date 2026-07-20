"""Word (.docx) va matn fayllardan anketa savollarini ajratish.

Nega python-docx emas: cPanel'da deploy `git pull` + restart bilan cheklanadi
(pip install qadamisiz). `.docx` — bu zip ichidagi `word/document.xml`, shuning
uchun stdlib (zipfile + re) yetarli — jonli anketa fayllarida tekshirilgan.

Formatlar har xil bo'lishi mumkin (Word versiyalari, qo'lda raqamlangan yoki
avto-ro'yxat, jadvalga joylangan savollar), shuning uchun ajratish EVRISTIK va
bosqichma-bosqich yumshaydi:

1. Hujjat bloklari tartib bilan olinadi (paragraflar + jadval katakchalari),
   har biri uchun: matn, avto-raqamlanganmi (`<w:numPr>`), sarlavha uslubimi,
   qalinmi.
2. Xizmat qatorlari (F.I.Sh, Sana, "Qanday to'ldiriladi", chiziqlar) tashlanadi.
3. Savol deb hisoblanadi: "?" bilan tugasa, raqam bilan boshlansa (1. / 2) / 3-),
   avto-ro'yxat elementi bo'lsa yoki uzun bulletli qator bo'lsa.
4. Savol bo'lmagan qisqa qatorlar joriy BO'LIM (section) sifatida eslab qolinadi.
5. Hech narsa topilmasa — zaxira rejim: barcha mazmunli qatorlar savol deb
   olinadi (foydalanuvchi baribir botda ko'rib chiqadi).
"""
import io
import re
import zipfile

MAX_QUESTIONS = 300
MIN_QUESTION_LEN = 5

_TBL_RE = re.compile(r"<w:tbl[ >].*?</w:tbl>", re.S)
_TC_RE = re.compile(r"<w:tc[ >].*?</w:tc>", re.S)
_P_RE = re.compile(r"<w:p[ >].*?</w:p>", re.S)
# Matn bo'laklari va satr/tab belgilari — hujjatdagi tartibda
_TEXT_RE = re.compile(r"<w:t[^>]*>(.*?)</w:t>|<w:br\s*/?>|<w:cr\s*/?>|<w:tab\s*/?>", re.S)
_NUMPR_RE = re.compile(r"<w:numPr[ >/]")
_PSTYLE_RE = re.compile(r'<w:pStyle[^>]*w:val="([^"]+)"')
_BOLD_RE = re.compile(r"<w:b(?:\s[^>]*)?/>")
_BOLD_OFF_RE = re.compile(r'<w:b[^>]*w:val="(?:0|false)"')
_BODY_RE = re.compile(r"<w:body[ >](.*)</w:body>", re.S)

_ENTITIES = (
    ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&#39;", "'"),
    ("&nbsp;", " "), ("&amp;", "&"),  # &amp; oxirida — ikki marta ochilmasin
)

# Xizmat qatorlari (savol ham, bo'lim ham emas)
_SKIP_RE = re.compile(
    r"^(f\.?\s*i\.?\s*sh|fish|ism|familiya|sana|to'?ldirdi|imzo|telefon|lavozim)\b[\s:._-]*",
    re.I,
)
_SKIP_CONTAINS = (
    "qanday to'ldiriladi",
    "qanday toldiriladi",
    "как заполнять",
)
_FILLER_RE = re.compile(r"^[\s._\-–—=*·•]+$")

_NUM_PREFIX_RE = re.compile(r"^\s*(\d{1,3})\s*[.)\]:\-–]\s+")
_NUM_PREFIX_TIGHT_RE = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*")
_BULLET_RE = re.compile(r"^\s*[-–—•*·▪●○]\s+")
_SECTION_HINT_RE = re.compile(r"^[A-ZА-Я]\s*(qism|bo'?lim|часть|раздел)\b", re.I)


class Block:
    __slots__ = ("text", "numbered", "heading", "bold", "in_table")

    def __init__(self, text, numbered=False, heading=False, bold=False, in_table=False):
        self.text = text
        self.numbered = numbered
        self.heading = heading
        self.bold = bold
        self.in_table = in_table


def _unescape(value: str) -> str:
    for src, dst in _ENTITIES:
        value = value.replace(src, dst)
    return value


def _para_text(p_xml: str) -> str:
    parts: list[str] = []
    for m in _TEXT_RE.finditer(p_xml):
        if m.group(1) is not None:
            parts.append(m.group(1))
        else:
            tag = m.group(0)
            parts.append("\n" if ("w:br" in tag or "w:cr" in tag) else " ")
    return _unescape("".join(parts))


def _paragraph_blocks(fragment: str, in_table: bool = False) -> list[Block]:
    blocks: list[Block] = []
    for p in _P_RE.findall(fragment):
        raw = _para_text(p)
        if not raw.strip():
            continue
        style = (_PSTYLE_RE.search(p).group(1) if _PSTYLE_RE.search(p) else "").lower()
        heading = "heading" in style or "zagolovok" in style or "title" in style
        bold = bool(_BOLD_RE.search(p)) and not _BOLD_OFF_RE.search(p)
        numbered = bool(_NUMPR_RE.search(p))
        # Bitta paragraf ichidagi satr uzilishlari alohida blok bo'ladi (Word'da
        # savollar ko'pincha shunday yoziladi)
        for i, line in enumerate(raw.split("\n")):
            if line.strip():
                blocks.append(
                    Block(line.strip(), numbered=numbered and i == 0, heading=heading,
                          bold=bold, in_table=in_table)
                )
    return blocks


def _document_blocks(document_xml: str) -> list[Block]:
    body_match = _BODY_RE.search(document_xml)
    body = body_match.group(1) if body_match else document_xml

    blocks: list[Block] = []
    pos = 0
    for tbl in _TBL_RE.finditer(body):
        blocks += _paragraph_blocks(body[pos : tbl.start()])
        for cell in _TC_RE.findall(tbl.group(0)):
            blocks += _paragraph_blocks(cell, in_table=True)
        pos = tbl.end()
    blocks += _paragraph_blocks(body[pos:])
    return blocks


def _is_skip(text: str) -> bool:
    low = text.lower()
    if _FILLER_RE.match(text):
        return True
    if any(s in low for s in _SKIP_CONTAINS):
        return True
    if _SKIP_RE.match(text) and len(text) < 80:
        return True
    # Ko'rsatma qatorlari: "— javoblarni ... yozing" (tire bilan boshlanadi,
    # savol emas, uzun)
    if text[0] in "—–" and not text.rstrip().endswith("?"):
        return True
    return False


def _strip_marker(text: str) -> str:
    stripped = _NUM_PREFIX_RE.sub("", text)
    if stripped == text:
        stripped = _NUM_PREFIX_TIGHT_RE.sub("", text)
    return _BULLET_RE.sub("", stripped).strip()


def _classify(blocks: list[Block]) -> tuple[list[dict], str | None]:
    """Bloklardan savollar ro'yxati va hujjat sarlavhasini ajratadi."""
    questions: list[dict] = []
    section = ""
    title: str | None = None
    seen: set[str] = set()

    for block in blocks:
        text = block.text.strip()
        if len(text) < 2 or _is_skip(text):
            continue

        had_number = bool(_NUM_PREFIX_RE.match(text) or _NUM_PREFIX_TIGHT_RE.match(text))
        had_bullet = bool(_BULLET_RE.match(text))
        core = _strip_marker(text)
        if len(core) < 2:
            continue

        is_question = (
            core.rstrip().endswith("?")
            or had_number
            or block.numbered
            or (had_bullet and len(core) >= 20)
        )

        if is_question and len(core) >= MIN_QUESTION_LEN:
            key = core.lower()
            if key in seen:  # bir xil savol ikki marta yozilgan bo'lsa
                continue
            seen.add(key)
            questions.append({"section": section or "Savollar", "text": core})
            if len(questions) >= MAX_QUESTIONS:
                break
            continue

        # Savol emas: sarlavha yoki bo'lim nomi bo'lishi mumkin
        if title is None and (block.heading or (block.bold and len(core) <= 120)):
            title = core
            continue
        if len(core) <= 100 and not core.endswith("."):
            if block.heading or block.bold or _SECTION_HINT_RE.match(core) or len(core) <= 60:
                section = core
    return questions, title


def _fallback(blocks: list[Block]) -> list[dict]:
    """Hech qanday savol topilmaganda — mazmunli qatorlarning hammasi savol."""
    questions: list[dict] = []
    seen: set[str] = set()
    for block in blocks:
        core = _strip_marker(block.text.strip())
        if len(core) < 10 or _is_skip(core):
            continue
        key = core.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append({"section": "Savollar", "text": core})
        if len(questions) >= MAX_QUESTIONS:
            break
    return questions


def _text_blocks(data: bytes) -> list[Block]:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            content = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = data.decode("utf-8", errors="ignore")
    return [Block(line.strip()) for line in content.splitlines() if line.strip()]


def parse_questions(data: bytes, filename: str) -> dict:
    """Fayldan savollarni ajratadi.

    Qaytaradi: {"title": str|None, "questions": [{"section", "text"}], "fallback": bool}
    Xato holatlarda ValueError (chaqiruvchi foydalanuvchiga tushunarli xabar beradi).
    """
    name = (filename or "").lower()
    if name.endswith(".txt"):
        blocks = _text_blocks(data)
    elif name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise ValueError(
                "Faylni o'qib bo'lmadi — u haqiqiy .docx emas (eski .doc bo'lsa, "
                "Word'da «Save as → .docx» qiling)."
            ) from exc
        blocks = _document_blocks(document_xml)
    else:
        raise ValueError("Faqat .docx yoki .txt fayl qabul qilinadi (.doc emas).")

    if not blocks:
        raise ValueError("Faylda matn topilmadi.")

    questions, title = _classify(blocks)
    fallback = False
    if not questions:
        questions = _fallback(blocks)
        fallback = True
    if not questions:
        raise ValueError("Faylda savollar topilmadi — savollarni alohida qatorlarga yozing.")
    return {"title": title, "questions": questions, "fallback": fallback}
