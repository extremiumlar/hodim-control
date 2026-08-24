# Yangi modullar — AI agent uchun bosqichma-bosqich yo'riqnoma

**Manba TZ:** `Xodimlar_tizimi_yangi_modullar_TUZATILGAN.docx` (31 modul, 98–140 dasturchi-kuni)
**Bu hujjat:** o'sha TZ ni **AI agent bajaradigan seanslarga** bo'lib chiqadi.
**Yozilgan:** 2026-08-18 · **Loyiha:** `D:\Project\hodimlar_tizimi`

---

## 0. Bu hujjat qanday ishlatiladi

1. **Bitta bosqich = bitta agent seansi = 5–6 soat.** Undan katta bo'lsa bo'ling, kichik bo'lsa keyingisini ham oling.
2. Bosqichlar **tartib bilan** bajariladi. Har bosqichning «Oldin» qatorida sharti yozilgan — u bajarilmagan bo'lsa boshlamang.
3. **Har seans oxirida majburiy:** testlar yashil → commit → master'ga merge → serverga deploy → jonli tekshiruv. Yarim qolgan ish keyingi seansga o'tkazilmaydi.
4. Har bosqichda **«Qabul mezoni»** bor. Uning hammasi ✅ bo'lmaguncha bosqich tugagan hisoblanmaydi.
5. TZ da yozilmagan qaror chiqsa — **o'zingiz tanlamang**. Agar qoida vaqt o'tib o'zgarishi mumkin bo'lsa (ushlanma qoldig'i, muddat, limit, summa) — uni **HR panelidagi sozlamaga** chiqaring, default eng xavfsiz tomonga qo'ying. Faqat bir marta qabul qilinadigan tamoyil bo'lsagina egasidan so'rang. Batafsil: hujjat oxiri, 3-band.

**Jami:** 84 bosqich · 4 blok. Blok oxirida tizim **ishlaydigan holatda** bo'ladi (TZ 5-qism: «uch oy davomida hech narsa ko'rinmasligi eng katta xavf»).

---

## 1. HAR BIR SEANSDA AMAL QILINADIGAN QOIDALAR

Bu bo'lim har seans boshida qayta o'qiladi. Bular — TZ tamoyillari va shu loyihada **jonli tekshirilgan tuzoqlar**.

### 1.1 Tizim tamoyillari (TZ 1-qism — buzilmasin)

| Tamoyil | Amalda nima degani |
|---|---|
| **Appeal hisoblamaydi, Request hisoblaydi** | Yangi modul pulni yoki davomatni O'ZI o'zgartirmaydi. Faqat mavjud mexanizm (`PayrollAdjustment`, `ExcusedDay`) orqali va qo'lda |
| **Tarixiylik** | Stavka, norma, yo'riqnoma UPDATE QILINMAYDI — `effective_from` bilan yangi qator qo'shiladi |
| **AI hukm chiqarmaydi** | AI faqat tasniflaydi; da'voni KOD tekshiradi. Yangi modulda ham AI ayblov chiqarmasin |
| **Sozlanmagan holat xavfsiz tomonga** | Qiymat kiritilmagan bo'lsa — modul JIM turadi, taxminiy raqam chiqarmaydi |
| **Fayl serverda saqlanmaydi** | Faqat Telegram `file_id`. Disk 537/1024 MB band — video saqlansa tizim bir necha kunda to'xtaydi |

### 1.2 Ko'rinish qoidasi (TZ 4-qism — istisnosiz)

> **XODIM FAQAT O'ZIGA TEGISHLI MA'LUMOTNI KO'RADI.**

- Filtr **serverda**. Mijozga hammasini yuborib, interfeysda yashirish **TAQIQLANADI**.
- Begona so'rovga **404**, 403 emas (403 = «yozuv bor» degani, bu ham ma'lumot).
- Har endpoint'da qo'lda `user_id` tekshiruvi yozilmasin — **markazlashgan qatlam** (S-06).
- Menyu ham filtrlansin: tegishli bo'lmagan bo'lim **umuman ko'rinmasin** (`GET /me/sections`).
- Bildirishnomada boshqa xodimning ismi/natijasi/taqqoslashi **bo'lmasin**.

### 1.3 Loyiha tuzoqlari (jonli uchragan — takrorlanmasin)

