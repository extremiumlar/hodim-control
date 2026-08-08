# Sayt qotishi — sabab tahlili va yechim rejasi

> **Holat:** tahlil tugadi, amalga oshirish BOSHLANMAGAN.
> **Sana:** 2026-08-07 · **Tuzatildi:** 2026-08-08
> **Qamrov:** faqat 1-muammo — cPanel/Passenger deploy'idagi konkurentlik cheklovi.
> Boshqa aniqlangan muammolar (Face ID brauzer qotishi, Excel eksport)
> shu hujjatga KIRMAYDI — ular alohida ko'rib chiqiladi (oxirgi bo'limga qarang).

> ### ⚠️ 2026-08-08 TUZATISHI — BAZA HAQIDAGI DA'VOLAR XATO EDI
>
> Hujjat dastlab **production SQLite ishlatadi** deb yozgan edi. Bu **NOTO'G'RI**:
> production **PostgreSQL** (`DATABASE_URL=postgresql+asyncpg://...`), repodagi
> `app.db` esa 0 baytlik qoldiq fayl. Sabab: lokal `.env` va lokal (eski dev)
> SQLite sxemasi production deb qabul qilingan.
>
> **Nima o'zgardi:**
> - **10.2 «Indekslar yo'qligi» — BUTUNLAY BEKOR.** PostgreSQL'da kerakli
>   indekslar allaqachon bor (jonli tekshirildi).
> - **SQLite/WAL/qulf** bilan bog'liq barcha xavflar — productionga **tegishli emas**.
> - 1-muammoning o'zi (konkurentlik = 1) **o'zgarishsiz qoladi** — u jonli
>   zinapoya testi bilan tasdiqlangan, bazaga bog'liq emas.

---

## 1. Qisqa xulosa (TL;DR)

Jonli deploy'da FastAPI **async bo'lsa ham, bir vaqtda ATIGI 1 ta so'rov ishlanadi**.
Shu bilan birga cron har 2 daqiqada saytga 30-45 soniyalik HTTP so'rov yuboradi.
Natijada sayt **soatiga ~17-20 daqiqa butunlay javob bermaydi** — bu "sekinlashish"
emas, to'liq to'xtash.

Eng yomon holatda (Uysot 429 qaytarsa) bitta so'rov ichida **4 daqiqagacha** kutiladi
va shu vaqt davomida sayt umuman ochilmaydi.

**Yechim yo'nalishi:** cron bilan API o'rtasidagi HTTP bog'liqlikni butunlay uzish —
og'ir joblarni cron jarayonining O'ZIDA (in-process) bajarish. Bu naqsh loyihada
allaqachon bor va ishlayapti (`hot_lead`, `idle_watch`, `lead_sync`, `lead_diff`),
shunchaki oxiriga yetkazilmagan.

---

## 2. Simptom

- Sayt goh-goh "qotadi", 25+ soniya javob bermaydi, keyin o'ziga keladi.
- Ba'zan bir necha daqiqa umuman ochilmaydi.
- Qotish **davriy** — tasodifiy emas.
- Bot ham, mobil ilova ham (WebView orqali) o'sha paytda sekinlashadi.

Bu simptomlar kod izohlarida allaqachon qayd etilgan
([`scripts/cron_tick.py:87-95`](scripts/cron_tick.py:87)):

> «...yagona ishchini to'ldirib qo'yardi va shu paytda kelgan sayt/bot so'rovlari
> navbatda qotib, 25s+ timeout berardi.»

Ya'ni muammo ilgari qisman aniqlangan va qisman hal qilingan — lekin **ildizi
saqlanib qolgan**.

---

## 3. Sabab — 3 qatlam

### 3.1. Qatlam 1 — Deploy arxitekturasi: konkurentlik = 1

#### Nima bo'lyapti

FastAPI — ASGI ilova. cPanel Passenger esa **WSGI** kutadi. Ko'prik sifatida
`a2wsgi.ASGIMiddleware` ishlatiladi
([`deploy/cpanel/passenger_wsgi.py:216`](deploy/cpanel/passenger_wsgi.py:216)):

```python
def application(environ, start_response):
    global _wrapped
    if _wrapped is None:
        from a2wsgi import ASGIMiddleware
        _wrapped = ASGIMiddleware(_build_target())
    return _wrapped(environ, start_response)
```

`a2wsgi` manbasini o'qidim (`a2wsgi/asgi.py:128-140`):

