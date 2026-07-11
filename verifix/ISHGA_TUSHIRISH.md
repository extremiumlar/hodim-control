# verifix (hodim_crm) — kelib-ketish davomati (Face ID)

Bu papka — `hodim_crm` loyihasining to'liq nusxasi (Django backend + Next.js frontend).
hodimlar_tizimi ostiga **`/verifix`** URL prefiksi bilan ulanadi:

```
http://<domen>/          -> hodimlar_tizimi (asosiy)
http://<domen>/verifix/  -> verifix (hodim_crm, Face ID davomat)
```

## Portlar

| Xizmat | Port | Izoh |
|--------|------|------|
| verifix frontend (Next.js) | **3000** | `basePath=/verifix` |
| verifix backend (Django) | **8002** | 8000 ni hodimlar_tizimi API egallagan |
| hodimlar_tizimi web (Vite) | 5173 | asosiy tizim |
| hodimlar_tizimi API (FastAPI) | 8000 | asosiy tizim |

verifix Django'ga to'g'ridan-to'g'ri emas, Next.js server-side proxy orqali boriladi
(`/verifix/django-api/...` → `http://localhost:8002/api/...`).

## Ishga tushirish (lokal dev)

**1-terminal — verifix Django (:8002):**
```powershell
cd D:\Project\hodimlar_tizimi\verifix\backend
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8002
```

**2-terminal — verifix Next.js (:3000):**
```powershell
cd D:\Project\hodimlar_tizimi\verifix\frontend
npm run dev
```

So'ng: **http://localhost:3000/verifix** (nginx'siz to'g'ridan-to'g'ri ham ishlaydi).

## Yagona domen (nginx gateway)

`deploy/nginx-gateway.conf` (hodimlar_tizimi ildizida) `/verifix` → :3000, `/` → :5173
ni bog'laydi. nginx bilan ishlatilganda `http://<domen>/verifix` ochiladi.
`server_name` ni haqiqiy domenga almashtiring.

## Toza (yangi) mashinaga o'rnatish

venv va node_modules git'da kuzatilmaydi. Yangi joyda tiklash:

```powershell
# Backend
cd verifix\backend
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe manage.py migrate

# Frontend
cd ..\frontend
npm install
```

`backend\.env` va `frontend\.env.local` fayllari (sozlamalar/portlar) shu papkada bor.

## Muhim eslatmalar

- verifix Django (8002) va hodimlar_tizimi API (8000) — **har xil portlar**, ikkalasi
  bir vaqtda ishlay oladi.
- basePath tufayli ilova faqat `/verifix` ostida ochiladi; `http://localhost:3000/`
  (prefiksisiz) 404 beradi — bu to'g'ri.
- verifix o'z bazasidan (`backend/db.sqlite3`) foydalanadi — hodimlar_tizimi bazasidan
  (`app.db`) mustaqil.
