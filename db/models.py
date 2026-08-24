import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Date,
    ForeignKey,
    String,
    Boolean,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class Role(str, enum.Enum):
    employee = "employee"
    hr = "hr"
    rop = "rop"
    boss = "boss"
    dasturchi = "dasturchi"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    overdue = "overdue"
    cancelled = "cancelled"


class ExcusedStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class MobilografStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"


class FaceReregStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class DailyResultSource(str, enum.Enum):
    crm = "crm"
    manual = "manual"


class MobilografSource(str, enum.Enum):
    telegram_reaction = "telegram_reaction"
    manual = "manual"


class AttendanceStatus(str, enum.Enum):
    present = "present"  # keldi (o'z vaqtida)
    late = "late"  # kechikdi
    absent = "absent"  # kelmadi (ish kuni bo'lsa-yu, check-in yo'q)
    weekend = "weekend"  # dam olish kuni (ish jadvali bo'yicha ishlanmaydi)
    # 5.1-band: tasdiqlangan sababli kun — kelib check-in qilgan bo'lsa ham
    # (masalan shifokordan keyin tushdan keyin ishga kelgan) bu "late" EMAS.
    # Ilgari sababli kun davomatga UMUMAN ta'sir qilmasdi: check-in bo'lsa
    # late_minutes to'liq hisoblanardi, ExcusedDay hech qayerda tekshirilmasdi.
    excused = "excused"


class PayBasis(str, enum.Enum):
    monthly = "monthly"  # qat'iy oylik
    daily = "daily"  # kunbay
    hourly = "hourly"  # soatbay


class OvertimeMode(str, enum.Enum):
    derived = "derived"  # xodimning o'z oyligidan (soatlik stavka = oylik / norma soat)
    fixed_rate = "fixed_rate"  # HR o'zi so'm/soat belgilaydi


class NormHoursSource(str, enum.Enum):
    schedule = "schedule"  # ish jadvalidan avtomatik (QAROR — default)
    fixed = "fixed"  # HR qat'iy son kiritadi


class FinePolicyScope(str, enum.Enum):
    global_ = "global"
    position = "position"
    user = "user"


class FineMode(str, enum.Enum):
    per_day = "per_day"  # limitdan keyingi HAR kechikkan kunga qat'iy summa (QAROR — default)
    per_minute = "per_minute"  # ⭐ kelajakda
    tiered = "tiered"  # ⭐ kelajakda
    percent_of_daily = "percent_of_daily"  # ⭐ kelajakda


class AbsentMode(str, enum.Enum):
    none = "none"
    fixed = "fixed"  # HR kiritgan qat'iy summa (QAROR — default)
    deduct_daily = "deduct_daily"  # ⭐ kelajakda: kunlik ish haqi ulushi


class FineAppliesTo(str, enum.Enum):
    """Ushlanma QAYERDAN olinadi.

    2026-08-18 (yangi TZ 2.1, S-02): default `net_salary` dan `bonus_first`
    ga o'zgartirildi. Sabab HUQUQIY — ish haqidan to'g'ridan-to'g'ri ushlab
    qolish O'zbekiston Mehnat kodeksida cheklangan; bonus esa rag'bat to'lovi
    va uni kamaytirish xavfsizroq."""

    bonus_first = "bonus_first"  # avval bonusdan, qoldig'i `fine_remainder_mode` bo'yicha
    net_salary = "net_salary"  # to'g'ridan-to'g'ri oylikdan


class FineRemainderMode(str, enum.Enum):
    """`bonus_first` rejimida bonus ushlanmadan KAM bo'lsa qoldiq nima bo'ladi.

    Bu BIZNES qarori va vaqt o'tib o'zgarishi mumkin — shuning uchun kodda
    qotirilmaydi, HR panelidan tanlanadi (yangi TZ, agent eslatmasi 3-band)."""

    drop = "drop"  # qoldiq umuman ushlanmaydi — DEFAULT, huquqiy jihatdan eng xavfsiz
    carry_next_month = "carry_next_month"  # keyingi oy bonusidan olinadi
    from_salary = "from_salary"  # oylikdan ushlanadi — faqat qonun ruxsat bergan hollarda


class OvertimeEntryStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PayrollPeriodStatus(str, enum.Enum):
    draft = "draft"
    calculated = "calculated"
    # 2026-08-08: VAZIFALAR AJRATILDI. Ilgari HR o'zi hisoblab, o'zi
    # tasdiqlab, davrni qulflab qo'yardi — bitta odam butun pul jarayonini
    # yakunlardi. Endi oraliq bosqich: HR tekshirib "tayyor" deydi
    # (`hr_approved`), YAKUNIY tasdiq va qulf esa Boshliq/Dasturchida.
    hr_approved = "hr_approved"
    approved = "approved"
    paid = "paid"


class PayslipStatus(str, enum.Enum):
    draft = "draft"
    calculated = "calculated"
    approved = "approved"
    paid = "paid"


class PayslipItemKind(str, enum.Enum):
    base = "base"
    overtime = "overtime"
    bonus = "bonus"
    fine_late = "fine_late"
    fine_absent = "fine_absent"
    adjustment_plus = "adjustment_plus"
    adjustment_minus = "adjustment_minus"


class PayrollAdjustmentKind(str, enum.Enum):
    plus = "plus"
    minus = "minus"


class PayrollAdjustmentStatus(str, enum.Enum):
    """2026-08-13: AVANS uchun tasdiq bosqichi (egasining qarori — "HR
    kiritadi, Boshliq tasdiqlaydi").

    MUHIM: default `approved`. Bu ataylab — bu maydon qo'shilishidan OLDIN
    yaratilgan yozuvlar allaqachon hisobga kirgan edi, ular `pending` bo'lib
    qolsa o'tgan oylar jimgina o'zgarib ketardi."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    # 2026-08-20 (Avans TZ A-04): tasdiq va PUL BERISH boshqa-boshqa
    # voqealar. Ilgari ular ajratilmagan edi va HR «berilgan sana» ni
    # kiritishda yozardi — Boshliq rad etsa pul allaqachon qo'lda bo'lardi.
    # Endi: `pending` -> `approved` (ruxsat berildi) -> `issued` (kassa
    # pulni berdi). Oylikka `approved` HAM, `issued` HAM kiradi: ruxsat
    # berilgan avans hisobga olinishi kerak, aks holda oy oxirida
    # «kutilmagan» ushlanma chiqardi.
    issued = "issued"


# Oylikka KIRADIGAN avans holatlari. Bitta joyda turishi shart: bu ro'yxat
# `build_payslip`, botdagi payslip va ariza qaytarish mantiqida bir xil
# bo'lmasa — xodim bitta summani ikki marta ko'radi yoki umuman ko'rmaydi.
PAYROLL_COUNTED_STATUSES = (
    PayrollAdjustmentStatus.approved.value,
    PayrollAdjustmentStatus.issued.value,
)


class PayrollAdjustmentCategory(str, enum.Enum):
    """`manual` — HR qo'lda kiritgan qo'shimcha/ushlanma (eski oqim, tasdiq
    talab qilmaydi). `advance` — AVANS: oy o'rtasida qo'lga berilgan pul,
    Boshliq tasdig'idan keyin oy oxirida oylikdan ayiriladi."""

    manual = "manual"
    advance = "advance"


class PayrollAdjustmentSource(str, enum.Enum):
    """Avans QAYERDAN kiritildi (Avans TZ, A-01).

    NEGA KERAK: avansning bir nechta kirish yo'li bor va ular BITTA jadvalga
    yozadi (tekshirilgan: `requests.py` va `payroll.py` ikkalasi ham
    `PayrollAdjustment(category='advance')` yaratadi). Jadval bitta bo'lgani
    YAXSHI — payslip uni bir marta yig'adi. Lekin manba ko'rinmasa HAQIQIY
    xavf qoladi: xodim ariza beradi (yozuv-1), HR o'sha avansni «Ish haqi →
    Avans» sahifasidan qo'lda HAM kiritadi (yozuv-2) — ikkita mustaqil qator
    va pul ikki marta ayiriladi.

    Manba yozib borilsa: (a) ro'yxatda «ariza orqali» ko'rinadi va HR
    takrorlamaydi, (b) dublikat qo'riqchisi ishlaydi, (c) bot qo'shilganda
    uchinchi yo'l ham ajratiladi."""

    hr_manual = "hr_manual"   # «Ish haqi → Avans» sahifasidan HR kiritdi
    request = "request"       # Xodim ariza berdi, tasdiqlangach yozildi
    bot = "bot"               # Bot orqali avans kuni so'rovi (C blok)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    telegram_group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="team")


class Position(Base):
    """Lavozim — xodimning ish funksiyasi (sotuvchi, operator, mobilograf va h.k.).

    Roldan (ruxsat darajasi) farqli o'laroq, lavozim botning qaysi menyu tugmalari
    ko'rinishini (`menu_flags`), qaysi ko'rsatkichlar kuzatilishini (`metrics`) va
    qaysi rahbar rol (ROP yoki HR) bu lavozimga vazifa/norma belgilay olishini
    (`managed_by_roles`) belgilaydi. Web paneldan to'liq sozlanadi."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    # {"tasks": true, "norm": true, "kpi": true, "excused": true} — bot menyu tugmalari
    menu_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ["suhbat", "tashrif", "oddiy_video", "dumaloq_video"] — shu lavozim uchun kuzatiladigan ko'rsatkichlar
    metrics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ["rop"] yoki ["hr"] — qaysi rahbar rol shu lavozimga vazifa/norma belgilay oladi
    # (boss/dasturchi har doim hammani boshqaradi, ro'yxatga kiritish shart emas)
    managed_by_roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #  Tashkiliy sxemadagi OTA lavozim (yangi TZ 3.16 / S-39).
    #  `NULL` — eng yuqori bo'g'in (masalan Direktor).
    #
    #  ⚠️ HALQA TAQIQLANADI. Faqat «o'ziga bo'ysunish» emas — A→B→C→A
    #  kabi uzun halqa ham. Halqa bo'lsa sxema chizilganda cheksiz
    #  rekursiyaga tushardi va `GET /org-chart` butun saytni osib
    #  qo'yardi (Passenger'da konkurentlik = 1). Tekshiruv
    #  `api/services/org.py::assert_no_cycle` da — YAGONA joyda.
    parent_position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="position")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)
    bot_started: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # "O'rin" (masalan Mobilogrof) — bu foydalanuvchining Telegram bog'lanishi doimiy
    # qayta-egallanadigan: invite-link har doim (bot_started bo'lsa ham) qayta olinadi,
    # va uni boshqa odam bosib /start qilsa, o'sha avtomatik joriy egasi bo'lib qoladi.
    is_seat: Mapped[bool] = mapped_column(Boolean, default=False)
    # Issiq lid taqsimotida QATNASHADIMI (2026-08-06, egasining talabi).
    # Bot mas'ulsiz lidni faqat shu bayrog'i yoqilgan operatorlarga beradi —
    # ya'ni ta'tildagi/sinov (Tester) akkauntiga lid "tushib qolmaydi".
    # Migratsiyada CRM ID biriktirilgan xodimlarga TRUE qo'yildi (ular
    # allaqachon operator edi), qolganlarga FALSE.
    hot_lead_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Davomat (keldi/ketdi) vaqtini QO'LDA tuzatish huquqi — ROLDAN qat'i nazar,
    # SHAXSAN berilgan ruxsat. Roli bo'yicha huquqi borlar (hr/boss/dasturchi)
    # uchun bu bayroq ahamiyatsiz — ular baribir tahrirlay oladi.
    #
    # Nega alohida ustun, yangi rol emas: egasi "ma'lum bir odamlarga" berishni
    # so'radi — masalan bitta ROP yoki bitta xodimga. Yangi rol yaratilsa,
    # o'sha odam boshqa hamma joyda ham (norma, oylik, statistika) yangi rol
    # huquqlarini olib qolardi.
    #
    # Beruvchi: FAQAT Dasturchi (`POST /admin/users/{id}/attendance-editor`).
    # Cheklov: shu bayroq bilan tahrirlayotgan odam O'Z yozuvini tuzata OLMAYDI
    # (o'z kechikishini o'zi o'chirib tashlamasligi uchun) — `manual_attendance`.
    can_edit_attendance: Mapped[bool] = mapped_column(Boolean, default=False)
    # Joylashuvsiz («bez lokatsiya») check-in ruxsati — shu bayroq yoqilgan xodim
    # «Keldim»/«Ketdim»ni ISTALGAN joydan bosa oladi: ofis radiusi tekshirilmaydi.
    #
    # Kimga: doimiy ob'ektda yurmaydigan xodimlar (masalan mobilograf, kuryer,
    # ko'chma sotuv) — ular ofisga kirmasdan ishlaydi va GPS tekshiruvi ularni
    # doim bloklardi.
    #
    # DIQQAT: Face ID (yuz tasdiqlash) BEKOR QILINMAYDI — faqat GPS chetlab
    # o'tiladi. Aks holda check-in umuman himoyasiz qolardi (istalgan odam
    # istalgan joydan bosaverardi).
    skip_location_check: Mapped[bool] = mapped_column(Boolean, default=False)
    # Kechikish/jarima QOIDASINI (`FinePolicy`) o'zgartirish huquqi — roldan
    # mustaqil, SHAXSAN beriladi. hr/boss/dasturchi uchun ahamiyatsiz (ularda
    # roli bo'yicha bor).
    #
    # Beruvchi: Dasturchi YOKI Boshliq (avvalgi ikki bayroqdan farqi shu —
    # ular faqat Dasturchi qo'lida edi; egasi "dasturchi yoki boss hal
    # qiladi" dedi).
    #
    # ⚠️ Bu bayroq FAQAT jarima qoidasini ochadi — oylik hisoblash,
    # tasdiqlash, stavka va boshqa payroll amallari TEGILMAYDI (ular
    # `_require_manage` da qoladi). Aks holda bir bayroq bilan butun
    # payroll boshqaruvi berilib qolardi.
    can_edit_fine_policy: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # Taklif havolasi muddati (Telegram login xavfsizlik arxitekturasi, Layer 3) —
    # `invite_token_ttl_days` (api/config.py) asosida beriladi. NULL — migratsiyadan
    # oldingi eski qatorlar, muddatsiz qoladi (orqaga moslik).
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    crm_external_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # Uysot'da tashriflar suhbatlardan (crm_external_id/employeeNum) boshqa ID tizimida
    # ("responsibleById", lid pipeline'idagi mas'ul xodim) hisoblanadi — shuning uchun
    # alohida ustun kerak.
    crm_visit_external_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # Face ID (davomat) — face-api.js 128-o'lchamli deskriptor JSON matn ko'rinishida.
    # Web check-in'da xodim yuzi shunga solishtiriladi (verifix/hodim_crm'dan
    # birlashtirilgan yagona backend qismi).
    face_descriptor: Mapped[str | None] = mapped_column(Text, nullable=True)
    face_registered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Ishga kirgan sana (2026-08-13, ARIZALAR_REJASI.md Bosqich 0).
    # `created_at` dan FARQI: u — tizimga qo'shilgan payt (xodim allaqachon
    # bir yil ishlagan bo'lishi mumkin). Ta'til stajini/balansini hisoblash
    # uchun haqiqiy ishga kirish sanasi kerak.
    #
    # Migratsiyada mavjud xodimlarga `SalaryRate.effective_from` ning eng
    # kichigidan to'ldirildi — payroll allaqachon shu sanani de-fakto
    # "ish boshlangan kun" sifatida ishlatadi (`compute_base` prorata,
    # api/services/payroll.py). Stavkasi yo'qlarda NULL qoladi.
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #  Tug'ilgan kun (yangi TZ 3.14 / S-22). Bo'sh bo'lsa tizim JIM
    #  turadi — tug'ilgan kunni bilmasdan tabriklab bo'lmaydi va
    #  «kim tug'ilgan kunini kiritmagan» degan ro'yxat HR ishi.
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #  ── Shaxsiy ma'lumotlar (yangi TZ 3.26 / S-26) ──
    #  Bularni xodim O'ZI to'g'ridan-to'g'ri o'zgartira OLMAYDI: so'rov
    #  yuboradi, HR tasdiqlaydi, shundan keyin shu yerga yoziladi.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["Team | None"] = relationship(back_populates="users", foreign_keys=[team_id])
    manager: Mapped["User | None"] = relationship(remote_side=[id])
    position: Mapped["Position | None"] = relationship(back_populates="users", lazy="selectin")

    @property
    def has_face(self) -> bool:
        return bool(self.face_descriptor)


class AppLoginStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    used = "used"


class AppLoginToken(Base):
    """Mobil ilova kirishi — deep-link + bir martalik token. Ilova `/auth/app-login/start`
    bilan token yaratadi, foydalanuvchi botga o'tib tasdiqlaydi (`telegram_id` shu yerda
    bog'lanadi), ilova esa `/auth/app-login/poll` bilan natijani kutib oladi. Token bir
    marta ishlatilgach (`status=used`) yoki `expires_at`dan o'tgach qayta ishlatilmaydi."""

    __tablename__ = "app_login_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=AppLoginStatus.pending.value)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ── Juftlik kodi (pairing code) — hisob egallashga qarshi ──
    # ILOVA ekranida ko'rsatiladi, foydalanuvchi esa uni BOTGA yozadi.
    #
    # NEGA KERAK (haqiqiy zaiflik edi): ilgari bot deep-link ochilishi bilan
    # hech narsa so'ramasdan tasdiqlardi. Hujumchi `/auth/app-login/start`ni
    # o'zi chaqirib (endpoint autentifikatsiyasiz), hosil bo'lgan havolani
    # xodimga yuborardi — xodim BIR MARTA bosishi bilan hujumchi
    # `/auth/app-login/poll` orqali o'sha xodimning 30 kunlik JWT'sini olardi.
    #
    # NEGA TUGMA EMAS, YOZISH: variantli tugmalar (to'g'ri kod + soxtalari)
    # muammoni HAL QILMAYDI — ilovani umuman ochmagan qurbon baribir taxmin
    # qilib bosishi mumkin (4 variantda 25% ehtimol). Kodni YOZISH esa
    # tasdiqlovchi odam haqiqatan ILOVA EKRANINI ko'rayotganini isbotlaydi:
    # hujumchining ilovasidagi kod qurbonga ko'rinmaydi, ya'ni u yozadigan
    # narsasi yo'q.
    pairing_code: Mapped[str] = mapped_column(String(8), default="")
    # Noto'g'ri urinishlar. Kod qisqa (4 raqam) — cheklovsiz bo'lsa taxmin
    # qilib topish mumkin. Chegaraga yetganda token butunlay kuyadi.
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Kod foydalanuvchiga QAYERDAN yetadi:
    #   screen — kirish boshlangan ekranning o'zida (mobil ilova o'z login
    #            ekranida ko'rsatadi — asl oqim);
    #   push   — SAYTDAN boshlangan kirish: bot deep-link ochilganda kod
    #            foydalanuvchining mobil ilovasiga push bilan yuboriladi
    #            (2026-08-05 talabi — saytda kod ko'rinmasin, faqat ilovada).
    # Push yuborib bo'lmasa (qurilma yo'q) qiymat "screen"ga tushiriladi va
    # sayt kodni o'zi ko'rsatadi (poll javobidagi shu maydon orqali biladi) —
    # aks holda mobil ilovasiz foydalanuvchi saytga umuman kira olmay qolardi.
    code_delivery: Mapped[str] = mapped_column(String(10), default="screen")


