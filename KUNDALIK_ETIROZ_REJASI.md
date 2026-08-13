# Ish kundaligi + E'tiroz/Shikoyat tizimi — loyiha rejasi

Sana: 2026-08-13. Ikki mustaqil modul, bitta reja:

1. **Ish kundaligi** — har xodim kun davomida bajargan ishlarini yozib boradi,
   rahbar oy kesimida ko'radi.
2. **E'tiroz va shikoyat (Appeal)** — xodim jarima/davomat/oylik bo'yicha rasmiy
   e'tiroz yoki umumiy shikoyat yuboradi, HR/Boshliq izli (auditli) qaror qiladi.

Modullar bir-biriga bog'liq emas — alohida bosqichlarda, alohida deploy qilinadi.

---

## 0. Mavjud poydevor (nima allaqachon bor, nimadan foydalanamiz)

| Tayyor narsa | Qayerda | Bu rejada qanday ishlatiladi |
|---|---|---|
| So'rov→qaror naqshi (`pending→answered→accepted/rejected`) | `ExplanationRequest` (`db/models.py:932`), `api/routers/attendance.py:1588-1729` | Appeal statuslari va qaror oqimi aynan shu andozada |
| Bot↔Web juftligi: bitta `_helper` + ikki adapter | `api/routers/excused_days.py:69,234,243` | Ikkala modulda ham shu naqsh |
| Qaror inline tugmalari + `edit_text` bilan ikkinchi bosishni yopish | `bot/handlers/excused.py:387-405` | Appeal qarori botda shu naqshda |
| `notify_user` + push toifalari (migratsiyasiz yangi toifa) | `api/notify.py:51`, `api/services/push.py:50-112` | 2 ta yangi toifa: `work_log`, `appeals` |
| Eslatma idempotentligi: IZ AVVAL + `UniqueConstraint` + `IntegrityError→continue` | `AttendanceReminder`, `api/routers/attendance.py:1450-1512` | Kundalik kechki eslatmasi shu jadvalga yangi `kind` bilan |
| Scheduler + cPanel cron_tick juftligi | `scheduler/main.py`, `scripts/cron_tick.py:_due()` | 2 yangi tick: `work-log/reminder-tick`, `appeals/sla-tick` |
| Oylik tuzatish — `PayrollAdjustment` | `db/models.py:1502` | E'tiroz qondirilganda pul tuzatish FAQAT shu orqali |
| Sababli kun — `ExcusedDay` + `recompute_attendance` | `attendance.py:1674-1707` | Davomat e'tirozi qondirilganda FAQAT shu orqali |
| `AuditLog` (inline `db.add`, `row_to_dict`) | `db/models.py:831`, `api/audit_json.py` | Har appeal qarori auditga |
| `ReasonDialog` (≥5 belgi sabab majburiy) | `web/src/components/ReasonDialog.tsx` | HR qaror izohi uchun tayyor |
| `MonthNav` + `MonthCalendar` oylik ko'rinish | `web/src/components/attendance/` | Kundalik oylik ko'rinishida qayta ishlatiladi |
| Sidebar badge (kutilayotgan ishlar soni) | `web/src/Layout.tsx:305-312` | Appeals uchun `pending` badge |
| Payslip tasdiqlanganda xodimga DM | `api/routers/payroll.py:1055-1066` | DM ostiga "⚖️ E'tiroz" tugmasi qo'shiladi (1.5-band orzusi) |

`OYLIK_JARIMA_REJASI.md` 1.5-band allaqachon shuni va'da qilgan edi:
*"⭐ Xodim payslip ostidan e'tiroz bildira oladi → HRga so'rov"* — bu reja o'sha
qarzni ham yopadi.

**Nom to'qnashuvi:** botda "E'tiroz" so'zi sotuv kontekstida band
(`bot/handlers/playbook.py:27` — mijoz e'tirozlari). Kodda yangi modul `appeal`
deb nomlanadi; UI matni "⚖️ E'tiroz / Shikoyat" — sotuv menyusidagi
"🛡 E'tiroz bilan ishlash"dan vizual farqli.

---

## 1. Idea takomillashtirilgan ko'rinishi

### 1.1 Ish kundaligi — tamoyillar

- **Kun ichida ko'p yozuv, har biri vaqt tamg'asi bilan.** Bitta katta matn emas:
  xodim ish tugagach 1-2 jumla qo'shadi ("Uysotda 14 lid qayta ishladim",
  "3 ta ko'rsatuvga chiqdim"). Bu oy oxirida to'qib chiqarilgan hisobotdan
  ishonchliroq va yozish psixologik yengil.
