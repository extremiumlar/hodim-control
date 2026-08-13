import contextvars
import asyncio
import logging
import time
from datetime import date, datetime

import httpx

from crm.base import CRMAdapter, TASHKENT_TZ, day_bounds_unix
from crm.config import (
    CRM_API_KEY,
    CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS,
    CRM_UYSOT_MAX_REQUESTS_PER_MINUTE,
    CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS,
    CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
)

logger = logging.getLogger(__name__)

UYSOT_BASE_URL = "https://api.service.app.uysot.uz/v1/open-api"
CALL_HISTORY_PAGE_SIZE = 100
LEAD_FILTER_PAGE_SIZE = 50  # /lead/filter uchun API'ning ruxsat etilgan maksimal "size"si
MAX_PAGES_PER_SYNC = 20  # xavfsizlik chegarasi — kunlik qo'ng'iroqlar/lidlar juda ko'p bo'lib ketsa ham to'xtaydi
# Diff-engine chegaralangan (tez) skani uchun xavfsizlik chegarasi — MAX_LEAD_SCAN_PAGES'dan
# kichik, chunki faqat so'nggi CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS kunlik lidlarni qamraydi.
MAX_ACTIVE_LEAD_SCAN_PAGES = 200

# Operator AI kompozit sifat o'lchovi (1-bosqich tekshiruvi asosida, 2026-07-08):
# Uysot call-history'da `contacted` va `qualityScore` maydonlari bu instansiyada
# doim bo'sh (false/0) — ishlatib bo'lmaydi. Haqiqiy signallar: `missed` (javob
# berildimi: missed==False ⟺ duration>0) va `duration` (=userTalkTime, suhbat
# sekundi). "Qisqa qo'ng'iroq" (aldash/sayoz suhbat anomaliyasi) — javob berilgan,
# lekin bu chegaradan qisqa qo'ng'iroqlar.
SHORT_CALL_SECONDS = 15

# To'liq baza skani (tungi reconcile) uchun xavfsizlik chegarasi
# (hozir ~184 sahifa, o'sish uchun zaxira).
MAX_LEAD_SCAN_PAGES = 400
# 429 javobida (Retry-After sarlavhasi bo'lmasa) BUTUN jarayon shuncha kutadi —
# Uysot limiti daqiqalik oynada, 60s kutish oyna yangilanishini kafolatlaydi.
RATE_LIMIT_BACKOFF_SECONDS = 60
MAX_RATE_LIMIT_RETRIES = 4
# Ko'p-sahifali OG'IR skanlar (diff-engine, call backfill) sahifalari orasidagi
# qo'shimcha pauza (~30 so'rov/daqiqa). Global byudjet (_SharedRateBudget)
# JARAYON-ichi; production cPanel rejimida esa Uysot'ga IKKI jarayon chiqadi:
# cron_tick.py (in-process skanlar) va Passenger API ishchisi (crm_sync, AI,
# bot). Har biri o'z byudjetiga ega bo'lgani uchun og'ir skan o'z jarayonining
# to'liq byudjetini yesa, ikkinchi jarayon bilan yig'indi 60/daqiqadan oshishi
# mumkin edi — bu pauza skanga sekinroq "tayanch" tezlik berib, qo'shni
# jarayonning yengil trafigiga joy qoldiradi. Yengil (bir-ikki sahifali)
# yo'llar pauzasiz — ular faqat byudjet slotini oladi.
SCAN_THROTTLE_SECONDS = 2.0
# Vaqtinchalik tarmoq xatosi (DNS/timeout)da bitta so'rovni qayta urinish — uzoq
# skaner bitta uzilishdan butunlay yiqilmasligi uchun.
MAX_PAGE_RETRIES = 4
TRANSIENT_RETRY_SECONDS = 5

class UysotBusy(RuntimeError):
    """CRM band va HTTP so'rov ichida kutish chegarasi tugadi.

    Chaqiruvchi buni 503/«CRM band, keyinroq urinib ko'ring» ga aylantiradi.
    Fon (cron) yo'lida bu istisno HECH QACHON ko'tarilmaydi — u yerda sabr
    qilish to'g'ri."""


