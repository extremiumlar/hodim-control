# DAVOMAT UX 2-TUR — uch yuza (web · mobil ilova · telegram bot) bo'ylab yaxshilash

Manba: 2026-08-06 dagi uch tomonlama audit (web tanqidiy, mobil ilova, bot).
Asosiy xulosa: 1-tur yangilanish STRUKTURANI to'g'riladi (tablar, matritsa,
kalendar), lekin AMALLAR ZANJIRINI yaratmadi — ekranlar ma'lumot ko'rsatadi,
ammo ko'rilgan muammoni o'sha yerdan hal qilib bo'lmaydi; rahbar quroli
(matritsa) telefonda ishlamaydi; bot xodim uchun davomatda deyarli bo'sh
(faqat xabar oladi, harakat qila olmaydi); mobil ilova push'i davomatga
ulanmagan.

Anti-maqsadlar (o'zgarmasin): mavjud endpointlar buzilmasin (faqat qo'shimcha),
check-in xavfsizlik oqimi (Face ID + GPS tekshiruv mantiqiy) o'zgarmasin,
bot/main.py ga TEGILMASIN (parallel sessiya ishlayapti), backend push path
o'zgarmasin (eski APK buzilmasin).

---

## W1 — Web tezkor yutuqlar (Bugun tabi = harakat markazi)

1. **A3 Kelmagan soni zid**: TodayTab karta sarlavhasi `Kelmagan ({not_come.length})`
   bo'lsin; sababli kunlar alohida "🌿 Sababli ({excused_today.length})" bo'limchaga.
2. **A4 Kechikdi ro'yxati**: yangi karta "⏱ Kechikdi (N)" — in_office+left
   ichidan late_minutes>0 filtrlab, kechikish bo'yicha kamayish tartibida,
   `+N daq` qizil chip bilan.
3. **A5 Sababli tugmasi**: har "Kelmagan" qatoriga "Sababli" tugma → kichik
   dialog (faqat sabab so'raydi; xodim/sana ma'lum) → POST /excused-days/for-user.
   Muvaffaqiyatda dashboard invalidatsiya.
