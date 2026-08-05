# DAVOMAT BO'LIMI — UX QAYTA QURISH TOPSHIRIG'I

> **Maqsad:** davomat bo'limini "ishlaydigan, lekin noqulay"dan "har kuni ishlatiladigan,
> tez va tushunarli" holatga keltirish. Bu hujjat joriy kodni chuqur o'rganish
> (2026-08-05) natijasi: har muammo aniq fayl/qator bilan, har yechim aniq
> spetsifikatsiya va qabul mezoni bilan yozilgan.
>
> **Ish tartibi:** bosqichlar tartib bilan bajariladi (A → G). Har bosqich = alohida
> commit. Har bosqichdan keyin: `test.py` (119/119 saqlanishi SHART) + `cd web && npx
> tsc --noEmit` + qo'lda tekshiruv. Mavjud endpointlar BUZILMAYDI — faqat yangilari
> qo'shiladi yoki javobga yangi maydonlar kiradi (eski frontend versiyalari ishlashda
> davom etadi).

---

## 0. DIZAYN TAMOYILLARI (hamma bosqichga tegishli)

1. **Rol o'z ekranini ko'radi.** Xodim — telefonda, bitta qo'l bilan: bugungi holat +
   o'z tarixi. Rahbar — desktopda: jonli nazorat, oylik jadval, hisobot. HR — tuzatish
   va payroll-tayyorlik. Bitta sahifaga hammasini uyish — hozirgi asosiy xato.
2. **Savolga bir qarashda javob.** Har ekran bitta asosiy savolga javob beradi:
   - Xodim: *"Bugun holatim qanday? Shu oyda qancha kechikdim?"*
   - Rahbar (ertalab): *"Kim kelmadi?"* — ISMLAR bilan, son bilan emas.
   - HR (oy oxiri): *"Oy jadvali qanday, qaysi kunlar tuzatish kerak?"*
3. **Oylik matritsa — HR ning asosiy quroli.** Qatorlar = xodimlar, ustunlar = kunlar.
   Bu klassik davomat jadvali; hozirgi 300-qatorlik flat ro'yxat uni almashtira olmaydi.
4. **Davr boshqaruvi yagona.** Hozir bitta sahifada uch xil davr bor (jadval — date
   range, summary — qotirilgan 30 kun, late-stats — o'z 7/30/90 tugmalari). Har tab
   bitta davr boshqaruviga ega bo'ladi va u tab ichidagi HAMMA bo'limga ta'sir qiladi.
5. **Bosiladigan narsa — chuqurlashadi.** Xodim ismi → o'sha xodim paneli. Matritsa
   katagi → kun tafsiloti + tahrirlash. Hozir hech narsa bosilmaydi.
6. **Og'ir kutubxona faqat kerak joyda.** Xarita (leaflet) faqat Offices chunk'ida;
   face-api allaqachon lazy — shu intizom saqlanadi.
7. **Mavjud naqshlar qayta ishlatiladi.** `EditAttendanceDialog`, `StatusBadge`,
   `DataTable`, `PeriodPicker`, Sheet/Popover (shadcn) — yangi "dizayn tizimi"
   O'YLAB TOPILMAYDI.

---

## 1. JORIY HOLAT AUDITI (aniq muammolar)

### 1.1 Rahbar sahifasi — `web/src/pages/Attendance.tsx` (824 qator)

Bitta cheksiz vertikal skrollda **8 ta bo'lim**: stat kartalar (8 ta) → dam
olishdagilar → "Hozir ofisda"+"Bugungi harakatlar" → Ma'lumot tayyorligi →
Kechikish statistikasi → 30 kunlik xulosa jadvali → Yozuvlar jadvali → Joylashuv
ruxsati kartasi.

| # | Muammo | Oqibat |
|---|---|---|
| M1 | Jonli nazorat (bugun) + tarixiy tahlil (30/90 kun) + payroll-tayyorlik + admin sozlama BITTA sahifada | Har kirishda 8 ta so'rov; kerakli bo'limgacha 3-4 ekran skroll |
| M2 | "Kelmagan: 2" — faqat SON. Kim kelmagani ko'rinmaydi (backend `not_checked_in` ismlarni qaytarmaydi) | Rahbar ertalabki asosiy savoliga javob ololmaydi; digest kutadi yoki taxmin qiladi |
| M3 | "Yozuvlar" — flat ro'yxat (sana ↓). 10 xodim × 30 kun = 300 qator | Oylik manzarani ko'rib bo'lmaydi; bitta xodimni kuzatish uchun qidiruvga ism yozish kerak |
| M4 | Uch bo'limda uch xil davr (M4≠M5≠M6 davrlari) | "30 kunlik jadvalda kechikish 130 daq, kechikish bo'limida 90 daq" — chalkashlik |
| M5 | Xodim ismi hech qayerda bosilmaydi; `EmployeeProfile.tsx`da davomat BO'LIMI UMUMAN YO'Q | "Shu xodim bilan gaplashaman, tarixini ko'rsat" — yo'l yo'q |
| M6 | `StatusBadge`da `excused` holati YO'Q (5.1-band qo'shgan yangi status) | Sababli kun jadvalda xom `excused` matni bilan kulrang chiqadi |
| M7 | "Yozuv qo'shish" jadval pastida yashiringan; LocationExemptCard eng pastda | Muhim amallar topilmaydi |
| M8 | Auto-refresh faqat dashboard so'roviga; qolgan bo'limlar "Yangilash" tugmasiga qaram | Yarim sahifa jonli, yarmi qotgan |