- **Faqat o'sha kunning o'zida tahrirlash/o'chirish mumkin.** Ertasi kundan yozuv
  QULFLANADI — kundalikning hujjatlik qiymati shunda. (Dasturchi roli
  `admin_override` orqali istisno, mavjud tamoyil bo'yicha.)
- **O'chirish — yumshoq** (`deleted_at`), `Norm` naqshi bo'yicha
  (`db/models.py:384-389`): tarix yo'qolmaydi, o'qishlar `deleted_at IS NULL`.
- **Kechki eslatma** — faqat o'sha kuni ISHLAGAN (present/late) va hali hech
  narsa yozmagan xodimga, check-out vaqtiga yaqin. Dam kuni/sababli kunda
  eslatma yo'q.
- **Pul mantig'iga ULANMAYDI.** Yozmaganlik jarima keltirmaydi — faqat rahbar
  hisobotida qizil ko'rinadi. (Egasi keyin xohlasa, alohida qaror bilan
  qo'shiladi — lekin bu reja doirasida EMAS, payroll yadrosi tinch qoladi.)
- **Rahbar oy kesimida ko'radi:** xodim tanlaydi → kalendar (yozgan kunlar yashil,
  ish kuni-yu yozmagan — qizil) + kunma-kun ro'yxat + qamrov foizi
  ("22 ish kunidan 19 tasida yozgan").
- ⭐ Keyinroq (ixtiyoriy bosqich): oy yopilganda AI qisqacha xulosa — "bu xodim
  oy davomida asosan X bilan shug'ullangan" (mavjud AI darvozalari bilan).

### 1.2 E'tiroz/Shikoyat — tamoyillar

- **Ikki tur bitta jadvalda:**
  - `objection` (e'tiroz) — aniq qarorga qarshi: davomat kuni (kechikish/kelmadi
    belgisi), oylik varaqasi (jarima summasi, hisob xatosi). Har doim manzilli:
    `ref_date` yoki `ref_period` bilan — HR ochganda kontekst darhol ko'rinadi.
  - `complaint` (shikoyat) — erkin mavzu: ish sharoiti, jamoa, boshqaruv, boshqa.