# HTTP so'rovi ichidamizmi. `contextvars` ATAYLAB: asyncio'da har so'rov o'z
# kontekstini oladi, oddiy global bayroq esa bitta jarayonda parallel
# ishlayotgan cron skani va web so'rovi orasida aralashib ketardi.
#
# NEGA KERAK (2026-08-13 o'lchovi): jonli saytda bitta so'rov 40.3 SONIYA
# kutdi. Sabab — cron API'ga HTTP orqali murojaat qiladi, Uysot 429 bersa
# so'rov ichida 60s × 4 = 4 daqiqagacha kutish mumkin, konkurentlik esa 1 —
# ya'ni butun sayt o'sha vaqt davomida o'lik. Fon skanlari uchun sabr to'g'ri,
# LEKIN foydalanuvchi kutayotgan so'rov uchun emas.
_REQUEST_CONTEXT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "uysot_request_context", default=False
)

# HTTP so'rov ichida Uysot'ni kutishga ajratilgan JAMI vaqt.
MAX_INREQUEST_WAIT_SECONDS = 10.0


def mark_request_context() -> None:
    """Joriy async kontekstni «HTTP so'rovi» deb belgilaydi.

    Buni CRM'ga boradigan endpointlar chaqiradi. Fon joblari chaqirmaydi —
    ular default (`False`) bilan qoladi va avvalgidek sabr qiladi."""
    _REQUEST_CONTEXT.set(True)


class _SharedRateBudget:
    """Uysot'ning 60 so'rov/daqiqa limitini BARCHA iste'molchilar o'rtasida
    bitta joyda taqsimlaydi (2026-08-03, production'dagi 429 bo'roniga javob).

    Muammo: adapter har chaqiruvda yangidan yaratiladi va har skan O'Z
    throttle'i bilan yurardi — lead snapshot (~40/daq) + diff-tick (~40/daq) +
    CRM sync bir vaqtga tushganda jami limitdan oshib, yengil joblar 429
    traceback bilan yiqilardi (429 bilan ishlashni faqat 2 ta uzun skan
    bilardi). Yechim: modul-darajali YAGONA byudjet — har so'rov global
    minimal-interval slotini oladi (asyncio.Lock FIFO — yengil job og'ir skan
    sahifalari orasida adolatli galma-gal o'tadi, navbatsiz qolmaydi), 429
    kelganda esa cooldown HAMMA so'rovlarga birdek qo'llanadi (joblararo
    muvofiqlashgan backoff).

    Bu JARAYON-ICHI mexanizm. Docker rejimida barcha Uysot chaqiruvlari yagona
    API jarayonida (uvicorn bitta worker) — byudjet to'liq qamraydi. cPanel
    cron rejimida esa ikki jarayon bor: cron_tick.py (in-process skanlar) va
    Passenger API ishchisi — har biri O'Z byudjetiga ega, shuning uchun og'ir
    skanlar qo'shimcha `SCAN_THROTTLE_SECONDS` bilan sekinlashtiriladi (yig'indi
    60/daqiqadan oshmasin). API ko'p-worker qilinsa byudjetni worker soniga
    bo'lish kerak bo'ladi."""

    def __init__(self, per_minute: int) -> None:
        self._min_interval = 60.0 / max(1, per_minute)
        self._lock = asyncio.Lock()
        self._next_slot = 0.0  # monotonic: keyingi so'rovga ruxsat vaqti
        self._cooldown_until = 0.0  # 429'dan keyin hamma shu vaqtgacha kutadi

    async def acquire(self, deadline: float | None = None) -> None:
        """Slot oladi va kerak bo'lsa kutadi.

        `deadline` (monotonic) berilsa va kutish undan oshsa — `UysotBusy`
        ko'tariladi. Bu HTTP so'rov ichidan chaqirilganda kerak: foydalanuvchi
        60 soniya kutib o'tirmasin (`_REQUEST_CONTEXT` izohiga qara).
        Slot BARIBIR band qilinadi — aks holda navbatdagi so'rovlar chalkashib,
        limitdan oshib ketardi."""
        async with self._lock:
            now = time.monotonic()
            slot = max(self._next_slot, self._cooldown_until, now)
            self._next_slot = slot + self._min_interval
        delay = slot - now
        if delay <= 0:
            return
        if deadline is not None and slot > deadline:
            raise UysotBusy(
                f"CRM band — navbat {delay:.0f}s, so'rov chegarasi tugadi"
            )
        await asyncio.sleep(delay)

    def start_cooldown(self, seconds: float) -> None:
        until = time.monotonic() + seconds
        self._cooldown_until = max(self._cooldown_until, until)
        self._next_slot = max(self._next_slot, until)