### 1.2 Xodim tomoni — `web/src/pages/CheckIn.tsx`

| # | Muammo | Oqibat |
|---|---|---|
| X1 | Xodim O'Z TARIXINI ko'ra olmaydi — na kalendar, na oylik jami (backendda ham `/attendance/me/history` yo'q, `/me/today` xolos) | "Shu oy nechi marta kechikdim? Qaysi kunlar?" — javob faqat rahbarda yoki jarima kelganda |
| X2 | Bugungi ish jadvali ko'rinmaydi ("bugun soat nechada kelishim kerak?") — u alohida `/me/schedule` tabda | Kechikish "kutilmagan" bo'lib tuyuladi; ayniqsa override kunlarda |
| X3 | Check-in oqimi 3 bosqich (GPS ruxsati → yuz → yuborish), lekin modal ichida qadam ko'rsatkichi yo'q — faqat almashib turadigan matn | Model yuklanishida (~10s) xodim "qotib qoldimi?" deb o'ylaydi |
| X4 | Kelmagan/dam kunda sahifa jim: ikkala karta "—" | "Bugun dam kunimmi yoki tizim buzuqmi?" — farqsiz |

### 1.3 Ish jadvali — `web/src/pages/WorkSchedule.tsx`

| # | Muammo | Oqibat |
|---|---|---|
| J1 | Faqat BITTA xodim rejimi (dropdown). Umumiy ko'rinish yo'q | "Hammaning jadvali to'g'rimi?" — 10 xodim uchun 10 marta tanlash |
| J2 | Nusxalash yo'q | Yangi xodimga jadval berish = qo'lda qayta terish |
| J3 | Override ro'yxati filtrsiz, hamma davr uchun | Vaqt o'tishi bilan cheksiz ro'yxat |
| J4 | Kim jadvalsiz (default bilan ishlayotgan) — ko'rinmaydi (faqat readiness'da) | Jarima "taxminiy jadval" ustiga hisoblanadi, rahbar buni sezmaydi |

### 1.4 Ofislar — `web/src/pages/Offices.tsx`

| # | Muammo | Oqibat |
|---|---|---|
| O1 | Lat/lng QO'LDA raqam bilan kiritiladi, xarita yo'q | Koordinata xatosi (masalan lat/lng almashib ketishi) faqat xodim check-in qila olmaganda bilinadi |
| O2 | Radius vizual emas (raqam xolos) | "150 m yetadimi?" — tasavvur qilib bo'lmaydi |

### 1.5 Backend qulaylik bo'shliqlari — `api/routers/attendance.py`

