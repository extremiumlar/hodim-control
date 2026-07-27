# Telegram bot — to'liq buyruqlar ro'yxati

Ushbu hujjat botdagi barcha `/buyruq`larni, ularni kim ishlata olishini va qayerda
(shaxsiy chat / guruh) ishlashini tasvirlaydi. Ko'pchilik funksiyalar asosiy
menyudagi tugmalar orqali ham ishlaydi (masalan "📈 Statistikam") — bu yerda
faqat **slash-buyruqlar** (`/...`) ro'yxati keltirilgan.

---

## 1. Kirish

### `/start`
- **Kim ishlatadi:** hamma — lekin faqat tizimda oldindan yaratilgan (HR/Boshliq/Dasturchi tomonidan) foydalanuvchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Telegram akkauntni tizimdagi xodim yozuviga bog'laydi. Ikki holat bor:
  - **Havola bilan** (`/start <kod>`, web paneldan olingan link): kodga mos foydalanuvchini topib, shu Telegram akkauntga bog'laydi. Agar bu akkaunt oldin boshqa xodimga bog'langan bo'lsa — eski bog'lanish avtomatik bekor qilinadi. Mobilogrof "o'rin" (seat) uchun link doim qayta ishlatiladigan — yangi odam shu orqali `/start` bossa, avvalgi egasi avtomatik almashadi.
  - **Kodsiz** (oddiy `/start`): agar bu Telegram akkaunt allaqachon bog'langan bo'lsa, shunchaki botni "ishga tushirilgan" deb belgilaydi va asosiy menyuni ko'rsatadi.

---

## 2. Guruh boshqaruvi (faqat Dasturchi)

### `/guruh_biriktir <mobilograf|main|stats>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** guruh ICHIDA (shu guruhni belgilash uchun aynan shu yerda yozilishi kerak).
- **Nima qiladi:** Joriy guruhni ko'rsatilgan maqsadga biriktiradi:
  - `mobilograf` — video kuzatiladigan guruh (bir vaqtda faqat bitta faol; yangisi eskisini avtomatik almashtiradi).
  - `main` — asosiy guruh: issiq lid ogohlantirishlari, `/statistika`, davomat xabarlari (bir vaqtda faqat bitta faol).
  - `stats` — qo'shimcha statistika/digest guruhi (bir nechtasi bo'lishi mumkin).

### `/guruh_ochir <mobilograf|main|stats>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** guruh ICHIDA.
- **Nima qiladi:** Joriy guruhni ko'rsatilgan maqsad ro'yxatidan olib tashlaydi (deaktivatsiya qiladi).

### `/guruhlar`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Hozir qaysi guruh qaysi maqsadga (mobilograf/main/stats) biriktirilganini to'liq ro'yxat qilib ko'rsatadi.

---

## 3. Norma, statistika va davomat

### `/norma_ozgartir`
- **Kim ishlatadi:** ROP (o'z jamoasi), HR (o'ziga biriktirilgan lavozimlar), Boshliq/Dasturchi (hamma xodim).
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Bosqichma-bosqich (tugmalar orqali): 1) xodim tanlanadi, 2) o'sha xodim lavozimida kuzatiladigan ko'rsatkich tanlanadi (Suhbatlar / Tashriflar / Oddiy videolar / Dumaloq videolar), 3) yangi son matn sifatida kiritiladi. Norma shu kundan kuchga kiradi.

### `/statistika`
- **Kim ishlatadi:** faqat HR/ROP/Boshliq/Dasturchi.
- **Qayerda:** faqat sozlangan guruh(lar)da (asosiy yoki statistika guruhi) — boshqa joyda ishlamaydi.
- **Nima qiladi:** Kunlik yagona hisobotni (vazifalar + qo'ng'iroq/lid/tashrif + AI xulosa, bitta xabar) darhol shu guruhga yuboradi — avtomatik kechqurun yuboriladigan digestni qo'lda, tezroq chaqirish uchun.