_RATE_BUDGET = _SharedRateBudget(CRM_UYSOT_MAX_REQUESTS_PER_MINUTE)


def _retry_after_seconds(resp: httpx.Response) -> float:
    """429 javobidagi Retry-After (sekund) — yo'q/nosog'lom bo'lsa default."""
    try:
        value = float(resp.headers.get("Retry-After", ""))
    except ValueError:
        return float(RATE_LIMIT_BACKOFF_SECONDS)
    if 0 < value <= 600:
        return value
    return float(RATE_LIMIT_BACKOFF_SECONDS)


async def _limited_request(
    client: httpx.AsyncClient, method: str, path: str, *, json: dict | None = None
) -> httpx.Response:
    """Barcha Uysot HTTP so'rovlari uchun YAGONA kirish nuqtasi: global byudjet
    slotini oladi; 429'da muvofiqlashgan cooldown bilan qayta urinadi (limitga
    urilgan job endi traceback bilan yiqilmaydi — kutadi, boshqa joblar ham
    o'sha cooldown'ni ko'radi); vaqtinchalik tarmoq xatosida ham qayta urinadi.
    Boshqa statuslarni tekshirmaydi (masalan 404 semantikasi chaqiruvchida) —
    retry'lar tugagan 429 ham chaqiruvchining `raise_for_status`iga qaytadi."""
    rate_limited = 0
    transient = 0
    # HTTP so'rovi ichida bo'lsak — kutishga QAT'IY chegara. Fon (cron)
    # yo'lida `deadline is None`, ya'ni xulq umuman o'zgarmaydi.
    in_request = _REQUEST_CONTEXT.get()
    deadline = time.monotonic() + MAX_INREQUEST_WAIT_SECONDS if in_request else None

    while True:
        await _RATE_BUDGET.acquire(deadline)
        try:
            resp = await client.request(method, path, json=json)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            transient += 1
            if transient > MAX_PAGE_RETRIES:
                raise
            if deadline is not None and time.monotonic() + TRANSIENT_RETRY_SECONDS > deadline:
                raise UysotBusy(f"CRM javob bermadi ({type(exc).__name__}) — so'rov chegarasi tugadi")
            logger.warning(
                "Uysot %s %s vaqtinchalik xato (%s) — %ss kutib qayta (%s/%s)",
                method, path, type(exc).__name__, TRANSIENT_RETRY_SECONDS, transient, MAX_PAGE_RETRIES,
            )
            await asyncio.sleep(TRANSIENT_RETRY_SECONDS)
            continue
        if resp.status_code != 429:
            return resp
        rate_limited += 1
        if rate_limited > MAX_RATE_LIMIT_RETRIES:
            return resp
        backoff = _retry_after_seconds(resp)
        # Cooldown HAR DOIM e'lon qilinadi — u global va boshqa (fon)
        # iste'molchilarga ham kerak. Faqat BIZ kutmaymiz.
        _RATE_BUDGET.start_cooldown(backoff)
        if deadline is not None:
            raise UysotBusy(
                f"CRM limitga urildi (429), {int(backoff)}s cooldown — so'rov kutmaydi"
            )
        logger.warning(
            "Uysot rate limit (%s %s) — %ss global cooldown, qayta urinish %s/%s",
            method, path, int(backoff), rate_limited, MAX_RATE_LIMIT_RETRIES,
        )
        # start_cooldown keyingi acquire'ni cooldown oxirigacha suradi —
        # bu yerda alohida sleep shart emas.


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
    filtrlashni qo'llab-quvvatlaydi, shuning uchun faqat "Tashrif" bosqich(lar)idagi
    (ID'lar `CRM_UYSOT_VISIT_PIPE_STATUS_IDS` orqali sozlanadi — bir nechta voronkada
    alohida "Tashrif" bosqichi bo'lishi mumkin) lidlarni so'raymiz — bu minglab
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

    def _client(self, timeout=30) -> httpx.AsyncClient:
        """Barcha Uysot so'rovlari uchun YAGONA klient fabrikasi. Pacing va 429
        muvofiqlashuvi bu yerda EMAS — `_limited_request` (global
        `_SharedRateBudget`) ichida; yangi so'rov joyi qo'shsangiz klientni shu
        fabrikadan oling va so'rovni faqat `_limited_request` orqali yuboring —
        aks holda u byudjetdan tashqarida qolib limitni buzadi."""
        return httpx.AsyncClient(
            base_url=UYSOT_BASE_URL,
            headers=self.headers,
            timeout=timeout,
        )

    async def _load_day_call_counts(self, client: httpx.AsyncClient, day: date) -> dict[str, int]:
        day_key = day.isoformat()
        if day_key in self._day_cache:
            return self._day_cache[day_key]

        start_ts, end_ts = day_bounds_unix(day)
        counts: dict[str, int] = {}
        page = 1

        while page <= MAX_PAGES_PER_SYNC:
            resp = await _limited_request(
                client, "POST", "/call-history/filter",
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
        async with self._client(timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await _limited_request(
                        client, "POST", "/call-history/filter",
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

    async def get_last_call_timestamps(
        self, employee_nums: set[str], since_ts: int
    ) -> dict[str, int] | None:
        """Real-vaqtli harakatsizlik nazorati uchun: har operatorning ENG OXIRGI
        qo'ng'irog'i vaqti. `/call-history/filter` yangidan-eskiga keladi, shuning
        uchun `employee_nums`ning HAMMASI birinchi marta ko'rilgach yoki
        `since_ts`dan eskiroq yozuvga yetilgach darhol to'xtaydi — odatda 1-2
        sahifa (arzon, tez-tez chaqirsa bo'ladi)."""
        if not CRM_API_KEY or not employee_nums:
            return None

        found: dict[str, int] = {}
        remaining = set(employee_nums)
        page = 1
        async with self._client(timeout=20) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC and remaining:
                    resp = await _limited_request(
                        client, "POST", "/call-history/filter",
                        json={"page": page, "size": CALL_HISTORY_PAGE_SIZE},
                    )
                    resp.raise_for_status()
                    body = resp.json().get("data") or {}
                    records = body.get("data") or []
                    if not records:
                        break

                    reached_cutoff = False
                    for record in records:
                        ts = record.get("startStamp")
                        employee_num = record.get("employeeNum")
                        if ts is None or not employee_num:
                            continue
                        if ts < since_ts:
                            reached_cutoff = True
                            continue
                        if employee_num in remaining:
                            found[employee_num] = ts  # birinchi ko'rinish = eng yangisi
                            remaining.discard(employee_num)

                    if reached_cutoff or page >= body.get("totalPages", page):
                        break
                    page += 1
            except httpx.HTTPError:
                logger.exception("Uysot'dan so'nggi qo'ng'iroq vaqtlarini olishda xatolik")
                return None

        return found

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
        tezligini global so'rov byudjeti (`_limited_request`) tekislaydi.
        CRM xatosida `None`."""
        if not CRM_API_KEY:
            return None

        start_ts, _ = day_bounds_unix(day_from)
        _, end_ts = day_bounds_unix(day_to)
        result: dict[str, dict] = {}
        page = 1
        async with self._client(timeout=30) as client:
            try:
                while page <= MAX_LEAD_SCAN_PAGES:
                    resp = await _limited_request(
                        client, "POST", "/call-history/filter",
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
                    await asyncio.sleep(SCAN_THROTTLE_SECONDS)
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
        async with self._client(timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await _limited_request(
                        client, "POST", "/call-history/filter",
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
        """"Tashrif" bosqichlaridagi (`CRM_UYSOT_VISIT_PIPE_STATUS_IDS` — bir nechta
        voronkada alohida "Tashrif" bosqichi bo'lishi mumkin, 5-band tuzatishi
        2026-07-24) lidlarni sahifalab o'qib, `responsibleById` bo'yicha shu kunda
        tahrirlanganlarni sanaydi. Har bir javobgar uchun oxirgi ko'ringan
        `responsibleBy` (ism) ham saqlanadi."""
        if not CRM_UYSOT_VISIT_PIPE_STATUS_IDS:
            return {}

        day_key = day.isoformat()
        if day_key in self._visit_day_cache:
            return self._visit_day_cache[day_key]

        start_ts, end_ts = day_bounds_unix(day)
        entries: dict[str, dict] = {}
        page = 1

        while page <= MAX_PAGES_PER_SYNC:
            resp = await _limited_request(
                client, "POST", "/lead/filter",
                json={
                    "page": page,
                    "size": LEAD_FILTER_PAGE_SIZE,
                    "pipeStatusIds": list(CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
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

        resp = await _limited_request(client, "GET", "/pipe/all")
        resp.raise_for_status()
        names: dict[int, str] = {}
        for pipe in resp.json().get("data") or []:
            for stage in pipe.get("pipeStatuses") or []:
                if stage.get("id") is not None and stage.get("name"):
                    names[stage["id"]] = stage["name"]
        self._pipe_status_names = names
        return names

    async def _fetch_lead_page(self, client: httpx.AsyncClient, page: int, extra: dict | None = None) -> dict:
        """Bitta `/lead/filter` sahifasi — 429/vaqtinchalik-xato chidamliligi
        `_limited_request` ichida (butun skaner bitta uzilishdan yiqilmaydi).
        `extra` — qo'shimcha so'rov maydonlari (masalan `start`/`finish` sana
        chegarasi)."""
        body = {"page": page, "size": LEAD_FILTER_PAGE_SIZE, **(extra or {})}
        resp = await _limited_request(client, "POST", "/lead/filter", json=body)
        resp.raise_for_status()
        return resp.json().get("data") or {}

    # ESLATMA (2026-08-03): ilgari shu yerda `get_daily_lead_breakdown` bor edi —
    # "bugun tegilgan lidlar" uchun BUTUN bazani (~184 sahifa) har 30 daqiqada
    # skanerlaydigan eng katta so'rov-iste'molchi. LeadStageDaily endi lokal
    # LeadEvent/CrmLeadState'dan hisoblanadi (api/routers/stats.py,
    # `_local_lead_breakdown`) — diff-engine/webhook shu jadvallarni allaqachon
    # to'ldiradi, qo'shimcha CRM skani ortiqcha edi.

    # ─── Diff-engine (kunlik statistika, api/services/lead_diff.py) ────────────
    async def _scan_active_leads(
        self, client: httpx.AsyncClient, created_since_ts: int | None
    ) -> list[dict]:
        """`created_since_ts` berilsa — shu vaqtdan keyin YARATILGAN lidlar bilan
        CHEGARALANGAN (tez) skan; `None` — BUTUN baza (sekin, tungi to'liq
        solishtiruv). Ikkalasida ham har sahifadagi lidning JORIY holati (bosqich +
        mas'ul) to'liq qaytariladi — `updatedTimestamp` bo'yicha kunlik filtr YO'Q,
        chunki diff-engine "o'zgardimi"ni o'zi oldingi holat bilan solishtirib
        aniqlaydi (bu yerda faqat "hozir nima" kerak)."""
        extra: dict = {}
        if created_since_ts is not None:
            extra = {"start": created_since_ts, "finish": int(time.time())}
        max_pages = MAX_LEAD_SCAN_PAGES if created_since_ts is None else MAX_ACTIVE_LEAD_SCAN_PAGES

        records_out: list[dict] = []
        page = 1
        total_pages = None
        while page <= max_pages:
            body = await self._fetch_lead_page(client, page, extra=extra)
            if total_pages is None:
                total_pages = body.get("totalPages") or 1
            records = body.get("data") or []
            if not records:
                break
            for record in records:
                if record.get("id") is not None:
                    records_out.append(record)
            if page >= total_pages:
                break
            page += 1
            await asyncio.sleep(SCAN_THROTTLE_SECONDS)
        else:
            logger.warning(
                "Uysot faol-lidlar skaneri %s sahifada to'xtadi (xavfsizlik chegarasi) — "
                "natija chala bo'lishi mumkin (created_since_ts=%s)",
                max_pages, created_since_ts,
            )

        return records_out

    async def _scan_visit_stage_leads(self, client: httpx.AsyncClient) -> list[dict]:
        """Hozir "Tashrif" bosqich(lar)ida TURGAN lidlar — yaratilgan sanasidan
        qat'i nazar. Nega kerak: tez skan faqat so'nggi N kunda YARATILGAN
        lidlarni ko'radi, 30+ kunlik lid Tashrifga o'tsa uni faqat tungi to'liq
        skan topardi (03:30 da — tashrif keyingi kunga yozilib ketardi,
        2026-08-03 da tasdiqlangan). Bu qo'shimcha so'rov arzon: Tashrifda
        odatda bir necha o'nlab lid turadi (1-2 sahifa)."""
        if not CRM_UYSOT_VISIT_PIPE_STATUS_IDS:
            return []
        extra = {"pipeStatusIds": list(CRM_UYSOT_VISIT_PIPE_STATUS_IDS)}
        records_out: list[dict] = []
        page = 1
        total_pages = None
        while page <= MAX_ACTIVE_LEAD_SCAN_PAGES:
            body = await self._fetch_lead_page(client, page, extra=extra)
            if total_pages is None:
                total_pages = body.get("totalPages") or 1
            records = body.get("data") or []
            if not records:
                break
            for record in records:
                if record.get("id") is not None:
                    records_out.append(record)
            if page >= total_pages:
                break
            page += 1
            await asyncio.sleep(SCAN_THROTTLE_SECONDS)
        return records_out

    async def get_active_leads_snapshot(self, created_since_ts: int | None = None) -> list[dict] | None:
        """Diff-engine uchun: lidlarning joriy holati (bosqich+mas'ul), sana
        filtrsiz. Qarang: `CRMAdapter.get_active_leads_snapshot`."""
        if not CRM_API_KEY:
            return None

        timeout = httpx.Timeout(30.0, read=30.0)
        async with self._client(timeout=timeout) as client:
            try:
                records = await self._scan_active_leads(client, created_since_ts)
                if created_since_ts is not None:
                    # Tez rejimda Tashrif bosqichidagi eski lidlar ham qo'shiladi
                    # (dublikatlar quyida id bo'yicha yutiladi); to'liq skan
                    # ularni allaqachon qamraydi.
                    seen_ids = {r["id"] for r in records}
                    for record in await self._scan_visit_stage_leads(client):
                        if record["id"] not in seen_ids:
                            records.append(record)
                names = await self._load_pipe_status_names(client)
            except httpx.HTTPError:
                logger.exception(
                    "Uysot'dan faol-lidlar skanini olishda xatolik (created_since_ts=%s)", created_since_ts
                )
                return None

        out: list[dict] = []
        for record in records:
            status_id = record.get("pipeStatusId")
            if status_id is None:
                continue
            out.append(
                {
                    "id": record["id"],
                    "pipe_status_id": status_id,
                    "stage_name": names.get(status_id, f"Bosqich #{status_id}"),
                    "responsible_id": record.get("responsibleById"),
                    "responsible_name": record.get("responsibleBy"),
                    "updated_ts": record.get("updatedTimestamp"),
                }
            )
        return out

    @staticmethod
    def default_diff_lookback_ts() -> int:
        """Chegaralangan diff skani uchun standart "shu vaqtdan keyin yaratilgan"
        chegarasi (`CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS` kun orqaga)."""
        return int(time.time()) - CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS * 86400

    # "Lid tugadi" tekshiruvi sozlamalari: da'voni rad etish uchun shuncha ochiq lid
    # topilishi kifoya (erta to'xtash — skan tez tugaydi, sahifa chegarasiga bog'liq
    # emas). Sahifa chegarasi kattaroq (jonli bazada ochiq bosqichlarda ~1600 lid,
    # ya'ni ~32 sahifa) — "haqiqatan bo'sh" (True) hukmi to'liq skan talab qiladi.
    OPEN_LEAD_ENOUGH = 5
    MAX_OPEN_LEAD_PAGES = 60

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
        async with self._client(timeout=30) as client:
            try:
                while page <= self.MAX_OPEN_LEAD_PAGES:
                    resp = await _limited_request(
                        client, "POST", "/lead/filter",
                        json={
                            "page": page,
                            "size": LEAD_FILTER_PAGE_SIZE,
                            "pipeStatusIds": CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS,
                        },
                    )
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
        async with self._client(timeout=30) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await _limited_request(
                        client, "POST", "/lead/filter",
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

        async with self._client(timeout=20) as client:
            try:
                resp = await _limited_request(client, "GET", f"/lead/{lead_id}")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json().get("data") or {}
            except httpx.HTTPError:
                logger.exception("Uysot'dan lid detalini olishda xatolik (lead_id=%s)", lead_id)
                return None

        contact_name = None
        phones: list[str] = []
        for contact in data.get("contacts") or []:
            contact_name = contact_name or contact.get("name")
            for p in contact.get("phones") or []:
                if p and p not in phones:
                    phones.append(p)
        source = None
        for attribution in data.get("attributions") or []:
            channel = attribution.get("channel") or {}
            source = source or channel.get("source")

        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "contact_name": contact_name,
            # `phone` — birinchisi (ko'rsatish uchun), `phones` — BARCHA ma'lum
            # raqamlar (mijozning ikkinchi/uchinchi raqami bo'lishi mumkin —
            # operator qaysi biriga qo'ng'iroq qilgani noma'lum, hammasi tekshiriladi).
            "phone": phones[0] if phones else None,
            "phones": phones,
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
        async with self._client(timeout=20) as client:
            try:
                while page <= MAX_PAGES_PER_SYNC:
                    resp = await _limited_request(
                        client, "POST", "/call-history/filter",
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

        async with self._client(timeout=20) as client:
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

    async def get_daily_results_bulk(self, users, day: date) -> dict[int, dict | None]:
        """Kunlik qo'ng'iroq/tashrif ma'lumotini BIR MARTA yuklab, keyin xodimlarga
        taqsimlaydi.

        Nega kerak: `_load_day_call_counts` va `_load_day_visits` faqat KUNGA
        bog'liq (foydalanuvchiga emas) — ular butun kunning ma'lumotini
        sahifalab yuklaydi. Shuning uchun har xodim uchun alohida
        `get_daily_results` chaqirish xuddi shu og'ir yuklashni N marta
        takrorlardi (jonli o'lchov: 4 xodimda /daily-results/sync ~4.4s).
        cPanel'da Passenger'ning YAGONA ishchisi shu vaqt davomida band bo'lib,
        sayt so'rovlari navbatda kutardi."""
        if not CRM_API_KEY:
            return {u.id: {"conversations": 0, "visits": 0} for u in users}

        targets = [u for u in users if u.crm_external_id or u.crm_visit_external_id]
        out: dict[int, dict | None] = {
            u.id: {"conversations": 0, "visits": 0} for u in users if u.id not in {t.id for t in targets}
        }
        if not targets:
            return out

        async with self._client(timeout=20) as client:
            try:
                counts = await self._load_day_call_counts(client, day)
                visits_by_id = await self._load_day_visits(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan kunlik ma'lumot olishda xatolik (bulk, day=%s)", day)
                # Xatoda `None` — chaqiruvchi mavjud yozuvni ustidan yozmaydi
                # (bitta-bitta chaqiruvdagi bilan bir xil semantika).
                for u in targets:
                    out[u.id] = None
                return out

        for u in targets:
            conversations = counts.get(u.crm_external_id, 0) if u.crm_external_id else 0
            visits = (
                visits_by_id.get(u.crm_visit_external_id, {}).get("count", 0)
                if u.crm_visit_external_id
                else 0
            )
            out[u.id] = {"conversations": conversations, "visits": visits}
        return out

    async def get_all_daily_call_counts(self, day: date) -> dict[str, int]:
        """Botning `/statistika` buyrug'i uchun: shu kunda barcha operator/managerlarning
        (Uysot `employeeNum`i bo'yicha) qo'ng'iroqlar sonini qaytaradi."""
        if not CRM_API_KEY:
            return {}

        async with self._client(timeout=20) as client:
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

        async with self._client(timeout=20) as client:
            try:
                entries = await self._load_day_visits(client, day)
            except httpx.HTTPError:
                logger.exception("Uysot'dan tashrif operatorlarini olishda xatolik")
                return []

        return [
            {"responsible_id": responsible_id, "responsible_name": entry["name"], "visits": entry["count"]}
            for responsible_id, entry in entries.items()
        ]
