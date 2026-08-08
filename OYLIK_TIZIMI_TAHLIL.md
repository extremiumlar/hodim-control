# Oylik / jarima / KPI / qo'shimcha ish — arxitektura tahlili

**Sana:** 2026-08-08 · **Tekshirgan:** Claude (agent)

**Holat:** BUG-1 TUZATILDI (`1409fd1`). Qolgan bandlar navbatda —
egasining qarorlari 8.5-bo'limda.

Bu hujjat egasining topshirig'i bo'yicha tuzildi: «bu bo'limlar deyarli
ishlamayapti, buglarga to'la, hatto oylikni ham belgilay olmayapmiz — shuni
arxitektura jihatdan to'liq ko'rib chiq».

---

## 0. Metodika — bu xulosalar qayerdan

Taxmin bilan emas, **ishlayotgan tizimda sinab** aniqlandi:

1. Lokal API ko'tarildi (`uvicorn`, 8020-port), sinov xodimi `T-PayEmp`
   yaratildi: 5 000 000 so'm stavka, du–ju 09:00–18:00 jadval, iyul oyida
   3 kun kechikish (20 / 45 / 60 daq), 1 kun kelmaslik.
2. HR tokeni bilan butun oqim uchidan-uchiga o'tkazildi: stavka → jarima
   qoidasi → preflight → hisoblash → payslip → tasdiqlash.
3. Har bir 500/422 uchun server traceback'i o'qildi.
4. Jonli production bazasida davomat holatlari taqsimoti tekshirildi
   (`present 79 / absent 37 / late 19 / weekend 3 / excused 2`).
5. Barcha sinov ma'lumotlari tozalandi (T- xodim, payslip, davr, audit).

**Muhim:** birinchi urinishda men ham xato xulosaga keldim — sinov
ma'lumotini `status='present' + late_minutes>0` deb yozgandim va «jarima
umuman ishlamayapti» degan natija chiqdi. Aslida tizim `status='late'`
yozadi va jarima **ishlaydi**. Quyidagi xulosalar shu tuzatishdan keyingi.

---

## 1. Qisqacha xulosa

