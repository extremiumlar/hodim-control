from datetime import date, datetime

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    telegram_id: int | None
    full_name: str
    role: str
    team_id: int | None
    manager_id: int | None
    bot_started: bool
    is_active: bool
    crm_external_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCrmIdUpdate(BaseModel):
    crm_external_id: str | None = None


class UserRoleUpdate(BaseModel):
    role: str


class UserCreate(BaseModel):
    full_name: str
    role: str
    team_id: int | None = None
    manager_id: int | None = None


class UserCreateOut(BaseModel):
    user: UserOut
    invite_link: str


class DevLoginRequest(BaseModel):
    telegram_id: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TelegramStartRequest(BaseModel):
    telegram_id: int
    invite_token: str | None = None


class TelegramStartResponse(BaseModel):
    status: str  # ok | invalid_token | already_linked | no_account
    user: UserOut | None = None


class TaskCreate(BaseModel):
    assigned_to: int
    title: str
    description: str | None = None
    deadline: datetime | None = None


class TaskBotCreate(BaseModel):
    assigner_telegram_id: int
    assigned_to: int
    title: str
    description: str | None = None
    deadline: datetime | None = None


class TaskOut(BaseModel):
    id: int
    assigned_by: int
    assigned_to: int
    assigned_to_name: str
    title: str
    description: str | None
    deadline: datetime | None
    status: str
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskCompleteRequest(BaseModel):
    telegram_id: int


class ExcusedDayCreate(BaseModel):
    telegram_id: int
    date: date
    reason: str


class ExcusedDayOut(BaseModel):
    id: int
    user_id: int
    user_full_name: str
    date: date
    reason: str
    status: str
    decided_by: int | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExcusedDayDecide(BaseModel):
    decider_telegram_id: int
    decision: str  # approved | rejected


class NormCreate(BaseModel):
    user_id: int
    metric_type: str  # suhbat | tashrif
    value: int


class NormBotUpdate(BaseModel):
    changer_telegram_id: int
    target_user_id: int
    metric_type: str
    value: int


class NormOut(BaseModel):
    id: int
    user_id: int
    metric_type: str
    value: int
    changed_by: int
    effective_from: date
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamNormRow(BaseModel):
    user_id: int
    full_name: str
    suhbat: int | None
    tashrif: int | None


class MobilografCreate(BaseModel):
    telegram_id: int
    telegram_message_id: int
    group_chat_id: int


class MobilografReact(BaseModel):
    group_chat_id: int
    telegram_message_id: int
    reactor_telegram_id: int
    action: str  # add | remove


class MobilografOut(BaseModel):
    id: int
    user_id: int
    telegram_message_id: int
    group_chat_id: int
    sent_at: datetime
    status: str
    confirmed_by: int | None
    confirmed_at: datetime | None

    model_config = {"from_attributes": True}


class DailyResultManualCreate(BaseModel):
    user_id: int
    date: date
    conversations_count: int
    visits_count: int


class DailyResultOut(BaseModel):
    id: int
    user_id: int
    date: date
    conversations_count: int
    visits_count: int
    source: str
    raw_data: dict | None

    model_config = {"from_attributes": True}


class DailyResultTodayOut(BaseModel):
    conversations_count: int
    visits_count: int
    suhbat_norm: int | None
    tashrif_norm: int | None


class CRMWebhookPayload(BaseModel):
    crm_external_id: str
    date: date
    conversations: int
    visits: int


class BonusOut(BaseModel):
    id: int
    user_id: int
    period: str
    amount: float
    calculated_at: datetime
    breakdown: dict | None

    model_config = {"from_attributes": True}


class BonusMyOut(BaseModel):
    calculated: bool
    period: str | None = None
    calculated_at: datetime | None = None


class AuditLogOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    target_user_id: int | None
    target_name: str | None
    before: dict | None
    after: dict | None
    created_at: datetime