```python
if loop is None:
    loop = asyncio.new_event_loop()
    loop_threading = threading.Thread(target=loop.run_forever, daemon=True)
    loop_threading.start()
```

Ya'ni: **bitta fon event-loop thread** yaratiladi. Har WSGI so'rovi shu loop'ga
topshiriladi va **chaqiruvchi WSGI thread bloklanib kutadi** (`ASGIResponder`
`SyncEvent` bilan sinxronlashtiradi).

#### Nega bu halokatli

Konkurentlik = **Passenger bir vaqtda nechta WSGI chaqiruv qila olsa, shuncha**.
Bu hostda Passenger'ga **1 ta ishchi jarayon** berilgan (loyiha izohlarida uch
joyda qayd etilgan: `cron_tick.py:87`, `keepalive_bot.sh:6`, `uysot.py:80`).
Passenger'ning Python qo'llab-quvvatlashi jarayon modelida ishlaydi (thread
modeli emas), ya'ni:

> **1 jarayon × 1 thread = bir vaqtda 1 ta so'rov.**

FastAPI'ning butun async arxitekturasi bu yerda **hech qanday foyda bermaydi**.
`await` paytida event loop bo'sh turadi, lekin yangi so'rov kira olmaydi — chunki
yagona WSGI thread bloklangan.

#### Muhim nuans

Agar Passenger ko'p **thread** bergan bo'lsa edi, a2wsgi'ning yagona loop'i
ularning hammasini bemalol multiplekslay olardi (kod haqiqatan async). Ya'ni
muammo a2wsgi'da EMAS — Passenger'ning jarayon/thread konfiguratsiyasida.
Bu 5-yechim variantiga bevosita aloqador.

---

### 3.2. Qatlam 2 — Cron API'ga HTTP orqali murojaat qiladi

`scripts/cron_tick.py` har daqiqada ishga tushadi va o'sha **yagona ishchiga**
HTTP so'rov yuboradi (`scheduler/client.py:call_api` orqali).

#### Hozirgi HTTP joblar jadvali ([`_due()`](scripts/cron_tick.py:71))

