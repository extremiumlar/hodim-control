# Chuqur tahlil metodikasi — AI agentni yuzaki yechimdan to'xtatish

> **Maqsad:** AI agent har bir muammoga ALOHIDA to'xtalsin, ildizigacha tushsin,
> va faqat shundan keyin yechim bersin. "Tez tuzatib qo'yish" refleksini to'sish.
>
> **Ishlatish:** 2-bo'limdagi promptni nusxalab agentga bering. Qolgan bo'limlar —
> nega shunday yozilgani va natijani qanday tekshirish.

---

## 1. Nega AI agent yuzaki yechim beradi

Muammoning ildizini bilmasdan qarshi chora ko'rish mumkin emas — shuning uchun
avval agentning "yuzakilik" sabablarini aniqlaymiz.

| # | Sabab | Qanday namoyon bo'ladi |
|---|---|---|
| 1 | **Naqsh bo'yicha moslash** | Muammoni ko'rgach, o'xshash holatlarning STANDART yechimini beradi: «sekinmi → kesh qo'sh», «xatomi → try/except», «timeout'mi → limitni oshir». Loyihaning O'ZINI o'rganmaydi. |
| 2 | **Birinchi mantiqiy izohda to'xtash** | Ishonarli tushuntirish topgach qidirishni to'xtatadi. Lekin ishonarli ≠ to'g'ri. |
| 3 | **Xato CHIQQAN joyni tuzatish** | Traceback qaysi qatorda bo'lsa, o'sha yerni tuzatadi — sabab esa 5 qavat pastda. |
| 4 | **Ko'p muammoni birga ishlash** | 10 ta muammo berilsa, har biriga 1/10 chuqurlik ajratadi. Natija — 10 ta yuzaki javob. |
| 5 | **Gipotezani tekshirmaslik** | Diagnoz qo'yadi, lekin uni RAD ETISHGA urinmaydi. Noto'g'ri diagnoz omon qoladi. |
| 6 | **Yordamchi bo'lishga shoshilish** | "Bilmayman" deyishdan qochadi, bo'shliqni taxmin bilan to'ldiradi. |

Quyidagi prompt shu 6 sababning **har biriga** alohida to'siq qo'yadi.

---

## 2. TAYYOR PROMPT (nusxalang)

