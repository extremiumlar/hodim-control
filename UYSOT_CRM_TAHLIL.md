# UYSOT CRM — TO'LIQ ARXITEKTURA TAHLILI (o'z CRM qurishdan oldingi o'rganish)

> Maqsad: Uysot'ni har bo'lim bo'yicha (frontend UI + backend API) o'rganib,
> o'zimizning kompaniyaga moslangan CRM uchun asos xarita tuzish.
> Usul: jonli kabinetda (app.uysot.uz, kuzatuvchi akkaunt) har sahifani ochib,
> SPA'ning backend'ga yuborgan REAL so'rovlarini (fetch/XHR hook) yozib olish.
> Sana: 2026-08-01. Tahlil davomida to'ldirib boriladi.

---

## 0. Umumiy manzara — uchta alohida API

Uysot'ning fronti (React SPA) **hech qachon** biz ilgari integratsiya qilgan
"Open API" bilan gaplashmaydi. U butunlay boshqa, ancha boy **ichki API**'ga
murojaat qiladi. Bu tahlilning eng muhim topilmasi.

| API oilasi | Bazaviy manzil | Autentifikatsiya | Kim ishlatadi |
|---|---|---|---|
| **Ichki (internal)** | `service.app.uysot.uz/v1` | brauzer **cookie-sessiya** | Uysot'ning o'z fronti. To'liq imkoniyat. |
| **Ochiq (Open API)** | `api.service.app.uysot.uz/v1/open-api` | `X-Open-Api-Token` | Tashqi integratsiya (bizning eski polling). Cheklangan qism. |
| **Showroom** | `srv.showroom.app.uysot.uz` | `X-Auth` (JWT) | Inventar: xonadonlar, shaxmatka, planirovka PDF. |

### Yagona javob konverti

Ichki API'ning **barcha** javoblari bir xil shaklda:

```json
{
  "data": ...,
  "message": {"uz": "Muvaffaqqiyatli!", "ru": "...", "en": "...", "kr": "...", "tr": "...", "tj": "...", "ky": "..."},
  "errorMessage": null,
  "accept": true,
  "errors": []
}
```

Sahifalangan ro'yxatlar esa `data` ichida:

```json
{"totalPages": 2, "currentPage": 1, "totalElements": 34, "data": [ ... ]}
```

> **Xulosa:** o'z tizimimizda ham yagona javob konverti (envelope) va yagona
> sahifalash shakli bo'lishi kerak — front kod bir marta yoziladi, hamma
> modulga yetadi.

---

## 1. Takrorlanuvchi naqsh — butun tizim bitta shablonda

Eng qimmatli tushuncha: **har bir ro'yxat-sahifasi bir xil to'rt qismli naqsh**
bilan ishlaydi. Buni bir marta qursak — CRM, shartnoma, to'lov, mijozlar,
qarzdorlik modullari bir xil poydevordan quriladi.

