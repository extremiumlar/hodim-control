import html
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import (
    TaskBotCreate,
    TaskBulkBotCreate,
    TaskBulkCreate,
    TaskCompleteRequest,
    TaskCreate,
    TaskOut,
    UserOut,
)
from api.routers.norms import is_orphan_employee
from api.telegram_notify import inline_keyboard, send_message
from api.timeutil import local_range_utc_naive, today_local
from db.models import AuditLog, Role, TaskModel, TaskStatus, User

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Vazifa bera oladigan rollar (umumiy tekshiruv; kimga berishi mumkinligi
# `_can_assign` matritsasida aniqlanadi).
MANAGER_ROLES = {Role.boss.value, Role.dasturchi.value, Role.rop.value, Role.hr.value}


def _can_assign(actor: User, target: User) -> bool:
    """Vazifa berish matritsasi:
    - Dasturchi — hammaga (boshliq ham kiradi);
    - Boshliq — ROP, HR va xodimlarga (alohida yoki ommaviy);
    - ROP (sotuv boshlig'i) — o'z jamoasidagi sotuvchilarga (manager_id), yoki
      lavozimi "ROP boshqaradi" deb belgilangan xodimlarga;
    - HR — faqat lavozimi "HR boshqaradi" deb belgilangan xodimlarga
      (masalan mobilograf, dasturchi-xodim lavozimlari), hamda zaxira sifatida
      "yetim" (rahbarsiz va boshqaruvchi-rolsiz) xodimlarga."""
    if not target.is_active or target.id == actor.id:
        return False
    if actor.role == Role.dasturchi.value:
        return True
    if actor.role == Role.boss.value:
        return target.role in {Role.employee.value, Role.rop.value, Role.hr.value}
    if actor.role == Role.rop.value:
        if target.role != Role.employee.value:
            return False
        if target.manager_id == actor.id:
            return True
        position = target.position
        return bool(position and position.managed_by_roles and Role.rop.value in position.managed_by_roles)
    if actor.role == Role.hr.value:
        if target.role != Role.employee.value:
            return False
        position = target.position
        if position and position.managed_by_roles and Role.hr.value in position.managed_by_roles:
            return True
        return is_orphan_employee(target)
    return False


async def _to_out(task: TaskModel, db: AsyncSession) -> TaskOut:
    assignee = await db.get(User, task.assigned_to)
    return TaskOut(
        id=task.id,
        assigned_by=task.assigned_by,
        assigned_to=task.assigned_to,
        assigned_to_name=assignee.full_name if assignee else "?",
        title=task.title,
        description=task.description,
        deadline=task.deadline,
        status=task.status,
        completed_at=task.completed_at,
        created_at=task.created_at,
    )


async def _to_out_many(tasks: list[TaskModel], db: AsyncSession) -> list[TaskOut]:
    """`_to_out`ning ro'yxat versiyasi — har bir vazifa uchun alohida `assigned_to`
    so'rovi yubormaslik uchun (N+1) barcha kerakli userlarni bitta so'rovda oladi."""
    assignee_ids = {t.assigned_to for t in tasks}
    assignees = list(await db.scalars(select(User).where(User.id.in_(assignee_ids))))
    name_by_id = {u.id: u.full_name for u in assignees}
    return [
        TaskOut(
            id=t.id,
            assigned_by=t.assigned_by,
            assigned_to=t.assigned_to,
            assigned_to_name=name_by_id.get(t.assigned_to, "?"),
            title=t.title,
            description=t.description,
            deadline=t.deadline,
            status=t.status,
            completed_at=t.completed_at,
            created_at=t.created_at,
        )
        for t in tasks
    ]


async def _create_task_record(
    db: AsyncSession,
    actor: User,
    assignee: User,
    title: str,
    description: str | None,
    deadline,
) -> TaskModel:
    task = TaskModel(
        assigned_by=actor.id,
        assigned_to=assignee.id,
        title=title,
        description=description,
        deadline=deadline,
        status=TaskStatus.pending.value,
    )
    db.add(task)
    await db.flush()

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="task_created",
            target_user_id=assignee.id,
            before=None,
            after={"title": task.title, "deadline": task.deadline.isoformat() if task.deadline else None},
        )
    )
    await db.commit()
    await db.refresh(task)

    if assignee.telegram_id:
        deadline_text = f"\nMuddat: {task.deadline:%Y-%m-%d %H:%M}" if task.deadline else ""
        text = f"🆕 <b>Yangi vazifa</b> ({actor.full_name} tomonidan)\n{html.escape(task.title)}{deadline_text}"
        await send_message(
            assignee.telegram_id,
            text,
            inline_keyboard([[("✅ Bajardim", f"task_done:{task.id}")]]),
        )

    return task