| Tuzoq | Nima qilish kerak |
|---|---|
| **Alembic ikki boshoq** | Migratsiya yozishdan oldin `python -m alembic -c db/alembic.ini heads`. Ikkita chiqsa — merge migratsiya (`down_revision = ("a", "b")`). Serverda doim `upgrade heads` (ko'plik) |
| **Revision ID to'qnashuvi** | Parallel seans bir xil ID ishlatgan hollar bo'lgan. Yangi ID tanlashdan oldin `ls db/alembic/versions/` bilan tekshiring |
| **SQLite + Postgres** | `batch_alter_table` ishlatilsin. `batch_alter_table` ichida `ForeignKey` **qo'shilmasin** (SQLite'da `CircularDependencyError`) — modelda qoldiring, migratsiyada oddiy `Integer` |
| **Test xabar yuboradi** | Test faqat `NOTIFICATIONS_ENABLED=false` bilan ko'tarilgan serverga qarshi ishlaydi (qo'riqchi bor). Aks holda **haqiqiy xodimlarga Telegram ketadi** |
| **Test jonli ma'lumotga tegadi** | Test yozuvlari `T-` prefiksi bilan. Ommaviy amal chaqirilsa (masalan norma tarqatish) **doim `user_ids` bilan cheklang** — bir marta 4 ta haqiqiy xodimning normasi o'zgarib ketgan |
| **Passenger — 1 ishchi** | Og'ir ish (hujjat generatsiyasi, eksport, statistika) **so'rov ichida BAJARILMAYDI**. Cron tick'ga qo'yiladi, foydalanuvchiga «tayyorlanmoqda» deyiladi, tayyor bo'lganda botga yuboriladi |
| **Diff-skaner productionda ISHLAMAYDI** | Webhook jonli bo'lgani uchun `lid diff: skipped: webhook_mode`. CRM'dan yangi maydon olish kerak bo'lsa — ommaviy skanerga tayanmang, `GET /lead/{id}` boyituvchisi orqali |
| **CRM so'rov limiti** | 60 so'rov/daqiqa, boshqa ishlar bilan bo'lishiladi. Yangi CRM so'rovi qo'shsangiz — byudjetli (tick'da N ta) va `_limited_request` orqali |
| **CRLF** | Server fayllari CRLF, repo LF. `git status` doim «M» ko'rsatadi. `git diff --ignore-all-space` bo'sh bo'lsa — kontent bir xil, `git checkout --` xavfsiz. **stash/pop ishlatmang** — konflikt markerlari faylga yoziladi |
| **webdist** | `web/src` o'zgarsa pre-commit hook frontendni qayta build qiladi. Commitdan oldin `npx tsc -b` bilan tekshiring |
| **Pul maydonlari** | INTEGER (so'mda), matn emas. Aks holda «5 mln» va «5000000» aralashadi |
| **`metrics = []` vs `None`** | Metrikasiz lavozimga **ataylab bo'sh ro'yxat**. `None` bo'lsa eski standart `suhbat+tashrif` qaytadi |
| **Cron tick semantikasi** | `>=` ishlatilsin («vaqt o'tgan va bugun yuborilmagan»), `==` emas — cron bir daqiqa kechiksa ham ishlasin |

### 1.4 Har seans yakunidagi checklist

```
[ ] npx tsc -b            (web o'zgargan bo'lsa)
[ ] python -m alembic -c db/alembic.ini heads   → BITTA boshoq
[ ] NOTIFICATIONS_ENABLED=false bilan server ko'tarilgan
[ ] test.py  → 0 FAIL
[ ] git add <faqat o'z fayllaringiz>  (parallel seans fayllariga tegmang)
[ ] commit → push → master merge → server pull → alembic upgrade heads → restart
[ ] Jonli tekshiruv: endpoint 200/401, sahifa ochiladi, xato logi toza
[ ] «Xodim boshqa birovning ma'lumotini ko'ra oladimi?» → YO'Q
```

---

## 2. BOG'LIQLIK GRAFIGI

```
A BLOK (poydevor) ─────────────────────────────► hammasidan OLDIN
   S-01..S-09

B BLOK (kichik modullar)          C BLOK (asosiy)
   S-10..S-31                        S-32: O'quv paneli (3.1)  ──┐
      │                                 │                        │
      │                                 ├─► 3.2 Onboarding ◄─────┤
      │                                 ├─► 3.6 Instruktaj ◄─────┤
      │                                 └─► 3.7 Offboarding      │
      │                                                          │
      └─► 3.3 Hujjat mexanizmi ─► 3.9 Ma'lumotnoma               │
                               └─► 3.21 Buyruqlar ─► 3.22 Intizomiy jazo
                                                                 │
      3.16 Tuzilma + acknowledgements ◄──────────────────────────┘
              │
              └─► 3.12 E'lonlar · 3.6 Instruktaj · 3.2 Onboarding (bitta jadval)

D BLOK (to'ldiruvchi) — A, B, C tugagach
   3.23 HR kalendari  ◄── 3.5, 3.8, 3.10, 3.14 dan keyin
   3.30 Kadr auditi   ◄── 3.4, 3.6, 3.16 dan keyin
```

**Qat'iy qoida:** A blok tugamaguncha B ga o'tilmaydi (TZ 5-qism).

---

# A BLOK — 0-BOSQICH (POYDEVOR)

> TZ: «Bular hal qilinmasa, yangi modullar mavjud muammolarni kattalashtiradi.»
> 9 bosqich · A blok tugagach tizim yangi modullarni qabul qilishga tayyor.

## ✅ A BLOK BAJARILDI (2026-08-19) — 9/9

| Bosqich | Holat | Commit |
|---|---|---|
| S-01 kelajak kunlari | ✅ | `fd5a967` |
| S-02 ushlanma → bonusdan | ✅ | `c9f11e0` |
| S-03 «ushlanma» atamasi | ✅ | `c6d283f` |
| S-04 `GET /me/sections` | ✅ | `bb1e802` |
| S-05 uchala mijoz | ✅ | `24c672c`, `28e82fa` |
| S-06 ko'rinish filtri | ✅ | `2836f95` |
| S-07 og'ir ish → cron | ✅ | `4d74815`, `7292ac7` |
| S-08 sozlanmagan modullar | ✅ | `6a5b4c7` |
| S-09 bayramlar + ta'til check-in | ✅ | `4eded9d` |

**⚠️ DEPLOY QILINMAGAN:** 9 ta commit lokalda turibdi (IP CSF/LFD blokida).
Blok ochilgach: `git pull && alembic upgrade heads` — ikkita migratsiya bor
(`background_jobs`, `holidays`).

**Kutilayotgan qiymatlar (HR kiritadi):** KPI stavkalari (suhbat/tashrif/video),
qo'shimcha ish koeffitsienti, bayramlar ro'yxati. Panellar tayyor, qiymat 0.

---

### S-01 · Kelajakdagi kunlar muammosini TEKSHIRISH (2.3)
**Oldin:** — · **Modul:** TZ 2.3 · **~3 soat** (qisqa bosqich — keyingisi bilan birga oling)

⚠️ **Bu ish allaqachon qilingan bo'lishi mumkin** — repoda `Oylik: kelajakdagi kunlar «kelmagan» deb sanalmasin (§5.1)` commiti bor. Avval TEKSHIRING, keyin yozing.

**Ish**
1. `git log --oneline --all | grep -i "kelajakdagi kun"` — commit bormi?
2. `api/services/payroll.py::collect_attendance` va `compute_base` — bugundan keyingi kunlar `absent` sanalyaptimi?
3. Test yozing: oy o'rtasida hisoblanganda kelajak kunlar `absent` **emas** va bazadan ayirilmaydi.
4. Xato hali bo'lsa — tuzating.

**Qabul mezoni**
- [ ] Joriy oyni oy o'rtasida hisoblasak, kelajak kunlar uchun ayirma YO'Q
- [ ] Test bu qoidani qotiradi (fixture: bugun 15-kun, oyda 30 kun)
- [ ] O'tgan oylar hisobiga ta'sir qilmagani tekshirilgan

**Tuzoq:** Payroll fayliga parallel seans ham tegishi mumkin — commitdan oldin `git status` ni tekshiring.

---

### S-02 · Jarima → bonus: model va hisob (2.1, 1-qism)
**Oldin:** S-01 · **Modul:** TZ 2.1 · **~6 soat** · 🔴 **HUQUQIY XAVF**

**Kontekst:** Hozir `fine_applies_to` default `net_salary` — jarima to'g'ridan-to'g'ri ish haqidan ushlanadi. TZ: bu O'zbekiston Mehnat kodeksiga zid va tekshiruvda birinchi topiladigan xato.

**Ish**
1. `FinePolicy.fine_applies_to` default'ini `bonus_first` ga o'zgartirish (migratsiya: mavjud qatorlarni ham ko'chirish — lekin **eski payslip'larga tegmaslik**).
2. `payroll.build_payslip`: `bonus_first` rejimida ushlanma **avval bonusdan** olinadi.
3. ⭐ **QOLDIQ QOIDASI — HR PANELIDAN BOSHQARILADI, kodda qotirilmaydi.**
   Bonus ushlanmadan kam bo'lsa qolgani nima bo'ladi — bu biznes qarori va u
   vaqt o'tib o'zgarishi mumkin. Shuning uchun **agent egasidan so'ramaydi va
   o'zi tanlamaydi** — sozlamani panelga chiqaradi (naqsh: `funnel_settings`
   va `FunnelSettingsCard.tsx`).

   `FinePolicy.fine_remainder_mode` (yangi ustun), uch qiymat:

   | Qiymat | Nima bo'ladi | Izoh |
   |---|---|---|
   | `drop` | Qoldiq **umuman ushlanmaydi** | 🟢 **DEFAULT** — huquqiy jihatdan eng xavfsiz (ish haqiga tegilmaydi) |
   | `carry_next_month` | Qoldiq keyingi oy bonusidan olinadi | Iqtisodiy natija saqlanadi, ish haqiga tegilmaydi |
   | `from_salary` | Qoldiq oylikdan ushlanadi | 🔴 Panelda **qizil ogohlantirish** bilan: «faqat qonunda nazarda tutilgan hollarda» |

   Sozlama har uch darajada ishlaydi (`resolve_policy`: xodim > lavozim >
   global) — mavjud qoida naqshi buzilmasin.
4. HR paneli (`/payroll/settings`): qoida tanlanadi + har variant ostida bir
   qatorlik izoh. `from_salary` tanlansa ogohlantirish ko'rsatiladi va
   `AuditLog` ga yoziladi (kim, qachon, nimaga o'zgartirdi).
5. `carry_next_month` uchun qoldiq qayerda saqlanadi: `PayrollAdjustment`
   yaratilmasin (u pul yozuvi) — `Payslip.breakdown` ga `fine_carried` maydoni
   va keyingi davr hisobida o'qiladi.
6. Band-darajasidagi breakdown: hozir `items` faqat `net_salary` ko'rinishida
   yig'iladi (kodda «ma'lum cheklov» deb yozilgan). `bonus_first` uchun alohida
   qatorlar: `bonus` (to'liq), `fine_from_bonus` (manfiy), qoldiq holati.

**Qabul mezoni**
- [ ] Yangi qoida default `bonus_first` + `fine_remainder_mode='drop'`
- [ ] Uchala qoldiq rejimi HR panelidan tanlanadi, kodda qotirilmagan
- [ ] `from_salary` tanlanganda ogohlantirish chiqadi va auditga yoziladi
- [ ] Payslip qatorlarida ushlanma QAYERDAN olingani ko'rinadi
- [ ] O'tgan davrlar payslip'i **o'zgarmagan** (qulflangan davrlar qayta hisoblanmaydi)
- [ ] Test: 3 rejim × 3 holat (bonus > ushlanma, bonus < ushlanma, bonus = 0) = 9 ssenariy
- [ ] `carry_next_month` da qoldiq keyingi oyda **bir marta** olinadi (ikki marta emas)

**Tuzoq 1:** `apply_fine_cap` (oylik cheklov) `bonus_first` da ham ishlashi kerak. Cheklov bazadan hisoblanadi — bonusdan emas.
**Tuzoq 2:** Sozlama o'zgarsa **o'tgan davrlar qayta hisoblanmasin** — qulflangan davr `PayrollLocked` bilan himoyalangan, lekin qulflanmagan eski davr ham tegilmasligi kerak. Yangi qoida faqat **keyingi hisobdan** kuchga kiradi.

---

### S-03 · Jarima → «ushlanma» atamasi va interfeys (2.1, 2-qism)
**Oldin:** S-02 · **Modul:** TZ 2.1 · **~5 soat**

**Ish**
1. Butun tizimda foydalanuvchi ko'radigan matnlarda «jarima» → **«ushlanma»** yoki **«bonus kamaytirilishi»**: web sahifalar, bot xabarlari, payslip qatorlari, digest, PDF/Excel eksport.
2. Kod ichidagi nom (`fine_*`) **o'zgartirilmaydi** — faqat ko'rinadigan matn. Aks holda migratsiya va tarix buziladi.
3. `grep -rn "jarima" web/src bot api --include=*.tsx --include=*.py` bilan ro'yxat chiqarib, bittasini ham qoldirmang.
4. `VORONKA_TARIFLAR.md` kabi hujjatlarda ham.

**Qabul mezoni**
- [ ] Xodim ko'radigan hech bir joyda «jarima» so'zi yo'q
- [ ] Kod nomlari o'zgarmagan (`fine_amount`, `FinePolicy` — qoladi)
- [ ] Testlar yashil (matn tekshiradigan testlar yangilangan)

**Tuzoq:** Bot klaviatura tugmalari matni o'zgarsa, `F.text == BTN_*` filtrlari buziladi — `bot/keyboards.py` dagi konstantani o'zgartiring, handlerga tegmang.

---

### S-04 · `GET /me/sections` — server tomoni (2.6)
**Oldin:** S-01 · **Modul:** TZ 2.6 · **~5 soat**

**Kontekst:** Hozir «kim nimani ko'radi» **uch joyda** yozilgan: web `Layout.tsx`, bot `keyboards.py`, mobil ilova. Har yangi modul uch joyga qo'shilishi kerak bo'ladi.

**Ish**
1. `api/routers/me_sections.py`: `GET /me/sections` → foydalanuvchi ko'radigan bo'limlar ro'yxati:
   ```json
   [{"key":"attendance","label":"Davomat","icon":"CalendarCheck","path":"/attendance","order":10}]
   ```
2. Manba — **bitta** joyda: `api/services/sections.py` da ro'yxat + har biriga `visible(user) -> bool`.
3. Mavjud uchala ro'yxatni (web nav, bot menyu, mobil) shu yagona manbaga ko'chirish uchun **to'liq inventarizatsiya** qiling: hozir kim nimani ko'radi — jadval qilib yozing.
4. Rol + lavozim metrikasi + shaxsiy bayroqlar (`can_edit_fine_policy` kabi) hisobga olinsin.

**Qabul mezoni**
- [ ] `GET /me/sections` uchala mijoz uchun yetarli ma'lumot beradi (key, label, path, icon, order)
- [ ] Ro'yxat **kodda bitta joyda**
- [ ] Har rol uchun test: boss/hr/rop/employee — nechta va qaysi bo'lim
- [ ] Hozirgi web nav bilan **aynan mos** (regressiya yo'q)

**Tuzoq:** Bot menyusi `ReplyKeyboardMarkup` — u `path` emas, tugma matni ishlatadi. `sections` javobiga `bot_button` maydonini qo'shing.

---

### S-05 · Uchala mijozni `/me/sections` ga o'tkazish (2.6)
**Oldin:** S-04 · **Modul:** TZ 2.6 · **~6 soat**

**Ish**
1. **Web:** `Layout.tsx` dagi `NAV_GROUPS` ni serverdan keladigan ro'yxatga almashtirish. Ikona nomi string bo'lgani uchun `lucide-react` dan dinamik map qiling.
2. **Bot:** `bot/keyboards.py::main_menu` — `api_client.me_sections()` dan quriladi. Keshlash: bir seansda bir marta.
3. **Mobil:** WebView orqali ochiladigan bo'limlar ro'yxati ham shundan.
4. Eski qattiq yozilgan shartlarni **o'chiring** (qoldirilsa ikkita manba bo'lib qoladi).

**Qabul mezoni**
- [ ] Uchala mijozda menyu serverdan keladi
- [ ] Qattiq yozilgan rol sharti qolmagan (`grep -n "role ===" web/src/Layout.tsx` bo'sh)
- [ ] Bot menyusi eski ko'rinish bilan aynan bir xil (regressiya testi)
- [ ] Server bo'lim qo'shsa, mijozda **kod o'zgarmasdan** paydo bo'ladi

**Tuzoq:** Bot menyusi keshlansa, rol o'zgarganda eskisi qolib ketadi — `/start` da kesh tozalansin.

---

### S-06 · Markazlashgan ko'rinish filtri (TZ 4-qism)
**Oldin:** S-04 · **Modul:** TZ 4-qism · **~6 soat** · 🔴 **XAVFSIZLIK**

**Ish**
1. `api/deps.py` ga yagona qatlam:
   ```python
   async def scoped_user_ids(actor, db) -> set[int] | None   # None = hammasi
   def assert_can_view(actor, target_user_id) -> None         # 404 ko'taradi
   ```
2. Qamrov matritsasi TZ 4-qismdan olinadi: xodim → faqat o'zi; ROP → o'z jamoasi (`manager_id`); HR/boss → hammasi; ba'zi modullarda ROP **umuman ko'rmaydi**.
3. Mavjud endpointlarni shu qatlamga ko'chiring (kamida: `employee_documents` kelajakda, `payroll`, `attendance`, `appeals`, `requests`).
4. **404, 403 emas** — `assert_can_view` `HTTPException(404)` ko'taradi.

**Qabul mezoni**
- [ ] Yagona funksiya, har endpointda qo'lda tekshiruv yo'q
- [ ] Begona so'rov → 404
- [ ] ROP «ko'rmaydi» ro'yxatidagi modullarga kira olmaydi
- [ ] Test: har rol × har modul matritsasi (kamida 12 ta tekshiruv)

**Tuzoq:** Eksport (Excel) ham shu qatlamdan o'tsin — TZ da alohida aytilgan.

---

### S-07 · Passenger: og'ir ishni cron'ga ko'chirish naqshi (2.2)
**Oldin:** S-01 · **Modul:** TZ 2.2 · **~5 soat**

**Ish**
1. Serverda root huquqi bor-yo'qligini aniqlang (`sudo -n true`, `systemctl` mavjudmi). Natijani hujjatga yozing.
2. Root bo'lmasa — **oraliq chora**: umumiy «fon ishi» mexanizmi:
   - `background_jobs` jadvali: turi, parametrlar (JSON), holat (`queued/running/done/failed`), natija `file_id`, `user_id`, `created_at`
   - `cron_jobs.background_tick` — navbatdan bittasini oladi va bajaradi
   - So'rov `202 {"job_id": N}` qaytaradi, foydalanuvchi «tayyorlanmoqda» xabarini oladi
   - Tayyor bo'lganda botga fayl yuboriladi
3. **Birinchi mijoz:** mavjud Excel eksport (`api/routers/reports.py`) — `to_thread`siz ishlab, yagona ishchini bloklaydi.

**Qabul mezoni**
- [ ] Excel eksport endi so'rov ichida bajarilmaydi
- [ ] Foydalanuvchi «tayyorlanmoqda» xabarini oladi, tayyor bo'lganda botga fayl keladi
- [ ] Bitta job ikki marta bajarilmaydi (lock yoki `status` qo'riqchisi)
- [ ] Xato bo'lsa `failed` va sabab yoziladi, cron o'lmaydi

**Tuzoq:** Cron har daqiqada yangi jarayon — modul darajasidagi navbat **ishlamaydi**, holat faqat bazada.

---

### S-08 · «Sozlanmagan modullar» bloki (2.7)
**Oldin:** S-04 · **Modul:** TZ 2.7 · **~4 soat**

**Kontekst:** Kamida to'rt modul mexanizmi tayyor, lekin qiymat kiritilmagani uchun jim turibdi (mobilograf normasi, KPI stavkalari, tabrik videolari, bayramlar).

**Ish**
1. `api/services/setup_status.py`: har modul uchun `(nomi, tayyormi, nima yetishmayapti, havola)`.
2. Boshlang'ich ro'yxat: mobilograf video normasi · KPI stavkalari · tabrik videolari · bayramlar jadvali · voronka maqsadi · reklama xarajati · shartnoma bosqichlari.
3. `GET /setup-status` + bosh sahifada blok (faqat HR/boss/dasturchi).
4. **Kengaytiriladigan qilib yozing:** har yangi modul shu ro'yxatga bir qator qo'shadi.

**Qabul mezoni**
- [ ] Bosh sahifada «Sozlanmagan modullar» bloki
- [ ] Har qator to'g'ridan-to'g'ri sozlash sahifasiga olib boradi
- [ ] Hammasi sozlangan bo'lsa blok **umuman ko'rinmaydi**
- [ ] Yangi modul qo'shish uchun bitta lug'at qatori yetadi

---

### S-09 · Bayramlar jadvali + ta'tildagi xodim check-in (2.9)
**Oldin:** S-01 · **Modul:** TZ 2.9 · **~5 soat**

**Ish**
1. `holidays` jadvali: sana, nomi, turi (davlat/kompaniya), yil, `created_at`. Panel: HR yillik ro'yxatni kiritadi.
2. Ish kuni hisoblaydigan **hamma joyni** shunga ulash: `payroll.month_schedule`, `workdays.calc_range`, `target_split._working_days`, `target_track._elapsed_share`.
3. **Ta'tildagi xodim check-in qila olmasin:** `attendance` check-in'da tasdiqlangan `ExcusedDay` bo'lsa — rad etiladi, tushunarli xabar bilan.
4. Dekabr eslatmasi: keyingi yil bayramlari kiritilmagan bo'lsa HR ga xabar (cron).

**Qabul mezoni**
- [ ] Bayram kuni ish kuni sifatida sanalmaydi (4 joyda ham)
- [ ] Ta'tildagi xodim check-in qilolmaydi
- [ ] Bayram kiritilmagan bo'lsa — «Sozlanmagan modullar» da ko'rinadi
- [ ] Test: bayram + ta'til + dam kuni birga tushgan holat

**Tuzoq:** Bayram ish kunini kamaytirgani uchun **oylik norma va payroll prorata** o'zgaradi. O'tgan davrlarni qayta hisoblamang — faqat joriy va kelajak.

---

**✅ A BLOK YAKUNI:** huquqiy xavf yopilgan, ko'rinish bitta joydan boshqariladi, og'ir ish saytni qotirmaydi, sozlanmagan modullar ko'rinib turadi. Endi yangi modul qo'shish xavfsiz.

---

# B BLOK — KICHIK MODULLAR (tez natija)

> TZ 1-bosqich: 23–34 dasturchi-kuni → **22 seans**.
> Bu blokda har modul mustaqil — tartibni o'zgartirish mumkin, faqat 3.3 → 3.9 bog'liqligi saqlansin.

## Holat: 22/22 — B BLOK TUGADI (2026-08-22)

| Bosqich | Holat | Commit |
|---|---|---|
| S-10 kadr hujjatlari — API | ✅ | `c8bc84f` |
| S-11 kadr hujjatlari — bot va kabinet | ✅ | `bdc8211` |
| S-12 muddat eslatmalari — yadro | ✅ | `733d45e` |
| S-13 muddat eslatmalari — cron va panel | ✅ | `7e25112` |
| S-14 hujjat generatsiyasi (.docx) | ✅ | `3f3a63f` |
| S-15 ish taklifi — model va forma | ✅ | `904e9a6` |
| S-16 offer → xodim → onboarding | ✅ | `8016b0e` |
| S-17 ma'lumotnoma generatsiyasi | ✅ | `eb5baa5` |
| S-18 mol-mulk — model va HR paneli | ✅ | `71cea51` |
| S-19 mol-mulk — xodim tomoni va dalolatnoma | ✅ | `a1a1bce` |
| S-20 `acknowledgements` — umumiy qayd | ✅ | `33d07da` |
| S-21 ichki e'lonlar | ✅ | `b62a4c0` |
| S-22 tug'ilgan kun va yubiley | ✅ | `36a55bf` |
| S-23 shtat jadvali | ✅ | `31d3b2d` |
| S-24 sinov muddatidagi xodimlar | ✅ | `50cb278` |
| S-25 ish haqi o'zgarishi sababi | ✅ | `ad30892` |
| S-26 xodim ma'lumotini yangilashi | ✅ | `cac6974` |
| S-27 shartnomani ro'yxatga olish | ✅ | `d4dcf1b` |
| S-28 murojaatlar jurnali — yadro | ✅ | `9db86ef` + `f09a4d8` |
| S-29 murojaatlar → bilim bazasi | ✅ | `8b077bf` + `0f8725b` |
| S-30 ko'rinish auditi | ✅ | `5365f44` |
| S-31 deploy va jonli tekshiruv | ✅ | `47b900f` deploy qilindi |

**B BLOK TUGADI. Keyingisi: S-32** (C blok — o'quv paneli, TZ 3.1).

⚠️ **PARALLEL SEANS** shu repoda «Avans TZ» ustida ishlayapti. `db/models.py`,
`test.py` va web umumiy fayllari birga ishlatiladi — `git add -A` ISHLATMANG,
faqat aniq yo'llar. Migratsiya id tanlashda mavjudlarini tekshiring va
tarmoqlanish bo'lsa merge migratsiyasi yozing.

⚠️ S-16 ning 3-4 bandlari (shtat o'rni «band», onboarding rejasi) 3.20 va
3.2 modullariga bog'liq — ular hali qurilmagan. Javobda `onboarding_ready`
bayrog'i turibdi, modul tayyor bo'lgach shu nuqtadan ulanadi.

---

### S-10 · Kadr hujjatlari arxivi — model va API (3.4)
**Oldin:** S-06 · **~5 soat**

**Ish**
1. `employee_documents`: `user_id`, `doc_type`, `name`, `file_id`, `file_type`, `uploaded_by`, `issued_at`, `expires_at`, `note`, `deleted_at`, `created_at`.
   Turlari: mehnat shartnomasi · lavozim yo'riqnomasi · mol-mulk dalolatnomasi · ishni topshirish dalolatnomasi · tibbiy ma'lumotnoma · diplom/sertifikat · boshqa.
2. `api/routers/employee_documents.py`: `GET /me`, `GET /user/{id}` (HR/boss), `POST` (HR), `DELETE /{id}` (yumshoq).
3. Ruxsat — S-06 qatlamidan. **ROP umuman ko'rmaydi.**

**Qabul mezoni**
- [ ] Xodim faqat o'zinikini ko'radi, begonaga **404**
- [ ] ROP ga 404 (hatto o'z jamoasi bo'lsa ham)
- [ ] Barcha o'qish `deleted_at IS NULL`
- [ ] Fayl serverda saqlanmaydi — faqat `file_id`
- [ ] Test: 8+ (rol matritsasi, soft delete, 404, muddat maydoni)

---

### S-11 · Kadr hujjatlari — bot va kabinet (3.4)
**Oldin:** S-10 · **~5 soat**

**Ish**
1. Bot: HR «Hujjat yuklash» → xodim tanlanadi → tur tanlanadi → fayl yuboriladi → `file_id` saqlanadi (FSM; `bot/handlers/celebration.py` dagi naqsh).
2. Kabinet: «Mening hujjatlarim» — ro'yxat + yuklab olish (`send_file_id` orqali botga qaytariladi).
3. Web (HR): xodim kartochkasida hujjatlar bo'limi.

**Qabul mezoni**
- [ ] HR botdan hujjat yuklay oladi, fayl Telegramda qoladi
- [ ] Xodim o'z hujjatini botdan qayta olishi mumkin
- [ ] Muddati o'tayotgan hujjat ro'yxatda ajratib ko'rsatiladi
- [ ] Test: yuklash → o'qish → soft delete zanjiri

---

### S-12 · Muddat eslatmalari — yadro (3.5)
**Oldin:** S-09 · **~5 soat**

**Ish**
1. `deadlines`: `user_id`, `kind`, `due_date`, `responsible_role`, `reminded_at`, `status`, `source_id`, `note`.
   Turlari: sinov muddati · shartnoma muddati · TX takroriy instruktaj · tibbiy ko'rik · pasport/ruxsatnoma · majburiy kurs.
2. `api/services/deadlines.py`: yaratish/yopish + `upcoming(days)`.
3. Ba'zi muddatlar **hisoblanadi** (shartnoma sanasi + muddat) — jadvalga yozilmasin, hisoblanib chiqsin. Ikkita manba bo'lmasin.

**Qabul mezoni**
- [ ] Muddat qo'lda ham, hisoblanib ham chiqadi
- [ ] `reminded_at` — bir muddat bo'yicha takroriy xabar yo'q
- [ ] Test: `>=` semantikasi (cron bir kun kechiksa ham xabar tushadi)

---

### S-13 · Muddat eslatmalari — cron va xabar (3.5)
**Oldin:** S-12 · **~4 soat**

**Ish**
1. `cron_jobs.deadline_tick` — kuniga bir marta, mas'ul rolga DM.
2. Xabar guruhga emas, **shaxsiy** (muddat = shaxsiy ma'lumot).
3. HR panelida «Yaqinlashayotgan muddatlar» bloki (7/30 kun).

**Qabul mezoni**
- [ ] Kuniga bir marta, takrorlanmaydi
- [ ] Bir necha muddat bir kunga tushsa — **bitta** xabarga birlashadi
- [ ] Test: xabar yuboruvchi patch qilingan holda

---

### S-14 · Hujjat generatsiyasi mexanizmi (3.3, 1-qism)
**Oldin:** S-07 · **~6 soat** · ⭐ **Keyingi uch modul shunga tayanadi**

**Ish**
1. `api/services/docx_render.py` — **yangi kutubxonasiz**: `.docx` = zip, ichida `word/document.xml`. Shablon nusxasi olinadi → belgilar almashtiriladi → zip qayta yig'iladi (`zipfile` + `re`).
2. ⚠️ **Word belgini bir necha XML tegga bo'lib yuboradi.** Yechim: `w:t` matnlarini birlashtirib, keyin almashtirish; shablon tayyorlangach **bir marta sinash majburiy**.
3. `document_templates`: turi, nomi, shablon `file_id`, belgilar ro'yxati (JSON).
4. Natija fayl **cron tick'da** tayyorlanadi (S-07 naqshi), `file_id` bilan qaytariladi.

**Qabul mezoni**
- [ ] Shablondan to'ldirilgan `.docx` chiqadi
- [ ] Bo'lingan belgi holati sinovdan o'tgan (fixture: bo'lingan `w:t`)
- [ ] Yangi kutubxona qo'shilmagan (`requirements.txt` o'zgarmagan)
- [ ] Generatsiya so'rov ichida emas, fon ishida

---

### S-15 · Ish taklifi (offer) — model va forma (3.3, 2-qism)
**Oldin:** S-14 · **~5 soat**

**Ish**
1. `offers`: nomzod_fish, telefon, `position_id` yoki matn, `salary INTEGER`, sinov_muddati, ishga_chiqish_sanasi, `manager_id`, holat, yaratgan_hr_id, `user_id`.
2. Web: «Yangi taklif» formasi → `.docx` yuklab olish havolasi.
3. Tizim nomzodga **hech narsa yubormaydi** — HR o'zi yuboradi.

**Qabul mezoni**
- [ ] `salary` INTEGER (matn emas)
- [ ] Taklif bazada qoladi, keyin qidiriladi
- [ ] Fayl fon ishida tayyorlanadi
- [ ] Test: forma → hujjat → baza yozuvi

---

### S-16 · Offer → xodim → onboarding bog'lanishi (3.3, 3-qism)
**Oldin:** S-15 · **~4 soat**

**Ish**
1. «Qabul qilindi» bosilganda taklifdan **xodim yaratiladi** (F.I.Sh., lavozim, ish haqi qayta terilmaydi).
2. `SalaryRate` yoziladi (`effective_from` = ishga chiqish sanasi).
3. Shtat o'rni «band» bo'ladi (3.20 tayyor bo'lsa).
4. Onboarding rejasi ochiladi (3.2 tayyor bo'lgach ulanadi — hozircha bayroq).

**Qabul mezoni**
- [ ] Bitta bosishda xodim + stavka yaratiladi
- [ ] `offers.user_id` bog'lanadi
- [ ] Ikki marta bosilsa ikkita xodim yaratilmaydi (idempotent)

---

### S-17 · Ma'lumotnoma (spravka) generatsiyasi (3.9)
**Oldin:** S-14 · **~5 soat**

**Ish**
1. Mavjud `certificate` ariza turini «C guruh»dan chiqarish: HR tasdiqlaganda hujjat **avtomatik** shakllanadi.
2. Maqsad tanlanadi (bank / viza / bog'cha / boshqa) — har biriga alohida shablon.
3. Ichida: F.I.Sh., lavozim, ishga qabul sanasi, shartnoma turi, o'rtacha oylik (so'ralsa), hujjat raqami va sanasi.
4. Chiqarilgan hujjat `employee_documents` (3.4) ga yoziladi.

**Qabul mezoni**
- [ ] Ariza tasdiqlanishi bilan hujjat tayyorlanadi
- [ ] Hujjat raqami takrorlanmaydi
- [ ] O'rtacha oylik faqat so'ralganda yoziladi
- [ ] Arxivda «kimga, qachon, qaysi maqsadda» tarixi qoladi

---

### S-18 · Biriktirilgan mol-mulk — model va HR paneli (3.11)
**Oldin:** S-06 · **~5 soat**

**Ish**
1. `assets`: inventar_raqami (unique), nomi, turi, holati, qiymati (INTEGER), `deleted_at`.
   `asset_assignments`: asset_id, user_id, berilgan_sana, qaytarilgan_sana, holati, hujjat_file_id.
2. HR paneli: ro'yxat + biriktirish/qaytarish.
3. Bitta buyum bir vaqtda **bitta** xodimda (qo'riqchi).

**Qabul mezoni**
- [ ] Band buyumni ikkinchi xodimga biriktirib bo'lmaydi
- [ ] Inventar raqami takrorlanmaydi
- [ ] Test: biriktirish → qaytarish → qayta biriktirish

---

### S-19 · Mol-mulk — xodim tomoni va dalolatnoma (3.11)
**Oldin:** S-18, S-14 · **~4 soat**

**Ish**
1. Kabinet: «Menga biriktirilgan» + «Qabul qildim» tugmasi (vaqt yoziladi).
2. Biriktirish/qaytarish dalolatnomasi — S-14 mexanizmi bilan.
3. `standard_set(position_id)` — lavozimga mos standart to'plam (onboarding/offboarding uchun).

**Qabul mezoni**
- [ ] Xodim faqat o'ziga biriktirilganini ko'radi
- [ ] «Qabul qildim» vaqti yoziladi
- [ ] Dalolatnoma `.docx` chiqadi

---

### S-20 · `acknowledgements` — umumiy tanishtirish qaydi
**Oldin:** S-06 · **~4 soat** · ⭐ **Uchta modul shuni ishlatadi (3.16, 3.12, 3.6)**

**Ish**
1. `acknowledgements`: `user_id`, `object_type` (yo'riqnoma/e'lon/instruktaj), `object_id`, `version`, `acknowledged_at`.
2. Yagona servis: `request_ack`, `mark_ack`, `pending_for(user)`, `who_read(object)`.
3. **Versiya muhim:** yangi versiya chiqsa eski tanishuv **o'tmaydi**.

**Qabul mezoni**
- [ ] Uchala obyekt turi bitta jadvalga yozadi
- [ ] Versiya o'zgarsa qayta tanishish talab qilinadi
- [ ] Bir odam bir versiyani ikki marta tasdiqlay olmaydi (unique)

---

### S-21 · Ichki e'lonlar (3.12)
**Oldin:** S-20 · **~5 soat**

**Ish**
1. `announcements`: matn, muallif_id, qamrov (JSON: hamma/rol/lavozim/xodimlar), muhimmi, `file_id`, sana.
2. Botga va kabinetga tushadi. Muhim e'londa «Tanishdim» → `acknowledgements`.
3. **Cheklov:** kuniga N tadan ko'p e'lon yuborilmasin (cooldown).

**Qabul mezoni**
- [ ] Rahbar panelida kim o'qigani/o'qimagani ko'rinadi
- [ ] Kunlik limit ishlaydi
- [ ] Qamrovga kirmagan xodimga e'lon **umuman** ko'rinmaydi

---

### S-22 · Tug'ilgan kun va ish yubileyi (3.14)
**Oldin:** S-09 · **~4 soat**

**Ish**
1. `users.birth_date` qo'shiladi (`hire_date` allaqachon **BOR** — tekshirilgan).
2. Kunlik cron: guruhga tabrik posti — **mavjud `celebration` mexanizmi** ishlatiladi, yangisi qurilmaydi.
3. HR ga bir kun oldin eslatma. Yubiley: 1 yil, 2 yil… (`hire_date` dan).

**Qabul mezoni**
- [ ] Yangi jadval **yaratilmagan**
- [ ] Tabrik guruhga bir marta ketadi (takroriy qo'riqchi)
- [ ] Tug'ilgan kun kiritilmagan xodim uchun jim
- [ ] Sana kiritish HR panelida bor

---

### S-23 · Shtat jadvali (3.20)
**Oldin:** S-06 · **~5 soat**

**Ish**
1. `staff_positions`: bo'lim, `position_id`, birlik soni, oylik vilkasi (min/max INTEGER), holati, `effective_from`.
2. Ekran: jami shtat / band / bo'sh (qaysi lavozimlar).
3. «Band» — faol xodimlardan **hisoblanadi**, qo'lda kiritilmaydi.

**Qabul mezoni**
- [ ] Band soni avtomatik hisoblanadi
- [ ] Bo'sh o'rin ro'yxatda ko'rinadi
- [ ] Xodim ko'rmaydi, ROP faqat o'z bo'limini

---

### S-24 · Sinov muddatidagi xodimlar ro'yxati (3.24)
**Oldin:** S-12 · **~4 soat**

**Ish**
1. Yangi jadval **kerak emas** — `hire_date` + sinov muddatidan hisoblanadi.
2. Ro'yxat: xodim, lavozim, boshlanish/tugash, qolgan kun, onboarding holati, oraliq baho.
3. Muddat yaqinlashganda — `deadlines` (S-12) orqali eslatma.

**Qabul mezoni**
- [ ] Ro'yxat doim ko'rinadi (eslatma o'tib ketsa ham)
- [ ] Muddati o'tganlar ajratib ko'rsatiladi
- [ ] Sinov muddati sozlamasi qayerdan olinishi hujjatlashtirilgan

---

### S-25 · Ish haqi o'zgarishi tarixi (3.25)
**Oldin:** S-02 · **~4 soat**

**Ish**
1. `salary_rates.reason` qo'shiladi (`changed_by` allaqachon **BOR** — tekshirilgan).
2. Sabab **majburiy**: davriy oshirish · lavozim o'zgardi · natija bo'yicha · bozorga moslash · boshqa (matn).
3. Xodim kabinetda **o'z** tarixini ko'radi. ROP ko'rmaydi.

**Qabul mezoni**
- [ ] Sababsiz stavka kiritib bo'lmaydi (400)
- [ ] Eski qatorlarda `reason` NULL — «kiritilmagan» deb ko'rsatiladi
- [ ] Xodim boshqasinikini ko'ra olmaydi (404)

---

### S-26 · Xodim o'z ma'lumotini yangilashi (3.26)
**Oldin:** S-06 · **~5 soat**

**Ish**
1. `profile_change_requests`: user_id, maydon, eski qiymat, yangi qiymat, holat, tasdiqlagan_hr_id, sana.
2. Xodim so'rov yuboradi → HR tasdiqlaydi → **shundan keyin** bazaga tushadi.
3. Maydonlar oq ro'yxati: telefon, manzil, oilaviy holat, favqulodda aloqa. F.I.Sh./pasport — ogohlantirish bilan.

**Qabul mezoni**
- [ ] To'g'ridan-to'g'ri o'zgartirish **yo'q**
- [ ] Oq ro'yxatdan tashqari maydon so'rovi rad etiladi
- [ ] Tasdiqlangach eski qiymat auditda qoladi

---

### S-27 · Shartnomani ro'yxatga olish nazorati (3.28)
**Oldin:** S-10 · **~3 soat**

**Ish**
1. Shartnoma yozuviga: `registered_at`, `registered_by`, `registration_note`.
2. Tizim ro'yxatga olishni **bajarmaydi** — faqat belgini yuritadi.
3. Yangi xodim qo'shilib 3 kun ichida belgi qo'yilmasa → HR ga eslatma (`deadlines`).

**Qabul mezoni**
- [ ] Belgisiz xodimlar ro'yxati bor
- [ ] 3 kundan keyin eslatma, takrorlanmaydi
- [ ] Kadr auditi (3.30) uchun so'rov tayyor

---

### S-28 · Xodim murojaatlari jurnali — yadro (3.29)
**Oldin:** S-06 · **~5 soat**

**Ish**
1. `hr_inquiries`: user_id, savol, javob, toifa, holat, sana, javob_bergan_id.
2. Bot: «HR ga savol» → matn → HR ga DM → javob xodimga qaytadi.
3. Toifa qo'lda yoki mavjud AI tasniflagichi bilan (**AI hukm chiqarmaydi** — faqat toifa).

**Qabul mezoni**
- [x] Savol-javob saqlanadi
- [x] Xodim faqat o'z murojaatlarini ko'radi
- [x] Javobsiz murojaat HR panelida ajralib turadi

---

### S-29 · Murojaatlar → bilim bazasi halqasi (3.29)
**Oldin:** S-28 · **~4 soat**

**Ish**
1. Takrorlanuvchi savollar hisoboti: qaysi toifa necha marta.
2. HR bir bosishda javobni **mavjud `knowledge_entries`** ga `verified` holatida yuboradi.
3. Shundan keyin bot o'zi javob beradi (mavjud Sotuv AI mexanizmi).

**Qabul mezoni**
- [x] «Eng ko'p beriladigan 10 savol» ro'yxati
- [x] Bir bosishda bilim bazasiga o'tadi
- [x] Bilim bazasida javob bo'lsa bot avval o'zi javob beradi
      (⚠️ JIMGINA emas — «to'g'ri keldimi?» deb TAKLIF qiladi;
      sabab `api/services/hr_inquiries.py` izohida)

---

### S-30 · B blok — ko'rinish auditi
**Oldin:** S-10…S-29 · **~4 soat**

**Ish**
1. Har yangi endpoint uchun: xodim / ROP / HR / boss so'rovi bilan test.
2. `GET /me/sections` ga yangi bo'limlar qo'shilgani tekshiriladi.
3. Excel eksport ham filtrdan o'tishi tekshiriladi.

**Qabul mezoni**
- [x] Har yangi modul uchun rol matritsasi testi bor
      (`test_b_block_visibility_audit`, 19 modul × 4 rol)
- [x] Begona so'rov hamma joyda **404**
      (auditda S-29 dagi bitta 403 topildi va tuzatildi)
- [x] Menyuda ortiqcha bo'lim ko'rinmaydi
      (menyu ↔ backend muvofiqligi avtomatik tekshiriladi)

---

### S-31 · B blok — deploy va jonli tekshiruv
**Oldin:** S-30 · **~4 soat**

**Ish**
1. Barcha migratsiyalar serverda (`upgrade heads`), bitta boshoq.
2. HR bilan bitta o'tish: hujjat yuklash, e'lon, mol-mulk biriktirish, spravka.
3. «Sozlanmagan modullar» blokiga yangi qatorlar qo'shilgani tekshiriladi.
4. Disk holati: `df -h`, `du -sh ~/hodimlar-tizimi`.

**Qabul mezoni**
- [x] Jonli serverda tekshirildi: `/api/health` 200, yangi endpointlar
      401 bilan qo'riqlangan, `hr_inquiries` jadvali yaratilgan,
      mavjud 30 ta bilim yozuvi `sales` qamroviga to'g'ri tushdi va
      Sotuv AI hamon 30 tasini ko'radi (regressiya yo'q).
      ⚠️ HR bilan QO'LDA o'tish hali qilinmadi — u odam ishtirokini
      talab qiladi.
- [x] Disk o'sishi: 123 MB → 125 MB (**+2 MB**, chegara 50 MB)
- [x] Cron logida xato yo'q; bot keepalive bilan 12:09 da qayta
      ko'tarildi va polling qilyapti

---

**✅ B BLOK YAKUNI:** HR ning kundalik qog'oz ishi tizimga ko'chdi. Xodim o'z hujjatini o'zi oladi, muddatlar unutilmaydi, mol-mulk yo'qolmaydi.

---

# C BLOK — ASOSIY MODULLAR

> TZ 2-bosqich: 28–39 dasturchi-kuni → **23 seans**.
> **3.1 birinchi qilinadi** — undan keyin 3.2, 3.6 va 3.7 uning mexanizmini qayta ishlatadi.

---

### S-32 · O'quv paneli — inventarizatsiya va model (3.1)
**Oldin:** S-31 · **~5 soat**

**Ish**
1. **Avval o'qing:** `api/services/anketa_data.py`, `api/services/docx_parse.py`, `bot/handlers/anketa.py`, `/anketa/tick`. O'quv paneli — bu **anketa mexanizmining kengaytmasi**, yangi mexanizm emas.
2. Qaysi qism qayta ishlatilishini yozing: tayinlash modeli · holat bazada (`current_q` naqshi, FSM emas) · ketma-ket savol tick'i · docx dan savol ajratish · `file_id` bilan video yuborish.
3. Model: `courses`, `course_materials`, `course_questions` (migratsiya).

**Qabul mezoni**
- [x] Anketa bilan umumiy qism hujjatlashtirilgan — `db/models.py`
      dagi «O'QUV PANELI» bloki (6 ta qayta ishlatiladigan qism +
      anketadan farqi)
- [x] Uch jadval migratsiyasi ikkala dialektda ishlaydi (Postgres
      DDL renderi test bilan tekshiriladi: `BOOLEAN DEFAULT false`,
      `options JSON`); downgrade ham sinaldi
- [x] `deleted_at` bor va barcha o'qish shu bilan filtrlanadi —
      yagona nuqta `courses.py::alive()`, tashqarida `select(Course)`
      test bilan TAQIQLANGAN

**Tuzoq:** Material `file_id` — video **serverda saqlanmaydi**. Disk 537/1024 MB.

---

### S-33 · O'quv paneli — tayinlash va natija modeli (3.1)
**Oldin:** S-32 · **~5 soat**

**Ish**
1. `course_assignments`: user_id, course_id, holat (tayinlandi/boshlandi/tugatildi), joriy material, muddat, tayinlagan_id.
2. `course_results`: assignment_id, ball, foiz, urinish raqami, tugatilgan sana.
3. Tayinlash qamrovi: aniq xodim / rol / lavozim / hamma (anketa naqshi).
4. Servis: `assign()`, `progress()`, `submit_answer()`, `finish()`.

**Qabul mezoni**
- [x] Bir xodimga bir kurs ikki marta tayinlanmaydi — IKKI qatlam:
      kod qo'riqchisi + `uq_course_assignment_active` qisman unique
      indeksi (test xom SQL bilan, servisni chetlab tekshiradi)
- [x] Holat **bazada** — test YANGI SESSIYADA o'qib tasdiqlaydi
      (restart taqlidi)
- [x] Urinish raqami saqlanadi — har urinish `course_results` da
      alohida qator, eskisi o'chirilmaydi

---

### S-34 · O'quv paneli — HR sayt tomoni (3.1)
**Oldin:** S-33 · **~6 soat**

**Ish**
1. Sahifa: kurs yaratish (nom, tavsif, kimga, majburiymi, muddat, o'tish chegarasi %).
2. Materiallar: bot orqali yuborilgan `file_id` biriktiriladi; matn va havola ham.
3. Savollar: qo'lda yoki `.docx` dan (mavjud `docx_parse.py`).

**Qabul mezoni**
- [x] Kurs yaratish → material → savol zanjiri ishlaydi (brauzerda
      to'liq sinaldi: kurs → material → savol → nashr → 9 xodimga
      tayinlash)
- [x] `.docx` dan savol import qilinadi (anketa ajratgichi bilan;
      kelgan savollar ochiq javobli)
- [x] O'tish chegarasi kursda saqlanadi (`pass_percent`, test bilan)

---

### S-35 · O'quv paneli — xodim tomoni (bot) (3.1)
**Oldin:** S-34 · **~6 soat**

**Ish**
1. Bot: «📚 Darsliklarim» → tayinlangan kurslar → ketma-ket material → test.
2. Material ko'rilgani qayd etiladi; hammasi ko'rilgach test ochiladi.
3. Test natijasi darhol: foiz, o'tdi/o'tmadi, qayta urinish.

**Qabul mezoni**
- [x] Bot restart bo'lsa ham xodim qolgan joyidan davom etadi
      (FSM umuman yo'q; test «restart taqlidi» bilan tekshiradi)
- [x] Test barcha material ko'rilmaguncha ochilmaydi (409)
- [x] O'tmasa qayta urinish beriladi (urinish soni `course_results`
      da alohida qator bo'lib yoziladi)

---

### S-36 · O'quv paneli — xodim tomoni (kabinet) (3.1)
**Oldin:** S-35 · **~5 soat**

**Ish**
1. Kabinetda ham xuddi shu oqim (video/hujjat ko'rish, test topshirish).
2. Bot va sayt **bitta holatni** o'qiydi — ikkita mustaqil progress bo'lmasin.

**Qabul mezoni**
- [x] Botda boshlab, saytda davom ettirish mumkin (test NAVBATMA-
      NAVBAT tekshiradi: bot → sayt → bot → sayt)
- [x] Ikkala joyda bir xil foiz — ro'yxat javoblari AYNAN teng
- [x] Xodim faqat o'ziga tayinlangan kursni ko'radi (begonaga 404)

---

### S-37 · O'quv paneli — HR hisoboti va cron (3.1)
**Oldin:** S-36 · **~5 soat**

**Ish**
1. Jadval: kim tugatgan / boshlamagan / muddatni o'tkazgan.
2. **Og'ir hisobot cron tick'da** tayyorlanadi (S-07), ro'yxat sahifasi faqat yig'ma raqamlarni oladi.
3. Muddat o'tayotgan kurs → `deadlines` (S-12).

**Qabul mezoni**
- [x] Ro'yxat sahifasi tez — S-34 dagi N+1 olib tashlandi, raqamlar
      `course_stats` dan BITTA so'rov bilan olinadi
- [x] Batafsil hisobot fon ishida (`course_report_tick`, 8:50)
- [x] **Kurs tugatmaslik pulga ta'sir qilmaydi** — test STRUKTURA
      darajasida qo'riqlaydi (ish haqi modullari kurs modellariga
      tegmasligi AST bilan tekshiriladi; qo'riqchi sinaldi)

---

### S-38 · O'quv paneli — yakuniy sinov va deploy (3.1)
**Oldin:** S-37 · **~4 soat**

**Ish**
1. Uchdan-uchgacha sinov: kurs yaratish → tayinlash → bot orqali o'tish → test → hisobot.
2. «Sozlanmagan modullar» ga «kurs materiali yuklanmagan» qatori.
3. Deploy + jonli tekshiruv.

**Qabul mezoni**
- [~] Jonli serverda bitta haqiqiy kurs oxirigacha o'tildi —
      DEPLOY qilindi va HR allaqachon o'z kursini yarata boshlagan
      («HR lik», 2026-08-22 12:20, qoralama). To'liq o'tish HR bilan
      qilinadi: sinov kursi yaratilsa u HR ro'yxatida ko'rinib,
      chalkashtirardi. Oqimning O'ZI `test_courses_end_to_end` da
      uchdan-uchgacha sinalgan.
- [x] Disk o'smagan — video/hujjat SERVERDA saqlanmaydi, faqat
      Telegram `file_id` (test bilan tekshiriladi)
- [x] Test: 17 ta tekshiruv (12+ so'ralgan)

---

### S-39 · Tashkiliy tuzilma — model va ierarxiya (3.16)
**Oldin:** S-20 · **~5 soat**

**Ish**
1. `positions.parent_position_id` qo'shiladi (hozir **yo'q** — tekshirilgan). `users.manager_id` allaqachon **bor**.
2. `job_descriptions`: position_id, maqsad, vazifalar (JSON), huquqlar, javobgarlik, talablar, **versiya**, `effective_from`.
3. `company_profile`: missiya, qadriyatlar, strategik maqsadlar.
4. ⚠️ **Yo'riqnoma UPDATE qilinmaydi** — yangi versiya qo'shiladi.

**Qabul mezoni**
- [x] Ierarxiya halqa hosil qilmaydi — qo'riqchi TZ so'raganidan
      kengroq: o'ziga bo'ysunish HAM, A→B→C→A uzun halqa HAM
      to'siladi (`org.assert_no_cycle`)
- [x] Yo'riqnoma tahriri yangi versiya yaratadi, eskisi qoladi —
      tahrirlash funksiyasi UMUMAN yozilmagan, bazada ham
      `(position_id, version)` unique
- [x] Test: versiya zanjiri (1→2→3) + «joriy versiya» kelajakdagi
      versiyani hisobga olmasligi

---

### S-40 · Tuzilma — sayt (sxema va yo'riqnoma tahriri) (3.16)
**Oldin:** S-39 · **~6 soat**

**Ish**
1. `GET /org-chart` — tugunlar va bog'lanishlar. **Rasm serverda yaratilmaydi** (Passenger).
2. Sxemani brauzer chizadi: CSS grid yoki qo'lda SVG (20–30 tugun, og'ir kutubxona olinmasin).
3. Lavozim ustiga bosilsa: kim ishlaydi, nechta o'rin, yo'riqnoma.
4. «Yo'riqnomasiz lavozimlar» va «rahbari belgilanmagan xodimlar» ro'yxati.

**Qabul mezoni**
- [x] Server faqat ma'lumot beradi — rasm YARATILMAYDI, test javob
      `application/json` ekanini tekshiradi
- [x] Mobil ko'rinish — «Mening o'rnim» sahifasi (`/me/place`):
      rahbarim → men → menga bo'ysunadiganlar; sxema esa ichma-ich
      `<ul>` bo'lgani uchun kichik ekranda o'zi ro'yxatga aylanadi
- [x] Bo'shliqlar ro'yxati ishlaydi (yo'riqnomasiz lavozimlar +
      rahbari belgilanmagan xodimlar)

---

### S-41 · «Mening o'rnim» — xodim tomoni (3.16)
**Oldin:** S-40 · **~5 soat**

**Ish**
1. Kabinet va botda «🏢 Mening o'rnim»: sxemadagi o'z o'rni · rahbari va bo'ysunuvchilari · yo'riqnomasi · kuzatiladigan ko'rsatkichlari (`Position.metrics` dan).
2. Yo'riqnoma ostida «✅ Tanishdim» → `acknowledgements` (S-20).

**Qabul mezoni**
- [x] Xodim faqat **o'z** lavozimi yo'riqnomasini ko'radi — begona
      lavozimda `description: null`, faqat `has_description` qoladi
      (S-40 da bu buzilgan edi: matn har kimga berilardi)
- [x] Tuzilma sxemasi hammaga ochiq (ish haqi va baho **yo'q**) —
      13 ta taqiqlangan kalit ichma-ich tekshiriladi; `gaps` esa
      faqat rahbarga (kadr rejalashtirish ma'lumoti). S-40 da butun
      endpoint yopilgandi — TZ ga zid edi, tuzatildi
- [x] Tanishuv versiyasi bilan yoziladi — S-20 ning umumiy
      `acknowledgements` jadvalida; yangi versiya eski tanishuvni
      bekor qiladi, eskisi tarix bo'lib qoladi

---

### S-42 · Yo'riqnoma tanishuvi — eslatma va HR paneli (3.16)
**Oldin:** S-41 · **~4 soat**

**Ish**
1. Cron: 3 kundan beri tanishmaganga eslatma. **Uch martadan keyin to'xtaydi** va HR ro'yxatiga tushadi.
2. HR paneli: kim tanishgan / tanishmagan / qaysi versiya bilan.
3. Yo'riqnoma yangilansa ro'yxat qaytadan ochiladi.

**Qabul mezoni**
- [x] Bot cheksiz eslatmaydi — 3 marta, har 3 kunda bir
      (`MAX_ESLATMA`/`ESLATMA_KUNI`); undan keyin bot jim, band HR
      ro'yxatiga tushadi. Chegarani 99 ga ko'tarib sinaldi — test
      yiqildi, ya'ni chegara haqiqatan ishlaydi
- [x] Yangi versiya eski tanishuvni bekor qiladi — sanoq ham
      noldan boshlanadi, ya'ni yangi matn uchun qayta eslatiladi;
      eski versiya uchun eslatma to'xtaydi
- [x] «Tanishmaganlar» ro'yxati aniq — `/acks/instructions/overview`,
      `exhausted` (bot jim bo'lganlar) tepada

---

### S-43 · Kompaniya profili va AI javobi (3.16)
**Oldin:** S-41 · **~5 soat**

**Ish**
1. Botda «🏢 Kompaniya» tugmasi: missiya, qadriyatlar, maqsadlar, tuzilma.
2. `company_profile` va tuzilma ma'lumoti mavjud **bilim bazasiga `verified`** holatida kiritiladi.
3. ⚠️ **AI taxmin qilmasin:** bilim bazasida yo'q bo'lsa javob «bu ma'lumot kiritilmagan» va savol `unknown` sifatida qayd etiladi.
4. Ish haqi, baho, shaxsiy ma'lumot bu javoblarga **hech qachon** kirmaydi.

**Qabul mezoni**
- [x] «Missiyamiz nima» savoliga aniq javob — 6 ta tabiiy aytilish
      mos keladi (ball 0.33-1.00), begona savol 0.00
- [x] Bilim bazasida yo'q savol → «kiritilmagan» + `unknown` qaydi;
      savol baribir HR ga ham boradi (qayd odam o'rnini bosmaydi)
- [x] Maxfiy ma'lumot javobga tushmaydi — uch qatlam:
      `audience="hr"` (tashqi chatbotga ketmaydi), tuzilmada xodim
      ismlari yo'q, ish haqi/baho kalitlari ichma-ich tekshiriladi

---

### S-44 · `managed_by_roles` ziddiyatini yopish (3.16)
**Oldin:** S-39 · **~5 soat** · ⚠️ **Mavjud mantiqqa tegadi**

**Ish**
1. Hozir «kim norma bera oladi» — `Position.managed_by_roles`, «kim kimga bo'ysunadi» — hech qayerda. **Ikkita manba bo'lmasin.**
2. Tasdiqlash va norma huquqi **ierarxiyadan** hisoblansin; `managed_by_roles` faqat rol darajasidagi istisno uchun qolsin.
3. Ariza zanjiri (`pending → manager_ok → hr_ok`) endi **aniq odamga** (bevosita rahbarga) boradi.

**Qabul mezoni**
- [x] `can_manage_norms` ierarxiyani biladi — endi ZANJIR bo'ylab
      (rahbarimning rahbari ham); qoida `api/services/hierarchy.py`
      da, uch nusxa o'rniga yagona manba
- [x] Ariza aniq rahbarga boradi — xabar bevosita rahbarga, qaror
      huquqi esa butun zanjirda (rahbar ta'tilda bo'lsa muzlamasin)
- [x] Eski xatti-harakat buzilmagan — eski mantiqning aynan nusxasi
      etalon sifatida testda, 900 kombinatsiya solishtirildi.
      Yagona farq: HR bevosita rahbar bo'lgan holat (ataylab
      tuzatildi). Yo'l-yo'lakay ruxsat oshib ketish xavfi topildi
      va yopildi (`MANAGING_ROLES`)

---

### S-45 · Onboarding — model va shablon (3.2)
**Oldin:** S-38 · **~5 soat**

**Ish**
1. `onboarding_templates`, `onboarding_steps` (nomi, mas'ul, muddat = +N kun, turi), `onboarding_plans`, `onboarding_progress`.
2. Qadam turlari: oddiy vazifa · hujjat (3.4) · kurs (3.1) · instruktaj (3.6) · uchrashuv.
3. Shablon lavozim yoki rol uchun.

**Qabul mezoni**
- [ ] Shablondan reja yaratiladi, qadamlar nusxalanadi
- [ ] Qadam turi bo'yicha bog'lanish (kurs tayinlanadi, hujjat kutiladi)
- [ ] Test: shablon → reja → progress

---

### S-46 · Onboarding — vazifalarga ulanish (3.2)
**Oldin:** S-45 · **~5 soat**

**Ish**
1. Har qadam `TaskModel` yozuvini yaratadi — bildirishnoma, muddat va «bajardim» tugmasi tayyor keladi.
2. ⚠️ **Vazifa statistikasini buzmasin:** alohida `source` belgisi bilan va **kunlik digestdagi ✅ ustuniga kirmasin**.

**Qabul mezoni**
- [ ] Qadam vazifa sifatida ko'rinadi va bajariladi
- [ ] Kunlik digestda vazifa foizi **o'zgarmagan** (test bilan isbot)
- [ ] Qadam bajarilsa progress yangilanadi

---

### S-47 · Onboarding — HR ekrani va yakunlash (3.2)
**Oldin:** S-46 · **~5 soat**

**Ish**
1. HR ekrani: hozir onboardingda nechta xodim, kimda qaysi qadam kechikkan.
2. Xodim kabinetida «📋 Birinchi kunlarim» — chekbox ro'yxati.
3. Barcha qadam bajarilsa reja `tugatildi` → sinov baholashi (3.8) ochiladi.
4. Offer qabul qilinganda reja **avtomatik** ochiladi (S-16 dagi bayroq ulanadi).

**Qabul mezoni**
- [ ] Kechikkan qadam ajratib ko'rsatiladi
- [ ] Reja avtomatik ochiladi (offerdan)
- [ ] Yakunlanganda keyingi bosqich ochiladi

---

### S-48 · Instruktaj jurnali (3.6)
**Oldin:** S-38, S-20 · **~5 soat**

**Ish**
1. `safety_briefings` (turi, sana, o'tkazuvchi, material_id) va `safety_briefing_signatures` (user_id, briefing_id, tanishgan_vaqt) — yoki `acknowledgements` (S-20) ishlatiladi.
2. Turlari: kirish · dastlabki · takroriy · rejadan tashqari · maqsadli.
3. Material **o'quv panelida** saqlanadi (3.1) — alohida mexanizm qurilmaydi.
4. Xodimga botda matn/video + «Tanishdim» tugmasi; vaqt yoziladi.

**Qabul mezoni**
- [ ] Instruktaj → qatnashchilar → tanishuv qaydi zanjiri
- [ ] Takroriy instruktaj muddati `deadlines` ga tushadi
- [ ] Qog'oz jurnal o'rnini bosmasligi hujjatda yozilgan

---

### S-49 · Instruktaj — hisobot va muddat (3.6)
**Oldin:** S-48 · **~4 soat**

**Ish**
1. Hisobot: kim tanishgan, kim yo'q, muddati o'tganlar.
2. Har 6 oyda takroriy instruktaj eslatmasi.
3. Kadr auditi (3.30) uchun so'rov tayyorlanadi.

**Qabul mezoni**
- [ ] Muddati o'tgan instruktaj ro'yxati
- [ ] Eslatma takrorlanmaydi
- [ ] Yangi xodimga kirish instruktaji onboardingdan tushadi

---

### S-50 · Buyruqlar reyestri — model va raqamlash (3.21)
**Oldin:** S-14 · **~5 soat**

**Ish**
1. `orders`: raqam (unique), turi, user_id, sana, parametrlar (JSON), fayl_id, holati, yaratgan_id.
2. Turlari: ishga qabul · o'tkazish · ta'til · bo'shatish · rag'batlantirish · intizomiy jazo · ish haqini o'zgartirish.
3. ⚠️ **Raqam tizim tomonidan beriladi va takrorlanmaydi.** Parallel so'rovda ham (unique + retry).
4. **Buyruq yaratilgach tahrirlanmaydi** — bekor qilinadi va yangisi chiqariladi.

**Qabul mezoni**
- [ ] Raqam takrorlanmaydi (parallel test bilan)
- [ ] Tahrirlash endpointi **yo'q**
- [ ] Bekor qilish yangi yozuv yaratadi

---

### S-51 · Buyruqlar — hujjat va tanishtirish (3.21)
**Oldin:** S-50, S-20 · **~5 soat**

**Ish**
1. Shablondan `.docx` (S-14 mexanizmi), `employee_documents` ga yoziladi.
2. Xodim «Tanishdim» bilan tanishtiriladi (`acknowledgements`).
3. Buyruq turiga qarab shablon tanlanadi.

**Qabul mezoni**
- [ ] Har tur uchun shablon bor yoki «shablon yuklanmagan» deb ko'rsatiladi
- [ ] Tanishuv qaydi buyruq versiyasi bilan
- [ ] Xodim faqat **o'ziga tegishli** buyruqni ko'radi, ROP **ko'rmaydi**

---

### S-52 · Buyruqlar — mavjud oqimlarga ulash (3.21)
**Oldin:** S-51 · **~4 soat**

**Ish**
1. Ta'til arizasi tasdiqlanganda buyruq **taklif** qilinadi (avtomatik yaratilmaydi — HR bosadi).
2. Ishga qabul (offer), bo'shatish (3.7), stavka o'zgarishi (3.25) uchun ham.

**Qabul mezoni**
- [ ] Buyruq avtomatik **yaratilmaydi**, faqat taklif qilinadi
- [ ] Bog'langan ariza/hodisa buyruqda ko'rinadi

---

### S-53 · Intizomiy jazo tartibi — model va zanjir (3.22)
**Oldin:** S-50 · **~5 soat** · 🔴 **HUQUQIY**

**Ish**
1. `disciplinary_cases`: user_id, buzilish tavsifi, sana, tushuntirish so'ralgan sana, izoh matni, qaror, buyruq_id, holati.
2. **Qat'iy ketma-ketlik:** buzilish qayd → yozma tushuntirish so'raladi → xodim izoh beradi (yoki bermaydi — bu ham qayd etiladi) → qaror → buyruq → tanishtirish.
3. Tushuntirish so'ralmagan bo'lsa **buyruq bosqichiga o'tkazmaydi**.

**Qabul mezoni**
- [ ] Bosqichni sakrab o'tib bo'lmaydi (400 xatosi)
- [ ] Tushuntirish bermaslik ham qayd etiladi
- [ ] Tizim jazo turini **o'zi tanlamaydi**

---

### S-54 · Intizomiy jazo — muddatlar va ogohlantirish (3.22)
**Oldin:** S-53 · **~4 soat**

**Ish**
1. Har qadamning muddati kuzatiladi, o'tkazib yuborilganda ogohlantirish.
2. Xodim faqat **o'z** ishini ko'radi; ROP **ko'rmaydi**.
3. Bot orqali xodimga tushuntirish so'rovi va uning javobi.

**Qabul mezoni**
- [ ] Muddat o'tsa HR ogohlantiriladi
- [ ] Xodim botdan izoh yubora oladi
- [ ] Ko'rinish matritsasi test bilan tekshirilgan

---

**✅ C BLOK YAKUNI:** xodim ishga kirgandan boshlab o'qitiladi, tuzilmadagi o'rnini biladi, hujjatlari rasmiylashtiriladi va intizomiy tartib qonuniy ketma-ketlikda yuritiladi.

---

# D BLOK — TO'LDIRUVCHI MODULLAR

> TZ 3-bosqich: 37–52 dasturchi-kuni → **30 seans**.
> Bu blokdagi ba'zi ish **allaqachon qilingan** — quyida aniq ko'rsatilgan.

---

### S-55 · Oylik reja — mavjudini inventarizatsiya qilish (3.18)
**Oldin:** S-54 · **~3 soat**

⚠️ **DIQQAT: 3.18 ning katta qismi ALLAQACHON QURILGAN.** TZ yozilgan paytda yo'q edi, endi bor. Qaytadan yozmang.

**Mavjud (tekshiring, keyin yozing):**
- `funnel_month.target_contracts` + `assumptions` — oylik maqsad va farazlar
- `api/services/target_calc.py` — teskari kalkulyator + sezgirlik
- `api/services/target_split.py` — xodimlarga tarqatish (ish kuniga proporsional)
- `api/services/target_track.py` — reja/fakt/prognoz + kunlik digest qatori
- Sayt: `/funnel` sahifasida 4 ta karta
- Kogorta mantig'i to'g'ri qo'yilgan

**Yetishmaydi (shu blokda qilinadi):** S-56, S-57, S-58.

**Qabul mezoni**
- [ ] Mavjud va yetishmaydigan qism jadval qilib yozilgan
- [ ] `VORONKA_TARIFLAR.md` bilan ziddiyat yo'qligi tekshirilgan

---

### S-56 · Oylik reja — kam namunada qo'lda konversiya (3.18)
**Oldin:** S-55 · **~5 soat**

**Ish**
1. TZ talabi: konversiya 0 bo'lsa **yoki kuzatuv soni 10 tadan kam** bo'lsa — avtomatik hisob o'rniga rahbardan qo'lda so'raladi («odatda nechta tashrifdan 1 ta shartnoma chiqadi?»).
2. Hozir 0 rad etiladi va zaxira faraz olinadi (`target_calc._resolve`), lekin **so'ralmaydi** — shuni qo'shing.
3. Kiritilgan qiymat sozlamada saqlanadi va **haqiqiy ma'lumot yig'ilganda avtomatik almashadi**.
4. TZ: konversiya **oxirgi 3 oy** o'rtachasidan (hozir 6 oy) — moslashtiring yoki farqni hujjatlang.

**Qabul mezoni**
- [ ] Kam namunada panel qo'lda kiritishni **so'raydi**
- [ ] Kiritilgan qiymat «qo'lda» deb belgilanadi
- [ ] Yetarli ma'lumot yig'ilganda o'lchanganga o'tadi

---

### S-57 · Oylik reja — reja versiyalari va taqsimlash usuli (3.18)
**Oldin:** S-56 · **~5 soat**

**Ish**
1. `monthly_targets` + `target_assignments` (TZ 6-qism) — **reja o'zgarsa eski versiya saqlanadi** (kim, qachon, nimadan nimaga).
2. Taqsimlash ikki usul: **teng** (standart) yoki natijaga qarab (o'tgan 3 oy). Hozir faqat ish kuniga proporsional.
3. Rahbar qo'lda tuzatsin; yig'indi farq qilsa **ogohlantiriladi, bloklanmaydi**.

**Qabul mezoni**
- [ ] Reja tarixi saqlanadi (oy oxirida «reja aslida shuncha edi» bahsi chiqmaydi)
- [ ] Ikkala taqsimlash usuli ishlaydi
- [ ] Qo'lda tuzatish + ogohlantirish

---

### S-58 · Oylik reja — xodim bildirishnomalari (3.18)
**Oldin:** S-57 · **~5 soat**

**Ish**
1. TZ jadvalidagi xabarlar: reja tayinlanganda · har bosqich bajarilganda · haftalik (dushanba) · oy o'rtasida orqada qolsa · reja bajarilganda · rejadan oshsa.
2. 🔴 **Qat'iy qoida:** xabar faqat xodimning **O'Z** raqamlari haqida. Boshqa xodim, reyting, «falonchi sizdan oldinda» — **HECH QACHON**.
3. Ohang: ayblov emas, hisob («kuniga 2 tashrif kerak» — «rejani bajarmayapsiz» emas).
4. Kuniga **bitta** reja xabari; bir kunga to'g'ri kelsa birlashtiriladi.
5. Barcha xabar cron/outbox orqali — webhook ichidan **yuborilmaydi**.

**Qabul mezoni**
- [ ] Xabar matnida boshqa xodim ismi yo'q (test bilan)
- [ ] Kuniga bittadan ko'p yuborilmaydi
- [ ] Xabar matnlari TZ namunasiga mos

---

### S-59 · Yillik ta'til jadvali — model va kiritish (3.10)
**Oldin:** S-09 · **~5 soat**

**Ish**
1. `vacation_schedule`: user_id, yil, boshlanish, tugash, holat (taklif/tasdiqlangan/o'zgartirilgan), tasdiqlagan_hr_id.
2. Xodim kabinetdan xohlagan davrni belgilaydi, HR tasdiqlaydi.
3. Ish kunlari **bayramlarni** (S-09) hisobga oladi.

**Qabul mezoni**
- [ ] Xodim o'z davrini kiritadi, HR tasdiqlaydi
- [ ] Bayram ta'til kunini yemaydi
- [ ] Xodim boshqasining jadvalini ko'rmaydi (faqat HR to'liq ko'radi)

---

### S-60 · Ta'til jadvali — to'qnashuv nazorati va ariza bog'lanishi (3.10)
**Oldin:** S-59 · **~5 soat**

**Ish**
1. Bir bo'limdan bir vaqtda bir nechta xodim ta'tilga chiqsa **ogohlantiradi** (bloklamaydi — qaror HR da).
2. Jadvalda turgan davr uchun ariza berilsa tizim taniydi va tasdiqlash yengillashadi.
3. Jadvaldan tashqari ariza HR uchun alohida belgilanadi.

**Qabul mezoni**
- [ ] Ogohlantirish chiqadi, lekin saqlash bloklanmaydi
- [ ] Jadvaldagi ariza «jadval bo'yicha» deb belgilanadi
- [ ] Test: to'qnashuv, jadval ichi/tashqarisi

---

### S-61 · Ta'til qoldig'i va yillik hisob (3.10)
**Oldin:** S-60 · **~4 soat**

**Ish**
1. Ta'til qoldig'i: mavjud `leave_balance` (arizalar modulida bor) bilan bog'lash — **ikkinchi hisob yo'li yaratilmasin**.
2. Kadr metrikalariga (3.17) «ta'til qoldig'i» ko'rsatkichi.

**Qabul mezoni**
- [ ] Qoldiq bitta joydan hisoblanadi
- [ ] Jadval va ariza bir xil raqamni ko'rsatadi

---

### S-62 · Kadr metrikalari — hisob yadrosi (3.17)
**Oldin:** S-31 · **~6 soat**

**Ish**
1. `users` ga `termination_date`, `termination_reason` (hozir **yo'q** — tekshirilgan).
2. Ko'rsatkichlar: kadrlar oqimi · o'rtacha staj · sinovdan o'tish % · birinchi 3 oyda ketish · onboarding tugatish % · majburiy kurs tugatish % · kechikish tendensiyasi · ta'til qoldig'i.
3. ⚠️ **Kadrlar oqimi ta'rifi (TZ qat'iy qarori):** sinovdan o'tmaganlar **kiradi**, lekin doim **ikkita ajratma** ko'rsatiladi: sinov davrida ketganlar (tanlov muammosi) va sinovdan keyin ketganlar (ushlab qolish muammosi).
4. O'z xohishi bilan / bo'shatilgan — alohida. Ta'tildagi xodim «ketgan» sanalmaydi.
5. 🔴 **Foiz bilan birga ABSOLYUT SON** («2 kishi / 12,5%») — 16 xodimda foiz chalg'itadi.

**Qabul mezoni**
- [ ] Har ko'rsatkich formulasi hujjatda yozilgan
- [ ] Oqim ikkita ajratma bilan ko'rsatiladi
- [ ] Absolyut son doim foiz yonida
- [ ] Test: har formula uchun fixture

---

### S-63 · Kadr metrikalari — oylik snapshot (3.17)
**Oldin:** S-62 · **~5 soat**

**Ish**
1. `hr_metrics_monthly`: yil, oy, bo'lim (NULL = umumiy), ko'rsatkich nomi, qiymat.
2. Oy oxirida cron yozadi — **har safar qayta hisoblanmaydi** (Passenger + o'tgan oy raqami o'zgarmasligi).
3. Ko'rinish: boss/HR to'liq, ROP faqat o'z jamoasi, xodim **ko'rmaydi**.

**Qabul mezoni**
- [ ] Snapshot oyiga bir marta yoziladi, takrorlanmaydi
- [ ] O'tgan oy raqami keyin o'zgarmaydi
- [ ] Ko'rinish matritsasi testda

---

### S-64 · Kadr metrikalari — panel (3.17)
**Oldin:** S-63 · **~4 soat**

**Ish**
1. Sahifa: ko'rsatkichlar + oylar dinamikasi + bo'lim kesimi.
2. Kichik jamoa ogohlantirishi matn sifatida ko'rsatiladi.

**Qabul mezoni**
- [ ] Sahifa snapshotdan o'qiydi (og'ir so'rov yo'q)
- [ ] Ma'lumot yetarli bo'lmasa «hisoblanmadi» deydi

---

### S-65 · Tungi navbatchilik — model va QR (3.19)
**Oldin:** S-31 · **~5 soat**

**Ish**
1. `patrol_points` (nomi, kodi, koordinatalar, faolmi), `patrol_checks` (user_id, so'ralgan vaqt, javob vaqti, nuqta_id, holati, gps, face natijasi).
2. QR matni oddiy: `NB-POST-01`, **ochiq havola emas**; kod **har oy almashtiriladi**.
3. QR chop etish sahifasi (oddiy HTML, brauzer chizadi).

**Qabul mezoni**
- [ ] Nuqta qo'shish/o'chirish ishlaydi
- [ ] Kod har oy almashadigan mexanizm bor
- [ ] QR chop etiladigan sahifa mavjud

---

### S-66 · Navbatchilik — tasodifiy tekshiruv generatori (3.19)
**Oldin:** S-65 · **~5 soat**

**Ish**
1. Tunda 3–4 marta **tasodifiy** vaqtda so'rov (masalan 23:40, 01:15, 03:50, 05:20). Vaqt oldindan ma'lum emas.
2. Qaysi nuqta so'ralishi ham tasodifiy.
3. Kunlik reja oldindan yaratiladi (tunning boshida), lekin qorovulga **ko'rsatilmaydi**.

**Qabul mezoni**
- [ ] Vaqtlar har kuni boshqacha
- [ ] Reja bazada, cron faqat vaqti kelganini yuboradi
- [ ] Qorovul kelgusi tekshiruv vaqtini API orqali ham ko'ra olmaydi (test bilan)

---

### S-67 · Navbatchilik — javob, GPS/Face va eskalatsiya (3.19)
**Oldin:** S-66 · **~6 soat**

**Ish**
1. QR skanerlanganda: GPS + Face ID (mavjud davomat mexanizmi, tiriklik bilan).
2. 10 daqiqada javob yo'q → takroriy so'rov. 20 daqiqada ham yo'q → prorab va direktorga xabar.
3. ⚠️ **Avtomatik jazo yo'q** — tizim faqat qayd etadi.
4. Javob kelmagani «buzilish» emas, «tekshirish kerak» deb belgilanadi.

**Qabul mezoni**
- [ ] Eskalatsiya zanjiri ishlaydi (10/20 daqiqa)
- [ ] Jarima/ushlanma **avtomatik yozilmaydi**
- [ ] Test: o'z vaqtida / kechikdi / o'tkazildi

---

### S-68 · Navbatchilik — ertalabki hisobot va ochiqlik (3.19)
**Oldin:** S-67 · **~4 soat**

**Ish**
1. Ertalab bitta hisobot: nechta tekshiruvdan nechtasi bajarildi.
2. 🔴 **Ochiqlik sharti:** tunda tekshiruv o'tkazilishi lavozim yo'riqnomasida yozilgan va xodim **«Tanishdim»** bilan tanishtirilgan bo'lishi shart (S-41). Tanishtirilmagan xodimga tekshiruv **yuborilmasin**.
3. Cheklovlar hujjatda yozilsin (mast holat aniqlanmaydi, internet uzilishi va h.k.).

**Qabul mezoni**
- [ ] Tanishtirilmagan xodimga tekshiruv ketmaydi
- [ ] Ertalabki hisobot bitta xabar
- [ ] Cheklovlar hujjatlashtirilgan

---

### S-69 · Sinov muddati baholashi (3.8)
**Oldin:** S-47 · **~5 soat**

**Ish**
1. `evaluations`: user_id, turi (sinov/davriy), davr, baholovchi_id, mezonlar (JSON), umumiy baho, xulosa, tavsiya, sana.
2. Onboarding tugagach yoki sinovga 7 kun qolganda rahbarga forma boradi.
3. Tavsiya: davom ettirish / muddatni uzaytirish / ajrashish.

**Qabul mezoni**
- [ ] Forma o'z vaqtida boradi
- [ ] Natija HR panelida va xodim faylida
- [ ] 🔴 **Pulga avtomatik ta'sir qilmaydi**

---

### S-70 · Davriy baholash va o'z-o'zini baholash (3.8)
**Oldin:** S-69 · **~5 soat**

**Ish**
1. Chorakda bir marta: rahbar baholaydi, xodim o'zini baholaydi, ikkisi **solishtiriladi**.
2. Xodim faqat **o'z** bahosini ko'radi.

**Qabul mezoni**
- [ ] Ikki baho yonma-yon ko'rinadi
- [ ] Xodim boshqasinikini ko'rmaydi
- [ ] Baho pulga ta'sir qilmasligi testda

---

### S-71 · Offboarding — cheklist yadrosi (3.7)
**Oldin:** S-47, S-19 · **~5 soat**

**Ish**
1. `resignation` arizasi tasdiqlanganda **avtomatik cheklist** ochiladi (onboarding teskarisi).
2. Qadamlar: ishni topshirish dalolatnomasi · mol-mulkni qaytarish (3.11 dan **avtomatik ro'yxat**) · kirish huquqlarini yopish · chiqish suhbati · yakuniy hisob-kitob.

**Qabul mezoni**
- [ ] Ariza tasdiqlanishi bilan cheklist ochiladi
- [ ] Qaytariladigan mol-mulk ro'yxati avtomatik
- [ ] Har qadam mas'ulga vazifa bo'lib boradi

---

### S-72 · Offboarding — kirish huquqlari va bilim (3.7)
**Oldin:** S-71 · **~5 soat**

**Ish**
1. 🔴 **Kirish huquqlarini yopish bajarilmaguncha ariza yakunlanmaydi** (TZ: eng katta xavf — odam ketadi, Telegram guruh admini va CRM kirishi qoladi).
2. Cheklist: tizim · Telegram guruhlar · CRM · pochta.
3. Chiqish suhbati javoblari **`knowledge_entries`** ga tushadi (anketa mexanizmi).

**Qabul mezoni**
- [ ] Huquqlar yopilmaguncha yakunlab bo'lmaydi (400)
- [ ] Chiqish suhbati javoblari bilim bazasiga tushadi
- [ ] Xodim `is_active=False` bo'lgach ham tarix qoladi

---

### S-73 · Anonim pulse-so'rovnoma (3.13)
**Oldin:** S-38 · **~5 soat**

**Ish**
1. `surveys`, `survey_questions`, `survey_responses`, `survey_assignments`. Anketa mexanizmi qayta ishlatiladi — faqat **anonim rejim** qo'shiladi.
2. 🔴 **Anonimlik:** `user_id` bazada saqlanadi (takroriy javobni tekshirish uchun), lekin **API javobida hech qachon qaytarilmaydi**.
3. Natija **faqat yig'ma**; bo'limda **4 dan kam** xodim bo'lsa **umuman ko'rsatilmaydi**.

**Qabul mezoni**
- [ ] API javobida `user_id` yo'q (test bilan isbot)
- [ ] 4 dan kam bo'lgan bo'lim kesimida natija ko'rsatilmaydi
- [ ] Natija pulga ta'sir qilmaydi va rahbarni baholamaydi

---

### S-74 · Tavsiya dasturi (referral) (3.15)
**Oldin:** S-16 · **~5 soat**

**Ish**
1. `referrals`: tavsiya_qilgan_id, nomzod_ismi, telefon, lavozim, holat, bonus_holati, sana. `users.referred_by` (hozir **yo'q**).
2. Bot: «Tanishimni tavsiya qilaman».
3. ⚠️ **Bonus avtomatik hisoblanmaydi:** sinov muddati muvaffaqiyatli tugaganda HR ga eslatma → HR `PayrollAdjustment` orqali **qo'lda** kiritadi.

**Qabul mezoni**
- [ ] Bonus avtomatik yozilmaydi
- [ ] Nomzod ishga olinsa `referred_by` bog'lanadi
- [ ] Tavsiya orqali kelganlar qancha ishlaganini solishtirish mumkin

---

### S-75 · Lavozim o'zgarishi (rotatsiya) (3.27)
**Oldin:** S-52, S-19, S-41 · **~5 soat**

**Ish**
1. Bitta joydan boshlanadigan cheklist: buyruq (3.21) · yangi yo'riqnoma + «Tanishdim» (3.16) · yangi norma va metrikalar · yangi rahbar · mol-mulkni qayta biriktirish (3.11) · yangi kurslar (3.1) · ish haqi o'zgarishi (3.25).
2. **Barcha qadam bajarilmaguncha o'tkazish yakunlanmaydi.**
3. Eski lavozim ma'lumoti **o'chirilmaydi** — lavozim tarixi ko'rinadi.

**Qabul mezoni**
- [ ] Cheklist to'liq bajarilmaguncha yakunlanmaydi
- [ ] Lavozim tarixi xodim kartochkasida
- [ ] Norma va metrikalar yangi lavozimga o'tadi

---

### S-76 · HR kalendari (3.23)
**Oldin:** S-13, S-59, S-69, S-22 · **~5 soat**

**Ish**
1. Bitta ekran: shu hafta va shu oy — sinov muddati tugaydiganlar · ta'tilga chiqish/qaytish · instruktaj · tibbiy ko'rik · tug'ilgan kun va yubiley · ko'rilmagan arizalar · muddati o'tgan vazifalar.
2. **Yangi ma'lumot yaratmaydi** — mavjud modullardan yig'adi.

**Qabul mezoni**
- [ ] Yangi jadval yaratilmagan
- [ ] Har element manba modulga havola qiladi
- [ ] Sahifa tez (og'ir so'rov yo'q yoki keshlangan)

---

### S-77 · Kadr auditi cheklisti (3.30)
**Oldin:** S-11, S-49, S-42, S-27 · **~5 soat**

**Ish**
1. Chorakda bir marta avtomatik tekshiruv: shartnoma bormi va arxivga yuklanganmi · yo'riqnoma bormi va tanishtirilganmi · TX instruktaji muddati · tibbiy ko'rik · YMMT ro'yxati · ta'til qoldig'i.
2. Natija: bitta ro'yxat — qaysi xodimda qaysi hujjat yetishmayapti. Har band tuzatilgach belgilanadi.

**Qabul mezoni**
- [ ] Yangi ma'lumot talab qilmaydi
- [ ] Har band manba modulga havola
- [ ] Chorakda avtomatik ishga tushadi

---

### S-78 · HR jarayonlari reglamenti (3.31)
**Oldin:** S-77 · **~4 soat**

**Ish**
1. Har jarayon uchun qisqa reglament: bosqichlar, mas'ullar, muddatlar (tizimda saqlanadi, HR ochib ko'radi).
2. ⚠️ **Muddatlar tizimga bog'lansin:** reglamentdagi muddat (masalan «ariza 2 ish kunida ko'riladi») `deadlines` (S-12) mexanizmi bilan ishlasin — shunchaki matn bo'lib qolmasin.

**Qabul mezoni**
- [ ] Reglament tizimda saqlanadi va tahrirlanadi
- [ ] Kamida bitta muddat amalda eslatma beradi
- [ ] Yangi HR shu hujjatdan ishlay oladi

---

### S-79 · Qurilish lavozimlari uchun metrikalar (2.8)
**Oldin:** S-31 · **~4 soat**

**Ish**
1. Prorab, kran mashinisti, usta lavozimlarida hozir `suhbat/tashrif` turibdi — **bu ish turiga mos emas**.
2. Yangi metrikalar (TZ taklifi): ob'ektda bajarilgan ish hajmi · kunlik ish jurnali to'ldirilganmi · TX buzilishi soni (0 maqsad) · materialga buyurtma o'z vaqtida.
3. Kran mashinisti/usta: ish soati (davomatdan) · nosozlik haqida xabar · TX instruktajidan o'tganlik.
4. 🔴 **Metrikasiz lavozimga `metrics = []` (ataylab bo'sh), `None` EMAS** — aks holda eski standart `suhbat+tashrif` qaytadi.

**Qabul mezoni**
- [ ] Qurilish lavozimlarida sotuv metrikalari **yo'q**
- [ ] `metrics = []` qo'yilgan (`None` emas) — test bilan
- [ ] Bu lavozimlarda norma/KPI ekranlari mos ko'rinadi

---

### S-80 · Video-replay hujumiga qarshi tasodifiy harakat (2.9)
**Oldin:** S-31 · **~5 soat**

**Ish**
1. Hozirgi tiriklik: pirpiratish/og'iz ochish — **oldindan yozib qo'yilgan video bilan aldash mumkin**.
2. Qo'shimcha: **tasodifiy harakat so'rash** (chapga qara / o'ngga qara / boshni ko'tar) — oldindan yozib bo'lmaydi.
3. Mavjud 3 qatlamli himoyani buzmang — ustiga qo'shing.

**Qabul mezoni**
- [ ] So'raladigan harakat har safar tasodifiy
- [ ] Mavjud tiriklik testlari yashil qoladi
- [ ] Muvaffaqiyatsiz urinish sababi bilan yoziladi (loyiha intizomi)

---

### S-81 · Webhook mustaqil tasdig'i (2.5)
**Oldin:** S-31 · **~5 soat** · 🔴 **XAVFSIZLIK — pulga ta'sir qiladi**

**Ish**
1. Hozir ishonchli IP yagona to'siq. IP ni bilgan har kim soxta lid yubora oladi → soxta tashrif → soxta KPI → **real pul**.
2. TZ yechimi: webhook voqeasi **darhol kreditlanmasin**. Voqea qayd etiladi, lekin tashrif/shartnoma sifatida hisobga olinishi uchun `GET /lead/{id}` bilan **mustaqil tasdiqlansin**.
3. Tasdiqlash — byudjetli (mavjud `lead_source` boyituvchisi naqshi), CRM limitini buzmasin.
4. Tasdiqlanmagan voqea statistikaga kirmaydi va «tasdiq kutilmoqda» deb belgilanadi.

**Qabul mezoni**
- [ ] Soxta webhook KPI ga ta'sir qilmaydi (test: CRM da yo'q lid)
- [ ] Tasdiqlash CRM limitini buzmaydi
- [ ] Kechikish o'lchangan va hujjatlashtirilgan

---

### S-82 · D blok — ko'rinish va xavfsizlik auditi
**Oldin:** S-55…S-81 · **~5 soat**

**Ish**
1. TZ 4-qism jadvalidagi **har qator** uchun avtomatik test (14 modul × 3 rol).
2. Bildirishnoma matnlarida boshqa xodim ismi yo'qligini tekshiradigan test.
3. Eksport va menyu filtri.

**Qabul mezoni**
- [ ] TZ 4-qism jadvali to'liq test bilan qoplangan
- [ ] Bildirishnoma testi bor
- [ ] Bitta ham 403 qolmagan (begona so'rovga 404)

---

### S-83 · Yakuniy integratsiya sinovi
**Oldin:** S-82 · **~6 soat**

**Ish**
1. Uchdan-uchgacha ssenariy: **offer → xodim → onboarding → kurs → instruktaj → yo'riqnoma tanishuvi → sinov baholashi → rotatsiya → offboarding**.
2. Har bosqichda hujjat, buyruq va tanishuv qaydi tekshiriladi.
3. Disk, cron logi, xotira.

**Qabul mezoni**
- [ ] Butun zanjir bitta xodimda oxirigacha o'tdi
- [ ] Har qadamda kerakli hujjat yaratildi
- [ ] Cron logida xato yo'q, disk o'sishi nazoratda

---

### S-84 · Hujjatlashtirish va topshirish
**Oldin:** S-83 · **~5 soat**

**Ish**
1. `YANGI_MODULLAR_HOLAT.md`: har modul — tayyor/qisman/yo'q, qayerda, qanday sozlanadi.
2. «Sozlanmagan modullar» blokini yakuniy to'ldirish (har yangi modul uchun qator).
3. HR uchun qisqa qo'llanma: qaysi ekrandan nima qilinadi.
4. Xotira fayllariga (agent xotirasi) asosiy tuzoqlarni yozish.

**Qabul mezoni**
- [ ] Har modulning holati hujjatda
- [ ] HR qo'llanmasi bor
- [ ] «Sozlanmagan modullar» to'liq ro'yxat beradi

---

# YAKUNIY JADVAL

| Blok | Bosqichlar | Seans | TZ kuni | Natija |
|---|---|---|---|---|
| **A — Poydevor** | S-01…S-09 | 9 | 10–15 | Huquqiy xavf yopildi, ko'rinish markazlashdi, sayt qotmaydi |
| **B — Kichik modullar** | S-10…S-31 | 22 | 23–34 | HR qog'oz ishi tizimga ko'chdi |
| **C — Asosiy modullar** | S-32…S-54 | 23 | 28–39 | O'quv, onboarding, tuzilma, buyruqlar |
| **D — To'ldiruvchi** | S-55…S-84 | 30 | 37–52 | Metrikalar, baholash, offboarding, navbatchilik |
| **JAMI** | | **84 seans** | 98–140 kun | |

**Har seans 5–6 soat** → taxminan **450–500 soat**.

---

# AGENT UCHUN ESLATMA

1. **Bosqichni bo'lish mumkin, birlashtirish — yo'q.** 5–6 soatdan oshsa ikkiga bo'ling va raqamiga `a`/`b` qo'shing.
2. **Har seans oxirida deploy.** «Keyingi seansda deploy qilaman» — taqiqlanadi: yarim ish serverda va lokalda farq qilib qoladi.
3. **TZ da yo'q qaror — o'zingiz tanlamang.** Ikki yo'l bor va tartib shu:
   **(a) Qoida vaqt o'tib o'zgarishi mumkinmi?** — bo'lsa **panelga sozlama qilib chiqaring**
   (naqsh: `funnel_settings` + `FunnelSettingsCard.tsx`), default eng xavfsiz tomonga qo'ying.
   Masalan: ushlanma qoldig'i (S-02), sinov muddati uzunligi, e'lon kunlik limiti,
   tavsiya bonusi summasi, ta'til to'qnashuvi chegarasi.
   **(b) Faqat bir marta qabul qilinadigan tamoyil bo'lsa** — egasidan so'rang.
   Shubha bo'lsa — (a) ni tanlang: sozlama ortiqcha bo'lsa zarari yo'q, kodda
   qotirilgan qaror esa keyin migratsiya talab qiladi.
4. **Parallel seans bo'lishi mumkin.** Commitdan oldin `git status`, faqat **o'z** fayllaringizni `git add` qiling, migratsiya ID sini tekshiring.
5. **Har modul yakunida bitta savol:** «xodim boshqa birovning ma'lumotini ko'ra oladimi?» Javob «yo'q» bo'lmaguncha modul tayyor emas (TZ yakuniy tavsiyasi).
6. **HR ishi parallel ketsin:** agent 3.1 ni yozayotganda HR kurs materiallarini tayyorlasin. Aks holda modul tayyor bo'ladi, ichi bo'sh qoladi — bu tizimda allaqachon **to'rt marta** takrorlangan.
