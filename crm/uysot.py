import logging
from datetime import date

import httpx

from crm.base import CRMAdapter, day_bounds_unix
from crm.config import CRM_API_KEY, CRM_UYSOT_VISIT_PIPE_STATUS_ID

logger = logging.getLogger(__name__)

UYSOT_BASE_URL = "https://api.service.app.uysot.uz/v1/open-api"
CALL_HISTORY_PAGE_SIZE = 100
LEAD_FILTER_PAGE_SIZE = 50  # /lead/filter uchun API'ning ruxsat etilgan maksimal "size"si
MAX_PAGES_PER_SYNC = 20  # xavfsizlik chegarasi — kunlik qo'ng'iroqlar/lidlar juda ko'p bo'lib ketsa ham to'xtaydi


class UysotAdapter(CRMAdapter):
    """Uysot CRM (https://uysot.uz) Open API orqali.

    `user.crm_external_id` — Uysot qo'ng'iroq tizimidagi xodim identifikatori (`employeeNum`,
    odatda xodimning email manzili, masalan "ism.familiya@gmail.com").

    Suhbatlar soni: `/call-history/filter` ro'yxati eng yangi qo'ng'iroqdan boshlab keladi,
    shuning uchun bugungi sanadan eskirgan yozuvga yetguncha sahifalab o'qiymiz va
    `employeeNum` bo'yicha sanaymiz. Bir sinxronizatsiya davomida barcha xodimlar uchun bitta
    umumiy so'rov natijasi qayta ishlatiladi (`_day_cache`) — aks holda har xodim uchun
    alohida to'liq skanerlash kerak bo'lib, API'ga ortiqcha yuklama tushardi.

    Tashriflar soni: `/lead/filter` endpointi `pipeStatusIds` bo'yicha server tomonida
    filtrlashni qo'llab-quvvatlaydi, shuning uchun faqat "Tashrif" bosqichidagi (ID
    `CRM_UYSOT_VISIT_PIPE_STATUS_ID` orqali sozlanadi) lidlarni so'raymiz — bu minglab
    lidning bir qismi (masalan yuzlab), to'liq ro'yxatni emas. Natijalar `updatedTimestamp`
    bo'yicha kamayish tartibida kelgani uchun call-history bilan bir xil "eskirgan yozuvga
    yetguncha sahifala" strategiyasi ishlatiladi. `user.crm_visit_external_id` — lid
    javobidagi `responsibleById` (raqamli ID, `crm_external_id`/`employeeNum`dan farqli
    ID tizimi) ga mos kelishi kerak.

    Muhim cheklov: `updatedTimestamp` — lidning oxirgi tahrirlangan vaqti, aynan "Tashrif"
    bosqichiga o'tgan vaqti emas (Uysot'da bosqich-o'tish tarixi/event log ochiq API orqali
    topilmadi). Ya'ni lidga aloqasiz tahrir (masalan teg qo'shish) qilinsa ham bugungi
    "tashrif" sifatida hisoblanishi mumkin — bu taxminiy hisob, aniq emas.
    """

    def __init__(self) -> None:
        if not CRM_API_KEY:
            logger.warning("Uysot sozlanmagan (CRM_API_KEY bo'sh)")
        self.headers = {"X-Open-Api-Token": CRM_API_KEY}
        self._day_cache: dict[str, dict[str, int]] = {}
        # responsible_id -> {"name": responsibleBy, "count": int} — ism ham saqlanadi,
        # chunki lid javobidagi `responsibleBy` xodimning o'qiladigan ismi bo'lib, uni
        # tizimdagi foydalanuvchi bilan qo'lda (email o'rniga ism bo'yicha) bog'lashda
        # foydalaniladi (`get_all_daily_visit_operators`).
        self._visit_day_cache: dict[str, dict[str, dict]] = {}

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

    async def _load_day_visits(self, client: httpx.AsyncClient, day: date) -> dict[str, dict]:
        """"Tashrif" bosqichidagi (`CRM_UYSOT_VISIT_PIPE_STATUS_ID`) lidlarni sahifalab
        o'qib, `responsibleById` bo'yicha shu kunda tahrirlanganlarni sanaydi. Har bir
        javobgar uchun oxirgi ko'ringan `responsibleBy` (ism) ham saqlanadi."""
        if not CRM_UYSOT_VISIT_PIPE_STATUS_ID:
            return {}

        day_key = day.isoformat()
        if day_key in self._visit_day_cache:
            return self._visit_day_cache[day_key]

        start_ts, end_ts = day_bounds_unix(day)
        entries: dict[str, dict] = {}
        page = 1

        while page <= MAX_PAGES_PER_SYNC:
            resp = await client.post(
                "/lead/filter",
                json={
                    "page": page,
                    "size": LEAD_FILTER_PAGE_SIZE,
                    "pipeStatusIds": [int(CRM_UYSOT_VISIT_PIPE_STATUS_ID)],
                },
            )
            resp.raise_for_status()
            body = resp.json()["data"]
            records = body.get("data", [])
            if not records:
                break

            reached_older_record = False
            for record in records:
                ts = record.get("updatedTimestamp")
                if ts is None:
                    continue
                if ts < start_ts:
                    reached_older_record = True
                    continue
                if start_ts <= ts <= end_ts:
                    responsible_id = record.get("responsibleById")
                    if responsible_id is not None:
                        key = str(responsible_id)
                        entry = entries.setdefault(key, {"name": record.get("responsibleBy") or key, "count": 0})
                        entry["count"] += 1

            if reached_older_record or page >= body.get("totalPages", page):
                break
            page += 1
        else:
            logger.warning("Uysot lead (tashrif) skanerlash %s sahifada to'xtatildi (xavfsizlik chegarasi)", MAX_PAGES_PER_SYNC)

        self._visit_day_cache[day_key] = entries
        return entries

    async def get_daily_results(self, user, day: date) -> dict | None:
        """`None` qaytarsa — CRM'dan ma'lumot olib bo'lmadi (xatolik), chaqiruvchi
        mavjud yozuvni ustidan yozmasligi kerak. Xodimda CRM ID bo'lmasa (0, 0)
        qaytariladi — bu xatolik emas, shunchaki mos yozuv yo'qligini bildiradi."""
        if (not user.crm_external_id and not user.crm_visit_external_id) or not CRM_API_KEY:
            return {"conversations": 0, "visits": 0}

        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                counts = await self._load_day_call_counts(client, day)
                visits_by_id = await self._load_day_visits(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan ma'lumot olishda xatolik (user_id=%s)", user.id)
                return None

        conversations = counts.get(user.crm_external_id, 0) if user.crm_external_id else 0
        visits = (
            visits_by_id.get(user.crm_visit_external_id, {}).get("count", 0)
            if user.crm_visit_external_id
            else 0
        )
        return {"conversations": conversations, "visits": visits}

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

    async def get_all_daily_visit_operators(self, day: date) -> list[dict]:
        """Sayt uchun: shu kunda "Tashrif" bosqichida qayd etilgan har bir javobgarning
        ID'si, ismi (`responsibleBy`) va tashriflar sonini qaytaradi — ism bo'yicha
        bog'lashni osonlashtirish uchun."""
        if not CRM_API_KEY:
            return []

        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                entries = await self._load_day_visits(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan tashrif operatorlarini olishda xatolik")
                return []

        return [
            {"responsible_id": responsible_id, "responsible_name": entry["name"], "visits": entry["count"]}
            for responsible_id, entry in entries.items()
        ]
