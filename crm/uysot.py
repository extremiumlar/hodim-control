import asyncio
import logging
from datetime import date, datetime

import httpx

from crm.base import CRMAdapter, TASHKENT_TZ, day_bounds_unix
from crm.config import (
    CRM_API_KEY,
    CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS,
    CRM_UYSOT_VISIT_PIPE_STATUS_ID,
)

logger = logging.getLogger(__name__)

UYSOT_BASE_URL = "https://api.service.app.uysot.uz/v1/open-api"
CALL_HISTORY_PAGE_SIZE = 100
LEAD_FILTER_PAGE_SIZE = 50  # /lead/filter uchun API'ning ruxsat etilgan maksimal "size"si
MAX_PAGES_PER_SYNC = 20  # xavfsizlik chegarasi — kunlik qo'ng'iroqlar/lidlar juda ko'p bo'lib ketsa ham to'xtaydi

# Operator AI kompozit sifat o'lchovi (1-bosqich tekshiruvi asosida, 2026-07-08):
# Uysot call-history'da `contacted` va `qualityScore` maydonlari bu instansiyada
# doim bo'sh (false/0) — ishlatib bo'lmaydi. Haqiqiy signallar: `missed` (javob
# berildimi: missed==False ⟺ duration>0) va `duration` (=userTalkTime, suhbat
# sekundi). "Qisqa qo'ng'iroq" (aldash/sayoz suhbat anomaliyasi) — javob berilgan,
# lekin bu chegaradan qisqa qo'ng'iroqlar.
SHORT_CALL_SECONDS = 15