| # | Muammo |
|---|---|
| B1 | `/attendance/dashboard` — `not_checked_in` faqat son; kelmaganlar ISMLARI va jadval boshlanish vaqti yo'q; "ketganlar" ro'yxati ham yo'q |
| B2 | Oylik matritsa endpointi yo'q (xodim×kun to'r); frontend buni o'zi qursa jadval/sababli kun/dam kunlarni bilmaydi (yozuvsiz kun ≠ kelmagan) |
| B3 | Xodim uchun `/attendance/me/history` yo'q — `GET /attendance` faqat rahbar/`can_edit_attendance` uchun |
| B4 | `employee-summary` va `late-stats` faqat `days` oynasi — "o'tgan oy" (kalendar oy) so'rab bo'lmaydi |
| B5 | Rahbar "kelmagan xodimga eslatma yuborish" imkoni yo'q (bot digest kutiladi) |
| B6 | Yuzni qayta ro'yxatdan o'tkazish so'rovlari webda KO'RINMAYDI (GET /face-reregistration bor, decide faqat bot-secret) — HR botni o'tkazib yuborsa so'rov osilib qoladi |
| B7 | `GET /work-schedule/{tg}/all/week` faqat bot-secret — web umumiy jadval ko'rinishi uchun JWT varianti yo'q |

---

## 2. YANGI STRUKTURA (informatsion arxitektura)

```
RAHBAR (desktop, sidebar):
  /attendance  ──  TABLAR (URL bilan sinxron: ?tab=)
      ├── "Bugun"        ← jonli nazorat (default)
      ├── "Oylik jadval" ← matritsa + tayyorlik banneri  (HR ning asosiy quroli)
      ├── "Hisobot"      ← summary + late-stats (YAGONA davr bilan) + eksport
      └── "Sozlamalar"   ← LocationExempt + Yuz qayta ro'yxat so'rovlari
  /work-schedule ── "Umumiy jadval" (default) + "Bitta xodim" (hozirgi UI)
  /offices       ── xarita + forma
  /employees/:id ── YANGI "Davomat" bo'limi (oylik kalendar + statlar)

XODIM (telefon, tab-bar) — /check-in bitta sahifa bo'lib qoladi:
  [Bugungi jadval chipi]  ← "Bugun: 09:00–18:00" / "Bugun dam olasiz 🌙"
  [Bugungi davomat kartasi + Keldim/Ketdim]   (hozirgi)
  [Kechikish limiti kartasi]                  (hozirgi)
  [📅 Oylik davomatim — kalendar + jami]      ← YANGI
```

Sahifa fayllari bo'linadi (824-qatorlik fayl saqlanmaydi):
```
web/src/pages/Attendance.tsx            — faqat tab konteyner (~80 qator)
web/src/components/attendance/
    TodayTab.tsx        MatrixTab.tsx        ReportTab.tsx
    SettingsTab.tsx     EmployeeDrawer.tsx   EditAttendanceDialog.tsx (ko'chiriladi)
    MonthCalendar.tsx   (xodim va rahbar ikkalasiga — bitta komponent)
```

---

## 🅰 BOSQICH A — Backend API qulayliklari

Hammasi QO'SHIMCHA (mavjudini buzmaydi). Har endpoint uchun test.py'ga tekshiruv.

### A1. Dashboard: kelmaganlar va ketganlar ISMLAR bilan (B1, M2)

`GET /attendance/dashboard` javobiga qo'shiladi (summary o'zgarmaydi):
```jsonc
"not_come": [   // bugun ishlashi kerak-u, hali check-in qilmaganlar
  {"user_id": 5, "full_name": "Albina", "schedule_start": "09:00",
   "telegram_linked": true}   // eslatma tugmasini ko'rsatish uchun
],
"left": [       // bugun kelib, allaqachon ketganlar
  {"user_id": 7, "full_name": "Hayot", "check_in_time": "...", "check_out_time": "...",
   "worked_minutes": 480}
]
```
`not_come` hisobi dashborddagi mavjud `_works_today` lug'atlaridan chiqadi (yangi
so'rov shart emas); tasdiqlangan sababli kunlilar `not_come`ga KIRMAYDI (ular
alohida `excused_today: [{user_id, full_name}]` ro'yxatida).

### A2. Oylik matritsa (B2, M3) — YANGI endpoint

