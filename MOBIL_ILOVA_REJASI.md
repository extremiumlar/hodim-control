# Mobil ilova — reja va arxitektura (loyihalashtirish bosqichi)

> Holat: **REJALASHTIRISH**. Hali kod yozilmagan. Ushbu hujjat — nima
> qurilishi, qanday arxitektura bilan, qaysi tartibda va qaysi ochiq
> savollar hal qilinishi kerakligi haqida umumiy xarita. Tasdiqlangandan
> keyin bosqichma-bosqich amalga oshiriladi.

## 1. Nega kerak (motivatsiya)

Hozir tizim uchta "old tomon"ga bo'lingan:

- **Telegram bot** — xodimlar uchun asosiy interfeys (davomat, ish jadvali,
  oylik, vazifalar, bilim bazasi, anketa).
- **Web (React)** — rahbarlar uchun boshqaruv paneli (dashboard, hisobotlar,
  tasdiqlashlar, CRUD).
- **Face ID check-in** — brauzerda ishlaydi (`@vladmandic/face-api`, HTTPS
  self-signed sertifikat, kamera ruxsati) — bu eng ko'p bug chiqargan joy
  ([[attendance-feature]] xotirasida "Keldim ishlamayapti" hodisasi,
  sertifikat/HTTPS muammolari bir necha marta qayd etilgan).

Mobil ilova uchta muammoni birdan yechadi:
1. **Native kamera+GPS** — brauzer sertifikat/ruxsat muammolarisiz barqaror
   Face ID + joylashuv.
2. **Bitta yaxlit tajriba** — xodim ham, rahbar ham bot+veb o'rtasida
   sakramaydi, hammasi bitta ilovada.
3. **Push-bildirishnoma** — Telegram xabarlaridan mustaqil, ishonchliroq
   background yetkazish (eslatmalar, issiq lid, digest).

Bot **saqlanib qoladi** — ilova o'rnatmagan xodimlar uchun zaxira va
tezkor buyruqlar kanali sifatida.

## 2. Ko'lam va foydalanuvchilar