- **Qabul qilinganda pul/davomat o'zgarishi FAQAT mavjud mexanizmlar orqali:**
  davomat e'tirozi → HR mavjud `ExcusedDay`/davomat tuzatish yo'lidan yuradi;
  oylik e'tirozi → `PayrollAdjustment` (davr ochiq bo'lsa) yoki Dasturchi
  unlock (davr qulf bo'lsa). Appeal jadvali o'zi HECH NARSANI hisoblamaydi —
  `ExplanationRequest`dagi isbotlangan tamoyil (`db/models.py:938-942`).
- **Qaror izohi majburiy** (≥5 belgi) — xodim har doim NEGA rad etilganini
  ko'radi. Shaffoflik nizoni kamaytiradi (payroll rejasidagi 1.5-band ruhi).
- **Oraliq holat `in_review`** — HR "O'rganyapman" tugmasini bossa xodimga
  "ko'rib chiqilyapti" degan xabar boradi. Kichik narsa, lekin "meni eshitishdi"
  hissi uchun muhim.
- **Manzil tanlash:** shikoyatda xodim "Kimga: HR yoki Boshliq" ni o'zi tanlaydi
  (shikoyat HR haqida bo'lishi mumkin!). E'tiroz doim HRga (HR yo'q bo'lsa
  Boshliqqa — mavjud fallback naqshi, `excused_days.py:104-108`).
- **SLA:** `pending`/`in_review` 3 kundan oshsa — qabul qiluvchiga eslatma;
  5 kundan oshsa — Boshliqqa eskalatsiya. Kunlik tick, idempotent.
- **Anonim shikoyat** (faqat `complaint`): xodim xohlasa ismi HR ro'yxatida
  ko'rinmaydi. Bazada `user_id` saqlanadi (suiiste'molga qarshi, faqat Dasturchi
  ko'ra oladi). Yoqish/o'chirish — egasining qarori (9-bo'lim).
- **Spamga qarshi:** bir xodimda bir vaqtda ko'pi bilan 5 ochiq murojaat.
- **Ilova biriktirish (bot):** rasm/hujjat — Telegram `file_id` saqlanadi,
  HR botda "📎 Faylni ko'rish" bilan oladi. Webda yuklash YO'Q (birinchi
  bosqichda) — upload infratuzilmasi yo'q, keyin qo'shiladi.
- **Payslip DM ostida "⚖️ E'tiroz" tugmasi** — davr tasdiqlanganda keladigan
  shaxsiy xabardan bir bosishda e'tiroz oqimi ochiladi, `ref_period` avtomatik.

---

## 2. Ma'lumot modeli (`db/models.py` ga)

### 2.1 Ish kundaligi

```python
class WorkLogSource(str, enum.Enum):
    bot = "bot"
    web = "web"   # kabinet ham, mobil WebView ham shu

class WorkLogEntry(Base):
    """Xodimning kunlik ish yozuvi. Kun ichida bir nechta yozuv normal holat.

    QULF QOIDASI: yozuvni faqat egasi va faqat `date == bugun` bo'lganda
    tahrirlaydi/o'chiradi — ertasi kundan hujjat. Tahrir oynasi server vaqti
    bilan (timeutil.today_local), mijoz vaqtiga ishonilmaydi.

    O'chirish yumshoq (Norm naqshi): barcha o'qishlar deleted_at IS NULL bilan.
    """
    __tablename__ = "work_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)   # ⚠️ dt.date — pydantic/anotatsiya tuzog'i
    text: Mapped[str] = mapped_column(Text)                   # 3..2000 belgi (sxemada)
    source: Mapped[str] = mapped_column(String(10), default=WorkLogSource.bot.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Indeks: `(user_id, date)` kompozit — oylik ko'rinish so'rovi uchun.

Eslatma izi uchun YANGI JADVAL KERAK EMAS: `AttendanceReminder`
(`UniqueConstraint(user_id, date, kind)`) ga yangi `kind="work_log"` qiymati —
String ustunga yangi qiymat migratsiyasiz qo'shiladi (isbot:
`a9b0c1d2e3f4:13-14` izohi).

### 2.2 E'tiroz/Shikoyat

```python
class AppealKind(str, enum.Enum):
    objection = "objection"   # e'tiroz — aniq qarorga qarshi
    complaint = "complaint"   # shikoyat — erkin mavzu

class AppealTopic(str, enum.Enum):
    attendance = "attendance"  # davomat kuni / kechikish jarimasi
    payroll = "payroll"        # oylik varaqasi / hisob
    work_env = "work_env"      # ish sharoiti (complaint)
    team = "team"              # jamoa/munosabatlar (complaint)
    other = "other"

class AppealStatus(str, enum.Enum):
    pending = "pending"        # yangi, hali ochilmagan
    in_review = "in_review"    # HR "o'rganyapman" dedi
    accepted = "accepted"      # e'tiroz qondirildi
    rejected = "rejected"      # rad etildi (izoh majburiy)
    resolved = "resolved"      # shikoyat hal qilindi (izoh majburiy)

class Appeal(Base):
    """Xodim murojaati. MUHIM TAMOYIL (ExplanationRequest'dan meros):
    bu jadval hech narsani HISOBLAMAYDI. `accepted` bo'lganda davomat/pul
    tuzatish FAQAT mavjud mexanizmlar orqali (ExcusedDay, PayrollAdjustment,
    admin unlock) — ikkita mustaqil hisob yo'li paydo bo'lmasligi uchun."""
    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), index=True)
    topic: Mapped[str] = mapped_column(String(12), default=AppealTopic.other.value)
    text: Mapped[str] = mapped_column(Text)                    # 10..3000 belgi
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    recipient_role: Mapped[str] = mapped_column(String(10), default=Role.hr.value)  # hr | boss
    # E'tiroz manzili — HR kontekstni bir qarashda ko'rsin:
    ref_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)      # davomat kuni
    ref_period: Mapped[str | None] = mapped_column(String(7), nullable=True)   # "YYYY-MM" payslip
    # Telegram ilova (ixtiyoriy):
    file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)   # photo | document
    status: Mapped[str] = mapped_column(String(12), default=AppealStatus.pending.value, index=True)
    review_started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SLA izlari — eslatma/eskalatsiya bir marta ketishi uchun (idempotentlik):
    sla_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
```

### 2.3 Migratsiya

Ikki ALOHIDA migratsiya (modullar mustaqil deploy bo'lsin):
`d3e4f5a6b7c8_work_log_entries.py` (down_revision = joriy head `c2d3e4f5a6b7`)
va `e4f5a6b7c8d9_appeals.py`. Ikkalasi ham `op.batch_alter_table`siz — yangi
jadvallar `op.create_table` bilan; docstringda biznes sabab (konvensiya).
Ishga tushirish LOYIHA ILDIZIDAN: `python -m alembic -c db/alembic.ini upgrade head`.

---

## 3. API

### 3.1 `api/routers/work_log.py` — prefix `/work-log`

```
# Xodim (bot adapter, X-Bot-Secret; shaxs = telegram_id)
POST /work-log/bot                     {telegram_id, text}      # bugunga yozuv
GET  /work-log/bot/today/{telegram_id}                          # bugungi yozuvlar (bot ko'rsatadi)

