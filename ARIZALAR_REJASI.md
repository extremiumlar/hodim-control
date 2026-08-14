# Arizalar bo'limi — loyiha rejasi

Sana: 2026-08-13. Uchinchi murojaat turi: **ariza** (xodim kelajakda biror
narsa so'raydi). Kundalik va e'tiroz/shikoyat allaqachon jonli.

---

## 0. Nega bu alohida modul (e'tirozga qo'shib bo'lmaydi)

Uchta murojaat turi **vaqt o'qi** va **tasdiqlangandagi oqibat** bo'yicha
tubdan farq qiladi:

| | Nima haqida | Tasdiqlanganda tizimda nima bo'ladi |
|---|---|---|
| **E'tiroz** | O'tgan qaror | **HECH NARSA** — ataylab. HR tuzatishni qo'lda kiritadi |
| **Shikoyat** | Hozirgi holat | Hech narsa — bu muhokama, hisob emas |
| **Ariza** | **Kelajak** | **REAL o'zgarish SHART** — ta'til kunlari yoziladi, avans hisobga kiradi |

`Appeal` modelining izohida qat'iy yozilgan: *«BU JADVAL HECH NARSANI
HISOBLAMAYDI»* (`db/models.py:1047-1056`). Ariza aynan buning teskarisi —
tasdiqlangach yozishi SHART. Bir jadvalga qo'shilsa o'sha tamoyil buziladi va
"qaysi murojaat nimani o'zgartiradi" degan savol chalkashadi.

**Shuning uchun: alohida jadval, lekin AYNAN o'sha naqshlar** (holat oqimi,
bot↔web adapter juftligi, audit, SLA, bildirishnoma).

---

## 1. Mavjud poydevor (nima allaqachon bor)

| Tayyor narsa | Qayerda | Ariza qanday ishlatadi |
|---|---|---|
| **Eski Django ta'til moduli** | `verifix/backend/leave/` — `LeaveRequest` modeli, approve/finish, testlar | To'g'ridan-to'g'ri ANDOZA: type (vacation/sick/unpaid), start/end, review izohi |
| `ExcusedDay` + `is_excused_day` | `db/models.py:481`, `api/services/attendance.py:167` | Ta'til tasdiqlangach shu qatorlar yoziladi → davomat, jarima, eslatma, digest **avtomatik to'g'ri** |
| `recompute_attendance` | `api/services/attendance.py:277` | Kun sababliga aylangach davomat o'zi qayta hisoblanadi |
| `WorkScheduleOverride` | `db/models.py:848`, `api/routers/work_schedule.py:299` | Ta'til kunini "dam" qilib belgilash |
| `_recalc_from` | `api/routers/work_schedule.py:77` | Jadval o'zgargach bugundan boshlab qayta hisoblash (o'tmishga tegmaydi) |
| **Avans tasdiq oqimi** (2026-08-13) | `PayrollAdjustment.category/status`, `api/routers/payroll.py:777-901` | Avans arizasi tasdiqlangach shu yozuvni yaratadi → Boshliq tasdiqlaydi → payslip o'zi ushlaydi |
| `resolve_rate` + `compute_base` | `api/services/payroll.py:146`, `:399` | Avans miqdorini stavkaga nisbatan cheklash |
| Bot↔web adapter juftligi | `api/routers/excused_days.py:69-186` | Bitta `_helper` + ikki adapter — qat'iy konvensiya |
| `Appeal` naqshi (yangi) | `api/routers/appeals.py` | Holat oqimi, SLA izlari, maxfiylik, `next_step` |
| `can_manage_norms` | `api/routers/norms.py:44-70` | "Kim kimni boshqaradi" — tasdiqlash zanjiri uchun |
| `notify_user` + toifalar | `api/notify.py:51` | Xabar + push, `data={"path": ...}` deep-link |
| Excel eksport naqshi | `api/services/export.py:96`, `:302` | Arizalar reestri |
| Botdan fayl yuborish | `bot/handlers/stats.py:200` (`answer_document`) | Ma'lumotnoma yetkazish |

---

## 2. ⚠️ Bosqich 0 — arizadan OLDIN yopilishi shart bo'lgan teshiklar

O'rganish paytida topilgan, **hozir jonli tizimda mavjud** kamchiliklar.
Ariza moduli ularning ustiga qurilsa, xatolar ko'payadi.

### 0.1 `ExcusedDay` da `UniqueConstraint` YO'Q
`db/models.py:481` — `Bonus`, `Attendance`, `WorkScheduleWeekly/Override`
hammasida bor, bu yerda yo'q. Dublikat faqat kod darajasida to'siladi
(`excused_days.py:85-97`). Ariza oraliqdagi 10 kunni yozayotganda poyga
holatida dublikat paydo bo'lishi mumkin.
→ `UniqueConstraint("user_id","date")` migratsiyasi (avval mavjud
dublikatlarni tozalab).

