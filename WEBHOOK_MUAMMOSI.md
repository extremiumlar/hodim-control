# Uysot webhook ishlamayapti — dalillar va Uysot'ga xat

> **Sana:** 2026-08-08 · **Holat:** bizning tomon sog'lom, Uysot yubormayapti
> **Ta'sir:** kritik EMAS — polling zaxira sifatida ishlab turibdi, ma'lumot yo'qolmayapti

---

## 1. Qisqa xulosa

Uysot kabinetida webhook sozlangandan keyin ham `https://nuriddin-building.uz`
serveriga **birorta ham webhook so'rovi kelmadi** — hatto shu vaqt oralig'ida
CRM'da o'nlab lid o'zgargan bo'lsa ham.

Bizning qabul qiluvchi endpoint **to'liq ishlayapti** (quyida sinov natijalari).
Muammo Uysot tomonida.

---

## 2. Sozlash joyi (topilgan yo'l)

```
Sozlamalar → Integratsiya → «Dasturchi oynasini ochish»
  → «Ulanishlar» oynasi → «Kirish tokeni» tabi
  → «Xodimlar tizimi» qatorini bosish
  → «Ulanish tafsilotlari» → «Webhook» tabi
```

Shu tabda: `Webhookni yoqish` (toggle) · `Webhook URL` · `Voqealar` (6 ta)

**Muhim:** 04.08.2026 16:43 da «Xodimlar tizimi» tokeni **qayta yaratilganda**
webhook sozlamalari ko'chirilmagan — toggle o'chiq, URL bo'sh, voqealar
tanlanmagan holatda qolgan.

---

## 3. Bizning tomon sog'lom — sinov natijalari

**Endpoint:** `POST https://nuriddin-building.uz/api/crm-webhook/uysot?secret=<SEKRET>`

| Sinov | Natija |
|---|---|
| `GET` + to'g'ri sekret | **HTTP 200** |
| `POST` + to'g'ri sekret | **HTTP 200** |
| `POST` sekretsiz | **HTTP 401** (to'g'ri rad etadi) |

Endpoint sekretni bir necha kanaldan qabul qiladi: `?secret=` query,
`X-Crm-Webhook-Secret` va shunga o'xshash headerlar, `Authorization: Bearer`.

> ### ⚠️ TUZATISH (11.08.2026): «Uysot ping yubordi» degan da'vo XATO edi
>
> Hujjat dastlab 01.08 dagi `{"ping":true}` (IP `84.54.71.13`) ni **Uysot'niki**
> deb yozgan va undan «ulanish yo'li ishlaydi» degan xulosa chiqargan edi.
>
> Loglarni chuqurroq tekshirganda ma'lum bo'ldiki, `84.54.71.*` — bu **bizning
> ofis/lokal tarmog'imiz**: o'sha IP'lardan `python-httpx` bilan
> `/api/daily-results/sync`, `/api/anketa/tick`, `/api/hot-lead/tick` kabi
> **bizning cron chaqiruvlarimiz** kelgan (eski deploy davrida scheduler
> ofisda ishlagan).
>
> Ya'ni o'sha ping ham **qo'lda yuborilgan test** bo'lgan.
>
> **Yangi, kuchliroq xulosa:** Uysot bizga **hech qachon, bironta ham** so'rov
> yubormagan. Iyul-avgust arxivlari to'liq tekshirildi.

---

## 4. Uysot'dan hech narsa kelmagani — uch mustaqil dalil

### 4.1. Ilova jurnali (`crm_webhook_log`)

Jami **4 ta** yozuv, **hammasi test**:

| # | Vaqt (UTC) | IP | Payload | Izoh |
|---|---|---|---|---|
| 1 | 01.08 11:14 | 84.54.71.13 | `{"ping":true}` | Uysot test ping'i |
| 2 | 04.08 09:55 | 167.235.222.200 | `{"diagnostika":...}` | o'z serverimizdan |
| 3 | 04.08 11:31 | 167.235.222.200 | `{"diagnostika":...}` | o'z serverimizdan |
| 4 | 08.08 05:41 | 213.230.93.61 | `{"ping":true}` | bugungi tekshiruv |

Haqiqiy lid voqeasi — **0 ta**.

### 4.2. Veb-server access log

`~/access-logs/nuriddin-building.uz-ssl_log` da `/api/crm-webhook/` bo'yicha
**yagona** yozuvlar — 08.08 10:41 dagi 3 ta tekshiruv so'rovi.