```
Quyidagi muammolar ro'yxati bo'yicha ishlaysan. Lekin ishlash USULI qat'iy
belgilangan — undan chetga chiqish natijani yaroqsiz qiladi.

═══════════════════════════════════════════════════════════════
ASOSIY QOIDA: BIR VAQTDA BITTA MUAMMO
═══════════════════════════════════════════════════════════════

Muammolarni birga ishlama. Bittasini OXIRIGACHA yopmasdan keyingisiga o'tma.
Har bir muammo uchun quyidagi 9 bosqichni TO'LIQ bajarasan va alohida hisobot
yozasan. "Bu ikkalasi o'xshash, birga ko'rib chiqaman" — TAQIQLANADI.

Agar ro'yxatda 12 ta muammo bo'lsa — 12 ta alohida, to'liq hisobot bo'ladi.

═══════════════════════════════════════════════════════════════
HAR BIR MUAMMO UCHUN 9 BOSQICH
═══════════════════════════════════════════════════════════════

── BOSQICH 0: CHEGARALASH ──
- Muammoni BITTA jumlada ayt (simptom, sabab emas).
- Nima bu ishga KIRADI, nima KIRMAYDI — aniq chegara.
- "Bu hal bo'lsa, aynan NIMA o'zgaradi?" — kuzatiladigan natija.

── BOSQICH 1: DALIL YIG'ISH  [DARVOZA] ──
- Har bir da'vo uchun DALIL: `fayl:qator`, log parchasi, yoki jonli o'lchov.
- TAQIQ: "odatda shunday bo'ladi", "menimcha", "ehtimol" — dalil emas.
- Kodni O'QI. Taxmin qilma. Fayl ochilmasdan yozilgan da'vo yaroqsiz.
- Dalil topilmasa — "DALIL YO'Q" deb yoz. Bo'shliqni taxmin bilan to'ldirma.
- ⛔ CHIQISH SHARTI: kamida 3 ta mustaqil dalil. Yetmasa — qidirishda davom et.

── BOSQICH 2: TAKRORLASH VA O'LCHASH  [DARVOZA] ──
- Muammoni qanday KO'RSATISH mumkin? Aniq buyruq yoki qadamlar ketma-ketligi.
- HOZIRGI raqamni o'lcha va yozib qo'y ("avval" qiymati).
  Masalan: "6 ta parallel so'rov: 2.7s, 3.0s, 3.5s, 4.0s, 4.5s, 5.0s".
- Takrorlab bo'lmasa — NEGA bo'lmasligini yoz. Bu ham natija.
- ⛔ CHIQISH SHARTI: raqam bor. "Sekin" — raqam emas. "3.4 soniya" — raqam.

── BOSQICH 3: SABAB ZANJIRI  [DARVOZA] ──
- Simptomdan boshlab "NEGA?" deb pastga tush. Har bosqichda dalil bo'lsin.
- Format:
      Simptom: <...>
        ↓ nega? <javob>  [dalil: fayl:qator]
        ↓ nega? <javob>  [dalil: ...]
        ↓ nega? <javob>  [dalil: ...]
      ILDIZ: <...>
- TO'XTASH SHARTI — faqat shu ikkitasidan biriga yetganda to'xta:
      (a) ONGLI LOYIHAVIY QAROR (kimdir shunday tanlagan), yoki
      (b) TASHQI CHEKLOV (hosting, kutubxona, protokol imkoniyati)
- ⛔ Simptom darajasida to'xtash TAQIQLANADI.
  "Sekin ishlayapti chunki so'rov ko'p" — bu ILDIZ EMAS, bu qayta aytilgan simptom.
  "So'rov ko'p, chunki halqa ichida chaqirilyapti, chunki bulk API yo'q edi,
   chunki adapter bitta-bitta ishlash uchun yozilgan" — MANA bu ildiz.
- ⛔ CHIQISH SHARTI: zanjir kamida 3 bo'g'in. 1-2 bo'g'in = yuzaki.

── BOSQICH 4: DIAGNOZNI RAD ETISHGA URINISH  [DARVOZA] ──
- Savol: "Agar mening diagnozim NOTO'G'RI bo'lsa, men nimani ko'rgan bo'lardim?"
- O'sha tekshiruvni HAQIQATAN bajar.
- Diagnozga QARSHI dalil qidirib ko'r — tasdiqlovchi emas.
- Diagnoz omon qolmasa → 3-BOSQICHGA QAYT. Bu muvaffaqiyatsizlik emas, ish.
- ⛔ CHIQISH SHARTI: "Diagnozni rad etishga urindim, natija: ___" deb yozilgan.

── BOSQICH 5: KAMIDA 3 TA YECHIM VARIANTI ──
- Har biri uchun: qanday ishlaydi | nimani YO'Q QILADI | narxi | xavfi |
  qanday sharoitda BUZILADI.
- MAJBURIY: bittasi eng minimal (yoki "hech narsa qilmaslik") bo'lsin.
- MAJBURIY: bittasi ildizni BUTUNLAY yo'q qiladigan bo'lsin (qimmat bo'lsa ham).
- ⛔ Bitta variant taklif qilish = yuzaki.

── BOSQICH 6: TANLOV VA OQIBAT ──
- Qaysi variant va NEGA aynan u.
- Rad etilganlar NEGA rad etildi (har biri uchun bir jumla).
- ⛔ MAJBURIY SAVOL: "Bu yechim qanday YANGI muammo tug'diradi?"
  "Hech qanday" javobi deyarli har doim yolg'on — yana o'yla.
  Ta'sir doirasini tekshir: bu o'zgarish yana qayerlarga tegadi?

── BOSQICH 7: ANIQ QADAMLAR ──
- Fayl-fayl, funksiya-funksiya. Mavhum emas.
  ❌ "Optimallashtirish kerak"
  ✅ "api/services/export.py:277 — wb.save(buffer) ni
      await asyncio.to_thread(wb.save, buffer) ga almashtirish"
- Har qadamdan keyin: qanday TEKSHIRILADI.
- Rollback: buzilsa qanday qaytariladi.

── BOSQICH 8: TUGALLANGANLIK MEZONI ──
- O'lchanadigan bo'lsin: "avval X → keyin Y" (2-bosqichdagi raqam bilan).
  ❌ "yaxshiroq ishlaydi"   ✅ "6 parallel so'rov: 5.0s → 0.9s"
- Qanday regressiya sinovi kerak.

── BOSQICH 9: YUZAKILIK O'Z-O'ZINI TEKSHIRUVI ──
Hisobotni topshirishdan oldin quyidagilarni O'ZING tekshir va javobini yoz.
Bittasiga ham "ha" bo'lsa — ORQAGA QAYT, hisobot tayyor emas:

  [ ] Yechim xato CHIQQAN joyni tuzatyaptimi (KELIB CHIQQAN joyni emas)?
  [ ] try/except, if None, yoki default qiymat bilan simptom KO'MILDIMI?
  [ ] Timeout/retry/limit sababni o'rganmasdan OSHIRILDIMI?
  [ ] Kesh qo'shildimi — lekin nega sekin ekani aniqlanmadimi?
  [ ] Sabab zanjiri 3 bo'g'indan QISQAMI?
  [ ] Biror da'vo `fayl:qator` yoki o'lchovsiz qoldimi?
  [ ] Faqat bitta yechim variantimi?
  [ ] "Yangi muammo tug'dirmaydi" deb yozildimi?
  [ ] Tugallanganlik mezoni o'lchanmaydiganmi?
  [ ] Kodni ochib o'qimasdan, nomiga qarab xulosa qilindimi?

═══════════════════════════════════════════════════════════════
XULQ-ATVOR QOIDALARI
═══════════════════════════════════════════════════════════════

1. KOD YOZMA. 7-bosqichgacha hech qanday tuzatish qilinmaydi — faqat tahlil.
   Tuzatishni men alohida buyuraman.

2. "BILMAYMAN" — TO'G'RI JAVOB. Taxmin — noto'g'ri javob.
   Aniqlash uchun mendan ma'lumot kerak bo'lsa — SO'RA, o'ylab topma.

3. ISHONCH DARAJASINI AYT. Har bir xulosa yoniga:
   [TASDIQLANGAN] — dalil bor
   [EHTIMOLIY]    — mantiqiy, lekin tekshirilmagan
   [TAXMIN]       — dalil yo'q
   Hisobotda [TAXMIN] ko'p bo'lsa — ish tugamagan.

4. QISQARTIRMA. "Vaqtni tejash uchun qisqacha aytaman" — kerak emas.
   Chuqurlik > qisqalik. Uzun hisobot yaxshi hisobot.

5. TARTIB. Muammolarni men bergan tartibda ishla. O'zgartirish kerak deb
   hisoblasang — avval sabab bilan ayt va tasdiqlashimni kut.

═══════════════════════════════════════════════════════════════
HISOBOT SHAKLI
═══════════════════════════════════════════════════════════════

Har bir muammo uchun ALOHIDA, quyidagi sarlavhalar bilan:

  # <raqam>. <muammo nomi>
  ## 0. Chegara
  ## 1. Dalillar
  ## 2. Takrorlash va "avval" o'lchovi
  ## 3. Sabab zanjiri
  ## 4. Rad etishga urinish
  ## 5. Yechim variantlari (3+)
  ## 6. Tanlov, asos va oqibatlar
  ## 7. Qadamlar
  ## 8. Tugallanganlik mezoni
  ## 9. Yuzakilik tekshiruvi

Boshla. Birinchi muammo: <shu yerga muammoni yoz>
```

