from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db, require_roles, verify_bot_secret
from api.schemas import TaskCompleteRequest, TaskCreate, TaskOut
from api.telegram_notify import inline_keyboard, send_message
from db.models import AuditLog, Role, TaskModel, TaskStatus, User

router = APIRouter(prefix="/tasks", tags=["tasks"])


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


@router.post("", response_model=TaskOut)
async def create_task(
    payload: TaskCreate,
    actor: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    assignee = await db.get(User, payload.assigned_to)
    if not assignee or assignee.role != Role.employee.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Xodim topilmadi")

    task = TaskModel(
        assigned_by=actor.id,
        assigned_to=assignee.id,
        title=payload.title,
        description=payload.description,
        deadline=payload.deadline,
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
        text = f"🆕 <b>Yangi vazifa</b>\n{task.title}{deadline_text}"
        await send_message(
            assignee.telegram_id,
            text,
            inline_keyboard([[("✅ Bajardim", f"task_done:{task.id}")]]),
        )

    return await _to_out(task, db)


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    date_filter: str | None = "today",
    _: User = Depends(require_roles(Role.hr.value, Role.rop.value, Role.boss.value)),
    db: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    query = select(TaskModel).order_by(TaskModel.created_at.desc())
    if date_filter and date_filter != "all":
        target_date = date.today() if date_filter == "today" else date.fromisoformat(date_filter)
        query = query.where(
            TaskModel.created_at >= datetime.combine(target_date, datetime.min.time()),
            TaskModel.created_at < datetime.combine(target_date, datetime.max.time()),
        )
    tasks = list(await db.scalars(query))
    return [await _to_out(t, db) for t in tasks]


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
    return [await _to_out(t, db) for t in tasks]


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
        text = f"⏰ <b>Eslatma:</b> vazifa hali bajarilmagan\n{task.title}{deadline_text}"
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