### 0.2 Ta'tildagi xodim «Keldim» bosa oladi
`perform_check_in` (`api/services/attendance.py:398-475`) sababli kunni
umuman tekshirmaydi. Eski Django'da bu **bloklangan** edi:
`verifix/backend/attendance/services.py:77-93` — *«Siz ta'tildasiz»*.
→ Check-in'da `is_excused_day` tekshiruvi (ogohlantirish yoki blok — 8-bo'lim,
savol 4).

### 0.3 To'lovli/to'lovsiz ta'til farqi yo'q
`ExcusedDay` da `is_paid` maydoni yo'q, natijada:
- `monthly` stavkada har qanday sababli kun **to'lanadi** (`payroll.py:423-424`)
- `daily`/`hourly` da **hech qachon to'lanmaydi** (`payroll.py:448-459`)

Ya'ni "o'z hisobidan ta'til" oyliklilarga bepul dam bo'lib qoladi. Eski
Django'da ajratilgan edi (`verifix/backend/payroll/services.py:37-38`).
→ `ExcusedDay.is_paid` (default `True` — bugungi xatti-harakat saqlanadi) +
`payroll.compute_base` da `monthly` uchun `is_paid=False` kunlarni ayirish.

### 0.4 E'tirozga biriktirilgan fayl HR ga BORMAYDI
`api/routers/appeals.py:266-281` — xabarda faqat matn. `file_id` bazada
saqlanadi, lekin hech qachon qayta yuborilmaydi. Ya'ni xodim skrinshot
biriktiradi, HR uni ko'rmaydi.
→ `api/telegram_notify.py` ga `send_file_id(chat_id, file_id, file_type, caption)`
(~20 qator, `sendPhoto`/`sendDocument` ga `file_id` matnini berish kifoya).
**Bu jonli tizimdagi xato — arizadan mustaqil tuzatilishi kerak.**

### 0.5 Oraliq (bulk) endpoint yo'q
10 kunlik ta'til = 10 ta HTTP so'rov, 10 ta audit qatori, tranzaksiya yo'q —
yarmida uzilsa yarim ta'til yozilib qoladi.
→ Ariza moduli ichida bitta tranzaksiyada yoziladi (yangi endpoint shart emas).

---

## 3. Idea takomillashtirilgan ko'rinishi

### 3.1 Ariza turlari — "tasdiqlangach nima bo'ladi" bo'yicha uch guruh

Bu modulning **markaziy g'oyasi**: ariza turi emas, uning **oqibati** muhim.

| Guruh | Turlari | Tasdiqlanganda tizim nima yozadi |
|---|---|---|
| **A — davomatga** | `vacation` (mehnat ta'tili), `unpaid` (o'z hisobidan), `sick` (kasallik) | Oraliqdagi har kunga `ExcusedDay(approved, is_paid=…)` + ixtiyoriy `WorkScheduleOverride(is_working=False)` |
| **B — pulga** | `advance` (avans) | `PayrollAdjustment(category='advance', kind='minus', status='pending')` → Boshliq tasdiqlaydi (mavjud oqim) |
| **C — qo'lda** | `certificate` (ma'lumotnoma), `resignation` (ishdan bo'shash), `schedule_change` (jadval o'zgartirish), `other` | Hech narsa yozilmaydi — HR ga **keyingi qadam** ko'rsatiladi (e'tirozdagi `next_step` naqshi) |

`schedule_change` ataylab C guruhda: ish jadvali o'zgarishi ko'p variantli
(vaqt, kun, doimiy/vaqtinchalik) — avtomatlashtirish xatoga olib keladi,
HR mavjud sahifadan kiritgani ishonchliroq.

### 3.2 Materializatsiya va uni QAYTARISH (eng nozik qism)

Ariza tasdiqlanganda yozilgan qatorlarning **id'lari saqlanadi**
(`applied_refs` JSON). Nega: ta'til tasdiqlangach bekor qilinsa
(xodim kasal bo'lib qoldi, reja o'zgardi), o'sha 10 ta `ExcusedDay` ni
**qaytarib olish** kerak. Iz bo'lmasa HR ularni qo'lda qidiradi va
albatta bittasini unutadi.

```
applied_refs = {"excused_day_ids": [12,13,14], "schedule_override_dates": ["2026-09-01", ...],
                "payroll_adjustment_id": 45}
```

Bekor qilish qoidalari:
- `ExcusedDay` → `status='rejected'` (o'chirilmaydi — tarix qoladi) +
  o'sha kunlarga `recompute_attendance`
- `WorkScheduleOverride` → o'chiriladi (u sof jadval yozuvi)
- `PayrollAdjustment` → agar `pending` bo'lsa o'chiriladi; `approved` bo'lsa
  **o'chirilmaydi**, HR ga xabar (pul allaqachon berilgan bo'lishi mumkin)
- Davr qulflangan bo'lsa — bekor qilish rad etiladi, Dasturchiga yo'naltiriladi