# Xodim (web/JWT; shaxs = token) — kabinet va mobil WebView
GET    /work-log/me?month=YYYY-MM                               # oylik: kunlar + yozuvlar + qamrov
POST   /work-log/me                    {text}                   # bugunga yozuv
PATCH  /work-log/me/{id}               {text}                   # faqat bugungi yozuv
DELETE /work-log/me/{id}                                        # faqat bugungi, soft-delete

# Rahbar (JWT, require_roles(hr, rop, boss, dasturchi))
GET /work-log?month=YYYY-MM&user_id=N                           # bitta xodim oyligi
GET /work-log/coverage?month=YYYY-MM                            # hamma xodim: yozgan/ish kunlari %

# Scheduler (X-Bot-Secret)
POST /work-log/reminder-tick                                    # kechki eslatma
```

Umumiy mantiq `_add_entry_for_user(db, user, text, source)` — bot/web
adapterlari shuni chaqiradi (excused_days naqshi). Tahrir/o'chirishda qulf:
`entry.date != today_local()` → 403 "Yozuv qulflangan — faqat o'sha kuni
o'zgartirish mumkin".

`reminder-tick` mantig'i (`attendance.py:1420-1547` andozasi):
1. Bugun `Attendance.status ∈ (present, late)` va check-out vaqtiga ≤30 daqiqa
   qolgan (yoki check-out qilib bo'lgan) xodimlar;
2. bugun `WorkLogEntry` yo'q (deleted hisobga olinmaydi);
3. `AttendanceReminder(kind="work_log")` izi yo'q;
4. IZ AVVAL yoziladi → `IntegrityError→rollback→continue` → keyin
   `notify_user(db, user, Category.WORK_LOG, "...")` (`force_telegram` SHART
   EMAS — yozishni ilova/saytda ham qilsa bo'ladi; `data={"path": "/me/work-log"}`).

### 3.2 `api/routers/appeals.py` — prefix `/appeals`

```
# Xodim (bot adapter)
POST /appeals/bot                      {telegram_id, kind, topic, text, is_anonymous,
                                        recipient_role, ref_date?, ref_period?, file_id?, file_type?}
GET  /appeals/bot/my/{telegram_id}                              # o'z murojaatlari (oxirgi 10)

# Xodim (web/JWT)
GET  /appeals/me                                                # o'z ro'yxati
POST /appeals/me                       {kind, topic, text, is_anonymous, recipient_role, ref_*}

# Qabul qiluvchi (JWT, require_roles(hr, boss, dasturchi))
GET  /appeals?status_filter=&kind=                              # ro'yxat (anonimda ism yashirin)
POST /appeals/{id}/review                                       # in_review + xodimga xabar
POST /appeals/{id}/decide              {decision, note}         # accepted|rejected|resolved, note ≥5

# Bot adapterlari (qaror botdan ham):
POST /appeals/{id}/review/bot          {telegram_id}
POST /appeals/{id}/decide/bot          {telegram_id, decision, note}