Arxitektura **yomon emas** — ma'lumot modeli puxta o'ylangan (tarixiy
stavka, snapshot'li payslip, 3 darajali jarima qoidasi, qulflanadigan davr).
Muammo modelda emas, **uchta joyda**:

| # | Nima | Og'irligi |
|---|---|---|
| A | Sozlamalarni **tahrirlash** 500 beradi (bir marta yaratasiz, keyin qamalib qolasiz) | 🔴 Kritik |
| B | KPI stavkalari **kodda qattiq yozilgan**, saytdan sozlab bo'lmaydi | 🔴 Kritik |
| C | HR va Boshliq huquqlari **aynan bir xil** — «HR belgilaydi, Boshliq tasdiqlaydi» yo'q | 🟠 Muhim |

Qolganlari — joylashuv (UX) va yetishmayotgan qulayliklar.

---

## 2. 🔴 BUG-1 — Sozlamalarni tahrirlab bo'lmaydi (Decimal → audit JSON)

**Bu eng katta bug va «hech narsa ishlamayapti» hissining asosiy sababi.**

### Nima bo'ladi

| Amal | 1-marta | 2-marta (tahrir) |
|---|---|---|
| `PUT /payroll/policies` (jarima qoidasi) | ✅ 200 | ❌ **500** |
| `PUT /payroll/overtime-profiles/{id}` | ✅ 200 | ❌ **500** |

Ya'ni jarima qoidasini yoki qo'shimcha ish profilini **bir marta yaratasiz,
keyin uni hech qachon o'zgartira olmaysiz**. Foydalanuvchi uchun bu «tugma
ishlamaydi» bo'lib ko'rinadi.

### Sabab

Server traceback'i:

```
sqlalchemy.exc.StatementError: (builtins.TypeError)
Object of type Decimal is not JSON serializable
[SQL: INSERT INTO audit_logs (...) VALUES (...)]
[parameters: {'action': 'overtime_profile_upserted',
  'before': {..., 'multiplier': Decimal('1.50'), ...}}]
```

Tahrirlashda kod eski holatning **snapshot**ini olib audit jurnaliga yozadi.
Snapshot ORM ustunlaridan to'g'ridan-to'g'ri olinadi, ya'ni ichida `Decimal`
(`Numeric` ustunlar) va `date` turlari bo'ladi — SQLAlchemy'ning JSON ustuni
esa oddiy `json.dumps` ishlatadi va bu turlarni tushunmaydi.

Aniq joylari:

- [api/routers/payroll.py:244](api/routers/payroll.py:244) — jarima qoidasi
- [api/routers/payroll.py:380](api/routers/payroll.py:380) — qo'shimcha ish profili

```python
before = {c.name: getattr(existing, c.name) for c in FinePolicy.__table__.columns if c.name != "id"}
```

### Yechim allaqachon loyihada bor

`admin_override.py` da AYNAN shu muammo hal qilingan va izohda
ogohlantirish ham yozilgan:

```python
# ... `date`/`Decimal`ni tushunmay 500 beradi. Shu sabab bu yerda
# oldindan xavfsiz turga o'giriladi.
def _json_safe(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, Decimal): return float(value)
    return value
```

`payroll.py` shu yordamchini ishlatmaydi. **Tuzatish — ikki qatorlik:**
`_json_safe` ni umumiy joyga chiqarib, ikkala snapshot'da qo'llash.

### Nega hozirgacha sezilmagan

Audit yozuvi `db.commit()` paytida yiqiladi, ya'ni **asosiy o'zgarish ham
qaytariladi**. Foydalanuvchi «saqlandi» demaydigan, sababini aytmaydigan
500 ko'radi. Testlarda esa bu yo'l qamrab olinmagan — mavjud testlar
qoidani faqat **yaratadi**, tahrirlamaydi.

### Tekshiruv rejasi (tuzatilgandan keyin)

Har bir upsert endpointi uchun test: **ikki marta ketma-ket chaqirish** va
ikkinchisi ham 200 qaytarishini talab qilish. Bu naqsh butun loyihada
qidirilishi kerak — `__table__.columns` bo'yicha snapshot oladigan har bir
joy shubhali.

---

## 3. 🔴 BUG-2 — KPI stavkalari kodda qattiq yozilgan

Egasining talabi: «oylik stavkaga KPI stavka qilish».

Hozir KPI bonusi [api/services/bonus.py](api/services/bonus.py) da
**PLACEHOLDER konstantalar** bilan hisoblanadi:

```python
PLACEHOLDER_RATE_PER_CONVERSATION = 2000
PLACEHOLDER_RATE_PER_VISIT = 5000
PLACEHOLDER_RATE_PER_VIDEO = 0     # umuman hisoblanmaydi
```

Faylning o'z izohida: *«Bonus formulasi hali kompaniya tomonidan
aniqlanmagan… stavkalar shunchaki PLACEHOLDER»*.

### Oqibati

- HR KPI stavkasini **saytdan o'zgartira olmaydi** — har o'zgarish uchun
  dasturchi kerak va deploy kerak.
- Mobilograf videosi stavkasi **0** — ya'ni uning KPI'si doim nol.
- Stavka **tarixiy emas**: o'zgartirilsa o'tgan oylar bonusi ham qayta
  hisoblanganda o'zgarib ketadi (oylik stavkada bu to'g'ri hal qilingan —
  `SalaryRate.effective_from`, lekin KPI'da yo'q).
- Lavozimga qarab farqlanmaydi (sotuvchi va mobilograf uchun bir xil mantiq).

### Taklif

`SalaryRate` bilan **bir xil naqsh**: yangi `KpiRate` jadvali —
`scope` (global / lavozim / xodim) + `metric` (suhbat / tashrif / video) +
`amount` + `effective_from`. Shunda:

- HR saytdan kiritadi, dasturchi kerak emas;
- o'tgan oylar buzilmaydi (tarixiy);
- lavozimga moslashadi;
- `calculate_bonus` faqat stavkani jadvaldan o'qiydigan qilib o'zgaradi.

---

## 4. 🟠 BUG-3 — «HR belgilaydi, Boshliq tasdiqlaydi» yo'q

Egasining talabi shundoq yozilgan edi. Hozir esa:

```python
PAYROLL_MANAGE_ROLES = (hr, boss, dasturchi)   # payroll.py:84
```

va **tasdiqlash ham shu darvoza ostida**:

```python
@router.post("/{period}/approve")
async def approve_period(..., actor = Depends(_require_manage))
```

Sinovda tasdiqlandi: **HR o'zi hisobladi va o'zi tasdiqladi** — `200
{"period":"2026-07","approved":1}`. Hech kim aralashmadi.

### Nega bu muhim

Tasdiqlash — davrni **qulflaydi** (`locked=True`). Qulfni faqat Dasturchi
ocha oladi. Ya'ni HR bexosdan tasdiqlab qo'ysa, tuzatish uchun dasturchi
kerak bo'ladi. Bu ham xavfsizlik (vazifalar ajratilmagan), ham amaliy
muammo.

### Taklif

Uch bosqichli holat: `draft` → `hisoblandi` → `HR tasdiqi` → `Boshliq
tasdiqi (qulf)`.

- `calculate` va `HR tasdiqi` — HR;
- **yakuniy tasdiq/qulf — faqat `boss` va `dasturchi`**;
- Boshliqqa «tasdiqlashingiz kutilmoqda» bildirishnomasi (mexanizm bor —
  `notify_user` allaqachon hisoblashdan keyin xabar yuboryapti).

---

## 5. 🟡 Joylashuv muammolari (egasi aytgan)

### 5.1 Ish haqini belgilash «Sozlamalar» ichida qolib ketgan

Menyu:

```
Ish haqi          /payroll
Qo'shimcha ish    /overtime
Sozlamalar        /payroll/settings   ← stavkalar SHU YERDA
```

`/payroll/settings` uchta tabdan iborat: **Jarima qoidasi · Oylik
stavkalar · Qo'shimcha ish**. Ya'ni «xodimga oylik belgilash» — kundalik
HR ishi — «Sozlamalar» ichiga ko'milgan, holbuki «Sozlamalar» odatda kamdan
kam tegiladigan joy.

**Taklif:** stavka belgilash xodim kontekstida bo'lsin — Foydalanuvchilar
sahifasidagi xodim kartochkasida yoki `/payroll` ichida «Stavkalar» tabi.
«Sozlamalar» da faqat qoidalar (jarima, qo'shimcha ish profillari) qolsin.

### 5.2 Stavkani tahrirlash yo'li yo'q

`SalaryRate` ataylab **o'zgarmas** (tarixiy) — bu to'g'ri qaror. Lekin
xato kiritilgan stavkani tuzatishning yagona yo'li — Dasturchi rejimi
(`/admin/records/salary_rate/{id}`). HR xato yozsa, dasturchi kerak.

**Taklif:** HR uchun «tuzatish» tugmasi — u yangi qator yaratmaydi, balki
**oxirgi, hali hech qanday tasdiqlangan payslip'ga kirmagan** stavkani
tahrirlaydi. Tasdiqlangan davrga tushgan stavka qulflanadi.

---

## 6. 🟢 Nima yaxshi ishlayapti (buzmaslik kerak)

Sinovda tasdiqlangan:

| Narsa | Holat |
|---|---|
| Stavka yaratish va tarix | ✅ ishlaydi |
| Oylikni hisoblash | ✅ `{"calculated": 1}` |
| Kechikish jarimasi | ✅ `late_days=3, late_minutes=125, fined_late_days=1` |
| Kelmagan kun jarimasi | ✅ `absent_days=16, absent_deduction=984 615` |
| Oylik shift (cap) | ✅ 20% cheklov aniq ishladi, proporsional taqsimlandi |
| Payslip snapshot | ✅ qoidalar `breakdown`da saqlanadi |
| Davr qulfi | ✅ qulflangan davr qayta hisoblanmaydi (409) |
| Preflight | ✅ jadvalsiz xodimlarni topib beradi |

### Diqqat: kechikish limiti mantig'i

Sinov: limit 60 daq, kechikishlar 20 / 45 / 60 daq. Natija — **faqat 1 kun**
jarimalandi.

Sabab kodda ataylab yozilgan: *«chegaradan o'tkazgan kunning o'zi hali
bepul, undan keyingi kun(lar) jarimali»* — `fined = cumulative_before >=
free_limit`.

- 1-kun: oldin 0 → bepul
- 2-kun: oldin 20 → bepul (garchi 65 ga chiqib limitni buzsa ham)
- 3-kun: oldin 65 → **jarimali**

Bu **bug emas, qaror**. Lekin egasi «limitdan o'tsa jarima» deganda
ehtimol 2-kunni ham jarimali deb tushungan. **Tasdiqlash kerak:** limitni
buzgan kunning o'zi jarimalanadimi yoki yo'qmi?

### Diqqat: kelmagan kun asosiy oylikni kamaytirmaydi

Sinovda 16 kun kelmagan xodimning `gross` i hamon to'liq 5 000 000 bo'ldi —
faqat jarima (cap bilan 1 000 000) ayirildi. Ya'ni **oyning yarmida
kelmagan odam oylikning 80% ini oladi**. Bu ham qaror bo'lishi mumkin,
lekin tasdiqlash kerak.

---

## 7. Yetishmayotgan narsalar (qo'shilmagan)

### 7.1 Interaktiv kalendar — QISMAN BOR

Egasi so'ragan «ranglar bilan kechikkan/kelgan/kelmagan kalendar»
**allaqachon mavjud**: [MonthCalendar.tsx](web/src/components/attendance/MonthCalendar.tsx)
— ranglar, kechikish daqiqasi, katak tafsiloti bilan. U xodim kartochkasida,
drawer'da va xodimning o'z tarixida ishlatiladi.

**Yetishmayotgani — pul bilan bog'lanish:**
- qaysi kun **qancha turgani** (jarima summasi) ko'rinmaydi;
- oylik sahifasidan bu kalendarga o'tish yo'li yo'q;
- oylik jamg'armasi («shu oy jami jarima X so'm») yo'q.

