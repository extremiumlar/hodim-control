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

    async def get_all_daily_visit_operators(self, day: date) -> list[dict]:
        """Ixtiyoriy: shu kunda tashrif qayd etilgan har bir operator/managerning
        {"responsible_id": str, "responsible_name": str, "visits": int} ko'rinishidagi
        ro'yxatini qaytaradi — saytda ism bo'yicha bog'lash uchun. Qo'llab-quvvatlamaydigan
        adapterlar bo'sh ro'yxat qaytaradi."""
        return []