async def _resolve_assignee(db: AsyncSession, actor: User, assigned_to: int) -> User:
    assignee = await db.get(User, assigned_to)
    if not assignee or not _can_assign(actor, assignee):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bu foydalanuvchiga vazifa bera olmaysiz")
    return assignee


def _can_manage_existing_task(actor: User, assignee: User) -> bool:
    """Mavjud vazifani bekor qilish uchun — `_can_assign` bilan bir xil rol
    ierarxiyasi, lekin "yangi vazifa berish"ga xos cheklovlarsiz (masalan xodim
    keyinchalik faolsizlantirilgan bo'lsa ham, avvalgi vazifasini bekor qilish
    kerak bo'lishi mumkin): Dasturchi — hammaga; Boshliq — ROP/HR/xodimlarga;
    ROP — o'z jamoasi yoki lavozimi orqali boshqaradigan xodimlarga."""
    if actor.role == Role.dasturchi.value:
        return True
    if actor.role == Role.boss.value:
        return assignee.role in {Role.employee.value, Role.rop.value, Role.hr.value}
    if actor.role == Role.rop.value:
        if assignee.role != Role.employee.value:
            return False
        if assignee.manager_id == actor.id:
            return True
        position = assignee.position
        return bool(position and position.managed_by_roles and Role.rop.value in position.managed_by_roles)
    return False


@router.post("", response_model=TaskOut)
async def create_task(
    payload: TaskCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    assignee = await _resolve_assignee(db, actor, payload.assigned_to)
    task = await _create_task_record(db, actor, assignee, payload.title, payload.description, payload.deadline)
    return await _to_out(task, db)


@router.post("/bot-create", response_model=TaskOut, dependencies=[Depends(verify_bot_secret)])
async def bot_create_task(payload: TaskBotCreate, db: AsyncSession = Depends(get_db)) -> TaskOut:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.assigner_telegram_id))
    if not actor or actor.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    assignee = await _resolve_assignee(db, actor, payload.assigned_to)
    task = await _create_task_record(db, actor, assignee, payload.title, payload.description, payload.deadline)
    return await _to_out(task, db)


@router.get(
    "/assignable-users/{telegram_id}", response_model=list[UserOut], dependencies=[Depends(verify_bot_secret)]
)
async def assignable_users(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[User]:
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    if actor.role not in MANAGER_ROLES:
        return []

    candidates = list(
        await db.scalars(
            select(User).where(User.is_active == True).order_by(User.full_name)  # noqa: E712
        )
    )
    # Matritsa bo'yicha filtrlash (HR uchun lavozim tekshiruvi Python tomonda —
    # position relationship selectin bilan yuklanadi, foydalanuvchilar soni kichik).
    return [u for u in candidates if _can_assign(actor, u)]


async def _resolve_bulk_targets(db: AsyncSession, payload: TaskBulkCreate) -> list[User]:
    """Ommaviy vazifa nishonlarini aniqlaydi: barcha xodimlar / rol(lar) bo'yicha /
    lavozim bo'yicha."""
    if payload.target_type == "all_employees":
        query = select(User).where(User.role == Role.employee.value, User.is_active == True)  # noqa: E712
    elif payload.target_type == "role":
        allowed = {Role.rop.value, Role.hr.value, Role.employee.value}
        roles = [r for r in (payload.target_roles or []) if r in allowed]
        if not roles:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rol(lar) ko'rsatilmagan yoki noto'g'ri")
        query = select(User).where(User.role.in_(roles), User.is_active == True)  # noqa: E712
    else:  # position
        if not payload.position_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lavozim ko'rsatilmagan")
        query = select(User).where(User.position_id == payload.position_id, User.is_active == True)  # noqa: E712

    return list(await db.scalars(query.order_by(User.full_name)))


async def _create_bulk_tasks(db: AsyncSession, actor: User, payload: TaskBulkCreate) -> dict:
    targets = [u for u in await _resolve_bulk_targets(db, payload) if u.id != actor.id]
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tanlangan nishonda hech kim topilmadi")

    for target in targets:
        await _create_task_record(db, actor, target, payload.title, payload.description, payload.deadline)

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="task_bulk_created",
            target_user_id=None,
            before=None,
            after={
                "title": payload.title,
                "target_type": payload.target_type,
                "target_roles": payload.target_roles,
                "position_id": payload.position_id,
                "count": len(targets),
            },
        )
    )
    await db.commit()

    return {"created": len(targets)}


