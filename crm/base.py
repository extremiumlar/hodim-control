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
