# Hodim CRM

Hodimlar boshqaruvi tizimi — **Django REST** + **Next.js** + **Tailwind** asosida qurilgan ofis CRM.

![tech](https://img.shields.io/badge/backend-Django%205-green) ![tech](https://img.shields.io/badge/frontend-Next.js%2014-black) ![tech](https://img.shields.io/badge/ui-Tailwind%203-blue)

---

## Imkoniyatlar

✅ **GPS tekshiruvi** bilan check-in / check-out
   – tashqarida bo'lsa "Avval ofisga keling" xabari
   – ofis radiusi ichida bo'lsa qabul qilinadi

✅ **Smenalar** (ish kunlari + grace daqiqalar) — har bir hodim uchun alohida

✅ **Avtomatik kechikish hisoblash** (Telegram guruhga xabar yuboradi)

✅ **Erta ketish** — kuzatuv va xabar

✅ **Vazifalar (Task Management)** — hodimga vazifa beriladi → bajardim → isbot foto/fayl → tasdiqlash (KPI ball)

✅ **Avtomatik oylik hisoblash** — bir tugmada:
   - Asosiy oylik (proporsional)
   - Dam olish kuni qo'shimchasi (stavka %)
   - Bonuslar (+)
   - Jarimalar (-)
   - Kechikish jarimasi (-)
   - **PDF payslip** hodimga

✅ **Ta'til / kasallik** — hodim so'rov yuboradi, HR tasdiqlaydi → avtomatik `is_on_leave` ga o'zgaradi

✅ **Bildirishnomalar (Telegram)** — kechikish, erta ketish, kelmaganlik (cron orqali)

✅ **Admin Dashboard** — real vaqtda kim ofisda, kechikadiganlar TOP, ishlaganlar TOP, 30 kunlik chiziqli grafik (Chart.js)

✅ **Hodim rollar**: Admin / HR (Manager) / Hodim

✅ **Eksport**: Excel (davomat, oylik) va PDF (payslip)

✅ **Audit log**: barcha POST/PUT/PATCH/DELETE so'rovlar saqlanadi

---

## Tuzilma

```
hodim_crm/
├── backend/                       # Django REST API
│   ├── config/                    # Django settings, urls
│   ├── accounts/                  # User, Department, Shift, OfficeLocation
│   ├── attendance/                # Keldim/Ketdim, GPS, kechikish
│   │   ├── services.py            # check-in logikasi
│   │   └── utils.py               # haversine, vaqt hisoblash
│   ├── tasks/                     # Vazifa + isbot fayl
│   ├── payroll/                   # Bonus, Penalty, MonthlyPayroll
│   │   └── services.py            # avtomatik hisoblash
│   ├── leave/                     # Ta'til so'rovlari
│   ├── audit/                     # AuditLog + middleware
│   ├── notifications/             # Telegram bot
│   │   └── management/commands/
│   │       └── check_absent.py    # cron uchun
│   ├── reports/                   # Excel/PDF eksport
│   ├── manage.py
│   ├── seed.py                    # boshlang'ich ma'lumot
│   └── requirements.txt
└── frontend/                      # Next.js + Tailwind
    └── src/
        ├── app/
        │   ├── login/
        │   └── (dashboard)/       # himoyalangan zona
        │       ├── dashboard/     # hodim asosiy sahifa + GPS check-in
        │       ├── admin/         # admin grafiklar
        │       ├── tasks/
        │       ├── attendance/
        │       ├── leaves/
        │       ├── payroll/
        │       └── employees/
        ├── components/
        │   ├── Sidebar.tsx
        │   └── CheckInCard.tsx   # GPS olib serverga yuboradi
        └── lib/
            ├── api.ts             # axios + JWT
            └── useMe.ts
```

---

## Ishga tushirish

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate                  # Windows
# yoki: source venv/bin/activate       # Linux/Mac

pip install -r requirements.txt
copy .env.example .env                 # va o'zgartiring
python manage.py migrate
python manage.py shell < seed.py       # admin/hodim yaratadi
python manage.py runserver
```

| URL | Maqsad |
|---|---|
| http://localhost:8000/admin/ | Django admin (`admin` / `admin123`) |
| http://localhost:8000/api/ | REST API |

**Seed orqali yaratiladi:**
- `admin` / `admin123` — superuser/admin
- `hodim` / `hodim123` — test hodim
- Ofis: Toshkent (41.311, 69.240, radius 200m)
- Smena: 09:00–18:00, Du–Ju

### 2. Frontend

```bash
cd frontend
npm install
copy .env.local.example .env.local
npm run dev
```

Sayt: http://localhost:3000

---

## Telegram bot sozlash

1. [@BotFather](https://t.me/BotFather) dan bot yaratib token oling.
2. Botni ofis guruhiga qo'shing, admin qiling.
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` orqali `chat_id` ni oling.
4. `.env` ga yozing:
   ```
   TELEGRAM_BOT_TOKEN=12345:AAA...
   TELEGRAM_GROUP_CHAT_ID=-1001234567890
   ```

### Kelmaganlik ogohlantirishi (cron)

Windows Task Scheduler / Linux cron orqali har kuni 09:35 da:
```bash
python manage.py check_absent --threshold 09:30
```

---

## Texnik stek

| Qatlam | Texnologiya |
|---|---|
| Backend | Django 5 + DRF + SimpleJWT |
| DB | SQLite (default) / PostgreSQL |
| Frontend | Next.js 14 (App Router, TypeScript) |
| UI | TailwindCSS 3 |
| Grafiklar | Chart.js + react-chartjs-2 |
| Auth | JWT (access + refresh, avto-refresh) |
| Eksport | openpyxl (Excel), reportlab (PDF) |
| Bildirishnoma | Telegram Bot API |

---

## API qisqacha

| Endpoint | Method | Tavsif |
|---|---|---|
| `/api/auth/token/` | POST | login (JWT) |
| `/api/accounts/users/me/` | GET | joriy foydalanuvchi |
| `/api/accounts/users/` | GET/POST | hodimlar (HR) |
| `/api/attendance/check-in/` | POST | `{latitude, longitude}` |
| `/api/attendance/check-out/` | POST | `{latitude, longitude}` |
| `/api/attendance/today/` | GET | bugungi davomat |
| `/api/attendance/live/` | GET | hozir kim ofisda (HR) |
| `/api/attendance/stats/?days=30` | GET | statistika (HR) |
| `/api/tasks/` | GET/POST | vazifalar |
| `/api/tasks/{id}/complete/` | POST | bajarildi |
| `/api/tasks/{id}/approve/` | POST | tasdiqlash (HR) |
| `/api/tasks/proofs/` | POST (multipart) | isbot fayl |
| `/api/payroll/payrolls/compute/` | POST | `{period: "2026-05"}` — avtomatik hisoblash |
| `/api/leave/` | GET/POST | ta'til so'rovlari |
| `/api/leave/{id}/approve/` | POST | tasdiqlash |
| `/api/reports/attendance.xlsx` | GET | Excel davomat |
| `/api/reports/payroll.xlsx?period=2026-05` | GET | Excel oylik |
| `/api/reports/payslip/{id}.pdf` | GET | PDF oylik varaqasi |

---

## Sinab ko'rish (qisqacha senariy)

1. Backend va frontend ishga tushiring.
2. http://localhost:3000 → `hodim` / `hodim123` bilan kiring.
3. **Dashboard** sahifasida "Keldim" tugmasini bosing — brauzer GPS so'raydi, ruxsat bering.
4. Agar ofis koordinatasidan uzoq bo'lsangiz — xato chiqadi (seed da Toshkent koordinatasi qo'yilgan, real test uchun `seed.py` da o'z koordinatangizni qo'ying).
5. **Admin** sifatida (`admin` / `admin123`) kirib — grafiklar, hodimlar, oylik hisoblashni ko'ring.

---

## Xavfsizlik eslatmasi

- Production'da `.env` ichidagi `DJANGO_SECRET_KEY` ni o'zgartiring.
- `DJANGO_DEBUG=False` qiling.
- HTTPS orqali ishga tushiring (geolokatsiya HTTPS talab qiladi production'da).
- `OfficeLocation` ning `latitude/longitude/radius` ni real ofisga moslang.
