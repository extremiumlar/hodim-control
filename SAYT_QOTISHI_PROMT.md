# Promt: sayt qotishini ILDIZIDAN tugatish

> Bu — AI agentga beriladigan **bitta to'liq topshiriq**. Nusxalab bering.
> Ichida 2026-08-07…12 oralig'ida **jonli o'lchangan** barcha faktlar bor —
> agent ularni qaytadan qidirmasin, lekin **tasdiqlasin**.

---

```
VAZIFA

`hodimlar_tizimi` loyihasida saytning qotishini ILDIZIDAN tugatish yo'lini
top. Menga palliativ (vaqtinchalik yamoq) emas, ARXITEKTURAVIY yechim kerak.

Sen avval tizimni TO'LIQ o'rganasan, og'riqli nuqtalarni o'lchaysan, so'ng
bir nechta yechim variantini narx-foyda bilan taqdim etasan. Kod YOZMAYSAN —
avval tahlil va taklif, tuzatishni men alohida buyuraman.


═══════════════════════════════════════════════════════════════
1. TIZIM (ma'lum, tekshirilgan)
═══════════════════════════════════════════════════════════════

Backend : FastAPI (ASGI), Python 3.11
Baza    : PostgreSQL (production). DIQQAT: repodagi `app.db` — 0 baytlik
          qoldiq, lokal `.env` esa SQLite ko'rsatadi. PRODUCTION = POSTGRES.
Frontend: React/Vite → `webdist/` statik
Bot     : Telegram, polling rejimida ALOHIDA jarayon (`bot.main`),
          API bilan in-process gaplashadi — Passenger'ga TEGMAYDI
Cron    : `scripts/cron_tick.py`, har daqiqada (cPanel cron)
Hosting : ahost (de.ahost.cloud), cPanel + CloudLinux, SHARED, root YO'Q
Deploy  : Passenger → `deploy/cpanel/passenger_wsgi.py` → a2wsgi
          ASGIMiddleware → FastAPI

Muhim hujjatlar:
  SAYT_QOTISHI_TAHLIL.md      — dastlabki tahlil (ba'zi joylari XATO, pastga qara)
  TAHLIL_TOPSHIRIQLARI.md     — 18 bo'limli kartalar
  CHUQUR_TAHLIL_METODIKASI.md — ISHLASH USULI, quyida majburiy


═══════════════════════════════════════════════════════════════
2. O'LCHANGAN FAKTLAR — qayta o'lchama, lekin TASDIQLA
═══════════════════════════════════════════════════════════════

KONKURENTLIK = 1
  6 ta parallel `/health` → 2.77 / 3.01 / 3.52 / 4.02 / 4.52 / 5.02 s
  (mukammal zinapoya = qat'iy navbat). `ps` da bitta `wsgi-loader.py`.
  Sabab: a2wsgi bitta event-loop thread'ga topshiradi va chaqiruvchi WSGI
  thread'ni bloklaydi; Passenger'ning Python qo'llab-quvvatlashi jarayon
  modelida va bu hostda 1 ta ishchi berilgan.
  ⇒ FastAPI async bo'lsa ham, amalda bir vaqtda BITTA so'rov ishlanadi.

SOVUQ START
  Passenger ishchini ~4 soniya bo'shliqdan keyin O'CHIRADI.
    3s tanaffus  → 0.013s (issiq)
    5s va undan yuqori → 1.5s (sovuq) — barcha oraliqlarda takrorlandi
  Import taqsimoti (jami 1119 ms):
    fastapi+sqlalchemy 316 ms | db.models 149 ms | routerlar 651 ms | a2wsgi 3 ms
  Alohida modullar: openpyxl 62 ms, httpx 44 ms — ya'ni BITTA og'ir
  kutubxona yo'q, vaqt 37 ta router bo'ylab tarqalgan.

CRON YUKI (har biri jonli o'lchandi)
  /daily-results/sync           4.14 s   ← YAGONA og'ir, har TOQ daqiqada
  /anketa/tick                  0.017 s
  /stats/lead-stages/group-tick 0.018 s
  /attendance/digest-tick       0.016 s
  /knowledge/tick               0.016 s
  /playbook/tick                0.016 s
  ⚠️ `/daily-results/sync` davomiyligi CRM yukiga qarab 4s dan 40s gacha
  o'zgaradi (boshqa kuzatuvda 40.3 s qayd etilgan; kod izohida "~30-40s").

RESURS LIMITLARI (CloudLinux LVE, `uapi ResourceUsage`)
  EP (kirish jarayonlari) : 40      (ishlatilgan ~0)
  NPROC                   : 80      (ishlatilgan ~7)
  PMEM                    : 1 GB    (ishlatilgan ~260 MB)
  CPU                     : 100% = 1 YADRO
  IOPS / IO               : 200 / 10 MB/s
  Inodes                  : 50 000  (68% band — kuzatuvda tutilsin)
  Ishchi RSS              : ~114-122 MB

BOSHQA JARAYONLAR (xotira byudjeti uchun)
  bot.main            ~233 MB
  chatbot userbot ×2  ~135 MB har biri (BOSHQA loyiha, TEGMA)
  cron_tick (cho'qqi) ~91 MB


═══════════════════════════════════════════════════════════════
3. SINAB KO'RILGAN VA RAD ETILGAN — TAKRORLAMA
═══════════════════════════════════════════════════════════════

❌ `.htaccess` ga `PassengerMinInstances 1`
   → butun sayt HTTP 500 berdi, darhol qaytarildi.
   Bu hostda Passenger direktivalarini o'zimiz qo'sha OLMAYMIZ.

❌ Sovuq startni optimallashtirish
   → o'lchandi: eng katta yutuq openpyxl (62 ms). 1119 ms ning asosiy qismi
   FastAPI+SQLAlchemy+37 router. Sezilarli qisqartirish MUMKIN EMAS.

❌ «Isitgich» (har 3 soniyada /health ga so'rov)
   → EGASI RAD ETDI: bu palliativ, ildizni tuzatmaydi. Qayta taklif qilma.

❌ SQLite / WAL / indekslar bo'yicha butun tahlil
   → ASOSSIZ edi: lokal SQLite sxemasi production deb qabul qilingan.
   Production PostgreSQL va kerakli indekslar allaqachon bor.

✅ ALLAQACHON TUZATILGAN (qayta qilma):
   • Bot webhook → polling: xotira 228→114 MB, sovuq start 2.8→1.5 s,
     bot trafigi Passenger'da 50/kun → 0
   • Uysot webhook ishlaydi (6 ms), rad etilganlar ham jurnalga tushadi
   • `logs/api.log` fayl-logging


═══════════════════════════════════════════════════════════════
4. OCHIQ MUAMMOLAR (ustuvorlik bo'yicha)
═══════════════════════════════════════════════════════════════

P1. `/daily-results/sync` yagona ishchini 4-40 soniya bloklaydi, har 2 daqiqada.
    Ma'lum yechim: cron jarayonining O'ZIDA bajarish. Naqsh loyihada BOR va
    ishlaydi — `cron_tick.py: _run_service_inprocess` (hot_lead, idle_watch,
    lead_sync, lead_diff shu yo'l bilan ko'chirilgan).

P2. Sovuq start: har izolyatsiyalangan so'rovga +1.5 s.

P3. Uysot rate byudjeti JARAYON-ICHI (`crm/uysot.py: _SharedRateBudget`).
    Production'da 2-3 jarayon alohida byudjet bilan ishlaydi → jami Uysot
    limitidan (60/daq) oshadi → 429 bo'ronlari.

P4. Excel eksport: N+1 (har xodimga 5+ so'rov) + `wb.save()` sinxron CPU
    ishi (`api/services/export.py`). Konkurentlik 1 da butun saytni muzlatadi.
    DIQQAT: `asyncio.to_thread` YETARLI EMAS — a2wsgi'da chaqiruvchi WSGI
    thread baribir bloklangan bo'ladi.

P5. N+1 halqalar ~15 joyda (payroll, bonuses, anketa, weekly_stats, export;
    bonuses.py da halqa ichida `commit`).


═══════════════════════════════════════════════════════════════
5. ISHLASH USULI — MAJBURIY
═══════════════════════════════════════════════════════════════

`CHUQUR_TAHLIL_METODIKASI.md` ni O'QI va unga AMAL QIL. Eng muhim uchtasi:

  1. Har da'vo uchun DALIL: `fayl:qator` yoki jonli o'lchov. "Odatda shunday
     bo'ladi" — dalil emas.
  2. Sabab zanjiri KAMIDA 3 bo'g'in, loyihaviy qarorga yoki tashqi cheklovga
     yetguncha. Simptomni qayta aytish — ildiz emas.
  3. Har diagnozni RAD ETISHGA urin: "agar noto'g'ri bo'lsam, nimani
     ko'rardim?" — va o'shani tekshir.

Qo'shimcha qat'iy qoidalar:

  • O'LCHAMASDAN XULOSA QILMA. Men aynan shunda xato qildim: 5 daqiqalik
    kuzatuvga qarab "cron aybdor emas" degandim — aslida `/daily-results/sync`
    o'sha payt tez bo'lgan, boshqa paytda 40 soniya. O'lchovni TURLI vaqtda
    va TURLI yukda takrorla.
  • "Bu kod nega shunday yozilgan?" — git log va izohlarni o'qi. Bu loyihada
    ko'p "xato" ko'ringan narsa ONGLI qaror (WAL o'chirilgani, cron
    daqiqalarining toq/juftga taqsimlangani, descriptor o'rtachalash olib
    tashlangani). Ularni "tuzatib" ishlab turgan narsani buzma.
  • BUZMASLIK SHART: bot (polling+in-process), Uysot webhook, cron
    joblari, mobil ilova, davomat/Face ID.


═══════════════════════════════════════════════════════════════
6. MENDAN KUTILADIGAN NATIJA
═══════════════════════════════════════════════════════════════

A) TIZIM XARITASI
   Bitta so'rov Passenger'ga kirganidan javobgacha qaysi qatlamlardan
   o'tadi; har qatlamda qancha vaqt ketadi (o'lchov bilan); qayerda
   navbat hosil bo'ladi.

B) OG'RIQLI NUQTALAR RO'YXATI
   Har biri uchun: qanday sharoitda og'riydi, KUNIGA QANCHA VAQT yo'qoladi
   (raqamda), qanchalik tez-tez, kimga ta'sir qiladi (rahbar / xodim /
   mobil ilova / bot).

C) YECHIM VARIANTLARI — kamida 4 ta, TOIFALARGA AJRATILGAN

   Toifa 1 — ARXITEKTURAVIY (ildizni yo'q qiladi)
     Masalan: Passenger'ni butunlay chetlab o'tish yo'llari; doimiy ASGI
     server + proksi; ilovani bo'lish (og'ir yo'llarni alohida jarayonga);
     boshqa hostingga ko'chish. Har biri uchun: bu hostda MUMKINMI, nima
     talab qiladi, nimani buzadi.

   Toifa 2 — YUKNI OLIB TASHLASH (ildizga tegmaydi, lekin sababni yo'qotadi)
     Masalan: P1 (in-process ko'chirish), P4, P5.

   Toifa 3 — PALLIATIV (ochiq shunday deb belgila)
     Egasi palliativlarni yoqtirmaydi — ularni TAKLIF sifatida emas,
     "agar 1 va 2 imkonsiz bo'lsa" izohi bilan ber.

   Har variant uchun MAJBURIY:
     • Kutilayotgan natija RAQAMDA (masalan: "izolyatsiyalangan so'rov
       1.5s → 0.15s", "har 2 daqiqadagi 4-40s cho'qqi butunlay yo'qoladi")
     • Bajarish mehnati (soat)
     • Xavf: nima buzilishi mumkin, qanday qaytariladi
     • Qanday SINOVDAN o'tkaziladi (o'lchanadigan mezon)

D) TAVSIYA ETILGAN YO'L
   Qaysi variantlar, qaysi tartibda va NEGA. Rad etilganlar sababi bilan.

E) NIMANI QILMASLIK KERAK
   Ko'rinishidan jozibali, lekin bu sharoitda foydasiz/zararli g'oyalar
   (masalan yuqoridagi 3-bo'limdagilar) — va nega.


═══════════════════════════════════════════════════════════════
7. YUZAKI JAVOB BELGILARI — o'zingni shunga qarshi tekshir
═══════════════════════════════════════════════════════════════

  [ ] "Kesh qo'shamiz" — nega sekin ekani o'lchanmasdan
  [ ] "Ishchi sonini oshiramiz" — 3-bo'limda RAD ETILGAN, hostda mumkin emas
  [ ] "Kodni optimallashtiramiz" — qaysi qator, qancha yutuq, o'lchov qani?
  [ ] `asyncio.to_thread` ni yechim deb taklif qilish — a2wsgi'da yordam
      bermaydi (4-bo'lim P4 ga qara)
  [ ] Bitta variant taklif qilish
  [ ] "Yangi muammo tug'dirmaydi" deb yozish
  [ ] Raqamsiz baho ("ancha tezlashadi", "sezilarli yaxshilanadi")

BOSHLA: avval tizimni o'rgan va o'lcha, keyin A→E bo'limlarini yoz.
Aniqlik kerak bo'lsa — SO'RA, taxmin qilma. Kod yozma.
```