```
GET /attendance/matrix?month=YYYY-MM        (_require_manager)
```
Javob:
```jsonc
{
  "month": "2026-08", "today": "2026-08-05",
  "days": ["2026-08-01", ...],                       // oyning hamma kuni
  "employees": [{
    "user_id": 5, "full_name": "Albina",
    "cells": [{
      "date": "2026-08-01",
      // present | late | absent | weekend | excused | pending | future
      "status": "late",
      "late_minutes": 12, "check_in": "09:17", "check_out": "18:03",
      "worked_minutes": 470,
      "flags": ["auto_closed"?, "manual"?, "no_checkout"?]   // burchak belgilari
    }, ...],
    "totals": {"present_days": 18, "late_count": 3, "late_minutes": 47,
               "absent_days": 1, "excused_days": 1, "worked_hours": 142.5}
  }]
}
```
**Katak statusi qoidasi** (yozuv + jadval birlashmasi):
1. Yozuv bor → yozuv statusi (`present/late/absent/weekend/excused`); vaqtlar
   mahalliy "HH:MM" ga aylantirib beriladi (frontend TZ hisoblamasin).
2. Yozuv yo'q, sana > bugun → `future` (jadval bo'yicha dam bo'lsa `weekend`).
3. Yozuv yo'q, sana == bugun, ish kuni → `pending` (kun hali tugamagan).
4. Yozuv yo'q, o'tgan ish kuni → `absent` (virtual — kechki yozish o'tkazib
   yuborgan bo'lishi mumkin); tasdiqlangan sababli kun bo'lsa → `excused`.
5. Yozuv yo'q, dam kuni → `weekend`.

Samaradorlik: butun oy uchun 5 ta bulk so'rov (users, attendance oy bo'yicha,
overrides oy bo'yicha, weekly hammasi, excused approved oy bo'yicha) — xodim boshiga
N+1 QILINMAYDI (3.5-band saboqlari). `flags.auto_closed` — `note`da
`AUTO_CLOSED_MARK` borligi; `manual` — audit emas, `check_in_distance_m IS NULL AND
check_in IS NOT NULL` (qo'lda tuzatish GPS'ni tozalaydi — mavjud xatti-harakat).

### A3. Xodimning o'z tarixi (B3, X1) — YANGI endpoint

```
GET /attendance/me/history?month=YYYY-MM      (get_current_user — HAR KIM O'ZINIKI)
```
Javob — matritsaning bitta qatori + limit kartasi ma'lumoti:
```jsonc
{ "month": "...", "days": [ /* A2 dagi cell formati + schedule_start/end */ ],
  "totals": { ...A2 totals... } }
```
A2 bilan BITTA yordamchi funksiya (`build_month_cells(db, user, month)`) — ikki
endpoint bitta hisoblash manbaidan foydalanadi, ikki nusxa mantiq YO'Q.

### A4. Davr parametrlari (B4, M4)

`employee-summary` va `late-stats`ga ixtiyoriy `date_from`/`date_to` qo'shiladi
(berilsa `days` e'tiborga olinmaydi; berilmasa hozirgidek). Frontend "Hisobot"
tabida oy/7/30/90 tanlovini IKKALASIGA bitta joydan uzatadi.

### A5. Kelmaganga eslatma (B5) — YANGI endpoint

```
POST /attendance/remind/{user_id}     (_require_manager)
```
Xodimning telegram_id'siga bot orqali: "⏰ Siz hali «Keldim» qilmadingiz. Jadvalingiz:
09:00. Sabab bo'lsa botdan «Sababli kun so'rash»ni bosing." Kuniga bir xodimga ko'pi
bilan 2 ta (spam himoya — oddiy in-day tekshiruv AuditLog yoki alohida jadvalsiz:
`Attendance.note`ga TEGMAYMIZ, `AiMessageLog` naqshidagi mavjud jadvaldan foydalanish
shart emas — eng soddasi: `AuditLog(action="attendance_reminder_sent")` yozuvini
sanash). Javob: `{"sent": true}` yoki 429 "Bugun allaqachon 2 marta eslatilgan".

### A6. Yuz so'rovlari webdan hal qilinadi (B6)

```
POST /attendance/face-reregistration/{id}/decide-web    (JWT, hr/boss/dasturchi)
```
Mavjud bot-secret endpointdagi mantiq YAGONA servis funksiyaga chiqariladi
(`decide_face_rereg(db, item_id, decider, decision)`), ikkala endpoint uni chaqiradi.

### A7. Umumiy jadval JWT bilan (B7)

```
GET /work-schedule/all/week?start=YYYY-MM-DD    (_require_manager)
```
Mavjud `_build_week` + bulk so'rovlar AYNAN qayta ishlatiladi (bot varianti bilan
bitta ichki funksiya).

