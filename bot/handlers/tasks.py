import httpx
from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import api_client

router = Router(name="tasks")


@router.callback_query(F.data.startswith("task_done:"))
async def on_task_done(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    try:
        task = await api_client.complete_task(task_id, callback.from_user.id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            await callback.answer("Bu vazifa sizga tegishli emas.", show_alert=True)
        else:
            await callback.answer("Xatolik yuz berdi.", show_alert=True)
        return

    await callback.message.edit_text(f"✅ Bajarildi: {task['title']}")
    await callback.answer("Vazifa bajarildi deb belgilandi!")