Bu muhim, chunki access log **autentifikatsiyadan oldin** yoziladi: agar Uysot
noto'g'ri sekret bilan yuborayotgan bo'lsa ham, so'rov bu yerda **ko'rinardi**.
Ko'rinmadi → **so'rov umuman kelmayapti**.

### 4.3. Polling bilan solishtirish (eng kuchli dalil)

O'sha vaqt oralig'ida bizning polling (diff-engine) CRM'dan **o'zi topgan**
o'zgarishlar:

| Voqea turi | So'nggi 2 soatda | Oxirgisi |
|---|---|---|
| `first_seen` (yangi lid) | **183** | 10:41 |
| `stage_change` (bosqich) | **56** | 10:51 |
| **Webhook orqali kelgani** | **0** | — |

Ya'ni CRM'da lidlar **faol o'zgaryapti**, Uysot esa bu haqda xabar yubormayapti.

---

## 4.4. Qayta tekshiruv — 11.08.2026, 16:10 (5 soatdan keyin)

Egasi «webhook uladim» deganidan keyin qayta tekshirildi:

| Tekshiruv | Natija |
|---|---|
| `crm-webhook` ga so'rovlar (access log) | **0** |
| **404 javoblar** (bugun, butun sayt) | **0** |
| Tashqi IP'lardan POST | faqat qonuniy: brauzer, mobil ilova, Telegram |

