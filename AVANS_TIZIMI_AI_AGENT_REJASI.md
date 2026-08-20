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

### A-01 · Dublikat avans qo'riqchisi (TZ #1)
**Oldin:** — · **~5 soat** · 🔴 **PUL XAVFI**

**Ish**
1. Avval **tasdiqlang**: `requests.py` va `payroll.py` ikkalasi ham `PayrollAdjustment(category='advance')` yozadi (1.1-bo'limga qarang). Yozib qo'ying — keyingi agent qayta tekshirmasin.
2. `payroll_adjustments` ga `source` ustuni: `hr_manual` · `request` · `bot`. Mavjud qatorlarga migratsiyada `hr_manual` (yoki `source_request_id` bo'lsa `request`).
3. **Dublikat qo'riqchisi:** bir xodimga bir davrda **yaqin summa va yaqin sana** bilan ikkinchi avans kiritilsa — saqlashdan oldin ogohlantirish: «Bu xodimda shu oyda allaqachon N ta avans bor: … Baribir kiritilsinmi?». Bloklamaydi, lekin **ko'r-ko'rona o'tkazmaydi**.
4. Ariza orqali kelgan avans HR sahifasida **«ariza orqali»** deb belgilanadi — HR uni qo'lda takrorlamasin.

**Qabul mezoni**
- [ ] `source` har uch qiymat bilan to'g'ri yoziladi
- [ ] Eski qatorlar migratsiyada to'g'ri belgilangan
- [ ] Dublikat ogohlantirishi ishlaydi (test: bir oyda ikki marta)
- [ ] Ariza orqali kelgani ro'yxatda ajralib turadi
- [ ] O'tgan oylar payslip'i **o'zgarmagan**

**Tuzoq:** `source` ni `NOT NULL` qilmang — migratsiya paytida eski qatorlar bor. Default bilan to'ldiring.

---

### A-02 · Chegara formulasi — yadro (TZ #2)
**Oldin:** A-01 · **~6 soat** · 🔴 **PUL XAVFI**

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
- [ ] Formula TZ dagidek, birma-bir test bilan
- [ ] Oyning 5-kunida ishga kirgan xodimda chegara kichik chiqadi
- [ ] Cap koeffitsientdan qat'i nazar oshmaydi
- [ ] Kutilayotgan avans ham ayiriladi (faqat tasdiqlangan emas)
- [ ] Chegara 0 bo'lsa **sababi** qaytariladi («ta'tilda», «to'liq ishlatilgan», …)
- [ ] Test: 8+ ssenariy

**Tuzoq:** Sof oylik hisoblash og'ir — chegara **cron ichida** hisoblanadi va saqlanadi; foydalanuvchi so'rovi uni tayyor holda oladi.

---

### A-03 · Chegarani kiritish nuqtalariga ulash (TZ #2)
**Oldin:** A-02 · **~5 soat**

**Ish**
1. HR qo'lda kiritishida chegara tekshiruvi: oshsa **400** + tushunarli xabar («ruxsat etilgan: 1 240 000»).
2. Ariza orqali avansda ham shu tekshiruv.
3. **Chetlab o'tish huquqi:** Boshliq/Dasturchi chegaradan oshiq kirita olsin, lekin **sabab majburiy** va auditga yoziladi (istisno bo'lishi mumkin, lekin izsiz emas).
4. Formada chegara **oldindan ko'rsatiladi** — HR kiritishdan oldin biladi.

**Qabul mezoni**
- [ ] Chegaradan oshiq oddiy yo'l bilan kiritib bo'lmaydi
- [ ] Boshliq istisno qila oladi, sabab bilan va auditda
- [ ] Xodim tanlanganda chegara darhol ko'rinadi
- [ ] Test: chegara ichida / chegaradan oshiq / istisno

---

### A-04 · «Kiritildi» va «berildi» ni ajratish (TZ #3, #4)
**Oldin:** A-01 · **~5 soat**

**Ish**
1. TZ #4: hozir «berilgan sana» kiritiladi, tasdiq keyin so'raladi — boshliq rad etsa **pul allaqachon qo'lda**.
   Yechim: `issued_on` faqat **tasdiqlangandan keyin** to'ldiriladi. Kiritishda u so'ralmaydi.
   Holatlar: `pending` → `approved` → `issued` (yoki `rejected`).
2. `issued` uchun alohida amal: «To'lab berildi» (kassa) — kim va qachon belgiladi.
3. TZ #3: xodim bo'yicha **oylik jami** ko'rsatilsin (bittalab qator emas, yuqorida yig'indi).

**Qabul mezoni**
- [ ] Tasdiqlanmagan avansga `issued_on` yozib bo'lmaydi
- [ ] `issued` holati alohida va kim belgilagani ko'rinadi
- [ ] Xodim bo'yicha oylik jami ro'yxatda bor
- [ ] Payslipga faqat `approved`/`issued` kiradi (hozirgi qoida buzilmasin)
- [ ] Test: holat zanjiri + noto'g'ri o'tishlar 400

**Tuzoq:** Mavjud yozuvlar `approved` va `issued_on` to'ldirilgan — migratsiyada ularni `issued` qiling, aks holda «to'lanmagan» bo'lib ko'rinadi.

---

### A-05 · Yumshoq o'chirish, audit va sabab maydoni (TZ #7, #8)
**Oldin:** A-01 · **~4 soat**

**Ish**
1. `payroll_adjustments.deleted_at` qo'shiladi. **Barcha o'qish** `deleted_at IS NULL` bilan filtrlanadi — ayniqsa `build_payslip`.
2. Kim o'chira oladi: HR (tasdiqlanmaganini), Boshliq/Dasturchi (hammasini). Har o'chirish `AuditLog` ga.
3. TZ #8 «sabab»: bo'sh yoki «avans» kabi ma'nosiz matn qabul qilinmasin. Ikki variant — **sozlamada tanlanadi**: (a) sabab majburiy va kamida N belgi, (b) umuman so'ralmaydi. Default: **(b) so'ralmaydi** (bot oqimida xodim sabab yozmaydi, majburiy qilsak oqim buziladi).

**Qabul mezoni**
- [ ] O'chirilgan avans payslipga **kirmaydi** (test bilan)
- [ ] Har o'chirish auditda: kim, qachon, qaysi summa
- [ ] Sabab qoidasi panelda sozlanadi
- [ ] Xodim o'chira olmaydi

---

### A-06 · Oy yopilishi qoidasi va xodim ko'rinishi (TZ #5, #6)
**Oldin:** A-04 · **~5 soat**

**Ish**
1. TZ #5: davr yopilganda (`payroll_periods.locked`) hali `pending` bo'lgan avans nima bo'ladi — **sozlamada**: (a) keyingi davrga o'tadi, (b) avtomatik bekor bo'ladi. Default: **(a) o'tadi** (pul so'ragan odam javobsiz qolmasin).
2. Yopish oldidan HR ga ogohlantirish: «3 ta avans hali tasdiqlanmagan».
3. TZ #6: xodim **botda** ham o'z avansini ko'rsin — «💵 Mening avanslarim»: shu oydagi so'rovlar, holati, jami va **qolgan chegara**. Kabinetda payslipda allaqachon ko'rinadi (tekshirilgan).

**Qabul mezoni**
- [ ] Yopilganda pending avans sozlamaga muvofiq ishlanadi
- [ ] HR ogohlantirish oladi
- [ ] Xodim botdan o'z avansini va qolgan chegarasini ko'radi
- [ ] Boshqa xodimniki ko'rinmaydi (404)

---

**✅ A BLOK YAKUNI:** mavjud modul pul xatosi bermaydigan holatga keldi. Endi bot qo'shish xavfsiz.

---

# B BLOK — SOZLAMA VA XABAR POYDEVORI

---

### B-01 · `advance_settings` — uch darajali qamrov
**Oldin:** A-06 · **~5 soat**

**Ish**
1. `advance_settings`: `scope` (global/position/user), `scope_id`, `advance_day` (20), `coefficient` (0.5), `cap_percent` (50), `min_amount`, `reminder_time` (14:00), `pending_on_close` (carry/cancel), `reason_required`, `is_active`, `effective_from`.
2. `resolve_advance_settings(user)` — **xodim > lavozim > global**, faqat `is_active`. Mavjud `payroll.resolve_policy` naqshi bilan **aynan bir xil** yozilsin.
3. Hech qanday sozlama bo'lmasa — **avans so'rovi umuman yuborilmaydi** (sozlanmagan holat xavfsiz tomonga).

**Qabul mezoni**
- [ ] Uch daraja to'g'ri ishlaydi (test: har daraja + bo'shliq)
- [ ] Sozlamasiz tizim jim turadi
- [ ] «Sozlanmagan modullar» blokiga qator qo'shildi

---

### B-02 · Sozlamalar paneli (HR)
**Oldin:** B-01 · **~4 soat**

**Ish**
1. `/payroll/settings` ga «Avans» bo'limi: TZ jadvalidagi beshta qiymat + qamrov tanlash.
2. Har maydon ostida bir qatorlik izoh (TZ dagi «Izoh» ustuni).
3. Kim o'zgartiradi: HR/Boshliq/Dasturchi. Har o'zgarish auditga.

**Qabul mezoni**
- [ ] Beshta qiymat ham panelda
- [ ] Lavozimga alohida chegara qo'yish ishlaydi
- [ ] O'zgarish auditda ko'rinadi

---

### B-03 · Outbox — xabar navbati
**Oldin:** B-01 · **~6 soat** · ⭐ **Boshqa modullar ham ishlatadi**

**Ish**
1. `outbox`: `id`, `chat_id`, `kind`, `payload` (JSON), `status` (kutmoqda/yuborildi/xato), `attempts`, `last_error`, `scheduled_at`, `sent_at`.
2. `cron_jobs.outbox_tick` — navbatdan N tani oladi va yuboradi. **3 urinishdan keyin to'xtaydi** va HR ga xabar beradi.
3. Telegram rate-limit: tick'da yuboriladigan xabar soni cheklangan (masalan 20), qolgani keyingi tick'da.
4. ⚠️ Xabar **so'rov ichida yuborilmaydi** — hamma joyda outbox orqali.

**Qabul mezoni**
- [ ] Xabar navbatga qo'yiladi va cron yuboradi
- [ ] 3 urinishdan keyin `xato` va HR ga xabar
- [ ] Bir xabar ikki marta yuborilmaydi (parallel tick testi)
- [ ] Rate-limit hisobga olingan

**Tuzoq:** Cron har daqiqada yangi jarayon — navbat faqat bazada. Lock yoki `status='running'` bilan ikki jarayon bitta xabarni olmasin.

---

### B-04 · Avans kuni cron'i va takroriylik qo'riqchisi
**Oldin:** B-03, A-02 · **~5 soat**

**Ish**
1. `cron_jobs.advance_day_tick`: bugun avans kunimi (`>=` semantikasi — TZ talabi, `==` emas).
2. `advance_announcements` (yoki `advance_month_state`): davr (yil, oy), `sent_at` — **har oy bir marta** qo'riqchisi.
3. Har faol xodim uchun chegara hisoblanadi (**cron ichida**, og'ir so'rov) va outboxga qo'yiladi.
4. **Kimga yuborilmaydi** (TZ ro'yxati): ishdan bo'shash arizasi bergan · ta'tilda (chegara 0) · chegarasi `min_amount` dan past · shu oyda chegarani to'liq ishlatgan.

**Qabul mezoni**
- [ ] Cron kechiksa ham xabar tushadi (`>=`)
- [ ] Bir oyda ikki marta yuborilmaydi
- [ ] To'rt istisno ham ishlaydi (har biriga test)
- [ ] Chegara xabar bilan birga saqlanadi (keyin tekshirishda ishlatiladi)

---

# C BLOK — BOT OQIMI

---

### C-01 · Avans kuni xabari
**Oldin:** B-04 · **~5 soat**

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
- [ ] Xabarda foiz **yo'q**, aniq summa bor
- [ ] «Kerak emas» javobi yoziladi
- [ ] O'tgan oyning xabari bosilsa «bu xabar eskirgan» deydi
- [ ] Matn taklif emas, eslatma ohangida (ko'rib chiqilgan)

---

### C-02 · Summa kiritish — holat bazada
**Oldin:** C-01 · **~5 soat**

**Ish**
1. «Summa kiritish» bosilganda holat **bazaga** yoziladi (`advance_pending_input`: user_id, davr, chegara, `expires_at`) — **FSM da emas** (Passenger o'chadi).
2. Keyingi matn xabari summa deb qabul qilinadi. Raqam bo'lmasa — tushunarli xato.
3. Holat muddati (masalan 2 soat) o'tsa bekor bo'ladi.
4. ⚠️ Bot matn handlerlari tartibi nozik (anketa modulida uchragan tuzoq) — yangi handler boshqa oqimlarni **yutib yubormasin**.

**Qabul mezoni**
- [ ] Bot restartdan keyin ham kutish holati saqlanadi
- [ ] Raqam bo'lmagan matn boshqa handlerga xalaqit bermaydi
- [ ] Muddat o'tsa holat bekor bo'ladi
- [ ] Test: restart simulyatsiyasi (holat bazadan o'qiladi)

---

### C-03 · Chegara tekshiruvi va rad javobi
**Oldin:** C-02, A-02 · **~4 soat**

**Ish**
1. Kiritilgan summa chegaradan oshsa — **qabul qilinmaydi**, ruxsat etilgan summa qayta ko'rsatiladi va qayta kiritish taklif qilinadi.
2. `min_amount` dan kichik bo'lsa ham rad etiladi (mayda so'rovlar).
3. Chegara **xabar yuborilgan paytdagi** emas, **kiritilgan paytdagi** holatdan qayta hisoblanadi (oraliqda boshqa avans tasdiqlangan bo'lishi mumkin).

**Qabul mezoni**
- [ ] Oshiq summa rad etiladi, aniq raqam ko'rsatiladi
- [ ] Eng kam summadan past rad etiladi
- [ ] Chegara qayta hisoblanadi (eski qiymatga ishonilmaydi)
- [ ] Test: oraliqda chegara kamaygan holat

---

### C-04 · So'rov panelga tushishi va natija xabari
**Oldin:** C-03 · **~5 soat**

**Ish**
1. Qabul qilingan summa `PayrollAdjustment(category='advance', source='bot', status='pending')` bo'lib yoziladi — **mavjud ro'yxatga** tushadi, yangi jadval yo'q.
2. HR/Boshliqqa xabar (outbox orqali).
3. Boshliq tasdiqlasa/rad etsa — xodimga natija xabari: tasdiqlandi (summa) yoki rad etildi (**sabab bilan**).
4. Rad sababi maydoni (`decided_note` mavjud) — xabarda ko'rsatiladi.

**Qabul mezoni**
- [ ] Bot so'rovi mavjud avans ro'yxatida `source='bot'` bilan ko'rinadi
- [ ] Tasdiq/rad natijasi xodimga boradi
- [ ] Rad sababi xabarda bor
- [ ] Xabarlar outbox orqali (so'rov ichida emas)

---

### C-05 · Takroriy eslatma va to'xtash
**Oldin:** C-04 · **~4 soat**

**Ish**
1. Sozlamadagi vaqtda (default 14:00) javob bermaganlarga **bitta** takroriy eslatma.
2. Shundan keyin **to'xtaydi** — kun davomida cheksiz eslatma yo'q.
3. «Kerak emas» bosgan yoki summa kiritganlarga eslatma **ketmaydi**.

**Qabul mezoni**
- [ ] Bir kunda ko'pi bilan 2 xabar (asosiy + 1 eslatma)
- [ ] Javob berganlarga eslatma ketmaydi
- [ ] Test: javob bergan / bermagan / kech javob bergan

---

# D BLOK — HR PANELI VA NAZORAT

---

### D-01 · «Avans kunini e'lon qilish» (TZ 3-bo'lim)
**Oldin:** B-04 · **~5 soat**

**Ish**
1. HR panelida tugma: sana tanlanadi + ixtiyoriy matn → barcha xodimga xabar (outbox).
2. ⚠️ **Qo'lda e'lon qilingan oyda avtomatik 20-kunlik xabar YUBORILMAYDI** — aks holda xodim ikki marta xabar oladi.
3. Kechiktirilsa xabar aniq aytsin: «Avans kuni 23-avgustga ko'chirildi».
4. `advance_announcements`: davr, sana, matn, yuborgan_id, yuborilgan_vaqt.

**Qabul mezoni**
- [ ] E'lon qilingan oyda avtomatik xabar **ketmaydi** (test bilan)
- [ ] Ko'chirilgan sana xabarda aniq
- [ ] E'lon tarixi saqlanadi
- [ ] Ikki marta e'lon qilinsa oxirgisi kuchda

---

### D-02 · Boshliq ekrani: kunlik jami summa (TZ 4-bo'lim)
**Oldin:** C-04 · **~4 soat**

**Ish**
1. Tasdiqlash ekranida yuqorida: «Bugun 9 xodim jami 11 400 000 so'm so'radi».
2. Tanlab tasdiqlash: bir nechta so'rovni belgilab, jami ko'rib, birdan tasdiqlash.
3. Tasdiqlanganlar jami alohida ko'rinadi (kassa uchun).

**Qabul mezoni**
- [ ] Jami summa tasdiqlashdan **oldin** ko'rinadi
- [ ] Ommaviy tasdiqlash ishlaydi va har biri auditga tushadi
- [ ] Xodim bu ekranni ko'rmaydi, ROP ham

---

### D-03 · Ketma-ket avans belgisi (TZ 4-bo'lim)
**Oldin:** D-02 · **~4 soat**

**Ish**
1. HR panelida: qaysi xodim **ketma-ket necha oy** avans olyapti.
2. 3 oydan ko'p bo'lsa belgi qo'yiladi — ⚠️ **jazo emas, suhbat uchun signal** (TZ shuni alohida aytadi).
3. Xodimga bu haqda **hech qanday xabar ketmaydi** va pulga ta'sir qilmaydi.

**Qabul mezoni**
- [ ] Ketma-ket oylar to'g'ri sanaladi (oraliq uzilsa qaytadan boshlanadi)
- [ ] Belgi neytral matn bilan («3 oy ketma-ket»), ayblov emas
- [ ] Xodimga xabar ketmaydi
- [ ] ROP ko'rmaydi

---

### D-04 · Yakuniy audit, deploy va huquqiy eslatma
**Oldin:** D-03 · **~5 soat**

**Ish**
1. Ko'rinish matritsasi testi: xodim / ROP / HR / Boshliq × (ro'yxat, chegara, jami, sozlama).
2. Uchdan-uchgacha jonli sinov: cron → xabar → summa → tasdiq → payslipda ayirilishi.
3. Payslip tekshiruvi: bot orqali kelgan avans **bir marta** ayirilgan.
4. 📋 **Huquqiy eslatma hujjatga yozilsin** (TZ 4-bo'lim): Mehnat kodeksi bo'yicha ish haqi oyiga kamida ikki marta to'lanadi; hozirgi «bir marta oylik + oraliqda avans» sxemasi buxgalter yoki yurist bilan bir marta aniqlashtirilsin. **Bu agent hal qiladigan masala emas — egasiga yozib bering.**

**Qabul mezoni**
- [ ] Rol matritsasi to'liq test bilan
- [ ] Jonli zanjir bir marta oxirigacha o'tdi
- [ ] Avans payslipda bir marta ayirilgan (dublikat yo'q)
- [ ] Huquqiy savol hujjatda va egasiga yetkazilgan

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

# AGENT UCHUN ESLATMA

1. **A blok tugamaguncha botga o'tilmaydi.** TZ ning o'zi shuni talab qiladi: bot so'rovlar sonini bir necha barobar oshiradi, mavjud teshik shuncha marta takrorlanadi.
2. **Yangi `advances` jadvali yaratilmaydi** — `payroll_adjustments` kengaytiriladi (1.2-bo'lim).
3. **Har pul o'zgarishi auditga.** Avans — pul, va har qadam izlanadigan bo'lishi kerak.
4. **Xabar matnlarini o'zingizdan yozmang** — TZ dagi namunalarni ishlating. Ohang ataylab tanlangan: eslatma, taklif emas.
5. **Har seans yakunidagi savol:** «xodim boshqa birovning avansini yoki jami summani ko'ra oladimi?» Javob «yo'q» bo'lmaguncha bosqich tugagan emas.
6. **Sozlamalar — panelda, kodda emas.** Avans kuni, koeffitsient, cap, eng kam summa, eslatma vaqti, oy yopilishi qoidasi, sabab majburiyligi — hammasi HR panelidan.
