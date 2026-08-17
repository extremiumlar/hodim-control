# Oylik (ish haqi) tizimidagi 4 ta muammo — tahlil va tuzatish yo'riqnomasi

> **Bu hujjat kim uchun:** shu vazifani bajaradigan Claude agenti uchun.
> Har bir muammo: *nima ko'rinadi → ildiz sabab (fayl:qator) → qanday tuzatish
> (backend / web / bot / APK) → test → tekshirish*.
>
> **Yozilgan sana:** 2026-08-15. **Repo holati:** `86f36e2`.
> **Til:** kod izohlari va UI matnlari — o'zbekcha (loyiha qoidasi).

---

## 0. Avval o'qing — ish boshlashdan oldingi 6 ta shart

1. **CRM XAVFSIZLIK QOIDASI (QAT'IY).** Uysot CRM'ga superuser dastupi ochiq.
   Foydalanuvchining aniq ruxsatisiz CRM'dan **hech narsa o'chirilmaydi va
   tahrirlanmaydi**. Har bir o'chirish/tahrirlash uchun **alohida** ruxsat
   so'raladi. Har bir CRM o'zgarishidan keyin hisobot **majburiy**.
   Bu vazifada CRM'ga umuman tegish **shart emas** — hammasi o'z bazamizda.

2. **4-muammodagi «reset» — pulga tegadigan, qaytarib bo'lmaydigan amal.**
   Zaxirasiz va foydalanuvchining aniq «ha» javobisiz **bajarilmaydi**
   (batafsil: §5.4).

3. **Lokal testlar jonli xodimlarga xabar yuboradi.** `test.py` ishlatishdan
   oldin `api.notify.send_message` / `api.telegram_notify.*` **patch qilinishi
   shart**. Test ma'lumotlari `T-` prefiksi bilan va oxirida tozalanadi.

4. **Alembic ikki boshoqli.** Serverda migratsiya `alembic upgrade heads`
   (ko'plik!) bilan qo'llanadi, `head` bilan xato beradi. Lokalda repo
   ildizidan: `python -m alembic -c db/alembic.ini upgrade heads`
   (`cd db && alembic ...` — **noto'g'ri**, stray `db/app.db` yaratadi).

5. **Serverda CRLF tuzog'i.** `git status` doim «M» ko'rsatadi;
   `git diff --ignore-all-space` bo'sh bo'lsa mazmun bir xil →
   `git checkout -- <fayl>` xavfsiz. `git stash`/`pop` fayllarga konflikt
   belgilarini yozib qo'yadi — **ishlatilmasin**.

6. **Serverga ulanish.** SSH: port `30151`, `nuriddi5@167.235.222.200`,
   kalit `~/.ssh/id_ed25519_hodimlar_cpanel`. Skript ishga tushirish:
   `cd ~/hodimlar-tizimi && PYTHONPATH=$PWD ~/virtualenv/hodimlar-tizimi/3.11/bin/python tmp/skript.py`.
   ⚠️ **2026-08-15, 13:00 atrofida bu mashinaning IP manzili cPanel xavfsizlik
   devori (CSF/LFD) tomonidan bloklandi** — 443 va 30151 portlari yopildi
   (sayt tashqi tekshiruvda sog'lom: `{"status":"ok"}`). Sabab: qisqa vaqtda
   juda ko'p SSH seansi. **Xulosa:** SSH buyruqlarini **birlashtirib**, kamroq
   seansda bajaring. Blok o'tmasa — foydalanuvchidan cPanel → *Security* →
   *IP Blocker* orqali ochishni so'rang.

---

## 1. Tizim xaritasi (qaysi fayl nima qiladi)

| Qatlam | Fayl | Vazifasi |
|---|---|---|
| Yadro | `api/services/payroll.py` | Butun hisob: baza, jarima, qo'shimcha ish, payslip yig'ish |
| Yadro | `api/services/bonus.py` | KPI bonusi (`bonuses` jadvaliga yoziladi) |
| Yadro | `api/services/kpi_rates.py` | KPI stavkasini aniqlash (xodim > lavozim > global, tarixiy) |
| API | `api/routers/payroll.py` | `/payroll/*` — hisoblash, tasdiqlash, stavka, qo'shimcha ish |
| API | `api/routers/bonuses.py` | `/bonuses/calculate-monthly` (**faqat bot siri bilan!**) |
| Web | `web/src/pages/Payroll.tsx` | «Ish haqi» sahifasi: 4 tab |
| Web | `web/src/components/payroll/SalaryRateTab.tsx` | Oylik stavkalar |
| Web | `web/src/components/payroll/KpiRateTab.tsx` | KPI stavkalari |
| Web | `web/src/pages/PayrollSettings.tsx` | Faqat QOIDALAR: jarima + qo'shimcha ish profillari |
| Web (xodim) | `web/src/pages/me/Payroll.tsx` | «Mening oyligim» |
| Bot | `bot/handlers/payroll.py` | «💵 Mening oyligim» + «🕐 Kechikishlarim» |
| Bot | `bot/handlers/stats.py:150` | «💰 Oylik KPI hisoblash» tugmasi |
| Cron | `scripts/cron_tick.py` | 01:00 qo'shimcha ish nomzodlari, oy oxiri 23:30 KPI, keyingi oy 1-kuni payroll |
| APK | `mobile/app/home.tsx` → `mobile/app/view.tsx` | Sayt sahifalarini WebView'da ochadi |

**APK haqida muhim fakt:** mobil ilovada payroll uchun *native* ekran **yo'q**.
`home.tsx` kafel bosilganda `view.tsx` WebView'da saytning sahifasini ochadi
(`webPath`). Ya'ni **web tuzatilsa — APK ham o'z-o'zidan tuzaladi**; APK'ni
qayta yig'ish faqat kafel ro'yxati/navigatsiya o'zgarsa kerak bo'ladi.

---

## 2. MUAMMO 1 — «Sozlamalar panelidan KPI stavkani oylikka o'tkazish»

### 2.1 Talab nimani anglatadi

Ikki o'qish bor, **ikkalasi ham bajarilishi kerak**:

- **(a) Joylashuv:** KPI stavkasi *Sozlamalar*da emas, *Ish haqi* sahifasida
  bo'lsin. → **Bu allaqachon qilingan** (`86f36e2`), pastga qarang.
- **(b) Mazmun:** KPI puli **oylikka qo'shilib** chiqsin. → **Bu ishlamayapti.**
  Uch xil sabab bor.

### 2.2 (a) qismi — bajarilgan, lekin DEPLOY tekshirilsin

`86f36e2` commiti KPI tabini `Sozlamalar`dan `Ish haqi`ga ko'chirgan:

- `web/src/pages/Payroll.tsx:229-241` — 4 ta tab: Hisob-kitob / Oylik stavkalar
  / **KPI stavkalari** / Avans.
- `web/src/pages/PayrollSettings.tsx:799-811` — endi faqat «Jarima qoidasi» va
  «Qo'shimcha ish» qoldi.

**Shubha:** foydalanuvchi hali ham eski holatni ko'rayotgan bo'lishi mumkin,
chunki `86f36e2` **serverga chiqarilganmi — tasdiqlanmagan** (oxirgi tasdiqlangan
deploy `0608575` edi).

**Birinchi qadam (5 daqiqa):**

```bash
ssh -p 30151 -i ~/.ssh/id_ed25519_hodimlar_cpanel nuriddi5@167.235.222.200 "cd ~/hodimlar-tizimi && git log --oneline -1 && ls webdist/assets | grep -i payroll"
```

Agar `86f36e2` bo'lmasa — **avval deploy qiling** (§7), keyin (b) qismiga o'ting.
Ehtimol muammoning yarmi shu bilan yopiladi.

### 2.3 (b) sabab №1 — KPI puli faqat BOT orqali hisoblanadi

`bonuses` jadvaliga yozuv yaratadigan yagona yo'l:

- `api/routers/bonuses.py:25` — `POST /bonuses/calculate-monthly`,
  `dependencies=[Depends(verify_bot_secret)]` → **JWT bilan, ya'ni saytdan
  chaqirib bo'lmaydi**.
- Uni chaqiradiganlar: bot tugmasi (`bot/handlers/stats.py:150`) va cron
  (`scripts/cron_tick.py:195-196`, **oyning oxirgi kuni 23:30**).

`api/services/payroll.py:693-694` esa payslip yig'ayotganda `bonuses`
jadvalidan **tayyor qatorni o'qiydi**:

```python
bonus_row = await db.scalar(select(Bonus).where(Bonus.user_id == user.id, Bonus.period == period))
bonus_amount = _dec(bonus_row.amount) if bonus_row is not None else Decimal("0")
```

**Oqibati:** HR saytda «Hisoblash» bosadi → `bonuses` jadvalida oy uchun qator
yo'q (oy hali tugamagan) → **bonus 0** → «KPI oylikka o'tmadi».

**Tuzatish (backend):**

1. `api/routers/bonuses.py` ga **JWT bilan ishlaydigan** yangi endpoint:
   `POST /bonuses/recalculate` — `require_roles(hr, boss, dasturchi)`,
   `period` parametri, ichida mavjud `calculate_bonus` sikli qayta
   ishlatiladi (kodni **ikki marta yozmang** — umumiy funksiyaga ajrating:
   `async def _recalculate_period(db, period) -> dict`, ikkala endpoint ham
   shuni chaqirsin).
2. `api/routers/payroll.py` `calculate` (1024-qator) ichida, `run_payroll`
   dan **oldin** shu funksiyani chaqiring — ya'ni oylik hisoblash KPI'ni
   o'zi yangilab olsin. Shunda tartib xatosi umuman yo'qoladi.
   ⚠️ Bu qo'shimcha yuk — §4 dagi «fon rejimi» tuzatishi bilan **birga**
   qilinsin, aks holda sayt yanada uzoq qotadi.

**Tuzatish (web):** «Ish haqi» sahifasidagi «Hisoblash» tugmasi ostiga kichik
izoh: *«KPI bonusi ham shu paytda qayta hisoblanadi»*. Alohida tugma **shart
emas** — kam tugma, kam xato.

**Tuzatish (bot):** o'zgarish shart emas; mavjud «💰 Oylik KPI hisoblash»
tugmasi qoladi (zaxira yo'l sifatida foydali).

### 2.4 (b) sabab №2 — stavka «kelajakdan» kuchga kiradi

- `api/services/bonus.py:66` — stavka **oy boshiga** aniqlanadi:
  `rate = await resolve_kpi_rate(db, user, metric, period_start)`.
- `web/src/components/payroll/KpiRateTab.tsx:55` — formadagi «kuchga kirish
  sanasi» **BUGUNGI kun** bilan to'ldirilgan.

**Oqibati:** HR 15-avgustda stavka kiritadi → `effective_from = 2026-08-15` →
avgust uchun `resolve_kpi_rate(..., 2026-08-01)` **`None`** qaytaradi →
o'sha ko'rsatkich bo'yicha bonus **0** va `breakdown.missing_rates` da
ko'rinadi. HR uchun bu «stavka kiritdim, lekin ishlamadi» bo'lib ko'rinadi.

**Tuzatish (web) — eng kam xatarli:**

- `KpiRateTab.tsx:55` va `SalaryRateTab.tsx:201` da default qiymat
  **joriy oyning 1-kuni** bo'lsin:
  ```ts
  const [effectiveFrom, setEffectiveFrom] = useState(format(startOfMonth(new Date()), "yyyy-MM-dd"));
  ```
- Sana maydoni ostiga izoh: *«Odatda oy boshi qo'yiladi — shu oyning butun
  hisobiga qo'llanadi»*.
- Agar tanlangan sana joriy oy boshidan **keyin** bo'lsa — sariq ogohlantirish:
  *«Bu stavka {oy} hisobiga KIRMAYDI (u oy boshida aniqlanadi)»*.

**Tuzatish (backend) — ixtiyoriy, lekin tavsiya etiladi:** `resolve_kpi_rate`
hech narsa topmasa, **o'sha oy ichida** boshlangan eng erta stavkani zaxira
sifatida olish. Bu «kech kiritilgan stavka» holatini o'z-o'zidan tuzatadi.
Qaror foydalanuvchiga qo'yilsin (§8, savol 1) — sukut bo'yicha **qilmang**,
chunki bu tarixiy hisobni o'zgartiradi.

### 2.5 (b) sabab №3 — bonus faqat `employee` roliga hisoblanadi

`api/routers/bonuses.py:31-33` — `User.role == Role.employee.value`.
Payroll esa `PAYROLL_TRACKED_ROLES` (Boshliqdan tashqari **hamma**, ya'ni
HR/ROP/dasturchi ham) bo'yicha payslip yasaydi
(`api/services/payroll.py:65`). Ya'ni HR/ROP payslip'ida bonus qatori
**hech qachon** paydo bo'lmaydi.

**Tuzatish:** ikkala joyda qamrovni bittaga keltiring. Tavsiya: bonusni ham
`PAYROLL_TRACKED_ROLES` bo'yicha hisoblang, lekin `metrics_for(user)` bo'sh
bo'lsa — jim o'tkazib yuboring (allaqachon shunday ishlaydi).

### 2.6 Testlar (majburiy)

`test.py` ga qo'shing (mavjud payroll bloki yonига):

- «KPI: oy o'rtasida kiritilgan stavka ogohlantirish beradi» (web bo'lsa —
  backend darajasida `missing_rates` bo'sh emasligi).
- «KPI: `/bonuses/recalculate` HR uchun 200, oddiy xodimga 403».
- «Oylik hisoblash KPI'ni ham yangilaydi» — `bonuses` qatori yo'q holatda
  `calculate` chaqirilsa, payslip'da `bonus_amount > 0` chiqsin.

---

## 3. MUAMMO 2 — «Qo'shimcha ishni avtomat hisoblab, vaqtini qo'shib-ayirib umumiy berish»

### 3.1 Yaxshi xabar: mantiq allaqachon yozilgan

`86f36e2` da `detect_overtime_candidates` (`api/services/payroll.py:937-1023`)
**sof farq**ga o'tkazilgan:

```python
scheduled_minutes = work_minutes(_hm_to_min(start), _hm_to_min(end))
delta_minutes = (att.worked_minutes or 0) - scheduled_minutes   # manfiy = kam ishlagan
```

va `compute_overtime` (551-622) manfiy qiymatni oy bo'yicha ortiqchadan
ayiradi; cheklovlar absolyut qiymatga qo'llanadi. Ya'ni **«qo'shib-ayirib
umumiy»** talabi bajarilgan.

### 3.2 Nega baribir ishlamayapti — 3 ta to'siq

**To'siq A — profil yo'q/o'chiq (eng ehtimoliy).**
`db/models.py:1645` — `OvertimeProfile.enabled` default **`False`**, profil
**har bir xodim uchun alohida** (`user_id` unique). `compute_overtime` esa:

```python
if profile is None or not profile.enabled:   # api/services/payroll.py:562
    return result   # 0 daqiqa, 0 so'm
```

`detect_overtime_candidates` ham faqat `enabled=True` profillar bo'yicha
nomzod yaratadi. **Ya'ni HR har bir xodimga qo'lda profil yaratmaguncha,
qo'shimcha ish umuman hisoblanmaydi.**

*Tekshirish:*
```sql
select count(*) from overtime_profiles where enabled = true;
```

**Tuzatish (tanlov, foydalanuvchidan so'raladi — §8 savol 2):**
- *Variant 1 (tavsiya):* `PayrollSettings` → «Qo'shimcha ish» tabiga
  **«Hammaga yoqish»** tugmasi + global default profil tushunchasi
  (`scope='global'` naqshi `FinePolicy` dagidek). Kod: `resolve_overtime_profile(db, user)`
  — xodim profili yo'q bo'lsa global profilga tushsin.
- *Variant 2:* migratsiya bilan barcha faol xodimga `enabled=True` profil
  yaratish (bir martalik, `multiplier` majburiy — qiymatini foydalanuvchi
  aytadi).

**To'siq B — cron kechasi 01:00 da ishlaydi.**
`scripts/cron_tick.py:178` + `scheduler/config.py:148-149`
(`OVERTIME_AUTO_DETECT_HOUR=1`). Ya'ni bugungi qo'shimcha ish **ertaga
ertalab** paydo bo'ladi. Bu normal, lekin HR buni bilmasa «ishlamayapti»
deb o'ylaydi.

*Tuzatish:* «Qo'shimcha ish» sahifasiga izoh — *«Kunlik farq ertasi kuni
01:00 da avtomatik yoziladi»* + **«Hozir hisoblab ber»** tugmasi
(mavjud `POST /payroll/overtime/auto-detect` ni JWT bilan ham ochish kerak —
hozir u faqat bot siri bilan, `api/routers/payroll.py:1456`).

**To'siq C — tasdiq talab qilinadi.**
`compute_overtime` faqat `status='approved'` yozuvlarni oladi; nomzodlar
`pending` bo'lib tug'iladi. `86f36e2` izohida bu «egasining qarori» deb
yozilgan, lekin hozirgi talab («avtomat hisoblab bersin») teskarisiga
ishora qilishi mumkin.

*Tuzatish (tavsiya):* tasdiq **qolsin** (pul xavfsizligi), lekin:
1. «Qo'shimcha ish» sahifasiga **«Hammasini tasdiqlash»** (bulk) tugmasi;
2. `OvertimeProfile` ga `auto_approve: bool = False` ustuni — HR xohlasa
   xodim bo'yicha avtomatik tasdiqni yoqadi (migratsiya + UI checkbox).
3. Oylik hisoblashdan oldin `preflight` allaqachon «tasdiqlanmagan
   qo'shimcha ish» ni ko'rsatadi (`api/routers/payroll.py:997-1012`) — uni
   ko'rinarli qiling.

### 3.3 Qamrab olinmagan holat (hujjatlashtiring, tuzatish shart emas)

Tungi smena: `check_out` ertasi kunga o'tsa, hisob noto'g'ri
(`api/services/payroll.py:948-952` da izohlangan). Hozircha xavfsiz tomonga
og'adi (nomzod yaratilmaydi).

### 3.4 Testlar

- profilsiz xodim → `overtime_amount == 0` (regressiya qo'riqchisi);
- `+90 daq` → to'g'ri summa; `−105 daq` → manfiy summa;
- aralash kunlar: `+120 / −30` → `+90 daq`;
- kunlik cheklov ikki tomonga simmetrik;
- `auto_approve=True` bo'lsa nomzod darhol `approved` (agar qo'shsangiz).

---

## 4. MUAMMO 3 — «Oylik belgilash panelida sayt qotib qoladi»

### 4.1 Ildiz sabab: bitta Passenger ishchisi + og'ir so'rov

Production'da **konkurentlik = 1** (cPanel Passenger, `a2wsgi` + 1 ishchi).
Ya'ni **bitta** uzoq so'rov butun saytni (va API'ni) navbatga qo'yadi.

`POST /payroll/{period}/calculate` (`api/routers/payroll.py:1024-1065`) shu
so'rov ichida:

1. `run_payroll` — har bir xodim uchun `build_payslip`, taxminan **12 ta SQL
   so'rov/xodim** (`collect_attendance` → `month_schedule` 2, `resolve_policy`
   1-3, `resolve_rate` 1, `_first_rate` 1, overtime profil 1, overtime
   yozuvlari 1, `resolve_rate` yana 1, bonus 1, tuzatmalar 1).
   20 xodim ≈ **240 so'rov**.
2. Keyin **har bir rahbarga xabar**: `notify_user` → FCM push **va** Telegram
   `sendMessage` (`api/notify.py:77-89`), har biri tarmoq I/O, timeout 10 s.

Ya'ni tugma bosilgandan keyin ishchi 10-40 soniya band → **sayt qotadi**.

### 4.2 Ikkinchi darajali sabab: sahifa ikkita og'ir so'rov yuboradi

- `web/src/pages/Payroll.tsx:54` — `usePayrollPreflight(period)`
- `web/src/components/payroll/SalaryRateTab.tsx:196` — `usePayrollPreflight(currentMonthKey())`

Ikkalasi **turli kalit** bilan (`period` ≠ joriy oy bo'lsa) → keshdan
foydalanmaydi, ikki marta og'ir `collect_readiness` ishlaydi.

### 4.3 Tuzatish — 3 qadam

**Qadam 1 (eng muhim): hisoblashni FON rejimiga o'tkazish.**

Loyihada tayyor naqsh bor: `scripts/cron_tick.py:_run_service_inprocess`
(lock fayl + alohida jarayon). Payroll uchun:

1. `PayrollPeriod` ga holat ustunlari qo'shing (migratsiya):
   `calc_state: str` (`idle|running|done|error`), `calc_started_at`,
   `calc_progress: int`, `calc_total: int`, `calc_error: str|None`.
2. `POST /payroll/{period}/calculate` **darhol** `202` qaytarsin va ishni
   FastAPI `BackgroundTasks` ga bersin (webhook'dagi
   `uysot_webhook.process_log_entry` naqshi: o'z sessiyasini ochadi).
   ⚠️ Passenger'da fon vazifasi ham **o'sha ishchida** ishlaydi — shuning
   uchun eng to'g'ri yechim: **cron orqali** bajarish
   (`api/services/cron_jobs.py` ga `payroll_tick`, `scripts/cron_tick.py` da
   har daqiqa) — u alohida jarayon va Passenger'ga umuman tegmaydi.
   Tugma esa faqat `calc_state='running'` deb belgilaydi (yengil UPDATE).
3. Web: `GET /payroll/{period}/status` ni 3 soniyada bir so'rab, progress
   ko'rsatsin («12/20 xodim»). Tugma `running` paytida bloklansin.

**Qadam 2: xabarlarni so'rovdan chiqarish.**
`calculate` ichidagi `notify_user` sikli fon ishiga ko'chsin (yuqoridagi
cron ichida, hisob tugagach). Telegram/FCM timeout'lari endi saytni
qotirmaydi.

**Qadam 3: preflight'ni bir marta so'rash.**
`SalaryRateTab` dagi `usePayrollPreflight(currentMonthKey())` ni olib
tashlang — «stavkasi yo'qlar» ro'yxatini `Payroll.tsx` allaqachon olgan
`preflight` natijasidan **prop orqali** bering. Yoki ikkalasida bir xil
`period` kalitini ishlating (react-query keshni bo'lishadi).

**Qo'shimcha (arzon va foydali):** `run_payroll` ichidagi `resolve_rate`
ikki marta chaqiriladi (`build_payslip:678` va `compute_overtime:611`) —
bittasini parametr sifatida uzating. Shuningdek `resolve_policy`ni bir
marta yuklab, hamma xodimga umumiy lug'at qilib bering.

### 4.4 Tekshirish

- Serverda: `tail -f ~/hodimlar-tizimi/logs/cron.log` da `payroll tick` chiqsin.
- Hisoblash paytida boshqa sahifa (masalan `/attendance`) **qotmasin** —
  brauzerda ikkinchi tab bilan tekshiring.
- `test.py`: «calculate darhol 202 qaytaradi», «status endpointi progress
  ko'rsatadi», «ikki marta ishga tushirib bo'lmaydi (409)».

---

## 5. MUAMMO 4 — «Ish haqi noto'g'ri hisoblanyapti + 1-avgustgacha reset»

### 5.1 Ildiz sabab №1 (ENG KATTA) — kelajakdagi kunlar «kelmagan» deb sanaladi

`api/services/payroll.py:271-275`:

```python
elif att is None:
    status = "absent"
```

`month_schedule` (176-220) **butun oyni** (1-31) qaytaradi va **bugungi kun
bo'yicha kesish YO'Q**. Ya'ni 15-avgustda avgust hisoblansa, 16-31 avgust
kunlari `absent` bo'lib sanaladi.

Agar jarima qoidasida `absent_mode='deduct_daily'` bo'lsa
(`compute_base:518-542`), har bir «kelmagan» kun uchun **kunlik ulush
oylikdan ayiriladi**:

> 5 000 000 so'm, 22 ish kuni, 15-avgustda hisoblandi → qolgan ~11 kun
> «kelmagan» → −2 500 000 so'm. **Oylik ikki barobar kam chiqadi.**

**Tuzatish (backend, majburiy):**

`collect_attendance` da (yoki `month_schedule` da) **kesish** qo'shing:

```python
# Kelajak kunlari hali "kelmagan" emas — ular HALI KELMAGAN.
# Oy tugamagan bo'lsa, bugundan keyingi kunlar hisobga umuman kirmaydi.
today = today_local()
if d > today:
    status = "future"      # yangi holat
```

va uni hamma joyda hisobdan chiqaring:
- `compute_base` — `full_scheduled` va `prorated_scheduled` **faqat
  `d <= today`** kunlarni sanasin (aks holda prorata noto'g'ri bo'ladi);
- `compute_late_fine` / `compute_absent_fine` — `future` kunlarni o'tkazib
  yuborsin;
- `fields.scheduled_days` / `scheduled_minutes` — «shu kungacha» ma'nosida.

⚠️ **Nozik joy:** oy **tugagach** hisoblansa, xatti-harakat avvalgidek
qolishi kerak (butun oy). Shuning uchun shart aynan `d > today` bo'lsin,
`period` tugagan bo'lsa `today` oy oxiridan katta va hech nima kesilmaydi.

**Payslip'da ko'rsatish:** oy tugamagan bo'lsa sarlavhada
*«Oraliq hisob — 15-avgustgacha»* deb yozilsin (web, bot, xodim kabineti),
aks holda xodim yarim oylik summani ko'rib xavotirga tushadi.

### 5.2 Ildiz sabab №2 — stavka bugungi sana bilan kiritiladi (prorata)

`compute_base:475-491` — `monthly` stavkada prorata `first_rate.effective_from`
dan boshlanadi:

```python
effective_from = first_rate.effective_from if first_rate is not None else period_start
prorate_from = max(period_start, effective_from)
prorated_scheduled = sum(1 for d in days if d["is_working"] and d["date"] >= prorate_from)
```

`SalaryRateTab.tsx:201` — forma default sanasi **bugun**. HR 14-avgustda
stavka kiritsa → avgust `~9/22` ulushga proratalanadi → **yana yarim oylik**.

**Tuzatish:** §2.4 dagi bilan bir xil — default sana **oy boshi**, va
tanlangan sana oy boshidan keyin bo'lsa ogohlantirish:
*«Bu xodimga avgust oyligi to'liq emas, {N}/{M} kun bo'yicha hisoblanadi»*.

Qo'shimcha: `SalaryRateTab` da «Ishga kirgan sana» (`users.hire_date`, u
allaqachon bor) bilan solishtirib, agar xodim oldin ishga kirgan bo'lsa —
sanani oy boshiga tushirishni **taklif qiling**.

### 5.3 Ildiz sabab №3 — «kelmagan kun» yozuvlari umuman bo'lmasligi mumkin

`write_absent_records` (`api/services/attendance_digest.py:543`) kechqurun
`absent` yozuvlarini yozadi. Agar u ishlamagan kunlar bo'lsa (tizim yangi
ishga tushgan, cron o'chgan), `att is None` → yana `absent`. Bu 5.1 dagi
kesish bilan qisman yopiladi, lekin **o'tgan** kunlar uchun emas.

**Tuzatish:** `preflight` ga yangi guruh — *«Davomat yozuvi umuman yo'q
kunlar»* (xodim × sana) — HR hisoblashdan oldin ko'rsin.

### 5.4 «1-avgustgacha hamma ma'lumot reset bo'lsin» — XAVFLI AMAL

> ⛔ **Bu bo'lim foydalanuvchining aniq, yozma «ha» javobisiz bajarilmaydi.**
> Ma'lumot o'chirilsa qaytarib bo'lmaydi (zaxiradan tiklashdan tashqari).

**Qadam 0 — zaxira (majburiy).**
```bash
ssh ... "cd ~/hodimlar-tizimi && bash deploy/cpanel/backup_db.sh && ls -lh backups | tail -3"
```
Zaxira faylini **lokalga ham** tushiring (`scp`). Zaxirasiz keyingi qadamga
o'tilmaydi.

**Qadam 1 — nima o'chishini ANIQLASH (dry-run).**
Skript `tmp/reset_dryrun.py` (faqat `SELECT count(*)`), quyidagi jadvallar
bo'yicha `< 2026-08-01` qatorlar sonini chiqarsin:

| Jadval | Ustun | Toifa | Tavsiya |
|---|---|---|---|
| `attendance` | `date` | Davomat | ✅ o'chirilsin |
| `daily_results` | `date` | KPI manbasi | ✅ o'chirilsin |
| `payslips` + `payslip_items` | `period < '2026-08'` | Pul | ✅ o'chirilsin |
| `payroll_periods` | `period < '2026-08'` | Pul | ✅ o'chirilsin |
| `bonuses` | `period < '2026-08'` | Pul | ✅ o'chirilsin |
| `overtime_entries` | `date` | Pul | ✅ o'chirilsin |
| `payroll_adjustments` | `period < '2026-08'` | Pul (avans!) | ⚠️ **alohida so'ralsin** |
| `excused_days` | `date` | Davomat | ✅ o'chirilsin |
| `explanation_requests`, `attendance_reminders` | `date` | Yordamchi | ✅ o'chirilsin |
| `work_log_entries` | `date` | Kundalik | ⚠️ so'ralsin (bu pul emas) |
| `hourly_target`, `hourly_actual`, `shortfall_reason` | `date` | AI/reja | ✅ o'chirilsin |
| `lead_events`, `lead_stage_daily`, `operator_calls_daily`, `hot_lead` | `detected_at`/`date` | CRM statistikasi | ⚠️ **so'ralsin** — tashrif tarixi yo'qoladi |
| `mobilograf_videos` | `sent_at` | KPI manbasi | ⚠️ so'ralsin |
| `audit_logs` | `created_at` | Tarix | ❌ **TEGILMASIN** (huquqiy iz) |
| `salary_rates`, `kpi_rates`, `norms`, `fine_policies`, `overtime_profiles` | — | Sozlama | ❌ **TEGILMASIN** (bular «ma'lumot» emas, qoida) |
| `users`, `positions`, `offices` | — | Ma'lumotnoma | ❌ **TEGILMASIN** |

**Qadam 2 — o'chirish tartibi (FK bo'yicha).**
`payslip_items` → `payslips` → `payroll_periods`; qolganlari mustaqil.
Hammasi **bitta tranzaksiyada**, oxirida `count` qayta o'qilib hisobot
chiqarilsin.

**Qadam 3 — «tizim boshlanish sanasi» qo'yish (takror xatoning oldini oladi).**
`.env` ga `PAYROLL_START_PERIOD=2026-08` va `api/services/payroll.py`
`run_payroll` boshida:

```python
if period < PAYROLL_START_PERIOD:
    raise PayrollLocked(f"«{period}» — tizim boshlanishidan oldingi davr, hisoblanmaydi")
```

Web'dagi oy tanlagich ham shu oydan oldingini ko'rsatmasin.

**Qadam 4 — audit.** O'chirishdan keyin `AuditLog` ga
`action="data_reset_before_august"`, `after={"jadvallar": {...}, "jami": N}`.

**Qadam 5 — qayta hisoblash.** `2026-08` uchun:
KPI (`/bonuses/recalculate`) → qo'shimcha ish auto-detect (1-14 avgust
kunlari uchun sikl) → `POST /payroll/2026-08/calculate` → natijani
**qo'lda 2-3 xodim bo'yicha tekshiring** (asosiy oylik, ish kunlari soni,
jarima, bonus).

### 5.5 Testlar (majburiy)

- «Oy o'rtasida hisoblansa kelajak kunlar `absent` sanalmaydi» — 15-kunda
  hisoblab, `absent_days == 0` (agar o'tgan kunlarda hammasi kelgan bo'lsa);
- «Oy tugagach butun oy hisoblanadi» (regressiya: kesish o'tmishga tegmasin);
- «Oy boshidan kuchga kirgan stavka to'liq oylik beradi» (prorata yo'q);
- «`PAYROLL_START_PERIOD` dan oldingi davr → 409».

---

## 6. Nima QILINMASIN (chegaralar)

- CRM'ga (Uysot) yozish/o'chirish — **umuman kerak emas**.
- `audit_logs`, sozlama jadvallari (`salary_rates`, `kpi_rates`,
  `fine_policies`, `overtime_profiles`, `norms`) o'chirilmaydi.
- `fine_applies_to` mantig'i (bonusdan avval/keyin) — **tegilmasin**,
  u yakuniy `net` ga ta'sir qilmaydi (`payroll.py:713-723` da izohlangan).
- APK kodini o'zgartirish — payroll WebView orqali ishlaydi, **shart emas**.

---

## 7. Bajarish tartibi (tavsiya etilgan ketma-ketlik)

| № | Ish | Qatlam | Hajm | Xatar | Holat |
|---|---|---|---|---|---|
| 1 | `86f36e2` deploy qilinganini tekshirish | deploy | 5 daq | past | ✅ |
| 2 | **§5.1** kelajak kunlari `absent` sanalmasin | backend | ~1 soat | **yuqori ta'sir** | ✅ `d151269` |
| 3 | **§2.4/§5.2** sana defaultlari + ogohlantirish | web | 30 daq | past | ✅ `915358f` |
| 4 | **§4.3** hisoblashni fon rejimiga | backend+web | ~3 soat | o'rta | ✅ `1cda82c`, `f221050` |
| 5 | **§2.3** KPI qayta hisoblash JWT bilan + calculate ichida | backend | 1 soat | o'rta | ✅ `15b583a` |
| 6 | **§3.2** qo'shimcha ish profilini yoqish yo'li | backend+web | 1-2 soat | o'rta | ✅ `be3b05e`, `b79b04a` |
| 7 | **§5.4** reset (faqat ruxsatdan keyin) | ma'lumot | 1 soat | **eng yuqori** | ⛔ RUXSAT KUTILYAPTI |
| 8 | 2026-08 ni qayta hisoblab, qo'lda tekshirish | — | 30 daq | — | ✅ (quyida) |

### 2026-08 tekshiruvi natijasi (2026-08-17)

Jonli bazada qayta hisoblandi, MUSTAQIL usulda solishtirildi:

- **kelmagan kun ayirmasi** — 7 xodimda formula bo'yicha to'g'ri
  (`stavka ÷ ish kuni × kelmagan`), chetlashish 0 (yaxlitlash 100 so'mgacha);
- **«kelmagan» deb belgilangan birorta kunda ham check-in YO'Q** — ya'ni
  ayirmalar o'rinli, tizim yo'qolgan check-in uchun pul kesmagan;
- **net = qatorlar yig'indisi** — 13 payslipda nomuvofiqlik 0.

⚠️ **Ochiq qolgan ma'lumot kamchiliklari (kod emas, sozlama):**

1. **KPI stavkalari 0 ta** — `kpi_rates` jadvali BO'SH. «KPI oylikka o'tmadi»
   shikoyatining oxirgi sababi shu: kod endi to'g'ri ishlaydi, lekin
   ko'paytiriladigan stavka yo'q. Avgustdagi haqiqiy hajm: Firuzabonu
   1639 suhbat / 25 tashrif, Shahnoza 804/12, Hayot 526/4, Albina 43/6.
2. **4 xodimda lavozim biriktirilmagan** (Abdurahmon, Farida, Otabek,
   Sanobar) — `metrics_for` bo'sh qaytadi, ya'ni ularga KPI umuman
   hisoblanmaydi.
3. **Lavozim ko'rsatkichlari shubhali**: HR, IT, Boss, Prorab, Mashenist
   kranchik lavozimlarida `suhbat`/`tashrif` (va video) turibdi.
4. **Samandar va Begzod** — faolsizlantirilgan, payslip'lari 0 so'm bilan
   eskirgan holda qolgan (pul zarari yo'q).

**Har bir qadamdan keyin:** `test.py` to'liq ishlatilsin (hozirgi holat:
**503 OK, 0 FAIL** — bu chiziq pasaymasligi kerak).

### Deploy (har safar bir xil)

```bash
git add -A && git commit -m "..." && git push origin xavfsizlik-tuzatishlar
```
Keyin `master` ga merge + push, so'ng **bitta** SSH seansida:

```bash
ssh -p 30151 -i ~/.ssh/id_ed25519_hodimlar_cpanel nuriddi5@167.235.222.200 "cd ~/hodimlar-tizimi && git pull --ff-only && PYTHONPATH=\$PWD ~/virtualenv/hodimlar-tizimi/3.11/bin/python -m alembic -c db/alembic.ini upgrade heads && touch tmp/restart.txt && bash deploy/cpanel/keepalive_bot.sh"
```

⚠️ `git pull` va `alembic upgrade` **bitta buyruqda** — orada ~3 daqiqalik
«ustun yo'q» xatolari oynasi bo'lgan (2026-08-14 da jonli uchradi).

Bot yangi kodni olishi uchun jarayonni to'xtatish kerak:
`pkill -f 'python3.11_bin -m bot'` (buyruq satrida `bot.main` matni
**bo'lmasin** — `keepalive_bot.sh` dagi `pgrep -f "bot\.main"` o'z ssh
buyrug'ingizni ham topib, botni qayta ishga tushirmaydi).

---

## 8. Foydalanuvchidan so'raladigan qarorlar

1. **KPI stavkasi kech kiritilsa** — o'sha oyga qo'llansinmi (zaxira qoida),
   yoki keyingi oydan boshlansinmi? *(Tavsiya: keyingi oydan; hozirgi oy uchun
   HR sanani oy boshiga qo'ysin.)*
2. **Qo'shimcha ish tasdiqlashi** — qolsinmi yoki avtomatik tasdiqlansinmi?
   *(Tavsiya: qolsin + «Hammasini tasdiqlash» tugmasi + xodim bo'yicha
   `auto_approve` bayrog'i.)*
3. **Reset qamrovi** — CRM statistikasi (`lead_events`, `lead_stage_daily`,
   `operator_calls_daily`), `work_log_entries` va `payroll_adjustments`
   (avans!) ham o'chirilsinmi?
4. **Avgust oyligi qachon to'liq hisoblansin** — oy tugagach (1-sentabr
   ertalab, cron allaqachon shunday) yoki HR xohlagan paytda oraliq
   hisob sifatidami?

---

## 9. Foydali diagnostika buyruqlari

**Jonli bazada (faqat o'qish), bitta SSH seansida:**

```python
# tmp/diag_payroll.py — PYTHONPATH=$PWD venv python bilan ishga tushiring
import asyncio
from sqlalchemy import text
from db.base import async_session

Q = [
 ("stavkalar", "select u.full_name, sr.amount, sr.pay_basis, sr.effective_from "
  "from salary_rates sr join users u on u.id=sr.user_id where sr.deleted_at is null "
  "order by sr.effective_from"),
 ("kpi stavkalari", "select scope, scope_id, metric, amount, effective_from from kpi_rates"),
 ("overtime profillari", "select count(*) filter (where enabled) as yoqilgan, count(*) as jami from overtime_profiles"),
 ("overtime yozuvlari", "select status, count(*), sum(minutes) from overtime_entries group by status"),
 ("bonuslar", "select period, count(*), sum(amount) from bonuses group by period order by period"),
 ("payslip 2026-08", "select u.full_name, p.base_amount, p.absent_days, p.worked_days, "
  "p.scheduled_days, p.bonus_amount, p.overtime_amount, p.net from payslips p "
  "join users u on u.id=p.user_id where p.period='2026-08' order by u.full_name"),
 ("avgustgacha davomat", "select count(*) from attendance where date < '2026-08-01'"),
 ("jarima qoidasi", "select scope, absent_mode, absent_fine, free_late_minutes_per_month, "
  "fine_per_day, monthly_cap_percent from fine_policies where is_active"),
]

async def main():
    async with async_session() as s:
        for nom, q in Q:
            print(f"\n=== {nom} ===")
            for r in (await s.execute(text(q))).all():
                print("  ", tuple(r))

asyncio.run(main())
```

**Eng muhim 3 ta savol shu chiqishdan javob topadi:**
1. `overtime_profiles.yoqilgan == 0` → 3-muammoning sababi tasdiqlanadi.
2. `salary_rates.effective_from` avgust o'rtasida → 4-muammo (prorata).
3. `payslips.absent_days` katta va `worked_days` kichik → 4-muammo
   (kelajak kunlari).

---

## 10. Xulosa — bir jumlada har bir muammo

1. **KPI oylikka tushmayapti**, chunki bonus faqat bot/cron orqali
   hisoblanadi va stavka bugungi sana bilan kiritilib, oy boshida topilmaydi.
2. **Qo'shimcha ish avtomat emas**, chunki `OvertimeProfile.enabled` default
   `False` va profil har bir xodimga qo'lda yaratiladi (mantiqning o'zi
   `86f36e2` da to'g'rilangan).
3. **Sayt qotadi**, chunki oylik hisoblash bitta Passenger ishchisida,
   so'rov ichida, ustiga Telegram/push yuborishlari bilan bajariladi.
4. **Ish haqi noto'g'ri**, chunki oy o'rtasida hisoblanganda **kelajakdagi
   kunlar «kelmagan»** deb sanaladi va stavka sanasi bugundan boshlanib
   oylikni proratalab yuboradi; 1-avgustgacha bo'lgan eski ma'lumot esa
   hisobga aralashib turibdi.