| # | Chaqiruv | Vazifasi |
|---|---|---|
| 1 | `GET /table/{entity}` | Jadval qaysi ustunlarni ko'rsatishi (foydalanuvchi sozlagan) |
| 2 | `POST /{entity}/filter` | Sahifalangan ro'yxat — filtr tanasi bilan |
| 3 | `POST /{entity}/filter/sum` | Ro'yxat tepasidagi yig'ma raqamlar (alohida so'rov!) |
| 4 | `GET /{entity}/employee`, `GET /{entity}/field` | Filtr uchun xodim / maxsus maydon ro'yxati |

**Bizga nima beradi:** frontendda bitta umumiy «ro'yxat + filtr + jami»
komponenti, backendda bitta generik `filter` naqshi. Har modulga noldan
yozish shart emas.

---

## 2. Modul → endpoint xaritasi

Barcha yo'llar `/v1` prefiksi bilan (`service.app.uysot.uz/v1/...`).

### 2.1. CRM tizimi — lidlar doskasi (kanban)

Eng ko'p ishlatiladigan va eng sekin qism. `pipeId=1010`.

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/lead/filter/v2` | Bosqich bo'yicha lidlar. Tanasi: `{page, size, pipeStatusIds[], pipeId}`. **Har kanban ustuni — ALOHIDA so'rov** |
| GET | `/lead/{id}` | Bitta lidning to'liq kartasi (balans, kontakt, valyuta, maydonlar) |
| POST | `/lead/data` | Lid **timeline**'i: voqealar + chat + vazifalar. Tanasi: `{leadId, isPrevious}` |
| GET | `/pipe/all-check` | Barcha voronkalar va bosqichlar (id → nom, rang, tur) |
| GET | `/lead/crm-employee?pipeStatusIds=` | Bosqichga biriktirilishi mumkin xodimlar |
| GET | `/lead-task/not-closed?leadId=` | Lidning yopilmagan vazifalari |
| GET | `/lead-task/count` | Vazifalar soni (badge uchun) |
| GET | `/lead-task-type/all` | Vazifa turlari: Uchrashuv (889), Qayta aloqa (890), To'lov (891) |
| GET | `/booking-lead-flat/{leadId}` | Lidga bog'langan bron xonadonlar |
| GET | `/lead/inviting-client/{leadId}` | Taklif qilingan mijoz ma'lumoti |
| GET | `/chat-message/available-accounts/{leadId}` | Chat kanallari (Telegram/IG) |
| GET | `/embed-widget/resolve?leadId=` | Kartadagi qo'shimcha vidjetlar |
| GET | `/company/integration/SMART_BUTTON` | «Aqlli tugma» integratsiyasi |

**Jonli bosqichlar (pipeId 1010):**

| ID | Nom |
|---|---|
| 8779 | Yangi lid |
| 8780 | Ishga olindi |
| 8781 | Bog'lanib bo'lmadi 1 |
| 8782 | Bog'lanib bo'lmadi 2 |
| 8785 | Malumot berildi, oylab ko'radi |
| 8786 | Officega taklif qilindi |
| 8787 | **Tashrif** |
| 8788 | Shartnoma qilindi |
| 8789 | Sifatsiz lead |

### 2.2. Buyurtma (bron)

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/booking/filter` | Bronlar ro'yxati — `{page, size}` |
| GET | `/booking/employee` | Filtr uchun mas'ul xodimlar |
| GET | `/table/order` | Jadval ustunlari sozlamasi |

### 2.3. Shartnoma

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/contract/filter` | Shartnomalar ro'yxati |
| POST | `/contract/filter/sum` | Jami summa (alohida so'rov) |
| GET | `/contract/field` | Shartnoma maxsus maydonlari |
| GET | `/contract/employee` | Mas'ul xodimlar |
| GET | `/table/contract` | Ustunlar sozlamasi |

### 2.4. To'lov

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/contract/payment/filter` | To'lovlar ro'yxati |
| POST | `/contract/payment/filter/sum` | Sana oralig'i bo'yicha jami — `{startDate, finishDate}` (format: `01.08.2026`) |
| GET | `/payment/field` | To'lov maydonlari |
| GET | `/payment-custom-type` | Kompaniya sozlagan to'lov turlari |
| GET | `/currency/basic` | Asosiy valyuta (UZS) |
| GET | `/company-config/document-template/compact/CLIENT_PAYMENT` | Chek shabloni |
| GET | `/company-config/document-template/compact/PAYMENT` | To'lov hujjati shabloni |
| GET | `/company-config/document-template/compact/BOOKING_PAYMENT` | Bron to'lovi shabloni |

To'lov kanallari (bosh sahifadagi diagrammadan): Naqd, Terminal, Bank, P2P,
Balansdan, My Uzcard, Uzum, Click.

### 2.5. Mijozlar

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/client/filter` | Mijozlar ro'yxati — `{page, size, expired}` |
| GET | `/client/filter/params` | Filtr parametrlari |
| GET | `/cashback/active` | Faol keshbek dasturi |
| GET | `/table/client` | Ustunlar sozlamasi |

### 2.6. Qarzdorlik

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/debt` | Qarzdorlar ro'yxati — `{page, size}` |
| GET | `/contract/field` | Shartnoma maydonlari (qayta ishlatiladi) |
| GET | `/table/arrearage` | Ustunlar sozlamasi |

### 2.7. SMS

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/client/send-message/filter` | Yuborilgan xabarlar ro'yxati |
| GET | `/table/message` | Ustunlar sozlamasi |

### 2.8. Topshiriqlar

Uch ko'rinish: Board (kanban) / Jadval / Kalendar.

| Metod | Endpoint | Vazifasi |
|---|---|---|
| POST | `/lead-task/filter` | Vazifalar — `{view: "kanban", employeeList[], page, size, startTimestamp, finishTimestamp}` |
| GET | `/task/employee` | Mas'ul xodimlar |
| GET | `/table/task-view` | Ustunlar sozlamasi |

**Diqqat:** kanban ustunlari (O'tib ketgan / Bugungi / Ertangi / Keyingi) —
har biri **alohida so'rov**, faqat timestamp oralig'i bilan farqlanadi.

### 2.9. Statistika (Boshliq paneli)

Bu bo'lim butunlay **boshqa API oilasini** (`/mobile/*`) ishlatadi — ehtimol
mobil ilova bilan umumiy.

| Metod | Endpoint | Vazifasi |
|---|---|---|
| GET | `/mobile/payment` | To'lovlar bo'yicha yig'ma |
| GET | `/mobile/indebtedness/all` | Umumiy qarzdorlik |
| GET | `/mobile/indebtedness/month` | Oylik qarzdorlik |
| POST | `/mobile/debt/month` | Oylik qarz — `{page, size, houseIdList[], buildingIdList[], text}` |
| GET | `/mobile/client/balance` | Mijozlar balansi |
| GET | `/mobile/flat-area` | Xonadon maydonlari |
| GET | `/open-api/embedded/resolve?page=STATS` | Sahifaga o'rnatilgan vidjetlar |

---

## 3. Ma'lumot oqimi — sekinlikning ildizi

Operator bitta lid kartasini bosganda front **20+ ketma-ket so'rov** yuboradi:

```
Lid kartasi bosildi
├── GET  /lead/{id}                        ← asosiy karta
├── POST /lead/data                        ← timeline (voqea + chat + vazifa)
├── GET  /lead-task/not-closed?leadId=     ← ochiq vazifalar
├── GET  /lead-task/count                  ← badge
├── GET  /booking-lead-flat/{id}           ← bron xonadonlar
├── GET  /pipe/all-check                   ← bosqichlar ro'yxati
├── GET  /lead/crm-employee                ← biriktirish uchun xodimlar
├── GET  /lead-task-type/all               ← vazifa turlari
├── GET  /lead/inviting-client/{id}        ← taklif qilingan mijoz
├── GET  /chat-message/available-accounts  ← chat kanallari
├── GET  /embed-widget/resolve             ← vidjetlar
├── GET  /company/integration/SMART_BUTTON ← integratsiya
└── ... (yana ~8 ta)
```

**Muammo:** 2931 lid bor, har karta ochilishi o'nlab chaqiruvni qo'zg'aydi,
server esa sekin javob beradi.

**Bizning yechim:** lid ochilganda **bitta** `GET /lead/{id}/full` — timeline,
vazifalar, bronlar, bosqichlar, xodimlar hammasi bitta javobda. Sahifa bir
zumda ochiladi. Statik ma'lumotlar (bosqichlar, vazifa turlari, xodimlar)
esa umuman qayta so'ralmaydi — front ularni bir marta yuklab keshlaydi.

---

## 4. Ko'chirish holati — bizda nima bor, nima yo'q

Asos: `D:\Project\hodimlar_tizimi` (FastAPI + React + PostgreSQL).

| Modul | Holat | Bizdagi asos |
|---|---|---|
| Lid-voqealari (bosqich/mas'ul o'zgarishi) | ✅ BOR | `CrmLeadState` + `LeadEvent` + webhook qabul qiluvchi |
| Xodimlar, rollar, huquqlar | ✅ BOR | `User` + `Role` + JWT + Telegram login |
| Statistika (operator × bosqich) | ✅ BOR | `LeadStageDaily` + digest + lokal hisob |
| Qo'ng'iroqlar tarixi, speed-to-lead | 🟡 QISMAN | Issiq-lid + call-history bor, lekin **token o'lik** |
| Mijozlar bazasi (kontakt/telefon) | 🟡 QISMAN | Lidda bor, alohida mijoz moduli yo'q |
| Shaxmatka / inventar | 🟡 QISMAN | Showroom API'dan o'qiladi (chatbot loyihasida), o'z bazaga ko'chirilmagan |
| **Lidlar kanban doskasi (UI)** | ❌ YO'Q | **1-bosqich nishoni** |
| Shartnoma / to'lov / qarzdorlik | ❌ YO'Q | 3-bosqich — pul hisobi, ehtiyotkorlik bilan |

---

## 5. Shoshilinch ogohlantirishlar

1. **Litsenziya tugayapti.** Kabinetda qizil banner: «Dastur litsenziyasi
   tugashiga 2 kun qoldi! Yangi litsenziya sotib olmasangiz tizim avtomatik
   o'chib qoladi». Ya'ni ~2026-08-03.

2. **Open API tokeni o'lik.** 2026-07-31 12:36 dan beri barcha so'rovlar
   `{"message": "Invalid or expired Open API token", "accept": false}`
   qaytaradi. Oqibati: qo'ng'iroq statistikasi, operator nazorati va lid
   tafsilotlari yangilanmayapti. Ehtimol litsenziya holati bilan bog'liq.

3. **Kirish huquqi cheklangan.** Joriy akkaunt (`Obloqulov Nurullojon`,
   rol: `kuzatuvchi`) da Open API token yoki webhook sozlamalari bo'limi
   **umuman ko'rinmaydi** — ular egasi/admin akkauntida bo'ladi.

---

## 6. Keyingi qadamlar

1. **Ma'lumotni qutqarish (shoshilinch).** Litsenziya o'chishidan oldin
   barcha lid (kontakt/telefon bilan), shartnoma, to'lovni eksport qilish.
   Ham sug'urta, ham migratsiya asosi. Token tiklanishi bilan birinchi ish.

2. **Lidning to'liq maydon strukturasini yozib olish.** Bitta lidning barcha
   maxsus maydonlari (Kasbi/ish joyi, Bu uy kim uchun, Qaysi qavat, Nechi
   xonali, Boshlang'ich to'lov, Oyiga maksimum, Shartnomani qachon...) va
   timeline formatini aniqlash — jadval sxemamiz shunga qurilishi kerak.

3. **1-bosqich: CRM lidlar doskasini qurish.** Generik «ro'yxat + filtr +
   jami» naqshini bir marta yozib, kanban doska + lid kartasi + filtrni
   `hodimlar_tizimi` ustiga qo'yish.

4. **Yozish (write) oqimlarini o'rganish.** Lid yaratish, bosqichga surish
   (drag-drop), mas'ul biriktirish qaysi endpointga borishini **test lidda**
   kuzatib aniqlash (real ma'lumotga tegmasdan).

---

## Ilova: tahlil qanday olingan

Jonli kabinetda (Chrome, foydalanuvchi seansi) sahifa kontekstiga `fetch` va
`XMLHttpRequest` ustiga kuzatuvchi (hook) qo'yilib, har bo'lim ochilganda
ketgan real so'rovlar (yo'l, metod, so'rov tanasi, javob) yozib olindi.
Hech qanday ma'lumot o'zgartirilmadi — faqat o'qish.

Vizual (HTML) variant ham bor — artifact sifatida nashr qilingan:
`https://claude.ai/code/artifact/74614b27-dbbd-4a58-8891-46267fee13d6`
