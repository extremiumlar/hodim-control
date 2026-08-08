# Tahlil topshiriqlari — 18 bo'lim uchun alohida kartalar

> **Bu hujjat nima:** [CHUQUR_TAHLIL_METODIKASI.md](CHUQUR_TAHLIL_METODIKASI.md) dagi
> 9 bosqichli usul **har bir bo'limga alohida** qo'llangan holati.
>
> **Qanday ishlatiladi:** metodika promptini bering, so'ng shu hujjatdan **BITTA**
> kartani qo'shib bering. Karta yopilmaguncha keyingisiga o'tmang.
>
> **Kartadagi «Ma'lum dalillar»** — 2026-08-07 dagi tekshiruvda topilgani.
> Agent ularni qaytadan qidirmasin, lekin **tasdiqlasin** (ko'r-ko'rona ishonmasin).
>
> **Kartadagi «⚠️ Kutilayotgan yuzaki yechim»** — eng muhim qism. Agent aynan
> shuni taklif qilsa, tahlil chuqur emas — qaytaring.

**Jami: 18 bo'lim / 5 ildiz.**

---

# ILDIZ 1 — Deploy arxitekturasi: konkurentlik = 1

---

## 1.1 — Passenger atigi 1 ta ishchi beradi

| | |
|---|---|
| **Simptom** | Bir vaqtda kelgan so'rovlar navbat bilan ishlanadi, parallel emas |
| **Ustuvorlik** | Ildiz — qolgan 1.x hammasi shunga tayanadi |
| **Bog'liq** | 1.2, 1.3, 1.5 (hammasi shu shift tufayli og'riydi), 2.2 (ishchi qo'shilsa buziladi) |

**Ma'lum dalillar**
- Jonli test: 6 parallel `GET /health` → 2.77 / 3.01 / 3.52 / 4.02 / 4.52 / 5.02s — mukammal zinapoya
- `ps` da atigi 1 ta `wsgi-loader.py`, RSS **225 MB**
- `~/public_html/.htaccess` — CloudLinux Passenger bloki: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerPython`. **Ishchi soniga oid direktiva YO'Q**
- Tarif (LVE): EP **40**, NPROC **80**, PMEM **1 GB**, CPU **100% (1 yadro)**
- `a2wsgi/asgi.py:128-140` — bitta fon event-loop thread, chaqiruvchi WSGI thread bloklanadi

**NOMA'LUM — agent aniqlashi shart**
- Server-darajadagi `PassengerMaxPoolSize` qiymati nima? (Bizga ko'rinadimi?)
- `.htaccess` da `PassengerMinInstances` **qabul qilinadimi**? `AllowOverride` ruxsat beradimi?
- Passenger **autoscaling** umuman ishlaydimi bu o'rnatmada, yoki qattiq 1 ga qotirilganmi?
- 3 ta ishchi 1 GB ichida haqiqatan sig'adimi? (225 MB × 3 = 675 MB + cron + bot)

**2-bosqich: nimani o'lchash**
- Zinapoya testini **uzunroq yuk** bilan takrorla (masalan 30 soniya davomida sekundiga 2 so'rov) — qisqa burst autoscaling'ni uyg'otmagan bo'lishi mumkin
- Har ishchining haqiqiy RSS'ini yuk ostida o'lcha (bo'sh turgandagi 225 MB emas)

**3-bosqich: zanjir qayerdan boshlanadi**
> Parallel so'rov yo'q → 1 ta jarayon → **nega faqat 1?** → (Passenger default? host qotirgan? autoscaling shartlari bajarilmadi?) → **nega shunday sozlangan?** → ...

**4-bosqich: rad etish testi**
> «Balki Passenger **autoscale qiladi**, men esa juda qisqa (3 soniyalik) burst berdim va u ulgurmadi.»
> — Uzoq davomli yuk bilan qayta sina. Jarayon soni oshsa — diagnozim noto'g'ri edi.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «`.htaccess` ga `PassengerMinInstances 5` yozamiz» — xotira (1 GB) va rate byudjet (2.2) oqibatini hisoblamasdan
- ❌ «Hostingni yuqoriroq tarifga ko'taring» — tarif limitlari (EP 40, NPROC 80) allaqachon **yetarli** ekani aniqlangan
- ❌ Direktivani qo'shib, `.htaccess` xatosi butun saytni 500 qilishi mumkinligini aytmaslik

---

## 1.2 — Cron HTTP orqali yagona ishchini bloklaydi

| | |
|---|---|
| **Simptom** | Sayt davriy ravishda 25-45 soniya javob bermaydi |
| **Ustuvorlik** | Eng katta o'lchanadigan zarar (~20 daq/soat) |
| **Bog'liq** | 1.1 (shift), 2.2 (rate byudjet), 1.4 (429) |

**Ma'lum dalillar**
- [`scripts/cron_tick.py:71`](scripts/cron_tick.py:71) `_due()` — 12 xil HTTP job
- `/daily-results/sync` **har toq daqiqada**, kod izohida «~30-40s» deyilgan
- [`crm/uysot.py:22`](crm/uysot.py:22) `MAX_PAGES_PER_SYNC = 20`; byudjet 50/daq → so'rovlar orasi **1.2s**
- Jonli `cron.log`: `2026-08-07 11:49 tik: ... /daily-results/sync, /anketa/tick`
- `_run_service_inprocess` naqshi allaqachon mavjud va **ishlayapti** (hot_lead, idle_watch, lead_sync, lead_diff)

**NOMA'LUM — agent aniqlashi shart**
- Har tick'ning **haqiqiy** davomiyligi — hech qachon jonli o'lchanmagan, faqat izohlardagi eski baholar
- Qaysi tick eng og'ir? (Taxmin `/daily-results/sync`, lekin **tasdiqlanmagan**)
- Ba'zi tick'lar allaqachon no-op'mi? (`/knowledge/tick`, `/playbook/tick`, `/auto-plan/snapshot` — AI o'chiq)
- Ko'chirishda mantiq **o'zgarmasligi** uchun qaysi nozik joylar bor? (`source == manual` qoidasi, CRM xatosida `None` semantikasi)

**2-bosqich: nimani o'lchash**
- Har HTTP tick'ni alohida chaqirib vaqtini o'lcha (`curl -w %{time_total}`)
- Toq va juft daqiqada saytdan `/health` javob vaqtini solishtir — farq **isbot** bo'ladi
- Sutkalik: qaysi soatda eng yomon? (kun oxirida qo'ng'iroq ko'p → sahifa ko'p)

**3-bosqich: zanjir qayerdan boshlanadi**
> Sayt qotadi → cron HTTP yuboradi → **nega HTTP?** → `scheduler/client.call_api` merosi → **nega hali ham?** → in-process ko'chirish boshlangan, lekin **tugallanmagan** → **nega tugallanmagan?** → ...

**4-bosqich: rad etish testi**
> «Balki `/daily-results/sync` aslida tez (2-3s) va qotishning sababi boshqa narsa.»
> — O'lchov bilan tekshir. Agar tez chiqsa, qotish manbaini qaytadan qidir.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Cron chastotasini siyraklashtiramiz» — **allaqachon qilingan** (9e4adc8, toq/juft taqsimot) va yetarli bo'lmadi
- ❌ «Timeout'ni kamaytiramiz» — so'rov baribir ishchini band qiladi, faqat uzilishi tez bo'ladi
- ❌ Hamma 12 tick'ni bir zarbada ko'chirib, alohida sinamaslik

---

## 1.3 — Bot webhook rejimida, keepalive cron yo'qolgan

| | |
|---|---|
| **Simptom** | Har Telegram xabari yagona Passenger ishchisidan o'tadi |
| **Ustuvorlik** | Yuqori — 1.2 ustiga qo'shimcha yuk |
| **Bog'liq** | 1.1, 1.2, 5.1 |

**Ma'lum dalillar**
- Serverda `.env`: `BOT_WEBHOOK_ENABLED=true`
- `crontab -l` — hodimlar `keepalive_bot.sh` qatori **YO'Q** (faqat boshqa loyiha `chatbot` niki bor)
- `ps -u nuriddi5` — `bot.main` jarayoni **ishlamayapti**
- `~/hodimlar-tizimi/logs/bot_polling.log` — **fayl yo'q**
- [`deploy/cpanel/keepalive_bot.sh:6-10`](deploy/cpanel/keepalive_bot.sh:6) — polling ataylab tanlangan, sababi aynan shu muammo

**NOMA'LUM — agent aniqlashi shart**
- Telegram tomonida webhook **haqiqatan o'rnatilganmi**? (`getWebhookInfo` — men tekshirmadim)
- Bot **umuman ishlayaptimi**? (Agar webhook ham o'chiq bo'lsa — bot o'lik)
- Keepalive qatori **qachon va nega** yo'qolgan? [crontab-xavfsizligi] hodisasi bilan bog'liqmi?
- `.env` qachon `BOT_WEBHOOK_ENABLED=true` ga o'zgargan — deploy paytida `.env.example` dan ko'chirilganmi?

**2-bosqich: nimani o'lchash**
- `getWebhookInfo` → URL, `pending_update_count`, `last_error_message`
- Botga xabar yuborib javob kelishini sinash (ishlayaptimi?)
- Agar webhook faol bo'lsa: bitta xabar qayta ishlanish vaqti

**3-bosqich: zanjir qayerdan boshlanadi**
> Bot yagona ishchini bandiga qiladi → webhook rejimi yoqiq → **nega yoqiq?** → `.env` shunday → **nega o'zgargan?** → **nega keepalive cron ham yo'q?** → ikkalasi bir vaqtda yo'qolganmi? → ...
>
> ⚠️ Bu ikki fakt (webhook yoqiq + cron yo'q) **bir hodisaning** natijasi bo'lishi mumkin. Zanjir shuni aniqlashi kerak.

**4-bosqich: rad etish testi**
> «Balki webhook ham o'rnatilmagan va bot polling bilan boshqa yo'ldan ishlayapti — men `ps` da noto'g'ri qidirdim.»
> — `ps -ef` to'liq ro'yxatini va Telegram `getWebhookInfo` ni tekshir.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Keepalive qatorini crontab'ga qaytaramiz» — **nega yo'qolganini bilmasdan**; yana yo'qoladi
- ❌ `(crontab -l; echo "...") | crontab -` naqshini ishlatish — bu naqsh ilgari **crontabni butunlay o'chirib yuborgan**. Faqat fayl orqali + oldindan zaxira
- ❌ Faqat `.env` ni o'zgartirib, Telegram tomonidagi webhook'ni o'chirmaslik (ikkisi bir vaqtda ishlab, qo'sh ishlov beradi)

---

## 1.4 — 429 backoff HTTP so'rov ichida 4 daqiqagacha kutadi

| | |
|---|---|
| **Simptom** | Ba'zan sayt bir necha daqiqa umuman ochilmaydi |
| **Ustuvorlik** | Eng yomon holat (worst case) |
| **Bog'liq** | 2.2 (429 sababi), 1.2 |

**Ma'lum dalillar**
- [`crm/uysot.py:38-39`](crm/uysot.py:38): `RATE_LIMIT_BACKOFF_SECONDS = 60`, `MAX_RATE_LIMIT_RETRIES = 4`
- [`uysot.py:118-151`](crm/uysot.py:118) `_limited_request` — 429 da `start_cooldown(backoff)` va qayta urinish
- Cooldown **butun jarayonga** qo'llanadi (`_SharedRateBudget._cooldown_until`)

**NOMA'LUM — agent aniqlashi shart**
- HTTP so'rov yo'lida **haqiqatan 429 bo'ladimi**? Jonli logda dalil bormi?
- 429 asosan qaysi yo'ldan keladi — og'ir skanlarmi yoki yengil HTTP endpointlarmi?
- 4 daqiqalik holat **kuzatilganmi**, yoki bu faqat nazariy maksimum?
- `_cooldown_until` jarayonga qo'llangani uchun: bitta 429 boshqa **barcha** so'rovlarni ham to'xtatadimi?

**2-bosqich: nimani o'lchash**
- `logs/cron.log` va API logida 429 hodisalarini **sanash** (sutkada nechta, qaysi soatda)
- Agar 429 kam bo'lsa — bu muammoning ustuvorligi tushadi, buni ochiq ayt

**3-bosqich: zanjir qayerdan boshlanadi**
> 4 daqiqalik blok → 60s × 4 retry → **nega 60s?** → Uysot limiti daqiqalik oynada → **nega HTTP yo'l ham shu qoidadan o'tadi?** → `_limited_request` **yagona** kirish nuqtasi, kontekst farqlanmaydi → **nega farqlanmagan?** → yozilganda faqat fon skanerlari nazarda tutilgan → ...

**4-bosqich: rad etish testi**
> «Balki HTTP endpointlar hech qachon 429 olmaydi, chunki ular yengil (1-2 sahifa) va byudjet slotini tez oladi.»
> — Logda tekshir. Agar 429 faqat og'ir skanlarda bo'lsa, bu muammo **1.2 ichida hal bo'ladi** va alohida ish talab qilmaydi.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «`MAX_RATE_LIMIT_RETRIES` ni 1 ga tushiramiz» — fon skanerlarini buzadi, ular uchun 4 retry **to'g'ri**
- ❌ «`RATE_LIMIT_BACKOFF_SECONDS` ni 10 ga tushiramiz» — Uysot oynasi daqiqalik, 10s kutish 429 ni **takrorlaydi**
- ❌ Global bayroq (`IS_WEB_REQUEST`) ishlatish — asyncio'da jarayonda aralashadi; `contextvars` kerak

---

## 1.5 — Excel eksport event loop'ni bloklaydi

| | |
|---|---|
| **Simptom** | Eksport bosilganda butun sayt muzlaydi |
| **Ustuvorlik** | O'rta (kam ishlatiladi, lekin ishlatilganda og'ir) |
| **Bog'liq** | 1.1, 3.3 (N+1) |

**Ma'lum dalillar**
- [`api/services/export.py:157-215`](api/services/export.py:157) — har xodim uchun 5+ alohida so'rov (DailyResult, video, Task, ExcusedDay, Bonus)
- [`export.py:277`](api/services/export.py:277) va [`export.py:407`](api/services/export.py:407) — `wb.save(buffer)`, `to_thread`siz sinxron CPU ishi

**NOMA'LUM — agent aniqlashi shart**
- Eksportning **haqiqiy** davomiyligi? Necha xodim, qancha davr?
- Vaqtning qanchasi N+1 da, qanchasi `wb.save` da? **Ikkalasini alohida** o'lchash shart
- Kim va qanchalik tez-tez bosadi? (Kuniga 1 marta bo'lsa — ustuvorlik past)

**2-bosqich: nimani o'lchash**
- Eksportni chaqirib to'liq vaqtini o'lcha
- Ichida: so'rovlar bloki va `wb.save` blokini alohida vaqtla

**3-bosqich: zanjir qayerdan boshlanadi**
> Sayt muzlaydi → eksport uzoq ishlaydi → **nega uzoq?** → (N+1? `wb.save`? ikkalasi?) → **nega shunday yozilgan?** → yozilganda konkurentlik cheklovi hisobga olinmagan → ...

**4-bosqich: rad etish testi**
> «Balki `wb.save` atigi 50 ms va butun vaqt N+1 so'rovlarida — u holda `to_thread` **umuman yordam bermaydi**.»
> — Ikkalasini alohida o'lchamasdan yechim tanlanmasin.

**⚠️ Kutilayotgan YUZAKI yechim — DIQQAT, bu tuzoqqa men ham tushgandim**
- ❌ «`asyncio.to_thread(wb.save, ...)` ga o'raymiz va muammo hal» —
  **BU YETARLI EMAS.** `to_thread` event loop'ni bo'shatadi, LEKIN a2wsgi'da
  chaqiruvchi **WSGI thread baribir bloklangan** va Passenger'da boshqa ishchi
  yo'q. Ya'ni sayt baribir kutadi. Bu tuzatish **1.1 hal bo'lmaguncha
  foydalanuvchi uchun hech narsani o'zgartirmaydi**.
- ✅ Haqiqiy yo'nalishlar: N+1 ni yo'q qilish (eksport **tez** bo'lsin) yoki
  eksportni **fon ishiga** o'tkazib, tayyor bo'lgach yuklab olish
- ❌ «Eksportni cheklaymiz (maksimal 50 xodim)» — muammoni yashirish

---

# ILDIZ 2 — Uysot CRM integratsiyasi

---

## 2.1 — Uysot API kaliti 401 qaytaryapti ✅ HAL BO'LDI (2026-08-08)

> **ILDIZ SABAB:** 04.08.2026 **16:43** da Uysot kabinetida «TechSupport Nurli
> Diyor» **yangi token yaratgan** («Xodimlar tizimi», muddati 31.12.2026).
> Yangi token eskisini bekor qildi, `.env` da esa **eskisi** qolgan edi.
> Bizning birinchi 401 xatomiz — **aynan o'sha daqiqada** (`cron.log`).
>
> **Rad etilgan gipotezalar:** ❌ litsenziya muddati · ❌ 429 suiiste'moli tufayli blok
> (ikkalasi ham ishonarli edi — 4-bosqich ularni yiqitdi).
>
> **Bajarilgan:** `.env` da `CRM_API_KEY` yangilandi (zaxira: `.env.bak_2026-08-08_103618`),
> Passenger restart (10:37:43).
>
> **Tasdiq:** `lead/filter` va `call-history` **401 → 200**. 10:38 dagi birinchi
> sog'lom tikda: **6 ta issiq lid** aniqlanib Telegram'ga yetkazildi, 2 ta
> kechikish eskalatsiyasi yuborildi, `lid snapshot: synced: True`.
>
> **Ochiq qoldi:** *nega 3 kun davomida hech kim bilmadi?* — kuzatuv tizimi
> CRM 401'ini ushlamadi. Bu **alohida** ish (qo'riqchini kengaytirish).

<details><summary>Asl karta (tarix uchun)</summary>

| | |
|---|---|
| **Simptom** | Lidlar CRM'dan umuman o'qilmayapti |
| **Ustuvorlik** | 🔴 **ENG SHOSHILINCH** — bu tuzatilmasa qolgan ishlar ma'nosiz |
| **Bog'liq** | 2.2, 2.3, 1.2 |

**Ma'lum dalillar**
- Jonli `cron.log`: `httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'https://api.service.app.uysot.uz/v1/open-api/lead/filter'`
- Xato [`crm/uysot.py:790`](crm/uysot.py:790) `get_leads_created_between` da
- O'sha tick'da `issiq lid ... 'detect': {'error': 'crm_xato'}` — ya'ni **oqibati ko'rinib turibdi**

**NOMA'LUM — agent aniqlashi shart**
- 401 **qachondan beri**? (Log tarixidan aniqlash — bu sababni topishga yordam beradi)
- **Barcha** endpointlar 401 beradimi, yoki faqat `/lead/filter`? (Call-history ishlayaptimi?)
- Kalit muddati tugaganmi, almashtirilganmi, yoki **huquq** olib qo'yilganmi?
- IP cheklovi bormi? (Server IP o'zgargan bo'lishi mumkin)

**2-bosqich: nimani o'lchash**
- Har xil Uysot endpointini bitta-bitta sinab, qaysilari 401 berishini aniqlash
- `cron.log` da 401 ning **birinchi** paydo bo'lgan vaqtini topish
- O'sha vaqtda boshqa nima o'zgargan? (deploy? kalit yangilanishi?)

**3-bosqich: zanjir qayerdan boshlanadi**
> Lidlar yo'q → 401 → **nega 401?** → kalit yaroqsiz → **nega yaroqsiz?** → (muddat / almashtirish / huquq / IP) → **nega bizga xabar bermadi?** → tizim qo'riqchisi buni ushladimi? → ...
>
> ⚠️ Ikkinchi zanjir muhim: **nega 24 soat davomida hech kim bilmadi?** Bu kuzatuv tizimidagi bo'shliq.

**4-bosqich: rad etish testi**
> «Balki kalit joyida, lekin `/lead/filter` uchun **alohida huquq** kerak va u olib qo'yilgan.»
> — Boshqa endpointlarni sinash bu farqni ochadi.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Yangi kalit qo'yamiz» — **nega eskisi o'lganini bilmasdan**; muddat bo'lsa 3 oydan keyin takrorlanadi
- ❌ 401 ni `try/except` bilan yutib, log'ga yozmaslik
- ❌ **Kalitni chatga yozish/so'rash** — maxfiy fayllar qoidasi: kalit faylini ochib o'qimaslik, faqat yo'li bilan ishlash
- ❌ «Qo'riqchi nega ushlamadi» savolini o'tkazib yuborish — bu muammoning yarmi

---

## 2.2 — Rate byudjet jarayon-ichi (150/daq vs limit 60)

| | |
|---|---|
| **Simptom** | 429 xatolari takrorlanadi |
| **Ustuvorlik** | O'rta — lekin **1.1 (ishchi qo'shish) uchun OLD SHART** |
| **Bog'liq** | 1.1, 1.4, 2.1 |

**Ma'lum dalillar**
- [`crm/uysot.py:71-80`](crm/uysot.py:71) `_SharedRateBudget` — `asyncio.Lock` bilan **modul darajasida**, ya'ni **jarayon-ichi**
- Kod izohida o'zi tan olingan: «cPanel cron rejimida esa ikki jarayon bor... har biri O'Z byudjetiga ega»
- `CRM_UYSOT_MAX_REQUESTS_PER_MINUTE = 50`, Uysot limiti **60**
- Uysot'ga chiqadigan jarayonlar: `cron_tick`, Passenger ishchisi, bot → **3 × 50 = 150**

**NOMA'LUM — agent aniqlashi shart**
- 3 jarayon **amalda bir vaqtda** chaqiradimi, yoki vaqtda ajralganmi?
- Haqiqiy 429 chastotasi qancha? (Nazariy 150 ≠ amaliy 150)
- `SCAN_THROTTLE_SECONDS = 2.0` qanchalik yumshatyapti?
- Jarayonlararo qulf uchun qaysi mexanizm mos: fayl-lock, SQLite jadval, yoki boshqa?

**2-bosqich: nimani o'lchash**
- Sutkalik 429 soni va vaqt taqsimoti
- Har jarayon aslida daqiqasiga nechta so'rov yuborayotganini o'lchash (log qo'shish)

**3-bosqich: zanjir qayerdan boshlanadi**
> 429 → jami so'rov limitdan oshadi → **nega byudjet ushlab qololmaydi?** → byudjet jarayon-ichi → **nega jarayon-ichi?** → `asyncio.Lock` modul darajasida, bitta jarayon faraz qilingan → **nega bunday faraz qilingan?** → Docker rejimida uvicorn bitta worker edi → ...

**4-bosqich: rad etish testi**
> «Balki 429 ning asosiy sababi 3 jarayon emas, balki **bitta** og'ir skan (lead_diff, 200 sahifa) o'zi limitni yeb qo'yishi.»
> — 429 hodisalari qaysi job paytida bo'lganini logdan bog'la.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Har jarayonga 20/daq beramiz» — statik bo'lish; bitta jarayon bo'sh turganda ham quvvat yo'qoladi
- ❌ «`CRM_UYSOT_MAX_REQUESTS_PER_MINUTE` ni 20 qilamiz» — yuqoridagi bilan bir xil, faqat sozlama orqali
- ❌ Jarayonlararo qulfni SQLite'ga qo'yish — ~~**3.4** (WAL o'chiq) bilan to'qnashadi~~
  **(2026-08-08 tuzatish: production PostgreSQL, ya'ni bu e'tiroz bekor —
  jarayonlararo qulfni bazada saqlash butunlay maqbul yo'l)**

---

## 2.3 — CRM webhook jim ⏳ SABAB ANIQLANDI, UYSOT TOMONIDA

> **2026-08-08 holati:** sozlash joyi topildi (`Integratsiya → Dasturchi
> oynasini ochish → «Xodimlar tizimi» → Webhook tabi`). 04.08 da yangi token
> yaratilganda webhook sozlamalari **ko'chirilmagan** — toggle o'chiq, URL bo'sh,
> voqealar tanlanmagan.
>
> Egasi sozlagach qayta tekshirildi — **hamon 0 ta webhook**. Batafsil dalillar
> va Uysot'ga yuboriladigan xat: [WEBHOOK_MUAMMOSI.md](WEBHOOK_MUAMMOSI.md)
>
> **Xulosa:** bizning endpoint sog'lom (test: sekret bilan 200, sekretsiz 401),
> polling qoplab turibdi → ma'lumot yo'qolmayapti. To'siq **Uysot tomonida**.

<details><summary>Asl karta (tarix uchun)</summary>

| | |
|---|---|
| **Simptom** | Webhook orqali lid o'zgarishlari kelmayapti, polling zaxira bo'lib ishlayapti |
| **Ustuvorlik** | Past-o'rta (polling qoplayapti — lekin 2.1 tufayli u ham buzuq) |
| **Bog'liq** | 2.1, 1.2 |

**Ma'lum dalillar**
- Jonli `cron.log`: «CRM webhook jonsiz (so'nggi 24 soatda lid ajratilgan so'rov kelmagan) — lid polling xavfsizlik to'ri sifatida davom etmoqda»
- Bu xabarni [`api/services/crm_mode.py`](api/services/crm_mode.py) mantig'i chiqaradi

**NOMA'LUM — agent aniqlashi shart**
- Uysot kabinetida webhook URL **umuman sozlanganmi**?
- Sozlangan bo'lsa — so'rovlar bizga **yetib kelyaptimi**? (Passenger/nginx logida iz bormi?)
- Kelayotgan bo'lsa — [`api/routers/uysot_webhook.py`](api/routers/uysot_webhook.py) ularni **rad etyaptimi**? (imzo, format, autentifikatsiya)
- 2.1 (401) bilan bog'liqmi? — bir xil kalit ishlatiladimi?

**2-bosqich: nimani o'lchash**
- Webhook endpointiga kelgan so'rovlar sonini (kirish logidan)
- Test so'rov yuborib, endpoint javobini tekshirish

**3-bosqich: zanjir qayerdan boshlanadi**
> Webhook jim → **so'rov kelmayaptimi yoki rad etilyaptimi?** (bu ikki butunlay boshqa zanjir — avval SHUNI aniqla) → keyin tegishli yo'nalishda davom et

**4-bosqich: rad etish testi**
> «Balki webhook so'rovlari kelyapti, lekin `crm_mode` ni "jonli" deb belgilaydigan **hisoblagich** noto'g'ri ishlayapti — ya'ni webhook sog'lom, detektor buzuq.»
> — Bazadagi webhook izlarini bevosita tekshir.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Uysot kabinetida webhook'ni qayta sozlaymiz» — **bizning endpoint ishlashini tekshirmasdan**
- ❌ Xabar matnini o'chirib qo'yish («bezovta qilmasin») — bu ogohlantirish **to'g'ri ishlayapti**

</details>

> ✅ **3-bosqichdagi ayri (kelmayaptimi / rad etilyaptimi) HAL QILINDI** —
> access log orqali: `/api/crm-webhook/*` ga Uysot'dan **umuman so'rov kelmagan**.
> Ya'ni «rad etilyapti» varianti bekor, «yubormayapti» tasdiqlandi.

---

# ILDIZ 3 — Baza: indekslar va so'rov sifati

> ### ⚠️ 2026-08-08 TUZATISHI — BU ILDIZNING KATTA QISMI BEKOR
>
> Kartalar dastlab **lokal `app.db`** (eski dev SQLite) sxemasiga qarab
> yozilgan edi. Production esa **PostgreSQL** — jonli tekshiruv indekslar
> **allaqachon borligini** ko'rsatdi:
>
> | Jadval | Qatorlar | Indekslar |
> |---|---|---|
> | `lead_events` | 10 925 | pkey, `crm_lead_id`, `event_type`, **`detected_at`** ✅ |
> | `hot_lead` | 1 100 | pkey, `crm_lead_id`, `user_id`, **`status`** ✅ |
> | `attendance` | 140 | pkey, uq, `user_id`, **`date`**, `status` ✅ |
> | `audit_logs` | 438 | pkey, `actor_id`, `action` |
> | `crm_lead_state` | 11 011 | faqat pkey |
>
> **Holat:** `3.1` ❌ bekor · `3.2` ❌ deyarli bekor · `3.4` ❌ bekor ·
> **`3.3` (N+1) — kuchida qoladi**, u bazadan qat'i nazar amal qiladi.
>
> Ya'ni bu ildizdan **faqat bitta** ish qoldi: **3.3**.

---

## 3.1 — ~~`lead_events` jadvalida umuman indeks yo'q~~ ❌ BEKOR

**Sabab:** da'vo lokal SQLite'dan olingan. Productionda `ix_lead_events_detected_at`
**mavjud** (10 925 qator). Ish talab qilinmaydi.

<details><summary>Asl karta (tarix uchun)</summary>

| | |
|---|---|
| **Simptom** | Statistika sahifalari vaqt o'tgani sari sekinlashadi |
| **Ustuvorlik** | O'rta hozir, **yuqori kelajakda** (jadval to'xtovsiz o'sadi) |
| **Bog'liq** | 3.2, 1.1 |

**Ma'lum dalillar**
- Sxema tekshirildi: `lead_events` da **PRIMARY KEY dan boshqa indeks yo'q**
- [`api/routers/stats.py:381`](api/routers/stats.py:381) — `LeadEvent.detected_at >= ... < ...` bo'yicha filtr, `distinct`
- Jadval har diff-tick'da (har 3 daqiqa) va har webhook'da o'sadi
- Lokal bazada 0 qator (toza baza) — **production'da o'lchanmagan**

**NOMA'LUM — agent aniqlashi shart**
- Production'da **necha qator**? O'sish tezligi (kuniga nechta)?
- So'rov **hozir** qancha vaqt oladi? (Balki hali tez)
- `EXPLAIN QUERY PLAN` nima deydi — haqiqatan to'liq skanmi?
- Qaysi ustunlarga indeks kerak: faqat `detected_at`mi, yoki `(detected_at, crm_lead_id)` kompozitmi?
- Jadval **cheksiz o'sishi** kerakmi, yoki eski yozuvlar arxivlanishi/o'chirilishi kerakmi?

**2-bosqich: nimani o'lchash**
- Production'da: `SELECT count(*) FROM lead_events`
- `EXPLAIN QUERY PLAN` + so'rovning haqiqiy vaqti
- Kunlik o'sish: `detected_at` bo'yicha guruhlab sanash

**3-bosqich: zanjir qayerdan boshlanadi**
> Sekin so'rov → to'liq skan → indeks yo'q → **nega yo'q?** → modelda `index=True` qo'yilmagan → **nega qo'yilmagan?** → jadval yangi edi, o'sish sur'ati hisobga olinmagan → ...
>
> ⚠️ Ikkinchi zanjir: **nega jadval cheksiz o'sadi?** Bu indeksdan ko'ra muhimroq savol bo'lishi mumkin.

**4-bosqich: rad etish testi**
> «Balki jadvalda atigi bir necha ming qator bor va to'liq skan 5 ms — ya'ni bu **hozir muammo emas**.»
> — O'lchamasdan indeks qo'shish = dalilsiz optimallashtirish. Agar shunday chiqsa, halol ayt va ustuvorlikni tushir.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Hamma ustunga indeks qo'yamiz» — yozuv tezligini pasaytiradi, disk va inode yeydi (**5.3** ga qara)
- ❌ O'lchamasdan indeks qo'shish — «indeks har doim yaxshi» degan noto'g'ri refleks
- ❌ Arxivlash/tozalash savolini umuman ko'rmaslik

</details>

> 💡 **Faqat bitta qoldiq savol** asl kartadan omon qoldi va u indeksga aloqador emas:
> **`lead_events` cheksiz o'sadimi?** (10 925 qator, har diff-tikda o'sadi.)
> Arxivlash/tozalash siyosati kerakmi — buni alohida ko'rib chiqish mumkin.

---

## 3.2 — ~~`hot_lead`, `audit_logs`, `attendance` indekslari~~ ❌ DEYARLI BEKOR

**Jonli holat:** `hot_lead` (`status`, `crm_lead_id`, `user_id`) va `attendance`
(`date`, `user_id`, `status`) indekslari **mavjud**.

**Yagona haqiqiy qoldiq:** `audit_logs.created_at` indeksi yo'q — lekin jadval
**438 qator**, ya'ni amalda sezilmaydi. Jadval 100 000+ ga yetganda qayta ko'riladi.

<details><summary>Asl karta (tarix uchun)</summary>

### 3.2 (eski matn)

| | |
|---|---|
| **Simptom** | Filtrlangan so'rovlar to'liq skanga tushadi |
| **Ustuvorlik** | O'rta |
| **Bog'liq** | 3.1 (bitta migratsiyada birga) |

**Ma'lum dalillar**
- `hot_lead` — `status`, `crm_lead_id`, `detected_at` bo'yicha indeks **yo'q**
- `audit_logs` — `created_at`, `target_user_id` **yo'q** (bor: `action`, `actor_id`)
- `attendance` — alohida `date` indeksi **yo'q** (bor: `UNIQUE(user_id, date)`)

**NOMA'LUM — agent aniqlashi shart**
- Har jadval uchun **haqiqiy so'rov naqshlari** qanday? (Kodni o'qib aniqlash — taxmin qilmasdan)
- `attendance` da `UNIQUE(user_id, date)` mavjud indeksi qaysi so'rovlarni **allaqachon qoplaydi**?
  (SQLite kompozit indeksning **birinchi** ustunidan foydalanadi — `date` yolg'iz filtrda ishlamaydi, lekin `user_id IN (...) AND date` da ishlaydi)
- `audit_logs` da eslatma spam-tekshiruvi (`_send_reminder`) qanday so'rov yuboradi?
- Production'da har jadvalning hajmi?

**2-bosqich: nimani o'lchash**
- Har jadval uchun qator soni
- Eng ko'p ishlatiladigan so'rovlar uchun `EXPLAIN QUERY PLAN`

**3-bosqich: zanjir qayerdan boshlanadi**
> Har jadval uchun **alohida** zanjir — ular bir xil sabab emas. `attendance` da qisman qoplangan, `hot_lead` da umuman yo'q.

**4-bosqich: rad etish testi**
> «`attendance.date` uchun alohida indeks kerak emas, chunki barcha so'rovlar `user_id` bilan birga keladi va mavjud UNIQUE indeks yetarli.»
> — Kodni o'qib, `date` yolg'iz ishlatiladigan joy bormi tekshir.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ Uch jadvalni bitta ro'yxatga qo'shib, «hammasiga indeks qo'shamiz» deyish — **har biri alohida asoslanishi kerak**
- ❌ Mavjud kompozit indekslarni hisobga olmaslik (ortiqcha, foydasiz indeks)

</details>

---

## 3.3 — N+1 halqalar (~15 joyda) ✅ KUCHIDA QOLADI

| | |
|---|---|
| **Simptom** | Bitta amal o'nlab ortiqcha so'rov yuboradi |
| **Ustuvorlik** | O'rta — lekin **qaysi biri HTTP yo'lida ekani hal qiluvchi** |
| **Bog'liq** | 1.5, 1.2 |

**Ma'lum dalillar** (skanerlash natijasi)
- `api/services/export.py:159,180,193,206` — har xodim uchun 4 so'rov
- `api/services/payroll.py:726-743` — halqa ichida `flush`
- `api/routers/bonuses.py:39,57,68` — halqa ichida **`commit`**
- `api/routers/anketa.py:153,305,499,1041` — halqada `db.get(User, ...)`
- `api/services/weekly_stats.py:48,60`, `watch_rules.py:92,119`, `knowledge.py:214-227`
- `api/routers/attendance.py:1463`, `daily_results.py:209`

**NOMA'LUM — agent aniqlashi shart**
- Qaysilari **foydalanuvchi kutadigan** HTTP yo'lida, qaysilari **fon** (cron/bot)?
  → Fon'dagilari ustuvorligi past; HTTP'dagilari yuqori
- Halqa **necha marta** aylanadi? (8 xodimda N+1 sezilmaydi, 100 xodimda sezilади)
- Halqa ichidagi **`commit`** (bonuses.py:68) — bu N+1 dan ham yomonroq: SQLite'da har commit disk yozuvi va qulf. Alohida ko'rib chiqilsinmi?

**2-bosqich: nimani o'lchash**
- Har bir shubhali yo'l uchun: haqiqiy so'rov soni va vaqti
- Xodimlar soni (hozir 8) — bu N+1 ning haqiqiy narxini belgilaydi

**3-bosqich: zanjir qayerdan boshlanadi**
> ⚠️ **Har bir joy uchun bitta umumiy zanjir yasashga urinmang.** Ular turli sabablardan:
> ba'zilari qulaylik uchun, ba'zilari bulk API yo'qligidan, ba'zilari tarixiy.
> Kamida **eng og'ir 3 tasini** alohida tahlil qiling.

**4-bosqich: rad etish testi**
> «Xodim atigi 8 ta — N+1 amalda 32 ta so'rov, SQLite'da bu ~5 ms. Ya'ni bu **nazariy** muammo, amaliy emas.»
> — O'lchov bilan tekshir. To'g'ri chiqsa — ustuvorlikni tushir va buni ochiq ayt.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ 15 joyning hammasini birdan «tuzatish» — regressiya xavfi yuqori, foydasi o'lchanmagan
- ❌ `selectinload`/`joinedload` ni ko'r-ko'rona qo'shish — ba'zi joylarda ortiqcha ma'lumot yuklaydi
- ❌ Halqadagi `commit` ni oddiy N+1 bilan bir xil ko'rish — u boshqa (og'irroq) muammo

---

## 3.4 — ~~SQLite WAL o'chiq~~ ❌ BEKOR

**Sabab:** production **PostgreSQL** ishlatadi. `db/base.py:32-42` dagi WAL
mantig'i faqat lokal SQLite rejimida bajariladi (`if DATABASE_URL.startswith("sqlite")`).
Productionda MVCC bor — «yozuvchi o'quvchini bloklaydi» muammosi **yo'q**.

**Muhim oqibat:** bu **1.1 (Passenger ishchilarini ko'paytirish)** yo'lidagi
to'siqni olib tashlaydi. Endi yagona jiddiy old shart — **2.2 (rate byudjet)**
va xotira (225 MB × N ≤ 1 GB).

<details><summary>Asl karta (tarix uchun)</summary>

| | |
|---|---|
| **Simptom** | Yozuvchi o'quvchilarni bloklaydi, 30 soniyagacha kutish |
| **Ustuvorlik** | Past hozir — **lekin 1.1 (ishchi qo'shish) uchun to'siq** |
| **Bog'liq** | 1.1, 2.2 |

**Ma'lum dalillar**
- [`db/base.py:32-42`](db/base.py:32) — WAL **ataylab o'chirilgan**, izohda batafsil sabab:
  «cPanel'da Passenger ostida bazaga tegadigan HAR BIR so'rov 500 bera boshladi
  (CLI'dan o'sha baza WAL'da muammosiz ochilardi)»
- `busy_timeout = 30000` (30 soniya)
- `docker-compose.yml` da PostgreSQL konfiguratsiyasi **tayyor**
- `scripts/migrate_sqlite_to_pg.py` **mavjud**

**NOMA'LUM — agent aniqlashi shart**
- WAL nega Passenger ostida ishlamagan? **Aniq sabab** aniqlanganmi, yoki faqat simptom qayd etilganmi?
  (Ehtimol: `-wal`/`-shm` fayllari uchun katalog yozuv huquqi, yoki `open_basedir`, yoki NFS)
- Bu **hal qilinadigan** muammomi? (Masalan katalog huquqini tuzatish bilan)
- Hozir «database is locked» xatolari **haqiqatan bo'lyaptimi**? Logda dalil bormi?
- PostgreSQL'ga o'tish bu hostda **umuman mumkinmi**? (cPanel'da PostgreSQL bormi?)

**2-bosqich: nimani o'lchash**
- Logda «database is locked» hodisalarini sanash
- Zaxira nusxada WAL ni yoqib sinab ko'rish (**jonli bazada EMAS**)

**3-bosqich: zanjir qayerdan boshlanadi**
> Qulf kutish → WAL o'chiq → **nega o'chiq?** → Passenger'da 500 bergan → **nega 500 bergan?** → **BU ANIQLANMAGAN** — zanjir shu yerda uzilgan
>
> ⚠️ Bu bo'limning **asosiy qiymati** aynan shu uzilgan bo'g'inni tiklashda.

**4-bosqich: rad etish testi**
> «Balki hozir qulf to'qnashuvi umuman yo'q (cron in-process ko'chirilgandan keyin) va WAL kerak emas.»
> — Logda dalil qidir. Bo'lmasa — bu muammo **1.2 hal bo'lgach o'z-o'zidan yopiladi**.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ **`PRAGMA journal_mode=WAL` ni qaytarib yoqish** — bu ilgari **butun saytni yiqitgan**.
  Sababi aniqlanmasdan qayta yoqish = o'sha xatoni takrorlash
- ❌ `busy_timeout` ni oshirish — kutishni uzaytiradi, muammoni hal qilmaydi
- ❌ «PostgreSQL'ga o'tamiz» deb yengil aytish — bu katta migratsiya, alohida qaror va reja talab qiladi

</details>

> 😅 **Kulgili yakun:** oxirgi «yuzaki yechim» bandi «PostgreSQL'ga o'tamiz deb
> yengil aytmang» degan edi — aslida **allaqachon o'tilgan ekan**. Bu kartaning
> o'zi 4-bosqich («rad etishga urinish») bajarilmagani uchun xato chiqdi:
> baza turini **jonli tekshirish** o'rniga lokal `.env` ga ishonildi.

---

# ILDIZ 4 — Frontend: Face ID og'irligi

---

## 4.1 — `setInterval(800ms)` in-flight guard'siz

| | |
|---|---|
| **Simptom** | «Keldim» sahifasida telefon qotadi |
| **Ustuvorlik** | Yuqori — xodimlar **har kuni** duch keladi |
| **Bog'liq** | 4.2, 4.3 |

**Ma'lum dalillar**
- [`web/src/components/FaceCapture.tsx:140`](web/src/components/FaceCapture.tsx:140):
  `const interval = setInterval(async () => { ... await captureFace(...) }, 800)`
- `setInterval` **async callback tugashini kutmaydi** — 800 ms da yangi chaqiruv boshlanadi
- Callback ichida `captureFace` → **3 ta model** (detector + landmark + descriptor)
- Guard bayrog'i (`busy`/`inFlight`) **yo'q**

**NOMA'LUM — agent aniqlashi shart**
- `captureFace` **haqiqatan** qancha vaqt oladi — real telefonda? 800 ms dan oshadimi?
- Oshmasa — to'planish yo'q va bu muammo **nazariy** bo'lib qoladi
- Qaysi qurilmalarda muammo? (Kuchli telefonda 200 ms, zaif telefonda 1500 ms bo'lishi mumkin)
- tfjs qaysi backend'da ishlayapti — WebGL, WASM, yoki CPU? (Bu tezlikni **bir necha barobar** o'zgartiradi)

**2-bosqich: nimani o'lchash**
- Real qurilmada `performance.now()` bilan `captureFace` davomiyligini o'lchash
- Bir necha xil telefonda (kuchli/zaif)
- tfjs backend'ini aniqlash: `faceapi.tf.getBackend()`

**3-bosqich: zanjir qayerdan boshlanadi**
> Sahifa qotadi → asosiy oqim band → callback'lar to'planadi → `setInterval` kutmaydi → **nega `setInterval` tanlangan?** → oddiy naqsh, async xususiyati hisobga olinmagan → ...
>
> ⚠️ Ikkinchi zanjir: **nega `captureFace` sekin?** → bu **4.2** ga olib boradi (keraksiz descriptor). Ikkalasini chalkashtirmang.

**4-bosqich: rad etish testi**
> «Balki `captureFace` 200 ms va to'planish umuman yo'q; qotish esa **model yuklanishi** (6.4 MB) paytida bo'ladi.»
> — O'lchamasdan tuzatmang. Qotish qaysi **fazada** bo'layotganini aniqlang.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «Intervalni 2000 ms qilamiz» — javob berish sekinlashadi, to'planish xavfi **qoladi** (zaif telefonda 2s ham yetmasligi mumkin)
- ❌ `try/catch` qo'shish — u allaqachon bor va muammoga aloqasi yo'q
- ❌ Guard qo'shib, `captureFace` ning **o'zi** nega og'irligini (4.2) ko'rmaslik

---

## 4.2 — Preview'da keraksiz 6.4 MB descriptor modeli

| | |
|---|---|
| **Simptom** | Har 800 ms da eng og'ir neyron tarmoq behuda ishlaydi |
| **Ustuvorlik** | Yuqori — **eng arzon katta yutuq** |
| **Bog'liq** | 4.1, 4.3 |

**Ma'lum dalillar**
- [`web/src/lib/face.ts:206-215`](web/src/lib/face.ts:206) `captureFace`:
  `.detectSingleFace(...).withFaceLandmarks().withFaceDescriptor()`
- Preview'da natijadan faqat `r.box` va `r.score` ishlatiladi
  ([`FaceCapture.tsx:146`](web/src/components/FaceCapture.tsx:146))
- Model hajmi: `face_recognition_model` shard1 **4.19 MB** + shard2 **2.25 MB** = **6.4 MB**
  (taqqoslash: `tiny_face_detector` 193 KB, `face_landmark_68` 357 KB)

**NOMA'LUM — agent aniqlashi shart**
- Descriptor hisoblash umumiy vaqtning **necha foizi**? (Model hajmi ≠ hisob vaqti — o'lchash shart)
- `captureFace` boshqa qayerlarda ishlatiladi va u yerlarda descriptor **kerakmi**?
  (`captureLiveFace` va `captureForRegister` ichida — 4.3 ga qara)
- Preview uchun landmark **kerakmi**, yoki faqat detector yetarlimi?
- Model **yuklanishi**ni ham o'tkazib yuborish mumkinmi, yoki u baribir kerakmi (yakuniy freym uchun)?

**2-bosqich: nimani o'lchash**
- `detectSingleFace()` yolg'iz / `+withFaceLandmarks()` / `+withFaceDescriptor()` —
  **uch variantni alohida** vaqtlash

**3-bosqich: zanjir qayerdan boshlanadi**
> Preview og'ir → descriptor hisoblanadi → **nega hisoblanadi?** → `captureFace` yagona funksiya, hamma joyda bir xil ishlatiladi → **nega yagona?** → soddalik uchun yozilgan, preview keyinroq qo'shilgan → ...

**4-bosqich: rad etish testi**
> «Balki descriptor hisoblash atigi 15 ms va asosiy vaqt detector'da (416×416 kirish) —
> u holda descriptor'ni olib tashlash deyarli hech narsa bermaydi.»
> — Uch variantni o'lchamasdan xulosa qilmang.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ `captureFace` ni **butunlay o'zgartirish** — u `captureLiveFace` va `captureForRegister` da ham ishlatiladi, ular descriptor'siz **buziladi**
- ❌ Model yuklashni preview'dan olib tashlash — yakuniy freym uchun baribir kerak, faqat kechikish siljiydi
- ❌ Descriptor'ni olib tashlab, Face ID **aniqligi**ga ta'sir qilmasligini tekshirmaslik

---

## 4.3 — Tiriklik sinovi 18 soniya davomida har freymda descriptor

| | |
|---|---|
| **Simptom** | Tiriklik sinovi davomida sahifa javob bermaydi |
| **Ustuvorlik** | Yuqori |
| **Bog'liq** | 4.1, 4.2 |

**Ma'lum dalillar**
- [`web/src/lib/face.ts:417-440`](web/src/lib/face.ts:417) — `while (Date.now() - started < maxMs)`, `CHALLENGE_MAX_MS = 18000`
- Halqa ichida har aylanishda `await captureFace(video)` → **descriptor ham hisoblanadi**
- Halqadan keyin ([`face.ts:454`](web/src/lib/face.ts:454)) **faqat bitta** eng yaxshi freymning descriptori ishlatiladi
- Aylanishlar orasida atigi `setTimeout(40ms)`

**NOMA'LUM — agent aniqlashi shart**
- Halqa amalda necha marta aylanadi? (18s / (freym vaqti + 40ms))
- Descriptor'siz halqa **necha barobar** tez bo'ladi?
- Yakuniy freym uchun descriptor'ni **keyin** hisoblash mumkinmi — `captureFace` `landmarks` va `box` ni qaytaradi, lekin **video freymi saqlanmaydi**. Bu texnik to'siq — qanday hal qilinadi?
- `MIN_CHALLENGE_FRAMES = 6` — tez halqada bu shart **osonroq** bajariladimi? Bu tiriklik aniqligiga ta'sir qiladimi?

**2-bosqich: nimani o'lchash**
- Halqadagi bir aylanish vaqti (descriptor bilan va usiz)
- Real qurilmada sinov to'liq necha soniya davom etadi

**3-bosqich: zanjir qayerdan boshlanadi**
> Sahifa 18s javob bermaydi → halqa asosiy oqimni yeydi → har freymda 3 model → **nega har freymda descriptor?** → `captureFace` yagona funksiya (4.2 bilan **bir xil ildiz**) → ...
>
> ⚠️ 4.2 va 4.3 **bir ildizdan** — lekin yechimlari **har xil** (biri descriptor'ni butunlay olib tashlaydi, ikkinchisi kechiktiradi). Shuning uchun alohida.

**4-bosqich: rad etish testi**
> «Descriptor'ni oxirida hisoblash **mumkin emas**, chunki o'sha freym allaqachon yo'qolgan —
> video oqimi davom etgan.»
> — Bu jiddiy texnik e'tiroz. Freymni saqlash (canvas) qancha xotira/vaqt oladi? Tekshiring.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ «`CHALLENGE_MAX_MS` ni 8000 ga tushiramiz» — tabiiy pirpiratishni ushlash ehtimoli tushadi;
  18s **ataylab** tanlangan ([`face.ts:112-121`](web/src/lib/face.ts:112) izohiga qarang)
- ❌ `setTimeout(40)` ni oshirish — freym soni kamayadi, tiriklik aniqligi tushadi
- ❌ Tiriklik chegaralarini (`BLINK_DIP_RATIO` va h.k.) «optimallashtirish» — ular
  **sintetik 3D proyeksiya bilan o'lchab** tanlangan, tegilmasin

---

# ILDIZ 5 — Ekspluatatsiya va kuzatuv

---

## 5.1 — Bot keepalive cron qatori yo'qolgan

| | |
|---|---|
| **Simptom** | `crontab` da hodimlar boti uchun keepalive yo'q |
| **Ustuvorlik** | Yuqori (1.3 ning bevosita sababi) |
| **Bog'liq** | 1.3 |

**Ma'lum dalillar**
- `crontab -l` — 6 qator bor, ulardan **hodimlar keepalive yo'q**; `chatbot` niki (2 ta) bor
- [`deploy/cpanel/keepalive_bot.sh:13`](deploy/cpanel/keepalive_bot.sh:13) — kerakli qator hujjatlashtirilgan
- `logs/cron_keepalive.log` — **fayl yo'q** (ya'ni hech qachon ishlamagan yoki o'chirilgan)

**NOMA'LUM — agent aniqlashi shart**
- Qator **qachon** yo'qolgan? U **umuman qo'shilganmi**?
  (`cron_keepalive.log` yo'qligi — hech qachon ishlamagan degan kuchli signal)
- [crontab-xavfsizligi] hodisasi bilan bog'liqmi? (Ilgari `(crontab -l; echo) | crontab -` naqshi crontabni o'chirgan)
- Boshqa qatorlar ham yo'qolganmi? Hujjatlarda ko'rsatilgan **barcha** cron qatorlari mavjudmi?
- cPanel'da cron o'zgarishlari **jurnali** bormi?

**2-bosqich: nimani o'lchash**
- Hujjatlardagi kutilgan cron qatorlari ro'yxati ↔ haqiqiy `crontab -l` — **farqni chiqarish**

**3-bosqich: zanjir qayerdan boshlanadi**
> Bot polling ishlamayapti → cron qatori yo'q → **hech qachon qo'shilmaganmi yoki o'chganmi?** →
> (ikki butunlay boshqa zanjir — avval SHUNI aniqla) → **nega hech kim sezmadi?** →
> qo'riqchi botning tirikligini tekshirmaydi → ...
>
> ⚠️ Oxirgi bo'g'in eng qimmatlisi: **kuzatuvdagi ko'r nuqta**.

**4-bosqich: rad etish testi**
> «Balki bot ataylab webhook rejimiga o'tkazilgan va keepalive **kerak emas** —
> ya'ni bu xato emas, qaror.»
> — git tarixi va `.env` o'zgarishlarini tekshir. Qaror bo'lsa, `keepalive_bot.sh` dagi
> izoh **eskirgan** demak.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ Qatorni jimgina qo'shib qo'yish — **nega yo'qligini** aniqlamasdan
- ❌ ⛔ `(crontab -l; echo "...") | crontab -` naqshi — **QAT'IY TAQIQ**, bu ilgari crontabni o'chirgan.
  Faqat: `crontab -l > zaxira.txt` → faylni tahrirlash → `crontab fayl.txt`
- ❌ «Qo'riqchi nega sezmadi» savolini o'tkazib yuborish

---

## 5.2 — Log rotatsiyasi ishlamayapti

| | |
|---|---|
| **Simptom** | `cron.log` 4.2 MB, `rotate.log` 3-avgustdan 0 bayt |
| **Ustuvorlik** | O'rta (disk, inode, diagnostika qiyinlashuvi) |
| **Bog'liq** | 5.3 |

**Ma'lum dalillar**
- `logs/cron.log` — **4 180 845 bayt**, oxirgi yozuv `Aug 7 11:49` (faol o'sib turibdi)
- `logs/rotate.log` — **0 bayt**, `Aug 4 16:09`
- `crontab`: `40 4 * * * bash .../rotate_logs.sh >> .../rotate.log 2>&1` — **qator MAVJUD**
- Ya'ni: cron qatori bor, lekin natija yo'q

**NOMA'LUM — agent aniqlashi shart**
- `rotate_logs.sh` **ishga tushyaptimi**? (0 bayt = umuman chiqish yo'q — bu g'alati, hatto xato ham yozilishi kerak edi)
- Skript ichida nima bor — chegaraga yetmagani uchun **hech narsa qilmayaptimi**?
  (Ehtimol 4.2 MB uning chegarasidan kichik — ya'ni skript **to'g'ri** ishlayapti!)
- 4-avgustda nima bo'lgan? (Fayl o'sha kuni yaratilgan/tegilgan)
- `logrotate` yoki boshqa mexanizm bilan to'qnashuv bormi?

**2-bosqich: nimani o'lchash**
- `rotate_logs.sh` ni **qo'lda** ishga tushirib chiqishini ko'rish
- Skriptdagi chegara qiymatini o'qish va 4.2 MB bilan solishtirish

**3-bosqich: zanjir qayerdan boshlanadi**
> Log o'smoqda → rotatsiya bo'lmayapti → **skript ishlayaptimi?** →
> (ha: chegaraga yetmagan / yo'q: cron yoki huquq muammosi) → ...

**4-bosqich: rad etish testi**
> «Balki hech qanday muammo yo'q — skript ishlayapti, shunchaki 4.2 MB uning
> chegarasidan (masalan 10 MB) kichik.»
> — Skriptni **o'qing**. Bu eng ehtimoliy izoh, uni birinchi tekshiring.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ Loglarni qo'lda o'chirish — sabab qoladi
- ❌ Skriptni «tuzatish» — u aslida **to'g'ri ishlayotgan** bo'lishi mumkin
- ❌ `cron.log` ni o'chirish: unda **2.1 (401) diagnostikasi uchun kerak bo'lgan tarix** bor

---

## 5.3 — Inodes 68% band (33 858 / 50 000)

| | |
|---|---|
| **Simptom** | Inode limitiga yaqinlashish |
| **Ustuvorlik** | Past hozir, **yuqori** limitga yetganda (fayl yaratib bo'lmaydi → tizim to'xtaydi) |
| **Bog'liq** | 5.2 |

**Ma'lum dalillar**
- LVE: `lveinodes` maximum **50 000**, usage **33 858** (**68%**)

**NOMA'LUM — agent aniqlashi shart**
- 33 858 inode **qayerda**? Qaysi kataloglar eng ko'p fayl saqlaydi?
  (Ehtimol nomzodlar: `node_modules`, `__pycache__`, `.venv`, `backups/`, `logs/`)
- O'sish tezligi qanday? (Sutkada nechta qo'shiladi → limitga qachon yetadi)
- Xavfsiz tozalash mumkin bo'lgan nima bor?
- Serverda `node_modules` **umuman kerakmi**? (Frontend lokalda build qilinadi, serverga `webdist/` boradi)

**2-bosqich: nimani o'lchash**
- Katalog bo'yicha inode taqsimoti:
  `for d in ~/*/; do echo "$(find "$d" | wc -l) $d"; done | sort -rn | head`
- Bir necha kun kuzatib o'sish tezligini aniqlash

**3-bosqich: zanjir qayerdan boshlanadi**
> Inode 68% → **qaysi kataloglar?** → **nega u yerda shuncha fayl?** →
> (kerakmi yoki qoldiqmi?) → ...

**4-bosqich: rad etish testi**
> «Balki 68% barqaror holat (o'smaydi) va umuman muammo emas.»
> — O'sish tezligini o'lchamasdan «muammo» deb atash noto'g'ri.

**⚠️ Kutilayotgan YUZAKI yechim**
- ❌ Tasodifiy fayllarni o'chirish — nima kerakligini aniqlamasdan
- ❌ ⛔ **Zaxira nusxalarni** (`backups/`, `app.db.bak_*`) o'ylamasdan o'chirish —
  ular qasddan saqlanadi, o'chirish uchun **alohida ruxsat** so'rang
- ❌ `.venv` yoki `node_modules` ni o'chirish — tizim ishlamay qolishi mumkin

---

# Ilova: qaysi tartibda ishlash

**2026-08-08 holatiga yangilangan.** 18 ta bo'limdan **5 tasi yopildi** →
qolgani **13 ta**.

| Navbat | Bo'lim | Holat / nega shu tartibda |
|---|---|---|
| ~~1~~ | ~~**2.1**~~ | ✅ **HAL BO'LDI** — token almashtirilgan edi |
| **1** | **1.3 + 5.1** | Birga (bir hodisaning ikki tomoni), bot saytni bloklab turibdi |
| **2** | **1.2** | Eng katta o'lchanadigan yutuq (~20 daq/soat) |
| **3** | **1.4** | 1.2 dan keyin: qolgan 429 xavfini yopadi |
| **4** | **4.1 → 4.2 → 4.3** | 4.1 o'lchov beradi, 4.2 asosiy yutuq, 4.3 qolgani |
| **5** | **3.3** | Yagona omon qolgan baza ishi (N+1) |
| **6** | **1.5** | 1.1 hal bo'lmaguncha to'liq yopilmaydi — buni bilib turib qiling |
| **7** | **5.2, 5.3** | Gigiyena |
| **8** | **2.2 → 1.1** | 2.2 **shart**, keyin 1.1 (endi 3.4 to'sig'i yo'q) |
| **9** | **2.3** | Uysot tomonida — [WEBHOOK_MUAMMOSI.md](WEBHOOK_MUAMMOSI.md) |
| — | ~~3.1, 3.2, 3.4~~ | ❌ **BEKOR** — noto'g'ri (lokal SQLite) dalilga asoslangan edi |

### Yangi ish (avvalgi ro'yxatda yo'q edi)

| Bo'lim | Nima |
|---|---|
| **5.4** (yangi) | **CRM 401'ini qo'riqchi ushlamadi** — 3 kun jimlik. Kuzatuvni kengaytirish kerak |

---

*Hujjat 2026-08-07, tuzatildi 2026-08-08. Manba:
[SAYT_QOTISHI_TAHLIL.md](SAYT_QOTISHI_TAHLIL.md), usul:
[CHUQUR_TAHLIL_METODIKASI.md](CHUQUR_TAHLIL_METODIKASI.md).*