---

## 3. Har bir mexanizm nega ishlaydi

| Mexanizm | Qaysi sababni to'sadi (1-bo'lim) | Qanday to'sadi |
|---|---|---|
| **Bir vaqtda bitta muammo** | 4 — ko'pni birga ishlash | Chuqurlikni bo'lib yuborishga imkon qoldirmaydi |
| **Darvozalar (chiqish sharti)** | 2 — birinchi izohda to'xtash | Shart bajarilmasa keyingi bosqichga o'tolmaydi |
| **`fayl:qator` majburiyati** | 1 — naqsh bo'yicha moslash | Umumiy bilim yetmaydi, loyihani O'QISHGA majbur qiladi |
| **Sabab zanjiri ≥3 bo'g'in** | 3 — xato chiqqan joyni tuzatish | Yuzaga chiqqan joydan pastga tushishga majbur qiladi |
| **Rad etishga urinish** | 5 — gipotezani tekshirmaslik | Tasdiqlash tarafkashligini (confirmation bias) sindiradi |
| **3+ variant majburiyati** | 1 — standart yechim refleksi | Birinchi kelgan fikr bilan cheklanishga yo'l qo'ymaydi |
| **"Yangi muammo nima?"** | 2 — yuzaki qoniqish | Yechimning ta'sir doirasini o'ylashga majbur qiladi |
| **"Bilmayman" ruxsati** | 6 — yordamchi bo'lishga shoshilish | Taxminni to'ldirish ehtiyojini olib tashlaydi |
| **Ishonch belgilari** | 6 — taxminni fakt sifatida berish | Tekshirilmaganni yashirib bo'lmaydi |
| **9-bosqich o'z-tekshiruvi** | Hammasi | Topshirishdan oldingi oxirgi filtr |
| **"Kod yozma"** | 1, 2 — tuzatishga shoshilish | Tahlil va tuzatishni ajratadi — aralashsa tahlil yutqazadi |

### Eng muhim uchtasi

Agar promptni qisqartirish kerak bo'lsa, **shu uchtasi qolsin**:

1. **Sabab zanjiri ≥3 bo'g'in, har biri dalil bilan** — yuzakilikka qarshi eng
   kuchli qurol. Yuzaki javob bu shartni jismonan bajara olmaydi.
2. **"Diagnozimni rad etishga urinaman"** — noto'g'ri, lekin ishonarli
   diagnozlarni ushlaydi.
