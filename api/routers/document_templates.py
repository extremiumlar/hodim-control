"""`.docx` shablonlari — HR paneli (yangi TZ 3.3 / S-14).

Shablon Telegram'da saqlanadi (`file_id`), serverda emas. Yuklashda
faylning O'ZIDAN belgilar ro'yxati o'qiladi va HR ga qaytariladi —
u qaysi maydonlar kerakligini darhol ko'radi.

Generatsiya SO'ROV ICHIDA bajarilmaydi: shablon Telegram'dan yuklanadi,
keyin ZIP qayta yig'iladi. Passenger'da konkurentlik = 1, ya'ni bu ish
butun saytni kutdirib qo'yardi. `POST /render` ishni NAVBATGA qo'yadi
va `202` qaytaradi (S-07 naqshi).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db, require_roles
from api.services.background_jobs import enqueue
from db.models import (
    DOCUMENT_TEMPLATE_LABELS,
    DocumentTemplate,
    Role,
    User,
)

router = APIRouter(prefix="/document-templates", tags=["document-templates"])

_HR = (Role.hr.value, Role.boss.value, Role.dasturchi.value)

#  Shablon `.docx` — o'nlab kilobayt. Chegara xotira uchun: cPanel'da
#  RAM tor va fayl butunlay xotiraga o'qiladi.
MAX_TEMPLATE_BYTES = 5 * 1024 * 1024


class TemplateOut(BaseModel):
    id: int
    kind: str
    kind_label: str
    name: str
    placeholders: list[str]
    is_active: bool


class TemplateIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=200)
    file_id: str = Field(min_length=1, max_length=512)
    #  Belgilar ro'yxati SERVERDA aniqlanadi (faylning o'zidan). Bu
    #  maydon faqat bot orqali yuklashda oldindan hisoblangan bo'lsa
    #  ishlatiladi; bo'sh bo'lsa fayl yuklab olinib o'qiladi.
    placeholders: list[str] | None = None


class RenderIn(BaseModel):
    template_id: int
    values: dict[str, str]
    filename: str | None = None


def _out(t: DocumentTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        kind=t.kind,
        kind_label=DOCUMENT_TEMPLATE_LABELS.get(t.kind, t.kind),
        name=t.name,
        placeholders=list(t.placeholders or []),
        is_active=t.is_active,
    )


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    _actor: User = Depends(require_roles(*_HR)), db: AsyncSession = Depends(get_db)
) -> list[TemplateOut]:
    rows = await db.scalars(
        select(DocumentTemplate)
        .where(DocumentTemplate.is_active.is_(True))
        .order_by(DocumentTemplate.kind, DocumentTemplate.name)
    )
    return [_out(t) for t in rows]


@router.post("/inspect")
async def inspect_template(
    file: UploadFile,
    _actor: User = Depends(require_roles(*_HR)),
) -> dict:
    """Yuklangan `.docx` dagi belgilarni qaytaradi — SAQLAMAYDI.

    HR shablonni panelga tashlaydi, qanday belgilar borligini ko'radi va
    to'g'ri yozilganiga ishonch hosil qiladi. TZ «shablon tayyorlangach
    bir marta sinash majburiy» deydi — bu o'sha sinovning birinchi
    qadami."""
    from api.services.docx_render import find_placeholders

    xom = await file.read(MAX_TEMPLATE_BYTES + 1)
    if len(xom) > MAX_TEMPLATE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fayl juda katta (5 MB dan ortiq)")
    if not xom.startswith(b"PK"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bu `.docx` emas. Word'da «Farqli saqlash → .docx» qiling.",
        )
    try:
        nomlar = find_placeholders(xom)
    except Exception:  # noqa: BLE001 — buzuq zip ham 400 bo'lsin
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Faylni o'qib bo'lmadi")
    return {"placeholders": nomlar, "count": len(nomlar)}


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def add_template(
    payload: TemplateIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    if payload.kind not in DOCUMENT_TEMPLATE_LABELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Noma'lum tur")

    nomlar = payload.placeholders
    if nomlar is None:
        #  Belgilar faylning O'ZIDAN o'qiladi. Qo'lda kiritilsa ro'yxat
        #  shablon bilan mos kelmay qolardi va xato faqat tayyor
        #  hujjatda ko'rinardi.
        from api.services.docx_render import find_placeholders
        from api.telegram_notify import download_file

        xom = await download_file(payload.file_id)
        nomlar = find_placeholders(xom) if xom else []

    t = DocumentTemplate(
        kind=payload.kind,
        name=payload.name.strip(),
        file_id=payload.file_id,
        placeholders=nomlar,
        uploaded_by=actor.id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _out(t)


@router.post("/render", status_code=status.HTTP_202_ACCEPTED)
async def render_template(
    payload: RenderIn,
    actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hujjatni NAVBATGA qo'yadi — so'rov ichida tayyorlanmaydi.

    Natija Telegram orqali so'ragan odamga boradi (S-07 naqshi)."""
    tmpl = await db.get(DocumentTemplate, payload.template_id)
    if tmpl is None or not tmpl.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shablon topilmadi")

    yetishmayotgan = [n for n in (tmpl.placeholders or []) if n not in payload.values]
    job = await enqueue(
        db,
        "document_render",
        {
            "template_id": payload.template_id,
            "values": payload.values,
            "filename": payload.filename,
        },
        actor.id,
    )
    await db.commit()
    return {
        "job_id": job.id,
        "queued": True,
        #  Yetishmayotgan belgilar DARHOL aytiladi: HR fon ishining
        #  natijasini kutib o'tirmasin.
        "missing": yetishmayotgan,
    }


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    _actor: User = Depends(require_roles(*_HR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yumshoq o'chirish: eski shablondan tayyorlangan hujjatlar tarixda
    qoladi va qaysi shablon ishlatilgani bilinib tursin."""
    t = await db.get(DocumentTemplate, template_id)
    if t is None or not t.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")
    t.is_active = False
    await db.commit()
    return {"ok": True}