**🅰 qabul mezonlari:**
- [ ] test.py: matrix (status qoidasi 5 holati), me/history (xodim FAQAT o'zinikini
      oladi), remind (403 oddiy xodimga, 429 3-chaqiruvda), dashboard not_come
      ismlari, date_from/date_to filtrlari — kamida 12 yangi tekshiruv
- [ ] Mavjud 119 tekshiruv o'zgarishsiz o'tadi

---

## 🅱 BOSQICH B — Rahbar sahifasi: tablar

`Attendance.tsx` konteynerga aylanadi: shadcn `Tabs`, faol tab URL bilan sinxron
(`useSearchParams`, `?tab=bugun|jadval|hisobot|sozlamalar`; default `bugun`).
Mavjud bo'limlar tablarga KO'CHIRILADI (hali qayta dizaynsiz — bu bosqich faqat
strukturani tuzatadi, komponentlar `components/attendance/` ga bo'linadi):

- **Bugun:** stat kartalar + dam olishdagilar + ofisda/harakatlar. Auto-refresh shu
  tabda qoladi; boshqa tabda dashboard so'rovi TO'XTAYDI (`enabled: tab==="bugun"` —
  bekor so'rovlar ketmaydi).
- **Oylik jadval:** hozircha "Yozuvlar" jadvali + Readiness + "Yozuv qo'shish"
  (C bosqichda matritsa bilan almashadi).
- **Hisobot:** LateStatsSection + summary jadvali.
- **Sozlamalar:** LocationExemptCard + (A6 dan keyin) yuz so'rovlari kartasi:
  pending ro'yxat + Tasdiqlash/Rad tugmalari.

Qo'shimcha shu bosqichda (kichik, lekin muhim):
- `StatusBadge`: `excused: {text: "Sababli", cls: "bg-sky-100 text-sky-700"}` (M6).
- "Bugun" stat kartalari 8 tadan 5 taga tushadi: **Keldi X/Y** (progress sifatida),
  **Kechikdi**, **Hozir ofisda**, **Kelmagan**, **Dam olishda**. "Oy: ishlangan soat"
  Hisobot tabiga; "Ketdi" alohida karta emas — quyidagi ro'yxatda.
- "Bugun" tabida `not_come` ISMLI ro'yxat (A1) uchta ustunli tartibda:
  **Kelmagan (N)** [har birida jadval vaqti + "Eslatish" tugmasi (A5) + agar
  excused bo'lsa "Sababli" badge] · **Ofisda (N)** · **Ketdi (N)**.
  Pastda "Bugungi harakatlar" lentasi qoladi.

**🅱 qabul mezonlari:**
- [ ] Tab almashganda URL o'zgaradi; sahifa yangilansa tab saqlanadi
- [ ] "Bugun" tabidan chiqilganda dashboard auto-refresh so'rovlari to'xtaydi
      (Network'da tekshiriladi)
- [ ] "Kelmagan" ro'yxatida ism + jadval vaqti + Eslatish tugmasi ishlaydi
- [ ] `excused` yozuvi "Sababli" (sky) badge bilan ko'rinadi
- [ ] tsc toza; Attendance.tsx < 150 qator

---

## 🅲 BOSQICH C — Oylik matritsa (asosiy yangi komponent)

`MatrixTab.tsx` — "Oylik jadval" tabining yangi mazmuni ("Yozuvlar" flat jadvali
matritsa OSTIDA yig'iladigan bo'limga tushadi — kerak bo'lganda ochiladi).

### Ko'rinish spetsifikatsiyasi

```
‹  Avgust 2026  ›                    [Legend: ●Keldi ●Kechikdi ●Kelmadi ●Sababli ●Dam]
┌──────────────┬──┬──┬──┬──┬──┬───────────────────┬──────┬─────┬──────┬──────┐
│ Xodim        │ 1│ 2│ 3│ 4│ 5│ ... 31            │Kelgan│Kech │Kelmadi│ Soat │
├──────────────┼──┼──┼──┼──┼──┼───────────────────┼──────┼─────┼──────┼──────┤
│ Albina       │ ✓│ ✓│12│ D│ ⋯│                   │  18  │3/47d│  1   │142.5 │
│ Firuzabonu   │ ✓│ S│ ✓│ D│ ⋯│                   │  19  │  —  │  0   │151.0 │
└──────────────┴──┴──┴──┴──┴──┴───────────────────┴──────┴─────┴──────┴──────┘
```

- **Oy tanlagich:** ‹ › tugmalar + oy nomi; default joriy oy; kelajak oyga o'tish
  bloklanmaydi (jadval rejalash uchun), lekin kataklar `future`.
- **Katak (28×28px):**
  - `present` — emerald nuqta/fon; `late` — amber fon, ICHIDA daqiqa soni
    (10px, 99+ → "99"); `absent` — rose; `excused` — sky "S"; `weekend` — slate-100;
    `pending` — pulsatsiyalanuvchi kulrang nuqta; `future` — oq, nuqtali chegara.
  - `flags` bor katak burchagida 6px uchburchak (amber=auto_closed, indigo=manual);
    tooltip'da izohi.
  - Bugungi ustun boshdan-oyoq och-ko'k fon bilan ajratiladi.
- **Sticky:** birinchi ustun (ism, w-44) chapga, sarlavha (kun raqami + hafta kuni
  harfi, Sh/Ya qizg'ish) tepaga yopishadi; jadval o'zi gorizontal skroll
  (`overflow-x-auto`), sahifa EMAS.
- **Katak bosilganda** — Popover: sana, status badge, keldi/ketdi, kechikish,
  ishlangan, izoh, bayroqlar; pastda "Tahrirlash" (canEdit bo'lsa) — MAVJUD
  `EditAttendanceDialog` xodim+sana oldindan to'ldirilgan holda ochiladi.
- **Ism bosilganda** — `EmployeeDrawer` (Sheet, o'ng tomondan): xodim nomi + oy
  statlari + `MonthCalendar` (7 ustunli kalendar, o'sha kataklar) + "Profilga
  o'tish" havolasi. Bu drawer D bosqichdagi xodim kalendari bilan BITTA komponent.
- **Tepada Readiness banneri:** `ok=false` bo'lsa amber banner "⚠ N muammo — oylik
  hisob uchun tayyor emas" → bosilsa ochiladi (hozirgi ReadinessSection mazmuni).
  Davri = tanlangan oy.
- **Yuklash:** skeleton to'r; xato: qayta urinish tugmasi.
- **Mobil (rahbar telefonda ochsa):** matritsa gorizontal skroll bilan qoladi
  (sticky ism ustuni ishlashi shart) — alohida mobil variant qilinmaydi.

**🅲 qabul mezonlari:**
- [ ] 10 xodim × 31 kun < 1s ochiladi (bitta so'rov)
- [ ] Katak popover'idan tahrirlash → saqlangach matritsa yangilanadi (invalidate)
- [ ] Drawer kalendari xodim sahifasidagi (D) bilan bitta komponent
- [ ] Sticky ustun/sarlavha skrollda ishlaydi; bugungi ustun ajralib turadi
- [ ] `EmployeeProfile.tsx`ga "Davomat" bo'limi qo'shiladi: o'sha `MonthCalendar` +
      totals (matrix endpointidan bitta xodim filtri bilan emas — `me/history`
      NI EMAS, `matrix`dan o'z qatorini olish ham emas: eng toza —
      `GET /attendance/matrix?month=&user_id=` ixtiyoriy filtri (A2 ga qo'shiladi))

---

## 🅳 BOSQICH D — Xodim tomoni

### D1. Bugungi jadval chipi (X2, X4)
"Bugungi davomat" kartasi sarlavhasi ostida:
- Ish kuni: `🕘 Bugun: 09:00–18:00` (+ override bo'lsa "o'zgartirilgan" amber belgi)
- Dam: `🌙 Bugun dam olasiz` — va tugmalar bloklanMAYdi (dam kuni kelsa ham check-in
  mumkin, hozirgi mantiq saqlanadi), faqat izoh: "dam kuni — kechikish yozilmaydi".
Ma'lumot: mavjud `useMyWorkWeek()` (kesh umumiy) — yangi so'rov YO'Q.

### D2. Oylik davomatim (X1)
`LateStatusCard`dan keyin yangi karta: **"📅 Oylik davomatim"**
- Tepa: oy nav (‹ Avgust ›) + jami satr: `18 kun · 3 kechikish (47 daq) · 142 soat`
- `MonthCalendar` (C dagi bilan BITTA komponent, xodim rejimida): 7 ustun, katak
  bosilsa pastdan kichik panel (mobil uchun Sheet emas — kartaning o'zida
  kengayadigan qator): sana, keldi/ketdi, kechikish, izoh.
- Ma'lumot: `GET /attendance/me/history?month=` (A3).
- Kelajak oy tugmasi o'chiq (xodimga kerak emas).

### D3. Qadam ko'rsatkichi (X3)
Yuz tasdiqlash modalining tepasiga 3 qadamli indikator:
`① Joylashuv → ② Yuz tasdiqlash → ③ Yuborish`
- skipLocation xodimida ① ko'rinmaydi (2 qadam).
- Faol qadam — primary rang; o'tilgan — emerald ✓; statusMsg matni indikator
  OSTIDA qoladi (matnlar allaqachon yaxshi yozilgan).
- FaceCapture'ga prop QO'SHILMAYDI — indikator CheckIn.tsx modal sarlavhasida,
  holatni mavjud statusMsg/showFace/busy'dan chiqaradi.

**🅳 qabul mezonlari:**
- [ ] Xodim faqat o'z tarixini ko'radi (boshqa user_id so'rab bo'lmaydi — backend test)
- [ ] Kalendar 360px ekranga gorizontal skrollsiz sig'adi
- [ ] Dam kunida chip "Bugun dam olasiz" chiqadi; jadvalsiz xodimga default vaqt
      ko'rinadi ("09:00–18:00 (standart)")
- [ ] Qadam indikatori: GPS bosqichida ①, kamera ochiq ②, yuborishda ③ faol

---

## 🅴 BOSQICH E — Ish jadvali: umumiy ko'rinish

`/work-schedule` ikkita tab: **"Umumiy"** (default, YANGI) va **"Bitta xodim"**
(hozirgi UI o'zgarishsiz shu tabga ko'chadi).

### Umumiy tab
- Ma'lumot: `GET /work-schedule/all/week` (A7).
- Jadval: qator=xodim, ustun=Du..Yak; katak: `09:00–18` (ixcham) / `🌙` (dam) /
  kulrang `standart` (unset — J4 shu yerda KO'RINADIGAN bo'ladi).
- Qator bosilsa → "Bitta xodim" tabiga o'sha xodim tanlangan holda o'tadi.
- Hafta nav (‹ ›) — override'lar haftaga qarab ko'rinadi (override katagi amber
  chegara bilan).

### Nusxalash (J2)
"Bitta xodim" tabida, haftalik andoza kartasi sarlavhasida: "Nusxalash…" tugmasi →
kichik dialog: "Kimdan nusxa olamiz?" (xodim select) → tanlangach uning haftalik
andozasi FORMAGA yuklanadi (saqlanMAYdi — rahbar ko'rib "Saqlash"ni o'zi bosadi).
Backend kerak emas (mavjud GET weekly bilan).

### Override ro'yxati filtri (J3)
Default: bugungi kundan boshlab kelgusi + o'tgan 30 kun; "Hammasini ko'rsatish"
havolasi bilan to'liq ro'yxat.

**🅴 qabul mezonlari:**
- [ ] Umumiy jadvalda barcha kuzatiladigan xodimlar bir ekranda; unset kunlar
      "standart" deb ajralib turadi
- [ ] Qator bosish → bitta xodim rejimi o'sha xodim bilan
- [ ] Nusxalash: A xodim jadvali B formasiga tushadi, saqlangunча bazaga yozilmaydi

---

## 🅵 BOSQICH F — Ofislar xaritasi

- `leaflet` + `react-leaflet` (faqat Offices chunk — lazy route allaqachon bor;
  bundle boshqa sahifalarga ta'sir qilmaydi). Tile: OpenStreetMap standart.
- Xarita (h-80): har faol ofis — marker + radius doirasi (yarim shaffof);
  faolsiz — kulrang.
- Formada koordinata kiritishning 3 yo'li: (1) xaritani BOSISH — marker tushadi,
  lat/lng forma maydonlariga yoziladi; (2) "Mening joyim" (hozirgi); (3) qo'lda
  raqam (hozirgi — saqlanadi, xarita bilan ikki tomonlama sinxron).
- Tahrirlashda o'sha ofis markeri draggable; radius slider (10–1000m) — doira
  jonli o'zgaradi.
- Internet yo'q/tile yuklanmasa: xarita o'rnida "Xarita yuklanmadi" + forma
  to'liq ishlayveradi (xarita — qulaylik, majburiyat emas).

**🅵 qabul mezonlari:**
- [ ] Xaritani bosish lat/lng maydonlarini to'ldiradi; qo'lda kiritish markerni suradi
- [ ] Radius o'zgarganda doira jonli o'zgaradi
- [ ] Leaflet faqat /offices chunk'ida (build hajmi tekshiriladi)

---

## 🅶 BOSQICH G — Sayqallar

1. **Sidebar badge:** "Sababli kunlar" bandida pending soni (excused pending +
   explanations answered). Yangi endpoint SHART EMAS: mavjud ro'yxat so'rovlari
   60s staleTime bilan; badge Layout'da `useExcusedDays("pending")` +
   `useExplanations("answered")` (faqat manager bo'lsa enabled).
2. **"Yozuvlar" jadvali** (matritsa ostidagi yig'ma bo'lim): xodim filtri (select)
   qo'shiladi — qidiruv yozish o'rniga tanlash.
3. **Bo'sh holatlar:** har tab o'z bo'sh holati bilan ("Bu oyda yozuv yo'q" + "Yozuv
   qo'shish" tugmasi).
4. **Toast → aniq matnlar:** "Saqlandi" o'rniga natija ("Albina — 12.08: keldi 09:15,
   kechikish 15 daq").
5. **Bot bilan izchillik:** botdagi "🕐 Davomat statistikasi" matni web "Hisobot"
   tabi bilan bir xil davr/raqam berishini tekshirish (bitta backend — avtomatik,
   faqat sinov).

---

## 3. NIMA QILMASLIK KERAK

- ❌ Mavjud endpointlarning javob maydonlarini O'CHIRMANG/o'zgartirmang — faqat
  qo'shing (bot va mobil ilova eski shaklga bog'langan).
- ❌ Check-in xavfsizlik oqimiga (Face ID, GPS, liveness) TEGMANG — bu boshqa
  hujjatning (BUG_FIX_PROMPT.md) tugallangan ishi.
- ❌ Payroll sahifalarini qayta dizayn qilmang (parallel ish ketmoqda) — faqat
  readiness banneri havola qiladi.
- ❌ `verifix/` ga tegmang.
- ❌ leaflet'dan boshqa yangi og'ir kutubxona qo'shmang (chart uchun mavjud
  recharts yetadi, agar kerak bo'lsa).
- ❌ Bot menyusini o'zgartirmang (web bilan bot menyusi sinxron —
  `employeeNav.ts` sharti buziladi).

## 4. EHTIYOT CHORALARI

1. Har bosqichdan oldin: `cp app.db app.db.bak_<sana>_ux<bosqich>`.
2. Lokal .env haqiqiy guruhga ulangan — digest/eslatma sinovlari FAQAT T- test
   foydalanuvchilar bilan (telegram_id=9994xxxxx — bot yuborolmaydi, xato jim).
3. Test ma'lumoti `T-` prefiksi, oxirida to'liq tozalash.
4. Xizmatlar faqat `schtasks /run /tn "HodimlarTizimi_StartAll"` bilan qayta
   ishga tushiriladi.

## 5. SINOV TALABLARI

Har bosqichdan keyin:
```
.venv/Scripts/python.exe test.py        # 119 + yangilari, 0 FAIL
cd web && npx tsc --noEmit              # toza
```
Frontend o'zgarishlari uchun qo'lda tekshiruv ro'yxati (har bosqich o'z qabul
mezonlari) + build hajmi nazorati (`npm run build` chiqishi — CheckIn chunk
kattalashmasin).
