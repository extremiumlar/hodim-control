import logging
from datetime import date

import httpx

from crm.base import CRMAdapter, day_bounds_unix
from crm.config import CRM_API_KEY

logger = logging.getLogger(__name__)

UYSOT_BASE_URL = "https://api.service.app.uysot.uz/v1/open-api"
CALL_HISTORY_PAGE_SIZE = 100
MAX_PAGES_PER_SYNC = 20  # xavfsizlik chegarasi — kunlik qo'ng'iroqlar juda ko'p bo'lib ketsa ham to'xtaydi


class UysotAdapter(CRMAdapter):
    """Uysot CRM (https://uysot.uz) Open API orqali.

    `user.crm_external_id` — Uysot qo'ng'iroq tizimidagi xodim identifikatori (`employeeNum`,
    odatda xodimning email manzili, masalan "ism.familiya@gmail.com").

    Suhbatlar soni: `/call-history/filter` ro'yxati eng yangi qo'ng'iroqdan boshlab keladi,
    shuning uchun bugungi sanadan eskirgan yozuvga yetguncha sahifalab o'qiymiz va
    `employeeNum` bo'yicha sanaymiz. Bir sinxronizatsiya davomida barcha xodimlar uchun bitta
    umumiy so'rov natijasi qayta ishlatiladi (`_day_cache`) — aks holda har xodim uchun
    alohida to'liq skanerlash kerak bo'lib, API'ga ortiqcha yuklama tushardi.

    Tashriflar soni: hozircha 0 qaytariladi. Sababi — Uysot'da "tashrif" alohida hodisa
    sifatida emas, balki lid pipeline bosqichi ("Tashrif") sifatida saqlanadi va lidlar
    ro'yxati (`/lead/filter`) minglab yozuvdan iborat bo'lib, unda ishonchli sana-oralig'i
    filtri topilmadi — shuning uchun har 30 soniyada to'liq skanerlash amaliy emas.
    Tashriflar hozircha xodim profilida qo'lda kiritiladi; kelajakda Uysot webhook yoki
    ishonchli filtr parametri aniqlansa, shu yerga qo'shiladi.
    """

    def __init__(self) -> None:
        if not CRM_API_KEY:
            logger.warning("Uysot sozlanmagan (CRM_API_KEY bo'sh)")
        self.headers = {"X-Open-Api-Token": CRM_API_KEY}
        self._day_cache: dict[str, dict[str, int]] = {}

    async def _load_day_call_counts(self, client: httpx.AsyncClient, day: date) -> dict[str, int]:
        day_key = day.isoformat()
        if day_key in self._day_cache:
            return self._day_cache[day_key]

        start_ts, end_ts = day_bounds_unix(day)
        counts: dict[str, int] = {}
        page = 1

        while page <= MAX_PAGES_PER_SYNC:
            resp = await client.post(
                "/call-history/filter",
                json={"page": page, "size": CALL_HISTORY_PAGE_SIZE},
            )
            resp.raise_for_status()
            body = resp.json()["data"]
            records = body.get("data", [])
            if not records:
                break

            reached_older_record = False
            for record in records:
                ts = record.get("startStamp")
                if ts is None:
                    continue
                if ts < start_ts:
                    reached_older_record = True
                    continue
                if start_ts <= ts <= end_ts:
                    employee_num = record.get("employeeNum")
                    if employee_num:
                        counts[employee_num] = counts.get(employee_num, 0) + 1

            if reached_older_record or page >= body.get("totalPages", page):
                break
            page += 1
        else:
            logger.warning("Uysot call-history skanerlash %s sahifada to'xtatildi (xavfsizlik chegarasi)", MAX_PAGES_PER_SYNC)

        self._day_cache[day_key] = counts
        return counts

    async def get_daily_results(self, user, day: date) -> dict:
        if not user.crm_external_id or not CRM_API_KEY:
            return {"conversations": 0, "visits": 0}

        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                counts = await self._load_day_call_counts(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan ma'lumot olishda xatolik (user_id=%s)", user.id)
                return {"conversations": 0, "visits": 0}

        return {"conversations": counts.get(user.crm_external_id, 0), "visits": 0}

    async def get_all_daily_call_counts(self, day: date) -> dict[str, int]:
        """Botning `/statistika` buyrug'i uchun: shu kunda barcha operator/managerlarning
        (Uysot `employeeNum`i bo'yicha) qo'ng'iroqlar sonini qaytaradi."""
        if not CRM_API_KEY:
            return {}

        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                return await self._load_day_call_counts(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan qo'ng'iroqlar statistikasini olishda xatolik")
                return {}