4. **A12 Hammaga eslatish**: karta sarlavhasida "Hammaga eslatish (N)" —
   bot ulanganlarga ketma-ket remind, yakunda BITTA toast ("6 yuborildi,
   2 yetkazilmadi"). 429/400 larni sanab ko'rsatish.
5. **B17 user_id**: dashboard in_office/left/recent yozuvlariga user_id qo'shish
   (backend) → barcha ismlar EmployeeDrawer/profilga bosiladigan.
6. **A2 Tab satri**: TabsList'ga to'liq kenglik + overflow-x-auto (Attendance
   va WorkSchedule).
7. **A10 LiveClock**: soatni alohida komponentga — sahifa har soniya qayta
   chizilmasin.
8. **B4 Hisobot skeleti**: yuklanayotganda "0 daq" o'rniga Skeleton.
9. **A13 Ofislar qatori**: tugmalar flex-wrap + "O'chirib qo'yish"→"Vaqtincha
   o'chirish"; telefonda chiqib ketmasin.

Qabul mezoni: telefon (375px) da Bugun tabidan turib kelmagan xodimga 2 bosishda
sababli kun beriladi, 1 bosishda hammaga eslatiladi, kechikkanlar ismma-ism
ko'rinadi, hech qanday gorizontal skroll yo'q.

## W2 — Web mobil moslashuvi (rahbar teleofondan kiradi)

1. **A1 Matritsa mobil ko'rinishi**: `md:` dan kichikda jadval o'rniga xodim
   kartalari (ism + oy xulosasi "21 keldi · 3 kechikdi · 1 yo'q" + bosilsa
   EmployeeDrawer — unda MonthCalendar allaqachon 360px ga sig'adi).
2. **M1 Avto-scroll**: desktop matritsada joriy oyda bugungi ustun ko'rinishga
   avtomatik aylantirilsin.
3. **A9 CheckIn tartibi**: faol amal (Keldim YOKI Ketdim) to'liq kenglikda h-16
   tepada; ikkinchisi kichik; MyHistoryCard akkordeonga; yuzsiz xodimga asosiy
   tugma "Yuzni ro'yxatdan o'tkazish" (B16).
4. **B15 SuccessScreen**: Dialog'ga o'tkazish + 4s avtoyopilish.
5. **B11 ScheduleOverviewTab mobil**: kichik ekranda xodim-kartalar ko'rinishi.
6. **B1/B18**: eng muhim title'lar → ko'rinadigan matn/Tooltip; legend telefonda
   ixcham (popover yoki bir qator qisqartma).
7. **B2**: legendga kehrabo uchburchak izohi; MonthCalendar kataklariga glif.

## W3 — Kontekst zanjirlari (ko'rgan joyingda hal qil)

1. **A6 Katak dialogi ko'p amal**: absent→[Sababli qilish][Tuzatish][Eslatish];
   late→[Tuzatish]; future/weekend kataklar bosilmaydigan.
2. **A15 EmployeeDrawer amallari**: pastda [Kun tuzatish][Sababli kun][Jadvali]
   [Profil]; oy almashganda drawer ma'lumoti yangilanadi.
3. **A7 Tayyorlik banneri**: "13 muammo" o'rniga toifalab ("3 xodimda jadval
   yo'q · 6 kun yopilmagan"); chiplar bosiladigan → hal qilish yo'li
   (jadval yo'q → /work-schedule?user=ID&tab=bitta; yopilmagan kun →
   EditAttendanceDialog preset).
4. **A14 WorkSchedule deep-link**: ?tab=umumiy|bitta&user=ID qo'llab-quvvatlash;
   window.confirm → ConfirmDialog.
5. **A8 URL holati**: matritsa oyi ?month= da; tab almashganda boshqa paramlar
   saqlanadi; Hisobot davri ?davr= da.
6. **A11 Matritsa filtri**: ism qidiruv + "faqat muammoli" chekboks + jami
   ustunlarini bosib saralash.
7. **B10**: EditPreset'ga jadval vaqti — dialog tepasida "Bu kun jadvali:
   10:00–19:00" + kiritilgan vaqtdan jonli kechikish hisobi.
8. **B9**: sabab tez-tanlash chiplari ("Face ID ishlamadi", "Bosishni unutgan",
   "Ofisdan tashqarida ish") — EditAttendanceDialog va Sababli dialogda.

## W4 — Telegram bot (xodimga davomat OCHILADI)

1. **C1 Keldim/Ketdim tugmasi**: xodim (va davomati kuzatiladigan barcha rol)
   menyusiga «✅ Keldim / Ketdim» — bosilganda inline URL tugma bilan
   FRONTEND_URL/check-in havolasi (WebApp emas, oddiy URL — mobil ilovada
   ham ochiladi).
2. **C2 Eslatmalarga tugma**: barcha keldim/ketdim/rahbar-eslatma xabarlariga
   inline URL tugma («✅ Keldim qilish»); force_telegram=True (C7).
3. **C3 FSM himoyasi**: keyboards.py'da ALL_MENU_BUTTONS frozenset; excused.py
   dagi 5 catch-all state handleriga ~F.text.in_(ALL_MENU_BUTTONS) filtri —
   menyu tugmasi sabab sifatida ketib qolmasin.
4. **C4 Kecha tugmasi**: sababli kun sana tanlashda [Kecha][Bugun][Ertaga] +
   birinchi qadamda cancel_menu.
5. **C5 Bugungi holat**: «🕐 Davomat statistikasi»ga [👥 Bugungi holat] inline
   tab (dashboard'dan: keldi/kechikdi/kelmadi/sababli ismlar bilan); menyu
   tugmasi nomi «🕐 Davomat».
6. **C6 Eslatish matni**: aktyor ismi bilan, sched_start None himoyasi,
   ayblovsiz ohang, 2 inline tugma (Keldim qilish / Sababli kun so'rash).
7. **C9 Statistikam bloki**: xodim «📈 Statistikam»da bu oy kechikish daq /
   kelgan / kelmagan kunlar.
8. **C10 Validatsiya**: sabab min 3 belgi (bot + api schema); sana ±60 kun
   oralig'ida.
9. **C11 Qaror xabari**: sabab + kim qaror qilgani + rad etilganda "qayta
   so'rash mumkin".
10. **C12 Digest matni**: "18:00 da o'tmadi demak u officeda" → to'g'ri o'zbekcha.
11. **C8 set_my_commands**: rolga qarab "/" menyusi (kamida rahbarga
    /davomat_vaqt, /guruhlar).

## W5 — Mobil ilova (yangi APK talab qiladi — oxirgi bosqich)

1. **MC1 Push yo'nalishi**: push.ts'da "/check-in" → nativ /checkin;
   rahbar yo'llari (/statistics, /excused-days, /payroll) ALLOWED_WEB_PATHS'ga.
2. **MC2 FCM kanali**: CHANNELS'ga attendance_reminder.
3. **MC4 Xato ekrani**: EmbeddedWeb onError/onHttpError → o'zbekcha xabar +
   "Qayta urinish"; 15s timeout.
4. **MC5 Sessiya**: onNavigationStateChange /login ko'rsa → nativ login.
5. **MC6 Embed chekka**: App.tsx embed marshrutini px-4 py-4 bilan o'rash
   (web tomonda — APK'siz ham jonli bo'ladi).
6. **MC3 Model prefetch**: CheckIn mount'da idle paytda FaceCapture import +
   loadModels (web tomonda — APK'siz jonli).
7. **MC7 O'zbekcha tarmoq xatosi**: client.ts fetch → ApiError(0, o'zbekcha)
   (web tomonda).
8. **MC8**: "CDN"/"4.4 MB" eskirgan matnlarni tuzatish; nginx /models/ kesh.

## W6 — Sayqal

1. **B5 QueryError**: yagona xato komponenti (matn + Qayta urinish) — barcha
   davomat query'lariga; TodayTab null→skeleton; ReadinessSection xatoni
   yashirmasin.
2. **B6 Bo'sh holatlar**: harakatga undovchi (nima qilish kerakligi bilan).
3. **B7 Yangilanish belgisi**: Bugun tabida "🔄 HH:MM da yangilandi" + qo'lda
   refresh.
4. **B14 SettingsTab havolalari**: Ofislar / jarima sozlamalari / ish jadvaliga
   yo'naltirish kartalari.
5. **B3**: matritsa ustun sarlavhalari tushunarli ("Kech (marta/daq)").
6. **M2**: TodayTab ism trim ("Albina·" emas "Albina ·").
7. **B12**: MarkExcusedForm xodim tanlash qidiruvli bo'lsin.

Har to'lqin: kod + test (test.py yangi tekshiruvlar, jonli ma'lumotga tegmasdan
T- prefiks bilan) + brauzer vizual tekshiruv + alohida commit.