3. **Bir vaqtda bitta muammo** — qolgan hammasi shunga tayanadi.

---

## 4. Natijani qanday tekshirasiz

Agent hisobot berdi. Chuqurmi yoki yuzakimi — 60 soniyada aniqlash:

### 🔴 Yuzaki hisobot belgilari

- Sabab zanjiri 1-2 bo'g'in yoki umuman yo'q
- Da'volarda `fayl:qator` yo'q
- "avval" o'lchovi yo'q, faqat sifat ta'rifi ("sekin", "og'ir")
- Bitta yechim varianti
- "Bu yangi muammo tug'dirmaydi"
- Tugallanganlik mezoni o'lchanmaydigan
- 4-bosqich (rad etish) bo'sh yoki formal
- Bir nechta muammo bitta bo'limda birlashtirilgan

### 🟢 Chuqur hisobot belgilari

- Zanjir loyihaviy QARORGA yoki tashqi cheklovga borib taqaladi
- Agent o'z diagnozining bir qismini rad etgan va qayta ishlagan
- "Bu joyni tekshirdim, dalil topilmadi" degan halol yozuvlar bor
- Rad etilgan variantlar sababi bilan ko'rsatilgan
- Yechimning yangi xavfi ochiq aytilgan
- Kamida bitta savol sizga qaytarilgan

### Qaytarish uchun tayyor iboralar

Yuzaki javob kelsa, quyidagilardan birini yuboring:

> «3-bosqich yetarli emas — sabab zanjiring 2 bo'g'in. Loyihaviy qarorga yoki
> tashqi cheklovga yetguningcha "nega?" deb davom et.»

> «Bu da'voda dalil yo'q. Qaysi fayl, qaysi qator? Ochib o'qib, tasdiqla.»

> «4-bosqichni bajarmagansan. Diagnozing NOTO'G'RI bo'lsa nimani ko'rarding —
> o'shani tekshir.»

> «Bitta variant berding. Yana ikkitasi qani — biri minimal, biri ildizni
> butunlay yo'q qiladigan?»

> «"Yangi muammo tug'dirmaydi" — bu deyarli har doim noto'g'ri. Bu o'zgarish
> yana qaysi joylarga tegadi?»

---

## 5. Qo'shimcha kuchaytirish usullari

Muammo ayniqsa muhim bo'lsa, promptga shularni qo'shing:

**a) Ikki bosqichli tekshiruv**
> «Hisobotni tugatgach, uni BOSHQA ko'z bilan qayta o'qi: sen bu tahlilni
> rad etishga harakat qilayotgan skeptik mutaxassissan. Eng zaif joyi qayerda?»

**b) Muqobil ildiz talabi**
> «Ildizni topgach, "agar ildiz bu BO'LMASA, yana nima bo'lishi mumkin edi?"
> degan savolga kamida 2 ta javob ber va ularni nega rad etganingni ayt.»

**c) Tarix so'rash**
> «Bu kod NEGA shunday yozilgan? git log / izohlarda sabab bormi? Ilgari
> boshqacha bo'lganmi va nega o'zgartirilgan?»
> — Ko'p "xato" aslida ongli qaror bo'lib chiqadi. Bu savol ularni ochadi.

**d) Narx-foyda majburiyati**
> «Yechimning bajarilish vaqtini va olib keladigan foydasini raqamda ayt.
> Foyda mehnatdan kam bo'lsa — buni ochiq yoz va "qilmaslik"ni tavsiya qil.»

---

## 6. Nima QILMASLIK kerak

| Xato | Nega yomon |
|---|---|
| Promptga "chuqur o'yla", "diqqat bilan" kabi umumiy so'zlarni qo'shish | O'lchanmaydi, tekshirilmaydi — ta'siri deyarli yo'q. Aniq DARVOZA qo'ying. |
| Bir marta prompt berib, natijani tekshirmaslik | Metodikaning yarmi — sizning qaytarishingiz (4-bo'lim) |
| Hamma muammoni bitta so'rovda berish | Agent baribir bo'lib yuboradi. Bittadan bering. |
| Tahlil va tuzatishni aralashtirib yuborish | Tuzatish boshlangach tahlil chuqurligi yo'qoladi |
| Juda uzun prompt (5+ sahifa) | Muhim qoidalar ko'milib ketadi. Eng muhim 3 tasini tepaga qo'ying. |

---

*Hujjat 2026-08-07. Amaliy manba: shu loyihadagi «sayt qotishi» tekshiruvi —
`SAYT_QOTISHI_TAHLIL.md`. O'sha tahlilda 1-6 bosqichlar aynan shu usulda
bajarilgan (jonli zinapoya testi = 2-bosqich, a2wsgi manbasini o'qish = 1-bosqich,
LVE limitlarini tekshirish = 4-bosqich).*
