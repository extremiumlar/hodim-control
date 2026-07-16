"""Bilim bazasi anketasi — savollar to'plami (anketalar/Anketa_toplam_N.docx
fayllaridan ko'chirilgan YAGONA manba).

Word fayllar qog'ozda to'ldirish uchun edi; bot orqali yuborishda savollar shu
modulda kod sifatida turadi (baza yoki fayl o'qish shart emas — savollar to'plami
o'zgarsa docx bilan birga shu fayl ham yangilanadi).

Har xodimga BITTA (takrorlanmas) to'plam biriktiriladi — `ANKETA_TARGETS`da
qat'iy 1:1 taqsimot: ism (users.full_name boshlanishi bo'yicha qidiriladi) →
to'plam raqami. Foydalanuvchi bazadan sessiya yaratilayotganda hal qilinadi,
shuning uchun ID o'zgarsa ham moslik buzilmaydi.
"""

# Xodim (full_name kichik harflarda shu bilan boshlanadi) → to'plam raqami.
# 5 xodim ↔ 5 to'plam, har biri faqat bitta to'plam oladi.
ANKETA_TARGETS: list[tuple[str, int]] = [
    ("kamola", 1),
    ("shahnoza", 2),
    ("hayot", 3),
    ("firuzabonu", 4),
    ("albina", 5),
]

# Xodimga anketa boshlanishida yuboriladigan qoidalar (docx'dagi "Qanday
# to'ldiriladi" bo'limining bot oqimiga moslangan varianti).
ANKETA_RULES = (
    "— Har bir savolga BITTA xabar bilan javob yozing; javob yuborilgach keyingi savol keladi.\n"
    "— Javoblar bot (avtomatik javob beruvchi dastur) bilim bazasiga kiritiladi — "
    "mijozga aytiladigan RASMIY variantda yozing.\n"
    "— Aniq bilmagan savolga taxmin yozmang — «aniq bilmayman» deb yozing, bu ham muhim ma'lumot.\n"
    "— O'zgarib turadigan ma'lumot (narx, muddat, bosqich) yonida bugungi sanani ko'rsating."
)

_A = "A qism · Asosiy savollar"
_C = "C qism · Ochiq savollar (eng muhimi!)"

# Barcha to'plamlarda bir xil bo'lgan A qism (docx'larda ham aynan shunday).
_COMMON_A: list[dict] = [
    {"section": _A, "text": "Xonadonni bron qilish uchun mijoz nima qilishi kerak va bron qancha vaqt turadi?"},
    {
        "section": _A,
        "text": "Quruvchi aybi bilan uy topshirish kechiksa, mijozga kompensatsiya/jarima to'lanadimi? Rasmiy javob nima?",
    },
    {
        "section": _A,
        "text": "Mijoz «ishonchim komil emas, qurilish bitmasa pulim kuyadimi?» desa, rasmiy javobimiz nima?",
    },
]


def _open_questions() -> list[dict]:
    return [
        {
            "section": _C,
            "text": "Mijozlar sizdan tez-tez so'raydigan, lekin yuqorida YO'Q 3-5 ta savolni yozing (javobi bilan).",
        },
        {
            "section": _C,
            "text": "Siz javob berishga qiynalgan yoki aniq javobi yo'q 2-3 ta savolni yozing (javobsiz bo'lsa ham).",
        },
    ]


