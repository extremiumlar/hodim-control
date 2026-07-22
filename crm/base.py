from abc import ABC, abstractmethod
from datetime import date, datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from db.models import User

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def day_bounds_unix(day: date) -> tuple[int, int]:
    """Berilgan kalendar kunning Asia/Tashkent bo'yicha boshlanishi/tugashini
    UTC unix timestamp'larga o'giradi (CRM API'lar odatda UTC unix qabul qiladi)."""
    start = datetime.combine(day, time.min, tzinfo=TASHKENT_TZ)
    end = datetime.combine(day, time.max, tzinfo=TASHKENT_TZ)
    return int(start.timestamp()), int(end.timestamp())


class CRMAdapter(ABC):
    """CRM-agnostik interfeys. Yangi CRM qo'shish uchun shu klassdan meros olib,
    faqat `get_daily_results`ni amalga oshirish kifoya — qolgan tizim o'zgarmaydi."""

    @abstractmethod
    async def get_daily_results(self, user: "User", day: date) -> dict | None:
        """`user.crm_external_id` orqali CRM tizimidagi xodimga moslanadi.
        Qaytaradi: {"conversations": int, "visits": int}, yoki CRM'dan ma'lumot
        olib bo'lmasa (xatolik) `None` — bu holda chaqiruvchi mavjud yozuvni
        ustidan yozmasligi kerak."""
        raise NotImplementedError

    async def get_all_daily_call_counts(self, day: date) -> dict[str, int]:
        """Ixtiyoriy: shu kunda barcha operator/managerlarning qo'ng'iroqlar sonini
        {crm_external_id: soni} ko'rinishida qaytaradi (masalan botning `/statistika`
        buyrug'i uchun). Qo'llab-quvvatlamaydigan adapterlar bo'sh dict qaytaradi."""
        return {}

    async def get_daily_call_breakdown(self, day: date) -> dict[str, dict] | None:
        """Ixtiyoriy: shu kundagi qo'ng'iroqlarni CRM xodim identifikatori
        (`crm_external_id`/employeeNum) bo'yicha kiruvchi/chiquvchi kesimida qaytaradi:
        {employee_id: {"in": int, "out": int}}. CRM'dan olib bo'lmasa `None`.
        Qo'llab-quvvatlamaydigan adapterlar `None` qaytaradi."""
        return None

    async def get_hourly_call_quality(self, day: date) -> dict[str, dict] | None:
        """Ixtiyoriy (Operator AI uchun): shu kundagi qo'ng'iroqlarni CRM xodim
        identifikatori (`employeeNum`) × soat kesimida kompozit sifat bilan qaytaradi —
        {employee_id: {"total": {...}, "hours": {soat: {...}}}}, har chelak calls,
        calls_in, calls_out, answered, talk_sec, short_calls. CRM'dan olib bo'lmasa
        `None`. Qo'llab-quvvatlamaydigan adapterlar `None` qaytaradi."""
        return None

    async def get_daily_lead_breakdown(self, day: date) -> list[dict] | None:
        """Ixtiyoriy: shu kunda ishlangan (yangilangan) lidlarni operator×bosqich
        kesimida sanaydi — har element {"responsible_id": int, "responsible_name": str,
        "pipe_status_id": int, "stage_name": str, "count": int}. CRM'dan olib bo'lmasa
        (xatolik) `None` — chaqiruvchi mavjud snapshot'ni ustidan yozmasligi kerak.
        Qo'llab-quvvatlamaydigan adapterlar `None` qaytaradi."""
        return None

    async def count_open_leads(self, responsible_id: str) -> int | None:
        """Ixtiyoriy (Operator AI sabab tekshiruvi uchun): operatorga biriktirilgan
        hali ishlanmagan ("ochiq"/yangi bosqichdagi) lidlar sonini qaytaradi —
        "lid/baza tugadi" da'vosini faktlar bilan solishtirish uchun. `None` —
        tekshirib bo'lmadi (sozlanmagan yoki CRM xatosi); chaqiruvchi bu holda
        hukm chiqarmasligi kerak. Qo'llab-quvvatlamaydigan adapterlar `None`."""
        return None

    async def get_leads_created_between(self, ts_from: int, ts_to: int) -> list[dict] | None:
        """Ixtiyoriy (issiq lid uchun): berilgan unix-sekund oralig'ida YARATILGAN
        lidlar ro'yxati — har element kamida {"id", "responsible_id", "responsible_name",
        "created_ts"} maydonlariga ega. `None` — CRM xatosi (chaqiruvchi hukm
        chiqarmasin). Qo'llab-quvvatlamaydigan adapterlar `None` qaytaradi."""
        return None

    async def get_lead_detail(self, lead_id: int) -> dict | None:
        """Ixtiyoriy (issiq lid uchun): bitta lidning kontakt ma'lumoti —
        {"id", "name", "contact_name", "phone", "phones", "source", "responsible_id"}.
        `phone` — birinchi (ko'rsatish uchun), `phones` — BARCHA ma'lum kontakt
        raqamlari ro'yxati (qo'ng'iroq tekshiruvi hammasini ko'rib chiqishi uchun).
        `None` — topilmadi yoki CRM xatosi. Qo'llab-quvvatlamaydigan adapterlar `None`."""
        return None

    async def find_first_contact_call(self, phone: str, since_ts: int) -> int | None:
        """Ixtiyoriy (issiq lid speed-to-lead uchun): shu raqam bilan `since_ts`dan
        keyingi ENG BIRINCHI "aloqa" qo'ng'irog'ining unix-sekund vaqti — chiquvchi
        (urinish kifoya) yoki kiruvchi javob berilgan. `None` — hali qo'ng'iroq yo'q
        yoki CRM xatosi. Qo'llab-quvvatlamaydigan adapterlar `None`."""
        return None

    async def get_all_daily_visit_operators(self, day: date) -> list[dict]:
        """Ixtiyoriy: shu kunda tashrif qayd etilgan har bir operator/managerning
        {"responsible_id": str, "responsible_name": str, "visits": int} ko'rinishidagi
        ro'yxatini qaytaradi — saytda ism bo'yicha bog'lash uchun. Qo'llab-quvvatlamaydigan
        adapterlar bo'sh ro'yxat qaytaradi."""
        return []

    async def get_active_leads_snapshot(self, created_since_ts: int | None = None) -> list[dict] | None:
        """Ixtiyoriy (diff-engine, kunlik statistika uchun — `api/services/lead_diff.py`):
        CRM'dagi lidlarning JORIY holatini (bosqich + mas'ul) qaytaradi — har element
        kamida {"id", "pipe_status_id", "stage_name", "responsible_id",
        "responsible_name", "updated_ts"}. `created_since_ts` berilsa faqat shu
        vaqtdan keyin YARATILGAN lidlar bilan CHEGARALANGAN (tez) skan; `None` —
        BUTUN baza (sekin, tungi to'liq solishtiruv uchun). Kunlik sana filtri
        YO'Q — diff-engine o'zi bu holatni oldingi ko'rgan holat bilan solishtirib
        "haqiqatan o'zgardimi"ni aniqlaydi. `None` — CRM xatosi yoki qo'llab-
        quvvatlamaydigan adapter (chaqiruvchi mavjud xotirani ustidan yozmasin)."""
        return None
