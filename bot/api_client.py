import httpx

from bot.config import API_BASE_URL, BOT_SHARED_SECRET

HEADERS = {"X-Bot-Secret": BOT_SHARED_SECRET}


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_BASE_URL, headers=HEADERS, timeout=10)


async def telegram_start(telegram_id: int, invite_token: str | None) -> dict:
    async with await _client() as client:
        resp = await client.post(
            "/users/telegram-start",
            json={"telegram_id": telegram_id, "invite_token": invite_token},
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_by_telegram(telegram_id: int) -> dict | None:
    async with await _client() as client:
        resp = await client.get(f"/users/by-telegram/{telegram_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def list_my_tasks(telegram_id: int) -> list[dict]:
    async with await _client() as client:
        resp = await client.get(f"/tasks/my/{telegram_id}")
        resp.raise_for_status()
        return resp.json()


async def complete_task(task_id: int, telegram_id: int) -> dict:
    async with await _client() as client:
        resp = await client.post(f"/tasks/{task_id}/complete", json={"telegram_id": telegram_id})
        resp.raise_for_status()
        return resp.json()


async def create_excused_day(telegram_id: int, date_str: str, reason: str) -> dict:
    async with await _client() as client:
        resp = await client.post(
            "/excused-days",
            json={"telegram_id": telegram_id, "date": date_str, "reason": reason},
        )
        resp.raise_for_status()
        return resp.json()


async def decide_excused_day(item_id: int, decider_telegram_id: int, decision: str) -> dict:
    async with await _client() as client:
        resp = await client.post(
            f"/excused-days/{item_id}/decide",
            json={"decider_telegram_id": decider_telegram_id, "decision": decision},
        )
        resp.raise_for_status()
        return resp.json()


async def list_employees() -> list[dict]:
    async with await _client() as client:
        resp = await client.get("/users/employees")
        resp.raise_for_status()
        return resp.json()


async def update_norm(changer_telegram_id: int, target_user_id: int, metric_type: str, value: int) -> dict:
    async with await _client() as client:
        resp = await client.post(
            "/norms/bot-update",
            json={
                "changer_telegram_id": changer_telegram_id,
                "target_user_id": target_user_id,
                "metric_type": metric_type,
                "value": value,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_mobilograf_video(telegram_id: int, telegram_message_id: int, group_chat_id: int) -> dict:
    async with await _client() as client:
        resp = await client.post(
            "/mobilograf-videos",
            json={
                "telegram_id": telegram_id,
                "telegram_message_id": telegram_message_id,
                "group_chat_id": group_chat_id,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def react_mobilograf_video(
    group_chat_id: int, telegram_message_id: int, reactor_telegram_id: int, action: str
) -> dict | None:
    async with await _client() as client:
        resp = await client.post(
            "/mobilograf-videos/react",
            json={
                "group_chat_id": group_chat_id,
                "telegram_message_id": telegram_message_id,
                "reactor_telegram_id": reactor_telegram_id,
                "action": action,
            },
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def today_daily_result(telegram_id: int) -> dict:
    async with await _client() as client:
        resp = await client.get(f"/daily-results/today/{telegram_id}")
        resp.raise_for_status()
        return resp.json()


async def my_latest_bonus(telegram_id: int) -> dict:
    async with await _client() as client:
        resp = await client.get(f"/bonuses/my/{telegram_id}")
        resp.raise_for_status()
        return resp.json()


async def assignable_users(telegram_id: int) -> list[dict]:
    async with await _client() as client:
        resp = await client.get(f"/tasks/assignable-users/{telegram_id}")
        resp.raise_for_status()
        return resp.json()


async def bot_create_task(assigner_telegram_id: int, assigned_to: int, title: str) -> dict:
    async with await _client() as client:
        resp = await client.post(
            "/tasks/bot-create",
            json={
                "assigner_telegram_id": assigner_telegram_id,
                "assigned_to": assigned_to,
                "title": title,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def trigger_daily_summary() -> dict:
    async with await _client() as client:
        resp = await client.post("/reports/daily-summary")
        resp.raise_for_status()
        return resp.json()


async def trigger_call_stats() -> dict:
    async with await _client() as client:
        resp = await client.post("/reports/call-stats")
        resp.raise_for_status()
        return resp.json()
