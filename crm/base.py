from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.models import User


class CRMAdapter(ABC):
    """CRM-agnostik interfeys. Yangi CRM qo'shish uchun shu klassdan meros olib,
    faqat `get_daily_results`ni amalga oshirish kifoya — qolgan tizim o'zgarmaydi."""

    @abstractmethod
    async def get_daily_results(self, user: "User", day: date) -> dict:
        """`user.crm_external_id` orqali CRM tizimidagi xodimga moslanadi.
        Qaytaradi: {"conversations": int, "visits": int}."""
        raise NotImplementedError

    async def get_all_daily_call_counts(self, day: date) -> dict[str, int]:
        """Ixtiyoriy: shu kunda barcha operator/managerlarning qo'ng'iroqlar sonini
        {crm_external_id: soni} ko'rinishida qaytaradi (masalan botning `/statistika`
        buyrug'i uchun). Qo'llab-quvvatlamaydigan adapterlar bo'sh dict qaytaradi."""
        return {}