### 3.3 Tasdiqlash zanjiri

Hozir barcha so'rovlar **hamma HR ga** ketadi (`excused_days.py:104-108`);
xodimning ROP'i (`manager_id`) umuman xabar olmaydi. Ta'tilda esa birinchi
"ha" aynan bevosita rahbardan kelishi kerak — u jamoaning ish yukini biladi.

**Ikki bosqichli, lekin ixtiyoriy:**
```
xodim → [ROP tasdig'i, agar manager_id bor bo'lsa] → HR qarori → (kerak bo'lsa Boshliq)
```
- `manager_id` yo'q bo'lsa ROP bosqichi **o'tkazib yuboriladi** (hozirgi xatti-harakat)
- Boshliq bosqichi faqat **chegaradan oshganda**: ta'til > N kun yoki avans
  stavkaning > X% (8-bo'lim, savol 2-3)
- Har bosqich `ArizaStep` yozuvi sifatida saqlanadi — kim, qachon, nima dedi

### 3.4 Ta'til balansi (Bosqich 2 — keyinroq)

Hozir hisoblab bo'lmaydi: `User.hire_date` yo'q, ta'til normasi yo'q,
`ExcusedDay` da ta'til/kasallik ajratilmagan. Minimal to'plam:
- `User.hire_date: Date | None` (mavjudlarga `SalaryRate.effective_from` dan
  to'ldirish — payroll allaqachon shundan foydalanadi, `payroll.py:463-465`)
- Yillik norma: global sozlama (default 21 kun) yoki `Position` da
- Ishlatilgan kunlar: `LeaveRequest(type='vacation', status='approved')` dan
  sanaladi — `ExcusedDay` dan EMAS (u kasallikni ham qamraydi)

Balans **maslahat sifatida** ko'rsatiladi, arizani bloklamaydi — HR qaror
qiladi. Aks holda noto'g'ri `hire_date` butun oqimni to'xtatib qo'yadi.

### 3.5 Boshqa tamoyillar

- **Anonim ariza YO'Q** — ariza aniq odamning aniq so'rovi
- **Bekor qilish xodimda ham bor**: `pending` holatda xodim o'zi qaytarib
  oladi (fikri o'zgardi) — HR vaqti behuda ketmasin
- **O'tmishga ariza cheklangan**: `start_date` bugundan ≥ N kun oldin bo'lsa
  ogohlantirish (kasallik uchun orqadan yozish normal, ta'til uchun shubhali)
- **To'qnashuv tekshiruvi**: so'ralgan oraliqda allaqachon tasdiqlangan
  `ExcusedDay` yoki boshqa ochiq ariza bo'lsa — ogohlantirish
- **Spam chegarasi**: bir xodimda 3 ta ochiq ariza (e'tirozdagi 5 dan kamroq —
  ariza og'irroq)

---

## 3.6 Taklif qilingan arxitektura yechimlari — tahlil (2026-08-13)

Egasi 5 ta me'moriy taklif berdi. Har biri shu loyihaning **haqiqiy
cheklovlariga** solishtirib tekshirildi (SQLite dev / PostgreSQL prod,
cPanel deploy, mavjud naqshlar). Natija: 3 tasi to'liq qabul, 2 tasi
o'zgartirilgan holda.

### ✅ 1.1 Teskari bog'liqlik (`source_request_id`) — QABUL

`applied_refs` JSON o'rniga `ExcusedDay`, `WorkScheduleOverride`,
`PayrollAdjustment` ga `source_request_id` ustuni. **To'g'ri va JSON'dan
yaxshiroq**, chunki:
- «Bu arizadan qanday qatorlar tug'ilgan» — oddiy `WHERE` so'rovi, JSON
  parse qilish shart emas
- Teskari savolga ham javob beradi: «bu sababli kun qayerdan paydo bo'lgan?»
  — HR ro'yxatda ko'rib turadi (JSON'da bu imkonsiz edi)
- Yetim qatorlar bazaviy darajada oldini olinadi

**Ikki texnik ogohlantirish:**

1. **FK'ni migratsiya ichida qo'shmang.** `f5a6b7c8d9e0_advance.py:38-43` da
   aynan shu tuzoq hujjatlangan: `batch_alter_table` ichida `ForeignKey`
   qo'shish SQLite'da `CircularDependencyError` beradi. Naqsh: migratsiyada
   oddiy `Integer` ustun + indeks, modelda `ForeignKey` (niyatni hujjatlaydi
   va noldan quriladigan bazada haqiqiy cheklov bo'ladi).

2. **Mavjud yozuvni «egallash» holati.** Ta'til kunida xodimda ALLAQACHON
   `WorkScheduleOverride` bo'lsa (masalan qisqa kun), ariza uni o'zgartiradi
   — bekor qilinganda **eski qiymatni tiklash** kerak, o'chirish emas.
   Teskari FK buni bilmaydi. Yechim: mavjud yozuvga TEGMASLIK (faqat yangi
   yaratish), o'zgartirish kerak bo'lsa `AuditLog.before` allaqachon
   yozilyapti — tiklash manbai shu.

### ⚠️ 1.2 Polimorfik `payload` (JSONB) — QISMAN, o'zgartirilgan holda

Taklif: barcha maxsus maydonlar `payload` (JSONB) ga. **Bu shaklda qabul
qilib bo'lmaydi**, ikki sabab:

**(a) JSONB — PostgreSQL'ga xos tur, lokal SQLite'da yo'q.** Loyihada
JSONB hech qayerda ishlatilmagan; 17 ta ustun oddiy `JSON` turida (u
SQLite'da TEXT, Postgres'da json bo'ladi). JSONB'ga o'tish lokal dev
muhitini buzadi.

**(b) Bu maydonlar QIDIRILADI — JSON ichida indekslab bo'lmaydi.**
Modulning uchta asosiy so'rovi aynan shu maydonlarga tayanadi:

| So'rov | Kerak bo'ladigan maydon |
|---|---|
| To'qnashuv tekshiruvi: «bu oraliqda boshqa ta'til bormi?» | `start_date`, `end_date` |
| Avans chegarasi: «bu oyda qancha avans olgan?» | `amount`, `created_at` |
| Ta'til balansi: «bu yil necha kun ishlatgan?» | `start_date`, `end_date`, `kind` |

SQLite'da JSON ichidagi qiymat bo'yicha indeks umuman yo'q; Postgres'da
ifoda-indeks va tip cast kerak bo'lardi. Har uchala so'rov ham jadval
bo'ylab to'liq skanga aylanadi.

**Loyihaning o'z pretsedenti ham shunday:** `Appeal` da `ref_date` va
`ref_period` — faqat ba'zi turlarga tegishli bo'lsa ham ALOHIDA ustun;
`PayrollAdjustment.issued_on` ham shunday. NULL ustun arzon, noto'g'ri
so'rov qimmat.

**QABUL QILINGAN GIBRID:**
- `start_date`, `end_date`, `amount` — **haqiqiy tipli ustunlar** (qidiriladi,
  validatsiya qilinadi, indekslanadi)
- `payload: JSON | None` — **faqat qidirilmaydigan** turga xos qo'shimchalar:
  ma'lumotnoma maqsadi, ishdan bo'shash oxirgi kuni, jadval o'zgartirishda
  so'ralgan yangi vaqt

Ya'ni taklifning g'oyasi (jadval NULL'ga to'lmasin) saqlanadi, lekin
qidiriladigan uchta maydon tashqarida qoladi.

### ✅ 2.1 «Ishdagi ta'tilchi» — QABUL, mexanizmi o'zgartirilgan

G'oya to'g'ri: ogohlantirish yetarli emas, tizim HR dan **qaror so'rashi**
kerak. Lekin buni `TaskModel` orqali qilish noto'g'ri bo'lardi:
- `TaskModel` — bu **xodimga beriladigan ish topshirig'i**; u vazifa
  statistikasi, muddat o'tishi (`mark-overdue`) va kunlik digestga kiradi.
  Tizim xabarlari u yerga tushsa, HR ning «bajarilmagan vazifalar» raqami
  buziladi.

**O'rniga — loyihada allaqachon isbotlangan uchlik:**
1. Arizada holat izi: `interrupted_at` (qachon ishga keldi) +
   `interrupt_decision` (kutilmoqda / qisqartirildi / davom etadi)
2. HR ga inline tugmali xabar: «✂️ Ta'tilni qisqartirish» / «▶️ Davom etsin»
   — `excused_decide:` naqshi
3. Hal qilinmagani rahbar sahifasida badge bo'lib turadi va SLA tick uni
   eslatadi — xabar o'tkazib yuborilsa ham yo'qolmaydi

**Qo'shimcha nozik joy (taklifda yo'q edi):** ta'tilni qisqartirish
payroll'ga tegadi. Agar o'sha davr **qulflangan** bo'lsa (oylik tasdiqlangan),
qisqartirish rad etilishi va Dasturchiga yo'naltirilishi kerak — bekor
qilishdagi bilan bir xil qoida.

### ✅ 2.2 `CalculationService` — QABUL, lekin sharti bor

Kalkulyator arzon: `is_working` mantig'i allaqachon uch joyda bor
(`hourly_plan.py:35-63`, `work_schedule.py:101-151`, `payroll.py:176-220`) —
oraliq bo'yicha yig'ish ustiga yupqa qatlam.

**Shart: global bayramlar hozir YO'Q.** Bayram faqat har xodimga alohida
`WorkScheduleOverride` bilan qo'yiladi. «10 kundan 2 tasi dam olish» degan
javob bayramlarni hisobga olishi uchun `Holiday(date, name)` jadvali kerak,
va u **uchala joyga birga** qo'shilishi shart (kod izohlarida «birini
o'zgartirsangiz ikkinchisini ham» deb yozilgan). Bu Bosqich 0 ga kiradi.

Bayramsiz ham kalkulyator ishlaydi — faqat javobi hafta oxiri va shaxsiy
jadval bo'yicha bo'ladi.

### ⚠️ 3 Dinamik tasdiqlash matritsasi — QABUL, soddalashtirilgan

Yo'nalish to'g'ri: chegaralar kodda emas, bazada bo'lsin. Lekin **yangi
«Global Settings» dvigateli qurish shart emas** — loyihada aynan shu
vazifani bajaradigan tayyor naqsh bor: `FinePolicy` (`db/models.py:1471+`)
— `scope` (global / position / user) + `scope_id` + `resolve_policy()`
prioriteti.

`RequestPolicy` shu naqshda quriladi: global qoida, lavozim bo'yicha
istisno, xodim bo'yicha istisno — **bepul**, chunki mantiq allaqachon
yozilgan. HR keyinchalik «rahbarlarga 30 kun, qolganlarga 21» desa,
yangi kod kerak bo'lmaydi.

**Zanjirni to'liq dinamik qilish (ixtiyoriy tasdiqlovchilar ketma-ketligi)
esa ortiqcha** — taklifdagi jadvalning o'zida atigi ikki naqsh bor:
`ROP → HR` va `ROP → HR → Boshliq`. Shuning uchun ikki maydon yetadi:
`requires_manager: bool` va `boss_threshold: Numeric | None`. 8-50 kishilik
kompaniyada undan murakkabroq zanjir sozlanmaydi, lekin qo'llab-quvvatlash
xarajati doimiy bo'lib qoladi.

### ❌ 4 `SELECT ... FOR UPDATE` — MEXANIZM ALMASHTIRILADI

Muammoning o'zi haqiqiy, lekin **bu yechim shu loyihada ishlamaydi**:

```
SQLite: FOR UPDATE XATO -> OperationalError near "for": syntax error
```

(hozir tekshirildi). Lokal dev SQLite'da — ya'ni ariza yaratishning har bir
so'rovi lokalda **xato bilan yiqiladi**, testlar yozib bo'lmaydi, va
kafolat faqat productionda «ko'r-ko'rona» yashaydi.

**Bundan muhimrog'i: eng xavfli poyga bu emas.** Ikki qurilmadan bir vaqtda
ariza yuborib limitni chetlab o'tish — kamdan-kam va oqibati yumshoq (HR
ko'radi va rad etadi). Haqiqiy xavf — **ikki marta materializatsiya**:
tasdiqlash tugmasi ikki marta bosilsa yoki ikki HR bir vaqtda tasdiqlasa,
10 ta ta'til kuni **20 ta** `ExcusedDay` bo'lib yozilishi va avans **ikki
marta** ushlanishi mumkin. Bu to'g'ridan-to'g'ri pulga tegadi.

**Portativ va isbotlangan himoya (loyihaning o'z naqshlari):**

1. **Holat o'tishining idempotentligi** — `status != pending` bo'lsa 400.
   Bu `Appeal`, `ExcusedDay`, `OvertimeEntry` da allaqachon ishlaydi
   (`appeals.py: _decide`, `excused_days.py:333-341`).
2. **`UNIQUE(user_id, date)` `ExcusedDay` da** (Bosqich 0.1) — ikkinchi
   yozuv `IntegrityError` oladi, `rollback` → qayta yozilmaydi. Aynan shu
   naqsh cPanel'dagi ikki cron jarayoniga qarshi ishlaydi
   (`AttendanceReminder`).
3. **Bitta tranzaksiya** — oraliq to'liq yoziladi yoki umuman yozilmaydi.

**Balans poygasi haqida:** rejada balans **maslahat sifatida** (bloklamaydi),
shuning uchun o'zgaruvchan `leave_balances` qatori umuman kerak emas —
ishlatilgan kunlar tasdiqlangan arizalardan **hisoblab olinadi**. Qatori
bo'lmagan narsada poyga ham bo'lmaydi.

Agar kelajakda qat'iy bloklash kerak bo'lsa: `leave_balances` + `version`
ustuni bilan **optimistik qulf** (`UPDATE ... WHERE version = X`, mos
kelmasa qayta urinish) — u ikkala bazada ham bir xil ishlaydi. `FOR UPDATE`
esa faqat Postgres'ga xos yo'l sifatida, dialekt tekshiruvi bilan
qo'shilishi mumkin, lekin lokalda sinab bo'lmasligi izohda yozilishi shart.

---

## 4. Ma'lumot modeli

```python
class LeaveKind(str, enum.Enum):
    vacation = "vacation"        # mehnat ta'tili (to'lovli)
    unpaid = "unpaid"            # o'z hisobidan
    sick = "sick"                # kasallik
    advance = "advance"          # avans
    certificate = "certificate"  # ma'lumotnoma
    schedule_change = "schedule_change"
    resignation = "resignation"
    other = "other"

class RequestStatus(str, enum.Enum):
    pending = "pending"            # yangi
    manager_ok = "manager_ok"      # ROP tasdiqladi, HR kutilmoqda
    approved = "approved"          # tasdiqlandi + materializatsiya qilindi
    rejected = "rejected"
    cancelled = "cancelled"        # xodim o'zi qaytarib oldi
    revoked = "revoked"            # tasdiqlangach bekor qilindi (qatorlar qaytarildi)

class EmployeeRequest(Base):
    """Xodim arizasi — KELAJAKKA qaratilgan so'rov.

    `Appeal` dan farqi (models.py:1047): bu jadval tasdiqlanganda REAL
    o'zgarish yozadi. Yozilgan qatorlar arizaga TESKARI bog'langan
    (`source_request_id`) — bekor qilinganda aynan shular qaytariladi."""
    __tablename__ = "employee_requests"

    id, user_id (FK, index)
    kind: String(20), index
    # ── Qidiriladigan maydonlar: ALOHIDA USTUN (JSON'da emas — 3.6/1.2) ──
    start_date: Date | None      # A guruh; to'qnashuv va balans so'rovlari
    end_date: Date | None
    amount: Numeric(14,2) | None # B guruh; oylik avans chegarasi
    # ── Qidirilmaydigan, turga xos qo'shimchalar ──
    payload: JSON | None         # ma'lumotnoma maqsadi, jadval o'zgartirish
                                 # tafsiloti, ishdan bo'shash oxirgi kuni...
    reason: Text                       # 10..2000
    file_id / file_type: String | None # Telegram ilova (Appeal naqshi)

    status: String(20), index
    # Zanjir izlari
    manager_id_at_creation: int | None  # kim tasdiqlashi kerak edi (tarix)
    manager_decided_by / _at / _note
    decided_by / decided_at / decision_note   # yakuniy (HR/Boshliq)
    applied_at: DateTime | None               # materializatsiya vaqti
    # «Ishdagi ta'tilchi» (3.6/2.1)
    interrupted_at: DateTime | None           # ta'til vaqtida check-in qildi
    interrupt_decision: String(20) | None     # pending | shortened | continued

    sla_reminded_at / escalated_at      # Appeal bilan bir xil
    created_at (index)
```

**Teskari bog'liqlik** — uchta mavjud jadvalga bittadan ustun:

```python
# ExcusedDay, WorkScheduleOverride, PayrollAdjustment ga:
source_request_id: Mapped[int | None] = mapped_column(
    ForeignKey("employee_requests.id"), nullable=True, index=True
)
```
⚠️ Migratsiyada FK EMAS, oddiy `Integer` + indeks (`f5a6b7c8d9e0:38-43`
tuzog'i: `batch_alter_table` ichida FK → SQLite'da `CircularDependencyError`).
Modelda `ForeignKey` qoladi — niyatni hujjatlaydi.

**Tasdiqlash qoidalari** — `FinePolicy` scoping naqshida (3.6/3):
```python
class RequestPolicy(Base):        # scope: global | position | user
    scope / scope_id / kind
    requires_manager: bool         # ROP bosqichi kerakmi
    boss_threshold: Numeric | None # shundan oshsa Boshliq ham
    max_days / max_amount: ...     # ogohlantirish chegaralari
```

Migratsiyalar: `g6h7i8j9k0l1_employee_requests.py` (asosiy),
`g7...(source_request_id x3)`, Bosqich 0 niki alohida (ExcusedDay unique,
`is_paid`, `User.hire_date`, `Holiday`).

---

## 5. API — `api/routers/requests.py`, prefix `/requests`

```
# Xodim (bot)
POST /requests/bot                    {telegram_id, kind, ...}
GET  /requests/bot/my/{telegram_id}
POST /requests/{id}/cancel/bot        {telegram_id}      # o'zi qaytarib oladi

# Xodim (web/JWT)
GET  /requests/me
POST /requests/me
POST /requests/{id}/cancel

# Rahbar
GET  /requests?status_filter=&kind=                      # ROP — faqat o'z jamoasi
POST /requests/{id}/manager-decide  {approve, note}      # ROP bosqichi
POST /requests/{id}/decide          {decision, note}     # HR/Boshliq yakuniy
POST /requests/{id}/revoke          {reason}             # tasdiqlangandan keyin bekor
GET  /requests/export?from=&to=                          # Excel reestr

# Yordamchi
GET  /requests/me/balance                                # ta'til balansi (Bosqich 2)
POST /requests/sla-tick                                  # scheduler
```

**Yadro — `_apply(db, req, actor)`** (materializatsiya):
- A guruh: oraliqdagi har kunga `ExcusedDay(approved, is_paid)` (mavjudini
  tekshirib), so'ng har kunga `recompute_attendance`; id'lar `applied_refs` ga
- B guruh: `PayrollAdjustment(advance, pending)`; davr qulf bo'lsa 400
- C guruh: hech narsa, `next_step` matni qaytariladi

Hammasi **bitta tranzaksiyada** — yarim ta'til yozilib qolmasin.

---

## 6. Bot — `bot/handlers/request.py`

Yangi tugma **YO'Q**. Mavjud «⚖️ E'tiroz / Shikoyat» tugmasi «📮 Murojaatlarim»
ga aylanadi va uch tugmali menyu beradi: e'tiroz / shikoyat / **ariza**.
Nega: menyuda allaqachon 8-10 tugma bor, yana bittasi qo'shilsa xodim
adashadi; uchalasi bitta tushunchaviy guruh.

Oqim: tur tanlash → turga qarab so'raladi (sana oralig'i / summa / erkin matn)
→ sabab → tasdiq ekrani (**nima yuborilayotgani to'liq ko'rsatiladi**) → yuborish.

Sana oralig'i uchun: «Bugundan», «Ertadan», «Aniq sana» → keyin necha kun.
Kalendar emas — Telegram'da u og'ir; oxirgi qadamda oraliq matn bilan
tasdiqlanadi («01.09 — 10.09, 10 kun»).

---

## 7. Web

- `pages/Requests.tsx` (rahbar): `Appeals.tsx` dan ko'chirma — filtr, SLA
  yoshi, qaror dialogi; qo'shimcha: oraliq/summa ustuni va «Bekor qilish»
- `pages/me/Requests.tsx` (xodim): forma (tur → maydonlar o'zgaradi) +
  ro'yxat + `pending` da «Qaytarib olish»
- Sidebar: «Ma'muriyat → Arizalar», badge = `pending` soni
- `StatusBadge` ga `kind="request"` (6 holat)
- Nav uch joyda sinxron (`employeeNav.ts`, `mobile/lib/sections.ts`, bot)

---

## 8. Egasidan kerakli qarorlar (defaultlar bilan)

| # | Savol | Default |
|---|---|---|
| 1 | ROP tasdig'i kerakmi? | HA, `manager_id` bor bo'lsa; yo'q bo'lsa to'g'ridan HR ga |
| 2 | Necha kundan oshsa Boshliq tasdig'i? | 7 kun |
| 3 | Avans chegarasi | Stavkaning 50% i; oshsa Boshliq tasdig'i |
| 4 | Ta'tildagi xodim «Keldim» bosa? | OGOHLANTIRISH (blok emas) — real hayotda ta'tildan chaqirib olinadi |
| 5 | Ma'lumotnoma qanday beriladi? | Bosqich 1 da: HR qo'lda tayyorlaydi, ariza faqat qayd etadi. Bosqich 3 da .docx shablon |
| 6 | Ishdan bo'shash arizasi bo'lsinmi? | HA, lekin C guruhda (hech narsa yozmaydi) — huquqiy jarayon tizimdan tashqarida |
| 7 | O'tmishga ariza | 30 kungacha ruxsat (kasallik uchun), undan narisi rad |

---

## 9. Bosqichma-bosqich ijro rejasi

**Bosqich 0 — poydevor tuzatishlari** (arizadan mustaqil qiymatga ega)
- [ ] **E'tiroz fayli HR ga yuborilsin** (`send_file_id`) — JONLI xato, eng shoshilinch
- [ ] `ExcusedDay` UNIQUE(user_id, date) + dublikatlarni tozalash
      → ikki marta materializatsiyaga qarshi ASOSIY himoya (3.6/4)
- [ ] `ExcusedDay.is_paid` + payroll `monthly` da hisobga olish
- [ ] `ExcusedDay/WorkScheduleOverride/PayrollAdjustment` ga `source_request_id`
- [ ] Check-in'da sababli kun aniqlash + `interrupted_at` yozish
- [ ] `User.hire_date` + `SalaryRate.effective_from` dan to'ldirish
- [ ] `Holiday(date, name)` global jadval + `override > holiday > weekly >
      default` — **uchala joyga birga** (`hourly_plan.py`, `work_schedule.py`,
      `payroll.py`)

**Bosqich 1 — ariza yadrosi** ✅ BAJARILDI (2026-08-13)
- [x] `EmployeeRequest` modeli (gibrid: `start_date`/`end_date`/`amount`
      alohida ustun + `payload` JSON) + `RequestKind`/`RequestStatus`
- [x] `source_request_id` — `excused_days`, `work_schedule_override`,
      `payroll_adjustments` (migratsiyada oddiy Integer + indeks; FK faqat
      modelda — SQLite batch tuzog'i)
- [x] Migratsiya `i8j9k0l1m2n3` (teskari yo'l sinaldi)
- [x] `api/services/workdays.py` — ish kunlari kalkulyatori (bulk, bir
      so'rovda) + to'qnashuv aniqlash
- [x] `api/routers/requests.py` — 14 endpoint, `_apply`/`_revert`
- [x] `api/services/cron_jobs.py: requests_sla_tick` + cron in-process
      ulanishi (`REQUESTS_SLA_MINUTE=10` — murojaat SLA'sidan 3 daqiqa keyin)
- [x] Sinov: 69 tekshiruv, 0 xato

**Ijro paytidagi qarorlar:**
- **Ta'til faqat ISH kunlariga yoziladi** — dam kunlariga `ExcusedDay`
  yozish shovqin bo'lardi (kalendarda «sababli» bo'lib chiqardi).
- **Mavjud sababli kunga TEGILMAYDI** — xodim o'zi so'rab olgan bo'lsa,
  arizaga «o'g'irlab» qo'yilmaydi (bekor qilinganda begona yozuv o'chib
  ketardi). UNIQUE baribir ruxsat bermaydi.
- **Bekor qilishda `ExcusedDay` o'chirilmaydi, `rejected` qilinadi** —
  tarix qoladi va «nega bu kun sababli edi» savoliga javob bo'ladi.
  `PayrollAdjustment` esa `pending` bo'lsa o'chiriladi; `approved` bo'lsa
  TEGILMAYDI (pul berilgan bo'lishi mumkin) va ogohlantirish qaytariladi.
- **Avansda davr qulfi tekshiriladi** — qulflangan davrga yozuv qo'shilsa
  u hech qachon hisobga kirmasdi va «avans berildi-yu payslipda yo'q»
  degan chalkashlik chiqardi.
- **SLA mantig'i `cron_jobs.py` da** — boshqa seans barcha ticklarni
  in-process ga ko'chirgan (sayt qotishi tuzatishi), shu naqshga moslashildi.

**Bosqich 2 — bot** ✅ BAJARILDI (2026-08-13)
- [x] Menyu hubi: `BTN_APPEAL` → `BTN_REQUESTS` («📮 Murojaatlarim»), uch
      tur bitta inline menyuda. Eski tugma matni ALL_MENU_BUTTONS da qoldi
      va handler ikkalasini ham ushlaydi — Telegram klaviaturani xodim
      qurilmasida keshlab qo'yadi, eski tugma bosilsa ishlashi kerak.
- [x] `bot/handlers/request.py` — 8 tur, uch xil shoxlanish (ta'til: sana →
      kun → KALKULYATOR; avans: summa; qolgani: to'g'ridan-to'g'ri sabab)
- [x] HR qarori: tasdiqlash/rad + majburiy izoh; javobda materializatsiya
      natijasi ko'rsatiladi («5 ta sababli kun yozildi», «avans 2026-08
      davriga qo'shildi») va C guruhda `next_step`
- [x] `api_client.py`: 5 funksiya (create, my_list, calc, decide, cancel)
- [x] Sinov: 51 tekshiruv, 0 xato. Mavjud to'plamlar regressiyasiz —
      jami **381 tekshiruv**.

**Ijro paytidagi qaror:** kalkulyator javobi ariza yuborishdan OLDIN
ko'rsatiladi va oraliqda ish kuni bo'lmasa ariza umuman yaratilmaydi
(«bu oraliqda ish kuni yo'q — ariza kerak emas»).

**Bosqich 3 — web**: rahbar sahifasi + kabinet + nav sinxroni

**Bosqich 4 — zanjir, qoidalar, balans**: `RequestPolicy` (scope naqshi),
ROP bosqichi, Boshliq chegarasi, sozlamalar sahifasi, ta'til balansi
(hisoblab olinadigan, bloklamaydi)

**Bosqich 5 — «ishdagi ta'tilchi»**: inline tugmali HR qarori, ta'tilni
qisqartirish + `recompute_attendance`, davr qulfi tekshiruvi

**Bosqich 6 — ⭐ ixtiyoriy**: ma'lumotnoma .docx shabloni (`zipfile` +
placeholder — yangi kutubxonasiz), arizalar Excel reestri, bayramlarni
ommaviy qo'yish UI

---

## 10. Taxminiy hajm

| Qism | Hajm |
|---|---|
| Bosqich 0 (7 ta tuzatish + bayramlar) | ~550 qator + 5 migratsiya |
| Yadro + API + kalkulyator | ~800 qator |
| Bot | ~450 qator |
| Web (2 sahifa) | ~550 qator |
| Zanjir + qoidalar + balans | ~450 qator |
| «Ishdagi ta'tilchi» | ~250 qator |
| **Jami (0-5)** | **~3050 qator** |

Arxitektura takliflari hajmni ~700 qatorga oshirdi (bayramlar, `RequestPolicy`
scoping, kalkulyator, ta'tilni qisqartirish oqimi) — lekin ularsiz modul
kelajakda qayta yozilishi kerak bo'lardi.

Solishtirish uchun: e'tiroz/shikoyat moduli ~2000 qator bo'ldi va 6 kunlik
seansda tugadi.
