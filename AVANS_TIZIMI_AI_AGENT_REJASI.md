# Avans tizimi — AI agent uchun bosqichma-bosqich yo'riqnoma

**Manba TZ:** `Avans_tizimi.docx` (bot orqali avans so'rovi + mavjud modulning 8 ta bo'shlig'i, 9–12 dasturchi-kuni)
**Bu hujjat:** o'sha TZ ni **AI agent bajaradigan seanslarga** bo'lib chiqadi.
**Yozilgan:** 2026-08-20 · **Loyiha:** `D:\Project\hodimlar_tizimi`

---

## 0. Bu hujjat qanday ishlatiladi

1. **Bitta bosqich = bitta agent seansi = 5–6 soat.**
2. Bosqichlar tartib bilan. «Oldin» qatorida sharti yozilgan.
3. Har seans oxirida: testlar yashil → commit → master → deploy → jonli tekshiruv.
4. «Qabul mezoni» to'liq ✅ bo'lmaguncha bosqich tugagan emas.
5. TZ da yo'q qaror chiqsa — **o'zingiz tanlamang**: qoida vaqt o'tib o'zgarishi mumkin bo'lsa **HR panelidagi sozlamaga** chiqaring (naqsh: `advance_settings`, `funnel_settings`), default eng xavfsiz tomonga.

**Jami:** 19 bosqich · 4 blok. Har blok oxirida tizim ishlaydigan holatda.

> **Umumiy loyiha qoidalari va 13 ta tuzoq** `YANGI_MODULLAR_AI_AGENT_REJASI.md` ning 1-bo'limida.
> Har seans boshida **o'sha bo'limni ham** o'qing. Quyida faqat avansga xos qo'shimchalar.

---

## 1. TZ NI TEKSHIRDIM — IKKITA TUZATISH

TZ yozilganda ba'zi narsalar taxmin qilingan edi. Kodda **tekshirdim** (2026-08-20):

### 1.1 🔴 «Ikki kirish yo'li bitta jadvalga yozadimi» — YOZADI, xavf boshqa joyda

TZ 5-bo'lim, 1-band buni «eng jiddiy xavf» deb belgilagan va «ikkalasi bitta jadvalga yozsin» degan.

**Haqiqiy holat:** ikkalasi ham allaqachon **bitta jadvalga** yozadi:
- `api/routers/requests.py:334` → `PayrollAdjustment(category='advance')`
- `api/routers/payroll.py:1063` → `PayrollAdjustment(category='advance')`

`build_payslip` shu jadvaldan `status='approved'` bo'lganlarini bir marta yig'adi. Ya'ni **«bitta avans ikki marta ayiriladi» xavfi jadval sababidan EMAS**.

**Lekin haqiqiy xavf bor va u boshqacha:** xodim ariza berib avans so'raydi (yozuv-1), HR o'sha avansni «Ish haqi → Avans» sahifasidan **qo'lda ham kiritadi** (yozuv-2). Ikkita mustaqil qator — ikki marta ayiriladi. Bot qo'shilsa uchinchi yo'l paydo bo'ladi va xavf uch barobar oshadi.

👉 **A-01 shu haqiqiy xavfni yopadi** (dublikat qo'riqchisi), jadval birlashtirish emas.

### 1.2 🔴 Yangi `advances` jadvali YARATILMAYDI

TZ 6-bo'limda `advances` jadvali tavsiflangan. **Yaratmang.**

Sabab: avans allaqachon `payroll_adjustments` (category=`advance`) da yashaydi va payroll hisobi **o'sha jadvaldan** o'qiydi. Yangi jadval ochilsa **ikkita haqiqat manbai** paydo bo'ladi — bu aynan TZ ning o'zi ogohlantirgan xato.

👉 To'g'ri yo'l: mavjud jadvalni **kengaytirish** (`source`, `deleted_at`, `requested_at`, `reject_reason`). TZ ning maydon ro'yxati saqlanadi, joyi boshqacha.

### 1.3 Mavjud holat (tekshirilgan)

| TZ bandi | Holat |
|---|---|
| #1 ikki kirish yo'li | ✅ bitta jadval · ❌ dublikat qo'riqchisi yo'q |
| #2 chegara yo'q | ❌ tasdiqlangan — hech qanday tekshiruv yo'q |
| #3 xodim bo'yicha jami | ❌ yo'q |
| #4 pul tasdiqdan oldin | ⚠️ `issued_on` bor, lekin «kiritildi/berildi» ajratilmagan |
| #5 oy yopilsa nima bo'ladi | ❌ qoida yozilmagan |
| #6 xodim o'z avansini ko'radimi | ⚠️ kabinetda payslipda ko'rinadi · ❌ botda yo'q |
| #7 yumshoq o'chirish | ❌ `deleted_at` yo'q |
| #8 «sabab» maydoni | ⚠️ bor, lekin bo'sh/ma'nosiz to'ldiriladi |
| `advance_settings` | ❌ yo'q |
| outbox (xabar navbati) | ❌ yo'q |

---

## 2. AVANSGA XOS QOIDALAR (har seansda)

| Qoida | Sabab |
|---|---|
| **Bot pul yubormaydi** | Faqat so'rov yig'adi va chegarani ko'rsatadi. Tasdiq — boshliqda, to'lov — kassada |
| **Foiz ko'rsatilmaydi** | Xabarda «oylikning 40%i» emas, **aniq summa**. Xodim tushunadi, bahs chiqmaydi |
| **Ohang: eslatma, taklif emas** | «Avans kuni, kerak bo'lsa so'rashingiz mumkin» — «Qancha avans olasiz?» EMAS. Aks holda avans odatga aylanadi |
| **Xabar cron/outbox orqali** | 15 xodimga so'rov ichida yuborilsa Telegram qayta yuboradi → xabar 2–3 marta ketadi |
| **Holat bazada, FSM da emas** | Passenger jarayoni istalgan paytda o'chadi |
| **ROP KO'RMAYDI** | Avans — shaxsiy moliyaviy ma'lumot. Begona so'rovga **404** |
| **Chegara hisobi og'ir** | Cron ichida, foydalanuvchi so'rovi ichida emas |
| **Manfiy oylik bo'lmasin** | Chegara + cap ikkalasi ham tekshiriladi |

---

## 3. BOG'LIQLIK

```
A BLOK (mavjud modulni tuzatish) ──► bot qo'shishdan OLDIN (TZ: «tartib muhim»)
   A-01..A-06
        │
        ▼
B BLOK (sozlama + outbox poydevori)
   B-01..B-04
        │
        ▼
C BLOK (bot oqimi)          D BLOK (HR paneli va nazorat)
   C-01..C-05  ──────────►     D-01..D-04
```

---

# A BLOK — MAVJUD MODULNI TUZATISH

> TZ: «Bot qo'shilsa, so'rovlar soni bir necha barobar oshadi — va mavjud teshik ham shuncha marta takrorlanadi.»

---

### A-01 · Dublikat avans qo'riqchisi (TZ #1) — ✅ BAJARILDI (2026-08-20)
**Oldin:** — · **~5 soat** · 🔴 **PUL XAVFI**

> **Bajarilgani:** `PayrollAdjustmentSource` enum + `payroll_adjustments.source`
> ustuni (migratsiya `av01a1b2c3d4`), `_find_duplicate_advance()` (summa ±10%,
> sana ±7 kun, rad etilganlar hisobga olinmaydi), `POST /payroll/advances`
> → 409 `advance_duplicate` + `confirm_duplicate` bayrog'i, HR ro'yxatida
> «ariza orqali» yorlig'i va tasdiq oynasi. Test: `test_advance_duplicate_guard`
> (15/15). **Tasdiqlandi (1-qadam):** `requests.py:_apply_advance` va
> `payroll.py:create_advance` ikkalasi ham AYNAN bitta jadvalga
> (`PayrollAdjustment(category='advance')`) yozadi — keyingi agent qayta
> tekshirmasin.

**Ish**
1. Avval **tasdiqlang**: `requests.py` va `payroll.py` ikkalasi ham `PayrollAdjustment(category='advance')` yozadi (1.1-bo'limga qarang). Yozib qo'ying — keyingi agent qayta tekshirmasin.
2. `payroll_adjustments` ga `source` ustuni: `hr_manual` · `request` · `bot`. Mavjud qatorlarga migratsiyada `hr_manual` (yoki `source_request_id` bo'lsa `request`).
3. **Dublikat qo'riqchisi:** bir xodimga bir davrda **yaqin summa va yaqin sana** bilan ikkinchi avans kiritilsa — saqlashdan oldin ogohlantirish: «Bu xodimda shu oyda allaqachon N ta avans bor: … Baribir kiritilsinmi?». Bloklamaydi, lekin **ko'r-ko'rona o'tkazmaydi**.
4. Ariza orqali kelgan avans HR sahifasida **«ariza orqali»** deb belgilanadi — HR uni qo'lda takrorlamasin.

**Qabul mezoni**
- [x] `source` yoziladi: `hr_manual` (HR sahifasi) va `request` (ariza).
      `bot` qiymati enum va UI'da tayyor, lekin uni YOZADIGAN yo'l C blokda
      quriladi — hozircha hech qayerdan yozilmaydi.
- [x] Eski qatorlar migratsiyada to'g'ri belgilangan
      (`source_request_id` bor bo'lsa `request`, aks holda `hr_manual`;
      avans bo'lmagan qatorlar tegilmaydi — ular uchun manba tushunchasi yo'q)
- [x] Dublikat ogohlantirishi ishlaydi (test: bir oyda ikki marta)
- [x] Ariza orqali kelgani ro'yxatda ajralib turadi
- [x] O'tgan oylar payslip'i **o'zgarmagan** — faqat ustun qo'shildi,
      summa/hisoblash mantiqiga tegilmadi (payroll testlari 86/86)

**Tuzoq:** `source` ni `NOT NULL` qilmang — migratsiya paytida eski qatorlar bor. Default bilan to'ldiring.

---

### A-02 · Chegara formulasi — yadro (TZ #2) — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-01 · **~6 soat** · 🔴 **PUL XAVFI**

> **Bajarilgani:** `api/services/advance.py` — `compute_limit()` (toza,
> DB'siz formula) + `limit_for()` (`AdvanceLimit` dataklassi: limit va
> BARCHA oraliq qiymatlar). Sof oylik, oydagi ish kuni va ishlangan kun
> `payroll.build_payslip` dan olinadi — ikkinchi hisob yo'li YO'Q.
> «Sof oylik» = `net + adjustments_minus` (ushlanmalardan oldingi netto),
> aks holda avans/ushlanma ikki marta ayirilardi. `coefficient` (0.5) va
> `cap_percent` (50) hozircha modul defaultlari va `limit_for()` ga
> parametr — B-01 `advance_settings` ni ulaganda bir qator o'zgaradi.
> Test: `test_advance_limit` (17/17).
>
> **Bajarilmagani:** «Tuzoq»dagi cron'da oldindan hisoblab saqlash
> qilinmadi. `limit_for()` bitta xodim uchun chaqiriladi (A-03 kirish
> nuqtalari aynan shunday ishlatadi) va bu narx normal. Ko'p xodim
> birdaniga kerak bo'ladigan joy — C blokdagi bot taqsimoti; kesh
> o'sha yerda, haqiqiy ehtiyoj ko'ringanda qurilsin.

**Ish**
1. `api/services/advance.py` — yangi modul:
   ```
   maksimal = (sof oylik ÷ oydagi ish kuni) × ishlangan kun × koeffitsient
   maksimal = min(maksimal, sof oylik × cap_foiz)
   maksimal −= shu oyda olingan (tasdiqlangan + kutilayotgan) avanslar
   maksimal −= shu oydagi ushlanmalar
   agar maksimal < 0 → 0
   ```
2. **Manbalar mavjud kodda:** sof oylik — `payroll.build_payslip` (yoki `resolve_rate` + `compute_base`); ish kunlari — `payroll.month_schedule` (bayramlar bilan, S-09 dan); ishlangan kun — `collect_attendance`.
3. ⚠️ **Ikkinchi hisob yo'li yaratmang.** Payroll qanday hisoblasa, avans ham shundan olsin — aks holda «payslipda boshqa, avansda boshqa» bo'ladi.
4. `limit_for(user, on_date)` → `{limit, sof_oylik, ish_kuni, ishlangan_kun, olingan, ushlanma, sabab_agar_0}`.

**Qabul mezoni**
- [x] Formula TZ dagidek, birma-bir test bilan
- [x] Oyning 5-kunida ishga kirgan xodimda chegara kichik chiqadi
- [x] Cap koeffitsientdan qat'i nazar oshmaydi (koef 2.0 da ham 50% da to'xtaydi)
- [x] Kutilayotgan avans ham ayiriladi (faqat tasdiqlangan emas)
- [x] Chegara 0 bo'lsa **sababi** qaytariladi — 6 ta sabab:
      stavka belgilanmagan · davr qulflangan · ishlangan kun yo'q ·
      ish kuni rejalashtirilmagan · oylik 0 · chegara to'liq ishlatilgan
- [x] Test: 17 ta tekshiruv (11 toza formula + 6 DB)

**Tuzoq:** Sof oylik hisoblash og'ir — chegara **cron ichida** hisoblanadi va saqlanadi; foydalanuvchi so'rovi uni tayyor holda oladi.

---

### A-03 · Chegarani kiritish nuqtalariga ulash (TZ #2) — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-02 · **~5 soat**

> **Bajarilgani:** `POST /payroll/advances` chegaradan oshsa 400
> `advance_over_limit` (ruxsat etilgan summa va kelib chiqishi xabarda —
> HR raqamni taxmin qilmasin). Istisno: `override_limit` + majburiy
> `override_reason`, faqat Boshliq/Dasturchi; auditga alohida
> `advance_over_limit` amali sifatida tushadi. Ariza yo'li
> (`requests._apply_advance`) ham AYNAN shu chegarada to'xtaydi.
> `GET /payroll/advances/limit` — forma xodim tanlangan zahoti chegarani
> va uning kelib chiqishini ko'rsatadi. Test: `test_advance_limit_gate`
> (12/12).
>
> **Qaror:** ariza tasdig'ida istisno yo'li ATAYLAB qo'yilmadi — u oynada
> sabab so'raydigan maydon yo'q, izsiz istisno esa qoidani ma'nosiz
> qiladi. Chindan kerak bo'lsa Boshliq HR sahifasidan sabab bilan kiritadi.

**Ish**
1. HR qo'lda kiritishida chegara tekshiruvi: oshsa **400** + tushunarli xabar («ruxsat etilgan: 1 240 000»).
2. Ariza orqali avansda ham shu tekshiruv.
3. **Chetlab o'tish huquqi:** Boshliq/Dasturchi chegaradan oshiq kirita olsin, lekin **sabab majburiy** va auditga yoziladi (istisno bo'lishi mumkin, lekin izsiz emas).
4. Formada chegara **oldindan ko'rsatiladi** — HR kiritishdan oldin biladi.

**Qabul mezoni**
- [x] Chegaradan oshiq oddiy yo'l bilan kiritib bo'lmaydi (HR -> 400, ariza -> 400)
- [x] Boshliq istisno qila oladi, sabab bilan va auditda (HR urinsa 403)
- [x] Xodim tanlanganda chegara darhol ko'rinadi (kelib chiqishi bilan)
- [x] Test: chegara ichida / chegaradan oshiq / istisno / sababsiz istisno /
      HR istisnosi / ariza yo'li

---

### A-04 · «Kiritildi» va «berildi» ni ajratish (TZ #3, #4) — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-01 · **~5 soat**

> **Bajarilgani:** `PayrollAdjustmentStatus.issued` + `issued_by`/`issued_at`
> (migratsiya `av02b2c3d4e5`). Zanjir: `pending` → `approved` → `issued`.
> `issued_on` endi KIRITISHDA so'ralmaydi va yozilmaydi — uni faqat
> `POST /payroll/advances/{id}/issue` («To'lab berildi») to'ldiradi.
> Noto'g'ri o'tishlar 400: tasdiqlanmaganni to'lash, ikki marta to'lash,
> kelajakdagi sana. Web: forma sana maydonisiz, ro'yxatda «To'lab berildi»
> tugmasi va **xodim bo'yicha oylik jami** bloki. Test:
> `test_advance_issue_flow` (12/12).
>
> **⭐ Eng xavfli joy va u qanday yopildi:** `issued` oylikka kirmasa,
> to'langan pul oylikdan ayirilmay qolardi. Shuning uchun
> `PAYROLL_COUNTED_STATUSES = (approved, issued)` konstantasi kiritildi va
> **uchta** joyda ishlatiladi: `build_payslip`, botdagi payslip
> (`advance_total`) va ariza qaytarish (`_revert` — to'langan avansni
> jimgina o'chirmaslik). Test payslipda summani aniq tekshiradi.
>
> **Yon ta'sir:** dublikat qo'riqchisi (A-01) endi `issued_on` o'rniga
> `_advance_ref_date()` ishlatadi — yangi avansda sana bo'sh bo'lgani
> uchun kiritilgan kun bilan solishtiriladi. Aks holda qo'riqchi eng
> kerakli holatda (ketma-ket ikki marta kiritish) jim qolardi.

**Ish**
1. TZ #4: hozir «berilgan sana» kiritiladi, tasdiq keyin so'raladi — boshliq rad etsa **pul allaqachon qo'lda**.
   Yechim: `issued_on` faqat **tasdiqlangandan keyin** to'ldiriladi. Kiritishda u so'ralmaydi.
   Holatlar: `pending` → `approved` → `issued` (yoki `rejected`).
2. `issued` uchun alohida amal: «To'lab berildi» (kassa) — kim va qachon belgiladi.
3. TZ #3: xodim bo'yicha **oylik jami** ko'rsatilsin (bittalab qator emas, yuqorida yig'indi).

**Qabul mezoni**
- [x] Tasdiqlanmagan avansga `issued_on` yozib bo'lmaydi
- [x] `issued` holati alohida va kim belgilagani ko'rinadi («To'ladi: …»)
- [x] Xodim bo'yicha oylik jami ro'yxatda bor
- [x] Payslipga faqat `approved`/`issued` kiradi — testda summa aniq
      tekshiriladi (200 000 + 50 000 ayirildi, rad etilgan 70 000 yo'q)
- [x] Test: holat zanjiri + 3 xil noto'g'ri o'tish 400 bilan to'xtaydi

**Tuzoq:** Mavjud yozuvlar `approved` va `issued_on` to'ldirilgan — migratsiyada ularni `issued` qiling, aks holda «to'lanmagan» bo'lib ko'rinadi.

---

### A-05 · Yumshoq o'chirish, audit va sabab maydoni (TZ #7, #8) — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-01 · **~4 soat**

> **Bajarilgani:** `payroll_adjustments.deleted_at/deleted_by/deleted_reason`
> (migratsiya `av03c3d4e5f6`, `SalaryRate` naqshi bilan bir xil). `DELETE`
> endi yumshoq: qator bazada qoladi, `deleted_at` qo'yiladi. Huquq: HR
> faqat `pending` ni, tasdiqlangan/to'langanni Boshliq/Dasturchi (HR urinsa
> 403). Har o'chirish auditda `before`/`after` bilan. Web: o'chirish
> tugmasi + sabab oynasi (tasdiqlangan yozuvda alohida ogohlantirish).
> Sabab qoidasi — `fine_policies.advance_reason_required` (HR paneli,
> DEFAULT O'CHIQ); yoqilganda kamida 5 belgi VA `_MEANINGLESS_REASONS`
> ro'yxatidagi matnlar («avans», «kerak», «pul», …) o'tmaydi.
> Test: `test_advance_soft_delete` (15/15).
>
> **⭐ `deleted_at IS NULL` OLTI joyda:** `build_payslip` (eng muhim),
> `advance.taken_and_deductions` (chegara bo'shasin), dublikat qidiruvi,
> `list_adjustments`, botdagi payslip, ariza qaytarish. Bittasi
> unutilsa o'chirish «ko'zga ko'rinadigan, lekin pulga ta'sir qilmaydigan»
> soxta amal bo'lib qolardi — test payslip summasini aniq tekshiradi.
>
> **Bajarilmagani:** sabab qoidasi ARIZA yo'lida tekshirilmaydi. Sabab:
> ariza matnini xodim yozadi, tekshiruv esa TASDIQLASH paytida ishga
> tushardi — ya'ni xodimning xatosi uchun rahbar bloklanardi. To'g'ri
> joy — ariza YARATISH oqimi (C blok, bot).

**Ish**
1. `payroll_adjustments.deleted_at` qo'shiladi. **Barcha o'qish** `deleted_at IS NULL` bilan filtrlanadi — ayniqsa `build_payslip`.
2. Kim o'chira oladi: HR (tasdiqlanmaganini), Boshliq/Dasturchi (hammasini). Har o'chirish `AuditLog` ga.
3. TZ #8 «sabab»: bo'sh yoki «avans» kabi ma'nosiz matn qabul qilinmasin. Ikki variant — **sozlamada tanlanadi**: (a) sabab majburiy va kamida N belgi, (b) umuman so'ralmaydi. Default: **(b) so'ralmaydi** (bot oqimida xodim sabab yozmaydi, majburiy qilsak oqim buziladi).

**Qabul mezoni**
- [x] O'chirilgan avans payslipga **kirmaydi** — test summani aniq
      tekshiradi (300 000 → 0)
- [x] Har o'chirish auditda: kim, qachon, qaysi summa, qaysi sabab
- [x] Sabab qoidasi panelda sozlanadi (HR «Ish haqi → Sozlamalar»)
- [x] Xodim o'chira olmaydi — endpoint `_require_manage`
      (HR/Boshliq/Dasturchi) ostida, xodimda bu sahifa umuman yo'q

---

### A-06 · Oy yopilishi qoidasi va xodim ko'rinishi (TZ #5, #6) — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-04 · **~5 soat**

> **Bajarilgani:** `fine_policies.advance_pending_on_close`
> (`carry` DEFAULT / `cancel`, migratsiya `av04d4e5f6a7`) + HR panelida
> tanlash. `approve_period` davrni qulflaganda `_close_pending_advances()`
> chaqiriladi — davr qulfi bilan **bitta tranzaksiyada** (yarim
> ko'chirilgan holat bo'lmasin). Har xodimning O'Z qoidasi o'qiladi
> (`resolve_policy`: xodim > lavozim > global). Xodimga ALOHIDA xabar
> boradi — «oyligingiz tasdiqlandi» xabarining ichiga qo'shilmaydi,
> chunki bu boshqa voqea. Preflight endi `pending_advances` qaytaradi va
> `ok=False` qiladi. Bot: «💵 Avanslarim» tugmasi (`/payroll/my/{tg}/advances`),
> kabinet uchun `/payroll/me/advances` — ikkalasi AYNAN bitta funksiyani
> chaqiradi. Test: `test_advance_period_close` (20/20).
>
> **Muhim tafsilot:** tasdiqlangan va to'langan avanslarga TEGILMAYDI —
> faqat `pending` ishlanadi. Ko'chirilgan avans keyingi davrda `pending`
> bo'lib qoladi, ya'ni tasdiq zanjiri uzilmaydi.

**Ish**
1. TZ #5: davr yopilganda (`payroll_periods.locked`) hali `pending` bo'lgan avans nima bo'ladi — **sozlamada**: (a) keyingi davrga o'tadi, (b) avtomatik bekor bo'ladi. Default: **(a) o'tadi** (pul so'ragan odam javobsiz qolmasin).
2. Yopish oldidan HR ga ogohlantirish: «3 ta avans hali tasdiqlanmagan».
3. TZ #6: xodim **botda** ham o'z avansini ko'rsin — «💵 Mening avanslarim»: shu oydagi so'rovlar, holati, jami va **qolgan chegara**. Kabinetda payslipda allaqachon ko'rinadi (tekshirilgan).

**Qabul mezoni**
- [x] Yopilganda pending avans sozlamaga muvofiq ishlanadi
      (`carry` → keyingi davr, `cancel` → rad + sabab)
- [x] HR ogohlantirish oladi (preflight `pending_advances`, `ok=False`)
- [x] Xodim botdan o'z avansini, jamisini va qolgan chegarasini ko'radi
- [x] Boshqa xodimniki ko'rinmaydi — yo'lda `user_id` umuman yo'q,
      shaxs `telegram_id`/JWT dan yechiladi; noma'lum id → 404,
      bot sirisiz → 401

---

**✅ A BLOK YAKUNI (2026-08-20 — TUGADI):** A-01…A-06 bajarildi, mavjud
modul pul xatosi bermaydigan holatga keldi. Endi bot qo'shish xavfsiz.

Umumiy test: 6 ta yangi test funksiyasi, avans+oylik jami **193/193**.
Migratsiyalar: `av01a1b2c3d4` (manba), `av02b2c3d4e5` (to'lash holati),
`av03c3d4e5f6` (yumshoq o'chirish + sabab), `av04d4e5f6a7` (oy yopilishi).

**Keyingi agent uchun eng muhim uch narsa:**
1. `PAYROLL_COUNTED_STATUSES` va `deleted_at IS NULL` — avans o'qiladigan
   HAR bir joyda ikkalasi ham bo'lishi shart. Yangi o'qish joyi
   qo'shsangiz shu ikkisini unutmang, aks holda pul jimgina noto'g'ri
   hisoblanadi.
2. `limit_for()` ichida `build_payslip` bor — QIMMAT. Ro'yxat ustida
   sikl ichida chaqirmang (C blok bot taqsimotida kesh kerak bo'ladi).
3. Sozlamalar hozircha `fine_policies` da (`advance_reason_required`,
   `advance_pending_on_close`). B-01 `advance_settings` jadvalini
   qurganda ularni O'SHA YERGA ko'chiring va `resolve_advance_settings`
   ni `limit_for(coefficient=..., cap_percent=...)` ga ulang.

---

# B BLOK — SOZLAMA VA XABAR POYDEVORI

---

### B-01 · `advance_settings` — uch darajali qamrov — ✅ BAJARILDI (2026-08-20)
**Oldin:** A-06 · **~5 soat**

> **Bajarilgani:** `advance_settings` jadvali (migratsiya `av05e5f6a7b8`)
> TZ dagi barcha maydonlar bilan. `resolve_advance_settings(db, user)` —
> xodim > lavozim > global, faqat `is_active`; naqsh `payroll.resolve_policy`
> dan AYNAN ko'chirilgan. A blokda vaqtincha `fine_policies` da turgan ikki
> sozlama migratsiyada **qamrovi bilan birga ko'chirildi** va eski ustunlar
> o'chirildi — HR kiritgan qiymat yo'qolmadi. `limit_for()` endi sozlamani
> O'ZI yechadi (chaqiruvchilar takrorlamasin va bittasi unutib default
> bilan ishlab ketmasin). Test: `test_advance_settings` (19/19).
>
> **«Sozlamasiz» holat ikki xil talqin qilinadi va bu ataylab:**
> chegara hisobi default qiymatlar bilan DAVOM ETADI (HR ning qo'lda
> kiritish ishi to'xtab qolmasin), botning avans kuni xabari esa UMUMAN
> yuborilmaydi (`announce_ready()` — sozlanmagan tizim xodimga pul taklif
> qilmasin). Ikkalasi bitta funksiyada, har chaqiruvchi o'zicha
> talqin qilmasin.

**Ish**
1. `advance_settings`: `scope` (global/position/user), `scope_id`, `advance_day` (20), `coefficient` (0.5), `cap_percent` (50), `min_amount`, `reminder_time` (14:00), `pending_on_close` (carry/cancel), `reason_required`, `is_active`, `effective_from`.
2. `resolve_advance_settings(user)` — **xodim > lavozim > global**, faqat `is_active`. Mavjud `payroll.resolve_policy` naqshi bilan **aynan bir xil** yozilsin.
3. Hech qanday sozlama bo'lmasa — **avans so'rovi umuman yuborilmaydi** (sozlanmagan holat xavfsiz tomonga).

**Qabul mezoni**
- [x] Uch daraja to'g'ri ishlaydi (test: har daraja + `is_active=False` bo'shligi)
- [x] Sozlamasiz tizim jim turadi (`resolve_advance_settings` -> `None`)
- [x] «Sozlanmagan modullar» blokiga qator qo'shildi (`advance_settings`, critical)

---

### B-02 · Sozlamalar paneli (HR) — ✅ BAJARILDI (2026-08-20)
**Oldin:** B-01 · **~4 soat**

> **Bajarilgani:** `/payroll/settings` da yangi **«Avans»** tabi
> (`AdvanceSettingsTab.tsx`) — beshta qiymat ham (avans kuni, koeffitsient,
> cap %, eng kam summa, xabar soati) + oy yopilishi qoidasi va sabab
> bayrog'i. Har maydon ostida bir qatorlik izoh. Qamrov tanlash:
> hamma / lavozim / xodim; qamrovni o'chirish kengroq darajaga qaytaradi.
> Endpointlar: `GET/PUT /payroll/advance-settings`,
> `DELETE /payroll/advance-settings/{id}` — `fine_policies` bilan aynan
> bir xil upsert naqshi. Har o'zgarish auditda
> (`advance_settings_upserted` / `advance_settings_deleted`), `before`
> to'liq oldingi holat bilan.
>
> **Ikki tuzoq oldindan yopildi:** (a) `row_to_dict` SHART — `Decimal`
> qiymatlar (coefficient, cap, min_amount) JSON audit ustuniga yozilmaydi
> va commit paytida sozlama o'zgarishi ham qaytarilardi (`fine_policies`
> da aynan shu xato bo'lgan); (b) `advance_day` 28 dan oshmaydi —
> fevralda 29–31-kun yo'q va xabar o'sha oyda umuman yuborilmasdi.

**Ish**
1. `/payroll/settings` ga «Avans» bo'limi: TZ jadvalidagi beshta qiymat + qamrov tanlash.
2. Har maydon ostida bir qatorlik izoh (TZ dagi «Izoh» ustuni).
3. Kim o'zgartiradi: HR/Boshliq/Dasturchi. Har o'zgarish auditga.

**Qabul mezoni**
- [x] Beshta qiymat ham panelda (+ yopilish qoidasi va sabab bayrog'i)
- [x] Lavozimga alohida chegara qo'yish ishlaydi (test: koef 0.6 -> chegara oshdi)
- [x] O'zgarish auditda ko'rinadi (yaratish, yangilash va o'chirish)

---

### B-03 · Outbox — xabar navbati — ✅ BAJARILDI (2026-08-20)
**Oldin:** B-01 · **~6 soat** · ⭐ **Boshqa modullar ham ishlatadi**

> **Bajarilgani:** `outbox` jadvali (migratsiya `av06a7b8c9d0`) +
> `api/services/outbox.py`: `enqueue()` / `tick()`.
> `cron_jobs.outbox_tick` va `scripts/cron_tick.py` da HAR DAQIQA
> (O'Z lock'i bilan — `cron_misc` dagi sekin tick tufayli xabar
> kechikmasin). Endpoint `POST /payroll/outbox-tick` (Docker/qo'lda
> tekshiruv uchun). Test: `test_outbox` (12/12).
>
> **Uch qo'riqchi:**
> 1. **Ikki jarayon.** Productionда cron IKKI nusxada ishlaydi
>    (`uysot-rate-budget` xotirasi). Navbatdan olish atomar
>    `UPDATE ... SET status='sending', claimed_by=:token WHERE
>    status='pending'`, keyin jarayon FAQAT o'z tokeni bo'yicha oladi.
>    Test band qilingan qatorni ikkinchi tick olmasligini tekshiradi.
> 2. **Osilib qolish.** Jarayon yuborish o'rtasida o'lsa qator abadiy
>    `sending` bo'lib qolardi — `_reclaim_stale()` 10 daqiqadan keyin
>    uni `pending` ga qaytaradi.
> 3. **Takror.** `dedupe_key` UNIQUE + `IntegrityError` ushlanadi
>    (poyga holati uchun). B-04 dagi «oyiga bir marta» aynan shu
>    maydon bilan ishlaydi — alohida jadval kerak emas.
>
> **Bitta ataylab qilingan istisno:** navbat nosozligi haqidagi HR
> ogohlantirishi navbatdan O'TMAYDI, to'g'ridan-to'g'ri yuboriladi —
> buzilgan navbatga «navbat buzilgan» xabarini qo'yish uni ham
> yo'qotish demak.

**Ish**
1. `outbox`: `id`, `chat_id`, `kind`, `payload` (JSON), `status` (kutmoqda/yuborildi/xato), `attempts`, `last_error`, `scheduled_at`, `sent_at`.
2. `cron_jobs.outbox_tick` — navbatdan N tani oladi va yuboradi. **3 urinishdan keyin to'xtaydi** va HR ga xabar beradi.
3. Telegram rate-limit: tick'da yuboriladigan xabar soni cheklangan (masalan 20), qolgani keyingi tick'da.
4. ⚠️ Xabar **so'rov ichida yuborilmaydi** — hamma joyda outbox orqali.

**Qabul mezoni**
- [x] Xabar navbatga qo'yiladi va cron yuboradi
- [x] 3 urinishdan keyin `failed` va HR ga xabar (test: aynan bir marta)
- [x] Bir xabar ikki marta yuborilmaydi — parallel tick + band qilingan
      qatorni ikkinchi tick olmasligi alohida tekshiriladi
- [x] Rate-limit hisobga olingan (`BATCH_SIZE=20`, ortiqchasi keyingi tick'da)

**Tuzoq:** Cron har daqiqada yangi jarayon — navbat faqat bazada. Lock yoki `status='running'` bilan ikki jarayon bitta xabarni olmasin.

---

### B-04 · Avans kuni cron'i va takroriylik qo'riqchisi — ✅ BAJARILDI (2026-08-20)
**Oldin:** B-03, A-02 · **~5 soat**

> **Bajarilgani:** `api/services/advance_day.py` — `tick(db, on_date)`.
> `cron_jobs.advance_day_tick` + `scripts/cron_tick.py` (har kuni 09:05)
> + `POST /payroll/advance-day-tick` (sinov uchun `target_date` bilan).
> Test: `test_advance_day_tick` (10/10).
>
> **`>=` semantikasi va u nega SHART.** Cron o'tkazib yuborilishi mumkin
> (deploy, server o'chishi). `==` bo'lsa xabar o'sha oy UMUMAN ketmasdi
> va buni hech kim sezmasdi. Ammo `>=` xabarni oyning qolgan HAR KUNI
> qayta yuborishga urinadi — shuning uchun takroriylik qo'riqchisi
> ajralmas juftlik.
>
> **Alohida jadval QURILMADI.** Reja `advance_announcements` taklif
> qilgan edi, lekin B-03 dagi `outbox.dedupe_key` (UNIQUE) aynan shu
> ishni bajaradi: `advance_day:2026-08:42`. Ikkinchi jadval bir xil
> haqiqatni ikki joyda saqlab, ular bir-biriga mos kelmay qolish
> xavfini tug'dirardi.
>
> **Chegara xabar bilan birga saqlanadi** (`payload.limit`) — C blokda
> tugma bosilganda qayta hisoblashsiz ishlatiladi va «xodim qanday summa
> ko'rgan edi?» savoliga javob qoladi.

**Ish**
1. `cron_jobs.advance_day_tick`: bugun avans kunimi (`>=` semantikasi — TZ talabi, `==` emas).
2. `advance_announcements` (yoki `advance_month_state`): davr (yil, oy), `sent_at` — **har oy bir marta** qo'riqchisi.
3. Har faol xodim uchun chegara hisoblanadi (**cron ichida**, og'ir so'rov) va outboxga qo'yiladi.
4. **Kimga yuborilmaydi** (TZ ro'yxati): ishdan bo'shash arizasi bergan · ta'tilda (chegara 0) · chegarasi `min_amount` dan past · shu oyda chegarani to'liq ishlatgan.

**Qabul mezoni**
- [x] Cron kechiksa ham xabar tushadi (`>=`) — test kun+2 bilan tekshiradi
- [x] Bir oyda ikki marta yuborilmaydi (`outbox.dedupe_key`)
- [x] To'rt istisno ham ishlaydi (har biriga test): ishdan bo'shash
      arizasi · chegara 0 · `min_amount` dan past · sozlama yo'q
- [x] Chegara xabar bilan birga saqlanadi (`payload.limit`)

---

**✅ B BLOK YAKUNI (2026-08-20 — TUGADI):** B-01…B-04 bajarildi.
Sozlama poydevori, xabar navbati va avans kuni cron'i tayyor — endi
C blokdagi bot oqimini qurish mumkin.

Test: 3 ta yangi test funksiyasi (`test_advance_settings`, `test_outbox`,
`test_advance_day_tick`), avans+oylik jami **211/211**.
Migratsiyalar: `av05e5f6a7b8` (sozlamalar), `av06a7b8c9d0` (outbox),
`mg01f6a7b8c9` (parallel shox bilan birlashtirish).

**C blok agenti uchun eng muhim uch narsa:**
1. **Xabarni to'g'ridan-to'g'ri yubormang** — `outbox.enqueue()` orqali.
   So'rov ichida `send_message` chaqirish cPanel'da butun saytni qotiradi
   (konkurentlik = 1).
2. **Avans kuni xabari allaqachon navbatga tushadi** (B-04). C-01 da
   qilinadigan ish — o'sha xabarga TUGMA qo'shish
   (`outbox.enqueue(..., reply_markup=...)`) va callback'ni ushlash.
   Chegara `payload.limit` da tayyor turadi.
3. **Sozlamasiz jim turing.** `resolve_advance_settings()` `None`
   qaytarsa bot hech narsa taklif qilmasligi kerak — bu qoida B-01 da
   qo'yilgan va C blokda ham amal qiladi.

---

# C BLOK — BOT OQIMI

---

### C-01 · Avans kuni xabari — ✅ BAJARILDI (2026-08-20)
**Oldin:** B-04 · **~5 soat**

> B-04 dagi xabarga tugmalar qo'shildi (`advance_bot.keyboard`).
> `callback_data` — `adv:need:2026-08` / `adv:no:2026-08`: DAVR ichida,
> shuning uchun o'tgan oyning xabari bosilsa «bu xabar eskirgan» deyiladi
> va jimgina joriy oyga yozilmaydi. «Kerak emas» → `declined` (takroriy
> eslatma ketmaydi) + qisqa tasdiq. Matn foizsiz, aniq summa bilan,
> eslatma ohangida — «Majburiy emas, kerak bo'lmasa e'tiborsiz qoldiring».

**Ish**
1. Xabar matni TZ namunasidek — **aniq summa**, foiz yo'q, **eslatma ohangida**:
   ```
   💰 Bugun — avans kuni
   {ism}, siz bugun {summa} so'mgacha avans olishingiz mumkin.
   Kerak bo'lsa summani yozing, kerak bo'lmasa «Kerak emas» tugmasini bosing.
   [ Summa kiritish ]   [ Kerak emas ]
   ```
2. «Kerak emas» bosilsa — javob yoziladi (takroriy eslatma **yuborilmaydi**) va qisqa tasdiq.
3. Tugma `callback_data` da **davr** bo'lsin (`adv:need:2026-08`) — eski xabar bosilsa chalkashmasin.

**Qabul mezoni**
- [x] Xabarda foiz **yo'q**, aniq summa bor
- [x] «Kerak emas» javobi yoziladi (`advance_responses.state='declined'`)
- [x] O'tgan oyning xabari bosilsa «bu xabar eskirgan» deydi
- [x] Matn taklif emas, eslatma ohangida (ko'rib chiqilgan)

---

### C-02 · Summa kiritish — holat bazada — ✅ BAJARILDI (2026-08-20)
**Oldin:** C-01 · **~5 soat**

> `advance_responses` jadvali (migratsiya `av07b8c9d0e1`) —
> `state='waiting_input'` + `input_expires_at` (2 soat). FSM da EMAS:
> Passenger jarayoni qayta ishga tushganda xodim yozayotgan summa
> yo'qolardi va u sababini tushunmasdi. Test ATAYLAB yangi sessiyada
> holatni o'qiydi (restart simulyatsiyasi).
>
> **Alohida `advance_pending_input` qurilmadi** — bitta jadval to'rt
> savolga javob beradi: summa kutilyaptimi · javob berdimi (C-05) ·
> eslatma yuborilganmi · qanday summa ko'rsatilgan edi.
>
> **Handler tartibi tuzog'i yopildi.** `amount_router` dispatcher'da
> `anketa.answer_router` dan OLDIN, lekin API summa kutmayotgan bo'lsa
> `SkipHandler` qiladi — aks holda u anketa javoblarini va AI sabab
> matnlarini YUTIB YUBORARDI. Raqamsiz matn ham o'tkaziladi.

**Ish**
1. «Summa kiritish» bosilganda holat **bazaga** yoziladi (`advance_pending_input`: user_id, davr, chegara, `expires_at`) — **FSM da emas** (Passenger o'chadi).
2. Keyingi matn xabari summa deb qabul qilinadi. Raqam bo'lmasa — tushunarli xato.
3. Holat muddati (masalan 2 soat) o'tsa bekor bo'ladi.
4. ⚠️ Bot matn handlerlari tartibi nozik (anketa modulida uchragan tuzoq) — yangi handler boshqa oqimlarni **yutib yubormasin**.

**Qabul mezoni**
- [x] Bot restartdan keyin ham kutish holati saqlanadi
- [x] Raqam bo'lmagan matn boshqa handlerga xalaqit bermaydi
- [x] Muddat o'tsa holat bekor bo'ladi va matn keyingi handlerga o'tadi
- [x] Test: restart simulyatsiyasi (ataylab yangi sessiyada o'qiladi)

---

### C-03 · Chegara tekshiruvi va rad javobi — ✅ BAJARILDI (2026-08-20)
**Oldin:** C-02, A-02 · **~4 soat**

> Chegara **kiritilgan paytda** qayta hisoblanadi — xabar yuborilgan
> paytdagi qiymatga ISHONILMAYDI. Test buni aniq tekshiradi: oraliqda
> boshqa avans tasdiqlanadi va o'sha summa endi «oshiq» bo'lib chiqadi.
> Rad javobida aniq raqam (ruxsat etilgan / so'ralgan) va holat
> `waiting_input` da QOLADI — xodim kichikroq summa yozishi mumkin.
> `min_amount` dan past summa ham rad etiladi.
>
> **Summa matni keng tushuniladi** (`parse_amount`): «1200000»,
> «1 200 000», «1.200.000», «1,5 mln», «500000 so'm». Sabab: «raqam
> tushunilmadi» degan javob xodimni to'xtatib qo'yardi. Butunlay
> raqamsiz matn esa avans oqimiga tegishli emas deb o'tkaziladi.

**Ish**
1. Kiritilgan summa chegaradan oshsa — **qabul qilinmaydi**, ruxsat etilgan summa qayta ko'rsatiladi va qayta kiritish taklif qilinadi.
2. `min_amount` dan kichik bo'lsa ham rad etiladi (mayda so'rovlar).
3. Chegara **xabar yuborilgan paytdagi** emas, **kiritilgan paytdagi** holatdan qayta hisoblanadi (oraliqda boshqa avans tasdiqlangan bo'lishi mumkin).

**Qabul mezoni**
- [x] Oshiq summa rad etiladi, aniq raqam ko'rsatiladi
- [x] Eng kam summadan past rad etiladi
- [x] Chegara qayta hisoblanadi (eski qiymatga ishonilmaydi)
- [x] Test: oraliqda chegara kamaygan holat

---

### C-04 · So'rov panelga tushishi va natija xabari — ✅ BAJARILDI (2026-08-20)
**Oldin:** C-03 · **~5 soat**

> Bot so'rovi `PayrollAdjustment(category='advance', source='bot',
> status='pending')` bo'lib MAVJUD ro'yxatga tushadi — yangi jadval
> yo'q, HR paneli va payslip o'zgarishsiz ishlaydi (A-01 dagi `source`
> ustuni aynan shu kun uchun qo'yilgan edi va endi uchinchi qiymati
> ham ishlatilyapti). Barcha xabarlar OUTBOX orqali.
>
> **Natija xabari faqat `source='bot'` uchun** — HR qo'lda kiritganida
> `decide_advance` allaqachon xodimga xabar beradi va ikki marta
> yuborilmasligi kerak. Rad xabarida `decided_note` SABAB sifatida
> ko'rsatiladi.

**Ish**
1. Qabul qilingan summa `PayrollAdjustment(category='advance', source='bot', status='pending')` bo'lib yoziladi — **mavjud ro'yxatga** tushadi, yangi jadval yo'q.
2. HR/Boshliqqa xabar (outbox orqali).
3. Boshliq tasdiqlasa/rad etsa — xodimga natija xabari: tasdiqlandi (summa) yoki rad etildi (**sabab bilan**).
4. Rad sababi maydoni (`decided_note` mavjud) — xabarda ko'rsatiladi.

**Qabul mezoni**
- [x] Bot so'rovi mavjud avans ro'yxatida `source='bot'` bilan ko'rinadi
      (web'da «bot orqali» yorlig'i A-01 da qo'yilgan)
- [x] Tasdiq/rad natijasi xodimga boradi
- [x] Rad sababi xabarda bor
- [x] Xabarlar outbox orqali (so'rov ichida emas)

---

### C-05 · Takroriy eslatma va to'xtash — ✅ BAJARILDI (2026-08-20)
**Oldin:** C-04 · **~4 soat**

> `advance_bot.reminder_tick` — `cron_jobs.advance_reminder_tick`,
> soatiga bir marta (`scripts/cron_tick.py`, `minute == 7`). Servis
> o'zi sozlamadagi `reminder_time` ni tekshiradi, shuning uchun cron
> jadvalida aniq soat qattiq yozilmagan — HR vaqtni panelidan
> o'zgartirsa kod tegilmaydi.
>
> **IKKI QATLAM to'xtatish:** `advance_responses.reminded_at` (kimga
> yuborilgani) va `outbox.dedupe_key` (`advance_reminder:2026-08:42`).
> `reminded_at` `enqueue` natijasidan QAT'I NAZAR qo'yiladi — dedupe
> ushlab qolsa ham eslatma allaqachon navbatda.
>
> Eslatmada chegara QAYTA hisoblanadi — asosiy xabardan beri
> o'zgargan bo'lishi mumkin.

**Ish**
1. Sozlamadagi vaqtda (default 14:00) javob bermaganlarga **bitta** takroriy eslatma.
2. Shundan keyin **to'xtaydi** — kun davomida cheksiz eslatma yo'q.
3. «Kerak emas» bosgan yoki summa kiritganlarga eslatma **ketmaydi**.

**Qabul mezoni**
- [x] Bir kunda ko'pi bilan 2 xabar (asosiy + 1 eslatma) — ikkinchi
      tick yangi eslatma qo'shmasligi test bilan tekshirilgan
- [x] Javob berganlarga eslatma ketmaydi (`declined`/`submitted`)
- [x] Test: javob bergan / bermagan / muddati o'tgan holat

---

**✅ C BLOK YAKUNI (2026-08-20 — TUGADI):** C-01…C-05 bajarildi.
Bot oqimi to'liq: e'lon → tugma → summa → so'rov → natija, javob
bermaganga bitta eslatma.

Test: `test_advance_bot_flow` (36/36), avans+oylik jami **247/247**.
Migratsiya: `av07b8c9d0e1` (`advance_responses`).

**D blok agenti uchun:**
1. Bot so'rovlari `PayrollAdjustment(source='bot')` — alohida jadval
   YO'Q. D blokdagi hisobotlar shu ustundan filtrlaydi.
2. `advance_responses` — kim javob bergan/bermaganini ko'rsatadi.
   D-01 dagi «qo'lda e'lon qilish» tugmasi `advance_day.tick(on_date=…)`
   ni chaqirsa yetadi: takroriylik qo'riqchisi allaqachon bor.
3. Xabar yuborish — HAR DOIM `outbox.enqueue()`.

---

# D BLOK — HR PANELI VA NAZORAT

---

### D-01 · «Avans kunini e'lon qilish» (TZ 3-bo'lim) — ✅ BAJARILDI (2026-08-20)
**Oldin:** B-04 · **~5 soat**

> `advance_announcements` jadvali (migratsiya `av08c9d0e1f2`) +
> `advance_day.announce_manually()`. HR panelida «Avans kunini e'lon
> qilish» tugmasi: sana + ixtiyoriy izoh.
>
> **Nega sozlamadagi `advance_day` ni o'zgartirish yaramaydi:** u
> KEYINGI oylarga ham ta'sir qilardi, bu esa faqat shu oyga tegishli
> bir martalik qaror (bayram, kassa kechikishi).
>
> **Avtomatik xabar TO'XTAYDI:** `advance_day.tick` shu davr uchun e'lon
> borligini ko'rsa umuman ishlamaydi — xodim ikki marta xabar olmasin.
>
> **«Oxirgisi kuchda»:** qayta e'lon eski e'londan qolgan HALI
> YUBORILMAGAN xabarlarni navbatdan olib tashlaydi va o'z `id` si
> kalitda bo'lgan yangi xabar qo'yadi. Allaqachon yuborilganini
> qaytarib bo'lmaydi — shuning uchun xabarda sana ANIQ aytiladi
> («avans 23-avgust kuni beriladi») va xodim oxirgisiga qaraydi.
>
> Qabul qiluvchilar ro'yxati avtomatik e'lon bilan AYNAN bir xil
> (chegara 0, ishdan bo'shash, `min_amount` istisnolari) — ikki yo'l
> turli odamlarga xabar yuborsa chalkashlik bo'lardi.

**Ish**
1. HR panelida tugma: sana tanlanadi + ixtiyoriy matn → barcha xodimga xabar (outbox).
2. ⚠️ **Qo'lda e'lon qilingan oyda avtomatik 20-kunlik xabar YUBORILMAYDI** — aks holda xodim ikki marta xabar oladi.
3. Kechiktirilsa xabar aniq aytsin: «Avans kuni 23-avgustga ko'chirildi».
4. `advance_announcements`: davr, sana, matn, yuborgan_id, yuborilgan_vaqt.

**Qabul mezoni**
- [x] E'lon qilingan oyda avtomatik xabar **ketmaydi** (test bilan)
- [x] Ko'chirilgan sana xabarda aniq («23-avgust», raqam emas)
- [x] E'lon tarixi saqlanadi (kim, qachon, nechta xodimga)
- [x] Ikki marta e'lon qilinsa oxirgisi kuchda

---

### D-02 · Boshliq ekrani: kunlik jami summa (TZ 4-bo'lim) — ✅ BAJARILDI (2026-08-20)
**Oldin:** C-04 · **~4 soat**

> `GET /payroll/advance-summary` — «N xodim jami M so'raydi», bugungi
> kesim va tasdiqlangan-lekin-to'lanmagan jami (kassa uchun). Tepada,
> tasdiqlashdan OLDIN: Boshliq bittalab bosib, umumiy og'irlikni faqat
> oxirida bilib qolmasin.
>
> `POST /payroll/advances/bulk-decide` — tanlanganlarni birdan
> tasdiqlash/rad etish. **Har biri ALOHIDA auditga tushadi**
> (`bulk: true` belgisi bilan) va xodimga xabar ham alohida —
> ommaviy amal «kim nimani tasdiqladi» izini yo'qotmasligi kerak.
>
> **«Hammasini belgilash» ATAYLAB yo'q:** ko'rilmagan so'rovni
> tasdiqlab yuborish eng qimmat xato bo'lardi. **Allaqachon hal
> qilingani jimgina o'tkaziladi** — Boshliq ro'yxatni ko'rib
> turganda boshqa birov bittasini tasdiqlagan bo'lishi mumkin va
> butun amal shu sababli yiqilmasligi kerak.

**Ish**
1. Tasdiqlash ekranida yuqorida: «Bugun 9 xodim jami 11 400 000 so'm so'radi».
2. Tanlab tasdiqlash: bir nechta so'rovni belgilab, jami ko'rib, birdan tasdiqlash.
3. Tasdiqlanganlar jami alohida ko'rinadi (kassa uchun).

**Qabul mezoni**
- [x] Jami summa tasdiqlashdan **oldin** ko'rinadi
- [x] Ommaviy tasdiqlash ishlaydi va har biri auditga tushadi
- [x] Xodim bu ekranni ko'rmaydi, ROP ham (test: ikkalasi ham 403).
      Ommaviy tasdiqlashni HR ham qila olmaydi — pul qarori Boshliqniki

---

### D-03 · Ketma-ket avans belgisi (TZ 4-bo'lim) — ✅ BAJARILDI (2026-08-20)
**Oldin:** D-02 · **~4 soat**

> `_advance_streaks()` — joriy davrdan ORQAGA qarab uzluksiz oylar
> sanaladi (oxirgi 12 oy oynasida). Oraliq uzilsa hisob QAYTADAN
> boshlanadi: «umumiy necha marta» emas, aynan «ketma-ket». Rad
> etilgan va o'chirilgan avanslar sanalmaydi — ular pul emas.
>
> 3 oydan boshlab ro'yxatda neytral yorliq: «3 oy ketma-ket».
> ⚠️ **JAZO EMAS** — TZ buni alohida ta'kidlaydi va yorliq matni ham
> ayblovsiz. Xodimga hech qanday xabar ketmaydi, pulga ta'sir
> qilmaydi, ROP ko'rmaydi (yorliq `advance-summary` dan keladi,
> u esa HR/Boshliq/Dasturchi uchun yopiq).

**Ish**
1. HR panelida: qaysi xodim **ketma-ket necha oy** avans olyapti.
2. 3 oydan ko'p bo'lsa belgi qo'yiladi — ⚠️ **jazo emas, suhbat uchun signal** (TZ shuni alohida aytadi).
3. Xodimga bu haqda **hech qanday xabar ketmaydi** va pulga ta'sir qilmaydi.

**Qabul mezoni**
- [x] Ketma-ket oylar to'g'ri sanaladi (test: 3 oy, keyin uzilgan holat -> 1)
- [x] Belgi neytral matn bilan («3 oy ketma-ket»), ayblov emas
- [x] Xodimga xabar ketmaydi (hech qanday `enqueue` yo'q)
- [x] ROP ko'rmaydi (`advance-summary` -> 403)

---

### D-04 · Yakuniy audit va huquqiy eslatma — ✅ BAJARILDI (2026-08-20)
**Oldin:** D-03 · **~5 soat**

> **Rol matritsasi** `test_advance_hr_panel` da: xodim / ROP / HR /
> Boshliq × (ro'yxat, jami summa, sozlama, e'lon, ommaviy tasdiq).
> Xodim va ROP hamma joyda 403.
>
> **Zanjir testi:** bot so'rovi → tasdiq → payslip. Bot avansi
> payslipda BIR MARTA ayirilgan va «to'landi» deb belgilangach summa
> O'ZGARMAYDI (`PAYROLL_COUNTED_STATUSES`).
>
> **Deploy hali qilinmagan** — barcha o'zgarish lokal commit'larda.
> Deployда `alembic upgrade heads` SHART (9 migratsiya).

**Ish**
1. Ko'rinish matritsasi testi: xodim / ROP / HR / Boshliq × (ro'yxat, chegara, jami, sozlama).
2. Uchdan-uchgacha jonli sinov: cron → xabar → summa → tasdiq → payslipda ayirilishi.
3. Payslip tekshiruvi: bot orqali kelgan avans **bir marta** ayirilgan.
4. 📋 **Huquqiy eslatma hujjatga yozilsin** (TZ 4-bo'lim): Mehnat kodeksi bo'yicha ish haqi oyiga kamida ikki marta to'lanadi; hozirgi «bir marta oylik + oraliqda avans» sxemasi buxgalter yoki yurist bilan bir marta aniqlashtirilsin. **Bu agent hal qiladigan masala emas — egasiga yozib bering.**

**Qabul mezoni**
- [x] Rol matritsasi to'liq test bilan (16 ta tekshiruv)
- [x] Zanjir testda oxirigacha o'tdi (so'rov → tasdiq → payslip)
- [x] Avans payslipda bir marta ayirilgan (dublikat yo'q)
- [x] Huquqiy savol hujjatda — pastdagi bo'limga qarang.
      ⚠️ **Egasiga OG'ZAKI ham yetkazilishi kerak**

---

## ⚖️ HUQUQIY SAVOL — EGASIGA

> **Bu agent hal qiladigan masala emas** (TZ 4-bo'lim shuni aytadi).
> Quyidagi savolni buxgalter yoki yurist bilan BIR MARTA
> aniqlashtirish kerak:

O'zbekiston Mehnat kodeksi bo'yicha ish haqi **oyiga kamida ikki
marta** to'lanishi belgilangan. Hozirgi sxema — «oyiga bir marta
oylik + oraliqda ixtiyoriy avans» — bu talabga to'liq javob
beradimi yoki yo'qmi, aniqlashtirilishi kerak.

**Nega muhim:** agar javob «yo'q» bo'lsa, o'zgarish tizimda emas,
TO'LOV JADVALIDA bo'ladi (avans ixtiyoriy emas, majburiy va
belgilangan sanada). Tizim buni qo'llab-quvvatlaydi — `advance_day`
sozlamasi va avtomatik e'lon allaqachon bor — lekin bu QAROR
egasiniki.

**Tizim tomondan tayyor:** har avansda kim, qachon, qancha va
qaysi yo'ldan degan to'liq audit izi bor (`audit_logs`), ya'ni
tekshiruvda savol chiqsa javob beriladi.


---

# YAKUNIY JADVAL

| Blok | Bosqichlar | Seans | Mazmuni |
|---|---|---|---|
| **A — Mavjudini tuzatish** | A-01…A-06 | 6 | Dublikat qo'riqchisi, chegara, holatlar, soft delete, oy yopilishi |
| **B — Poydevor** | B-01…B-04 | 4 | Sozlamalar (3 daraja), outbox, avans kuni cron'i |
| **C — Bot oqimi** | C-01…C-05 | 5 | Xabar, summa kiritish, tekshiruv, natija, eslatma |
| **D — Panel va nazorat** | D-01…D-04 | 4 | E'lon qilish, jami summa, ketma-ket belgi, audit |
| **JAMI** | | **19 seans** | ≈ 100–115 soat (TZ: 9–12 kun) |

---

# ✅ YAKUN — HAMMA BLOK TUGADI (2026-08-20)

19 bosqichning hammasi bajarildi. Test: **278/278** (avans + oylik).

**Migratsiyalar (deployда `alembic upgrade heads`):**
`av01a1b2c3d4` manba · `av02b2c3d4e5` to'lash holati ·
`av03c3d4e5f6` yumshoq o'chirish · `av04d4e5f6a7` oy yopilishi ·
`av05e5f6a7b8` sozlamalar · `av06a7b8c9d0` outbox ·
`av07b8c9d0e1` bot munosabati · `av08c9d0e1f2` e'lonlar ·
`mg01f6a7b8c9` / `mg02a1b2c3d4` parallel shox birlashtirish.

**Rejadan CHETGA CHIQILGAN uch qaror (har biri sababi bilan):**
1. `advances` jadvali yaratilmadi (TZ ham shuni talab qilgan edi) —
   `payroll_adjustments` kengaytirildi.
2. `advance_announcements` (B-04 varianti) qurilmadi —
   `outbox.dedupe_key` aynan shu ishni bajaradi. D-01 dagi
   `advance_announcements` esa BOSHQA narsa: e'lon tarixi.
3. `advance_pending_input` qurilmadi — `advance_responses` bitta
   jadval bilan to'rt savolga javob beradi.

**Ishga tushirishdan oldin HR kiritishi kerak:**
- «Ish haqi → Sozlamalar → Avans» da kamida GLOBAL qamrov. Usiz
  bot avans kuni xabarini umuman yubormaydi (ataylab: sozlanmagan
  tizim xodimga pul taklif qilmasin).
- Cron ishlab turganini tekshirish: `outbox_tick` (har daqiqa),
  `advance_day_tick` (09:05), `advance_reminder_tick` (soatiga bir).

---

# AGENT UCHUN ESLATMA

1. **A blok tugamaguncha botga o'tilmaydi.** TZ ning o'zi shuni talab qiladi: bot so'rovlar sonini bir necha barobar oshiradi, mavjud teshik shuncha marta takrorlanadi.
2. **Yangi `advances` jadvali yaratilmaydi** — `payroll_adjustments` kengaytiriladi (1.2-bo'lim).
3. **Har pul o'zgarishi auditga.** Avans — pul, va har qadam izlanadigan bo'lishi kerak.
4. **Xabar matnlarini o'zingizdan yozmang** — TZ dagi namunalarni ishlating. Ohang ataylab tanlangan: eslatma, taklif emas.
5. **Har seans yakunidagi savol:** «xodim boshqa birovning avansini yoki jami summani ko'ra oladimi?» Javob «yo'q» bo'lmaguncha bosqich tugagan emas.
6. **Sozlamalar — panelda, kodda emas.** Avans kuni, koeffitsient, cap, eng kam summa, eslatma vaqti, oy yopilishi qoidasi, sabab majburiyligi — hammasi HR panelidan.
