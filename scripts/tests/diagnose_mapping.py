"""Mapping diagnostikasi: lidi bor lekin qo'ng'irog'i yo'q CRM operatorlari va
ularning tizimdagi bog'lanish holati (crm_visit_external_id, crm_external_id).
Statistikada operator 0 qo'ng'iroq / "—" gaplashgan bo'lib ko'rinsa shu skript
sababini aytadi (CRM ID to'ldirilmaganlarini ro'yxatlaydi).

Ishga tushirish (repo ildizidan):
    .venv/Scripts/python scripts/tests/diagnose_mapping.py
"""
import asyncio
import datetime as dt
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
# Repo ildizi: scripts/tests/ dan ikki daraja yuqorida
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


async def main():
    from sqlalchemy import func, select

    from api.timeutil import today_local
    from db.base import async_session
    from db.models import LeadStageDaily, OperatorCallsDaily, User

    today = today_local()
    start = today - dt.timedelta(days=6)

    async with async_session() as db:
        # Oxirgi 7 kunda lidi bor rid'lar
        lead_rids = {
            (rid, name)
            for rid, name in (
                await db.execute(
                    select(LeadStageDaily.responsible_id, func.max(LeadStageDaily.responsible_name))
                    .where(LeadStageDaily.date >= start)
                    .group_by(LeadStageDaily.responsible_id)
                )
            ).all()
        }
        # Oxirgi 7 kunda qo'ng'irog'i bor rid'lar
        call_rids = {
            rid
            for (rid,) in (
                await db.execute(
                    select(OperatorCallsDaily.responsible_id)
                    .where(OperatorCallsDaily.date >= start)
                    .group_by(OperatorCallsDaily.responsible_id)
                )
            ).all()
        }
        users = list(await db.scalars(select(User)))
        user_by_rid = {}
        for u in users:
            try:
                if u.crm_visit_external_id:
                    user_by_rid[int(u.crm_visit_external_id)] = u
            except (TypeError, ValueError):
                pass

        print(f"Oxirgi 7 kun ({start} – {today}):")
        print(f"  lidi bor operatorlar (rid): {len(lead_rids)}")
        print(f"  qo'ng'irog'i bor rid'lar:   {sorted(call_rids)}")
        print()
        print("LIDI BOR, QO'NG'IROG'I YO'Q operatorlar tahlili:")
        for rid, name in sorted(lead_rids):
            if rid in call_rids or rid == 0:
                continue
            u = user_by_rid.get(rid)
            if u is None:
                status = "❌ tizimda BUNDAY crm_visit_external_id'li foydalanuvchi YO'Q"
            elif not u.crm_external_id:
                status = (
                    f"⚠️ tizimda bor ({u.full_name}, faol={u.is_active}), lekin "
                    "crm_external_id (qo'ng'iroq/employeeNum bog'lanishi) BO'SH"
                )
            else:
                status = (
                    f"✅ tizimda bor ({u.full_name}, faol={u.is_active}), "
                    f"crm_external_id='{u.crm_external_id}' — demak bu odam shu davrda "
                    "umuman qo'ng'iroq qilmagan (yoki employeeNum CRM'da boshqacha)"
                )
            print(f"  rid={rid} «{name}»: {status}")

        print()
        print("Tizim foydalanuvchilari bog'lanish jadvali (faollar):")
        for u in users:
            if not u.is_active:
                continue
            print(
                f"  {u.full_name:35} role={u.role:10} "
                f"crm_external_id={u.crm_external_id or '—':20} "
                f"crm_visit_external_id={u.crm_visit_external_id or '—'}"
            )


asyncio.run(main())