### `/statistika_vaqt [SS:DD]`
- **Kim ishlatadi:** faqat Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh.
- **Nima qiladi:** Kunlik digest guruhga avtomatik yuboriladigan vaqtni ko'rsatadi (argumentsiz) yoki o'zgartiradi (masalan `/statistika_vaqt 20:00`).

### `/oylik`
- **Kim ishlatadi:** faqat HR/ROP/Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh — natija shu chatning o'ziga yuboriladi.
- **Nima qiladi:** Oylik yakuniy hisobotni (joriy oy vs o'tgan oy, operator kesimida, bonus bilan) darhol yuboradi.

### `/davomat_vaqt [ertalab|kechqurun HH:MM | on|off]`
- **Kim ishlatadi:** ko'rish — HR/ROP/Boshliq; o'zgartirish — faqat Boshliq.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Kunlik davomat (kechikish) hisobotining ertalabki va kechki avtomatik yuborilish vaqtini ko'rsatadi/sozlaydi, yoqadi/o'chiradi.

### `/reja`
- **Kim ishlatadi:** faqat HR/ROP/Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat yoki guruh.
- **Nima qiladi:** Rahbar nazoratidagi xodimlar ro'yxatini tugma qilib chiqaradi; bittasi tanlanganda o'sha xodimning bugungi soatma-soat ish rejasi (norma vs haqiqiy bajarilgan) alohida ko'rsatiladi.

---

## 4. Sotuv AI va bilim bazasi

### `/ai_markazi`
- **Kim ishlatadi:** faqat Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Sotuv AI'ning to'rtta bo'limini (savol to'plamlari/anketa, bilim bazasi, playbook, sinov rejimi) bitta umumiy boshqaruv panelida — har birining holati va tavsiya etilgan keyingi qadam bilan — ko'rsatadi.

### `/anketa`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Xodimlardan savol-javob anketasi olish jarayonini boshqaradi: savol to'plamini yuklash (.docx/.txt), kimlarga (hammaga bir xil yoki har kimga alohida taqsimlab) va qachon (darhol yoki rejalashtirilgan vaqtda) yuborishni sozlash, joriy sessiya holatini kuzatish, javoblarni yuklab olish.

