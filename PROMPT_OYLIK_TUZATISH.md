# PROMPT — oylik / jarima / qo'shimcha ish tizimini to'liq tuzatish

> Bu faylni yangi seansda **to'liq nusxalab** Claude'ga bering. U o'zi yetarli —
> oldingi suhbat konteksti kerak emas.
>
> Tayyorlangan: 2026-08-11 · Dalillar jonli production bazasidan olingan.

---

## Vazifa

`D:\Project\hodimlar_tizimi` loyihasidagi **oylik ish haqi, kechikish jarimasi,
qo'shimcha ish va KPI bonusi** tizimini to'liq ko'rib chiq, buglarni topib
tuzat va deploy qil.

Quyida men (oldingi seans) jonli bazada tekshirib **tasdiqlagan** buglar bor.
Ulardan tashqari ham buglar bo'lishi mumkin — mustaqil qidir.

⚠️ **Muhim:** quyidagi «tasdiqlangan» faktlar 2026-08-11 holatiga tegishli.
Ish boshlashdan oldin har birini **qayta tekshir** — vaziyat o'zgargan
bo'lishi mumkin. Menga ishonma, o'zing ko'r.

---

## A. TASDIQLANGAN BUG-1 — tasdiqlangan qo'shimcha ish to'lanmayapti

### Dalil (jonli baza)

```
Qo'shimcha ish yozuvlari:
  Gulomjon  2026-08-05   59 daq  approved  auto_attendance
  Gulomjon  2026-08-06   13 daq  approved  auto_attendance
  Gulomjon  2026-08-07   30 daq  approved  auto_attendance
  Gulomjon  2026-08-08   75 daq  approved  auto_attendance
  Gulomjon  2026-08-09   52 daq  approved  auto_attendance
                        --------
                        229 daq, hammasi TASDIQLANGAN

Gulomjon profili: enabled=True, mode=fixed_rate, fixed_rate_per_hour=50 000

2026-08 payslip'lari: 13 ta, overtime_amount = 0.00  ← HAMMASIDA NOL
```

Kutilgan: `229/60 × 50 000 ≈ 190 833 so'm`. Haqiqiy: **0**.

### Asosiy shubha (tekshir!)

`payroll_periods` da `2026-08` uchun `calculated_at = 2026-08-03 15:00`, lekin
qo'shimcha ish yozuvlari **2026-08-05 dan keyin** yaratilgan. Ya'ni payslip
hisoblangandan KEYIN qo'shilgan hamma narsa (qo'shimcha ish, qo'lda
qo'shimcha/ushlanma, jarima) payslip'ga **umuman tushmaydi** va buni hech kim
sezmaydi — saytda «bu hisob eskirgan» degan belgi YO'Q.

### Nima qilish kerak

1. Gipotezani tasdiqla: `2026-08` ni qayta hisoblab, `overtime_amount`
   o'zgaradimi. (Qayta hisoblash **pulni o'zgartiradi** — avval egasidan
   ruxsat so'ra.)
2. **Eskirganlik belgisi**: payslip hisoblangandan keyin unga tegishli yangi
   ma'lumot paydo bo'lsa (yangi tasdiqlangan overtime / adjustment / davomat
   tuzatishi), saytda aniq ogohlantirish chiqsin: «Bu hisob eskirgan — qayta
   hisoblang». Buni `Payslip.calculated_at` bilan bog'liq yozuvlarning
   `created_at`/`updated_at` ini solishtirib aniqlash mumkin.
3. Qo'shimcha ish **tasdiqlangan** paytda HR'ga «davrni qayta hisoblang»
   eslatmasi yuborilsinmi — o'ylab ko'r va taklif qil.

### `compute_overtime` da JIM NOLGA aylanadigan 6 ta yo'l

`api/services/payroll.py::compute_overtime` — har biri **xatosiz, izohsiz** 0
qaytaradi. Bu «nega qo'shimcha ish yozilmadi» degan savolni javobsiz qoldiradi:

