import logging
from datetime import date

import httpx

from crm.base import CRMAdapter, day_bounds_unix
from crm.config import CRM_AMOCRM_SUBDOMAIN, CRM_API_KEY

logger = logging.getLogger(__name__)

PAGE_SIZE = 250
MAX_PAGES_PER_REQUEST = 20  # xavfsizlik chegarasi — juda ko'p sahifa bo'lib ketsa ham to'xtaydi


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

    async def _count_paginated(
        self, client: httpx.AsyncClient, endpoint: str, params: dict, embedded_key: str
    ) -> int:
        """amoCRM javoblari `limit`gacha (250) cheklangan — undan ortiq natija bo'lsa
        sahifalab (page=1,2,...) hammasini yig'ib sanaydi, aks holda haqiqiy son yashirin
        qolib ketardi."""
        total = 0
        page = 1
        while page <= MAX_PAGES_PER_REQUEST:
            resp = await client.get(endpoint, params={**params, "page": page, "limit": PAGE_SIZE})
            if resp.status_code == 204:
                break
            resp.raise_for_status()
            items = resp.json().get("_embedded", {}).get(embedded_key, [])
            total += len(items)
            if len(items) < PAGE_SIZE:
                break
            page += 1
        else:
            logger.warning(
                "amoCRM %s skanerlash %s sahifada to'xtatildi (xavfsizlik chegarasi)",
                endpoint,
                MAX_PAGES_PER_REQUEST,
            )
        return total

    async def _count_events(self, client: httpx.AsyncClient, external_id: str, day: date) -> int:
        start_ts, end_ts = day_bounds_unix(day)
        return await self._count_paginated(
            client,
            "/events",
            {
                "filter[created_by]": external_id,
                "filter[created_at][from]": start_ts,
                "filter[created_at][to]": end_ts,
            },
            "events",
        )

    async def _count_completed_tasks(self, client: httpx.AsyncClient, external_id: str, day: date) -> int:
        start_ts, end_ts = day_bounds_unix(day)
        return await self._count_paginated(
            client,
            "/tasks",
            {
                "filter[responsible_user_id]": external_id,
                "filter[is_completed]": "true",
                "filter[updated_at][from]": start_ts,
                "filter[updated_at][to]": end_ts,
            },
            "tasks",
        )

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
