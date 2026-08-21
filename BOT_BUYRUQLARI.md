# Telegram bot — buyruqlar va ruxsatlar

Botdagi barcha `/buyruq`lar, ularni kim ishlata olishi va qayerda (shaxsiy chat /
guruh) ishlashi. Ko'pchilik funksiya asosiy menyu tugmalari orqali ham bor
(masalan «📈 Statistikam») — bu yerda faqat **slash-buyruqlar**.

> **Yagona manba:** ro'yxat va ruxsat qoidalari `api/services/sections.py`
> (`ALL_COMMANDS`) da. Bu hujjat — o'sha reestrning o'qish uchun qulay
> ko'rinishi. Yangi buyruq qo'shilsa avval reestrga qo'shiladi, aks holda
> `test.py::test_bot_commands_by_role` testi yiqiladi.

---

## Qanday ishlaydi

**1. Har kim FAQAT o'ziga tegishli buyruqni ko'radi.** Telegram'ning «/»
menyusi lavozimga qarab to'ldiriladi:

| Qayerda | Qanday to'ldiriladi | Qachon |
|---|---|---|
| Shaxsiy chat | `BotCommandScopeChat` — xodimga xos ro'yxat | `/start` bosilganda |
| Guruh | `BotCommandScopeChatMember` — aynan shu guruh + shu xodim | `/start` da (biriktirilgan guruhlar uchun) va guruhda birinchi buyruqdan keyin |
| Umumiy (zaxira) | faqat `/start` | bot ishga tushganda |

Guruhda umumiy ro'yxat **ataylab bo'sh**: a'zolarning ko'pchiligi oddiy xodim,
ularda guruh buyrug'i yo'q. Rahbarlar o'z ro'yxatini a'zo-qamrovi orqali oladi.

**2. Ruxsati yo'q buyruq JIM QOLMAYDI.** `bot/middlewares.py: CommandGuard`
har slash-buyruqni handlerdan OLDIN tekshiradi va uch xil aniq javob beradi:

- **Lavozim yetmasa** — «sizda bu buyruqqa ruxsat yo'q, bu buyruq *{kim uchun}*,
  sizning lavozimingiz *{rol · lavozim}*» + `/buyruqlar` maslahati;
- **Noto'g'ri joyda** — «bu buyruq faqat guruh ichida / shaxsiy chatda ishlaydi»;
- **Noto'g'ri guruhda** (`/statistika`) — «bu guruh statistika uchun
  biriktirilmagan».

Ro'yxatdan o'tmagan odam shaxsiy chatda tushuntirish oladi; guruhda esa bot
**jim turadi** (begona odamning tasodifiy `/...` xabari guruhni ifloslantirmasin).

**3. `/buyruqlar`** — xodim istalgan vaqtda o'ziga ruxsat etilganlarni ko'radi
(shaxsiy chatda ham, guruhda ham) va shu bilan birga «/» menyusi yangilanadi.

---

## Kim nimani ko'radi (qisqacha)

| Rol | Shaxsiy chat | Guruh |
|---|---|---|
| **Xodim** | `/start` `/buyruqlar` `/sotuv_ai`¹ | `/buyruqlar` |
| **ROP / HR** | + `/oylik` `/davomat_vaqt` `/reja` `/norma_ozgartir` `/ai_sozlama` | + `/statistika` `/oylik` `/reja` |
| **Boshliq** | + `/statistika_vaqt` `/ai_markazi` `/bilim` `/playbook` | + `/statistika_vaqt` |
| **Dasturchi** | + `/anketa` `/guruhlar` `/norm_set` `/norm_del` `/att_fix` `/unlock` `/undo` | + `/guruh_biriktir` `/guruh_ochir` |

¹ `/sotuv_ai` — faqat sotuv ko'rsatkichi (suhbat/tashrif) bor lavozimda.
Bugalter kabi metrikasiz lavozimda ko'rinmaydi.

---

## 1. Kirish

### `/start`
- **Kim:** hamma (yagona ochiq buyruq) — lekin hisob oldindan yaratilgan bo'lishi kerak.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Telegram akkauntni xodim yozuviga bog'laydi, asosiy menyuni va
  lavozimga mos «/» menyusini beradi.
  - **Havola bilan** (`/start <kod>`): kodga mos xodimni topib bog'laydi; akkaunt
    ilgari boshqa xodimga bog'langan bo'lsa — eskisi avtomatik bekor qilinadi.
    Mobilograf «o'rin» (seat) havolasi qayta ishlatiladigan.
  - **Kodsiz:** botni «ishga tushirilgan» deb belgilaydi va menyuni ko'rsatadi.

