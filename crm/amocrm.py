import logging
from datetime import date

import httpx

from crm.base import CRMAdapter, day_bounds_unix
from crm.config import CRM_AMOCRM_SUBDOMAIN, CRM_API_KEY

logger = logging.getLogger(__name__)


class AmoCRMAdapter(CRMAdapter):
    """amoCRM REST API (v4) orqali xodimning kunlik faoliyatini o'qiydi.

    `user.crm_external_id` amoCRM foydalanuvchi ID'siga (responsible_user_id) mos kelishi kerak.
    "Suhbat" ko'rsatkichi sifatida shu kun ichida foydalanuvchi yaratgan Events soni,
    "tashrif" sifatida esa shu kun ichida bajarilgan Tasks soni olinadi — bu aniq biznes
    qoidasi CRM tomonidan tasdiqlangach `_count_events`/`_count_completed_tasks` ichida
    moslashtiriladi (masalan maxsus task_type_id bo'yicha filtr qo'shiladi).
    """

    def __init__(self) -> None:
        if not CRM_AMOCRM_SUBDOMAIN or not CRM_API_KEY:
            logger.warning("amoCRM sozlanmagan (CRM_AMOCRM_SUBDOMAIN/CRM_API_KEY bo'sh)")
        self.base_url = f"https://{CRM_AMOCRM_SUBDOMAIN}.amocrm.ru/api/v4"
        self.headers = {"Authorization": f"Bearer {CRM_API_KEY}"}

    async def _count_events(self, client: httpx.AsyncClient, external_id: str, day: date) -> int:
        start_ts, end_ts = day_bounds_unix(day)
        resp = await client.get(
            "/events",
            params={
                "filter[created_by]": external_id,
                "filter[created_at][from]": start_ts,
                "filter[created_at][to]": end_ts,
                "limit": 250,
            },
        )
        if resp.status_code == 204:
            return 0
        resp.raise_for_status()
        data = resp.json()
        return len(data.get("_embedded", {}).get("events", []))

    async def _count_completed_tasks(self, client: httpx.AsyncClient, external_id: str, day: date) -> int:
        start_ts, end_ts = day_bounds_unix(day)
        resp = await client.get(
            "/tasks",
            params={
                "filter[responsible_user_id]": external_id,
                "filter[is_completed]": "true",
                "filter[updated_at][from]": start_ts,
                "filter[updated_at][to]": end_ts,
                "limit": 250,
            },
        )
        if resp.status_code == 204:
            return 0
        resp.raise_for_status()
        data = resp.json()
        return len(data.get("_embedded", {}).get("tasks", []))

    async def get_daily_results(self, user, day: date) -> dict | None:
        """`None` qaytarsa — CRM'dan ma'lumot olib bo'lmadi (xatolik), chaqiruvchi
        mavjud yozuvni ustidan yozmasligi kerak. Xodimda CRM ID bo'lmasa (0, 0)
        qaytariladi — bu xatolik emas, shunchaki mos yozuv yo'qligini bildiradi."""
        if not user.crm_external_id or not CRM_AMOCRM_SUBDOMAIN or not CRM_API_KEY:
            return {"conversations": 0, "visits": 0}

        async with httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=15) as client:
            try:
                conversations = await self._count_events(client, user.crm_external_id, day)
                visits = await self._count_completed_tasks(client, user.crm_external_id, day)
            except httpx.HTTPError:
                logger.exception("amoCRM'dan ma'lumot olishda xatolik (user_id=%s)", user.id)
                return None

        return {"conversations": conversations, "visits": visits}