---

## Promtdan foydalanish

1. Yuqoridagi blokni nusxalab agentga bering
2. Agent A→E bo'limlarini qaytaradi (kod emas, tahlil va takliflar)
3. Javobni **7-bo'lim ro'yxati** bilan tekshiring
4. Yoqqan variantni tanlab, alohida topshiriq bilan bajartiring

## Nega shu ma'lumotlar kiritilgan

| Bo'lim | Nimani oldini oladi |
|---|---|
| 2 — o'lchangan faktlar | Agent kunlarni qayta o'lchashga sarflamaydi |
| 3 — rad etilganlar | Bir marta sinalgan va yiqilgan yo'llar takrorlanmaydi (ayniqsa `PassengerMinInstances` — u saytni **500 qilgan**) |
| 5 — "o'lchamasdan xulosa qilma" | **Mening xatoim** — bir marta o'lchab «cron aybdor emas» degandim, noto'g'ri chiqdi |
| 5 — "bu kod nega shunday yozilgan" | Ongli qarorlarni "tuzatib" buzib qo'yishning oldini oladi |
| 6C — toifalarga ajratish | Palliativ va arxitekturaviy yechim aralashib ketmaydi |
| 7 — yuzakilik ro'yxati | Sizga javob sifatini 30 soniyada baholash imkonini beradi |

Fayl sifatida ham saqladim: **[SAYT_QOTISHI_PROMT.md](SAYT_QOTISHI_PROMT.md)** — keyingi safar ham ishlatasiz. Commit qilaymi?

