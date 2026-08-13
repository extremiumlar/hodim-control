# Uysot webhook — muammo va yechim (HAL BO'LDI)

> **Holat:** ✅ **ISHLAYAPTI** (2026-08-12, 15:47)
> **Tasdiq:** webhook 10:47:23.801 UTC da keldi → voqea 10:47:23.807 da bazaga
> yozildi (**6 ms**). Polling bilan bu 3 daqiqagacha kutardi.

---

## 1. Yakuniy holat

| Bosqich | Holat |
|---|---|
| Uysot yuboradi | ✅ |
| Server qabul qiladi | ✅ `QABUL` |
| Autentifikatsiya | ✅ ishonchli IP + imzo mavjudligi |
| Parse | ✅ `parsed=1` |
| Bazaga qo'llash | ✅ `stage_change=1` |
| Kechikish | ✅ **6 ms** (polling: 3 daqiqagacha) |

**Ishlayotgan sozlama (Uysot kabineti):**
```
Sozlamalar → Integratsiya → «Dasturchi oynasini ochish»
  → «Ulanishlar» → «Xodimlar tizimi» → «Webhook» tabi

Webhookni yoqish : YOQIQ
Webhook URL      : https://nuriddin-building.uz/api/crm-webhook/uysot
Webhook maxfiy kaliti : (Uysot generatsiya qilgan, 64 hex)
Voqealar         : Lid yaratildi · Lid biriktirildi · Lid bosqichi o'zgardi
```

---

## 2. Muammoning TO'RT qatlami

Bu bitta xato emas edi — to'rtta mustaqil to'siq, har biri alohida butun
tizimni ishlamas holga keltirardi. Shuning uchun ularni birin-ketin ochish
kerak bo'ldi.

### 2.1. «Webhookni yoqish» toggle'i O'CHIQ edi
URL va kalit to'g'ri kiritilgan, lekin toggle yoqilmagan → Uysot **umuman
yubormasdi**. Bu «bizda hech qanday so'rov yo'q» degan barcha o'lchovlarni
tushuntiradi.

### 2.2. URL'da `?secret=...` ishlatilardi
Bizning format `.../uysot?secret=<SEKRET>` edi. Uysot esa **query parametr
yubormaydi** (webhook.site namunasi: «Query strings: None»). Sekret hech
qachon yetib kelmasdi.

Uysot autentifikatsiyani **imzo** bilan qiladi:
```
x-webhook-signature: sha256=<64 hex>
x-webhook-timestamp: <unix>
x-webhook-id:        <uuid>
```

### 2.3. Rad etilgan so'rovlar HECH QAYERGA yozilmasdi ⭐
**Eng qiyin qatlam.** Uchala iz qoldirish yo'li ham buzuq edi:

| Manba | Nega ishlamasdi |
|---|---|
| Baza (`crm_webhook_log`) | `_verify_secret` 401 ni **log yozishdan oldin** otardi |
| `logger.warning` | `api/main.py`da logging **sozlanmagan** → stderr → Passenger yo'qotadi |
| Apache access log | Kechikadi/ishonchsiz (o'lchandi: 200 qaytargan so'rov 1 daqiqadan keyin ham yo'q edi) |

Natijada «Uysot yubormayaptimi yoki yuboryapti-yu rad etilyaptimi» degan
savolga javob topib bo'lmasdi.

> **Bu qatlam hal qilinmaganda 2.4 ni topib bo'lmasdi.** Diagnostika
> imkoniyatining o'zi — mustaqil muammo edi.

### 2.4. Proksi IPv4-mapped IPv6 beradi
Ishonchli IP mezoni qo'shilgandan keyin ham rad etilardi. Sabab:
```
x-real-ip: ::ffff:158.179.201.167
```
Ro'yxatdagi `158.179.201.167` bilan `::ffff:158.179.201.167` **hech qachon**
mos kelmasdi.

---

## 3. Kiritilgan tuzatishlar

| Commit | Nima |
|---|---|
| `4e76a43` | Rad etilgan so'rovlar ham jurnalga (avval yoz → keyin tekshir) + `logs/api.log` fayl-logging |
| `fffe356` | Parserga Uysot'ning haqiqiy `statusName` maydoni |
| `bf576cd` | Ishonchli IP + imzo mezoni; `_proxy_verified_ip` (soxtalashtirishga qarshi) |
| `5436f71` | `_normalize_ip` — `::ffff:` prefiksi; `x-real-ip`/`x-forwarded-for` jurnalga |

### Xavfsizlik: soxtalashtirishga qarshi
Ishonch qarori uchun `_remote_ip` **yaramaydi** — u `x-forwarded-for`ning
BIRINCHI elementini oladi, uni esa mijozning o'zi yuborishi mumkin. Proksi
haqiqiy IP'ni oxiriga qo'shadi, shuning uchun `_proxy_verified_ip` avval
`x-real-ip`, bo'lmasa XFF ning **oxirgi** elementini oladi.

Jonli sinov:
```
imzosiz                      -> 401
soxta X-Forwarded-For + imzo -> 401   (to'sildi)
soxta X-Real-IP + imzo       -> 401   (to'sildi)
haqiqiy Uysot so'rovi        -> 200   QABUL
```

---

## 4. Uysot payload formati (namuna)

```json
{"lead": {
  "id": 12276261,
  "name": "+998772920092",
  "phone": "+998772920092",
  "pipeId": 839,
  "pipeName": "Pipeline",
  "statusId": 7136,
  "statusName": "Ro'yxatdan o'tgan mijozlar",
  "attributions": [{"source": "WEBSITE", "channelId": 1591}]
}, "eventType": "LEAD_CREATED", "occurredAt": 1786460450}
```

Yuboruvchi: IP `158.179.201.167` (Shvetsiya), UA `ReactorNetty/1.0.26`.

Parser (`api/services/uysot_webhook.py`) shu formatni to'liq tushunadi:
`id` → `lead_id`, `statusId` → `pipe_status_id`, `statusName` → `stage_name`.

---

## 5. Qolgan ish: to'liq HMAC tekshiruvi

Hozir imzo **mavjudligi** tekshiriladi, qiymati **qayta hisoblanmaydi** —
chunki Uysot imzo qaysi qatordan hisoblanishini hujjatlashtirmagan.

To'g'ri kalit bilan **1536 kombinatsiya** sinaldi va mos kelmadi:
HMAC-SHA256/SHA1/SHA512/MD5 × 8 xabar tuzilishi (`body`, `ts+body`,
`ts.body`, `id+ts+body`, ...) × 8 ajratuvchi × kalitning matn/hex
ko'rinishlari × hex/base64 chiqish.

**Uysot'ga yuboriladigan savol:**

```
Assalomu alaykum!

Kompaniya: Nurli Diyor
Ulanish: «Xodimlar tizimi» (Kirish tokeni)

Webhook muvaffaqiyatli ishlayapti, rahmat. Bitta texnik savol bor:

x-webhook-signature (sha256=<hex>) imzosi AYNAN QAYSI qatordan
hisoblanadi? Bizga quyidagilar kerak:
  1. Imzolanadigan xabar tuzilishi (masalan: timestamp + "." + body,
     yoki faqat body, yoki webhook-id ham qo'shiladimi?)
  2. Kalit qanday ishlatiladi — matn sifatidami yoki hex baytlar sifatida?
  3. Natija hex yoki base64?

Bizda imzo qiymati saqlanadi, shuning uchun javobingizdan keyin uni
darhol tekshirib ko'ra olamiz.

Hurmat bilan.
```

Javob kelgach: eski yozuvlarda algoritm tekshiriladi → haqiqiy HMAC yoziladi
→ IP mezoni olib tashlanishi mumkin (`CRM_WEBHOOK_TRUSTED_IPS`).

---

## 6. Saboqlar

1. **Diagnostika imkoniyati — mustaqil xususiyat.** Rad etilgan so'rovlar
   yozilmagani uchun asl muammo (2.4) ko'rinmasdi. «Nega ishlamayapti»ga
   javob berish uchun avval «ko'ra olish»ni tuzatish kerak edi.
2. **Bir necha marta noto'g'ri xulosa chiqardim.** «Uysot hech qachon
   yubormagan» degan da'vom asossiz edi — access log ishonchsiz ekan, va
   01.08 dagi «Uysot ping'i» aslida bizning ofis IP'imizdan bo'lgan test edi.
   Egasi «boshqa product ishlayapti» deb turib olgani muhim burilish bo'ldi.
3. **Egasining kuzatuvi dalildan ustun keldi.** Ma'lumot «kelmayapti» degan
   uchta mustaqil o'lchovim bor edi — lekin ularning hammasi bitta ko'r
   nuqtadan azob chekardi.

---

*Hujjat 2026-08-08 da muammo sifatida boshlangan, 2026-08-12 da yechim bilan
yakunlangan. Bog'liq: [TAHLIL_TOPSHIRIQLARI.md](TAHLIL_TOPSHIRIQLARI.md)
bo'lim 2.3.*