# Scheduler
POST /appeals/sla-tick                                          # 3 kun → eslatma, 5 kun → eskalatsiya
```

Yaratishda:
- ochiq (`pending`/`in_review`) murojaatlar soni ≥5 → 400 "Avval ochiq
  murojaatlaringiz hal bo'lsin";
- `objection` uchun `topic ∈ {attendance, payroll}` va mos `ref_*` majburiy
  (sxema validatori);
- qabul qiluvchilarga xabar: `recipient_role` bo'yicha (`hr` bo'lsa-yu HR yo'q —
  Boshliqqa fallback), `Category.APPEALS`, `force_telegram=True` + inline:
  `[("🔎 O'rganyapman", f"appeal_review:{id}"), ("✅ Hal qilish", f"appeal_decide:{id}")]`
  (qaror turi va izoh keyin botda FSM orqali — callback_data qisqa qoladi,
  anketa saboqlari);
- anonim bo'lsa xabarda ism o'rniga "Anonim xodim".

Qarorda:
- idempotentlik: allaqachon hal qilingan → 400 (dasturchi override'siz — bu
  yerda ehtiyoj yo'q, keyin kerak bo'lsa qo'shiladi);
- `decision ∈ {accepted, rejected}` faqat `objection` uchun, `resolved` faqat
  `complaint` uchun — sxema tekshiradi;
- `accepted` javobida HRga ESLATMA QAYTADI (apidan matn): "E'tiroz qondirildi.
  Endi tuzatishni kiriting: davomat → Sababli kunlar / davomat tuzatish;
  oylik → Payroll tuzatish (davr qulf bo'lsa Dasturchi ochadi)" + webda
  tegishli sahifaga `data={"path": ...}` havola. AVTOMATIK tuzatish YO'Q;
- xodimga `Category.DECISIONS` xabar (`data={"path": "/me/appeals"}`);
- `AuditLog`: `appeal_created`, `appeal_review_started`, `appeal_decided`
  (before/after status, anonimlik bayrog'i bilan).

`sla-tick` (kuniga 1 marta yetadi): `pending|in_review` va `created_at` dan
≥3 kun va `sla_reminded_at IS NULL` → qabul qiluvchiga eslatma + `sla_reminded_at`
belgilanadi; ≥5 kun va `escalated_at IS NULL` → Boshliqqa + belgi. Izlar ustun
sifatida — tick necha marta chaqirilsa ham xabar bir marta (cPanel 2-jarayon
ehtiyoti).

### 3.3 Push toifalari (`api/services/push.py`, migratsiyasiz)

| Konstanta | Qiymat | Yorliq | Xodim | Rahbar |
|---|---|---|---|---|
| `WORK_LOG` | `work_log` | "Ish kundaligi eslatmasi" | ✅ | ❌ |
| `APPEALS` | `appeals` | "E'tiroz va shikoyatlar" | ✅ (o'z qarori haqida `DECISIONS` ketadi, bu toifa rahbar tomonga) | ✅ |

3 joyga yozish: `Category`, `CATEGORY_LABELS` (unutilsa `KeyError`!),
`_DEFAULTS_*`. `PERSONAL_CATEGORIES` ga `work_log` kiradi (ilova bo'lsa
Telegram takrorlanmasin); `appeals` kirmasin — qaror tugmalari faqat botda,
lekin biz baribir `force_telegram=True` beramiz.

### 3.4 Scheduler ulanishi

- `scheduler/jobs.py`: `work_log_reminder_tick()` va `appeals_sla_tick()` —
  4 qatorlik korutinlar, `call_api(...)`.
- `scheduler/main.py:_build_jobs()`: `JobSpec("work_log_reminder_tick", ...,
  IntervalTrigger(minutes=10))` va `JobSpec("appeals_sla_tick", ...,
  CronTrigger(hour=10, minute=7))`.
- `scripts/cron_tick.py:_due()`: `m % 10 == 9` (work-log — boshqa joblarning
  toq qoldiqlari bilan to'qnashmaydigan daqiqa) va kunlik `hh:mm == 10:07`
  atrofi (mavjud kunlik joblar naqshida). Endpointlar idempotent bo'lgani
  uchun ikki jarayon ham xavfsiz.

---

## 4. Bot

### 4.1 Tugmalar (`bot/keyboards.py`) — 4 qadam kontrakti

1. `BTN_WORK_LOG = "📝 Ish kundaligi"`, `BTN_APPEAL = "⚖️ E'tiroz / Shikoyat"`
2. **Ikkalasi `ALL_MENU_BUTTONS` ga** (unutilsa: FSMdagi xodim tugma bossa
   tugma matni "yozuv" bo'lib saqlanadi — UX2-W4 bug'i takrorlanadi)
3. `main_menu()`: ikkala tugma HAM barcha xodimlarga (rolsiz shart) —
   employee qatoriga; rahbarlarga ham ko'rinadi (o'zi ham xodim)
4. Handlerlar boshida `await state.clear()`

### 4.2 `bot/handlers/work_log.py`

Oqim: `BTN_WORK_LOG` → bugungi yozuvlar ro'yxati + "➕ Yozuv qo'shish" inline →
`WorkLogFSM.waiting_text` → matn (`~F.text.in_(ALL_MENU_BUTTONS)` filtri!) →
API → "Saqlandi ✅ (bugun 3-yozuv)" + yana qo'shish taklifi. `~F.text` uchun
alohida "faqat matn yuboring" handler (excused.py:311 naqshi). Validatsiya
xatosida holat SAQLANADI.

### 4.3 `bot/handlers/appeal.py`

Yozish oqimi (FSM, callback'da uzun ma'lumot YO'Q — hammasi `state.update_data`,
anketa saboqlari):
1. `BTN_APPEAL` → inline: "📣 E'tiroz (jarima/davomat/oylik)" | "📨 Shikoyat" |
   "📋 Mening murojaatlarim"
2. E'tiroz: mavzu (davomat kuni / oylik) → davomat bo'lsa oxirgi 30 kundagi
   late/absent kunlar inline ro'yxati (API beradi), oylik bo'lsa oxirgi payslip
   davri avtomatik → matn → tasdiq.
3. Shikoyat: mavzu → "Kimga: HR / Boshliq" → "Anonimmi?" (agar yoqilgan bo'lsa) →
   matn → ixtiyoriy rasm/hujjat ("O'tkazib yuborish" tugmasi bilan) → tasdiq.
4. Har matn bosqichida `~F.text.in_(ALL_MENU_BUTTONS)`; fayl bosqichida
   `F.photo | F.document` handleri alohida.

Qaror oqimi (HR/Boss):
- `appeal_review:{id}` → API `/review` → `edit_text` "🔎 O'rganilmoqda" +
  "✅ Hal qilish" tugmasi qoladi
- `appeal_decide:{id}` → inline: e'tirozda "✅ Qondirish"/"❌ Rad etish",
  shikoyatda "✔️ Hal qilindi" → `AppealDecideFSM.waiting_note`
  (state'da `appeal_id`, `decision` — JSON-mos!) → izoh matni (≥5) → API →
  `edit_text` bilan yakun (ikkinchi bosish yopiladi)
- 403/400 → `callback.answer(..., show_alert=True)` (excused naqshi)

### 4.4 Router tartibi (`bot/setup.py`) — QAT'IY

Ikkala yangi router **B zonaga** (FSM oqimlari, ~91-108 qatorlar orasiga),
**`anketa.answer_router` dan OLDIN**. Catch-all zonaga (C) mutlaqo tegilmaydi.

### 4.5 Payslip DM tugmasi

`api/routers/payroll.py:1055-1066` dagi shaxsiy DM klaviaturasiga
`("⚖️ E'tiroz bildirish", f"appeal_payslip:{period}")` qo'shiladi; bot
handleri shu callback'dan e'tiroz oqimini `ref_period` oldindan to'ldirilgan
holda boshlaydi. `callback_data` qisqa: davr 7 belgi.

---

## 5. Web

### 5.1 Rahbar sahifalari

**`pages/WorkLog.tsx`** (`/work-log`, `ManagerRoute`):
- `PageHeader` + xodim tanlagich (qidiruvli picker — `ExcusedDays.tsx:137-171`
  naqshi) + `MonthNav`
- Yuqorida qamrov kartalari (`/work-log/coverage`): har xodim — "19/22 kun",
  past qamrov qizil; bosilsa o'sha xodim ochiladi
- Tanlangan xodim: kunma-kun yozuvlar (kalendar `MonthCalendar` bilan: yozgan
  kun yashil, ish kuni-yu bo'sh — qizil, dam — kulrang) + kun bosilganda
  yozuvlar ro'yxati

**`pages/Appeals.tsx`** (`/appeals`, guard: hr/boss/dasturchi — ROP EMAS;
`ManagerRoute` ichida qo'shimcha rol tekshiruvi yoki yangi guard):
- Status/tur filtri + `DataTable`; anonimda ism "—"
- Qator amallar: "O'rganyapman" / "Hal qilish" → `ReasonDialog` (tayyor, ≥5 belgi)
- `StatusBadge.tsx` MAP'iga yangi `kind: "appeal"` ranglari
- Sidebar badge: `pending` soni (`Layout.tsx:305-312` naqshi), `Ma'muriyat`
  guruhiga "E'tiroz/Shikoyat", `Boshqaruv`ga "Ish kundaligi"