@router.post("/bulk")
async def create_bulk_tasks(
    payload: TaskBulkCreate,
    actor: User = Depends(require_roles(Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ommaviy vazifa (faqat Boshliq/Dasturchi): barcha xodimlarga, rol bo'yicha
    (ROPlarga, HRlarga yoki ikkalasiga umumiy) yoki lavozim bo'yicha."""
    return await _create_bulk_tasks(db, actor, payload)


@router.post("/bot-bulk-create", dependencies=[Depends(verify_bot_secret)])
async def bot_create_bulk_tasks(payload: TaskBulkBotCreate, db: AsyncSession = Depends(get_db)) -> dict:
    actor = await db.scalar(select(User).where(User.telegram_id == payload.assigner_telegram_id))
    if not actor or actor.role not in {Role.boss.value, Role.dasturchi.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    return await _create_bulk_tasks(db, actor, payload)


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    date_filter: str | None = "today",
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    query = select(TaskModel).order_by(TaskModel.created_at.desc())
    if date_filter and date_filter != "all":
        target_date = today_local() if date_filter == "today" else date.fromisoformat(date_filter)
        start_utc, end_utc = local_range_utc_naive(target_date, target_date)
        query = query.where(
            TaskModel.created_at >= start_utc,
            TaskModel.created_at < end_utc,
        )
    if actor.role == Role.rop.value:
        query = query.where(TaskModel.assigned_to.in_(select(User.id).where(User.manager_id == actor.id)))
    tasks = list(await db.scalars(query))
    return await _to_out_many(tasks, db)


@router.get(
    "/overview/{telegram_id}", response_model=list[TaskOut], dependencies=[Depends(verify_bot_secret)]
)
async def bot_tasks_overview(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[TaskOut]:
    """Bot "📋 Vazifalar nazorati" tugmasi uchun: bugungi (Toshkent) barcha
    vazifalar — kim bajardi, kim bajarmadi. ROP faqat o'z jamoasini ko'radi
    (web'dagi list_tasks bilan bir xil qamrov)."""
    actor = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not actor or actor.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu amal uchun ruxsat yo'q")

    start_utc, end_utc = local_range_utc_naive(today_local(), today_local())
    query = (
        select(TaskModel)
        .where(TaskModel.created_at >= start_utc, TaskModel.created_at < end_utc)
        .order_by(TaskModel.status.desc(), TaskModel.created_at)
    )
    if actor.role == Role.rop.value:
        query = query.where(TaskModel.assigned_to.in_(select(User.id).where(User.manager_id == actor.id)))
    tasks = list(await db.scalars(query))
    return await _to_out_many(tasks, db)


@router.get("/my/{telegram_id}", response_model=list[TaskOut], dependencies=[Depends(verify_bot_secret)])
async def list_my_tasks(telegram_id: int, db: AsyncSession = Depends(get_db)) -> list[TaskOut]:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foydalanuvchi topilmadi")

    query = (
        select(TaskModel)
        .where(TaskModel.assigned_to == user.id)
        .order_by(TaskModel.created_at.desc())
        .limit(20)
    )
    tasks = list(await db.scalars(query))
    return await _to_out_many(tasks, db)


@router.post("/send-reminders", dependencies=[Depends(verify_bot_secret)])
async def send_reminders(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tomonidan kun davomida bir necha marta chaqiriladi — hali bajarilmagan
    barcha vazifalar uchun xodimga eslatma qayta yuboriladi."""
    query = select(TaskModel).where(TaskModel.status == TaskStatus.pending.value)
    pending_tasks = list(await db.scalars(query))

    sent = 0
    for task in pending_tasks:
        assignee = await db.get(User, task.assigned_to)
        if not assignee or not assignee.telegram_id:
            continue
        deadline_text = f"\nMuddat: {task.deadline:%Y-%m-%d %H:%M}" if task.deadline else ""
        text = f"⏰ <b>Eslatma:</b> vazifa hali bajarilmagan\n{html.escape(task.title)}{deadline_text}"
        result = await send_message(
            assignee.telegram_id,
            text,
            inline_keyboard([[("✅ Bajardim", f"task_done:{task.id}")]]),
        )
        if result:
            sent += 1

    return {"pending_count": len(pending_tasks), "reminders_sent": sent}


@router.post("/{task_id}/complete", response_model=TaskOut, dependencies=[Depends(verify_bot_secret)])
async def complete_task(task_id: int, payload: TaskCompleteRequest, db: AsyncSession = Depends(get_db)) -> TaskOut:
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vazifa topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or user.id != task.assigned_to:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu vazifa sizga tegishli emas")

    if task.status == TaskStatus.done.value:
        # Idempotent: ✅ tugma ikkinchi marta bosilsa completed_at qayta yozilmaydi
        # va takroriy audit yozuvi yaratilmaydi — foydalanuvchiga xato ko'rsatilmaydi.
        return await _to_out(task, db)

    task.status = TaskStatus.done.value
    task.completed_at = datetime.utcnow()

    db.add(
        AuditLog(
            actor_id=user.id,
            action="task_completed",
            target_user_id=user.id,
            before={"status": TaskStatus.pending.value},
            after={"status": TaskStatus.done.value},
        )
    )
    await db.commit()
    await db.refresh(task)
    return await _to_out(task, db)


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(
    task_id: int,
    actor: User = Depends(require_roles(Role.boss.value, Role.rop.value, Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    """Vazifani bekor qiladi (status=cancelled) — o'chirilmaydi, tarix audit
    jurnalida saqlanadi. Boshliq/ROP/Dasturchi uchun; ROP faqat o'zi boshqaradigan
    xodimning vazifasini bekor qila oladi. Butunlay o'chirish uchun (Dasturchi)
    `DELETE /tasks/{id}`dan foydalaning."""
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vazifa topilmadi")

    assignee = await db.get(User, task.assigned_to)
    if not assignee or not _can_manage_existing_task(actor, assignee):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bu vazifani bekor qilish huquqingiz yo'q")

    if task.status == TaskStatus.cancelled.value:
        return await _to_out(task, db)  # idempotent
    if task.status == TaskStatus.done.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bajarilgan vazifani bekor qilib bo'lmaydi")

    before_status = task.status
    task.status = TaskStatus.cancelled.value

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="task_cancelled",
            target_user_id=assignee.id,
            before={"status": before_status},
            after={"status": TaskStatus.cancelled.value},
        )
    )
    await db.commit()
    await db.refresh(task)

    if assignee.telegram_id:
        await send_message(assignee.telegram_id, f"❌ Vazifangiz bekor qilindi:\n{html.escape(task.title)}")

    return await _to_out(task, db)


@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    actor: User = Depends(require_roles(Role.dasturchi.value)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Vazifani bazadan butunlay o'chiradi. Faqat Dasturchi uchun — Boshliq/ROP
    "Bekor qilish" (`POST /{id}/cancel`, tarix saqlanadi) bilan cheklanadi."""
    task = await db.get(TaskModel, task_id)
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vazifa topilmadi")

    db.add(
        AuditLog(
            actor_id=actor.id,
            action="task_deleted",
            target_user_id=task.assigned_to,
            before={"id": task.id, "title": task.title, "status": task.status},
            after=None,
        )
    )
    await db.delete(task)
    await db.commit()
    return {"deleted": True}