class UsedTelegramLoginHash(Base):
    """Telegram Login Widget'ning `hash`ini bir marta ishlatilgach eslab qoladi —
    aynan shu hash bilan qayta so'rov (replay, masalan brauzer tarixidan eski
    Login Widget URL'i qayta ochilsa) rad etiladi. Imzoning o'zi 24 soatlik
    `auth_date` oynasida amal qiladi (`verify_telegram_login`) — shu oyna ichida
    hash sizib chiqsa ham qayta ishlatib bo'lmasligi uchun kerak."""

    __tablename__ = "used_telegram_login_hashes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    consumed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LoginAttempt(Base):
    """Parol so'ramaydigan kirish endpointlariga (Telegram imzosi yoki tasodifiy
    token) DoS/resurs himoyasi uchun sliding-window hisoblagich — bu yerda
    taxmin qilinadigan qisqa maxfiy narsa yo'q, shuning uchun BRUTE-FORCE
    HIMOYASI EMAS, faqat ko'p sonli so'rovlar bazani/CPU'ni band qilishining
    oldini oladi."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(40), index=True)
    identifier: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


#  ⚠️ STATISTIKAGA KIRMAYDIGAN VAZIFA MANBALARI (S-46).
#  Onboarding qadamlaridan yaratilgan vazifalar xodimning «bajarilgan
#  vazifalar foizi»ga KIRMAYDI (TZ 3.2). Ro'yxat shu yerda —
#  filtr uch joyda takrorlanmasin va yangi manba qo'shilganda
#  bittasi unutilmasin.
TASK_STATS_EXCLUDED_SOURCES = ("onboarding",)


class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.pending.value, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    #  ── VAZIFA MANBAI (yangi TZ 3.2 / S-46) ──
    #
    #  ⚠️ BU MAYDON STATISTIKA UCHUN. `NULL` — odatdagi ish
    #  topshirig'i; `"onboarding"` — onboarding qadamidan avtomatik
    #  yaratilgan vazifa.
    #
    #  NEGA KERAK: yangi xodimga birinchi kunlarida 10-15 qadam
    #  tushadi va ular vazifa sifatida yaratiladi. Agar ular oddiy
    #  vazifa deb sanalsa, xodimning «bajarilgan vazifalar foizi»
    #  birinchi hafta sun'iy ravishda o'zgarardi (avval keskin
    #  pastga, keyin keskin yuqoriga) va rahbar buni ISH ko'rsatkichi
    #  deb o'qirdi. TZ 3.2 aynan shuni taqiqlaydi: «vazifa
    #  statistikasini buzmasin».
    #
    #  Filtrlanadigan joylar: `daily_digest._tasks_by_user`,
    #  `stats.py` (kunlik vazifa hisoblari). Test buni tekshiradi.
    source: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    #  Manba yozuv (`onboarding_progress.id`) — ikki tomonlama
    #  sinxron uchun: vazifa bajarilsa qadam ham bajarilgan bo'ladi.
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class Norm(Base):
    __tablename__ = "norms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    metric_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Bosqich 3.5 (Dasturchi rejimi) — YUMSHOQ o'chirish: xato kiritilgan tarixiy
    # yozuvni butunlay yo'qotmasdan "faol emas" qilish. Barcha o'qish so'rovlari
    # (masalan `_current_value`) `deleted_at IS NULL` bilan filtrlanishi shart.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DailyResult(Base):
    __tablename__ = "daily_results"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_results_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date)
    conversations_count: Mapped[int] = mapped_column(Integer, default=0)
    visits_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default=DailyResultSource.manual.value)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class WorkLogSource(str, enum.Enum):
    bot = "bot"
    web = "web"  # xodim kabineti ham, mobil WebView ham shu


class WorkLogEntry(Base):
    """Xodimning kunlik ish yozuvi — "ish kundaligi" (KUNDALIK_ETIROZ_REJASI.md).

    `DailyResult`dan farqi: u kunda BITTA qator va RAQAM (suhbat/tashrif soni),
    bu esa kun ichida BIR NECHTA erkin MATNLI yozuv — har biri o'z vaqt
    tamg'asi bilan. Oy oxirida "to'qib chiqarilgan" hisobotning oldini vaqt
    tamg'alari oladi.

    QULF QOIDASI: yozuvni faqat egasi va faqat `date == bugun (Toshkent)`
    bo'lganda tahrirlaydi/o'chiradi — ertasi kundan hujjat (router tekshiradi,
    `timeutil.today_local`; mijoz yuborgan sanaga ishonilmaydi).

    O'chirish YUMSHOQ (`Norm` naqshi): barcha o'qish so'rovlari
    `deleted_at IS NULL` bilan filtrlanishi SHART.

    Pul mantig'iga ULANMAYDI: yozmaganlik jarima keltirmaydi, faqat rahbar
    hisobotida (coverage) ko'rinadi — payroll yadrosi tinch qoladi."""

    __tablename__ = "work_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    text: Mapped[str] = mapped_column(Text)  # 3..2000 belgi (sxema tekshiradi)
    source: Mapped[str] = mapped_column(String(10), default=WorkLogSource.bot.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MobilografVideo(Base):
    __tablename__ = "mobilograf_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Qo'lda kiritilgan ("manual" source) yozuvlarda Telegram xabari yo'q — NULL.
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default=MobilografStatus.pending.value)
    # telegram_reaction — guruhdagi reaksiya orqali; manual — HR/rahbar qo'lda kiritgan
    # (masalan TELEGRAM_GROUP_CHAT_ID sozlanmagan yoki guruh ishlamay qolgan holat uchun).
    source: Mapped[str] = mapped_column(String(20), default=MobilografSource.telegram_reaction.value)
    # oddiy (F.video) yoki dumaloq (F.video_note) — ikkalasi alohida norma/hisob.
    video_type: Mapped[str] = mapped_column(String(20), default="oddiy")
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExcusedDay(Base):
    """Sababli kun. Bitta xodim + bitta sana — UNIKAL.

    NEGA UNIQUE (2026-08-13, ARIZALAR_REJASI.md Bosqich 0.1): ilgari cheklov
    faqat KODDA edi (`excused_days.py` dublikatni qo'lda tekshiradi). Bu
    yagona so'rovda yetarli, lekin ariza moduli ta'til oralig'idagi 10 kunni
    BIRVARAKAYIGA yozadi — poyga holatida (ikki HR yoki takroriy tasdiq)
    dublikat paydo bo'lardi va sababli kun ikki marta hisoblanardi.
    Bazaviy cheklov `IntegrityError` beradi va takror yozuv jimgina
    o'tkazib yuboriladi (`AttendanceReminder` bilan bir xil himoya)."""

    __tablename__ = "excused_days"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_excused_day_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    # To'lovli sababli kunmi (2026-08-13, Bosqich 0.3). `True` — bugungi
    # xatti-harakat: `monthly` stavkada sababli kun to'liq to'lanadi
    # (kasallik, mehnat ta'tili). `False` — «o'z hisobidan» ta'til: monthly
    # stavkadan kunlik ulush AYIRILADI (`compute_base`).
    #
    # `daily`/`hourly` stavkaga ta'sir qilmaydi — u yerda sababli kun
    # allaqachon to'lanmaydi (faqat `present`/`late` kunlar sanaladi).
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Qaysi arizadan tug'ilgan (ARIZALAR_REJASI.md 3.2). Ariza bekor
    # qilinganda aynan shu bog'liqlik bo'yicha topib qaytariladi; teskari
    # savolga ham javob beradi: «bu sababli kun qayerdan paydo bo'lgan?».
    # NULL — qo'lda kiritilgan (HR yoki xodim so'rovi).
    source_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_requests.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=ExcusedStatus.pending.value)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FaceReregistrationRequest(Base):
    """Yuzni QAYTA ro'yxatdan o'tkazish so'rovi (Savol A — yumshoq choralar). Mavjud
    yuzi bo'lgan xodim yangi descriptorni bevosita almashtira olmaydi: yangi
    descriptor shu yerda kutib turadi, HR/rahbar tasdiqlagandan keyingina
    `User.face_descriptor`ga ko'chiriladi (`ExcusedDay` bilan bir xil naqsh).
    Birinchi marta ro'yxatdan o'tishda (hali `has_face=False`) bu jarayon
    ishlatilmaydi — darhol yoziladi (`register_face` ichida tekshiriladi)."""

    __tablename__ = "face_reregistration_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    new_descriptor: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=FaceReregStatus.pending.value)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Bonus(Base):
    __tablename__ = "bonuses"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_bonuses_user_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    period: Mapped[str] = mapped_column(String(7))
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LeadStageDaily(Base):
    """CRM (Uysot) lidlarining kunlik snapshot'i — operator (`responsibleById`) va
    pipeline bosqichi kesimida. CRM API o'tgan kunlar tarixini bermaydi (faqat lidning
    oxirgi `updatedTimestamp`i) va "bugun tegilgan" lidlar bo'yicha server filtri yo'q,
    shuning uchun scheduler butun bazani sekin skanerlab shu jadvalga yozadi; bot va
    oylik/kunlik statistika shu yerdan tez o'qiladi.

    Grain: (date, responsible_id, pipe_status_id) — tashkilot jami operatorlar bo'yicha,
    bir kun bir bosqich jami esa operatorlar bo'yicha yig'indi orqali olinadi."""

    __tablename__ = "lead_stage_daily"
    __table_args__ = (
        UniqueConstraint("date", "responsible_id", "pipe_status_id", name="uq_lead_stage_daily_grain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # Uysot `responsibleById` — lidning mas'ul operatori (User.crm_visit_external_id bilan
    # bir xil ID tizimi). Nom ham snapshot paytida saqlanadi (CRM'dagi `responsibleBy`).
    responsible_id: Mapped[int] = mapped_column(Integer)
    responsible_name: Mapped[str] = mapped_column(String(255))
    pipe_status_id: Mapped[int] = mapped_column(Integer)
    # Bosqich nomi snapshot paytida saqlanadi — CRM'da bosqich o'chirilsa/qayta nomlansa
    # ham eski kunlar statistikasi o'qiladigan bo'lib qoladi.
    stage_name: Mapped[str] = mapped_column(String(255))
    leads_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperatorCallsDaily(Base):
    """CRM (Uysot) qo'ng'iroqlarining kunlik snapshot'i — operator kesimida
    (kiruvchi/chiquvchi). "Gaplashilgan lidlar" (suhbatlar) aynan shu — call-history'dan.

    Qo'ng'iroqlar `employeeNum` (email) bo'yicha keladi; snapshot paytida u tizim
    foydalanuvchisining `crm_external_id`i orqali `crm_visit_external_id`iga
    (`responsibleById`) o'giriladi — shunda qo'ng'iroqlar lid bosqichlari bilan bir xil
    operator qatoriga tushadi. Bog'lanmagan `employeeNum`lar `responsible_id=0`
    ("Boshqa") ostida jamlanadi (tashkilot jami to'g'ri bo'lishi uchun)."""

    __tablename__ = "operator_calls_daily"
    __table_args__ = (UniqueConstraint("date", "responsible_id", name="uq_operator_calls_daily_grain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    responsible_id: Mapped[int] = mapped_column(Integer)  # 0 = bog'lanmagan (Boshqa)
    responsible_name: Mapped[str] = mapped_column(String(255))
    calls_in: Mapped[int] = mapped_column(Integer, default=0)
    calls_out: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CrmLeadState(Base):
    """CRM (Uysot) lidining OXIRGI KO'RILGAN holati — diff-engine xotirasi.

    CRM ochiq API'sida bosqich-o'tish tarixi (event log) yo'q, faqat joriy holat
    va `updatedTimestamp` (istalgan tahrir, "bosqichga o'tish" voqeasi emas).
    Shuning uchun har skanerlashda joriy holatni shu yerdagi OLDINGI holat bilan
    solishtirib, HAQIQIY o'zgarishni (`LeadEvent`) o'zimiz aniqlaymiz — CRM'ning
    o'zi voqea bermasa ham (`api/services/lead_diff.py`)."""

    __tablename__ = "crm_lead_state"

    crm_lead_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipe_status_id: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(255))
    responsible_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    responsible_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Lidga birinchi marta duch kelganimizda ko'rilgan mas'ul — keyinchalik
    # o'zgarmaydi. "Kim olib kelgan" (asl operator) signalini bosqichlar orasidagi
    # bo'shliqsiz saqlaydi (masalan operator→manager tashrif kreditlash uchun).
    first_responsible_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crm_updated_ts: Mapped[int] = mapped_column(Integer)
    # Lid CRM'DA yaratilgan vaqt (`createdTimestamp`). Voronka KOGORTASI aynan
    # shunga tayanadi: «avgustda kelgan lid» — bizning skanerimiz uni qachon
    # ko'rgani emas, CRM'da qachon paydo bo'lgani. `first_seen_at` zaxira
    # sifatida qoladi (eski qatorlarda bu ustun NULL — skaner ishga tushgan
    # kunda mavjud bo'lgan lidlarning yaratilish vaqti bizda yo'q).
    crm_created_ts: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # ── Lid manbai (voronka 2-bosqichi) ──
    # `tags` — CRM teglari (masalan ["#telegram", "#Webinar_15_aprel"]). Ommaviy
    # skanerda BEPUL keladi, shuning uchun asosiy kanal signali shu: kampaniya
    # nomi ham, kanal ham teglarda uchraydi.
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # `source` — attribution kanali (`MOI_ZVONKI`, `FACEBOOK_FORM`...). Ommaviy
    # javobda YO'Q, faqat `/lead/{id}` detalida — ya'ni har lid uchun alohida
    # so'rov. Shuning uchun byudjetli boyituvchi (`lead_source.py`) sekin-asta
    # to'ldiradi; NULL = hali so'ralmagan.
    source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Manba so'ralgan vaqt — qayta so'ramaslik uchun (manba topilmasa ham
    # belgilanadi, aks holda bir xil lidga cheksiz so'rov ketardi).
    source_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeadEvent(Base):
    """CRM lidining HAQIQIY holat o'zgarishi — diff-engine (`lead_diff.py`)
    tomonidan `CrmLeadState`dagi oldingi holat bilan solishtirib aniqlangan.
    Kunlik statistika (guruh digesti) shu jadvaldan hisoblanadi —
    `updatedTimestamp`ga asoslangan taxminiy hisobdan farqli, aniq "qachon,
    qaysi bosqichdan qaysi bosqichga, kimdan kimga o'tdi" voqeasi.

    `detected_at` — bizning tizim buni PAYQAGAN vaqt. Kunlik kesimda voqea kuni
    endi `crm_updated_ts` (CRM'ning o'z vaqti, bosqich o'tishida yangilanadi)
    bo'yicha olinadi, `detected_at` faqat zaxira (`lead_diff._event_effective_utc`)
    — skan kechikkanda (uzilish, tungi to'liq skan) tashrif noto'g'ri kunga
    yozilmasligi uchun (2026-08-03 tuzatishi)."""

    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crm_lead_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)  # stage_change | responsible_change
    from_pipe_status_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_stage_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_pipe_status_id: Mapped[int] = mapped_column(Integer)
    to_stage_name: Mapped[str] = mapped_column(String(255))
    from_responsible_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_responsible_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_responsible_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # CrmLeadState.first_responsible_id'dan shu voqea yozilgan paytdagi nusxa —
    # keyinchalik "operator olib kelgan, manager tashrifga o'tkazgan" kabi
    # kreditlash uchun qayta CRM'ga/State'ga murojaat qilmasdan o'qiladi.
    first_responsible_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crm_updated_ts: Mapped[int] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HourlyActual(Base):
    """Operator AI — operatorning bir kundagi bir soatlik haqiqiy natijasi (CRM
    call-history'dan kompozit sifat bilan). Ham real-vaqt "actual" (bugungi kun),
    ham tarixiy manba (`OperatorProfile` shu jadvaldan 30 kunlik baseline hisoblaydi).

    `user_id` — tizim foydalanuvchisi (`employeeNum`/email → `User.crm_external_id`
    orqali bog'lanadi; bog'lanmagan qo'ng'iroqlar bu jadvalga yozilmaydi, chunki reja
    faqat tizimdagi operatorlar uchun). Grain: (user_id, date, hour)."""

    __tablename__ = "hourly_actual"
    __table_args__ = (UniqueConstraint("user_id", "date", "hour", name="uq_hourly_actual_grain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    hour: Mapped[int] = mapped_column(Integer)  # 0–23, Asia/Tashkent
    calls: Mapped[int] = mapped_column(Integer, default=0)
    calls_in: Mapped[int] = mapped_column(Integer, default=0)
    calls_out: Mapped[int] = mapped_column(Integer, default=0)
    answered: Mapped[int] = mapped_column(Integer, default=0)  # missed==False
    talk_sec: Mapped[int] = mapped_column(Integer, default=0)  # jami suhbat sekundi (javob berilganlar)
    short_calls: Mapped[int] = mapped_column(Integer, default=0)  # javob berilgan, lekin < SHORT_CALL_SECONDS
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperatorProfile(Base):
    """Operator AI — operatorning soatlik "odatiy tempi" (oxirgi ~30 kun `HourlyActual`
    dan hisoblangan, haftada yangilanadi). Bu TAVSIFIY (operator odatda nima qiladi) —
    jamoa benchmarki va stretch reja tuzishda (`hourly_target`) qo'shiladi, bu yerda
    saqlanmaydi. Grain: (user_id, hour)."""

    __tablename__ = "operator_profile"
    __table_args__ = (UniqueConstraint("user_id", "hour", name="uq_operator_profile_grain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    hour: Mapped[int] = mapped_column(Integer)  # 0–23
    baseline_calls: Mapped[int] = mapped_column(Integer, default=0)  # shu soatdagi odatiy qo'ng'iroq (median)
    baseline_answered: Mapped[int] = mapped_column(Integer, default=0)
    baseline_talk_sec: Mapped[int] = mapped_column(Integer, default=0)  # odatiy jami suhbat sekundi
    sample_days: Mapped[int] = mapped_column(Integer, default=0)  # necha kunlik data qatnashgani (ishonch darajasi)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HourlyTarget(Base):
    """Operator AI — operatorga bir kun uchun tuzilgan soatlik reja (BUYRUQ: nima
    qilinishi kerak). `OperatorProfile` (o'z imkoniyati) + jamoa benchmarki + kichik
    stretch'dan tuziladi, ish jadvali oynasiga moslanadi (tushlik/dam chiqariladi).
    Kechasi tuziladi va kun davomida o'zgarmaydi (kuzatuv shu barqaror rejaga
    solishtiradi). Grain: (user_id, date, hour)."""

    __tablename__ = "hourly_target"
    __table_args__ = (UniqueConstraint("user_id", "date", "hour", name="uq_hourly_target_grain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    hour: Mapped[int] = mapped_column(Integer)  # 0–23
    target_calls: Mapped[int] = mapped_column(Integer, default=0)
    target_answered: Mapped[int] = mapped_column(Integer, default=0)
    target_talk_sec: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiConfig(Base):
    """Operator AI ish vaqtida (runtime) rahbar boshqaradigan sozlamalar (yagona
    qator, id=1). Env bayroqlari (AI_ENABLED, AI_NUDGE_ENABLED) deploy darajasidagi
    bosh kalit; bu jadval esa boss botdan turib alohida qismlarni yoqib-o'chirishi
    uchun — ikkalasi HAM yoqiq bo'lsagina yuboriladi."""

    __tablename__ = "ai_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # doim 1
    nudges_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    group_summary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weekly_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hot_leads_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Real-vaqtli harakatsizlik nazorati (4-band, idle_watch.py) — soatlik shaxsiy
    # nudge'dan ALOHIDA bayroq (ommaviy/guruh xabari, tezroq va qattiqroq signal).
    idle_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    summary_hour: Mapped[int] = mapped_column(Integer, default=19)
    summary_minute: Mapped[int] = mapped_column(Integer, default=0)
    # Bir kunda/haftada ikki marta yubormaslik qo'riqchilari
    summary_last_posted: Mapped[date | None] = mapped_column(Date, nullable=True)
    weekly_last_posted: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ShortfallReason(Base):
    """Operator AI — reja ortda qolganda operatordan yig'ilgan sabab. Nudge yuborilganda
    kutish (pending) yozuvi ochiladi (`reason` NULL); operator sababini ERKIN MATN bilan
    botga yozadi, AI matnni tasniflaydi (`ai_category`) va tekshiriladigan da'volarni
    kod/CRM tasdiqlaydi (`verified`): "lid tugadi" → CRM'dagi ochiq lidlar,
    "ko'tarmadi" → terilgan raqamlar soni. Sabablar jamlanib rahbarga tizimli xulosa
    beriladi va zid chiqqan da'vo rahbarga darhol ko'rinadi (aldashning oldi olinadi).

    Grain: (user_id, date, hour) — bir soatga bitta sabab (qayta yozilsa yangilanadi)."""

    __tablename__ = "shortfall_reason"
    __table_args__ = (UniqueConstraint("user_id", "date", "hour", name="uq_shortfall_reason_grain"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    hour: Mapped[int] = mapped_column(Integer)  # sabab so'ralgan soat (0-23)
    # Yakuniy yorliq ("Lid/baza tugadi"). NULL — operator javobi hali kutilmoqda (pending).
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # operatorning o'z so'zlari
    ai_category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # no_answer|no_base|tech|meeting|other
    # True — da'vo tekshiruvda tasdiqlandi; False — faktlarga ZID (ehtimoliy aldash);
    # NULL — tekshirib bo'lmaydi (yig'ilish kabi) yoki CRM javob bermadi.
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verify_note: Mapped[str | None] = mapped_column(String(255), nullable=True)  # tekshiruv fakti ("CRM: 42 ta ochiq lid")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AiMessageLog(Base):
    """Operator AI — Claude (yoki fallback) yozgan har bir matn. Audit va xotira:
    keyingi murojaatlarda "kecha shu soatda past eding" kabi trendni eslash uchun
    saqlanadi. `context` — Claude'ga berilgan agregat kirish (PII yo'q), qayta
    tekshirish uchun."""

    __tablename__ = "ai_message_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # nudge | group_summary | weekly
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai | fallback
    text: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # agregat kirish (PII yo'q)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HotLead(Base):
    """Operator AI — issiq lid (speed-to-lead, 5-bosqich). CRM'da yangi yaratilgan
    lid aniqlanishi bilan CRM tayinlagan operatorga darhol xabar beriladi va javob
    tezligi o'lchanadi. Uch vaqt farqi metrika beradi: lid yaratilishi → aniqlash
    (tizim tezligi), aniqlash → qabul (operator reaksiyasi), yaratilish → birinchi
    aloqa qo'ng'irog'i (haqiqiy speed-to-lead, call-history phoneSearch'dan;
    chiquvchi urinish yoki kiruvchi javob berilgan qo'ng'iroq sanaladi).

    `status`: baseline (tizim yoqilganda mavjud bo'lgan eski lid — kuzatilmaydi) |
    notified (operatorga yuborildi) | claimed (operator qabul qildi) | called
    (birinchi qo'ng'iroq qayd etildi — yakuniy). Taqsimotni CRM o'zi qiladi
    (`responsibleById`), biz uni buzmaymiz — faqat tezlik va javobgarlik qatlami."""

    __tablename__ = "hot_lead"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crm_lead_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    lead_name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # CRM "#8323326"
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 128: jonli CRM'da bir nechta raqam qo'shilib kelgan holatlar bor (65+ belgi);
    # SQLite uzunlikni tekshirmasdi, PostgreSQL esa qat'iy (PG'ga ko'chirishda topildi)
    phone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Mijozning BARCHA ma'lum kontakt raqamlari (CRM ko'pincha bir nechtasini beradi) —
    # qo'ng'iroq tekshiruvi faqat `phone`ga emas, shu ro'yxatning hammasiga qaraydi
    # (operator ikkinchi raqamga qo'ng'iroq qilgan bo'lishi mumkin).
    phones: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # FACEBOOK_FORM ...
    responsible_crm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # responsibleById (JORIY)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_ts: Mapped[int] = mapped_column(Integer)  # CRM createdTimestamp (unix sekund)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_call_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lid yaratilishidan birinchi aloqa qo'ng'irog'igacha sekund (speed-to-lead)
    first_call_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Shu lid uchun oxirgi marta qo'ng'iroq TEKSHIRILGAN payt (topilmagan bo'lsa ham) —
    # eskalatsiya navbatda hali tekshirilmagan lidni "kechikdi" deb yolg'on
    # aniqlamasligi uchun (backlog holatida poyga himoyasi).
    last_call_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Eskalatsiyadan KEYIN qo'ng'iroq/qonuniy yopilish topilsa, guruhga tuzatuvchi
    # xabar shu qo'riqchi bilan bir marta yuboriladi.
    correction_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # CRM'da mas'ul boshqa operatorga o'tkazilgani aniqlangan payt (diff-engine
    # CrmLeadState orqali) — aniqlansa `responsible_crm_id`/`user_id` YANGI
    # mas'ulga ko'chiriladi, eski operator endi ayblanmaydi.
    reassigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lid qo'ng'iroqsiz, lekin QONUNIY sabab bilan yopilgan bo'lsa (spam/dublikat/
    # noto'g'ri raqam — terminal bosqich), shu bosqich nomi — eskalatsiya to'xtaydi.
    resolved_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # baseline | notified | claimed | called | resolved_no_call
    status: Mapped[str] = mapped_column(String(16), default="notified", index=True)
    # ── Bosqichma-bosqich eslatmalar (egasining talabi 2026-08-06) ──
    # Operatorga 3/5/7/9-daqiqada shaxsiy ogohlantirish yuboriladi; bu yerda
    # OXIRGI yuborilgan bosqich (daqiqa) saqlanadi — tick qayta ishlaganda
    # o'sha eslatma ikkinchi marta ketmasin.
    last_reminder_minute: Mapped[int] = mapped_column(Integer, default=0)
    # Sovutish e'lon qilingan paytdagi jarima summasi (FinePolicy'dan olingan
    # nusxa) — keyin HR summani o'zgartirsa, o'tmishdagi e'lon o'zgarmasin.
    fine_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)


class WorkScheduleWeekly(Base):
    """Xodimning haftalik takrorlanuvchi ish jadvali andozasi — hafta kuni bo'yicha
    (0=Dushanba ... 6=Yakshanba). `is_working=False` — dam olish kuni. Vaqtlar "HH:MM"
    matn ko'rinishida. Aniq sana uchun `WorkScheduleOverride` ustun keladi."""

    __tablename__ = "work_schedule_weekly"
    __table_args__ = (UniqueConstraint("user_id", "weekday", name="uq_work_schedule_weekly"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Dush ... 6=Yak
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "09:00"
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "18:00"
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkScheduleOverride(Base):
    """Aniq sana uchun ish jadvali o'zgartirishi — haftalik andozadan ustun turadi
    (bayram, almashtirilgan smena va h.k.). `is_working=False` — o'sha kuni dam olish."""

    __tablename__ = "work_schedule_override"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_work_schedule_override"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ariza materializatsiyasi izi — `ExcusedDay.source_request_id` bilan
    # bir xil maqsad (bekor qilishda qaytarish).
    source_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_requests.id"), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GroupPostConfig(Base):
    """Guruhga kunlik lid statistikasini yuborish sozlamasi (yagona qator, id=1).
    Boss vaqtni o'zgartira oladi; scheduler har daqiqa tekshiradi va shu vaqt kelganда
    yuboradi. `last_posted_date` — bir kunda ikki marta yubormaslik uchun qo'riqchi.

    `last_posted_*` jami raqamlar — kechqurungi avtomatik digest yuborilgan paytdagi
    holat: ma'lumot 23:57 gacha yangilanib boradi, ertasi 09:00 dagi "kecha yakuni"
    tuzatish xabari yakuniy raqamlarni aynan shu saqlangan sonlar bilan solishtiradi.
    `correction_last_posted` — tuzatish xabarining bir-kunda-bir-marta qo'riqchisi."""

    __tablename__ = "group_post_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # doim 1
    post_hour: Mapped[int] = mapped_column(Integer, default=19)
    post_minute: Mapped[int] = mapped_column(Integer, default=10)
    last_posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_posted_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_posted_leads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_posted_visits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_posted_contracts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correction_last_posted: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OfficeLocation(Base):
    """Ofis joyi — kelib-ketish (davomat) GPS tekshiruvi uchun markaz + radius.
    Xodim check-in/out qilganda joylashuvi FAOL ofislardan biriga (radius ichida)
    tushishi shart; bir nechta ofis bo'lsa eng yaqini olinadi. verifix (hodim_crm)
    `OfficeLocation` modelidan yagona backendga birlashtirildi."""

    __tablename__ = "office_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6))
    radius_meters: Mapped[int] = mapped_column(Integer, default=150)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Attendance(Base):
    """Bir kunlik davomat yozuvi (bitta xodim, bitta sana). `late_minutes`,
    `early_leave_minutes`, `worked_minutes`, `status` check-in/out vaqtlari va
    xodimning o'sha kungi ish jadvali (WorkScheduleWeekly/Override) asosida
    hisoblanadi (api/services/attendance.py). verifix (hodim_crm) `Attendance`
    modelidan yagona backendga birlashtirildi; kechikish alohida `Shift` emas,
    mavjud ish jadvali oynasidan hisoblanadi."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_attendance_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)

    check_in_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_in_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_in_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_in_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)

    check_out_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out_lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    check_out_lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default=AttendanceStatus.present.value, index=True)
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AttendanceReminder(Base):
    """«Keldim/Ketdim bosishni unutmang» eslatmasi YUBORILGANINING izi.

    Nega alohida jadval kerak: eslatma tick'i har ~5 daqiqada ishlaydi, ya'ni
    ish oynasi boshlanishiga 15 daqiqa qolganda TRIGGER shart bir necha marta
    rost bo'ladi. Iz bo'lmasa xodim bitta ertalab 3-4 marta bir xil xabar
    olardi va eslatmani butunlay o'chirib qo'yardi.

    Nega `Attendance` yozuvining o'ziga bayroq qo'yilmadi: eslatma aynan
    check-in HALI YO'Q paytda yuboriladi — o'sha payt `Attendance` qatori
    umuman mavjud bo'lmasligi mumkin (xodim hech narsa bosmagan).

    `kind`: "<check_in|check_out>_<offset>" — masalan "check_in_10",
    "check_out_0". Offset = ish oynasigacha qolgan daqiqa (10 / 5 / 0), ya'ni
    bir kunda bir xodimga oltita alohida iz tushishi mumkin. Ilgari faqat
    "check_in"/"check_out" edi va bitta eslatma yuborilardi."""

    __tablename__ = "attendance_reminders"
    __table_args__ = (UniqueConstraint("user_id", "date", "kind", name="uq_att_reminder_user_date_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    # 20: "check_out_10" 12 belgi — eski String(10) ga SIG'MASDI (PostgreSQL
    # varchar uzunligini qat'iy tekshiradi, SQLite esa jimgina qabul qiladi).
    kind: Mapped[str] = mapped_column(String(20))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExplanationStatus(str, enum.Enum):
    pending = "pending"      # so'raldi, xodim hali javob yozmagan
    answered = "answered"    # xodim javob yozdi, HR qarori kutilmoqda
    accepted = "accepted"    # HR sababli deb qabul qildi -> ExcusedDay yaratiladi
    rejected = "rejected"    # HR rad etdi -> jarima o'z kuchida qoladi


class ExplanationRequest(Base):
    """Sababsiz kelmagan kun uchun TUSHUNTIRISH XATI so'rovi.

    Egasining talabi: "agar sababsiz bo'lsa tushuntirish xati olinadi, agar
    sababli bo'lsa hr o'zi kiritadigan funksiya ham kerak".

    ⚠️ MAVJUD JARIMA MANTIQIGA TEGMAYDI — bu ustiga qo'shiladigan QATLAM.
    Kun `absent` bo'lib qolaveradi va jarima o'z kuchida turadi; faqat HR
    "sababli" deb qabul qilsa, MAVJUD `ExcusedDay` mexanizmi orqali kun
    sababliga aylanadi va jarima o'z-o'zidan tushadi. Yangi jarima yo'li
    YARATILMAYDI — aks holda ikkita mustaqil hisob paydo bo'lardi.

    Bir kunga bitta so'rov: UNIQUE(user_id, date) — kechqurungi job bir necha
    marta ishlasa ham (yoki qo'lda qayta chaqirilsa) takror so'ralmaydi."""

    __tablename__ = "explanation_requests"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_explanation_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(20), default=ExplanationStatus.pending.value, index=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppealKind(str, enum.Enum):
    objection = "objection"  # e'tiroz — ANIQ qarorga qarshi (davomat kuni, oylik)
    complaint = "complaint"  # shikoyat — erkin mavzu


class AppealTopic(str, enum.Enum):
    attendance = "attendance"  # davomat kuni / kechikish jarimasi (objection)
    payroll = "payroll"  # oylik varaqasi / hisob (objection)
    work_env = "work_env"  # ish sharoiti (complaint)
    team = "team"  # jamoa/munosabatlar (complaint)
    other = "other"


class AppealStatus(str, enum.Enum):
    pending = "pending"  # yangi, hali ochilmagan
    in_review = "in_review"  # qabul qiluvchi "o'rganyapman" dedi
    accepted = "accepted"  # e'tiroz qondirildi
    rejected = "rejected"  # rad etildi (izoh majburiy)
    resolved = "resolved"  # shikoyat hal qilindi (izoh majburiy)


# Hali yopilmagan murojaatlar — SLA tick va spam limiti shu ikkitasini sanaydi.
APPEAL_OPEN_STATUSES = (AppealStatus.pending.value, AppealStatus.in_review.value)


class Appeal(Base):
    """Xodim murojaati: e'tiroz (aniq qarorga qarshi) yoki shikoyat (erkin mavzu).

    ⚠️ ENG MUHIM TAMOYIL (`ExplanationRequest`dan meros, models.py:938-942):
    BU JADVAL HECH NARSANI HISOBLAMAYDI. `accepted` bo'lganda davomat yoki pul
    tuzatish FAQAT MAVJUD mexanizmlar orqali bajariladi — davomat uchun
    `ExcusedDay` (+ `recompute_attendance`), oylik uchun `PayrollAdjustment`
    (davr qulf bo'lsa Dasturchi `admin_override` bilan ochadi). Aks holda
    ikkita mustaqil hisob yo'li paydo bo'lardi va payslip raqami qaysi
    yo'ldan kelganini hech kim ayta olmasdi.

    Shuning uchun qaror qabul qilinganda API faqat XABAR beradi ("endi
    tuzatishni kiriting") — avtomatik hech nima o'zgartirmaydi.

    MAXFIYLIK: `recipient_role` — shikoyat KIMGA yuborilgani (hr yoki boss).
    Shikoyat HR haqida bo'lishi mumkin, shuning uchun HR faqat O'ZIGA
    yuborilganlarini ko'radi; Boshliq va Dasturchi hammasini ko'radi
    (`api/routers/appeals.py: _can_access`).

    ANONIMLIK: `is_anonymous` faqat shikoyatda. Bazada `user_id` HAR DOIM
    saqlanadi (suiiste'molni tekshirish uchun), lekin API javobida ism
    yashiriladi — yashirish BACKENDDA, frontendda emas."""

    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), index=True)
    topic: Mapped[str] = mapped_column(String(12), default=AppealTopic.other.value)
    text: Mapped[str] = mapped_column(Text)  # 10..3000 belgi (sxema tekshiradi)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    recipient_role: Mapped[str] = mapped_column(String(10), default=Role.hr.value)

    # E'tiroz manzili — qabul qiluvchi kontekstni bir qarashda ko'rsin.
    ref_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # davomat kuni
    ref_period: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "YYYY-MM" payslip

    # Telegram ilovasi (ixtiyoriy): rasm yoki hujjat. Faylning O'ZI saqlanmaydi —
    # faqat Telegram `file_id`, botda shu bilan qayta yuboriladi.
    file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # photo | document

    status: Mapped[str] = mapped_column(String(12), default=AppealStatus.pending.value, index=True)
    review_started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SLA izlari — eslatma/eskalatsiya BIR MARTA ketishi uchun (cPanel'da cron
    # ikki jarayonda ishlashi mumkin; alohida jadval o'rniga shu ikki ustun).
    sla_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RequestKind(str, enum.Enum):
    """Ariza turi. Guruhlari — TASDIQLANGANDA nima bo'lishi bo'yicha
    (ARIZALAR_REJASI.md 3.1): bu modulning markaziy g'oyasi."""

    # A guruh — davomatga yoziladi (ExcusedDay qatorlari)
    vacation = "vacation"  # mehnat ta'tili (to'lovli)
    unpaid = "unpaid"  # o'z hisobidan (to'lovsiz)
    sick = "sick"  # kasallik
    # B guruh — pulga yoziladi (PayrollAdjustment)
    advance = "advance"  # avans
    # C guruh — tizim hech nima yozmaydi, HR qo'lda bajaradi
    certificate = "certificate"  # ma'lumotnoma
    schedule_change = "schedule_change"  # ish jadvalini o'zgartirish
    resignation = "resignation"  # ishdan bo'shash
    other = "other"


# Guruhlar — `_apply` shu ro'yxatlarga qarab ish tutadi.
LEAVE_KINDS = (RequestKind.vacation.value, RequestKind.unpaid.value, RequestKind.sick.value)
MONEY_KINDS = (RequestKind.advance.value,)
# To'lovsiz yagona tur — `ExcusedDay.is_paid=False` bilan yoziladi.
UNPAID_KINDS = (RequestKind.unpaid.value,)


class RequestStatus(str, enum.Enum):
    pending = "pending"  # yangi, qaror kutilmoqda
    manager_ok = "manager_ok"  # ROP tasdiqladi, HR kutilmoqda (Bosqich 4)
    hr_ok = "hr_ok"  # HR tasdiqladi, Boshliq kutilmoqda (chegaradan oshgan)
    approved = "approved"  # tasdiqlandi VA materializatsiya qilindi
    rejected = "rejected"
    cancelled = "cancelled"  # xodim o'zi qaytarib oldi (qarordan OLDIN)
    revoked = "revoked"  # tasdiqlangach bekor qilindi (yozuvlar qaytarildi)


# Hali yopilmagan arizalar — SLA tick, spam limiti va to'qnashuv tekshiruvi
# shu ikkitasini sanaydi.
REQUEST_OPEN_STATUSES = (
    RequestStatus.pending.value,
    RequestStatus.manager_ok.value,
    RequestStatus.hr_ok.value,
)


class EmployeeRequest(Base):
    """Xodim arizasi — KELAJAKKA qaratilgan so'rov (ARIZALAR_REJASI.md).

    `Appeal` dan TUB FARQI (models.py izohiga qarang): u ataylab hech narsani
    hisoblamaydi, bu esa tasdiqlanganda REAL o'zgarish YOZADI —
    ta'til `ExcusedDay` qatorlariga, avans `PayrollAdjustment` ga aylanadi.

    QAYTARISH: yozilgan qatorlar arizaga TESKARI bog'langan
    (`source_request_id`) — bekor qilinganda aynan shular topib qaytariladi.
    JSON ro'yxat saqlashdan farqi: «bu sababli kun qayerdan paydo bo'lgan?»
    degan teskari savolga ham javob beradi va yetim qator qolmaydi.

    MAYDONLAR: `start_date`/`end_date`/`amount` — ALOHIDA ustun (JSON'da emas),
    chunki ular QIDIRILADI: to'qnashuv tekshiruvi, avans chegarasi, ta'til
    balansi — uchalasi ham shu maydonlar bo'yicha filtrlaydi va JSON ichida
    indeks bo'lmaydi. `payload` esa faqat qidirilmaydigan, turga xos
    qo'shimchalar uchun (ma'lumotnoma maqsadi, jadval o'zgartirish tafsiloti).
    """

    __tablename__ = "employee_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)

    # ── Qidiriladigan maydonlar ──
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # ── Turga xos, qidirilmaydigan qo'shimchalar ──
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    reason: Mapped[str] = mapped_column(Text)  # 10..2000 (sxema tekshiradi)
    file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=RequestStatus.pending.value, index=True)

    # ⭐ Bosqich 4 (zanjir) uchun joy — hozircha to'ldirilmaydi.
    manager_id_at_creation: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    manager_decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    manager_decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Materializatsiya vaqti — `approved` bo'lgan, lekin yozuvlar hali
    # yaratilmagan holat bo'lmasligi kerak; NULL bo'lsa nimadir noto'g'ri.
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ⭐ Bosqich 5: ta'til vaqtida ishga kelish izi.
    interrupted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interrupt_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    sla_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RequestPolicy(Base):
    """Ariza tasdiqlash qoidasi — `FinePolicy` scoping naqshida
    (ARIZALAR_REJASI.md 3.6/3: yangi «Global Settings» dvigateli qurish
    shart emas, loyihada tayyor naqsh bor).

    Prioritet: user > position > global (`resolve_request_policy`). Ya'ni HR
    keyinchalik «rahbarlarga 30 kun, qolganlarga 21» desa yangi kod kerak
    bo'lmaydi.

    ZANJIR ATAYLAB SODDA: taklif qilingan «ixtiyoriy tasdiqlovchilar
    ketma-ketligi» ortiqcha — amalda ikki naqsh bor (ROP→HR va
    ROP→HR→Boshliq), ularni ikki maydon qoplaydi. 8-50 kishilik
    kompaniyada undan murakkabrog'i sozlanmaydi, lekin
    qo'llab-quvvatlash xarajati doimiy bo'lib qolardi."""

    __tablename__ = "request_policies"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "kind", name="uq_request_policy_scope_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # global | position | user (FinePolicyScope bilan bir xil qiymatlar)
    scope: Mapped[str] = mapped_column(String(20), default=FinePolicyScope.global_.value)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL — barcha turlar uchun; aks holda aniq tur (`RequestKind`)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Bevosita rahbar (`User.manager_id`) tasdig'i kerakmi. Xodimda
    # `manager_id` bo'lmasa bosqich baribir o'tkazib yuboriladi.
    requires_manager: Mapped[bool] = mapped_column(Boolean, default=True)
    # Shu KUNDAN oshsa Boshliq ham tasdiqlashi kerak (ta'til turlari uchun).
    boss_threshold_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Shu SUMMADAN oshsa Boshliq ham (avans uchun).
    boss_threshold_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class FsmState(Base):
    """Bot FSM holati — cPanel (webhook) rejimida XOTIRA O'RNIGA bazada.

    Passenger ishchi jarayonni harakatsizlikdan keyin o'chirib/qayta ochadi va
    bir nechta ishchi ochishi mumkin — MemoryStorage'dagi holat yo'qolib, ko'p
    bosqichli oqimlar (javob tahriri, ma'lumot qo'shish, vaqt kiritish, Sotuv AI
    rejimi...) o'rtasida uzilib qolardi (jonli bug: rahbar javob yozganda bot
    "unutib" qo'ygan). Docker/polling rejimida ishlatilmaydi (u yerda bitta
    doimiy jarayon, MemoryStorage yetarli)."""

    __tablename__ = "fsm_states"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # bot:chat:user:destiny
    state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class KnowledgeStatus(str, enum.Enum):
    draft = "draft"  # anketadan yaratilgan, AI ishlovi kutilmoqda (cron tick)
    unverified = "unverified"  # AI ishlagan, rahbar tasdig'i kutilmoqda
    unknown = "unknown"  # javob yo'q/taxminiy — "bilim bo'shlig'i"
    conflict = "conflict"  # xodimlar javoblari zid — rahbar hal qiladi
    verified = "verified"  # tasdiqlangan — sotuv AI'ga faqat shular beriladi


class KnowledgeEntry(Base):
    """Sotuv bilim bazasi yozuvi (savol → rasmiy javob).

    Manba: anketa javoblari (ingest → draft → AI ishlovi → unverified/unknown/
    conflict → rahbar tasdig'i → verified) yoki qo'lda kiritilgan yozuv (darhol
    verified). `kind`: single — oddiy savol-javob; common — A qism (5 xodimda bir
    xil savol, AI birlashtiradi, `group_key` bilan guruhlangan); open — C qism
    ochiq javobi (AI alohida savol-javob juftlarga ajratadi, keyin o'chiriladi).
    `date_sensitive` yozuvlar 30 kundan eskirsa `needs_recheck` belgilanadi."""

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), default="single")  # single|common|open
    #  ⚠️ QAMROV — MAXFIYLIK CHEGARASI, bezak emas (S-29).
    #  `sales` yozuvlar MIJOZGA ko'rinadi: ular Sotuv AI promptiga va
    #  TASHQI chatbot datasetiga (`build_dataset`) tushadi. `hr` yozuvlar
    #  esa ichki (oylik, jarima, intizom) va u yerga TUSHMASLIGI SHART —
    #  aks holda xodimga aytilgan ichki qoida mijozga ketardi.
    audience: Mapped[str] = mapped_column(String(8), default="sales", index=True)
    group_key: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(30), default="umumiy")
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=KnowledgeStatus.draft.value, index=True)
    date_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_recheck: Mapped[bool] = mapped_column(Boolean, default=False)
    recheck_notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(255), default="")
    source_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("anketa_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    anketa_answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("anketa_answers.id", ondelete="SET NULL"), nullable=True
    )
    ai_attempts: Mapped[int] = mapped_column(Integer, default=0)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PlaybookBuild(Base):
    """Sotuv playbook qurish jarayoni — og'ir AI ishi cron tick'da bosqichma-bosqich
    boradi (cPanel gateway limiti): profiles (har sotuvchi uslubi, anketa
    javoblaridan) → objections (shortfall_reason erkin matnlaridan real mijoz
    e'tirozlari) → synthesis (yakuniy playbook yozuvlari, eng natijali sotuvchiga
    og'irlik berib) → done. Oraliq natijalar `data` JSON'ida to'planadi."""

    __tablename__ = "playbook_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="profiles", index=True)
    # {"targets": [...], "profiles": {...}, "objections": [...]}
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PlaybookEntry(Base):
    """Playbook yozuvi: vaziyat → texnika → xodimlarning namunaviy iboralari.
    `kind`: etiroz (e'tiroz bilan ishlash), uslub (ohang/uslub qoidasi), qoida
    (umumiy sotuv qoidasi, masalan tezlik). Sotuv AI (3-bosqich) faqat verified
    yozuvlardan foydalanadi — Boss tasdig'i shart."""

    __tablename__ = "playbook_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    build_id: Mapped[int | None] = mapped_column(
        ForeignKey("playbook_builds.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10), default="etiroz")  # etiroz|uslub|qoida
    situation: Mapped[str] = mapped_column(Text)
    technique: Mapped[str] = mapped_column(Text)
    phrases: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{"text","source"}]
    status: Mapped[str] = mapped_column(String(20), default="unverified", index=True)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AnketaSessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class AnketaTemplate(Base):
    """Word/matn faylidan yuklangan savol to'plami (Dasturchi botga .docx tashlaydi,
    api/services/docx_parse.py savollarni ajratadi). `questions` — [{"section",
    "text"}] ro'yxati, fayl o'zgarsa ham sessiya savollari shu yerda muzlatilgan
    holda qoladi. O'chirish YUMSHOQ (`is_active=False`) — o'tgan sessiyalarning
    savollari yo'qolmasligi uchun."""

    __tablename__ = "anketa_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255), default="")
    questions: Mapped[list] = mapped_column(JSON, default=list)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnketaSession(Base):
    """Bilim bazasi anketasi sessiyasi — Dasturchi bot orqali kun/vaqtni
    tasdiqlaganda yaratiladi; `scheduled_at` (naive UTC) yetganda tick uni
    boshlaydi (savollar xodimlarga botdan yuboriladi). Bir vaqtda faqat bitta
    faol (scheduled/in_progress) sessiya bo'lishi mumkin."""

    __tablename__ = "anketa_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)  # naive UTC
    status: Mapped[str] = mapped_column(
        String(20), default=AnketaSessionStatus.scheduled.value, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnketaAssignment(Base):
    """Bitta xodimga biriktirilgan bitta savol to'plami (1:1 — har to'plam
    sessiyada faqat bitta xodimga tushadi, UniqueConstraint bilan kafolatlanadi).
    `current_q` — keyingi yuboriladigan savolning 0-asosli indeksi; javoblar
    kelgani sari bittaga oshadi (savollar api/services/anketa_data.py'da)."""

    __tablename__ = "anketa_assignments"
    # Eslatma: ilgari (session_id, toplam) ham unique edi — qatnashchilar erkin
    # tanlanadigan bo'lgach (5 kishidan ko'p guruhda to'plamlar 1-5 aylanib
    # takrorlanadi) bu cheklov olib tashlandi (f2a3b4c5d6e7).
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_anketa_assignment_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("anketa_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Ichki (kodga yozilgan) to'plam raqami 1-5. Yuklangan Word to'plami
    # ishlatilsa `template_id` to'ldiriladi va bu maydon 0 bo'ladi.
    toplam: Mapped[int] = mapped_column(Integer)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("anketa_templates.id"), nullable=True, index=True
    )
    current_q: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|in_progress|done
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnketaAnswer(Base):
    """Xodimning bitta savolga javobi. `question_text` — javob paytidagi savol
    matni nusxasi (keyin to'plam o'zgarsa ham javob konteksti saqlanadi)."""

    __tablename__ = "anketa_answers"
    __table_args__ = (
        UniqueConstraint("assignment_id", "question_index", name="uq_anketa_answer_q"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("anketa_assignments.id", ondelete="CASCADE"), index=True
    )
    question_index: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Bilim bazasiga qachon yuklangani (NULL — hali yuklanmagan). Javob darajasida
    # kuzatiladi — tugallanmagan sessiyani qisman yuklash va keyin faqat yangi
    # javoblarni qo'shib yuklash uchun.
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AttendanceDigestConfig(Base):
    """Davomat digesti guruhga yuborish sozlamasi (yagona qator, id=1).
    Rahbar botdan (/davomat_vaqt) vaqtlarni o'zgartira oladi; cron har daqiqa
    tekshiradi va vaqt yetganда yuboradi. `*_last_posted` — bir kunda ikki marta
    yubormaslik uchun qo'riqchi (ertalabki va kechki alohida)."""

    __tablename__ = "attendance_digest_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # doim 1
    # 10:05 va 22:30 — egasining talabi (2026-08-04). Ilgari 09:30 / 22:00 edi.
    # DIQQAT: kechki vaqt shunchaki xabar emas — `write_absent_records` va
    # tushuntirish xatlari ham AYNI shu nuqtada ishga tushadi ("kun tugadi").
    morning_hour: Mapped[int] = mapped_column(Integer, default=10)
    morning_minute: Mapped[int] = mapped_column(Integer, default=5)
    evening_hour: Mapped[int] = mapped_column(Integer, default=22)
    evening_minute: Mapped[int] = mapped_column(Integer, default=30)
    morning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    evening_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    morning_last_posted: Mapped[date | None] = mapped_column(Date, nullable=True)
    evening_last_posted: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Kelmagan xodimlarga `absent` yozuvini yozish qo'riqchisi (evening_enabled'dan
    # MUSTAQIL — "xodim kelmadi" haqiqati bildirishnoma sozlamasiga bog'liq
    # bo'lmasligi kerak). Vaqti evening_hour/minute bilan bir xil ("kun tugadi").
    absent_marked_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MonitoredGroup(Base):
    """Bot kuzatadigan Telegram guruhlar — maqsad bo'yicha (`purpose`) ro'yxatga
    olinadi va dasturchi botdan (`/guruh_biriktir`) o'zgartira oladi, .env qayta
    ishga tushirish shart emas. "mobilograf" va "main" — bir vaqtda faqat bitta
    faol guruh (yangisi ro'yxatga olinsa eskisi is_active=False bo'ladi — "guruhni
    o'zgartirish" shunday ishlaydi); "stats" — bir nechtasi faol bo'lishi mumkin."""

    __tablename__ = "monitored_groups"
    __table_args__ = (UniqueConstraint("purpose", "chat_id", name="uq_monitored_group_purpose_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(30), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OperatorBusyPeriod(Base):
    """Boshliq/Dasturchi operator/managerni ma'lum vaqt oralig'ida "band" (yig'ilish,
    vazifa va h.k.) deb belgilaydi — real-vaqtli harakatsizlik nazorati
    (`api/services/idle_watch.py`) shu oraliqda ogohlantirish yubormaydi.
    `end_at` o'tib ketgan yozuvlar tekshiruvda avtomatik e'tiborsiz qoldiriladi
    (alohida tozalash job'i shart emas — sana bo'yicha filtrlanadi)."""

    __tablename__ = "operator_busy_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    set_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SalaryChangeReason(str, enum.Enum):
    """Ish haqi nega o'zgargani (yangi TZ 3.25 / S-25).

    NEGA MAJBURIY: stavka tarixi bor edi, lekin «nega?» degan savolga
    javob yo'q edi. Bir yildan keyin «bu odamga nega 20% qo'shgan
    edik?» degan savol javobsiz qolardi va keyingi qaror ham asossiz
    bo'lardi. Ro'yxat YOPIQ — erkin matn bo'lsa har kim boshqacha
    yozib, guruhlash va tahlil qilish imkonsiz bo'lardi."""

    periodic = "periodic"  # davriy oshirish
    position = "position"  # lavozim o'zgardi
    performance = "performance"  # natija bo'yicha
    market = "market"  # bozorga moslash
    hire = "hire"  # ishga qabul (dastlabki stavka)
    other = "other"  # boshqa — izohda tushuntiriladi


SALARY_CHANGE_REASON_LABELS: dict[str, str] = {
    SalaryChangeReason.periodic.value: "Davriy oshirish",
    SalaryChangeReason.position.value: "Lavozim o'zgardi",
    SalaryChangeReason.performance.value: "Natija bo'yicha",
    SalaryChangeReason.market.value: "Bozorga moslash",
    SalaryChangeReason.hire.value: "Ishga qabul",
    SalaryChangeReason.other.value: "Boshqa",
}


class SalaryRate(Base):
    """Xodimning oylik stavkasi — TARIXIY (`Norm` bilan bir xil naqsh:
    `effective_from`, hech qachon UPDATE qilinmaydi, faqat yangi qator
    qo'shiladi). Amaldagi stavka — `effective_from <= sana` bo'yicha eng
    so'nggisi. Shu tufayli oylik oshirilganda o'tgan oylar payslip'i
    buzilmaydi (ular allaqachon o'sha paytdagi stavka bilan hisoblangan)."""

    __tablename__ = "salary_rates"
    __table_args__ = (UniqueConstraint("user_id", "effective_from", name="uq_salary_rates_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    pay_basis: Mapped[str] = mapped_column(String(20), default=PayBasis.monthly.value)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    #  ⚠️ NEGA o'zgardi (yangi TZ 3.25 / S-25). Yangi qatorlarda
    #  MAJBURIY (API tekshiradi). ESKI qatorlarda NULL qoladi va
    #  interfeysda «kiritilmagan» deb ko'rsatiladi — migratsiya ularni
    #  taxmin bilan to'ldirmaydi, chunki noto'g'ri sabab yo'q sababdan
    #  yomonroq (u tahlilni buzadi).
    reason: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Bosqich 3.5 — `Norm` bilan bir xil yumshoq o'chirish naqshi.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class KpiRate(Base):
    """KPI (bonus) stavkasi — bitta ko'rsatkich birligi uchun necha so'm.

    NEGA KERAK (2026-08-08, egasining talabi "oylik stavkaga KPI stavka
    qilish"): ilgari stavkalar `api/services/bonus.py` da KONSTANTA edi
    (`PLACEHOLDER_RATE_PER_CONVERSATION = 2000` va h.k.). Oqibati:
      - HR stavkani saytdan o'zgartira olmasdi, har safar dasturchi + deploy;
      - stavka TARIXIY emasdi — o'zgartirilsa o'tgan oylar bonusi ham qayta
        hisoblanganda o'zgarib ketardi;
      - lavozimga qarab farqlanmasdi (sotuvchi va mobilograf bir xil).

    ARXITEKTURA: ikkita mavjud naqsh birlashtirildi —
      - `FinePolicy` dan: 3 DARAJALI qamrov (global -> lavozim -> xodim),
        `resolve_kpi_rate` xodim > lavozim > global tartibida qidiradi;
      - `SalaryRate` dan: TARIXIYLIK (`effective_from`, UPDATE qilinmaydi,
        faqat yangi qator qo'shiladi) — o'tgan oy payslip'i buzilmaydi.

    `metric` — `api/routers/norms.py::METRIC_LABELS` kalitlari: "suhbat",
    "tashrif", "oddiy_video", "dumaloq_video". Alohida jadval qilinmadi:
    metrikalar ro'yxati kod darajasida belgilangan va lavozimga biriktiriladi.

    Stavka topilmasa bonus o'sha ko'rsatkich uchun 0 — "sozlanmagan" holat
    xavfsiz tomonga og'adi (tasodifan pul yozilmasin)."""

    __tablename__ = "kpi_rates"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "metric", "effective_from", name="uq_kpi_rates_grain"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "global" | "position" | "user" — `FinePolicy.scope` bilan bir xil
    # so'zlar. `scope_id` polimorfik (positions.id yoki users.id), shuning
    # uchun FK YO'Q; "global"da NULL.
    scope: Mapped[str] = mapped_column(String(20), index=True)
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # `SalaryRate` bilan bir xil yumshoq o'chirish (Dasturchi rejimi).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class OvertimeProfile(Base):
    """Kimga qo'shimcha ish (overtime) yoqilgani va qanday hisoblanishi.
    `multiplier`da tizim darajasidagi default YO'Q (2026-07-27 QAROR,
    9-bo'lim savol 6) — `derived` rejimda HR MAJBURIY o'zi kiritadi.

    2026-08-15 (§3.2): IKKI DARAJALI bo'ldi — `scope='global'` (user_id NULL)
    barcha xodimga default, `scope='user'` esa uni bosadi
    (`resolve_overtime_profile`, `FinePolicy` naqshi bilan bir xil ruh).

    NEGA: ilgari profil faqat xodim bo'yicha edi va `enabled` default False —
    ya'ni HR har bir xodimga qo'lda profil ochmaguncha qo'shimcha ish UMUMAN
    hisoblanmasdi. Jonli bazada `enabled=true` profillar soni 0 edi, shu
    sababli «avtomat hisoblab bersin» talabi bajarilmayotgan edi. Global
    daraja bilan yangi ishga kirgan xodim ham o'z-o'zidan qamrab olinadi."""

    __tablename__ = "overtime_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # `scope='global'` bo'lsa NULL. Unikallik migratsiyadagi QISMAN
    # indekslar bilan ta'minlanadi (oddiy UNIQUE NULL'larni farqli sanaydi,
    # ya'ni bir nechta global qator sig'ib ketardi).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope: Mapped[str] = mapped_column(String(10), default="user", server_default="user")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Nomzod yaratilishi bilan `approved` bo'lsinmi. Default O'CHIQ —
    # tasdiqsiz pul payslip'ga kirmaydi (1.3-band).
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    mode: Mapped[str] = mapped_column(String(20), default=OvertimeMode.derived.value)
    fixed_rate_per_hour: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    multiplier: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    norm_hours_source: Mapped[str] = mapped_column(String(20), default=NormHoursSource.schedule.value)
    fixed_norm_hours_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_minutes: Mapped[int] = mapped_column(Integer, default=15)
    daily_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FinePolicy(Base):
    """Kechikish/kelmagan kun jarima qoidasi — 3 DARAJALI (global → lavozim →
    xodim). Amaldagisi: xodim > lavozim > global (`api/services/payroll.py`
    `resolve_policy`). `scope_id` polimorfik — `scope='position'` bo'lsa
    `positions.id`, `scope='user'` bo'lsa `users.id`ga ishora qiladi
    (shuning uchun FK YO'Q, oddiy Integer); `scope='global'`da NULL.

    2026-07-27 QARORLARI (9-bo'lim):
    - Limit FAQAT daqiqada (`free_late_minutes_per_month`) — kun bo'yicha
      limit (`free_late_days_per_month`) kod darajasida qoldirilgan, lekin
      hozircha ishlatilmaydi.
    - Limit tugagach — HAR bir keyingi kechikkan KUNGA `fine_per_day`
      (necha daqiqa kechikishidan qat'i nazar).
    - `fine_applies_to='net_salary'` — to'g'ridan-to'g'ri oylikdan (huquqiy
      eslatma: O'zbekiston mehnat qonunchiligida ish haqidan ushlab qolish
      cheklangan bo'lishi mumkin, HR/yurist tekshiruvi tavsiya etiladi).
    - `monthly_cap_percent`/`monthly_cap_amount` — MAJBURIY (ikkalasidan
      birortasi), qiymati tizimda qattiq kodlanmagan, HR web saytdan kiritadi.
    - `absent_mode='fixed'` — kelmagan kun uchun kunlik ulush emas, alohida
      qat'iy summa (`absent_fine`)."""

    __tablename__ = "fine_policies"
    __table_args__ = (UniqueConstraint("scope", "scope_id", name="uq_fine_policies_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grace_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_late_days_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ⭐ kelajakda
    free_late_minutes_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fine_mode: Mapped[str] = mapped_column(String(20), default=FineMode.per_day.value)
    fine_per_day: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fine_per_minute: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # ⭐ kelajakda
    tiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # ⭐ kelajakda
    percent_of_daily: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # ⭐ kelajakda
    absent_mode: Mapped[str] = mapped_column(String(20), default=AbsentMode.fixed.value)
    absent_fine: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    early_leave_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    early_leave_per_minute: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    monthly_cap_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    monthly_cap_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fine_applies_to: Mapped[str] = mapped_column(
        String(20), default=FineAppliesTo.bonus_first.value, server_default="bonus_first"
    )
    # Bonus ushlanmadan kam bo'lsa qoldiq nima bo'ladi — HR panelidan
    # tanlanadi. Default `drop`: ish haqiga UMUMAN tegilmaydi.
    fine_remainder_mode: Mapped[str] = mapped_column(
        String(20), default=FineRemainderMode.drop.value, server_default="drop"
    )
    # ── Issiq lid (speed-to-lead) qoidasi — egasining talabi 2026-08-06 ──
    # Lid CRM'da yaratilganidan keyin shuncha daqiqa ichida aloqa qo'ng'irog'i
    # bo'lmasa — lid "sovutilgan" hisoblanadi: guruhga chiqadi va shu summa
    # jarima sifatida e'lon qilinadi. Boshlang'ich: 10 daqiqa, jarima 0
    # (HR o'z panelidan o'zgartiradi — 0 bo'lsa xabarga summa yozilmaydi).
    hot_lead_cool_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hot_lead_fine: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    # ⚠️ Avans sozlamalari BU YERDA EMAS. A blokda ular vaqtincha shu
    # jadvalga qo'yilgan edi (yagona mavjud «HR paneli» jadvali edi),
    # B-01 da `advance_settings` ga ko'chirildi — jarima qoidasi bilan
    # avans qoidasi aralashmasin.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OvertimeEntry(Base):
    """Bir kunlik qo'shimcha ish yozuvi. `source='auto_attendance'` — check-out
    ish oynasi tugaganidan keyin bo'lganda avtomatik nomzod sifatida yaratiladi
    (`status='pending'`); `source='manual'` — HR/rahbar qo'lda kiritgan. HAR
    IKKALASI HAM tasdiqdan (`approved`) o'tmaguncha payslip hisobiga kirmaydi —
    tasdiqsiz pul hisoblanmaydi."""

    __tablename__ = "overtime_entries"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_overtime_entries_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default=OvertimeEntryStatus.pending.value, index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PayrollPeriod(Base):
    """Bir oylik payroll'ning umumiy holati (qulf). `locked=True` (odatda
    `status='approved'` yoki `'paid'` bilan birga) bo'lsa — shu davr uchun
    qayta hisoblash rad etiladi (409), faqat Dasturchi `reopen` orqali ochadi
    (Bosqich 3.5)."""

    __tablename__ = "payroll_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # "YYYY-MM"
    status: Mapped[str] = mapped_column(String(20), default=PayrollPeriodStatus.draft.value)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # HR bosqichi — "men tekshirdim, tayyor". Qulflamaydi, pul o'zgarmaydi.
    # Alohida ustunlar (audit yetarli emas): kim va qachon tayyorlaganini
    # Boshliq tasdiqlash oynasida DARHOL ko'rishi kerak.
    hr_approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    hr_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Yakuniy tasdiq — faqat Boshliq/Dasturchi, shu bilan `locked=True`.
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Fon rejimidagi hisoblash holati (2026-08-15, §4.3) ──
    # NEGA: production'da Passenger konkurentligi = 1. Hisoblash so'rov ichida
    # bajarilganda (~20 xodim × 12 SQL + har rahbarga Telegram/FCM) yagona
    # ishchi 10-40 soniya band bo'lib, BUTUN sayt navbatga tushardi. Endi
    # tugma faqat shu ustunlarni belgilaydi (yengil UPDATE), og'ir ishni esa
    # alohida cron JARAYONI bajaradi — Passenger'ga umuman tegmaydi.
    # `queued` → `running` → `done`/`error`.
    calc_state: Mapped[str] = mapped_column(String(10), default="idle", server_default="idle")
    calc_requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    calc_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    calc_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    calc_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    calc_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    calc_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Faqat tanlangan xodimlar so'ralgan bo'lsa — cron o'sha ro'yxatni bilishi
    # uchun saqlanadi (so'rov tugagach kontekst yo'qolmasin).
    calc_user_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)


class Payslip(Base):
    """Bir xodim, bir oy — to'liq hisob-kitob natijasi. `breakdown` (JSON) hisob
    paytidagi qoida/stavka SNAPSHOT'ini saqlaydi — keyin `FinePolicy`/
    `SalaryRate` o'zgarsa ham bu yozuv o'zgarmaydi (moliyaviy hujjat
    barqarorligi). Tafsilot qatorlari — `PayslipItem` (1:N)."""

    __tablename__ = "payslips"
    __table_args__ = (UniqueConstraint("user_id", "period", name="uq_payslips_user_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"

    base_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    pay_basis: Mapped[str] = mapped_column(String(20), default=PayBasis.monthly.value)
    rate_snapshot: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    scheduled_days: Mapped[int] = mapped_column(Integer, default=0)
    worked_days: Mapped[int] = mapped_column(Integer, default=0)
    absent_days: Mapped[int] = mapped_column(Integer, default=0)
    excused_days: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_minutes: Mapped[int] = mapped_column(Integer, default=0)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)

    late_days: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    fined_late_days: Mapped[int] = mapped_column(Integer, default=0)
    fined_late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    absent_deduction: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    overtime_rate_snapshot: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    bonus_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    adjustments_plus: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    adjustments_minus: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    gross: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    net: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="UZS")

    status: Mapped[str] = mapped_column(String(20), default=PayslipStatus.draft.value, index=True)
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PayslipItem(Base):
    """Payslip'ning bitta qatori (masalan "Kechikish jarimasi — 3 kun × 15 000
    so'm"). Har bir summaning kelib chiqishi shu jadvaldan ko'rinadi — "nega bu
    summa" degan savolga bir bosishda javob (nizolarning katta qismi shu
    yerda tugaydi)."""

    __tablename__ = "payslip_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payslip_id: Mapped[int] = mapped_column(ForeignKey("payslips.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    rate: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PayrollAdjustment(Base):
    """HR qo'lda kiritgan qo'shimcha (mukofot) yoki ushlanma (avans, zarar) —
    payroll hisobida `plus`/`minus` sifatida qo'shiladi. Avans tizimi ham shu
    orqali (2026-07-27 QAROR, 9-bo'lim savol 9): oy o'rtasida HR avansni
    `kind='minus'` bilan kiritadi, oy oxirida payslip'dan avtomatik ayiriladi."""

    __tablename__ = "payroll_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # ── Avans (2026-08-13) ──
    category: Mapped[str] = mapped_column(
        String(20), default=PayrollAdjustmentCategory.manual.value, server_default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(20), default=PayrollAdjustmentStatus.approved.value, server_default="approved"
    )
    # Avans QO'LGA BERILGAN sana. 2026-08-20 dan (A-04) u KIRITISHDA
    # so'ralmaydi va `NULL` bo'ladi — faqat «To'lab berildi» amali uni
    # to'ldiradi. Sabab: ilgari HR kiritishda «berilgan sana» yozardi,
    # ya'ni pul Boshliq tasdig'idan OLDIN berilgan bo'lib chiqardi va
    # rad javobi kelsa qaytarib olib bo'lmasdi.
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Avans arizasidan tug'ilgan bo'lsa — manba (ARIZALAR_REJASI.md 3.2).
    source_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_requests.id"), nullable=True, index=True
    )
    # Qaysi yo'ldan kiritildi (`PayrollAdjustmentSource`). Eski qatorlarni
    # migratsiya to'ldiradi: `source_request_id` bor bo'lsa «request»,
    # aks holda «hr_manual».
    source: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # Pulni KIM va QACHON berdi (A-04). `issued_on` — pul qo'lga berilgan
    # KUN (kassa ko'rsatadi), `issued_at` — tizimda belgilangan payt.
    # Ikkalasi bir xil emas: kassa 5-kuni bergan pulni 7-kuni belgilashi
    # mumkin, va «qachon berildi» savoliga aynan `issued_on` javob beradi.
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # YUMSHOQ O'CHIRISH (A-05). Pul yozuvini butunlay yo'qotish — «bu avans
    # qayerga ketdi?» degan savolga javobsiz qolish. Shuning uchun qator
    # qoladi, lekin BARCHA o'qish `deleted_at IS NULL` bilan filtrlanishi
    # SHART — ayniqsa `build_payslip`, aks holda o'chirilgan avans oylikdan
    # ayirilaverardi.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deleted_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AdvanceSettings(Base):
    """Avans sozlamalari — UCH DARAJALI qamrov (Avans TZ B-01).

    NEGA ALOHIDA JADVAL: A blokda ikkita sozlama vaqtincha `fine_policies`
    ga qo'yilgan edi (u yagona mavjud «HR paneli sozlamalari» jadvali edi).
    Lekin avansning o'z qiymatlari beshta va ular jarima qoidasiga hech
    qanday aloqasi yo'q — bitta jadvalda saqlash ikkalasini ham
    tushunarsiz qilardi. Bu yerga ko'chirilgach `fine_policies` yana
    faqat jarimaga oid bo'ldi.

    DARAJALAR: xodim > lavozim > global (`resolve_advance_settings`).
    Naqsh `payroll.resolve_policy` bilan AYNAN bir xil — ikki xil qoida
    ikki xil natija bermasin.

    HECH QANDAY SOZLAMA BO'LMASA: bot avans kuni xabarini UMUMAN
    yubormaydi (sozlanmagan holat xavfsiz tomonga — TZ talabi). HR ning
    qo'lda kiritish yo'li esa ishlayveradi va `advance.py` dagi default
    koeffitsientlardan foydalanadi.
    """

    __tablename__ = "advance_settings"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", name="uq_advance_settings_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))          # global | position | user
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Oyning nechanchi kuni avans e'lon qilinadi. Cron kechiksa ham
    # o'tkazib yubormaslik uchun taqqoslash `>=` (B-04).
    advance_day: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    # Ishlab bo'lingan pulning qanchasi berilishi mumkin (0.5 = yarmi).
    coefficient: Mapped[float] = mapped_column(Numeric(4, 2), default=0.5, server_default="0.5")
    # Oylikning eng ko'pi bilan necha foizi (koeffitsientdan qat'i nazar).
    cap_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=50, server_default="50")
    # Shundan kam chegara qolgan xodimga avans taklif qilinmaydi — mayda
    # summa uchun butun oqimni ishga tushirishning ma'nosi yo'q.
    min_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Avans kuni xabari soati ("HH:MM", mahalliy vaqt).
    reminder_time: Mapped[str] = mapped_column(String(5), default="14:00", server_default="14:00")
    # Davr yopilganda `pending` avans: carry (keyingi davrga) | cancel.
    pending_on_close: Mapped[str] = mapped_column(
        String(10), default="carry", server_default="carry"
    )
    # Sabab majburiymi. Default `False` — botda xodim tugma bosadi, matn
    # yozmaydi; majburiy qilinsa o'sha oqim buziladi.
    reason_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Qachondan amal qiladi — o'tgan oylarni qayta hisoblaganda eski
    # qoidani saqlab qolish uchun (hozircha ma'lumot sifatida yoziladi).
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AdvanceResponseState(str, enum.Enum):
    """Xodimning avans kuni xabariga munosabati (Avans TZ C bloki)."""

    offered = "offered"            # xabar yuborildi, javob yo'q
    waiting_input = "waiting_input"  # «Summa kiritish» bosildi, raqam kutilyapti
    declined = "declined"          # «Kerak emas» bosildi
    submitted = "submitted"        # summa kiritildi, so'rov yaratildi


class AdvanceResponse(Base):
    """Avans kuni xabariga munosabat — BIR XODIM, BIR DAVR (Avans TZ C-01…C-05).

    NEGA BAZADA, FSM DA EMAS (C-02 talabi): bot holati aiogram FSM da
    saqlansa, Passenger/cPanel jarayoni qayta ishga tushganda («deploy»,
    idle timeout, OOM) xodim yozayotgan summa yo'qolardi va u sababini
    tushunmasdi. Bazadagi holat qayta ishga tushishdan omon qoladi.

    BITTA JADVAL to'rt savolga javob beradi — shuning uchun alohida
    `advance_pending_input` qurilmadi:
      · «Summa kutilyaptimi?»  → `state == waiting_input` va muddati o'tmagan
      · «Javob berdimi?»       → `state != offered` (C-05 eslatmasi uchun)
      · «Eslatma yuborilganmi?» → `reminded_at`
      · «Qanday summa ko'rsatilgan edi?» → `offered_limit`

    `offered_limit` — xabar yuborilgan PAYTDAGI chegara. U faqat
    ma'lumot uchun: summa kiritilganda chegara QAYTA hisoblanadi
    (C-03), chunki oraliqda boshqa avans tasdiqlangan bo'lishi mumkin.
    """

    __tablename__ = "advance_responses"
    __table_args__ = (
        UniqueConstraint("user_id", "period", name="uq_advance_responses_user_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"
    state: Mapped[str] = mapped_column(
        String(16), default=AdvanceResponseState.offered.value, server_default="offered"
    )
    offered_limit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    # Summa kutish muddati — o'tgach holat bekor bo'ladi va xodim yozgan
    # matn oddiy xabar sifatida boshqa handlerlarga o'tadi.
    input_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Takroriy eslatma (C-05) — BIR marta. `NULL` bo'lsa hali yuborilmagan.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Yaratilgan so'rov (`PayrollAdjustment`) — natija xabari uchun (C-04).
    adjustment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payroll_adjustments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AdvanceAnnouncement(Base):
    """HR qo'lda e'lon qilgan avans kuni (Avans TZ D-01).

    NEGA KERAK: avans kuni ko'chishi mumkin (bayram, kassa kechikishi).
    Sozlamadagi `advance_day` ni har safar o'zgartirish noqulay va u
    KEYINGI oylarga ham ta'sir qilardi — bu esa faqat SHU oyga tegishli
    bir martalik qaror.

    ⚠️ AVTOMATIK XABARNI TO'XTATADI: shu davr uchun e'lon bo'lsa,
    `advance_day.tick` o'sha oyda umuman ishlamaydi. Aks holda xodim
    ikki marta xabar olardi (qo'lda + avtomatik).

    «Ikki marta e'lon qilinsa oxirgisi kuchda»: yangi e'lon eski
    e'londan qolgan YUBORILMAGAN xabarlarni navbatdan olib tashlaydi
    va o'z `id` si bilan yangi xabar qo'yadi.
    """

    __tablename__ = "advance_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"
    # Avans qaysi kuni beriladi (xabarda aynan shu sana ko'rsatiladi).
    advance_date: Mapped[date] = mapped_column(Date)
    # HR qo'shimcha izohi — bo'sh bo'lsa standart matn ishlatiladi.
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Nechta xodimga ketgani — tarixda ko'rinsin.
    recipients: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class OutboxStatus(str, enum.Enum):
    pending = "pending"
    sending = "sending"   # bir jarayon band qildi (B-03 qo'riqchisi)
    sent = "sent"
    failed = "failed"


class Outbox(Base):
    """Chiquvchi xabarlar navbati (Avans TZ B-03) — ⭐ umumiy poydevor.

    MUAMMO: hozir xabarlar SO'ROV ICHIDA yuboriladi. Telegram sekinlashsa
    yoki 429 bersa, foydalanuvchi so'rovi o'sha yerda kutib turadi
    (cPanel'da konkurentlik 1 — bitta sekin xabar butun saytni qotiradi).
    Xabar yo'qolsa esa iz ham qolmaydi: qayta urinish mexanizmi yo'q.

    Navbat orqali: so'rov xabarni BAZAGA yozadi va darhol javob qaytaradi,
    yuborishni cron o'z jarayonida bajaradi.

    IKKI JARAYON MUAMMOSI (production cPanel'da cron ikki nusxada ishlaydi
    — `uysot-rate-budget` xotirasidagi holat): navbatdan olish `pending`
    dan `sending` ga ATOMAR `UPDATE ... WHERE status='pending'` bilan
    o'tadi va band qilgan jarayon `claimed_by` tokeni bo'yicha o'z
    qatorlarini oladi. Shu sababli bitta xabarni ikki jarayon ola olmaydi.

    `dedupe_key` — takrorlanmaslik kafolati (masalan «avans kuni,
    2026-08, xodim 42»): UNIQUE, ya'ni ikkinchi qo'yish jimgina
    o'tkazib yuboriladi. B-04 dagi «oyiga bir marta» qo'riqchisi aynan
    shu maydon bilan ishlaydi.
    """

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # Xabar turi — hisobot va filtr uchun (masalan "advance_day").
    kind: Mapped[str] = mapped_column(String(40), index=True)
    # {"text": "...", "reply_markup": {...}} — yuborish uchun yetarli hamma narsa.
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(10), default=OutboxStatus.pending.value, server_default="pending", index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Shu paytdan OLDIN yuborilmaydi (kechiktirilgan xabar uchun).
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Qaysi jarayon band qilgani va qachon — osilib qolgan `sending`
    # qatorlarni qaytarib olish uchun (jarayon o'lib qolsa).
    claimed_by: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PushToken(Base):
    """Mobil ilovaning push manzili (Expo push token).

    Bitta xodimda bir nechta qurilma bo'lishi mumkin, shuning uchun `user_id`
    UNIKAL EMAS — unikal kalit `token` (bir qurilma bitta token beradi va uni
    qayta o'rnatishda yangilaydi).

    `last_seen_at` — ilova oxirgi marta token'ni tasdiqlagan payt. Shu maydon
    "xodim ilovadan foydalanadimi" savoliga javob beradi: agar foydalansa,
    SHAXSIY xabarlar Telegramga takroran yuborilmaydi (2026-07-31 qarori —
    aks holda har voqea uchun ikki marta chalinadi). Qurilma yo'qolsa yoki
    ilova o'chirilsa `last_seen_at` eskiradi va Telegram o'z-o'zidan qaytadi.

    `is_active` — Expo "DeviceNotRegistered" qaytarsa false qilinadi (ilova
    o'chirilgan). Yozuv o'chirilmaydi: qaysi qurilma qachon o'chganini
    ko'rish diagnostikada kerak bo'ladi.
    """

    __tablename__ = "push_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # android | ios | web. `web` — brauzer/PWA (iPhone uchun asosiy yo'l:
    # iOS'da nativ ilova yo'q, xodim saytni bosh ekranga qo'shadi).
    platform: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PushSetting(Base):
    """Xodimning push toifalari bo'yicha tanlovi — FAQAT standartdan FARQ
    qilganda yozuv paydo bo'ladi.

    Nega shunday: standart qiymatlar rolga bog'liq (`api/services/push.py:
    DEFAULT_CATEGORIES`) va vaqt o'tib o'zgarishi mumkin. Har xodimga
    to'liq nusxa yozib qo'yilsa, standart o'zgarganda eski nusxalar uni
    bosib qolardi va "nega menda yangi toifa chiqmadi" degan savol tug'ilardi.
    """

    __tablename__ = "push_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_push_setting_user_category"),)


class CrmWebhookLog(Base):
    """Uysot CRM webhook'idan kelgan har bir XOM so'rov jurnali.

    Uysot webhook'ni endigina ochdi (2026-08-01, faqat lid eventlari) va payload
    formati RASMIY HUJJATLASHTIRILMAGAN — shu jurnal formatni jonli oqimdan
    o'rganish, parse xatolarini keyin qayta o'ynatish va "webhook keldimi o'zi"
    diagnostikasi uchun YAGONA manba. Parse muvaffaqiyatli bo'lsa ham yoziladi
    (keyin format o'zgarsa taqqoslab bo'ladi); jadval o'sib ketmasin deb
    scheduler'ning kunlik tozalash joyidan emas, webhook servisining o'zida
    RETENTION_DAYS bo'yicha eski qatorlar o'chiriladi."""

    __tablename__ = "crm_webhook_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    remote_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Maxsus (standart bo'lmagan) headerlar JSON ko'rinishida — Uysot sekretni
    # qaysi header bilan yuborishini aniqlash uchun. Sekret qiymatining o'zi
    # yozilishidan OLDIN maskalanadi (api/services/uysot_webhook.py).
    headers: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[str] = mapped_column(Text)  # xom tana (JSON bo'lmasa ham saqlanadi)
    # Parse natijasi: nechta lid voqeasi ajratildi / xato bo'lsa qisqa izoh
    parsed_events: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SystemHealthState(Base):
    """Tizim sog'ligi qo'riqchisining holati — HAR TEKSHIRUV uchun bitta qator.

    NEGA KERAK: 2026-08-04 16:45 da Uysot Open API tokeni bekor qilindi va tizim
    27 soat davomida JIMGINA ko'r bo'lib qoldi — lid saralash, issiq-lid xabari,
    tashrif statistikasi va harakatsizlik nazorati to'xtadi, lekin buni hech kim
    bilmadi (xato faqat cron log'ida edi). Qo'riqchi shunday holatlarni aniqlab
    guruhga ogohlantiradi (`api/services/system_health.py`).

    `check` — tekshiruv nomi: `crm` | `backup` | `attendance` (kelajakda yana
    qo'shilishi mumkin). Har biri MUSTAQIL holatga ega: biri ogohlantirsa
    boshqasining takrorlanish qo'riqchisi susmaydi.

    DIQQAT — holat NEGA bazada: production cPanel CRON rejimida ishlaydi, ya'ni
    har daqiqa YANGI python jarayoni ko'tariladi. Modul darajasidagi o'zgaruvchi
    saqlanmaydi, shuning uchun "allaqachon ogohlantirdikmi" qo'riqchisi faqat
    bazada bo'lishi mumkin."""

    __tablename__ = "system_health_state"

    check: Mapped[str] = mapped_column(String(32), primary_key=True)
    # True — hozir "nosoz" holatidamiz (tiklanganda False bo'ladi va guruhga
    # "tiklandi" xabari ketadi)
    alerting: Mapped[bool] = mapped_column(Boolean, default=False)
    # Oxirgi ogohlantirish vaqti — takroriy xabar oralig'i shu asosda hisoblanadi
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Ogohlantirish yuborilgan paytdagi "signal oxirgi marta yangilangan" vaqt
    stale_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CelebrationKind(str, enum.Enum):
    """Guruhga tabrik yuboriladigan hodisa turi."""

    visit = "visit"        # lid «Tashrif» bosqichiga o'tdi
    contract = "contract"  # lid «Shartnoma qilindi» bosqichiga o'tdi
    #  ODAM hodisalari (yangi TZ 3.14 / S-22). Ular CRM voqeasidan emas,
    #  kundalik crondan keladi — shuning uchun `lead_event_id` bo'sh
    #  bo'ladi va takrorlanishdan `dedupe_key` qo'riqlaydi.
    birthday = "birthday"        # tug'ilgan kun
    anniversary = "anniversary"  # ish yubileyi (hire_date dan)


class CelebrationMedia(Base):
    """Tashrif/shartnoma bo'lganda guruhga yuboriladigan tabrik videosi.

    NEGA JADVAL, NEGA FAYL EMAS: video Telegram'ning O'ZIDA qoladi — biz faqat
    `file_id` ni saqlaymiz (xuddi `telegram_notify.send_file_id` naqshi kabi).
    Serverda video fayli saqlanmaydi, qayta yuborish oddiy JSON so'rov.

    Kim boshqaradi: Dasturchi / HR / Boshliq botdan yangi video (yoki GIF)
    yuboradi — eski qator `is_active=False` bo'lib tarixda qoladi, yangisi
    faol bo'ladi. HAR TUR uchun alohida video (`kind`).

    Faol video YO'Q bo'lsa — guruhga hech narsa yuborilmaydi. Ya'ni funksiya
    "o'chiq" holatda tug'iladi va faqat rahbar video yuklagach jonlanadi
    (deploy'dan keyin guruh kutilmaganda xabarga to'lib ketmasin)."""

    __tablename__ = "celebration_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    file_id: Mapped[str] = mapped_column(String(512))
    # "video" -> sendVideo, "animation" -> sendAnimation (GIF)
    file_type: Mapped[str] = mapped_column(String(16), default="video")
    # Rahbar xohlasa o'z matnini qo'shadi (bo'sh bo'lsa standart matn ishlatiladi)
    caption: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CelebrationPost(Base):
    """Guruhga YUBORILGAN bitta tabrik — takroriy yuborishning oldini oladi.

    `lead_event_id` UNIQUE: bir voqea uchun faqat bitta post. Bu shart, chunki
    voqealarni IKKI manba yozadi (webhook va diff-skaner) va e'lon qiluvchi
    har daqiqada ishlaydi — takrorlanish xavfi real."""

    __tablename__ = "celebration_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    #  CRM voqeasidan kelgan tabrikda to'ladi. ODAM hodisalarida
    #  (tug'ilgan kun, yubiley) bo'sh — S-22 dan beri nullable.
    lead_event_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, index=True, nullable=True
    )
    crm_lead_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    #  ⚠️ ODAM hodisalari uchun TAKRORLANISH QO'RIQCHISI:
    #  `birthday:7:2026`. `lead_event_id` ularda bo'sh, shuning uchun
    #  eski qo'riqchi ishlamaydi — cron kuniga bir necha marta ishlasa
    #  guruhga bir xil tabrik qayta-qayta ketardi.
    dedupe_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    # Tizimdagi xodim (CRM mas'uli bog'lanmagan bo'lsa — NULL)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    claps: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CelebrationClap(Base):
    """«👏 Tabriklash» bosilishi — bitta odam bitta postga bir marta.

    Nega alohida jadval: tugmani bosgan har kim sanoqni oshiraversa, bitta
    odam 50 marta bosib "50 tabrik" qilib qo'yardi."""

    __tablename__ = "celebration_claps"
    __table_args__ = (UniqueConstraint("post_id", "telegram_id", name="uq_celebration_clap"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("celebration_posts.id", ondelete="CASCADE"), index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdSpend(Base):
    """Reklama xarajati — oy × kanal (voronka 3-bosqich).

    NEGA QO'LDA: xarajat na tizimda, na CRM'da bor — u reklama kabinetlarida
    (Meta/Google/Telegram). Boshlanishiga oyiga bir marta qo'lda kiritiladi;
    keyin kabinet API'lariga ulash mumkin.

    `channel` — voronkadagi kanal nomi bilan AYNAN bir xil bo'lishi kerak
    (CRM tegi «#telegram» yoki manba «WEB_FORM»), aks holda xarajat lidlar
    bilan bog'lanmaydi. Shuning uchun kiritish sahifasi kanal nomini
    voronkada HAQIQATAN uchragan qiymatlardan tanlatadi — qo'lda yozish
    imlo xatosiga olib kelardi va CPL jimgina noto'g'ri chiqardi.

    `reach` — qamrov/ko'rsatishlar soni (ixtiyoriy): voronkaning eng yuqori
    bo'g'ini. Kiritilsa «auditoriya → lid» konversiyasi ham hisoblanadi."""

    __tablename__ = "ad_spend"
    __table_args__ = (UniqueConstraint("period", "channel", name="uq_ad_spend_period_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"
    channel: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class FunnelMonth(Base):
    """Oylik voronka farazlari — hozircha bittasi: o'rtacha shartnoma foydasi.

    NEGA KERAK: ROMI («reklama puli o'zini qopladimi») daromadsiz hisoblanmaydi,
    daromad esa CRM'da yo'q — lid yozuvidagi `balance` jonli bazada deyarli
    doim 0. Shuning uchun rahbar bitta shartnomadan o'rtacha QANCHA FOYDA
    qolishini kiritadi; kiritilmasa ROMI ko'rsatilmaydi (taxminiy raqam
    chiqarib, unga ishonib qolishdan ko'ra «hisoblanmadi» deyish to'g'riroq).

    Kelajakda oylik maqsad (4-bosqich) ham shu jadvalga qo'shiladi."""

    __tablename__ = "funnel_month"

    period: Mapped[str] = mapped_column(String(7), primary_key=True)  # "YYYY-MM"
    avg_deal_profit: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # ── Teskari kalkulyator (4-bosqich) ──
    # Oylik maqsad: nechta shartnoma (= nechta uy). Shundan yuqoriga qarab
    # kerakli tashrif/suhbat/lid/byudjet hisoblanadi.
    target_contracts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Rahbar QO'LDA o'zgartirgan farazlar, masalan
    # {"visit_to_contract": 8.0, "cpl": 45000}. Bo'sh kalitlar o'lchangan
    # qiymat bilan to'ldiriladi — ya'ni bu «ustiga yozish» qatlami, to'liq
    # nusxa emas: o'lchov yangilansa, tegilmagan farazlar ham yangilanadi.
    assumptions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class FunnelSettings(Base):
    """Voronka hisobining QOIDALARI — rahbar panelidan boshqariladi (yagona
    qator, id=1). `AiConfig` bilan bir xil naqsh.

    NEGA PANELDA, .ENV DA EMAS: bular texnik sozlama emas, BIZNES qarori.
    «Bekor qilingan shartnoma sotuvdan ayrilsinmi?» degan savolga javobni
    dasturchi emas, egasi beradi va u vaqt o'tib o'zgarishi mumkin — har
    safar deploy kutib o'tirmasin.

    Bosqich ID'lari ham shu yerda: ular CRM'ga bog'liq va voronkaning
    boshqa bosqichlaridan (`.env` dagi tashrif/shartnoma/taklif) farqli
    o'laroq, bu ikkitasi KEYIN qo'shildi va ularni tanlash uchun panelda
    tayyor ro'yxat bor (bosqich nomlari bizning jurnalimizdan olinadi,
    CRM'ga so'rov ketmaydi)."""

    __tablename__ = "funnel_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # doim 1
    # «Bekor qilingan shartnoma» bosqichlari (masalan «Muvaffaqiyatsiz yopildi»)
    cancelled_pipe_status_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Yoqilsa: shartnomaga yetgan, lekin keyin bekor bo'lgan lid SOTUV
    # sanalmaydi. O'chiq bo'lsa (default) — hozirgi xatti-harakat saqlanadi.
    subtract_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

    # «Sifatsiz lead» bosqichlari
    low_quality_pipe_status_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Yoqilsa: hozirgi holati «sifatsiz» bo'lgan lid LID SONIGA kirmaydi,
    # ya'ni konversiya maxraji tozalanadi.
    exclude_low_quality: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BackgroundJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class BackgroundJob(Base):
    """Og'ir ishlar navbati (yangi TZ 2.2 / S-07).

    NEGA KERAK: cPanel Passenger'da konkurentlik = 1 — bitta uzoq so'rov
    BUTUN saytni navbatga qo'yadi. Excel eksporti, hujjat generatsiyasi va
    shunga o'xshash ishlar so'rov ichida bajarilmasligi kerak.

    Oylik hisobi uchun allaqachon shunday navbat bor
    (`payroll_periods.calc_state`), lekin u O'SHA modulga xos (progress,
    davr qulfi). Bu esa UMUMIY mexanizm: yangi og'ir ish qo'shilganda
    faqat ishlovchi funksiya yoziladi.

    ⚠️ Holat FAQAT bazada. Cron har daqiqada YANGI jarayon ishga tushiradi,
    ya'ni modul darajasidagi navbat/lock ishlamaydi."""

    __tablename__ = "background_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), default=BackgroundJobStatus.queued.value, server_default="queued", index=True
    )
    # Kim so'ragan — natija SHU odamga yuboriladi.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    # Natija Telegram'da qoladi (serverda fayl SAQLANMAYDI — disk kvotasi tor).
    result_file_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    result_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HolidayKind(str, enum.Enum):
    state = "state"  # davlat bayrami
    company = "company"  # kompaniya qarori (masalan korporativ dam kun)


class Holiday(Base):
    """Dam olish deb e'lon qilingan kunlar (yangi TZ 2.9 / S-09).

    NEGA KERAK: tizim bayramni oddiy ish kuni deb sanardi. Oqibati ikki
    tomonlama — xodim kelmagani uchun «kelmagan kun» ushlanmasiga tushardi,
    normalar esa bajarilmagan bo'lib ko'rinardi.

    Sana UNIKAL: bir kun ikki marta e'lon qilinmasin (HR ro'yxatni yildan
    yilga ko'chirganda takrorlash oson)."""

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default=HolidayKind.state.value)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentType(str, enum.Enum):
    """Kadr hujjati turlari (yangi TZ 3.4).

    Ro'yxat YOPIQ: HR har safar o'z nomini yozsa bir xil hujjat besh xil
    nom bilan yotardi va «kimda mehnat shartnomasi yo'q?» degan savolga
    javob berib bo'lmasdi. Yangi tur kerak bo'lsa — shu yerga qo'shiladi."""

    contract = "contract"  # mehnat shartnomasi
    job_description = "job_description"  # lavozim yo'riqnomasi
    property_act = "property_act"  # mol-mulk dalolatnomasi
    handover_act = "handover_act"  # ishni topshirish dalolatnomasi
    medical = "medical"  # tibbiy ma'lumotnoma
    diploma = "diploma"  # diplom / sertifikat
    other = "other"  # boshqa


#  Foydalanuvchiga ko'rsatiladigan nomlar — bitta joyda (bot, web, kabinet
#  shu lug'atdan oladi, aks holda uch xil tarjima paydo bo'lardi).
DOCUMENT_TYPE_LABELS: dict[str, str] = {
    DocumentType.contract.value: "Mehnat shartnomasi",
    DocumentType.job_description.value: "Lavozim yo'riqnomasi",
    DocumentType.property_act.value: "Mol-mulk dalolatnomasi",
    DocumentType.handover_act.value: "Ishni topshirish dalolatnomasi",
    DocumentType.medical.value: "Tibbiy ma'lumotnoma",
    DocumentType.diploma.value: "Diplom / sertifikat",
    DocumentType.other.value: "Boshqa",
}


class EmployeeDocument(Base):
    """Xodimning kadr hujjati (yangi TZ 3.4 / S-10).

    NEGA KERAK: hujjatlar hozir HR ning shaxsiy Telegram yozishmalarida va
    qog'oz papkasida. «Falonchining mehnat shartnomasi qani?» degan savol
    har safar qidiruvga aylanadi, ishdan bo'shaganda esa mol-mulk
    dalolatnomasi topilmaydi.

    ⚠️ FAYL SERVERDA SAQLANMAYDI — faqat Telegram `file_id`. Disk kvotasi
    tor (1 GB) va TZ 1.1 shuni talab qiladi; fayl Telegram'ning o'zida
    qoladi, biz uni istagancha qayta yuboramiz (`send_file_id` naqshi,
    `CelebrationMedia` bilan bir xil).

    ⚠️ MAXFIY. Ruxsat `api/deps.py::assert_can_view(..., rop_sees_team=False)`
    orqali: xodim faqat O'ZINIKINI, HR/Boshliq/Dasturchi hammasini ko'radi.
    ROP bu modulda «begona» — o'z jamoasining diplomini ham ko'rmaydi.

    O'chirish YUMSHOQ (`deleted_at`): kadr hujjatini butunlay yo'qotish
    huquqiy xavf, xato bosilgan «o'chirish» qaytarilishi kerak. BARCHA
    o'qish `deleted_at IS NULL` bilan filtrlanishi SHART."""

    __tablename__ = "employee_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(24), index=True)
    name: Mapped[str] = mapped_column(String(200))
    file_id: Mapped[str] = mapped_column(String(512))
    # "document" -> sendDocument, "photo" -> sendPhoto
    file_type: Mapped[str] = mapped_column(String(16), default="document")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    #  Hujjat qachon berilgan va qachon tugaydi. `expires_at` NULL —
    #  muddatsiz (mehnat shartnomasi odatda shunday). S-12 muddat
    #  eslatmalari aynan shu ustundan o'qiydi.
    issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #  ── Davlat ro'yxatidan o'tkazish belgisi (yangi TZ 3.28 / S-27) ──
    #  ⚠️ TIZIM RO'YXATGA OLISHNI BAJARMAYDI. Bu tashqi jarayon (mehnat
    #  organi); tizim faqat «qilindimi?» degan BELGINI yuritadi. Aks
    #  holda HR uni bajarilgan deb o'ylab, aslida qilinmagan bo'lardi.
    registered_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    registered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    registration_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeadlineKind(str, enum.Enum):
    """Muddat turlari (yangi TZ 3.5).

    Bir qismi HISOBLANADI (manbasidan), bir qismi QO'LDA kiritiladi —
    farqi `DEADLINE_COMPUTED` to'plamida."""

    probation = "probation"  # sinov muddati (hisoblanadi: hire_date + N kun)
    contract = "contract"  # shartnoma muddati (hisoblanadi: hujjat expires_at)
    document = "document"  # boshqa hujjat muddati (hisoblanadi)
    safety_briefing = "safety_briefing"  # TX takroriy instruktaj
    medical_exam = "medical_exam"  # tibbiy ko'rik
    permit = "permit"  # pasport / ruxsatnoma
    course = "course"  # majburiy kurs
    #  Shartnomani davlat ro'yxatidan o'tkazish (yangi TZ 3.28 / S-27).
    #  Muddati qo'lda emas, ishga qabul sanasidan hisoblanadi, lekin
    #  qator QO'LDA yaratiladi (cron) — chunki u faqat belgi qo'yilmagan
    #  xodimlar uchun kerak, hammasi uchun emas.
    contract_registration = "contract_registration"


DEADLINE_KIND_LABELS: dict[str, str] = {
    DeadlineKind.probation.value: "Sinov muddati",
    DeadlineKind.contract.value: "Shartnoma muddati",
    DeadlineKind.document.value: "Hujjat muddati",
    DeadlineKind.safety_briefing.value: "TX takroriy instruktaj",
    DeadlineKind.medical_exam.value: "Tibbiy ko'rik",
    DeadlineKind.permit.value: "Pasport / ruxsatnoma",
    DeadlineKind.course.value: "Majburiy kurs",
    DeadlineKind.contract_registration.value: "Shartnomani ro'yxatga olish",
}

#  Bu turlar jadvalga YOZILMAYDI — sanasi manbasidan hisoblanadi.
#  Jadvalda ular uchun faqat «eslatma yuborildi» izi turadi (TZ 3.5:
#  «ikkita manba bo'lmasin»).
DEADLINE_COMPUTED: frozenset[str] = frozenset(
    {DeadlineKind.probation.value, DeadlineKind.contract.value, DeadlineKind.document.value}
)


class DeadlineStatus(str, enum.Enum):
    open = "open"
    done = "done"  # bajarildi (yangilandi, o'tildi)
    cancelled = "cancelled"


class Deadline(Base):
    """Muddat — qo'lda kiritilgani yoki hisoblangani uchun eslatma izi
    (yangi TZ 3.5 / S-12).

    IKKI XIL QATOR, BITTA JADVAL:

    1. QO'LDA kiritilgan muddat (`source_kind IS NULL`) — `due_date`
       to'ldirilgan, u yagona manba.

    2. HISOBLANADIGAN muddat (`source_kind` bor, `due_date` NULL) —
       sana HECH QACHON bu yerda saqlanmaydi, har safar manbasidan
       o'qiladi (`users.hire_date`, `employee_documents.expires_at`).
       Qator faqat `reminded_at` uchun yaratiladi va faqat birinchi
       eslatma yuborilganda.

    NEGA SHUNDAY: shartnoma sanasi hujjatda o'zgarsa, nusxasi jadvalda
    eskirib qolardi va tizim ikki xil muddat ko'rsatardi. TZ buni aniq
    taqiqlaydi — «ikkita manba bo'lmasin»."""

    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    #  QO'LDA kiritilganda majburiy; hisoblanadiganda NULL (yuqoriga qarang).
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #  Kimga eslatiladi. Bo'sh bo'lsa HR ga (S-13 default).
    responsible_role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #  `None` — qo'lda kiritilgan. Aks holda "document" yoki "probation".
    source_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #  Oxirgi eslatma sanasi — kuniga bir marta yuborish uchun (S-13).
    reminded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default=DeadlineStatus.open.value, index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeadlineConfig(Base):
    """Muddat modulining sozlamalari — bitta qator (`id=1`).

    `attendance_digest_config` bilan bir xil naqsh: modulga xos bir
    nechta son uchun alohida jadval."""

    __tablename__ = "deadline_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    #  Sinov muddati necha kun (O'zbekistonda odatda 3 oy).
    probation_days: Mapped[int] = mapped_column(Integer, default=90)
    #  Necha kun oldin eslatilsin.
    remind_days: Mapped[int] = mapped_column(Integer, default=30)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DocumentTemplateKind(str, enum.Enum):
    """Shablon turlari (yangi TZ 3.3). Keyingi modullar shu ro'yxatga
    tayanadi: ish taklifi (S-15), buyruq (3.21), ma'lumotnoma (3.9)."""

    offer = "offer"  # ish taklifi
    order = "order"  # buyruq
    reference = "reference"  # ma'lumotnoma
    contract = "contract"  # mehnat shartnomasi
    act = "act"  # dalolatnoma
    other = "other"


DOCUMENT_TEMPLATE_LABELS: dict[str, str] = {
    DocumentTemplateKind.offer.value: "Ish taklifi",
    DocumentTemplateKind.order.value: "Buyruq",
    DocumentTemplateKind.reference.value: "Ma'lumotnoma",
    DocumentTemplateKind.contract.value: "Mehnat shartnomasi",
    DocumentTemplateKind.act.value: "Dalolatnoma",
    DocumentTemplateKind.other.value: "Boshqa",
}


class DocumentTemplate(Base):
    """`.docx` shabloni — belgilari bilan (yangi TZ 3.3 / S-14).

    Shablon fayli SERVERDA SAQLANMAYDI — Telegram `file_id`. Generatsiya
    paytida yuklab olinadi (`telegram_notify.download_file`).

    `placeholders` — shablonda topilgan belgilar ro'yxati (JSON). U
    YUKLASH paytida faylning O'ZIDAN o'qiladi, qo'lda kiritilmaydi:
    HR ro'yxatni qo'lda yozsa, u shablon bilan mos kelmay qolardi va
    xato faqat tayyor hujjatda ko'rinardi."""

    __tablename__ = "document_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(200))
    file_id: Mapped[str] = mapped_column(String(512))
    placeholders: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OfferStatus(str, enum.Enum):
    """Ish taklifi holati (yangi TZ 3.3 / S-15).

    ⚠️ `sent` — «HR nomzodga YUBORDI» degani, tizim yuborgani emas.
    Tizim nomzodga hech narsa jo'natmaydi (TZ talabi): nomzod hali
    xodim emas, uning Telegram'i bizda yo'q va bo'lmasligi ham kerak."""

    draft = "draft"  # tayyorlanmoqda
    sent = "sent"  # HR nomzodga yubordi
    accepted = "accepted"  # nomzod rozi bo'ldi
    declined = "declined"  # nomzod rad etdi
    cancelled = "cancelled"  # kompaniya bekor qildi


OFFER_STATUS_LABELS: dict[str, str] = {
    OfferStatus.draft.value: "Qoralama",
    OfferStatus.sent.value: "Yuborilgan",
    OfferStatus.accepted.value: "Qabul qilingan",
    OfferStatus.declined.value: "Rad etilgan",
    OfferStatus.cancelled.value: "Bekor qilingan",
}


class Offer(Base):
    """Ish taklifi (yangi TZ 3.3 / S-15).

    NEGA BAZADA QOLADI: taklif hozir Word faylida va HR ning
    yozishmalarida. «O'tgan oy falonchiga qancha taklif qilgandik?» degan
    savolga javob yo'q, kelishilgan oylik esa ishga qabul qilinganda
    boshqacha bo'lib chiqadi.

    ⚠️ `salary` — INTEGER (TZ qabul mezoni). Matn bo'lsa «12 mln»,
    «12,000,000», «12000000 so'm» kabi yozuvlar aralashib, taqqoslash va
    yig'ish umuman ishlamasdi.

    ⚠️ TIZIM NOMZODGA HECH NARSA YUBORMAYDI. Hujjat HR ga beriladi, uni
    nomzodga HR o'zi jo'natadi. Nomzod hali xodim emas."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #  Lavozim ro'yxatdan yoki erkin matn: yangi lavozim hali
    #  `positions` da bo'lmasligi mumkin, taklif esa kutib turmasin.
    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True
    )
    position_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary: Mapped[int] = mapped_column(Integer)
    probation_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #  Bo'lajak rahbari — qabul qilinganda xodimning `manager_id` siga o'tadi.
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), default=OfferStatus.draft.value, index=True
    )
    #  Nomzod xodimga aylangach shu yerga bog'lanadi (S-16).
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CertificatePurpose(str, enum.Enum):
    """Ma'lumotnoma maqsadi (yangi TZ 3.9). HAR BIRIGA alohida shablon —
    bankka beriladigan matn bilan bog'chaga beriladigani bir xil emas."""

    bank = "bank"
    visa = "visa"
    kindergarten = "kindergarten"
    other = "other"


CERTIFICATE_PURPOSE_LABELS: dict[str, str] = {
    CertificatePurpose.bank.value: "Bank uchun",
    CertificatePurpose.visa.value: "Viza uchun",
    CertificatePurpose.kindergarten.value: "Bog'cha uchun",
    CertificatePurpose.other.value: "Boshqa",
}


class Certificate(Base):
    """Berilgan ma'lumotnoma — ARXIV (yangi TZ 3.9 / S-17).

    NEGA JADVAL KERAK: TZ «arxivda kimga, qachon, qaysi maqsadda tarixi
    qoladi» deydi. Amalda bu savol tez-tez chiqadi — «bu odamga shu yil
    nechta ma'lumotnoma berdik?», «bankka bergani qaysi raqamda edi?».

    ⚠️ `number` UNIKAL. Ma'lumotnoma raqami rasmiy rekvizit: ikkita
    hujjat bir xil raqam bilan chiqsa tashqi tashkilot ularni qalbaki
    deb hisoblaydi. Unikallik BAZA darajasida kafolatlanadi, kod
    darajasidagi hisoblash yetarli emas (parallel tasdiq)."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    #  Qaysi arizadan chiqqani. Qo'lda berilgan bo'lsa NULL.
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_requests.id"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    #  O'rtacha oylik FAQAT so'ralganda yoziladi (TZ qabul mezoni):
    #  bu maxfiy ma'lumot va bog'chaga kerak emas.
    include_salary: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_salary: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_templates.id"), nullable=True
    )
    #  Tayyor hujjat `employee_documents` ga yozilgach shu yerga bog'lanadi.
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_documents.id"), nullable=True
    )
    issued_at: Mapped[date] = mapped_column(Date, index=True)
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssetKind(str, enum.Enum):
    """Mol-mulk turlari (yangi TZ 3.11)."""

    laptop = "laptop"
    phone = "phone"
    sim = "sim"
    furniture = "furniture"
    tool = "tool"
    vehicle = "vehicle"
    other = "other"


ASSET_KIND_LABELS: dict[str, str] = {
    AssetKind.laptop.value: "Kompyuter / noutbuk",
    AssetKind.phone.value: "Telefon",
    AssetKind.sim.value: "SIM-karta",
    AssetKind.furniture.value: "Mebel",
    AssetKind.tool.value: "Asbob-uskuna",
    AssetKind.vehicle.value: "Transport",
    AssetKind.other.value: "Boshqa",
}


class AssetCondition(str, enum.Enum):
    """Buyumning JISMONIY holati — biriktirish va qaytarishda yoziladi."""

    new = "new"
    good = "good"
    worn = "worn"
    broken = "broken"


ASSET_CONDITION_LABELS: dict[str, str] = {
    AssetCondition.new.value: "Yangi",
    AssetCondition.good.value: "Yaxshi",
    AssetCondition.worn.value: "Eskirgan",
    AssetCondition.broken.value: "Nosoz",
}


class Asset(Base):
    """Kompaniya mol-mulki (yangi TZ 3.11 / S-18).

    NEGA KERAK: noutbuk, telefon, SIM-karta va asbob kimdaligi hech qayerda
    yozilmagan. Xodim ishdan bo'shaganda «unda nima bor edi?» degan savolga
    javob yo'q va buyum shunchaki yo'qoladi.

    ⚠️ `inventory_no` UNIKAL. Inventar raqami buyumning yagona belgisi;
    takrorlansa ikkita buyum bir-biriga aralashib ketadi va «kimda?»
    degan savol yana javobsiz qoladi.

    ⚠️ `value` — INTEGER (`Offer.salary` bilan bir xil sabab): matn bo'lsa
    «5 mln» va «5,000,000» aralashib, jami qiymatni hisoblab bo'lmasdi.

    O'chirish YUMSHOQ: buyum hisobdan chiqarilsa ham biriktirish TARIXI
    saqlanishi kerak (kimda bo'lgan, qanday holatda qaytgan)."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), index=True)
    condition: Mapped[str] = mapped_column(String(12), default=AssetCondition.good.value)
    value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AssetAssignment(Base):
    """Buyum kimga, qachon berilgani (yangi TZ 3.11 / S-18).

    ⚠️ BITTA BUYUM — BITTA XODIMDA. Qo'riqchi ikki qatlamli:
    (1) kod tekshiradi va tushunarli xato beradi;
    (2) QISMAN UNIKAL indeks (`returned_at IS NULL`) bazada kafolatlaydi.
    Faqat kodga tayanish yetarli emas: parallel ikki so'rov bir vaqtda
    tekshiruvdan o'tib, ikkita ochiq biriktirish yaratishi mumkin edi.

    Qaytarilgan qator O'CHIRILMAYDI — tarix. Shu tufayli bitta buyumda
    ko'p qator bo'ladi, lekin `returned_at IS NULL` bo'lgani faqat bitta."""

    __tablename__ = "asset_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[date] = mapped_column(Date, index=True)
    returned_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #  Berishdagi va qaytarishdagi holat — ular farq qilsa zarar ko'rinadi.
    condition_out: Mapped[str] = mapped_column(String(12), default=AssetCondition.good.value)
    condition_in: Mapped[str | None] = mapped_column(String(12), nullable=True)
    #  Dalolatnoma (S-19 da S-14 mexanizmi bilan tayyorlanadi).
    document_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #  Xodim «Qabul qildim» bosgan vaqt (S-19). NULL — hali tasdiqlamagan.
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PositionAssetSet(Base):
    """Lavozimga tegishli STANDART mol-mulk to'plami (yangi TZ 3.11 / S-19).

    NEGA KERAK: yangi sotuvchi kelganda unga nima berish kerakligini HR
    xotirasidan tiklaydi va har safar bir narsa unutiladi (odatda SIM-karta
    yoki quloqchin). Ishdan bo'shaganda esa aksincha — nima qaytarilishi
    kerakligi noma'lum bo'lib qoladi.

    Bu jadval BUYUMNI EMAS, TURNI belgilaydi: «sotuvchiga 1 ta noutbuk,
    1 ta telefon, 1 ta SIM». Aniq inventar raqamni HR biriktirish paytida
    tanlaydi — omborda qaysi biri bo'sh bo'lsa o'sha.

    Onboarding (3.2) va offboarding (3.7) shu ro'yxatdan foydalanadi."""

    __tablename__ = "position_asset_sets"
    __table_args__ = (
        UniqueConstraint("position_id", "kind", name="uq_position_asset_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AckObjectType(str, enum.Enum):
    """Nima bilan tanishtirilyapti (yangi TZ / S-20).

    UCHTA MODUL bitta jadvalga yozadi: lavozim yo'riqnomasi (3.16), ichki
    e'lon (3.12) va texnika xavfsizligi instruktaji (3.6). Har biriga
    alohida jadval qilinsa «kim nima bilan tanishmagan?» degan savolga
    uchta so'rov kerak bo'lardi va yangi tur qo'shilganda to'rtinchisi."""

    instruction = "instruction"  # lavozim yo'riqnomasi
    announcement = "announcement"  # ichki e'lon
    briefing = "briefing"  # TX instruktaji
    policy = "policy"  # ichki qoida / nizom


ACK_OBJECT_LABELS: dict[str, str] = {
    AckObjectType.instruction.value: "Lavozim yo'riqnomasi",
    AckObjectType.announcement.value: "E'lon",
    AckObjectType.briefing.value: "Instruktaj",
    AckObjectType.policy.value: "Ichki qoida",
}


class Acknowledgement(Base):
    """«Tanishdim» qaydi — UMUMIY mexanizm (yangi TZ / S-20).

    Qator IKKI holatda bo'ladi:
      • `acknowledged_at IS NULL` — tanishish SO'RALGAN, hali bosilmagan;
      • to'ldirilgan — tanishgan, vaqti bilan.

    ⚠️ VERSIYA MUHIM. Yo'riqnoma yangilansa eski tanishuv O'TMAYDI:
    xodim eski matnga rozi bo'lgan, yangisiga emas. Yangi versiya
    so'ralganda yangi qatorlar yaratiladi, eskilari TARIX bo'lib qoladi
    — «o'sha paytda nimaga rozi bo'lgan edi?» degan savolga javob shu.

    ⚠️ UNIQUE(user_id, object_type, object_id, version) — bir odam bir
    versiyani ikki marta tasdiqlay olmaydi (TZ qabul mezoni). Bu BAZA
    darajasida: takroriy so'rov yuborilsa ikkinchi qator yaratilmaydi.

    `title` — SO'RALGAN PAYTDAGI sarlavha nusxasi. Bu ataylab
    denormalizatsiya: manba keyin tahrirlansa ham, xodim NIMAGA rozi
    bo'lgani ko'rinib turishi kerak. Joriy sarlavha manbadan olinadi."""

    __tablename__ = "acknowledgements"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "object_type", "object_id", "version", name="uq_ack_user_object_version"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(16), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    #  Manba moduli boshqaradi. Matn o'zgarsa u versiyani oshiradi.
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #  Mijoz shu yo'lga o'tadi («E'lonni ochish»).
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    #  ── ESLATMA HISOBI (yangi TZ 3.16 / S-42) ──
    #  ⚠️ ESLATMA CHEKSIZ BO'LMASLIGI SHART. Sanoqsiz bot har kuni
    #  yozaverardi va xodim uni o'chirib qo'yardi — shundan keyin
    #  BOSHQA hech qanday eslatma ham yetib bormasdi. Uch martadan
    #  keyin bot jim bo'ladi va band HR ro'yxatiga tushadi: bu yerda
    #  masala texnik emas, HR ning odam bilan gaplashishi kerak.
    #
    #  ⚠️ Sanoq (obyekt, VERSIYA) bo'yicha: yangi versiya yangi qator
    #  demak, ya'ni yangi yo'riqnoma uchun eslatma noldan boshlanadi.
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnnouncementAudience(str, enum.Enum):
    """E'lon kimga boradi (yangi TZ 3.12 / S-21)."""

    all = "all"  # hamma faol xodim
    roles = "roles"  # tanlangan rollar
    positions = "positions"  # tanlangan lavozimlar
    users = "users"  # aniq xodimlar


class Announcement(Base):
    """Ichki e'lon (yangi TZ 3.12 / S-21).

    NEGA KERAK: e'lonlar hozir umumiy Telegram guruhida yo'qoladi —
    yangi xabarlar ostida qolib ketadi va «men ko'rmadim» degan javob
    tekshirib bo'lmaydi. Muhim e'londa «Tanishdim» talab qilinadi va
    kim o'qiganini ko'rish mumkin (`acknowledgements`, S-20).

    ⚠️ QAMROVGA KIRMAGAN XODIMGA E'LON UMUMAN KO'RINMAYDI (TZ qabul
    mezoni). Ya'ni qamrov — ko'rinishni bezash emas, FILTR: sotuv
    bo'limiga aytilgan gap prorabga ko'rinmasligi kerak.

    `scope_ids` — `audience` ga qarab rol nomlari, lavozim id lari yoki
    xodim id lari. Bo'sh ro'yxat `audience="all"` bilan bir xil EMAS:
    bo'sh ro'yxat hech kimni qamramaydi va e'lon jimgina yo'qolardi,
    shuning uchun API uni rad etadi."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(12), default=AnnouncementAudience.all.value)
    scope_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    #  Muhim e'lon: «Tanishdim» talab qilinadi va u `acknowledgements`
    #  ga yoziladi. Oddiy e'lon shunchaki ko'rinadi.
    important: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #  Matn tahrirlansa versiya oshadi va tanishuv QAYTA so'raladi (S-20).
    version: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    #  Yumshoq o'chirish: e'lon tarixi va tanishuv qaydi saqlanishi kerak.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AnnouncementConfig(Base):
    """E'lonlar modulining sozlamasi — bitta qator (`id=1`).

    ⚠️ KUNLIK LIMIT (TZ talabi). Cheklovsiz tizim e'lon spamiga
    aylanadi: kuniga o'nta xabar kelsa xodim ularni o'qimay yopib
    qo'yadi va MUHIM e'lon ham shu taqdirni ko'radi."""

    __tablename__ = "announcement_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    daily_limit: Mapped[int] = mapped_column(Integer, default=3)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StaffPositionStatus(str, enum.Enum):
    """Shtat birligining holati (yangi TZ 3.20 / S-23)."""

    open = "open"  # amalda, to'ldirilishi mumkin
    frozen = "frozen"  # muzlatilgan (byudjet yopiq)
    closed = "closed"  # yopilgan


STAFF_POSITION_STATUS_LABELS: dict[str, str] = {
    StaffPositionStatus.open.value: "Amalda",
    StaffPositionStatus.frozen.value: "Muzlatilgan",
    StaffPositionStatus.closed.value: "Yopilgan",
}


class StaffPosition(Base):
    """Shtat jadvali birligi (yangi TZ 3.20 / S-23).

    NEGA KERAK: «bizda nechta sotuvchi o'rni bor va nechtasi bo'sh?»
    degan savolga javob hech qayerda yo'q. Ishga olish qarori shu
    savolga tayanadi, lekin u har safar boshdan sanaladi.

    ⚠️ «BAND» SONI SAQLANMAYDI — HISOBLANADI (TZ qabul mezoni). Faol
    xodimlar soni bo'yicha. Qo'lda kiritilsa u darhol eskirardi: xodim
    ishdan bo'shaydi, shtat jadvalini yangilash esa unutiladi va tizim
    «hammasi band» deb yolg'on ko'rsatib turaveradi.

    ⚠️ `salary_min`/`salary_max` — INTEGER (`Offer.salary` bilan bir xil
    sabab): matn bo'lsa «5-7 mln» kabi yozuvlar paydo bo'lib, taqqoslash
    va byudjet hisobi ishlamasdi.

    `effective_from` — shtat jadvali TARIXIY hujjat: «o'tgan yil nechta
    o'rin bor edi?» degan savolga javob berishi kerak. Shuning uchun
    eski qator o'chirilmaydi, yangisi qo'shiladi."""

    __tablename__ = "staff_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #  Bo'lim — ERKIN MATN. `teams` jadvali mavjud, lekin amalda bo'sh
    #  va hech kim to'ldirmagan; unga bog'lash modulni ishlamas holga
    #  keltirardi. Matn HR uchun guruhlash belgisi.
    department: Mapped[str] = mapped_column(String(120), index=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    units: Mapped[int] = mapped_column(Integer, default=1)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), default=StaffPositionStatus.open.value, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProfileFieldKind(str, enum.Enum):
    """Xodim o'zgartirishni SO'RAY oladigan maydonlar (yangi TZ 3.26).

    ⚠️ OQ RO'YXAT. Ro'yxatdan tashqari maydon so'rovi rad etiladi:
    aks holda xodim `role`, `salary` yoki `is_active` ni «so'rab»
    yuborishi mumkin bo'lardi va HR e'tiborsiz tasdiqlab qo'yishi
    mumkin edi."""

    phone = "phone"
    address = "address"
    marital_status = "marital_status"
    emergency_contact = "emergency_contact"
    #  ⚠️ Bular OGOHLANTIRISH bilan (TZ 3-band): hujjatga ta'sir qiladi,
    #  shuning uchun HR ga tasdiqlashdan oldin eslatiladi.
    full_name = "full_name"


PROFILE_FIELD_LABELS: dict[str, str] = {
    ProfileFieldKind.phone.value: "Telefon",
    ProfileFieldKind.address.value: "Manzil",
    ProfileFieldKind.marital_status.value: "Oilaviy holat",
    ProfileFieldKind.emergency_contact.value: "Favqulodda aloqa",
    ProfileFieldKind.full_name.value: "F.I.Sh.",
}

#  Tasdiqlashdan oldin HR ga ogohlantirish ko'rsatiladigan maydonlar.
PROFILE_FIELDS_SENSITIVE: frozenset[str] = frozenset({ProfileFieldKind.full_name.value})


class ProfileChangeStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ProfileChangeRequest(Base):
    """Xodimning shaxsiy ma'lumotini o'zgartirish so'rovi (TZ 3.26 / S-26).

    NEGA SO'ROV, TO'G'RIDAN-TO'G'RI EMAS: telefon va manzil kadr
    hujjatlariga tushadi. Xodim ularni o'zi o'zgartira olsa, hujjatdagi
    va bazadagi ma'lumot bir-biriga mos kelmay qoladi va buni hech kim
    payqamaydi. HR tasdiqlashi — bu nomuvofiqlikni oldini oladigan
    yagona nuqta.

    ⚠️ ESKI QIYMAT SAQLANADI (`old_value`) va tasdiqlanganda AUDITGA
    ham yoziladi (TZ qabul mezoni): «bu odam telefonini qachon
    o'zgartirgan edi?» degan savolga javob kerak bo'ladi."""

    __tablename__ = "profile_change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    field: Mapped[str] = mapped_column(String(24), index=True)
    #  So'rov YUBORILGAN paytdagi qiymat. Tasdiqlashda qaytadan
    #  o'qilmaydi — HR aynan nimani ko'rib tasdiqlagani qolishi kerak.
    old_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    new_value: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        String(12), default=ProfileChangeStatus.pending.value, index=True
    )
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class HrInquiryCategory(str, enum.Enum):
    """Murojaat toifasi (yangi TZ 3.29 / S-28).

    ⚠️ AI HUKM CHIQARMAYDI (TZ 3-band) — u faqat TOIFANI taxmin
    qiladi. Javobni har doim odam yozadi va toifani HR o'zgartira
    oladi. Bu chegara ataylab: HR savoliga AI javob bersa, xato javob
    rasmiy pozitsiya sifatida qabul qilinardi."""

    salary = "salary"  # oylik, ushlanma, avans
    vacation = "vacation"  # ta'til, sababli kun
    documents = "documents"  # hujjat, ma'lumotnoma
    schedule = "schedule"  # ish jadvali, smena
    conditions = "conditions"  # ish sharoiti, mol-mulk
    other = "other"


HR_INQUIRY_CATEGORY_LABELS: dict[str, str] = {
    HrInquiryCategory.salary.value: "Oylik va to'lovlar",
    HrInquiryCategory.vacation.value: "Ta'til va sababli kun",
    HrInquiryCategory.documents.value: "Hujjatlar",
    HrInquiryCategory.schedule.value: "Ish jadvali",
    HrInquiryCategory.conditions.value: "Ish sharoiti",
    HrInquiryCategory.other.value: "Boshqa",
}


class HrInquiryStatus(str, enum.Enum):
    open = "open"  # javob kutilmoqda
    answered = "answered"
    closed = "closed"  # javobsiz yopilgan (takroriy, ahamiyatsiz)


class HrInquiry(Base):
    """Xodimning HR ga murojaati (yangi TZ 3.29 / S-28).

    NEGA JURNAL: xodimlar bir xil savolni qayta-qayta so'raydi va
    javoblar HR ning shaxsiy yozishmalarida qoladi. Kim nima so'raganini
    ham, qanday javob berilganini ham keyin topib bo'lmaydi — natijada
    ikki xodimga ikki xil javob berilishi mumkin.

    Jurnal S-29 uchun ham asos: takrorlanuvchi savollar bilim bazasiga
    ko'chiriladi va bot o'zi javob beradi.

    ⚠️ Xodim FAQAT o'z murojaatlarini ko'radi (TZ qabul mezoni) — bu
    ko'pincha shaxsiy savol (oylik, oilaviy sharoit)."""

    __tablename__ = "hr_inquiries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(16), default=HrInquiryCategory.other.value, index=True
    )
    #  Toifa AI tomonidan taxmin qilinganmi. HR uni o'zgartirsa `False`
    #  bo'ladi — S-29 hisobotida «AI qanchalik to'g'ri tasniflayapti»
    #  degan savolga javob shundan chiqadi.
    category_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(
        String(12), default=HrInquiryStatus.open.value, index=True
    )
    answered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #  S-29: shu javob bilim bazasiga ko'chirilganmi.
    knowledge_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #  Javobni ODAM emas, bilim bazasi bergan (S-29). Ajratib yuritiladi:
    #  (a) HR avto-javoblar to'g'ri ishlayotganini ko'rishi kerak,
    #  (b) takroriy savollar hisobotida avto-javob berilgani ham sanaladi
    #      — aks holda «bu savol endi berilmayapti» degan noto'g'ri
    #      xulosa chiqardi.
    auto_answered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ═════════════════════════════════════════════════════════════
# O'QUV PANELI (yangi TZ 3.1 / S-32)
#
# ⚠️ BU YANGI MEXANIZM EMAS — ANKETA mexanizmining kengaytmasi.
# Anketadan QAYTA ISHLATILADIGAN qismlar (S-32 qabul mezoni):
#
#   1. SAVOLLARNI MUZLATISH. `AnketaTemplate.questions` (JSON) naqshi:
#      savollar shablonga nusxa qilinadi va fayl keyin o'zgarsa ham
#      boshlangan sessiya savollari o'zgarmaydi. Bu yerda ham shunday —
#      `CourseQuestion` kursga NUSXA qilinadi, material fayliga bog'liq
#      emas.
#   2. HOLAT BAZADA, FSM DA EMAS. `AnketaAssignment.current_q` naqshi:
#      keyingi savolning 0-asosli indeksi bazada turadi. Sabab —
#      cPanel Passenger jarayoni har so'rovda qayta ko'tariladi va
#      xotiradagi holat yo'qoladi. S-33 dagi `course_assignments`
#      AYNAN shu naqshni oladi.
#   3. KETMA-KET SAVOL TICK'i. `/anketa/tick` (cron har daqiqa) vaqti
#      kelgan sessiyalarni boshlaydi; `/anketa/answer` javobni yozib
#      keyingi savolni qaytaradi va `{"handled": bool}` beradi — bot
#      shu bayroq bo'yicha xabarni boshqa oqimlarga o'tkazadi. O'quv
#      paneli shu protokolni takrorlaydi (S-35 da).
#   4. `.docx` DAN SAVOL AJRATISH. `api/services/docx_parse.py::
#      parse_questions` — yangi bog'liqliksiz (ZIP + XML). Kurs
#      savollari ham shundan yuklanadi, ikkinchi ajratgich YOZILMAYDI.
#   5. SAVOL MATNI NUSXASI. `AnketaAnswer.question_text` naqshi:
#      javob paytidagi savol matni saqlanadi, keyin shablon o'zgarsa
#      ham javob konteksti yo'qolmaydi (S-33 `course_results`).
#   6. FAYL SERVERDA SAQLANMAYDI. Anketa `.docx` ni bazaga yozmaydi,
#      faqat ajratilgan savollarni saqlaydi. Bu yerda ham material
#      VIDEOSI Telegram `file_id` sifatida turadi — disk cheklangan
#      (S-32 tuzog'i).
#
# ANKETADAN FARQI (nega alohida jadval kerak):
#   • anketa — BIR martalik sessiya (hamma bir vaqtda), kurs esa
#     xodimga ALOHIDA tayinlanadi va o'z tezligida o'tiladi;
#   • anketada javob BAHOLANMAYDI (u bilim yig'ish), kursda esa
#     to'g'ri javob va ball bor (S-33 `course_results`);
#   • kursda MATERIAL (video/matn) bor — anketada faqat savol.
#
# ⚠️ O'CHIRISH YUMSHOQ: `deleted_at`. Anketa `is_active` ishlatadi,
# lekin bu yerda TZ aniq `deleted_at` talab qiladi va u yaxshiroq —
# QACHON o'chirilgani ham saqlanadi. HAR BIR o'qish uni filtrlashi
# SHART, aks holda o'chirilgan kurs xodimga ko'rinib qolardi.
# ═════════════════════════════════════════════════════════════


class CourseMaterialKind(str, enum.Enum):
    """Material turi. `file_id` — Telegram fayl identifikatori."""

    video = "video"
    document = "document"
    photo = "photo"
    text = "text"  # faqat matn, fayl yo'q
    link = "link"


COURSE_MATERIAL_KIND_LABELS: dict[str, str] = {
    CourseMaterialKind.video.value: "Video",
    CourseMaterialKind.document.value: "Hujjat",
    CourseMaterialKind.photo.value: "Rasm",
    CourseMaterialKind.text.value: "Matn",
    CourseMaterialKind.link.value: "Havola",
}


class Course(Base):
    """O'quv kursi (yangi TZ 3.1 / S-32).

    Kurs = tartiblangan MATERIALLAR (video/matn) + ular oxiridagi
    SAVOLLAR. Xodimga tayinlanadi (S-33) va u o'z tezligida o'tadi.

    `pass_percent` — kursni o'tish uchun kerakli foiz. Kursda
    saqlanadi, sozlamada emas: turli kurslarga turli talab qo'yiladi
    (xavfsizlik yo'riqnomasi 100%, umumiy tanishtiruv 60%)."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #  Kursni o'tish uchun kerakli to'g'ri javob foizi (0-100).
    pass_percent: Mapped[int] = mapped_column(Integer, default=70)
    #  Nechta urinish beriladi. 0 — cheksiz.
    max_attempts: Mapped[int] = mapped_column(Integer, default=0)
    #  Nashr qilinmagan kurs xodimga tayinlanmaydi — HR uni tinch
    #  to'ldirib, tayyor bo'lgach ochadi.
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #  Majburiy kurs — o'tilmasa muddat eslatmasi (TZ 3.5) va HR
    #  tahlilida «majburiy kurs tugatish %» (TZ 3.31) shundan hisoblanadi.
    #  Ixtiyoriy kurs esa faqat taklif — u uchun eslatma yuborilmaydi.
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    #  ⚠️ YUMSHOQ o'chirish — o'tilgan kurs tarixi yo'qolmasin.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CourseMaterial(Base):
    """Kursning bitta materiali (video, hujjat yoki matn).

    ⚠️ FAYL SERVERDA SAQLANMAYDI — Telegram `file_id` yoziladi
    (anketa/kadr hujjatlari naqshi). Disk cheklangan, video esa eng
    og'ir fayl turi."""

    __tablename__ = "course_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    #  Ko'rsatish tartibi. Bo'shliq qoldirib beriladi (10, 20, 30) —
    #  oraga material qo'shish uchun hammasini qayta raqamlash shart
    #  bo'lmasin.
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    kind: Mapped[str] = mapped_column(String(12), default=CourseMaterialKind.text.value)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CourseQuestion(Base):
    """Kurs savoli (test yoki ochiq javob).

    ⚠️ Savollar kursga NUSXA qilinadi (`AnketaTemplate.questions`
    naqshi): `.docx` fayl keyin o'zgarsa ham boshlangan kurs savollari
    o'zgarmaydi — aks holda xodim yarim yo'lda boshqa savolni ko'rardi.

    `options` — variantlar ro'yxati (`["A", "B", ...]`), bo'sh bo'lsa
    savol OCHIQ javobli. `correct_index` — to'g'ri variant indeksi;
    ochiq savolda `None` va u AVTOMAT baholanmaydi (odam ko'radi).
    Bu chegara ataylab: ochiq javobni mashina baholasa, xodim noto'g'ri
    sababdan kursdan yiqilardi."""

    __tablename__ = "course_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, index=True)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)
    correct_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #  Savol nechta ball beradi — muhim savolga ko'proq ball.
    points: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CourseAssignmentStatus(str, enum.Enum):
    """Tayinlash holati (yangi TZ 3.1 / S-33)."""

    assigned = "assigned"  # tayinlandi, hali ochilmagan
    in_progress = "in_progress"  # boshlandi
    finished = "finished"  # yakunlandi (o'tdi yoki yiqildi — natijada)


class CourseAudience(str, enum.Enum):
    """Kurs kimga tayinlanadi.

    ⚠️ Qiymatlar `AnnouncementAudience` (S-21) bilan AYNAN bir xil va
    bu ataylab: `announcements.audience_user_ids()` qamrovni hal
    qiladigan YAGONA funksiya bo'lib qoladi. Uchinchi nusxa yozilsa,
    biri o'zgarib ikkinchisi eskirardi."""

    all = "all"
    roles = "roles"
    positions = "positions"
    users = "users"


class CourseAssignment(Base):
    """Xodimga tayinlangan kurs (yangi TZ 3.1 / S-33).

    ⚠️ HOLAT BAZADA, FSM DA EMAS — `AnketaAssignment.current_q` naqshi.
    Sabab: cPanel Passenger jarayoni har so'rovda qayta ko'tarilishi
    mumkin va xotiradagi holat yo'qoladi. Xodim yarim yo'lda turgan
    kursini qaytadan boshlashi kerak bo'lardi.

    `current_material` / `current_q` — TARTIBLANGAN tirik ro'yxatdagi
    0-asosli indeks (id EMAS). Material o'chirilsa ro'yxat qisqaradi va
    indeks o'z-o'zidan keyingi bandga suriladi.

    `answers` — joriy urinishning javoblari:
    `[{"q": <savol_id>, "text": <matn>, "choice": <indeks|null>,
       "correct": <true|false|null>}]`.
    ⚠️ Alohida jadval ATAYLAB yaratilmadi (TZ S-33 ikkita jadval
    ko'rsatadi). Ochiq javob matni SAQLANISHI SHART — u avtomat
    baholanmaydi (`correct=null`) va odam ko'radi; javobsiz uni
    baholab bo'lmasdi. Urinish yakunlanganda javoblar
    `CourseResult.answers` ga NUSXA qilinadi va bu maydon
    keyingi urinish uchun tozalanadi."""

    #  ⚠️ BIR XODIMGA BIR KURS IKKI MARTA TAYINLANMAYDI (S-33 qabul
    #  mezoni) — `uq_course_assignment_active` QISMAN unique indeksi,
    #  `deleted_at IS NULL` shartli. U MIGRATSIYADA e'lon qilinadi
    #  (loyiha naqshi: qisman indekslar modelda emas, migratsiyada —
    #  `as01b2c3d4e5_assets`, `x3y4z5a6b7c8_deadlines`).
    #
    #  Nega QISMAN, to'liq emas: yillik qayta o'qitish (xavfsizlik
    #  yo'riqnomasi har yili qayta o'tiladi) to'liq unique bilan UMUMAN
    #  mumkin bo'lmasdi. Eskisini yumshoq o'chirib yangisini tayinlash
    #  yo'li ochiq qoladi, tarix esa saqlanadi.
    __tablename__ = "course_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(12), default=CourseAssignmentStatus.assigned.value, index=True
    )
    current_material: Mapped[int] = mapped_column(Integer, default=0)
    current_q: Mapped[int] = mapped_column(Integer, default=0)
    #  Joriy urinish raqami (1 dan boshlanadi).
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    answers: Mapped[list] = mapped_column(JSON, default=list)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class CourseResult(Base):
    """Bitta URINISH natijasi (yangi TZ 3.1 / S-33).

    Har urinish uchun ALOHIDA qator — eskisi o'chirilmaydi. Sabab:
    «uch marta yiqilib, to'rtinchida o'tdi» degan ma'lumot kadr
    bo'limiga kerak, faqat oxirgi natija emas.

    `pending_review` — ochiq savollar bor va ular hali odam tomonidan
    baholanmagan. Bunday urinish `passed` bo'la olmaydi: ball to'liq
    emas."""

    __tablename__ = "course_results"
    __table_args__ = (
        UniqueConstraint("assignment_id", "attempt_no", name="uq_course_result_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("course_assignments.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[int] = mapped_column(Integer, default=0)
    max_score: Mapped[int] = mapped_column(Integer, default=0)
    percent: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pending_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #  Urinish javoblarining NUSXASI (savol matni bilan birga) —
    #  `AnketaAnswer.question_text` naqshi: kurs savoli keyin
    #  o'zgarsa ham javob konteksti yo'qolmaydi.
    answers: Mapped[list] = mapped_column(JSON, default=list)
    finished_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CourseStat(Base):
    """Kurs bo'yicha YIG'MA raqamlar (yangi TZ 3.1 / S-37).

    ⚠️ NEGA ALOHIDA JADVAL: ro'yxat sahifasi har kurs uchun material,
    savol va tayinlash sonini ALOHIDA so'rov bilan olardi (S-34 da
    kiritilgan N+1). Kurslar ko'paygach bu sahifani sekinlashtiradi,
    cPanel'da esa konkurentlik = 1 — bitta sekin so'rov BUTUN saytni
    kutdiradi.

    Shuning uchun raqamlar CRON'da hisoblanadi (S-07 naqshi) va
    sahifa tayyor qatorni o'qiydi. Ma'lumot bir necha daqiqa
    eskirishi mumkin — bu HISOBOT, real vaqt emas.

    ⚠️ Bu jadval faqat KESH: yo'qolsa ham hech narsa buzilmaydi,
    keyingi tick qayta hisoblaydi."""

    __tablename__ = "course_stats"

    #  Kurs bilan 1:1 — `course_id` ning o'zi kalit.
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True
    )
    material_count: Mapped[int] = mapped_column(Integer, default=0)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    assigned_count: Mapped[int] = mapped_column(Integer, default=0)
    #  Boshlamagan / boshlagan / yakunlagan.
    not_started: Mapped[int] = mapped_column(Integer, default=0)
    in_progress: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    #  Ochiq savoli bor, HR baholashini kutmoqda.
    pending_review: Mapped[int] = mapped_column(Integer, default=0)
    #  Muddati o'tgan va hali yakunlanmagan.
    overdue: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class JobDescription(Base):
    """Lavozim yo'riqnomasi — VERSIYALANADI (yangi TZ 3.16 / S-39).

    ⚠️ TAHRIRLANMAYDI, YANGI VERSIYA QO'SHILADI (TZ 4-band). Sabab:
    yo'riqnoma — huquqiy hujjat. Xodim uni o'qib «tanishdim» degan
    bo'lsa (S-20), keyin matn jimgina o'zgarsa, u AYNAN NIMAGA rozi
    bo'lgani noma'lum bo'lib qolardi. Eski versiya o'z holicha qoladi
    va tanishish yozuvi o'sha versiyaga bog'lanadi.

    `version` — 1 dan boshlab o'sadi, `(position_id, version)` unique.
    `effective_from` — qachondan kuchga kiradi; kelajakdagi sana bilan
    oldindan tayyorlab qo'yish mumkin.

    Matn maydonlari ATAYLAB alohida (bitta katta matn emas): TZ ular
    ro'yxatini aniq beradi va sxemada har biri alohida ko'rsatiladi."""

    __tablename__ = "job_descriptions"
    __table_args__ = (
        UniqueConstraint("position_id", "version", name="uq_job_description_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)
    #  Lavozim maqsadi — «bu lavozim nima uchun bor».
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    #  Vazifalar ro'yxati: ["...", "..."].
    duties: Mapped[list] = mapped_column(JSON, default=list)
    rights: Mapped[list] = mapped_column(JSON, default=list)
    responsibility: Mapped[list] = mapped_column(JSON, default=list)
    requirements: Mapped[list] = mapped_column(JSON, default=list)
    effective_from: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyProfile(Base):
    """Kompaniya haqida — YAGONA qator (id=1).

    Missiya, qadriyatlar va strategik maqsadlar (yangi TZ 3.16).
    Yagona qator naqshi loyihada allaqachon bor (`AttendanceDigestConfig`,
    `DeadlineConfig`) — sozlama jadvali emas, bitta hujjat."""

    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    values: Mapped[list] = mapped_column(JSON, default=list)
    goals: Mapped[list] = mapped_column(JSON, default=list)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ─────────────────────────────────────────────────────────────
# ONBOARDING — «birinchi kunlar» (yangi TZ 3.2 / S-45)
# ─────────────────────────────────────────────────────────────


class OnboardingStepKind(str, enum.Enum):
    """Qadam turi — u BOSHQA MODULGA BOG'LANADI (TZ 3.2).

    Ro'yxat YOPIQ: har tur uchun tizimda aniq bir mexanizm bor va
    yangi tur qo'shish o'sha mexanizmni ham ulashni talab qiladi."""

    task = "task"  # oddiy vazifa (matn bilan)
    document = "document"  # kadr hujjati kutiladi (3.4)
    course = "course"  # kurs tayinlanadi (3.1)
    briefing = "briefing"  # instruktaj bilan tanishish (3.6)
    meeting = "meeting"  # uchrashuv (rahbar/jamoa bilan)


class OnboardingStatus(str, enum.Enum):
    active = "active"
    done = "done"
    cancelled = "cancelled"


class OnboardingTemplate(Base):
    """Onboarding SHABLONI — lavozim yoki rol uchun (TZ 3.2 / S-45).

    ⚠️ SHABLON — ANDOZA, REJA EMAS. Reja yaratilganda qadamlar
    NUSXALANADI (`OnboardingProgress`). Sabab `AnketaTemplate` bilan
    bir xil: shablon keyin tahrirlansa, YO'LDA turgan xodimning
    ro'yxati o'zgarib ketardi — u kecha ko'rgan qadam bugun
    yo'qolardi yoki muddat siljib ketardi.

    ⚠️ `position_id` yoki `role` — IKKALASI HAM ixtiyoriy. Ikkalasi
    ham bo'sh bo'lsa shablon UMUMIY (hamma uchun zaxira). Aniqroq
    moslik ustun: avval lavozim, keyin rol, keyin umumiy."""

    __tablename__ = "onboarding_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True, index=True
    )
    role: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    #  Yumshoq o'chirish — `courses` naqshi. Shablon o'chirilsa ham
    #  undan yaratilgan REJALAR tirik qoladi.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    steps: Mapped[list["OnboardingStep"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class OnboardingStep(Base):
    """Shablon qadami — ANDOZA bandi (TZ 3.2 / S-45).

    ⚠️ `due_offset_days` — MUTLAQ SANA EMAS, ishga chiqishdan
    keyingi kunlar soni. Shablon barcha xodim uchun umumiy, ya'ni
    unda aniq sana bo'lishi mumkin emas; sana reja yaratilganda
    hisoblanadi (`plan.start_date + offset`).

    `ref_id` — qadam turi bo'yicha bog'lanish nishoni:
      • `course`   -> `courses.id`
      • `document` -> `DocumentType` qiymati `ref_text` da
      • qolganlari -> ishlatilmaydi."""

    __tablename__ = "onboarding_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("onboarding_templates.id"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(16), default=OnboardingStepKind.task.value, index=True
    )
    #  Mas'ul ROL (aniq odam emas): shablon uzoq yashaydi va aniq
    #  odam ishdan bo'shashi mumkin. Aniq odam reja yaratilganda
    #  hisoblanadi.
    owner_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    due_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    template: Mapped["OnboardingTemplate"] = relationship(back_populates="steps")


class OnboardingPlan(Base):
    """Bitta xodimning onboarding REJASI (TZ 3.2 / S-45).

    ⚠️ BIR XODIMDA BIR VAQTDA BITTA FAOL REJA. Ikkinchisi
    yaratilsa xodimda ikkita «birinchi kunlarim» ro'yxati paydo
    bo'lardi va qaysi biri haqiqiy ekani noma'lum bo'lardi.
    Chegara MIGRATSIYADA — qisman unique indeks (`status='active'`
    bo'lganlar uchun), chunki tugagan rejalar tarix bo'lib qoladi
    va ular uchun cheklov bo'lmasligi kerak."""

    __tablename__ = "onboarding_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    #  Shablon nomi NUSXASI — shablon keyin o'chirilsa/qayta
    #  nomlansa ham reja nimadan yaratilgani ko'rinib tursin.
    template_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(
        String(12), default=OnboardingStatus.active.value, index=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["OnboardingProgress"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )


class OnboardingProgress(Base):
    """Reja bandi — SHABLON QADAMINING NUSXASI (TZ 3.2 / S-45).

    ⚠️ NUSXA, HAVOLA EMAS. `title`, `kind`, `due_date` shu yerda
    saqlanadi. Shablon keyin tahrirlansa yo'lda turgan xodimning
    ro'yxati O'ZGARMAYDI — bu `AnketaAnswer.question_text` va
    `Acknowledgement.title` bilan bir xil naqsh: odam NIMANI
    ko'rgan bo'lsa, o'sha saqlanadi.

    `ref_id` — qadam boshqa modulda yaratgan yozuv (masalan
    `CourseAssignment.id`). Shu orqali «kurs o'tildimi?» degan
    savolga javob beriladi — holat IKKI JOYDA saqlanmaydi."""

    __tablename__ = "onboarding_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default=OnboardingStepKind.task.value)
    owner_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    #  Qadam boshqa modulda yaratgan yozuv (kurs tayinlovi, vazifa).
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    done_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped["OnboardingPlan"] = relationship(back_populates="items")