### `/buyruqlar`
- **Kim:** hamma ro'yxatdan o'tgan xodim.
- **Qayerda:** shaxsiy chat va guruh.
- **Nima qiladi:** shu chat turida O'ZIGA ruxsat etilgan buyruqlarni izohi bilan
  chiqaradi; shaxsiy chatda «faqat guruhda ishlaydi» turkumini alohida ko'rsatadi.
  Har chaqiruvda «/» menyusini ham yangilaydi (kesh eskirsa o'zi tuzaladi).

---

## 2. Statistika, norma va davomat

### `/statistika`
- **Kim:** HR / ROP / Boshliq / Dasturchi.
- **Qayerda:** faqat `main` yoki `stats` sifatida biriktirilgan guruhda.
- **Nima qiladi:** kunlik yagona hisobotni (vazifalar + qo'ng'iroq/lid/tashrif +
  AI xulosa, bitta xabar) darhol shu guruhga yuboradi.

### `/statistika_vaqt [SS:DD]`
- **Kim:** Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh.
- **Nima qiladi:** kunlik digest avtomatik yuboriladigan vaqtni ko'rsatadi
  (argumentsiz) yoki o'zgartiradi (`/statistika_vaqt 20:00`).

### `/oylik`
- **Kim:** HR / ROP / Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh — natija shu chatga keladi.
- **Nima qiladi:** oylik yakuniy hisobot (joriy oy vs o'tgan oy, operator
  kesimida, bonus bilan).

### `/davomat_vaqt [ertalab|kechqurun HH:MM | on|off]`
- **Kim:** ko'rish — HR/ROP/Boshliq; o'zgartirish — faqat Boshliq.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** kunlik davomat (kechikish) hisobotining ertalabki va kechki
  yuborilish vaqtini ko'rsatadi/sozlaydi, yoqadi/o'chiradi.

### `/reja`
- **Kim:** HR / ROP / Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh.
- **Nima qiladi:** nazoratdagi xodimlar ro'yxatini tugma qilib chiqaradi; xodim
  tanlanganda uning bugungi soatma-soat rejasi (norma vs bajarilgan) ko'rsatiladi.

### `/norma_ozgartir`
- **Kim:** ROP (o'z jamoasi), HR (biriktirilgan lavozimlar), Boshliq/Dasturchi (hamma).
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** bosqichma-bosqich: xodim → ko'rsatkich (Suhbat / Tashrif /
  Oddiy video / Dumaloq video) → yangi son. Norma shu kundan kuchga kiradi.

---

## 3. Sotuv AI va bilim bazasi

### `/ai_sozlama`
- **Kim:** ko'rish — HR/ROP/Boshliq; o'zgartirish — faqat Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Operator AI qismlarini (kunlik/haftalik xulosa, kechikish
  ogohlantirishi, issiq lid) ✅/❌ tugma bilan yoqib-o'chirish.

### `/ai_markazi`
- **Kim:** Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Sotuv AI'ning to'rtta bo'limini (anketa, bilim bazasi,
  playbook, sinov rejimi) bitta panelda — holati va keyingi qadam bilan.

### `/bilim`
- **Kim:** Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** bilim bazasi holati; anketa javoblaridan AI orqali yangi
  yozuv chiqarish, tasdiqlash/tahrirlash/o'chirish, qo'lda qo'shish, eksport.

### `/playbook`
- **Kim:** Boshliq / Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** «vaziyat → texnika → ibora» qo'llanmasi paneli: AI orqali
  qurish, ko'rib chiqib tasdiqlash, eksport.

### `/sotuv_ai`
- **Kim:** sotuv ko'rsatkichi bor xodim + ROP/Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** «Mijoz savoliga AI javobi» rejimi — xodim savolni yozadi, AI
  tasdiqlangan bilim bazasi + playbook asosida rasmiy javob taklif qiladi.
  Bazada javob topilmasa «bilim bo'shlig'i» sifatida rahbarga xabar boradi.

### `/anketa`
- **Kim:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** savol to'plamini yuklash (.docx/.txt), kimlarga va qachon
  yuborishni sozlash, sessiya holatini kuzatish, javoblarni yuklab olish.

### `/ai_vaqt` *(eskirgan)*
- Reestrda **yo'q** — «/» menyusida ko'rinmaydi va to'silmaydi. Bot uni
  tushuntirib, o'rniga `/statistika_vaqt`ni tavsiya qiladi.

---

## 4. Guruh boshqaruvi (faqat Dasturchi)

