"""Vazifa statistikasining QAMROVI — yagona joy (yangi TZ 3.2 / S-46).

⚠️ NEGA ALOHIDA MODUL. Filtr KAMIDA ikki joyda kerak
(`daily_digest._tasks_by_user` va `stats.py` dagi oylik hisoblar).
S-44 da xuddi shunday qoida uch joyda nusxalanib, bittasi
o'zgarganda qolganlari eski holida qolib ketgani aniqlangan edi —
o'sha xatoni takrorlamaymiz.
"""
from __future__ import annotations

from sqlalchemy import or_

from db.models import TASK_STATS_EXCLUDED_SOURCES, TaskModel


def task_stats_filter():
    """Statistikaga KIRADIGAN vazifalar sharti.

    ⚠️ `IS NULL` sharti SHART. SQL da `source NOT IN ('onboarding')`
    ifodasi `source` `NULL` bo'lganda `NULL` (ya'ni «rost emas»)
    qaytaradi — natijada ODDIY vazifalar (ular aynan `source IS
    NULL`) statistikadan BUTUNLAY tushib qolardi va foiz nolga
    aylanardi. Bu SQL ning klassik tuzog'i va uni test aniq
    tekshiradi.
    """
    return or_(
        TaskModel.source.is_(None),
        TaskModel.source.notin_(TASK_STATS_EXCLUDED_SOURCES),
    )