ANKETA_TOPLAMLAR: dict[int, list[dict]] = {
    1: [
        *_COMMON_A,
        {
            "section": "B qism · Kompaniya va ishonch",
            "text": "Kompaniyaning rasmiy yuridik nomi va rekvizitlari: mijozga «Nuriddin buildings» deymizmi "
            "yoki «Sayxun invest MCHJ»mi? STIR/litsenziya raqamlarini yozing.",
        },
        {
            "section": "B qism · Qurilish va texnik",
            "text": "Isitish individual kotyolmi yoki markaziymi? Qishki kommunal xarajat taxminan qancha bo'ladi?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "Balkon/lodjiya maydoni umumiy kvadraturaga kiradimi, koeffitsiyenti qanday?",
        },
        {
            "section": "B qism · Narx va to'lov",
            "text": "Narx qurilish bosqichi oshgani sari ko'tariladimi? Mijozga «hozir oling»ni qanday asoslaymiz?",
        },
        {
            "section": "B qism · Topshirish va muddat",
            "text": "Kalit topshirish jarayoni qanday bo'ladi (dalolatnoma, tekshirish, kamchiliklar ro'yxati)?",
        },
        {
            "section": "B qism · Hudud va infratuzilma",
            "text": "Bozor va oziq-ovqat do'konlari hozir qayerda (masofa)?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Obyektga borib ko'rish qanday tashkil qilinadi (transport beriladimi, oldindan yozilish kerakmi)?",
        },
        {
            "section": "B qism · Qiyin savollar va e'tirozlar",
            "text": "«Guliston kichkina shahar, keyin sotolmasam-chi?» — nima deymiz?",
        },
        *_open_questions(),
    ],
    2: [
        *_COMMON_A,
        {
            "section": "B qism · Kompaniya va ishonch",
            "text": "Mijoz puli qayerga tushadi — eskrou/maxsus hisob bormi? Mijoz so'rasa nima deymiz?",
        },
        {
            "section": "B qism · Qurilish va texnik",
            "text": "Qurilish hozir qaysi bosqichda (qaysi blok nechanchi qavatda)? Sana bilan yozing.",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "Birinchi va oxirgi qavatning afzallik/kamchiliklarini mijozga qanday tushuntiramiz?",
        },
        {
            "section": "B qism · Narx va to'lov",
            "text": "Ijaraga berish maqsadida olayotgan investorga nima deymiz (ijara narxi, daromad taxmini)?",
        },
        {
            "section": "B qism · Topshirish va muddat",
            "text": "Uy topshirilgunicha mijoz o'z kvartirasini ko'rib tura oladimi (qurilishga kirish)?",
        },
        {
            "section": "B qism · Hudud va infratuzilma",
            "text": "Jamoat transporti qatnovi qanday (qaysi yo'nalishlar, bekat qancha masofada)?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Masofadan (telefon/telegram orqali) xonadon tanlash va rasmiylashtirish mumkinmi?",
        },
        {
            "section": "B qism · Qiyin savollar va e'tirozlar",
            "text": "«O'ylab ko'raman» deb ketayotgan mijozga nima deymiz (qayta aloqa qoidasi)?",
        },
        *_open_questions(),
    ],
    3: [
        *_COMMON_A,
        {
            "section": "B qism · Qurilish va texnik",
            "text": "Lift nechta, qaysi firmaniki? Har blokda bormi?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "«Korobka» holatda topshirilganda aniq nima bo'ladi (stjajka, shtukaturka, eshik, radiator...)?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "Ko'rgazma (namuna) xonadon bormi? Qayerda va qachon ko'rsa bo'ladi?",
        },
        {
            "section": "B qism · Shartnoma va rasmiylashtirish",
            "text": "Voyaga yetmagan bola nomiga rasmiylashtirish mumkinmi?",
        },
        {
            "section": "B qism · Topshirish va muddat",
            "text": "Kommunal to'lovlar qachondan boshlab mijoz zimmasiga o'tadi?",
        },
        {
            "section": "B qism · Hudud va infratuzilma",
            "text": "Toshkentga qatnov qanday (masofa, vaqt, transport turlari)?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Qaysi ijtimoiy tarmoq/kanallarimiz bor? Mijozni qayerga obuna qilamiz?",
        },
        {
            "section": "B qism · Qiyin savollar va e'tirozlar",
            "text": "Mijozlar eng ko'p qaysi savolda ikkilanib qoladi va o'sha joyda qanday yordam beramiz?",
        },
        *_open_questions(),
    ],
    4: [
        *_COMMON_A,
        {
            "section": "B qism · Qurilish va texnik",
            "text": "Shift balandligi necha metr (kvartirada va birinchi qavatda)?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "«Ta'mirli» va «o'rtacha ta'mir» variantlari aniq nimani o'z ichiga oladi "
            "(pol, devor, santexnika, oshxona...)?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "Kvartira tanlashda mijozlar eng ko'p nimaga e'tibor beradi va biz nimani tavsiya qilamiz?",
        },
        {
            "section": "B qism · Shartnoma va rasmiylashtirish",
            "text": "Chet elda yashovchi mijoz (masalan, Rossiyadagi mehnat muhojiri) qanday rasmiylashtiradi — "
            "masofadan bo'ladimi?",
        },
        {
            "section": "B qism · Hudud va infratuzilma",
            "text": "HOZIR ishlab turgan eng yaqin maktab va bog'cha qaysi, piyoda necha daqiqa?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Sotuv ofisining ish vaqti qanday (dam olish kunlari ishlaydimi)? Mo'ljal/orientir?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Mijoz shikoyat qilsa yoki norozi bo'lsa, kimga yo'naltiramiz?",
        },
        *_open_questions(),
    ],
    5: [
        *_COMMON_A,
        {
            "section": "B qism · Qurilish va texnik",
            "text": "Derazalar qanday (profil, stakan soni), balkonlar oynalanganmi?",
        },
        {
            "section": "B qism · Xonadon va ta'mir",
            "text": "Mijoz planirovkani o'zgartira oladimi (devor olib tashlash, ikkita kvartirani qo'shish)?",
        },
        {
            "section": "B qism · Narx va to'lov",
            "text": "Subsidiya/davlat dasturlari bo'yicha xarid qilish mumkinmi?",
        },
        {
            "section": "B qism · Shartnoma va rasmiylashtirish",
            "text": "Shartnoma qaysi tilda tuziladi? Rus tilida varianti bormi?",
        },
        {
            "section": "B qism · Hudud va infratuzilma",
            "text": "HOZIR ishlab turgan poliklinika/shifoxona qancha masofada?",
        },
        {
            "section": "B qism · Jarayon va aloqa",
            "text": "Mijoz qo'ng'iroq qilsa birinchi suhbatda nimalarni aniqlaymiz (skript bo'yicha)?",
        },
        {
            "section": "B qism · Qiyin savollar va e'tirozlar",
            "text": "«Narxingiz qimmat, falon joyda arzonroq ekan» — rasmiy javobimiz qanday?",
        },
        *_open_questions(),
    ],
}


def toplam_questions(toplam: int) -> list[dict]:
    return ANKETA_TOPLAMLAR[toplam]
