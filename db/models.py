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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    team: Mapped["Team | None"] = relationship(back_populates="users", foreign_keys=[team_id])
    manager: Mapped["User | None"] = relationship(remote_side=[id])
    position: Mapped["Position | None"] = relationship(back_populates="users", lazy="selectin")


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
    yuboradi. `last_posted_date` — bir kunda ikki marta yubormaslik uchun qo'riqchi."""

    __tablename__ = "group_post_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # doim 1
    post_hour: Mapped[int] = mapped_column(Integer, default=19)
    post_minute: Mapped[int] = mapped_column(Integer, default=10)
    last_posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
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
