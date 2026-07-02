from datetime import date

from crm.base import CRMAdapter


class OneCAdapter(CRMAdapter):
    """1C integratsiyasi uchun joy — hozircha stub. Kompaniya 1C'ga o'tishga qaror qilsa,
    faqat shu klass ichini (1C REST/OData so'rovlari bilan) to'ldirish kifoya qiladi,
    qolgan tizim (API, bot, sayt) o'zgarmaydi."""

    async def get_daily_results(self, user, day: date) -> dict:
        return {"conversations": 0, "visits": 0}