### `/bilim`
- **Kim ishlatadi:** faqat Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Sotuv bilim bazasi holatini (tasdiqlangan/kutayotgan/bo'shliq yozuvlar) ko'rsatadi; anketa javoblaridan yangi yozuvlarni AI orqali chiqarish, ularni birma-bir tasdiqlash/tahrirlash/o'chirish, qo'lda savol-javob qo'shish, yoki bazani faylga eksport qilish imkonini beradi.

### `/playbook`
- **Kim ishlatadi:** faqat Boshliq/Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** "Sotuv playbook" (vaziyat → texnika → ibora qo'llanmasi) panelini ochadi — AI orqali qurish, yozuvlarni ko'rib chiqib tasdiqlash, yoki faylga eksport qilish.

### `/sotuv_ai`
- **Kim ishlatadi:** ro'yxatdan o'tgan operator/sotuv xodimlari va rahbarlar.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** "Mijoz savoliga AI javobi" rejimini yoqadi — xodim mijoz savolini yozadi, AI tasdiqlangan bilim bazasi + playbook asosida tayyor rasmiy javob taklif qiladi. Bazada javob topilmasa, "bilim bo'shlig'i" sifatida rahbarga xabar boradi.

---

## 5. Operator AI kuzatuvi

### `/ai_sozlama`
- **Kim ishlatadi:** ko'rish — ROP/Boshliq; o'zgartirish — faqat Boshliq.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Operator AI qismlarining (kunlik/haftalik xulosa, kechikish ogohlantirishi, issiq lid) har birini alohida ✅/❌ tugma bilan yoqib-o'chirish.

### `/ai_vaqt` *(eskirgan)*
- **Kim ishlatadi:** hamma.
- **Qayerda:** istalgan joy.
- **Nima qiladi:** Bu buyruq endi ishlamaydi (AI xulosa endi kunlik digest bilan birga chiqadi, alohida vaqti yo'q) — bot buni tushuntirib, o'rniga `/statistika_vaqt`ni tavsiya qiladi.

---

## 6. Mobilogrof guruhidagi buyruq-bo'lmagan harakatlar

Bular slash-buyruq emas, lekin mobilogrof oqimining asosiy qismi:

| Harakat | Kim | Natija |
|---|---|---|
| Guruhga oddiy video yuborish | mobilogrof | "Oddiy video" sifatida "kutilmoqda" holatida yoziladi |
| Guruhga dumaloq video (video-message) yuborish | mobilogrof | "Dumaloq video" sifatida yoziladi |
| Videoga uzoq bosib ✅ reaksiya qo'yish | boshliq/rahbar/dasturchi | Videoni tasdiqlaydi |
| Videoga **reply** qilib matnda ✅ yuborish | boshliq/rahbar/dasturchi | Xuddi reaksiya kabi tasdiqlaydi (amaliyotda ko'proq shu ishlatiladi) |
| ✅ reaksiyani olib tashlash | tasdiqlagan shaxs | Tasdiqni bekor qiladi |

---

## 7. Dasturchi rejimi (super-admin, faqat Dasturchi)

OYLIK_JARIMA_REJASI.md 11-bo'lim. Har biri sababni FSM orqali so'raydi (kamida
5 belgi) — sabab `AuditLog(action="override_*")`ga yoziladi, Boshliq buni
saytdagi «Dasturchi rejimi» → «Override tarixi» tabidan ko'ra oladi. Bu
buyruqlar tez-tez kerak bo'ladigan 5 tasini qamraydi (11.5-band ro'yxati);
kengroq boshqaruv (barcha 11 jadval, payroll qulflari, tizim darajasi) —
saytda `/dasturchi` (faqat dasturchi).

### `/norm_set <xodim> <metrika> <qiymat>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** HAR QANDAY qiymatni, metrika/lavozim cheklovisiz, HAR
  QANDAY rolga (HR/ROP/Boshliq ham) belgilaydi — oddiy `/norma_ozgartir`dan
  farqli, bu yerda hech qanday tekshiruv yo'q. Masalan: `/norm_set Aziz
  Karimov suhbat 40`. Xodim ismi bo'yicha qisman moslik ishlaydi; bir nechta
  topilsa `#ID` bilan aniqlashtirish so'raladi.

### `/norm_del <xodim> <metrika>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Shu xodimning shu metrika bo'yicha barcha FAOL tarix
  qatorlarini yumshoq o'chiradi (butunlay tozalaydi, keyin `/undo` bilan
  bittalab tiklash mumkin).

### `/att_fix <xodim> <YYYY-MM-DD> <HH:MM>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Shu kunga xodimning kelish vaqtini qo'lda belgilaydi/
  tuzatadi (`PUT /attendance/manual` — kechikish/ishlangan vaqt ish jadvali
  asosida qayta hisoblanadi). Face ID/GPS ishlamay qolgan holatlar uchun.

### `/unlock <YYYY-MM>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Tasdiqlangan (qulflangan) oylik ish haqi davrini ochadi —
  shundan keyin HR qayta hisoblay oladi. Masalan: `/unlock 2026-07`.

### `/undo <norma ID>`
- **Kim ishlatadi:** faqat Dasturchi.
- **Qayerda:** shaxsiy chat.
- **Nima qiladi:** Yumshoq o'chirilgan NORMA yozuvini ID bo'yicha tiklaydi
  (ID — `/dasturchi` saytidagi «Yozuvlar» tabida yoki «Override tarixi»da
  ko'rinadi). Faqat normalar uchun (asosiy talab); boshqa jadvallarni
  tiklash uchun sayt ishlatiladi.