### 5.2 Xodim kabineti

**`pages/me/WorkLog.tsx`** (`/me/work-log`): `MonthNav` + kalendar + bugungi
kunga forma (textarea + "Qo'shish"), bugungi yozuvlarda ✏️/🗑 (soft),
o'tgan kunlarda faqat o'qish + 🔒 belgisi.

**`pages/me/Appeals.tsx`** (`/me/appeals`): o'z murojaatlari kartalari
(status badge, HR izohi ko'rinadi) + "Yangi murojaat" forma (tur/mavzu/matn,
anonim checkbox agar yoqiq).

### 5.3 Uch joyda sinxron (MAJBURIY checklist)

Yangi `me/` bo'limlari uchun: `web/src/lib/employeeNav.ts` +
`mobile/lib/sections.ts` (webPath — APK qayta qurilmaydi!) +
`bot/keyboards.py`. `lib/api/endpoints.ts` + `types.ts` + `queries.ts`
(`useApiMutation`, invalidate prefikslari `[["work-log"]]`, `[["appeals"]]`).

---

## 6. Nozik joylar (kodda izoh bilan mustahkamlanadi)

1. **`ALL_MENU_BUTTONS`** — ikkala yangi tugma kiritilmasa, FSM matn bosqichi
   menyu tugmasini "yozuv/izoh" deb yutib yuboradi (jonli bug tarixi bor).