**Taklif:** yangi kalendar qurmaslik. Mavjudiga ikki narsa qo'shish:
(1) katakda jarima summasi, (2) payslip tafsilotidan «kalendarda ko'rish»
havolasi. Shunda «nega bu summa» degan savol bir bosishda yopiladi.

### 7.2 Yo'q narsalar ro'yxati

| Narsa | Holat |
|---|---|
| Avans (oy o'rtasida to'lov) | Model bor (`PayrollAdjustment kind='minus'`), UI yo'q |
| Xodimga payslip bildirishnomasi | Bot endpointi bor, avtomatik yuborish yo'q |
| Jarima uchun e'tiroz (apeliatsiya) | Umuman yo'q |
| KPI maqsad vs haqiqat ko'rinishi | Yo'q |
| Oylik tarixi grafigi (xodim uchun) | Yo'q |
| Global jarima qoidasi (default) | **Yo'q** — bazada 0 ta qoida. Qoida yaratilmasa hech kim jarimalanmaydi, lekin bu hech qayerda ogohlantirilmaydi |

### 7.3 Lavozim bo'yicha moslashtirilmagan

Egasi «mansab bo'yicha moslashtirib chiqilmagan» dedi — to'g'ri:

- **Jarima qoidasi** 3 darajali (global → lavozim → xodim) — ✅ moslashadi;
- **KPI** — ❌ faqat metrika ro'yxati lavozimga qarab, stavka bir xil;
- **Qo'shimcha ish** — ❌ faqat xodim darajasida, lavozim darajasi yo'q;
- **Stavka** — ❌ faqat xodim darajasida (bu to'g'ri bo'lishi mumkin).

---

## 8. Tavsiya etilgan tartib

Har bandda «nega shu tartibda» izohi bor — tartib ahamiyatli.

### 1-bosqich — qon ketishni to'xtatish (1 kun)

1. **BUG-1 tuzatish** — `_json_safe` ni umumiy joyga chiqarib, `payroll.py`
   dagi ikkala snapshot'da qo'llash.
   *Nega birinchi:* busiz HR hech qanday sozlamani o'zgartira olmaydi, ya'ni
   qolgan hamma ish sinab ko'rilmaydi.
2. **Regressiya testi** — har bir upsert endpointini **ikki marta** chaqirib
   sinaydigan test. Busiz bu bug yana qaytadi.
3. Butun kodda `__table__.columns` snapshot naqshini qidirib chiqish.

### 2-bosqich — vazifalarni ajratish (1 kun)

4. `approve_period` ni `boss`/`dasturchi` ga cheklash, HR uchun oraliq
   «HR tasdiqladi» holati.
5. Boshliqqa «tasdiqingiz kutilmoqda» bildirishnomasi.
   *Nega ikkinchi:* pul qulflanadigan amal, xato qimmatga tushadi.

### 3-bosqich — KPI stavkalari (2-3 kun)

6. `KpiRate` jadvali + migratsiya (scope / metric / amount / effective_from).
7. `calculate_bonus` ni jadvaldan o'qiydigan qilish, PLACEHOLDER'larni olib
   tashlash.
8. Sozlamalarda «KPI stavkalari» tabi.
   *Nega uchinchi:* bu yangi funksiya, avvalgi ikkitasi — buzilganni tuzatish.

### 4-bosqich — joylashuv va qulaylik (2 kun)

9. Stavka belgilashni xodim kontekstiga ko'chirish.
10. Stavkani tuzatish (tasdiqlanmagan davrlar uchun).
11. Kalendarga jarima summasini qo'shish + payslip'dan havola.

### 5-bosqich — egasining qarorlari (2026-08-08 da olindi)

| Savol | Javob | Nima qilinadi |
|---|---|---|
| Limitni buzgan kunning o'zi jarimalanadimi? | **Yo'q — faqat keyingilari** | ✅ Hozirgi xulq TO'G'RI, kod o'zgarmaydi |
| Kelmagan kun asosiy oylikni kamaytiradimi? | **Ha, kamaytiriladi** | 🔧 Hisoblash o'zgaradi (quyida) |
| Video KPI stavkasi qancha? | KPI bo'limi ochilsin, **keyin belgilanadi** (mobilografga) | 🔧 Faqat mexanizm quriladi, qiymat bo'sh |
| Global (default) jarima qoidasi kerakmi? | **Ha** — hozirgilari «faqat nomiga, ChatGPT'dan olingan umumiy xulosalar, haqiqiy qoida emas» | 🔧 Global qoida + HR uni to'ldiradi |

#### Kelmagan kun — aniqlashtirish kerak bo'lgan nuqta

«Ha, kamaytiriladi» degani hozirgi `absent_fine` (qat'iy summa) **ustiga**
qo'shiladimi yoki **o'rniga** keladimi — bu ikki xil natija beradi:

- **Ustiga:** kelmagan kun uchun ham kunlik ulush ayiriladi, ham jarima →
  ikki marta jazolanadi;
- **O'rniga:** kunlik ulush ayiriladi, alohida jarima yo'q.

Sinovda 16 kun kelmagan xodim hozir oylikning 80% ini oladi. «O'rniga»
variantida u ~30% oladi (ishlagan kunlari uchun), «ustiga» variantida
undan ham kam.

**Amalga oshirishdan oldin shu bitta narsa tasdiqlanishi kerak.**

---

## 9. Ilova — sinov natijalari (xom)

```
1. STAVKA BELGILASH        OK  200
   stavka ro'yxati         OK  200, 1 ta
2. JARIMA QOIDASI          OK  200, 0 ta qoida
   global qoida bormi      XATO YOQ
   xodimga qoida qo'yish   OK  200   (1-marta)
   xodimga qoida qo'yish   XATO 500  (2-marta — BUG-1)
3. PREFLIGHT               OK  200
4. HISOBLASH               OK  200 {"calculated":1}
5. PAYSLIP                 OK  200
     base_amount          5000000.0
     late_days            3
     late_minutes         125
     fined_late_days      1
     fine_amount          15384.62      (cap bilan proporsional)
     absent_days          16
     absent_deduction     984615.38
     gross                5000000.0
     net                  4000000.0     (cap: 20% = 1 000 000 ayirildi)
6. HR O'ZI TASDIQLADI      HA (ajratish yo'q) 200
7. OVERTIME profil yoqish  OK  200      (1-marta)
   OVERTIME profil tahrir  XATO 500     (2-marta — BUG-1)
```