# Fon (scheduler) lead breakdown skaneri uchun: butun bazani sahifalab o'qiydi.
# Uysot rate limiti daqiqasiga 60 so'rov — 30s CRM sync ham shu endpointdan
# foydalangani uchun ~40 so'rov/daqiqa'ga throttle qilamiz (zaxira qoldirib).
MAX_LEAD_SCAN_PAGES = 400  # xavfsizlik chegarasi (hozir ~184 sahifa, o'sish uchun zaxira)
REQUEST_THROTTLE_SECONDS = 1.5
RATE_LIMIT_BACKOFF_SECONDS = 60
# Vaqtinchalik tarmoq xatosi (DNS/timeout)da bitta sahifani qayta o'qish — uzoq
# skaner bitta uzilishdan butunlay yiqilmasligi uchun.
MAX_PAGE_RETRIES = 4
TRANSIENT_RETRY_SECONDS = 5


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
        # pipe_status_id -> bosqich nomi (/pipe/all dan, jarayon davomida bir marta olinadi)
        self._pipe_status_names: dict[int, str] | None = None

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

    async def get_daily_call_breakdown(self, day: date) -> dict[str, dict] | None:
        """Shu kundagi qo'ng'iroqlarni `employeeNum` bo'yicha kiruvchi/chiquvchi kesimida
        sanaydi: {employeeNum: {"in": int, "out": int}}. call-history `startStamp` bo'yicha
        kamayish tartibida keladi, shuning uchun bugungi yozuvlardan eskirgani chiqquncha
        sahifalanadi (tez — butun baza skanerlanmaydi). CRM xatosida `None`."""
        if not CRM_API_KEY:
            return None

        start_ts, end_ts = day_bounds_unix(day)
        breakdown: dict[str, dict] = {}
        page = 1
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await client.post(
                        "/call-history/filter",
                        json={"page": page, "size": CALL_HISTORY_PAGE_SIZE},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
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
                            if not employee_num:
                                continue
                            entry = breakdown.setdefault(employee_num, {"in": 0, "out": 0})
                            if record.get("callDirection") == "INBOUND":
                                entry["in"] += 1
                            else:
                                # OUTBOUND yoki noma'lum — chiquvchi deb hisoblaymiz
                                entry["out"] += 1

                    if reached_older_record or page >= body.get("totalPages", page):
                        break
                    page += 1
            except httpx.HTTPError:
                logger.exception("Uysot'dan qo'ng'iroq breakdown olishda xatolik (day=%s)", day)
                return None

        return breakdown

    @staticmethod
    def _empty_quality_bucket() -> dict[str, int]:
        return {"calls": 0, "calls_in": 0, "calls_out": 0, "answered": 0, "talk_sec": 0, "short_calls": 0}

    def _apply_call_to_bucket(self, bucket: dict[str, int], record: dict) -> None:
        """Bitta qo'ng'iroqni kompozit sifat chelakiga qo'shadi (miqdor + sifat +
        anomaliya). `missed`/`duration` haqiqiy signallar (1-bosqich tekshiruviga
        qarang) — `contacted`/`qualityScore` ishlatilmaydi (bu instansiyada bo'sh)."""
        bucket["calls"] += 1
        if record.get("callDirection") == "INBOUND":
            bucket["calls_in"] += 1
        else:  # OUTBOUND yoki noma'lum — chiquvchi deb hisoblaymiz
            bucket["calls_out"] += 1
        # Javob berildimi: missed==False ⟺ duration>0 (tekshiruvda ziddiyat topilmadi).
        if record.get("missed") is False:
            duration = record.get("duration") or 0
            bucket["answered"] += 1
            bucket["talk_sec"] += duration
            if duration < SHORT_CALL_SECONDS:
                bucket["short_calls"] += 1

    async def get_hourly_call_quality_range(self, day_from: date, day_to: date) -> dict[str, dict] | None:
        """`OperatorProfile` bootstrap (backfill) uchun: [day_from, day_to] oralig'idagi
        qo'ng'iroqlarni BITTA skanerda `employeeNum` × sana × soat kesimida kompozit
        sifat bilan sanaydi. Har kunni alohida o'qish o'rniga (bu holda eski kun uchun
        ustidagi barcha kunlarni qayta varaqlash kerak bo'lardi) newest→oldest yagona
        o'tishda day_from'dan eskirgan yozuvga yetguncha varaqlaydi.

        Qaytaradi: {employeeNum: {"YYYY-MM-DD": {soat: bucket}}}. Uzoq skaner —
        rate-limit (429) da kutadi, sahifalar orasi throttle. CRM xatosida `None`."""
        if not CRM_API_KEY:
            return None

        start_ts, _ = day_bounds_unix(day_from)
        _, end_ts = day_bounds_unix(day_to)
        result: dict[str, dict] = {}
        page = 1
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=30) as client:
            try:
                while page <= MAX_LEAD_SCAN_PAGES:
                    resp = await client.post(
                        "/call-history/filter",
                        json={"page": page, "size": CALL_HISTORY_PAGE_SIZE},
                    )
                    if resp.status_code == 429:
                        logger.warning("Uysot rate limit (call backfill) — %ss kutib qayta (sahifa %s)", RATE_LIMIT_BACKOFF_SECONDS, page)
                        await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                        continue
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
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
                        if not (start_ts <= ts <= end_ts):
                            continue  # day_to'dan yangi (oraliqdan tashqari) — o'tkazamiz
                        employee_num = record.get("employeeNum")
                        if not employee_num:
                            continue
                        local = datetime.fromtimestamp(ts, TASHKENT_TZ)
                        emp = result.setdefault(employee_num, {})
                        day_hours = emp.setdefault(local.date().isoformat(), {})
                        bucket = day_hours.setdefault(local.hour, self._empty_quality_bucket())
                        self._apply_call_to_bucket(bucket, record)

                    if reached_older_record or page >= body.get("totalPages", page):
                        break
                    page += 1
                    await asyncio.sleep(REQUEST_THROTTLE_SECONDS)
                else:
                    logger.warning("Uysot call backfill %s sahifada to'xtatildi (xavfsizlik chegarasi)", MAX_LEAD_SCAN_PAGES)
            except httpx.HTTPError:
                logger.exception("Uysot call backfill xatosi (%s..%s)", day_from, day_to)
                return None

        return result

    async def get_hourly_call_quality(self, day: date) -> dict[str, dict] | None:
        """Operator AI avto-reja/kuzatuvi uchun: shu kundagi qo'ng'iroqlarni
        `employeeNum` × soat (Asia/Tashkent, 0–23) kesimida KOMPOZIT sifat bilan
        sanaydi. Har chelak: calls, calls_in, calls_out, answered (javob berilgan),
        talk_sec (jami suhbat sekundi), short_calls (qisqa/sayoz qo'ng'iroq anomaliyasi).

        Qaytaradi: {employeeNum: {"total": {...}, "hours": {soat: {...}}}}.
        call-history `startStamp` bo'yicha kamayish tartibida keladi — bugungidan
        eskirgan yozuvga yetguncha sahifalanadi (tez, butun baza emas). CRM xatosida
        yoki kalit yo'q bo'lsa `None` (chaqiruvchi eski snapshotni ustidan yozmasin)."""
        if not CRM_API_KEY:
            return None

        start_ts, end_ts = day_bounds_unix(day)
        result: dict[str, dict] = {}
        page = 1
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await client.post(
                        "/call-history/filter",
                        json={"page": page, "size": CALL_HISTORY_PAGE_SIZE},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
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
                        if not (start_ts <= ts <= end_ts):
                            continue
                        employee_num = record.get("employeeNum")
                        if not employee_num:
                            continue
                        hour = datetime.fromtimestamp(ts, TASHKENT_TZ).hour
                        emp = result.setdefault(
                            employee_num, {"total": self._empty_quality_bucket(), "hours": {}}
                        )
                        hour_bucket = emp["hours"].setdefault(hour, self._empty_quality_bucket())
                        self._apply_call_to_bucket(emp["total"], record)
                        self._apply_call_to_bucket(hour_bucket, record)

                    if reached_older_record or page >= body.get("totalPages", page):
                        break
                    page += 1
            except httpx.HTTPError:
                logger.exception("Uysot'dan soatlik sifat olishda xatolik (day=%s)", day)
                return None

        return result

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

    async def _load_pipe_status_names(self, client: httpx.AsyncClient) -> dict[int, str]:
        """`/pipe/all` dan barcha voronkalar bosqichlarining {id: nom} lug'ati.
        Lid javobida faqat `pipeStatusId` keladi, nom shu lug'atdan olinadi."""
        if self._pipe_status_names is not None:
            return self._pipe_status_names

        resp = await client.get("/pipe/all")
        resp.raise_for_status()
        names: dict[int, str] = {}
        for pipe in resp.json().get("data") or []:
            for stage in pipe.get("pipeStatuses") or []:
                if stage.get("id") is not None and stage.get("name"):
                    names[stage["id"]] = stage["name"]
        self._pipe_status_names = names
        return names

    async def _fetch_lead_page(self, client: httpx.AsyncClient, page: int) -> dict:
        """Bitta `/lead/filter` sahifasini chidamli o'qiydi: 429 (rate limit)da
        `RATE_LIMIT_BACKOFF_SECONDS` kutadi; vaqtinchalik tarmoq xatosida (DNS/timeout)
        `TRANSIENT_RETRY_SECONDS` kutib `MAX_PAGE_RETRIES` martagacha qayta urinadi.
        Butun skaner uzoq davom etgani uchun bitta vaqtinchalik uzilish hammasini
        bekor qilmasligi kerak — shu sabab retry bu yerda."""
        attempt = 0
        while True:
            try:
                resp = await client.post(
                    "/lead/filter",
                    json={"page": page, "size": LEAD_FILTER_PAGE_SIZE},
                )
                if resp.status_code == 429:
                    logger.warning("Uysot rate limit — %ss kutib qayta (sahifa %s)", RATE_LIMIT_BACKOFF_SECONDS, page)
                    await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                    continue
                resp.raise_for_status()
                return resp.json().get("data") or {}
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                attempt += 1
                if attempt > MAX_PAGE_RETRIES:
                    raise
                logger.warning(
                    "Uysot sahifa %s vaqtinchalik xato (%s) — %ss kutib qayta (%s/%s)",
                    page, type(exc).__name__, TRANSIENT_RETRY_SECONDS, attempt, MAX_PAGE_RETRIES,
                )
                await asyncio.sleep(TRANSIENT_RETRY_SECONDS)

    async def _scan_day_lead_breakdown(
        self, client: httpx.AsyncClient, day: date
    ) -> dict[tuple[int, int], dict]:
        """Shu kunda yangilangan (`updatedTimestamp`) barcha lidlarni operator×bosqich
        kesimida sanaydi.

        MUHIM: `/lead/filter` natijani lid ID'si bo'yicha (yaratilish tartibida)
        qaytaradi, `updatedTimestamp` bo'yicha EMAS — shuning uchun "bugun tegilgan"
        lidlar butun ro'yxat bo'ylab tarqoq. Server tomonda "updated bugun" filtri
        ham yo'q (`start`/`finish` faqat yaratilgan sana bo'yicha). Demak butun bazani
        to'liq skanerlash shart. Bu sekin (minglab lid ~ yuzlab sahifa), shuning uchun
        bu metod faqat fon (scheduler) ishida chaqiriladi, bot bevosita chaqirmaydi."""
        start_ts, end_ts = day_bounds_unix(day)
        # (responsible_id, pipe_status_id) -> {"name": str, "count": int}
        entries: dict[tuple[int, int], dict] = {}
        page = 1
        total_pages = None

        while page <= MAX_LEAD_SCAN_PAGES:
            body = await self._fetch_lead_page(client, page)
            if total_pages is None:
                total_pages = body.get("totalPages") or 1
            records = body.get("data") or []
            if not records:
                break

            for record in records:
                ts = record.get("updatedTimestamp")
                if ts is None or not (start_ts <= ts <= end_ts):
                    continue
                responsible_id = record.get("responsibleById")
                status_id = record.get("pipeStatusId")
                if responsible_id is None or status_id is None:
                    continue
                key = (responsible_id, status_id)
                entry = entries.setdefault(
                    key, {"name": record.get("responsibleBy") or str(responsible_id), "count": 0}
                )
                entry["count"] += 1

            if page >= total_pages:
                break
            page += 1
            await asyncio.sleep(REQUEST_THROTTLE_SECONDS)
        else:
            logger.warning(
                "Uysot lead breakdown skaner %s sahifada to'xtadi (xavfsizlik chegarasi) — natija chala bo'lishi mumkin",
                MAX_LEAD_SCAN_PAGES,
            )

        return entries

    async def get_daily_lead_breakdown(self, day: date) -> list[dict] | None:
        """Kunlik lid statistikasi operator×bosqich kesimida (fon snapshot uchun).
        `None` — CRM'dan olib bo'lmadi (chaqiruvchi mavjud snapshot'ni saqlab qolsin).

        Har element: {responsible_id, responsible_name, pipe_status_id, stage_name, count}.

        Cheklov: hisob `updatedTimestamp` (oxirgi har qanday tahrir) ga asoslangan —
        "bosqichga o'tish" voqeasi emas, shuning uchun taxminiy. Aniq hisob Uysot
        lead-event API'si (X-Auth token) orqali keyingi bosqichda quriladi."""
        if not CRM_API_KEY:
            return None

        # Skaner uzoq davom etadi (rate-limit throttle bilan bir necha daqiqa) —
        # umumiy timeout kengroq, sahifa-so'rov timeouti alohida.
        timeout = httpx.Timeout(30.0, read=30.0)
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=timeout) as client:
            try:
                entries = await self._scan_day_lead_breakdown(client, day)
                names = await self._load_pipe_status_names(client)
            except httpx.HTTPError:
                logger.exception("Uysot'dan lead breakdown olishda xatolik (day=%s)", day)
                return None

        return [
            {
                "responsible_id": responsible_id,
                "responsible_name": entry["name"],
                "pipe_status_id": status_id,
                "stage_name": names.get(status_id, f"Bosqich #{status_id}"),
                "count": entry["count"],
            }
            for (responsible_id, status_id), entry in entries.items()
        ]

    # "Lid tugadi" tekshiruvi sozlamalari: da'voni rad etish uchun shuncha ochiq lid
    # topilishi kifoya (erta to'xtash — skan tez tugaydi, sahifa chegarasiga bog'liq
    # emas). Sahifa chegarasi kattaroq (jonli bazada ochiq bosqichlarda ~1600 lid,
    # ya'ni ~32 sahifa) — "haqiqatan bo'sh" (True) hukmi to'liq skan talab qiladi.
    OPEN_LEAD_ENOUGH = 5
    MAX_OPEN_LEAD_PAGES = 60
    OPEN_LEAD_THROTTLE_SECONDS = 0.4  # 60/min rate limitda 30s CRM sync bilan yonma-yon sig'ishi uchun

    async def count_open_leads(self, responsible_id: str) -> int | None:
        """Operatorga (`responsibleById`) biriktirilgan, "ochiq" bosqichlardagi
        (`CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS`) lidlar soni — "lid/baza tugadi"
        da'vosini tekshirish uchun. `/lead/filter` bosqich bo'yicha server tomonda
        filtrlaydi, mas'ul bo'yicha mijoz tomonda sanaladi.

        Hukm adolati: `OPEN_LEAD_ENOUGH` ta topilgach darhol qaytadi (da'vo rad —
        aniq); skan sahifa chegarasiga urilib 0 topgan bo'lsa `None` (chala skan
        asosida "lid bor edi-ku" ham, "haqiqatan bo'sh" ham deb bo'lmaydi); faqat
        TO'LIQ skan 0 bersa 0 (da'vo tasdiq). `None` — sozlanmagan/CRM xatosi ham."""
        if not CRM_API_KEY or not CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS:
            return None

        try:
            responsible_key = int(responsible_id)
        except (TypeError, ValueError):
            return None

        count = 0
        page = 1
        completed = False
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=30) as client:
            try:
                while page <= self.MAX_OPEN_LEAD_PAGES:
                    resp = await client.post(
                        "/lead/filter",
                        json={
                            "page": page,
                            "size": LEAD_FILTER_PAGE_SIZE,
                            "pipeStatusIds": CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS,
                        },
                    )
                    if resp.status_code == 429:
                        logger.warning("Uysot rate limit (ochiq lid sanovi) — %ss kutib qayta (sahifa %s)", RATE_LIMIT_BACKOFF_SECONDS, page)
                        await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                        continue
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
                    if not records:
                        completed = True
                        break
                    count += sum(1 for r in records if r.get("responsibleById") == responsible_key)
                    if count >= self.OPEN_LEAD_ENOUGH:
                        return count  # da'voni rad etishga yetarli — davom etish shart emas
                    if page >= (body.get("totalPages") or page):
                        completed = True
                        break
                    page += 1
                    await asyncio.sleep(self.OPEN_LEAD_THROTTLE_SECONDS)
            except httpx.HTTPError:
                logger.exception("Uysot'dan ochiq lidlarni sanashda xatolik (responsible_id=%s)", responsible_id)
                return None

        if count == 0 and not completed:
            # Chala skanda hech narsa topilmadi — "bo'sh" deb hukm chiqarib bo'lmaydi
            logger.warning(
                "Uysot ochiq lid sanovi %s sahifada to'xtadi, 0 topildi — hukmsiz (None)",
                self.MAX_OPEN_LEAD_PAGES,
            )
            return None
        return count

    # ─── Issiq lid (speed-to-lead, 5-bosqich) ────────────────────────────────────
    # 2026-07-09 jonli tekshiruvdan tasdiqlangan faktlar:
    #   - `/lead/filter` `start`/`finish`ni unix-SEKUND (yaratilgan vaqt) sifatida
    #     qabul qiladi (ISO sana 400 qaytaradi) va natija ID bo'yicha KAMAYISH
    #     tartibida keladi (eng yangi lid birinchi).
    #   - `GET /lead/{id}` to'liq detal beradi: contacts (ism + phones), attributions
    #     (manba kanali) — ro'yxat javobida bu maydonlar YO'Q, alohida so'rov shart.
    #   - `/call-history/filter` `phoneSearch`ni qo'llab-quvvatlaydi — lid raqamiga
    #     qilingan qo'ng'iroqlar kichik to'plam bo'lib keladi (birinchi chiquvchi
    #     qo'ng'iroq = speed-to-lead o'lchovi).

    async def get_leads_created_between(self, ts_from: int, ts_to: int) -> list[dict] | None:
        """Oraliqda YARATILGAN lidlar (yangi lid aniqlash uchun — oraliq qisqa,
        odatda bir sahifa). Har element: {"id", "responsible_id", "responsible_name",
        "pipe_status_id", "created_ts"}. `None` — CRM xatosi."""
        if not CRM_API_KEY:
            return None

        leads: list[dict] = []
        page = 1
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await client.post(
                        "/lead/filter",
                        json={"page": page, "size": LEAD_FILTER_PAGE_SIZE, "start": ts_from, "finish": ts_to},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
                    if not records:
                        break
                    for r in records:
                        if r.get("id") is None:
                            continue
                        leads.append(
                            {
                                "id": r["id"],
                                "name": r.get("name"),
                                "responsible_id": r.get("responsibleById"),
                                "responsible_name": r.get("responsibleBy"),
                                "pipe_status_id": r.get("pipeStatusId"),
                                "created_ts": r.get("createdTimestamp"),
                            }
                        )
                    if page >= (body.get("totalPages") or page):
                        break
                    page += 1
            except httpx.HTTPError:
                logger.exception("Uysot'dan yangi lidlarni o'qishda xatolik (%s..%s)", ts_from, ts_to)
                return None
        return leads

    async def get_lead_detail(self, lead_id: int) -> dict | None:
        """Bitta lidning kontakt detali (`GET /lead/{id}`): kontakt ismi, telefon,
        manba kanali. `None` — topilmadi/xatolik."""
        if not CRM_API_KEY:
            return None

        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                resp = await client.get(f"/lead/{lead_id}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json().get("data") or {}
            except httpx.HTTPError:
                logger.exception("Uysot'dan lid detalini olishda xatolik (lead_id=%s)", lead_id)
                return None

        contact_name = None
        phone = None
        for contact in data.get("contacts") or []:
            contact_name = contact_name or contact.get("name")
            for p in contact.get("phones") or []:
                if p:
                    phone = phone or p
        source = None
        for attribution in data.get("attributions") or []:
            channel = attribution.get("channel") or {}
            source = source or channel.get("source")

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "contact_name": contact_name,
            "phone": phone,
            "source": source,
            "responsible_id": data.get("responsibleById"),
        }

    async def find_first_contact_call(self, phone: str, since_ts: int) -> int | None:
        """Shu raqam bilan `since_ts`dan keyingi ENG BIRINCHI "aloqa" qo'ng'irog'i
        vaqti (unix sekund). Aloqa = CHIQUVCHI (urinishning o'zi kifoya, mijoz
        ko'tarmasa operator aybdor emas) YOKI KIRUVCHI javob berilgan (missed=False —
        mijoz o'zi chaldi va operator gaplashdi; kiruvchi o'tkazib yuborilgani
        sanalmaydi). `phoneSearch` kichik to'plam qaytargani uchun sahifalar kam;
        `start` parametri o'rniga mijoz tomonda filtrlanadi (format riskisiz).
        `None` — hali qo'ng'iroq yo'q yoki CRM xatosi."""
        if not CRM_API_KEY or not phone:
            return None

        earliest: int | None = None
        page = 1
        async with httpx.AsyncClient(base_url=UYSOT_BASE_URL, headers=self.headers, timeout=20) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await client.post(
                        "/call-history/filter",
                        json={"page": page, "size": CALL_HISTORY_PAGE_SIZE, "phoneSearch": phone},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
                    if not records:
                        break
                    for r in records:
                        ts = r.get("startStamp")
                        if ts is None or ts < since_ts:
                            continue
                        direction = r.get("callDirection")
                        is_contact = direction == "OUTBOUND" or (
                            direction == "INBOUND" and r.get("missed") is False
                        )
                        if not is_contact:
                            continue
                        if earliest is None or ts < earliest:
                            earliest = ts
                    if page >= (body.get("totalPages") or page):
                        break
                    page += 1
            except httpx.HTTPError:
                logger.exception("Uysot'da raqam bo'yicha qo'ng'iroq izlashda xatolik")
                return None
        return earliest

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
