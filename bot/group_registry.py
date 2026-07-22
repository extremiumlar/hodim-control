"""Bot kuzatadigan Telegram guruhlarning maqsad(purpose) bo'yicha kesh registri.

Nega kerak: aiogram magic filterlari (`F.chat.id == KONSTANTA`) handler ro'yxatga
olinganda (modul import vaqtida) BIR MARTA hisoblanib "muzlab qoladi" — shuning
uchun guruh chat_id'larini endi DB'dan (`MonitoredGroup`) olamiz va HAR UPDATE
kelganda tekshiradigan oddiy async funksiyalar/filterlar ishlatamiz. Har update
uchun API'ga so'rov yubormaslik uchun natija qisqa TTL bilan keshlanadi;
`/guruh_biriktir`/`/guruh_ochir` o'zgartirgandan keyin `invalidate()` chaqirib
keshni darhol eskirtiradi."""
import time

from bot import api_client

_CACHE_TTL_SECONDS = 60

_by_purpose: dict[str, set[int]] = {}
_loaded_at: float | None = None


async def _ensure_fresh() -> None:
    global _loaded_at
    now = time.monotonic()
    if _loaded_at is not None and (now - _loaded_at) < _CACHE_TTL_SECONDS:
        return

    rows = await api_client.list_monitored_groups()
    fresh: dict[str, set[int]] = {}
    for row in rows:
        fresh.setdefault(row["purpose"], set()).add(row["chat_id"])

    _by_purpose.clear()
    _by_purpose.update(fresh)
    _loaded_at = now


async def get_group_ids(purpose: str) -> set[int]:
    """Berilgan maqsad uchun faol guruh chat_id'lari (kesh orqali)."""
    await _ensure_fresh()
    return _by_purpose.get(purpose, set())


async def is_in_group(chat_id: int, purpose: str) -> bool:
    return chat_id in await get_group_ids(purpose)


def invalidate() -> None:
    """Guruh ro'yxati o'zgargandan keyin (masalan `/guruh_biriktir`) keshni
    darhol eskirtiradi — keyingi chaqiruv API'dan yangisini oladi."""
    global _loaded_at
    _loaded_at = None