| Chastota | Endpoint | Taxminiy davomiylik |
|---|---|---|
| **har daqiqa** | `/stats/lead-stages/group-tick` | ~1-2s |
| **har daqiqa** | `/attendance/digest-tick` | ~1-2s |
| **har toq daqiqa** (30×/soat) | `/daily-results/sync` | **30-45s** ⚠️ |
| **har toq daqiqa** (30×/soat) | `/anketa/tick` | ~1s |
| m%5==3 (12×/soat) | `/knowledge/tick` | ~1s (no-op) |
| m%5==3 (12×/soat) | `/playbook/tick` | ~1s (no-op) |
| m%15==0 (4×/soat) | `/tasks/mark-overdue` | <1s |
| m%15==0 (4×/soat) | `/auto-plan/snapshot` | ~1s (AI o'chiq → no-op) |
| m%30==17 (2×/soat) | `/system-health/tick` | ~1s |
| m%N==1 | `/attendance/reminder-tick` | ~2-5s |
| m==0 (1×/soat) | `/hourly-plan/send` | ~1-2s |
| m==0 (1×/soat) | `/auth/login-security-cleanup` | <1s |

#### Nega `/daily-results/sync` 30-45 soniya

[`api/routers/daily_results.py:173`](api/routers/daily_results.py:173) →
[`crm/uysot.py:926`](crm/uysot.py:926) `get_daily_results_bulk`:

1. `_load_day_call_counts` — Uysot `/call-history/filter` sahifalab o'qiydi,
   `MAX_PAGES_PER_SYNC = 20` sahifagacha ([`uysot.py:22`](crm/uysot.py:22))
2. Har so'rov `_SharedRateBudget(50/daqiqa)` slotini oladi →
   **so'rovlar orasida 1.2s majburiy pauza** ([`uysot.py:88-93`](crm/uysot.py:88))
3. Keyin `_load_day_visits` — yana bir necha sahifa
4. Undan keyin xodimlar bo'yicha **N+1 halqa**
   ([`daily_results.py:209`](api/routers/daily_results.py:209))

**Hisob:** 20 sahifa × 1.2s = 24s (faqat pauza) + tarmoq kechikishi (~0.3-1s/so'rov)
+ tashrif sahifalari + N+1 → **30-45 soniya**.

Kun oxiriga borib qo'ng'iroqlar ko'payadi → sahifalar soni ortadi → **kechqurun
qotish uzayadi**. Bu foydalanuvchi sezadigan naqsh bilan mos.

#### Miqdoriy baho

```
/daily-results/sync : 30 marta/soat × ~35s     ≈ 17.5 daq/soat
har daqiqalik 2 tick: 60 marta/soat × ~2s      ≈  2.0 daq/soat
qolganlari                                      ≈  1.0 daq/soat
──────────────────────────────────────────────────────────────
JAMI                                            ≈ 20 daq/soat
```

> **Soatiga ~20 daqiqa (33%) sayt to'liq bloklangan.**

---

### 3.3. Qatlam 3 — So'rov ichida cheksizga yaqin kutish

[`crm/uysot.py:38-39`](crm/uysot.py:38):

```python
RATE_LIMIT_BACKOFF_SECONDS = 60
MAX_RATE_LIMIT_RETRIES = 4
```

Uysot 429 qaytarsa, `_limited_request` **60 soniya kutadi va 4 martagacha qayta
uriniladi** ([`uysot.py:118-151`](crm/uysot.py:118)).

> Bitta HTTP so'rov ichida **4 daqiqagacha** kutish. Shu 4 daqiqa davomida sayt
> **butunlay o'lik** — hech kim kira olmaydi, hech kim «Keldim» bosa olmaydi.

Bu — «sayt umuman ochilmayapti» shikoyatining bevosita manbai.

`RATE_LIMIT_BACKOFF_SECONDS = 60` fon skanerlari uchun **to'g'ri** qiymat
(Uysot limiti daqiqalik oynada). Lekin **HTTP so'rov kontekstida** u mutlaqo
noto'g'ri — u yerda so'rov tez muvaffaqiyatsiz bo'lishi kerak.

---

### 3.4. Yon ta'sir: 429 bo'roni strukturaviy

`_SharedRateBudget` — **jarayon-ichi** mexanizm
([`uysot.py:71-80`](crm/uysot.py:71), izohda o'zi tan olingan).

Hozir Uysot'ga **3 ta mustaqil jarayon** chiqadi:

| Jarayon | Nima chaqiradi | O'z byudjeti |
|---|---|---|
| `cron_tick.py` | lead_sync, lead_diff, hot_lead, idle_watch | 50/daq |
| Passenger ishchisi | `/daily-results/sync`, AI joblar | 50/daq |
| Bot (`BOT_INPROCESS_API=true`) | `/statistika` va h.k. | 50/daq |

**Jami potensial: 150 so'rov/daqiqa.** Uysot limiti esa 60/daqiqa.

Ya'ni 429 bo'ronlari **tasodif emas, strukturaviy**. Va har 429 → 60s cooldown →
3.3-qatlamdagi 4 daqiqalik qotish.

**Muhim bog'liqlik:** `/daily-results/sync`ni cron jarayoniga ko'chirish 3 ta
jarayondan 2 tasini birlashtiradi → byudjet 150 dan 100 ga tushadi → 429 chastotasi
ham kamayadi. Ya'ni bitta o'zgarish **ikki muammoni** birdan yumshatadi.

---

## 4. Yechim variantlari

| # | Yechim | Ta'sir | Xavf | Mehnat | Qaror |
|---|---|---|---|---|---|
| 1 | `/daily-results/sync` + `/anketa/tick` → in-process | 🟢 Juda katta | Past | O'rta | ✅ QILAMIZ |
| 2 | Qolgan BARCHA ticklar → in-process | 🟢 Katta | Past | O'rta | ✅ QILAMIZ |
| 3 | 429 backoff'ga so'rov-ichi chegara | 🟡 O'rta | Past | Kichik | ✅ QILAMIZ (birinchi) |
| 4 | Cron o'rniga doimiy scheduler jarayoni | 🟢 Katta | O'rta | O'rta | ⏸ Keyinroq |
| 5 | Passenger ishchilarini ko'paytirish | 🟡 Noaniq | ⚠️ Yuqori | Kichik | ❌ Rad |
| 6 | Passenger'ni chetlab o'tish (uvicorn + proxy) | 🟢 To'liq | ⚠️ Yuqori | Katta | ⏸ Aniqlashtirilsin |

### 4.1. Nega 5-variant rad etildi

Passenger ishchilarini ko'paytirish (agar hosting bersa ham) **yangi muammolar**
keltiradi:

- `_SharedRateBudget` ishchi soniga bo'linishi kerak — kod izohida o'zi yozilgan
  ([`uysot.py:80`](crm/uysot.py:80)): *«API ko'p-worker qilinsa byudjetni worker
  soniga bo'lish kerak bo'ladi»*
- ~~SQLite yozuv to'qnashuvi ortadi, WAL esa o'chiq~~ — **BEKOR (2026-08-08)**:
  production **PostgreSQL** ishlatadi, ya'ni bu xavf yo'q (pastdagi 6-bo'limga qarang)
- Xotira: bitta ishchi **225 MB**, LVE limiti **1 GB** → realistik maksimum **3 ta**
- cPanel "Setup Python App" bu sozlamani odatda **umuman ko'rsatmaydi**

Ya'ni asosiy to'siq — **rate byudjet** (2.2) va xotira; baza emas.

### 4.2. 6-variant — aniqlashtirish kerak

SSH manzili `167.235.222.200:30151` — bu **Hetzner** IP oralig'i, ya'ni bu haqiqiy
server bo'lishi mumkin (begona shared hosting emas). Agar root huquqi bo'lsa,
Passenger'ni umuman chetlab o'tish real: doimiy `uvicorn` jarayoni + nginx/Apache
`ProxyPass`. Loyihada `docker-compose.yml` va `deploy/nginx-production.conf`
allaqachon tayyor turibdi.

> ❓ **Ochiq savol:** serverda root huquqi bormi? Javob "ha" bo'lsa, 6-variant
> butun muammoni ildizi bilan yopadi va 1-2-3 vaqtinchalik chora bo'lib qoladi.
> Javob "yo'q" bo'lsa, 1-2-3 — yagona to'g'ri yo'l.

---

## 5. Amalga oshirish rejasi

### Umumiy tamoyil

Har bosqich **mustaqil deploy qilinadi va alohida tekshiriladi**. Bir bosqich
buzilsa, faqat o'sha qaytariladi.

Barcha HTTP endpointlar **saqlanib qoladi** — ular Docker/scheduler rejimi uchun
kerak (`scheduler/main.py` ularni chaqiradi). Faqat `cron_tick.py` ularni HTTP
o'rniga to'g'ridan-to'g'ri chaqiradi.

**Mavjud naqsh** ([`cron_tick.py:271`](scripts/cron_tick.py:271)):

```python
async def _run_service_inprocess(now, label, lock, stale_min, runner) -> None:
    """Lock oladi, servisni shu jarayonda bajaradi, natija/xatoni log'ga yozadi."""
```

Bu naqsh `hot_lead` va `idle_watch` uchun **jonli ishlayapti**. Yangi joblar aynan
shu qolipga tushadi.

---

### Bosqich 0 — O'lchov (kod o'zgarmaydi)

**Maqsad:** tuzatishdan OLDIN haqiqiy raqamlarni qayd etish, keyin solishtirish uchun.

**Qadamlar:**

1. Serverda `logs/cron.log` dan oxirgi 24 soatni olish.
2. Har tick'ning haqiqiy davomiyligini o'lchash — `cron_tick.py`ga vaqtinchalik
   `time.monotonic()` bilan log qo'shish (yoki mavjud loglardan hisoblash).
3. Saytdan bir necha o'lchov: toq daqiqada va juft daqiqada `/health` javob vaqti.

**Natija:** «avval» raqamlari yozib qo'yiladi (masalan: toq daqiqada `/health`
32s, juft daqiqada 0.2s).

**Nega kerak:** tuzatishdan keyin foydani isbotlash uchun. Aks holda «yaxshi
bo'ldiga o'xshaydi» darajasida qolamiz.

---

### Bosqich 1 — 429 backoff'ga so'rov-ichi chegara ⚡ (eng tez foyda)

**Muammo:** HTTP so'rov ichida 4 daqiqagacha kutish (3.3-bo'lim).

**Yechim:** `_limited_request` ga «kontekst» tushunchasi kiritish:

- **Fon rejimi** (cron in-process skanerlar): hozirgidek — 60s × 4 retry.
  Ular hech kimni kutdirmaydi, sabr qilishi to'g'ri.
- **So'rov rejimi** (HTTP endpoint ichidan): qattiq chegara, masalan **jami 10
  soniya**. Undan oshsa — 429 xatoni yuqoriga qaytarish, chaqiruvchi
  «CRM band, keyinroq» deb yopiladi.

**Tegiladigan fayl:** [`crm/uysot.py`](crm/uysot.py) — `_limited_request` va
`_SharedRateBudget`.

**Amalga oshirish eskizi:**

```python
# Modul darajasida — jarayon turini bir marta aniqlash o'rniga,
# ANIQ chaqiruv joyidan uzatiladi (aniqroq va sinovga qulay).
import contextvars

_REQUEST_CONTEXT = contextvars.ContextVar("uysot_request_context", default=False)

MAX_INREQUEST_WAIT_SECONDS = 10  # HTTP so'rov ichida jami kutish chegarasi
```

`_limited_request` ichida: agar `_REQUEST_CONTEXT.get()` rost bo'lsa —
`RATE_LIMIT_BACKOFF_SECONDS` o'rniga qolgan byudjetni ishlatish va u tugasa
`raise`.

`contextvars` tanlangani sabab: asyncio'da har so'rov o'z kontekstini oladi,
global bayroq esa jarayonda aralashib ketardi.

HTTP endpointlar (`api/routers/*.py`) CRM chaqirishidan oldin
`_REQUEST_CONTEXT.set(True)` qiladi — buni bitta FastAPI middleware yoki
dependency bilan markazlashtirish mumkin.

**Sinov:**
- Uysot'ni sun'iy 429 qaytaradigan qilib mock qilish → HTTP endpoint ≤10s da
  xato qaytarishi kerak, cron in-process yo'l esa hozirgidek sabr qilishi kerak.
- `scripts/tests/` da mavjud sinov uslubiga mos test yozish.

**Rollback:** bitta faylning bitta funksiyasi — `git revert`.

**Kutilgan natija:** eng yomon holatdagi 4 daqiqalik o'lik holat **yo'qoladi**.
O'rtacha holat o'zgarmaydi (bu himoya chorasi, tezlashtiruvchi emas).

---

### Bosqich 2 — `/daily-results/sync` → in-process 🎯 (asosiy foyda)

**Muammo:** soatiga ~17.5 daqiqa qotish (3.2-bo'lim).

#### 2a. Mantiqni servisga ko'chirish

Hozir mantiq **router funksiyasi ichida**
([`daily_results.py:173-235`](api/routers/daily_results.py:173)).

**Yangi fayl:** `api/services/daily_results_sync.py`

```python
async def sync_from_crm(db: AsyncSession) -> dict:
    """CRM'dan bugungi kunlik natijalarni o'qib bazaga yozadi.
    Router ham, cron_tick ham SHU funksiyani chaqiradi."""
    ...
```

Router yupqa o'ramga aylanadi:

```python
@router.post("/daily-results/sync", dependencies=[Depends(verify_bot_secret)])
async def sync_daily_results(db: AsyncSession = Depends(get_db)) -> dict:
    return await sync_from_crm(db)
```

> ⚠️ Ko'chirishda mantiq **o'zgarmasligi** shart — bu faqat joy almashtirish.
> Xususan: `source == manual` yozuvlarni ustidan yozmaslik qoidasi
> ([`daily_results.py:212`](api/routers/daily_results.py:212)) va CRM xatosida
> `None` semantikasi saqlanishi kerak.

#### 2b. N+1 halqani tuzatish (shu yerda, chunki baribir tegilyapti)

[`daily_results.py:209`](api/routers/daily_results.py:209) — har xodim uchun
alohida `db.scalar`. Bitta so'rovga birlashtirish:

```python
existing_by_user = {
    r.user_id: r
    for r in await db.scalars(
        select(DailyResult).where(
            DailyResult.date == today,
            DailyResult.user_id.in_([e.id for e in employees]),
        )
    )
}
```

#### 2c. `cron_tick.py`ga in-process yo'l qo'shish

```python
DAILY_SYNC_LOCK = ROOT / "logs" / "daily_sync.lock"
DAILY_SYNC_LOCK_STALE_MINUTES = 8


async def _run_daily_sync_inprocess(now: datetime) -> None:
    async def runner(db):
        from api.services.daily_results_sync import sync_from_crm
        return await sync_from_crm(db)

    await _run_service_inprocess(
        now, "kunlik natijalar", DAILY_SYNC_LOCK, DAILY_SYNC_LOCK_STALE_MINUTES, runner
    )
```

`_due()` dan `add("/daily-results/sync", timeout=120)` **olib tashlanadi**,
`main()` ga qo'shiladi:

```python
if now.minute % 2 == 1:
    await _run_daily_sync_inprocess(now)
```

**Lock SHART:** 35 soniyalik job 2 daqiqalik intervalga sig'adi, lekin 429
cooldown'da cho'zilishi mumkin — keyingi tick boshlanmasin.

#### 2d. Tartib masalasi

`main()` da chaqiruv tartibi muhim: **yengil, vaqt-sezgir ishlar avval**, og'irlari
keyin (hozirgi `urgent`/`rest` mantig'i bilan bir xil falsafa).

```
1. Vaqt-sezgir ticklar (digest'lar)
2. hot_lead / idle_watch
3. daily_sync            ← YANGI, og'ir
4. lead_sync / lead_diff ← og'ir
5. heartbeat
```

#### 2e. Heartbeat masalasi

`_write_heartbeat` sikl **oxirida** yoziladi. In-process joblar qo'shilgach sikl
uzayadi. Tashqi qo'riqchi chegarasi `MAX_CRON_AGE=1200` (20 daqiqa,
[`.github/workflows/watchdog.yml:42`](.github/workflows/watchdog.yml:42)) —
2-3 daqiqalik sikl uchun **zaxira yetarli**, o'zgartirish kerak emas.

Lekin tekshirish kerak: eng og'ir kombinatsiya (daily_sync + lead_sync + diff bir
tick'da) 20 daqiqadan oshmasin. Lock'lar buni qisman kafolatlaydi, lekin
Bosqich 5 da o'lchanadi.

**Sinov:**
- Lokal: `python scripts/cron_tick.py` qo'lda ishga tushirib, log'da
  `kunlik natijalar (in-process): {...}` chiqishini tekshirish.
- Serverda: bir soat kuzatish, `logs/cron.log` da xato yo'qligini tasdiqlash.
- Bazada `daily_results` yozuvlari avvalgidek yangilanayotganini tekshirish.

**Rollback:** `_due()` ga bitta qatorni qaytarish + `main()` dan olib tashlash.
Servis fayli qolaveradi (zarari yo'q).

**Kutilgan natija:** soatiga ~17.5 daqiqa qotish **yo'qoladi**. Bu — butun
rejaning asosiy foydasi.

---

### Bosqich 3 — `/anketa/tick` → in-process

**Hozirgi holat:** [`anketa.py:915`](api/routers/anketa.py:915) — router ichida
kichik halqa (`_start_session`). Og'ir emas (~1s), lekin `/daily-results/sync`
bilan **bir xil toq daqiqada** ishlaydi.

**Qadamlar:** Bosqich 2 bilan bir xil qolip:
1. `tick` mantig'ini `api/services/anketa_data.py` ga (yoki yangi
   `api/services/anketa_tick.py`) ko'chirish.
2. Router yupqa o'ramga aylanadi.
3. `cron_tick.py` da `_run_service_inprocess` bilan chaqirish.

> ⚠️ `_start_session` Telegram'ga xabar yuboradi. Cron jarayonida bot tokeni bor
> (hot_lead allaqachon xabar yuboradi) — qo'shimcha sozlash kerak emas, lekin
> **birinchi ishga tushirishda tasdiqlash shart**.

---

### Bosqich 4 — Qolgan ticklarni ko'chirish

Maqsad: **Passenger'ga cron trafigi umuman tegmasin.**

#### 4a. Yupqa o'ramlar (refaktor KERAK EMAS — darhol ko'chiriladi)

Bular allaqachon servisga to'g'ridan-to'g'ri chaqiruv:

| Endpoint | Servis chaqiruvi | Fayl |
|---|---|---|
| `/attendance/digest-tick` | `digest_tick(db)` | [`attendance.py:1121`](api/routers/attendance.py:1121) |
| `/playbook/tick` | `svc.process_build(db)` | [`playbook.py:109`](api/routers/playbook.py:109) |
| `/system-health/tick` | `system_health.tick(db, dry_run)` | [`system_health.py:20`](api/routers/system_health.py:20) |
| `/auto-plan/snapshot` | `auto_plan.snapshot_hourly_actual(db, d)` | [`auto_plan.py:23`](api/routers/auto_plan.py:23) |

#### 4b. Kichik ko'chirish kerak

| Endpoint | Router ichidagi mantiq | Murakkablik |
|---|---|---|
| `/tasks/mark-overdue` | bitta `UPDATE` | Juda oson |
| `/auth/login-security-cleanup` | 3 ta `DELETE` | Juda oson |
| `/knowledge/tick` | `count` + servis | Oson |
| `/stats/lead-stages/group-tick` | `_get_group_config` + `send_daily_digest` | O'rta |
| `/attendance/reminder-tick` | halqa + audit | O'rta |
| `/hourly-plan/send` | ish oynasi tekshiruvi | O'rta |

#### 4c. Yakuniy holat

`cron_tick.py` da `call_api` **umuman ishlatilmaydi**. `scheduler/client.py` va
`API_BASE_URL` faqat Docker/scheduler rejimi uchun qoladi.

> 💡 Shu nuqtada `cron_tick.py` va `scheduler/main.py` bir-biriga juda o'xshab
> qoladi — bu 4-variantga (doimiy scheduler jarayoni) tabiiy o'tish nuqtasi.

**Diqqat:** vaqt-sezgir ticklar (`digest-tick`, `group-tick`) har daqiqa ishlaydi
va **tez** — ularga lock kerak emas (yoki juda qisqa stale bilan). Og'irlariga
lock SHART.

---

### Bosqich 5 — Tekshirish va o'lchash

1. **Bosqich 0 raqamlari bilan solishtirish** — toq daqiqada `/health` javob vaqti
   30s+ dan 1s gacha tushishi kerak.
2. **`logs/cron.log`** — 24 soat davomida xato/timeout yo'qligi.
3. **Cron sikli davomiyligi** — eng og'ir kombinatsiyada 20 daqiqadan oshmasligi
   (`MAX_CRON_AGE` chegarasi).
4. **429 chastotasi** — avval/keyin solishtirish (byudjet 150→100 ga tushgani
   sezilishi kerak).
5. **Funksional regressiya** — har ko'chirilgan job haqiqatan ishlayotganini
   tasdiqlash:
   - kunlik natijalar bazada yangilanyaptimi
   - anketa sessiyalari boshlanyaptimi
   - digest'lar guruhga kelyaptimi
   - eslatmalar yuborilyaptimi

---

## 6. Kutilgan yakuniy natija

| Ko'rsatkich | Hozir | Bosqich 4 dan keyin |
|---|---|---|
| Sayt bloklangan vaqt | ~20 daq/soat (33%) | ~0 |
| Eng yomon qotish | 4 daqiqa | ~0 (foydalanuvchi so'rovlari qisqa) |
| Uysot byudjeti | 150/daq (limit 60) | 100/daq |
| Passenger'ga cron yuki | 12 xil job | **0** |

**Diqqat:** konkurentlik baribir **1 ta so'rov** bo'lib qoladi. Ya'ni og'ir
FOYDALANUVCHI so'rovi (masalan Excel eksport — 2-muammo) baribir saytni bloklaydi.
Bu reja **cron kelib chiqadigan** qotishni yopadi, deploy arxitekturasini emas.
To'liq yechim uchun 4- yoki 6-variant kerak.

---

## 7. Xavflar va ehtiyot choralari

| Xavf | Ehtimol | Yumshatish |
|---|---|---|
| Ko'chirishda mantiq buzilishi | O'rta | Har bosqich alohida deploy + sinov; mantiq O'ZGARMAYDI, faqat joyi |
| Cron sikli 20 daqiqadan oshishi | Past | Lock'lar + Bosqich 5 da o'lchash |
| Cron jarayonida Telegram/CRM sozlamalari yetishmasligi | Past | hot_lead allaqachon ishlayapti — muhit tayyor |
| Bir job xatosi butun tick'ni yiqitishi | Past | `_run_service_inprocess` har jobni `try/except` bilan o'raydi |
| Docker/scheduler rejimi buzilishi | Past | HTTP endpointlar saqlanadi, `scheduler/main.py` tegilmaydi |

**Deploy tartibi:** har bosqich alohida commit + alohida deploy. Ketma-ket emas,
**bir-biridan keyin tasdiqlash bilan**.

---

## 8. Bajarilish ketma-ketligi (qisqacha)

```
[ ] Bosqich 0 — o'lchov (kod o'zgarmaydi)
[ ] Bosqich 1 — 429 so'rov-ichi chegara          ← eng tez, eng xavfsiz
[ ] Bosqich 2 — /daily-results/sync in-process   ← ASOSIY FOYDA
[ ] Bosqich 3 — /anketa/tick in-process
[ ] Bosqich 4 — qolgan 10 ta tick
[ ] Bosqich 5 — tekshirish va o'lchash
```

---

## 9. Ochiq savollar

1. **Serverda root huquqi bormi?** (167.235.222.200 — Hetzner IP)
   - Ha → 6-variant ko'rib chiqilsin, bu reja vaqtinchalik chora bo'ladi
   - Yo'q → bu reja yagona to'g'ri yo'l
2. **Passenger ishchilar sonini oshirish imkoni bormi?** (aniqlash arziydi,
   lekin 4.1-bo'limdagi sabablarga ko'ra baribir tavsiya qilinmaydi)
3. **4-variantga (doimiy scheduler) o'tish qachon?** Bosqich 4 dan keyin foyda
   kamayadi — shoshilinch emas, lekin `cron_tick.py` murakkabligini yo'qotadi.

---

## 10. Bu hujjatga KIRMAGAN muammolar

Sayt qotishi tekshiruvida yana 3 ta mustaqil muammo aniqlandi. Ular **alohida**
ko'rib chiqiladi:

### 10.1. Face ID — brauzer qotishi (mustaqil, yuqori muhimlik)

- [`FaceCapture.tsx:140`](web/src/components/FaceCapture.tsx:140) —
  `setInterval(800ms)` **in-flight guard'siz**: aniqlash 800ms dan uzoq cho'zilsa
  chaqiruvlar ustma-ust to'planadi
- O'sha halqada `withFaceDescriptor()` chaqiriladi — **6.4MB'lik eng og'ir model**,
  holbuki preview'ga faqat `box` va `score` kerak
- [`face.ts:417-440`](web/src/lib/face.ts:417) — tiriklik sinovi 18 soniya davomida
  har freymda descriptor hisoblaydi (oxirida faqat bittasi kerak)

### 10.2. ~~Indekslar yo'qligi~~ — ❌ BEKOR QILINDI (2026-08-08)

> **Bu bo'lim XATO edi.** Men **lokal `app.db`** (eski dev SQLite) sxemasini
> o'qib, uni production deb hisoblagandim. Production esa **PostgreSQL**
> (`DATABASE_URL=postgresql+asyncpg://...`; repodagi `app.db` — 0 baytlik qoldiq).
>
> Jonli PostgreSQL tekshiruvi (2026-08-08) **indekslar borligini** ko'rsatdi:

| Jadval | Qatorlar | Indekslar |
|---|---|---|
| `lead_events` | 10 925 | pkey, `crm_lead_id`, `event_type`, **`detected_at`** ✅ |
| `hot_lead` | 1 100 | pkey, `crm_lead_id`, `user_id`, **`status`** ✅ |
| `attendance` | 140 | pkey, uq(user_id,date), `user_id`, **`date`**, `status` ✅ |
| `hourly_actual` | 1 004 | pkey, uq, `user_id`, `date` ✅ |
| `lead_stage_daily` | 1 195 | pkey, uq, `date` ✅ |
| `crm_webhook_log` | 4 | pkey, `received_at` ✅ |
| `audit_logs` | 438 | pkey, `actor_id`, `action` — `created_at` yo'q |
| `crm_lead_state` | 11 011 | faqat pkey (`crm_lead_id`) |

**Qoldiq (juda kichik):** `audit_logs.created_at` indeksi yo'q — lekin jadval
438 qator, ya'ni amalda muammo emas. `crm_lead_state` faqat PK bo'yicha
so'raladi — indeks yetarli.

**Saboq:** lokal `.env`/baza production bilan bir xil emas. Sxema da'volari
faqat **jonli bazadan** tekshirilsin.

### 10.2b. SQLite/WAL bo'yicha barcha da'volar ham BEKOR

`db/base.py:32-42` dagi WAL izohi **lokal SQLite** rejimiga tegishli.
Productionda PostgreSQL ishlaydi — MVCC bor, «yozuvchi o'quvchini bloklaydi»
muammosi **yo'q**, `busy_timeout` ham ahamiyatsiz.

### 10.3. Excel eksport — event loop'ni bloklaydi

- [`export.py:157-215`](api/services/export.py:157) — har xodim uchun 5+ so'rov
- [`export.py:277`](api/services/export.py:277), [`407`](api/services/export.py:407) —
  `wb.save()` sinxron CPU ishi, `to_thread`siz
- Konkurentlik 1 bo'lgani uchun eksport **butun saytni** muzlatadi

> ⚠️ 10.3 aynan shu hujjatdagi 1-muammo bilan bir xil ildizdan (konkurentlik = 1)
> kelib chiqadi, lekin tuzatilishi boshqacha — shuning uchun alohida.

---

*Hujjat 2026-08-07 da tuzildi. Kod holati: `xavfsizlik-tuzatishlar` tarmog'i,
`8eb4243`.*
