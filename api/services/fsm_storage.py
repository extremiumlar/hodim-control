"""aiogram FSM holatini bazada saqlovchi storage — cPanel (webhook) rejimi uchun.

Nega kerak: Passenger ishchi jarayonni harakatsizlikdan keyin o'chiradi va bir
nechta ishchi ochishi mumkin — MemoryStorage'dagi holat yo'qolib, ko'p bosqichli
oqimlar (bilim bazasida javob tahriri, ma'lumot qo'shish, anketa vaqtini kiritish,
Sotuv AI rejimi, norma/vazifa FSM'lari) o'rtasida uzilib qolardi. Bu storage
holatni `fsm_states` jadvalida saqlaydi — barcha ishchilar bitta SQLite'ni
ko'radi, restart ham ta'sir qilmaydi.

Faqat api/routers/bot_webhook.py ulaydi; Docker/polling bot bu modulni import
qilmaydi (u yerda db paketi yo'q, MemoryStorage yetarli)."""
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from db.base import async_session
from db.models import FsmState


def _key(key: StorageKey) -> str:
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.destiny}"


class DbFsmStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with async_session() as db:
            row = await db.get(FsmState, _key(key))
            if row is None:
                if value is None:
                    return
                db.add(FsmState(key=_key(key), state=value, data={}))
            else:
                row.state = value
                if value is None and not row.data:
                    await db.delete(row)  # bo'sh qatorlar to'planib qolmasin
            await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with async_session() as db:
            row = await db.get(FsmState, _key(key))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        async with async_session() as db:
            row = await db.get(FsmState, _key(key))
            if row is None:
                if not data:
                    return
                db.add(FsmState(key=_key(key), state=None, data=data))
            else:
                row.data = data
                if not data and row.state is None:
                    await db.delete(row)
            await db.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        async with async_session() as db:
            row = await db.get(FsmState, _key(key))
            return dict(row.data or {}) if row else {}

    async def close(self) -> None:  # интерфейс talabi — yopadigan resurs yo'q
        return None
