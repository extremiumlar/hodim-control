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

**Qo'shimcha dalil:** 01.08.2026 11:14 da IP `84.54.71.13` dan (Uysot'niki
bo'lsa kerak) `{"ping":true}` kelgan va **200 bilan qabul qilingan**. Ya'ni
tarmoq yo'li, TLS, DNS va autentifikatsiya — hammasi ishlaydi.

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

## 5. Tekshirilgan va rad etilgan sabablar

| Gipoteza | Holat | Nega rad etildi |
|---|---|---|
| Bizning endpoint ishlamaydi | ❌ | Sinovda 200; Uysot ping'i ham o'tgan |
| Sekret noto'g'ri → rad etilyapti | ❌ | Access logda umuman so'rov yo'q |
| DNS/TLS/tarmoq to'sig'i | ❌ | 01.08 dagi Uysot ping'i muvaffaqiyatli |
| Server o'chiq edi | ❌ | Sayt 200 qaytaradi, boshqa trafik kelib turibdi |
| Lid o'zgarmagan | ❌ | 2 soatda 56 ta bosqich o'zgarishi (polling ko'rgan) |

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
1. Endpointimiz ishlayapti — to'g'ri sekret bilan HTTP 200, sekretsiz HTTP 401.
2. 01.08.2026 11:14 da sizning IP (84.54.71.13) dan {"ping":true} kelgan va
   200 bilan qabul qilingan. Ya'ni tarmoq yo'li ishlaydi.
3. Veb-server access logimizda 01.08 dan keyin /api/crm-webhook/ ga sizdan
   birorta so'rov yo'q (access log autentifikatsiyadan OLDIN yoziladi, ya'ni
   sekret xato bo'lganda ham so'rov ko'rinardi).
4. Shu vaqtda Open API polling orqali biz o'zimiz 56 ta bosqich o'zgarishi va
   183 ta yangi lidni ko'rdik — ya'ni voqealar sodir bo'lgan.

SAVOLLAR:
1. Webhook yuborish sizning tomondan haqiqatan faolmi? Yuborish jurnalini
   (delivery log) ko'ra olasizmi — urinishlar bormi, xato qaytganmi?
2. 04.08.2026 16:43 da token qayta yaratilganda webhook sozlamalari
   o'chib ketgani ma'lummi? (Biz shunday holatni ko'rdik.)
3. Webhook ishlashi uchun qo'shimcha shart bormi — masalan alohida
   litsenziya/tarif, voronka (pipeline) tanlash, yoki tasdiqlash bosqichi?
4. Sinov uchun test-webhook yuborish imkoniyati bormi?

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