**404 yo'qligi muhim xulosa beradi:** agar URL'da faqat **yo'l** xato bo'lsa
(masalan `/api/crm-webhook/uysot` o'rniga `/crm-webhook/uysot`), so'rov bizga
kelib **404** olardi va logda ko'rinardi. Ko'rinmadi.

Demak qolgan ikki ehtimol:
1. **Domen nomida xato** — so'rov butunlay boshqa manzilga ketyapti (bizda iz qolmaydi)
2. **Uysot umuman yubormayapti**

### URL'ni belgima-belgi tekshirish

Uysot'dagi maydonda aynan shu bo'lishi kerak (`nuriddin`, ikkita `n` bilan;
`building` to'liq; `.uz`):

```
https://nuriddin-building.uz/api/crm-webhook/uysot?secret=<SEKRET>
```

Tez-tez uchraydigan xatolar: `nuridin` (bitta `n`), `bulding`, `http://`
(`https` o'rniga), `?secret=` qismining tushib qolishi, oxirida ortiqcha `/`.

---

## 5. Tekshirilgan va rad etilgan sabablar

| Gipoteza | Holat | Nega rad etildi |
|---|---|---|
| Bizning endpoint ishlamaydi | ❌ | Sinovda 200; Uysot ping'i ham o'tgan |
| Sekret noto'g'ri → rad etilyapti | ❌ | Access logda umuman so'rov yo'q |
| DNS/TLS/tarmoq to'sig'i | ❌ | 01.08 dagi Uysot ping'i muvaffaqiyatli |
| Server o'chiq edi | ❌ | Sayt 200 qaytaradi, boshqa trafik kelib turibdi |
| Lid o'zgarmagan | ❌ | 2 soatda 56 ta bosqich o'zgarishi (polling ko'rgan) |

---

## 5b. Chuqurroq gipotezalar (11.08.2026)

Uysot **hech qachon** urinmagani aniqlangach, sabab uch qatlamdan birida
bo'lishi mumkin. Ularning ba'zilarini biz **tekshira olmaymiz**:

| # | Gipoteza | Tekshirish imkoni |
|---|---|---|
| A | **Server xavfsizlik devori (CSF/LFD) Uysot IP'sini bloklagan** — so'rov Apache'ga yetmasdan tashlanadi, shuning uchun access logda **iz qolmaydi** | ❌ Root kerak — **ahost'dan so'rash** |
| B | **Uysot tomonda yuborish umuman yoqilmagan** (saqlash muvaffaqiyatsiz, yoki tarif/ruxsat cheklovi) | ❌ Uysot'dan so'rash |
| C | **Webhook voronka (pipeline) darajasida sozlanishi kerak** — token darajasidagi sozlama yetarli bo'lmasligi mumkin | 🟡 Kabinetda tekshirish |
| D | **Uysot'ning chiquvchi tarmog'ida `.uz` yoki bizning IP bloklangan** | ❌ Uysot'dan so'rash |

**A gipotezasi ayniqsa muhim:** agar xavfsizlik devori bloklayotgan bo'lsa,
Uysot «yubordik» deydi, biz «kelmadi» deymiz — **ikkalasi ham to'g'ri** bo'ladi.
Buni faqat hosting (ahost) tekshira oladi.

Shu sababli quyidagi xatda **eng muhim savol — ularning yuborish jurnali
(delivery log)**: unda urinish bormi, va qanday xato qaytgan (timeout /
connection refused / 403 / DNS). Bu javob A va B ni darhol ajratadi.

---

## 6. Uysot qo'llab-quvvatlashiga xat (nusxalab yuboring)

```
Assalomu alaykum!

Kompaniya: Nurli Diyor (super admin: Nurullojon Obloqulov)
Ulanish nomi: «Xodimlar tizimi» (Kirish tokeni, yaratilgan 04.08.2026 16:43,
muddati 31.12.2026)

MUAMMO: Ulanish tafsilotlari → Webhook tabida webhook yoqilgan va URL
kiritilgan bo'lsa ham, serverimizga BIRORTA HAM webhook so'rovi kelmayapti.

Webhook URL:
https://nuriddin-building.uz/api/crm-webhook/uysot?secret=***

Tanlangan voqealar: Lid yaratildi, Lid biriktirildi, Lid bosqichi o'zgardi

TEKSHIRGANLARIMIZ:
1. Endpointimiz ishlayapti — to'g'ri sekret bilan HTTP 200, sekretsiz HTTP 401
   (tashqaridan sinab ko'rildi, javob normal).
2. Veb-server access logimizni iyul va avgust arxivlari bilan birga to'liq
   tekshirdik: /api/crm-webhook/ manziliga sizdan BIRORTA HAM so'rov
   kelmagan. Muhim: access log autentifikatsiyadan OLDIN yoziladi, ya'ni
   sekret xato bo'lganda ham (401) so'rov logda ko'rinardi. Shuningdek
   bugun butun saytda 404 javoblar soni — 0, ya'ni noto'g'ri yo'l bilan ham
   urinish bo'lmagan.
3. Shu vaqtda Open API polling orqali biz o'zimiz 56 ta bosqich o'zgarishi va
   183 ta yangi lidni ko'rdik — ya'ni voqealar sodir bo'lgan.

SAVOLLAR (eng muhimi — 1-si):
1. YUBORISH JURNALINGIZNI (delivery log) ko'ra olasizmi? Bizga aynan
   quyidagilar kerak: urinish bo'lganmi, qachon, va qanday xato qaytgan
   (timeout / connection refused / DNS / 403 / boshqa). Bu javob muammo
   sizning tomondami yoki yo'lda ekanini darhol aniqlaydi.
2. 04.08.2026 16:43 da token qayta yaratilganda webhook sozlamalari
   o'chib ketgani ma'lummi? (Biz shunday holatni ko'rdik.)
3. Webhook ishlashi uchun qo'shimcha shart bormi — masalan alohida
   litsenziya/tarif, VORONKA (pipeline) darajasida sozlash, yoki
   tasdiqlash bosqichi?
4. Sinov uchun test-webhook yuborish imkoniyati bormi? Agar aniq vaqtni
   aytsangiz, biz o'sha daqiqada serverni jonli kuzatib turamiz.
5. Chiquvchi so'rovlaringizda .uz domenlari yoki bizning IP (167.235.222.200)
   uchun cheklov yo'qmi?

Hurmat bilan.
```

---

## 7. Hozircha ta'siri

**Kritik emas.** Polling (diff-engine) har 3 daqiqada CRM'ni tekshiradi va
barcha lid voqealarini yozadi. Webhook faqat **kechikishni** kamaytirardi
(3 daqiqa → bir necha soniya).

Kod buni to'g'ri boshqaradi: `crm_mode.lead_polling_active()` webhook jonli
ekaniga **dalil** bo'lmasa pollingni davom ettiradi. Ya'ni webhook ishlamasa
ham hech narsa yo'qolmaydi, va u ishlab ketsa polling o'zi to'xtaydi.

---

## 8. Bog'liq

- Karta: [TAHLIL_TOPSHIRIQLARI.md](TAHLIL_TOPSHIRIQLARI.md) → bo'lim **2.3**
- Qabul qiluvchi kod: [`api/routers/uysot_webhook.py`](api/routers/uysot_webhook.py)
- Qayta ishlash: [`api/services/uysot_webhook.py`](api/services/uysot_webhook.py)
- Rejim mantiqi: [`api/services/crm_mode.py`](api/services/crm_mode.py)

> ⚠️ Xatdagi `secret=***` ni yuborishdan oldin haqiqiy qiymatga almashtirmang —
> Uysot'ga sekretni oshkor qilish shart emas, ular URL'ni o'z tizimida
> allaqachon ko'radi.
