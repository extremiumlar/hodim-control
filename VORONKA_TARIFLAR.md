# Voronka ta'riflari (0-bosqich natijasi)

**Sana:** 2026-08-15 · **Qaror qabul qildi:** egasi (Boshliq) ·
**Reja:** `VORONKA_TARGET_REJASI.html`

Bu hujjat — voronkaning YAGONA haqiqat manbai. Har bir hisob (o'lchov,
konversiya, teskari kalkulyator, target tarqatish) shu ta'riflarga tayanadi.
**Ta'rif o'zgarsa — butun tarixni qayta hisoblash kerak bo'ladi**, shuning
uchun o'zgartirish faqat ongli qaror bilan va shu faylga yozib qo'yiladi.

---

## 1. Bosqichlar va ularning manbai

| # | Bosqich | Ta'rif | Manba (tizimda) |
|---|---------|--------|-----------------|
| 1 | **Lid** | CRM'da yangi lid paydo bo'lgani | `CrmLeadState` — `crm_created_ts` (CRM'ning o'z vaqti), yo'q bo'lsa `first_seen_at` |
| 2 | **Urinish** | Terilgan HAR QANDAY qo'ng'iroq (ko'tarilmagani ham) | `HourlyActual.calls` |
| 3 | **Suhbat** | Javob berilgan qo'ng'iroq (`missed == false`) | `HourlyActual.answered` |
| 4 | **Ofisga taklif** | Lid «Officega taklif qilindi» bosqichiga o'tgani | `LeadEvent` → `CRM_UYSOT_INVITE_PIPE_STATUS_IDS` (7139, 8090, 8786) |
| 5 | **Tashrif** | Lid «Tashrif» bosqichiga KO'CHIRILGANI | `LeadEvent` → `CRM_UYSOT_VISIT_PIPE_STATUS_IDS` (7166, 8787) |
| 6 | **Shartnoma = SOTUV** | Lid «Shartnoma qilindi» bosqichiga o'tgani | `LeadEvent` → `CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS` (8060, 8788) |

**1 shartnoma = 1 uy.** «Oyiga 10 uy» = «oyiga 10 shartnoma». Bitta
shartnomada bir nechta xonadon bo'lishi hozircha hisobga OLINMAYDI — kerak
bo'lsa alohida ma'lumot manbai qo'shiladi.

---

## 2. Qotirilgan qoidalar

### 2.1 «Kamida shu bosqichga yetgan» mantig'i
Lid oraliq bosqichni **chetlab o'tishi** mumkin (masalan taklifsiz to'g'ridan
tashrifga). Shuning uchun bosqich soni «aynan shu bosqichga kirganlar» emas,
**«shu bosqich yoki undan keyingisiga yetganlar»** deb hisoblanadi. Aks holda
konversiya 100% dan oshib ketardi (tashrif taklifdan ko'p chiqardi).

Bosqich tartibi (rank): lid(0) < taklif(1) < tashrif(2) < shartnoma(3).

### 2.2 `first_seen` bosqich o'tishi EMAS
Skanerimiz lidni birinchi marta ko'rgani (`event_type='first_seen'`) — CRM'dagi
hodisa emas. U **lid** sifatida sanaladi, lekin taklif/tashrif/shartnomaga
KIRITILMAYDI. Sabab va tarix: `api/services/lead_diff.py::_is_visit_event`
(2026-08-13 qarori — bir kunda 149 ta soxta «tashrif» chiqqan edi).

### 2.3 Bitta lid — bitta hisob
Bosqich sonlari **noyob lid** bo'yicha (`distinct crm_lead_id`). Lid bir
bosqichga ikki marta kirsa (orqaga qaytib yana o'tsa) — bir marta sanaladi.

### 2.4 Ikki rejim, ikki savol
- **Davr kesimi** (operativ): «shu oy ichida nechta tashrif bo'ldi». Oyni
  taqqoslash va kunlik nazorat uchun.
- **Kogorta** (haqiqiy konversiya): «shu oyda KELGAN lidlarning nechtasi
  keyinchalik sotuvga aylandi». Vaqt siljishi tuzog'iga yagona to'g'ri javob —
  avgustda kelgan lid oktyabrda shartnoma qilishi mumkin.

Konversiya foizi **faqat kogorta rejimida** «haqiqiy» deb ataladi. Davr
kesimidagi nisbat ma'lumot uchun ko'rsatiladi, lekin rejalashtirishga asos
bo'lmaydi.

### 2.5 Kogorta «pishmagan» bo'lishi mumkin
Bu oyda kelgan lidning sotuvga aylanishiga hali vaqt bor. Shuning uchun
kogorta natijasi yoshi bilan birga ko'rsatiladi (`days_elapsed`) va
**yetilmagan kogorta konversiyasi «hali to'liq emas» deb belgilanadi** — aks
holda joriy oy har doim eng yomon ko'rinadi.

---

## 3. Ruxsatlar

| Amal | Kim |
|------|-----|
| Voronkani KO'RISH | rahbar rollar (hr, rop, boss, dasturchi) |
| Oylik maqsad («10 uy») QO'YISH | **Boshliq, Dasturchi, ROP** |
| Konversiyani qo'lda o'zgartirish (kalkulyatorda) | maqsad qo'yuvchilar bilan bir xil |

---

## 4. Hali hal qilinmagan (kelajak bosqichlar)

- **Bekor qilingan shartnoma** — hozir avtomatik ayrilmaydi. Shartnoma bosqichiga
  kirgan lid keyin «Muvaffaqiyatsiz»ga o'tsa, sotuv soni kamaymaydi.
  Kerak bo'lsa: 6-bosqichda «bekor» hisobi qo'shiladi.
- **Lid manbai (kanal)** — 2-bosqich.
- **Reklama xarajati va auditoriya** — 3-bosqich (qo'lda kiritiladi).
- **Takroriy murojaat** — hozir CRM yangi lid yaratsa yangi lid deb sanaladi.
