import enum
from datetime import date, datetime

from sqlalchemy import JSON, DateTime, Date, ForeignKey, String, Boolean, Integer, Numeric, Text, UniqueConstraint
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


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    telegram_group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

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
    # ["suhbat", "tashrif", "video"] — shu lavozim uchun kuzatiladigan ko'rsatkichlar
    metrics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ["rop"] yoki ["hr"] — qaysi rahbar rol shu lavozimga vazifa/norma belgilay oladi
    # (boss/dasturchi har doim hammani boshqaradi, ro'yxatga kiritish shart emas)
    managed_by_roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="position")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)
    bot_started: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["Team | None"] = relationship(back_populates="users", foreign_keys=[team_id])
    manager: Mapped["User | None"] = relationship(remote_side=[id])
    position: Mapped["Position | None"] = relationship(back_populates="users", lazy="selectin")

    @property
    def has_face(self) -> bool:
        return bool(self.face_descriptor)


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


class Norm(Base):
    __tablename__ = "norms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    metric_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


class MobilografVideo(Base):
    __tablename__ = "mobilograf_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Qo'lda kiritilgan ("manual" source) yozuvlarda Telegram xabari yo'q — NULL.
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_chat_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), default=MobilografStatus.pending.value)
    # telegram_reaction — guruhdagi reaksiya orqali; manual — HR/rahbar qo'lda kiritgan
    # (masalan TELEGRAM_GROUP_CHAT_ID sozlanmagan yoki guruh ishlamay qolgan holat uchun).
    source: Mapped[str] = mapped_column(String(20), default=MobilografSource.telegram_reaction.value)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ExcusedDay(Base):
    __tablename__ = "excused_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ExcusedStatus.pending.value)
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
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)  # FACEBOOK_FORM ...
    responsible_crm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # responsibleById
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_ts: Mapped[int] = mapped_column(Integer)  # CRM createdTimestamp (unix sekund)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_call_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Lid yaratilishidan birinchi aloqa qo'ng'irog'igacha sekund (speed-to-lead)
    first_call_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="notified", index=True)


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


class AnketaSessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


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
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_anketa_assignment_user"),
        UniqueConstraint("session_id", "toplam", name="uq_anketa_assignment_toplam"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("anketa_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    toplam: Mapped[int] = mapped_column(Integer)
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