| # | Shart | Natija |
|---|---|---|
| 1 | `profile is None or not profile.enabled` | 0 |
| 2 | `e.minutes < profile.min_minutes` | o'sha kun jim tashlanadi |
| 3 | `total_minutes <= 0` | 0 |
| 4 | `derived` rejim + `multiplier is None` | stavka 0 |
| 5 | `derived` rejim + xodimda oylik stavkasi yo'q | stavka 0 |
| 6 | `norm_hours == 0` (jadval bo'sh) | stavka 0 |
| 7 | `fixed_rate` rejim + `fixed_rate_per_hour is None` | `_dec(None)` → 0 |

**Talab:** har bir 0-holat payslip `breakdown` iga SABAB bilan yozilsin
(masalan `overtime_skipped: "multiplier sozlanmagan"`), UI'da ko'rinsin.
Jim nol — eng yomon xato turi, chunki hech kim sezmaydi.

---

## B. TASDIQLANGAN BUG-2 — bonus oylikdan katta, baza esa nol

### Dalil (jonli baza, 2026-07)

```
Xodim         baza      bonus        net
Firuzabonu       0    7 096 000   7 096 000
Shahnoza         0    5 115 000   5 115 000
Albina           0    1 114 000   1 114 000
Hayot            0      630 000     630 000
```

Ikki xato bir joyda:

1. **`baza = 0`** — o'sha xodimlarda oylik stavkasi (`salary_rates`) yo'q edi.
   Payslip yaratildi, lekin asosiy oylik nol.
2. **Bonus 7 million** — KPI stavkalari o'sha paytda kodda PLACEHOLDER
   konstanta edi (`2000`/suhbat, `5000`/tashrif) va real CRM raqamlariga
   ko'paytirilgan.

Natija: oyligi umuman belgilanmagan odamga 7 million «bonus» yozilgan.

### Holat o'zgargan (tekshir!)

KPI stavkalari `kpi_rates` jadvaliga ko'chirilgan (commit `4aefe09`) va jadval
**bo'sh**. Ya'ni hozir qayta hisoblansa bonus **0** ga tushadi. Bu ham to'g'ri
emas — egasi stavkalarni kiritishi kerak.

### Nima qilish kerak

1. `run_payroll` xodimda **stavka yo'q** bo'lsa nima qilishi aniqlansin:
   hozir payslip'ni baza=0 bilan yaratadi. Bu chalg'ituvchi. Variantlar:
   (a) payslip umuman yaratilmasin, (b) yaratilsin-u aniq «STAVKA YO'Q»
   bayrog'i bilan. Egasidan so'ra.
2. `preflight` allaqachon `no_salary_rate` ro'yxatini beradi va `ok=False`
   qiladi — LEKIN hisoblashni **to'xtatmaydi**. Hisoblash `ok=False` bo'lsa
   ogohlantirishi yoki majburiy tasdiq so'rashi kerakmi — o'ylab ko'r.
3. Bonus/baza nisbati aql bovar qilmasa (masalan bonus bazadan 3 barobar
   katta) — payslip'da ogohlantirish chiqsin.

---

## C. TEKSHIRILMAGAN — kunlik «oyligingiz tasdiqlandi» xabari

### Egasining shikoyati

> «Har kuni oylik tasdiqlandi deb Dasturchi va HR ga boryapti, balkim boshqa
> xodimlarga ham borayotgandir.»

### Men aniqlagan narsalar (takrorlama, davom ettir)

- Xabar matni `api/routers/payroll.py::approve_period` da:
  `"💵 {period} oyi uchun oyligingiz tasdiqlandi..."` — u **har bir payslip
  egasiga** yuboriladi.
- **LEKIN** `approve_period` production'da **hech qachon ishlamagan**:
  `audit_logs` da `payroll_period_approved` yozuvi **umuman yo'q**.
- Kunlik cron'da `approve` chaqiruvi **yo'q** (`scripts/cron_tick.py` va
  `scheduler/` tekshirildi).
- `payroll_calculated` atigi **7 marta** (2026-07-27 .. 2026-08-03), kunlik emas.
- `bonus_calculated` esa **25 marta** (2026-07-07 .. 07-31) — deyarli har kuni.
  U `api/routers/bonuses.py` da har bir xodimga
  `"💰 Bonusingiz ({period}) hisoblandi"` yuboradi.

### Shubha

Egasi ko'rayotgan kunlik xabar ehtimol **bonus xabari** yoki
`late-warnings-tick` dagi jarima ogohlantirishi. Yoki `MONTHLY_BONUS_DAY =
"last"` shartida xato bor va job har kuni ishlayapti.

### Nima qilish kerak

1. `scripts/cron_tick.py` dagi `last_day` hisobini tekshir — `bonus_calculated`
   nega 25 marta ishlagan? Oyning oxirgi kuni bir marta bo'lishi kerak edi.
2. Egasidan **xabarning aniq matnini va skrinshotini** so'ra — «tasdiqlandi»
   so'zi qaysi xabarda ekanini aniqlash uchun. Taxmin bilan tuzatma.
3. Yuborilgan xabarlar **jurnali yo'q** — shuning uchun «kimga nima ketgan»
   savoliga javob berib bo'lmaydi. Yengil `notification_log` jadvali qo'shishni
   taklif qil (kim, qachon, qaysi toifa, matn hash'i). Busiz bu sinf
   muammolar har safar taxmin bilan hal qilinadi.
4. Har bir avtomatik xabar uchun **takrorlanmaslik qo'riqchisi** bor-yo'qligini
   tekshir (`attendance_reminders` jadvalidagi kabi iz). Bonus jobida bunday
   qo'riqchi YO'Q — shuning uchun har chaqiruvda qayta yuboradi.

---

## D. Egasining aniq talablari (bajarilishi shart)

1. **Kechikish limitidan o'tsa** — HR belgilagan summa **har kunga** oylikdan
   ayirilsin. Mexanizm bor (`FinePolicy.fine_per_day`), lekin uchidan-uchiga
   ishlayotgani tasdiqlanmagan — **haqiqiy xodim ma'lumotida** sinab ko'r.
2. **Qo'shimcha ishga** HR belgilagan stavkadagi summa yozilsin — A-bo'limga
   qara.
3. Kunlik keraksiz xabar to'xtatilsin — C-bo'limga qara.

---

## E. Boshqa ma'lum kamchiliklar (tahlildan)

To'liq ro'yxat: [`OYLIK_TIZIMI_TAHLIL.md`](OYLIK_TIZIMI_TAHLIL.md). Qisqacha:

- **Stavka «Sozlamalar» ichida** — kundalik HR ishi kamdan-kam ochiladigan
  bo'limga ko'milgan. Xodim kartochkasiga chiqarish kerak.
- **Stavkani tuzatish yo'li yo'q** — xato kiritilsa faqat Dasturchi tuzatadi
  (`SalaryRate` ataylab o'zgarmas, lekin tasdiqlanmagan davr uchun tahrir
  ruxsat etilishi mumkin).
- **Kalendarda jarima summasi yo'q** — `MonthCalendar` komponenti bor, unga
  pul bog'lanmagan. Yangi kalendar qurmang, mavjudini kengaytiring.
- **Avans UI yo'q** — model bor (`PayrollAdjustment`, `kind='minus'`).
- **Jarimaga e'tiroz mexanizmi yo'q**.
- **`fine_applies_to`** (`bonus_first`/`net_salary`) yakuniy summaga ta'sir
  qilmaydi — kodda «ma'lum cheklov» deb yozilgan, item darajasida
  ko'rsatilmaydi.

---

## F. Global jarima qoidasining hozirgi holati

```
scope=global, is_active=true
  absent_mode                  = deduct_daily   (kelmagan kun kunlik ulush bilan ayiriladi)
  free_late_minutes_per_month  = 90
  fine_per_day                 = 50 000
  monthly_cap_percent          = 20
  grace_minutes                = NULL   ← global sozlamaga (5 daq) tushadi
  early_leave_enabled          = false  ← erta ketish jarimalanmaydi
```

Egasi bu raqamlarni «ChatGPT'dan olingan, haqiqiy qoida emas» dedi. Yakuniy
raqamlarni **egasidan so'ra**, o'zing tanlama.

Diqqat: **90 daqiqa juda yumshoq** — avgustda 15 xodimdan faqat 1 kishi
(Farida, 95 daq) limitdan o'tdi.

---

## G. ASOSIY TO'SIQ — buni birinchi ayting

**15 xodimdan 9 tasida oylik stavkasi YO'Q:**
Firuzabonu, Hayot, Farida, Albina, Sanobar, Abdurahmon, Gulomjon, Abdulaziz,
Otabek.

Ularga oylik ham, jarima ham hisoblanmaydi. Qoida qanday sozlansa ham natija
**0** bo'ladi. Bu kod muammosi emas — ma'lumot yetishmasligi. Ishni
boshlashdan oldin egasiga eslat.

---

## H. Ish tartibi (qat'iy)

1. **Avval `git status` va `git log --oneline -5`.**
2. **Repo PARALLEL seans bilan bo'lishiladi.** Faqat o'zing yozgan/o'zgartirgan
   fayllarni `git add` qil, **hech qachon `git add -A` ishlatma**.
3. Har bir tuzatishdan keyin: test → commit → push → deploy → **jonli
   tekshiruv**.
4. Deploy: `ssh -i ~/.ssh/id_ed25519_hodimlar_cpanel -p 30151
   nuriddi5@167.235.222.200`, papka `~/hodimlar-tizimi`, venv
   `~/virtualenv/hodimlar-tizimi/3.11/bin/python`.
   Migratsiya: `cd db && alembic upgrade head`. Keyin `touch tmp/restart.txt`.
5. **Alembic'ni lokalda ildizdan yurit:** `alembic -c db/alembic.ini upgrade
   head`. `db/` ichidan yursang `db/app.db` degan NOTO'G'RI bazaga yozadi.
6. Izohlar va commit xabarlari **o'zbekcha**, «nima» emas «nega» tushuntirsin.

## I. Xavfsizlik qoidalari (buzilmasin)

- **Haqiqiy Telegram xabari yubormang.** Lokal `.env` da **production bot
  tokeni** bor. `approve_period`, bonus jobi, digest — hammasi haqiqiy
  xodimlarga xabar yuboradi. Sinovda `dry_run` ishlating yoki xabar yuborish
  qismini chetlab o'ting.
- **Pulga tegadigan amalni ruxsatsiz bajarmang.** Payslip qayta hisoblash,
  davrni tasdiqlash, jarima qoidasini o'zgartirish — har biri uchun egasidan
  alohida ruxsat so'ra.
- Sinov ma'lumotlari `T-` prefiksi bilan va oxirida **to'liq tozalansin**
  (`audit_logs` dan ham — `target_user_id` va `actor_id` bo'yicha).
- Production bazasi **PostgreSQL**, lokal — SQLite. Yangi so'rov ikkala
  dialektda ham sinalsin. Ilgari aynan shu farq tufayli
  `date >= 'satr'` jonli serverda 500 bergan (commit `87bb8d6`).

## J. Testlar

Mavjud to'plamlar (`test.py`) buzilmasin:
`test_payroll_engine`, `test_payroll_api`, `test_kpi_rates`,
`test_absent_deduct_daily`, `test_payroll_approval_segregation`,
`test_payroll_settings_reedit`, `test_audit_json_guard`.

Test naqshi: **upsert endpointini IKKI MARTA chaqir.** Bir marta chaqiruvchi
testlar `Decimal → JSON` bugini o'tkazib yuborgan edi (birinchi chaqiruv har
doim ishlaydi, bug faqat ikkinchisida chiqadi).

---

## K. Kutilayotgan natija

1. Har bir bug uchun: **sabab** (kod qatori bilan), **tuzatish**, **test**,
   **jonli tasdiq**.
2. Jim nolga aylanadigan yo'llar sabab bilan ko'rinadigan bo'lsin.
3. Egasiga: nima tuzatildi, nima qoldi, undan qanday qaror kutilyapti —
   aniq ro'yxat.