2. **Router tartibi** — `anketa.answer_router`/`ai_watch.reason_text_router`
   catch-all'laridan keyin ulansa, erkin matn oqimlari buziladi.
3. **FSM ma'lumoti JSON-mos** — webhook rejimida bazaga tushadi; `date` →
   `isoformat()` str, `set` ishlatilmaydi.
4. **`dt.date` anotatsiyasi** — `date: date | None` pydantic/SQLAlchemy'da
   buziladi (`schemas.py:316-319` tarixi); har doim `import datetime as dt`.
5. **Tahrir qulfi server vaqtida** — `timeutil.today_local()`; mijoz yuborgan
   sana qabul qilinmaydi (bugunga yoziladi, nuqta).
6. **Eslatma IZ AVVAL** — `AttendanceReminder(kind="work_log")` commit →
   keyin yuborish; `IntegrityError → rollback → continue` (cPanel'da 2 jarayon!).
7. **SLA izlari ustunda** (`sla_reminded_at`, `escalated_at`) — tick idempotent.
8. **`force_telegram=True`** — inline tugmali xabarlar (appeal qarori) faqat
   botda ishlaydi; unutilsa push ketadi-yu tugma yo'q.
9. **`CATEGORY_LABELS`** to'ldirilmasa push sozlamalar sahifasi `KeyError`.
10. **Anonimlik chegarasi** — API javoblarida (`AppealOut`) anonim bo'lsa
    `user_full_name=None`; yashirish frontendda EMAS, backendda. Dasturchi
    roli uchun alohida `?reveal=1` YO'Q — kerak bo'lsa keyin, audit bilan.
11. **`/appeals` web yo'li** — `vite.config.ts` `verifixRedirect()` band yo'llar
    bilan to'qnashmaydi (`/admin`, `/verifix`) — tekshirildi, toza.
12. **Payslip DM klaviaturasi** — mavjud DM `inline_url_keyboard` ishlatsa,
    aralash (url + callback) klaviatura kerak bo'ladi — `telegram_notify.py`
    helperiga e'tibor.

---

## 7. Bosqichma-bosqich ijro rejasi

### Bosqich 1 — Ish kundaligi: poydevor + API ✅ BAJARILDI (2026-08-13)
- [x] `db/models.py`: `WorkLogSource`, `WorkLogEntry` (yumshoq o'chirish, qulf izohi)
- [x] Migratsiya `d3e4f5a6b7c8_work_log_entries.py` — qo'llandi (head), teskari yo'l ham sinaldi
- [x] `api/schemas.py`: `WorkLogBotCreate`, `WorkLogMeCreate/Patch`, `WorkLogEntryOut`, `WorkLogDayOut`, `WorkLogMonthOut`, `WorkLogCoverageRow/Out`, `WorkLogReminderTick`
- [x] `api/routers/work_log.py` (3.1 dagi hamma endpoint) + `main.py` ulash
- [x] `push.py`: `Category.WORK_LOG` (4 joy: Category, CATEGORY_LABELS, PERSONAL_CATEGORIES, _DEFAULTS_*)
- [x] `reminder-tick` + `scheduler/config.py` (`WORK_LOG_REMINDER_INTERVAL_MINUTES=10`), `jobs.py`, `main.py` JobSpec, `cron_tick.py` (`m%10==4` — bo'sh daqiqa)
- [x] Sinov: 51 tekshiruv, 0 xato — bot/web adapterlari, oylik ko'rinish, qamrov,
      tahrir/o'chirish qulfi (kechagi yozuv 403), yumshoq o'chirish, ROP maxfiylik
      cheklovi, eslatma nomzodlari + idempotentlik izi, push toifasi defaultlari.
      T- sinov ma'lumotlari to'liq tozalandi.

**Qo'shimcha qarorlar (ijro paytida):**
- `editable` bayrog'i SERVER hisoblaydi (`date == today_local()`) — bot ham, web
  ham "tahrirlash mumkinmi" qoidasini takrorlamaydi, kun chegarasi bitta joyda.
- Kun "ish kunimi" belgisi `build_month_cells`dan olinadi — davomat kalendari
  bilan AYNAN bir qoida (override > haftalik > default), ikkinchi nusxa yo'q.
- Qamrov faqat O'TGAN ish kunlari bo'yicha — kelajak kunlar "yozilmagan"
  deb hisoblanmaydi.
- Begona yozuvga 403 emas, **404** — yozuv mavjudligi ham oshkor bo'lmasin.
- Eslatma oynasi: ish tugashiga 30 daqiqa qolganidan to 2 soat keyingacha
  (cron uzoq to'xtasa ham eslatma tushib qolmaydi; UNIQUE iz kuniga bittani
  kafolatlaydi).
- Eslatma faqat BUGUN KELGAN (check-in bosgan) xodimga — kelmagan odamdan
  kundalik so'ralmaydi (u uchun tushuntirish xati mexanizmi bor).

### Bosqich 2 — Ish kundaligi: bot
- [ ] `keyboards.py` (BTN + ALL_MENU_BUTTONS + main_menu)
- [ ] `bot/handlers/work_log.py` + `setup.py` B zonaga
- [ ] `api_client.py`: `work_log_add`, `work_log_today`

### Bosqich 3 — Ish kundaligi: web
- [ ] `endpoints.ts`/`types.ts`/`queries.ts`
- [ ] `pages/WorkLog.tsx` (rahbar) + `pages/me/WorkLog.tsx`
- [ ] `App.tsx` route'lar, `Layout.tsx` NAV, `employeeNav.ts`, `mobile/lib/sections.ts`
- Deploy №1 — kundalik jonli, appeal'siz

### Bosqich 4 — Appeal: poydevor + API
- [ ] Modellar (`AppealKind/Topic/Status`, `Appeal`) + migratsiya `e4f5a6b7c8d9_appeals.py`
- [ ] Sxemalar (bot/web juftligi, kind↔decision validatorlari)
- [ ] `api/routers/appeals.py` to'liq + `main.py`
- [ ] `Category.APPEALS`, AuditLog action'lari
- [ ] `sla-tick` + scheduler/cron_tick

### Bosqich 5 — Appeal: bot
- [ ] Tugma + `bot/handlers/appeal.py` (yozish + qaror oqimlari)
- [ ] `api_client.py` funksiyalari
- [ ] Payslip DM'ga "⚖️ E'tiroz" (`payroll.py:1055-1066` + `appeal_payslip:` handler)

### Bosqich 6 — Appeal: web
- [ ] `pages/Appeals.tsx` + badge + `StatusBadge` yangi kind
- [ ] `pages/me/Appeals.tsx` + nav sinxronlari
- Deploy №2

### Bosqich 7 — ⭐ ixtiyoriy sayqal (alohida qaror bilan)
- [ ] AI oylik xulosa (kundalikdan; mavjud `ai_enabled` darvozalari bilan)
- [ ] Payroll sahifasida payslip yonida kundalik qamrovi ustuni
- [ ] Appeal statistikasi (oy kesimida: nechta, o'rtacha hal vaqti)

---

## 8. Egasidan kerakli qarorlar (defaultlar bilan — javob bo'lmasa shular)

| # | Savol | Default |
|---|---|---|
| 1 | Anonim shikoyatga ruxsat berilsinmi? | HA (faqat shikoyatda; bazada kim ekani saqlanadi, HR ko'rmaydi) |
| 2 | SLA: eslatma / eskalatsiya necha kunda? | 3 kun / 5 kun |
| 3 | Kundalik yozmaganlik uchun biror sanksiya bo'lsinmi? | YO'Q — faqat rahbar hisobotida ko'rinadi (pul mantig'iga ulanmaydi) |
| 4 | E'tiroz muddati cheklansinmi (masalan payslipdan keyin 7 kun)? | YO'Q (hozircha cheklovsiz; spam limiti 5 ochiq murojaat yetadi) |
| 5 | Kundalikni rahbarlardan kim ko'radi? | hr, rop, boss, dasturchi (Appeals esa ROP'siz: hr, boss, dasturchi) |
| 6 | Kechki eslatma vaqti? | Check-out vaqtiga 30 daqiqa qolganda (ish jadvalidan), yozmaganlarga |

---

## 9. Taxminiy hajm

| Qism | Hajm | Izoh |
|---|---|---|
| Kundalik: model+API+eslatma | ~400 qator | ExcusedDay darajasi |
| Kundalik: bot | ~200 qator | oddiy 1-bosqichli FSM |
| Kundalik: web (2 sahifa) | ~450 qator | kalendar qayta ishlatiladi |
| Appeal: model+API+SLA | ~550 qator | ExplanationRequest + qaror oqimi |
| Appeal: bot (2 oqim) | ~400 qator | eng katta bot qismi |
| Appeal: web (2 sahifa) | ~450 qator | ReasonDialog/badge tayyor |
| **Jami** | **~2450 qator** | 6 bosqich, 2 deploy nuqtasi |