### `/guruh_biriktir <mobilograf|main|stats>`
- **Qayerda:** guruh ICHIDA (aynan shu guruhni belgilash uchun).
- **Nima qiladi:** joriy guruhni ko'rsatilgan maqsadga biriktiradi:
  - `mobilograf` — video kuzatiladigan guruh (bitta faol; yangisi eskisini almashtiradi);
  - `main` — asosiy guruh: issiq lid, `/statistika`, davomat xabarlari (bitta faol);
  - `stats` — qo'shimcha statistika/digest guruhi (bir nechtasi bo'lishi mumkin).

### `/guruh_ochir <mobilograf|main|stats>`
- **Qayerda:** guruh ICHIDA.
- **Nima qiladi:** joriy guruhni shu maqsad ro'yxatidan olib tashlaydi.

### `/guruhlar`
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** qaysi guruh qaysi maqsadga biriktirilganini ro'yxat qilib beradi.

---

## 5. Mobilograf guruhidagi buyruq-bo'lmagan harakatlar

| Harakat | Kim | Natija |
|---|---|---|
| Guruhga oddiy video yuborish | mobilograf | «Oddiy video», «kutilmoqda» holatida |
| Guruhga dumaloq video (video-message) | mobilograf | «Dumaloq video» sifatida |
| Videoga uzoq bosib ✅ reaksiya | boshliq/rahbar/dasturchi | Tasdiqlaydi |
| Videoga **reply** qilib ✅ yozish | boshliq/rahbar/dasturchi | Xuddi reaksiya kabi (amaliyotda ko'proq shu) |
| ✅ reaksiyani olib tashlash | tasdiqlagan shaxs | Tasdiqni bekor qiladi |

---

## 6. Dasturchi rejimi (super-admin)

`OYLIK_JARIMA_REJASI.md` 11-bo'lim. Har biri sababni FSM orqali so'raydi (kamida
5 belgi) — sabab `AuditLog(action="override_*")` ga yoziladi, Boshliq buni
saytdagi «Dasturchi rejimi» → «Override tarixi» tabidan ko'radi. Kengroq
boshqaruv (barcha jadvallar, payroll qulflari) — saytda `/dasturchi`.

### `/norm_set <xodim> <metrika> <qiymat>`
HAR QANDAY qiymatni, metrika/lavozim cheklovisiz, HAR QANDAY rolga belgilaydi
(masalan `/norm_set Aziz Karimov suhbat 40`). Ism bo'yicha qisman moslik
ishlaydi; bir nechta topilsa `#ID` bilan aniqlashtirish so'raladi.

### `/norm_del <xodim> <metrika>`
Shu metrika bo'yicha barcha FAOL tarix qatorlarini yumshoq o'chiradi
(keyin `/undo` bilan bittalab tiklash mumkin).

### `/att_fix <xodim> <YYYY-MM-DD> <HH:MM>`
Shu kunga kelish vaqtini qo'lda belgilaydi/tuzatadi (kechikish va ishlangan
vaqt ish jadvali asosida qayta hisoblanadi). Face ID/GPS ishlamagan holatlar uchun.

### `/unlock <YYYY-MM>`
Tasdiqlangan (qulflangan) oylik ish haqi davrini ochadi — shundan keyin HR
qayta hisoblay oladi. Masalan `/unlock 2026-07`.

### `/undo <norma ID>`
Yumshoq o'chirilgan NORMA yozuvini ID bo'yicha tiklaydi (ID — `/dasturchi`
saytidagi «Yozuvlar» yoki «Override tarixi» tabida ko'rinadi).

---

## Texnik eslatma

| Fayl | Vazifasi |
|---|---|
| `api/services/sections.py` | **Yagona manba:** `ALL_COMMANDS`, `commands_for`, `bot_commands_payload` |
| `api/routers/users.py` | `_with_bot_view` — javobga `bot_menu` + `bot_commands` qo'shadi |
| `bot/commands.py` | «/» menyusini o'rnatish, buyruq matnini ajratish, `check_access` |
| `bot/middlewares.py` | `CommandGuard` — ruxsat/joy nazorati va aniq xato matni |
| `bot/handlers/help.py` | `/buyruqlar` |
| `test.py::test_bot_commands_by_role` | 36 tekshiruv: reestr to'liqligi, rol namunalari, rad etish sabablari |

Handlerlardagi eski rol tekshiruvlari **ataylab qoldirilgan** — ikkinchi qavat
(guard o'chirilsa yoki backend javob bermay guard buyruqni o'tkazib yuborsa).