Bitta ilova, **rolga qarab UI** (xuddi web'dagi kabi `role` asosida):

- **employee** — davomat (Face ID+GPS check-in/out), ish jadvali, oylik/
  jarima, vazifalar, bilim bazasi, anketa, soatma-soat reja.
- **hr / rop / boss / dasturchi** — yuqoridagilar + davomat dashboard,
  hisobotlar, tasdiqlashlar (excused days, bonuslar), lid statistikasi,
  AI markaz (issiq lid, kuzatuv).

**Bosqichlash mantig'i:** xodim funksiyalari MVP'da to'liq bo'lishi kerak
(kundalik ishlatiladigan telefon funksiyasi), rahbar funksiyalari birinchi
bosqichda faqat "tezkor ko'rish" darajasida (to'liq CRUD/hisobot hozircha
web'da qoladi, keyingi bosqichda ilovaga ko'chadi).

## 3. Tex-stack

- **React Native + Expo (managed workflow)** — jamoa allaqachon React+TS
  biladi (`web/src`), backend REST API tayyor, bitta kod bazasi iOS+
  Android.
- **Navigatsiya:** `expo-router` (fayl-asosli, web'dagi `pages/` tuzilishiga
  konseptual yaqin).
- **State/data:** `@tanstack/react-query` — web'da allaqachon shu pattern
  ishlatilgan ([[frontend-overhaul]]), API klienti deyarli bir xil bo'ladi.
- **UI:** oddiy component kit (masalan `react-native-paper` yoki
  tailwind-uslub `nativewind`) — shadcn/ui'ning to'g'ridan-to'g'ri RN
  analogi yo'q, shuning uchun yangi tanlov kerak.
- **Build/deploy:** EAS Build (Expo Application Services) — Windows'dagi
  dev mashinada Android Studio/Xcode shart emas, bulutda build qilinadi;
  test uchun Expo Go ilovasi orqali jonli reload.
- **Push:** Expo Push Notifications (ikkala platforma uchun yagona API,
  orqasida FCM/APNs).

## 4. Backend'ga kerak bo'ladigan o'zgarishlar

Mavjud FastAPI backend **qayta ishlatiladi** (yangi backend YO'Q) — lekin
quyidagi qo'shimchalar kerak bo'ladi:

### 4.1 Autentifikatsiya — QAROR: deep-link + bir martalik token

Web'da `telegram-login` — Telegram Login Widget (JS, domenga bog'liq) orqali
ishlaydi; bu **native ilovada ishlamaydi** (widget web sahifa talab qiladi).
Tanlangan yechim — mavjud `bot-token` patterniga o'xshash, lekin foydalanuvchi
tomonidan boshlanadigan oqim:

1. Ilova ochilganda backend'dan **kriptografik tasodifiy token** so'raladi:
   `POST /auth/app-login/start` → `{login_token, deep_link, expires_at}`
   (token hali hech qanday `telegram_id`ga bog'lanmagan, faqat "session"ni
   belgilaydi).
2. Ilova foydalanuvchini `t.me/<bot>?start=applogin_<login_token>` deep-link
   bilan botga yo'naltiradi (bitta tugma bosish — foydalanuvchi allaqachon
   botda bo'lsa, Telegram avtomatik ochadi).
3. Bot `/start applogin_<token>` ni qabul qilib, **allaqachon bazada bor**
   `telegram_id` orqali foydalanuvchini aniqlaydi va tasdiqlash tugmasi
   ko'rsatadi ("Ushbu ilovaga kirishni tasdiqlaysizmi? ✅"), so'ng
   `POST /auth/app-login/confirm` (X-Bot-Secret bilan, boshqa bot
   endpointlari kabi) ni `{login_token, telegram_id}` bilan chaqiradi —
   backend token'ni shu foydalanuvchiga bog'laydi va **bir martalik**
   belgilaydi (qayta ishlatib bo'lmaydi).
4. Ilova fonda `POST /auth/app-login/poll {login_token}` ni bir necha
   soniyada bir chaqirib turadi (yoki WebSocket/long-poll) — tasdiqlangach
   JWT qaytadi, xuddi `telegram-login`/`bot-token` kabi `TokenOut`.

Xavfsizlik qoidalari (implementatsiyada shart):
- `login_token` kamida 32 bayt tasodifiy (`secrets.token_urlsafe`), TTL 5
  daqiqa, ishlatilgach yoki muddati o'tgach bazadan o'chadi/`used=true`.
- `app-login/confirm` faqat bot orqali (`X-Bot-Secret`) chaqiriladi —
  ilova to'g'ridan-to'g'ri `telegram_id` yubora olmaydi (aks holda
  istalgan kishi boshqa birovning ID'sini yozib login qila oladi).
- `app-login/poll` javobida token holatini oshkor qilmaslik (faqat
  pending/confirmed/expired), brute-force uchun rate-limit.
- Bitta qurilma/sessiya = bitta `login_token`; eski token'lar tozalanadi.

Bu login oqimi keyinchalik **push-token ro'yxatdan o'tkazish bilan bir
qatorda** ishlaydi — tasdiqlangan zahoti ilova o'z push-token'ini ham
yuboradi (4.3).

### 4.2 Face ID — server vs on-device
Hozirgi model brauzerda `face-api.js` (TensorFlow.js, 128-dim descriptor)
bilan ishlaydi. Native ilovada ikkita yo'l bor:

- **(A) Server-side matching (tavsiya):** ilova faqat kamera orqali
  selfie+liveness challenge (masalan "ko'zingizni yuming" yoki bosh
  burish) oladi va rasmni backend'ga yuboradi; backend python
  (`face_recognition`/`dlib` yoki `mediapipe`) bilan descriptor chiqarib
  taqqoslaydi. Afzalligi — bitta model manbasi, ammo **eski
  ro'yxatdan o'tgan yuzlar (face-api.js bilan yaratilgan) qayta
  ro'yxatdan o'tkazilishi kerak** (descriptor formati boshqa bo'ladi).
- **(B) On-device matching:** TFLite/MobileFaceNet bilan telefonda hisoblab,
  faqat natijani yuborish — tezroq, lekin ikkita alohida ML pipeline
  saqlash og'irlik qo'shadi.

**Qaror kerak:** (A) tavsiya qilinadi (soddaroq, yagona haqiqat manbai),
lekin bu amaliy ta'sir — xodimlar birinchi marta ilova ochganda yuzni
qayta ro'yxatdan o'tkazishi kerak bo'ladi.

### 4.3 Push-token ro'yxatdan o'tkazish
Yangi jadval `push_tokens` (user_id, expo_push_token, platform, created_at)
+ endpoint `POST /users/me/push-token`. Mavjud digest/hot-lead/eslatma
yuboruvchi kod (`attendance_digest.py`, `hot_lead.py`, `daily_digest.py`)
Telegram'ga qo'shimcha shu jadvaldan push yuborish bilan boyitiladi.

### 4.4 Personalizatsiya — mavjud mexanizmni kengaytirish

Bot allaqachon **statik emas** — har xodimning menyusi `Position.menu_flags`
(masalan `{"tasks": true, "norm": true, "kpi": true, "excused": true}`) va
`Position.metrics` (masalan `["suhbat", "tashrif"]`) asosida qurilishi
(`bot/keyboards.py: main_menu`/`menu_for_user`) — bu ishlab chiqilgan,
sinovdan o'tgan tizim. Mobil ilova **xuddi shu backend maydonlaridan**
foydalanadi, faqat chiroyliroq UI'da:

- **Bosh ekran tayl (tile)lari** `role` + `position.menu_flags` bo'yicha
  dinamik quriladi — flag `false` bo'lgan bo'lim umuman ko'rinmaydi
  (masalan KPI'siz lavozimda "Oylik KPI'm" tayli yo'q).
- **Norma/ko'rsatkich widget'i** `position.metrics` ro'yxatiga qarab
  o'zgaruvchan bo'lim(lar) chiqaradi (mobilograf — video soni, sotuvchi —
  suhbat/tashrif) — bugungi bot `show_norm`dagi mantiqning vizual versiyasi.
- **Rol bo'yicha pastki navigatsiya (tab bar)** farqlanadi: employee'da
  Bosh/Davomat/Jadval/Vazifalar/Ko'proq; rahbarlarda qo'shimcha
  Boshqaruv/Tasdiqlashlar tab'i qo'shiladi.
- **Jamoa ko'lami (scope):** `rop`/`hr` — faqat `team_id` mos xodimlarni
  ko'radi (mavjud API filtri bilan bir xil), `boss`/`dasturchi` — hammasini.
  Bu backend'da allaqachon bor filtrlash mantig'ini frontendga to'g'ri
  ulash masalasi, yangi backend kodi shart emas.
- **Push-bildirishnoma toifalari sozlanadi:** har foydalanuvchi qaysi
  toifani olishini tanlaydi (masalan employee — faqat "mening eslatmalarim";
  rop/boss — qo'shimcha "issiq lid", "kim kelmadi"). Standart qiymat rolga
  qarab oldindan belgilanadi, foydalanuvchi Sozlamalar ekranida o'zgartira
  oladi.
- **Birinchi ochilish holatlari (onboarding/empty-state)** kontekstga mos:
  yuz ro'yxatdan o'tmagan bo'lsa — bosh ekranda "Yuzingizni ro'yxatdan
  o'tkazing" banner; norma/lavozim belgilanmagan bo'lsa — botdagi kabi
  tushunarli xabar (umidsizlantiradigan bo'sh ekran o'rniga).
- **Kun vaqtiga mos salomlashish** ("Xayrli tong, {ism}!") + eng dolzarb
  amal birinchi joyda (masalan ish boshlanish vaqti yaqin bo'lsa — Check-in
  tugmasi katta va tepada; ish tugagandan keyin — Check-out taklif qilinadi).
- **Tizim mavzusi (dark/light)** — Expo/`nativewind` bilan arzon qo'shiladi,
  hozircha web'da yo'q ([[frontend-overhaul]]) — mobil uchun qo'shish
  tavsiya etiladi (foydalanuvchilar telefonda buni kutadi), lekin MVP'ni
  bloklamaydigan "nice-to-have" sifatida belgilanadi.
- **Shrift kattalashtirish/accessibility** — tizim sozlamalariga (katta
  matn) hurmat qilinadi, RN standart komponentlari buni bepul beradi.

Amaliy natija: har lavozim/rol o'zi kerak bo'lmagan tugma/bo'limni
umuman ko'rmaydi — bosh ekran "hammaga bitta" emas, balki backend'dagi
mavjud `menu_flags`/`metrics`/`team_id` ma'lumotidan **avtomatik** quriladi
(qo'lda har rol uchun alohida ekran yozish shart emas — bitta moslashuvchan
komponent yetarli).

### 4.5 Boshqa API o'zgarishlar
Ko'pchilik endpoint (work_schedule, payroll, tasks, knowledge, anketa)
**o'zgarishsiz qayta ishlatiladi** — ular allaqachon JWT-based REST API.
Faqat mobil uchun qulaylik uchun ba'zi "aggregate" endpointlar qo'shilishi
mumkin (masalan bitta `/mobile/home-summary` — bugungi davomat holati +
vazifalar soni + bildirishnomalar bitta so'rovda, ilovaning bosh ekrani
tez ochilishi uchun) — bu optimallashtirish, MVP'da shart emas.

## 5. Ekranlar (birinchi bosqich — xodim MVP)

1. **Kirish** — deep-link/bot orqali login (4.1-band).
2. **Bosh sahifa** — `position.menu_flags`/`metrics`ga qarab dinamik
   taylar (4.4-band), kun vaqtiga mos salomlashuv, bugungi davomat holati
   birinchi o'rinda.
3. **Check-in/Check-out** — kamera (liveness) + GPS, natija (kechikdi/
   vaqtida/xatolik); yuz ro'yxatdan o'tmagan bo'lsa — avval ro'yxatdan
   o'tkazish oqimi.
4. **Ish jadvali** — haftalik andoza + bugungi smena (`menu_flags.schedule`
   yo'q bo'lsa umuman ko'rinmaydi).
5. **Oylik/jarima** — joriy oy hisob-kitobi (faqat ko'rish, `menu_flags.kpi`
   ga bog'liq).
6. **Vazifalar** — ro'yxat + holat belgilash (`menu_flags.tasks`).
7. **Bilim bazasi** — qidiruv/ko'rish (anketa orqali to'plangan).
8. **Bildirishnomalar** — push tarixi + toifa sozlamalari (4.4-band).
9. **Sozlamalar/Profil** — til (agar kerak bo'lsa), push toifalari, yuzni
   qayta ro'yxatdan o'tkazish, chiqish.

## 6. Ekranlar (ikkinchi bosqich — rahbar)

Rahbar tab-bariga qo'shiladigan bo'limlar — `team_id` bo'yicha avtomatik
qamrovli (rop/hr — o'z jamoasi, boss/dasturchi — hammasi):

1. Davomat dashboard (bugun/hafta, kim kelmadi/kechikdi).
2. Tasdiqlashlar (excused days, bonuslar) — push kelganda bir tegishda
   tasdiqlash/rad etish (deep push action, ekranga kirmasdan).
3. Lid statistikasi (qisqacha, to'liq grafik hali web'da).
4. Issiq lid bildirishnomalari (AI markaz) — faqat shu toifaga obuna
   bo'lganlarga (4.4-band push sozlamalari).

## 7. Yo'l xaritasi (bosqichlar)

| Bosqich | Mazmun | Chiqish mezoni |
|---|---|---|
| 0 | ✅ Arxitektura qarorlari — auth (deep-link+token) va face-matching (server-side) tasdiqlandi | Bajarildi 2026-07-27 |
| 1 | ✅ Expo loyiha skeleton + auth (deep-link login) + API klient — jonli telefonda (Samsung) APK o'rnatildi va login ishladi | Bajarildi 2026-07-30 |
| 2 | Face ID+GPS check-in/out (server-side matching) | Jonli xodim bilan sinov — check-in muvaffaqiyatli |
| 3 | Ish jadvali, oylik, vazifalar, bilim bazasi (faqat o'qish) | Xodim MVP tayyor — ichki beta (TestFlight/Play internal) |
| 4 | Push-bildirishnoma infratuzilmasi | Digest/hot-lead push orqali ham keladi |
| 5 | Rahbar ekranlari (dashboard, tasdiqlashlar) | Rahbar ham ilovadan asosiy ishni qila oladi |
| 6 | Store'ga chiqarish (Google Play + App Store) | Public/ichki tarqatish |

## 8. Ochiq savollar (boshlashdan oldin hal qilinishi kerak)

1. ~~Auth oqimi~~ — **HAL BO'LDI**: deep-link + bir martalik token (4.1-band).
2. ~~Face matching~~ — **HAL BO'LDI**: server-side (A variant) — xodimlar
   ilovada yuzni qayta ro'yxatdan o'tkazadi (4.2-band).
3. **App Store/Play Console hisoblari** — kompaniya nomidan ro'yxatdan
   o'tganmi? ($99/yil Apple, bir martalik $25 Google) — bo'lmasa, birinchi
   navbatda shuni ochish kerak (build tayyor bo'lgan payt kutib qolmaslik
   uchun).
4. **Offline rejim** — GPS/kamera check-in internetsiz joyda ishlashi
   kerakmi (keyin sinxronlanadi), yoki doim onlayn talab qilinadi (soddaroq,
   tavsiya — MVP uchun onlayn talab qilish yetarli)?
5. **Minimal qo'llab-quvvatlanadigan versiya** — eng eski Android/iOS
   qaysi versiyagacha (xodimlarning aksariyati qanday telefon ishlatadi)?
6. **Push toifalari standart to'plami** (4.4) — har rol uchun qaysi
   toifalar boshlang'ich holatda YOQIQ bo'lishi kerak (haddan tashqari
   ko'p push — o'chirib qo'yishga olib kelishi mumkin)?

## 8.5 APK yasash va telefonga o'rnatish (Bosqich 1 amaliyoti)

Store'ga chiqmagunimizcha (Bosqich 6) APK'ni qo'lda tarqatamiz. Shu bosqichda
uchragan real muammolar va ularning yechimi:

### Build

```
cd mobile/android
./gradlew assembleRelease
```

Natija: `mobile/android/app/build/outputs/apk/release/app-release.apk`

- Release kaliti: `D:/Android/keystores/hodimlar-release.keystore`
  (yo'l va parollar `mobile/android/gradle.properties` da). **Bu fayl
  yo'qolsa, eski ilova ustiga yangi APK o'rnatilmaydi** — zaxirasi shart.
- APK **v1+v2+v3** imzo bilan imzolanadi (`app/build.gradle` →
  `signingConfigs.release`). v1 ataylab yoqilgan: MIUI va One UI'ning ba'zi
  versiyalari yon o'rnatishda (sideload) hali ham JAR imzoni tekshiradi va
  faqat-v2 APK'ni "ilova o'rnatilmadi" deb rad etadi.

### ⚠️ Samsung «Auto Blocker» — eng ko'p uchraydigan to'siq

Samsung One UI 6.1+ da **Auto Blocker** (Avtomatik bloklovchi) funksiyasi bor.
Yoqilgan bo'lsa, do'kondan tashqari **har qanday** APK o'rnatilishini to'sadi —
«noma'lum manbalar» ruxsati berilgan bo'lsa ham. Telefonda
«avtomatik bloklovchi tomonidan bloklandi» xabari chiqadi.

Yechimi:

1. Sozlamalar → **Xavfsizlik va maxfiylik** → **Avtomatik bloklovchi**
2. Asosiy tugmani o'chiring (yoki *«Ruxsatsiz manbalardan o'rnatishni
   bloklash»* bandini)
3. APK'ni o'rnatib bo'lgach, Auto Blocker'ni qayta yoqish mumkin —
   o'rnatilgan ilova o'chib ketmaydi

Diqqat: Auto Blocker **USB orqali o'rnatishni ham** to'sadi
(«USB kabel orqali zararli buyruqlarni bloklash»), ya'ni `adb install` ham
shu tugma o'chirilmaguncha ishlamaydi. Sabab topilmaganda birinchi navbatda
shuni tekshirish kerak.

Xodimlarga tarqatishda: Samsung telefonli xodimlar uchun bu qadam
ko'rsatmaga majburiy kiritilishi kerak.

### Fayl nomi — nuqta qo'ymang

APK nomida **faqat bitta nuqta** (kengaytma oldidagi) bo'lsin:

- ✅ `hodimlar-tizimi.apk`
- ❌ `hodimlar-tizimi-v1.0.0.apk`

Sabab: Telegram (va bir qancha fayl menejeri) MIME turini kengaytmadan
`MimeTypeMap.getFileExtensionFromUrl()` bilan aniqlaydi. Nomda bir nechta
nuqta bo'lsa kengaytma noto'g'ri o'qilishi va MIME `null` qaytishi mumkin —
u holda Android faylni Package Installer'ga bermay, umumiy `ACTION_VIEW`
bilan boshqa ilovaga uzatadi.

Versiyani nomga yozish kerak bo'lsa, nuqta o'rniga chiziqcha:
`hodimlar-tizimi-v1-0-1.apk`.

Tarix: 2026-07-30 da telefonda avval «AR uchun Google Play xizmatlari talab
qilinadi», keyin «avtomatik bloklovchi tomonidan bloklandi» xatolari chiqqan.
Haqiqiy sabab — Samsung Auto Blocker. Nom qoidasi va v1 imzo profilaktika
sifatida qoldirilgan (MIUI uchun v1 baribir kerak), lekin AR xatosining
sababi ekani isbotlanmagan.

### Telefonga o'rnatish

0. Samsung bo'lsa — yuqoridagi **Auto Blocker**ni o'chiring.
1. APK'ni Telegram orqali yuboring (Saved Messages ham bo'ladi).
2. Telefonda faylni bosib **Yuklab olish**, keyin **Ulashish → Fayllarga
   saqlash** bilan `Download` papkasiga tushiring.
3. Telefondagi **Files / Fayllar** ilovasi → `Download` → APK ustiga bosing.
4. "Open with" so'ralsa — **Package Installer / Paket o'rnatuvchi** tanlang.
5. "Noma'lum manbalar" so'ralsa — Files ilovasiga ruxsat bering.
6. Play Protect ogohlantirsa — **"Baribir o'rnatish"** (imzo bizniki,
   `CN=Hodimlar Tizimi, O=Nuriddin Building`).

Xato aniq bo'lmasa, USB orqali sababni ko'rish eng tez yo'l:

```
adb install -r hodimlar-tizimi.apk
```

### Tekshiruv (build'dan keyin)

```
"$ANDROID_HOME/build-tools/36.0.0/apksigner" verify --verbose --print-certs hodimlar-tizimi.apk
"$ANDROID_HOME/build-tools/36.0.0/aapt2" dump badging hodimlar-tizimi.apk
```

v1/v2/v3 uchtasi ham `true` bo'lishi va `minSdkVersion:'24'`,
`native-code: 'arm64-v8a' 'armeabi-v7a'` chiqishi kerak.

### Bosqich 6 uchun eslatma

Bu qo'lda tarqatish faqat ichki sinov uchun. Xodimlar soni ko'payganda
APK'ni loyiha veb-serveridan to'g'ri MIME turi
(`application/vnd.android.package-archive`) bilan berish kerak — u holda
Chrome to'g'ridan-to'g'ri o'rnatuvchini ochadi va yuqoridagi 6 qadam
kerak bo'lmaydi.

## 9. Keyingi qadam

Ushbu reja tasdiqlansa (yoki ochiq savollarga javob berilsa), **Bosqich 1**
dan boshlanadi: Expo loyihasini `mobile/` papkasida yaratish, asosiy
navigatsiya skeleton, va auth oqimini backend bilan birga loyihalash.

[[dev-environment]] [[attendance-feature]] [[frontend-overhaul]] [[deploy-setup]]
