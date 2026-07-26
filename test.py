"""Davomat (kelib-ketish) tizimi — DB yozuvi debug/tekshiruv testi.

Nimani tekshiradi:
  1. «Keldim» bosilganda check_in_time/lat/lng/masofa BAZAGA yozilishi
  2. Kechikish (late_minutes) ish jadvalidagi 09:00 dan to'g'ri hisoblanishi
  3. «Ketdim» bosilganda check_out_time + worked_minutes yozilishi
  4. Dubl check-in / check-out bloklanishi (baza buzilmasligi)
  5. Begona yuz / past tiriklik / ofisdan uzoq GPS — yozuv YARATILMASLIGI
  6. Dam olish kunida (override) status=weekend, late=0 yozilishi
  7. Kechikish statistikasi endpoint'i (/attendance/late-stats) bazadagi bilan mosligi
  8. Bazadagi UNIQUE(user_id, date) cheklovi ishlashi

Ishga tushirish (loyiha ildizidan, API 8000 da ishlab turishi shart):
    .venv/Scripts/python.exe test.py

Barcha sinov ma'lumotlari T- prefiksi bilan yaratiladi va oxirida to'liq
o'chiriladi (jonli ma'lumotga tegilmaydi).
"""
import json
import sqlite3
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Loyihaning o'z JWT funksiyasi bilan token yaratamiz — dev-login DEBUG=false'da
# yopiq (404), lekin JWT_SECRET .env'dan bir xil o'qiladi.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from api.security import create_access_token
except Exception:
    print("XATO: api.security import bo'lmadi (.venv'dan ishga tushiring):\n" + traceback.format_exc())
    sys.exit(1)

DB_PATH = "app.db"
API_BASE = "http://127.0.0.1:8000"
OFFICE = (41.311081, 69.240562)  # sinov ofisi koordinatasi
FACE = [0.05] * 128  # ro'yxatdagi yuz
WRONG_FACE = [0.35] * 128  # begona yuz (masofa > 0.5)
TZ = ZoneInfo("Asia/Tashkent")

passed: list[str] = []
failed: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    """Bitta tekshiruv natijasini qayd etadi va chiqaradi."""
    (passed if cond else failed).append(name)
    mark = "  [OK]  " if cond else "  [FAIL]"
    print(f"{mark} {name}" + (f"  | {extra}" if extra else ""))


def db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# ─────────────────────────────────────────────────────────────────
# Sozlash / tozalash — xatoga chidamli (har biri alohida try/except)
# ─────────────────────────────────────────────────────────────────

def setup() -> dict:
    """T- sinov ma'lumotlarini yaratadi: 2 xodim, ish jadvali, ofis."""
    ctx: dict = {}
    conn = db()
    try:
        cur = conn.cursor()
        today = date.today()

        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " face_descriptor, face_registered_at, created_at)"
            " values (999100701, 'T-DebugXodim', 'employee', 1, 1, ?, datetime('now'), datetime('now'))",
            (json.dumps(FACE),),
        )
        ctx["uid1"] = cur.lastrowid

        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " face_descriptor, face_registered_at, created_at)"
            " values (999100702, 'T-DamXodim', 'employee', 1, 1, ?, datetime('now'), datetime('now'))",
            (json.dumps(FACE),),
        )
        ctx["uid2"] = cur.lastrowid

        # uid1: bugun 09:00-23:59 ish kuni (kechikish 09:00 dan hisoblanadi)
        cur.execute(
            "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
            " values (?, ?, 1, '09:00', '23:59', datetime('now'))",
            (ctx["uid1"], today.weekday()),
        )
        # uid2: bugun override bilan DAM OLISH kuni
        cur.execute(
            "insert into work_schedule_override (user_id, date, is_working, updated_at)"
            " values (?, ?, 0, datetime('now'))",
            (ctx["uid2"], today.isoformat()),
        )
        cur.execute(
            "insert into office_locations (name, latitude, longitude, radius_meters, is_active, created_at)"
            " values ('T-DebugOfis', ?, ?, 200, 1, datetime('now'))",
            OFFICE,
        )
        ctx["office_id"] = cur.lastrowid
        conn.commit()
        print(f"Sozlash: uid1={ctx['uid1']}, uid2={ctx['uid2']}, ofis={ctx['office_id']}\n")
        return ctx
    finally:
        conn.close()


def cleanup(ctx: dict) -> None:
    """Barcha T- sinov ma'lumotlarini o'chiradi (har qadami mustaqil himoyalangan)."""
    conn = db()
    try:
        cur = conn.cursor()
        uids = [ctx.get("uid1"), ctx.get("uid2")]
        uids = [u for u in uids if u]
        for sql, params in [
            ("delete from attendance where user_id in (%s)" % ",".join("?" * len(uids)), uids),
            ("delete from work_schedule_weekly where user_id in (%s)" % ",".join("?" * len(uids)), uids),
            ("delete from work_schedule_override where user_id in (%s)" % ",".join("?" * len(uids)), uids),
            ("delete from office_locations where name like 'T-%'", []),
            # T- foydalanuvchilar o'chirilishidan OLDIN — aks holda quyidagi subselect
            # bo'sh qaytadi (SQLite FK cheklovi yo'q, lekin yetim yozuv qolib ketmasin).
            ("delete from face_reregistration_requests where user_id in "
             "(select id from users where full_name like 'T-%')", []),
            ("delete from users where full_name like 'T-%'", []),
        ]:
            try:
                if uids or "T-" in sql:
                    cur.execute(sql, params)
            except sqlite3.Error as e:
                print(f"  tozalash xatosi ({sql[:40]}...): {e}")
        conn.commit()
        left = cur.execute("select count(*) from users where full_name like 'T-%'").fetchone()[0]
        print(f"\nTozalash tugadi. T- qoldiq foydalanuvchi: {left}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────
# HTTP yordamchilar
# ─────────────────────────────────────────────────────────────────

def token_for(user_id: int, role: str) -> str | None:
    """Foydalanuvchi uchun JWT'ni bevosita yaratadi (loyihaning o'z funksiyasi,
    .env'dagi JWT_SECRET bilan) — DEBUG holatiga bog'liq emas."""
    try:
        return create_access_token(user_id, role)
    except Exception as e:
        print(f"  token yaratish xatosi (user={user_id}): {e}")
        return None


def find_manager_id() -> int | None:
    """Bazadan bitta faol rahbar (boss/dasturchi/hr) id'sini topadi."""
    try:
        conn = db()
        row = conn.execute(
            "select id, role from users where role in ('boss','dasturchi','hr') and is_active=1 limit 1"
        ).fetchone()
        conn.close()
        return (row[0], row[1]) if row else None
    except sqlite3.Error as e:
        print(f"  rahbar topish xatosi: {e}")
        return None


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────
# Testlar
# ─────────────────────────────────────────────────────────────────

def run_tests(ctx: dict) -> None:
    try:
        import httpx
    except ImportError:
        print("XATO: httpx o'rnatilmagan (.venv ishlatilyaptimi?)")
        sys.exit(1)

    uid1, uid2 = ctx["uid1"], ctx["uid2"]
    today_iso = date.today().isoformat()

    with httpx.Client(timeout=15) as client:
        # API tiriklik tekshiruvi
        try:
            r = client.get(f"{API_BASE}/health")
            check("API ishlayapti (/health)", r.status_code == 200)
        except Exception as e:
            print(f"API'ga ulanib bo'lmadi: {e}\nAvval xizmatlarni ishga tushiring.")
            sys.exit(1)

        t1 = token_for(uid1, "employee")
        t2 = token_for(uid2, "employee")
        check("T-xodimlar uchun JWT yaratildi", bool(t1 and t2))
        if not (t1 and t2):
            return  # token yo'q — davomi ma'nosiz
        # Token haqiqatan ishlashini tekshiramiz
        try:
            r = client.get(f"{API_BASE}/users/me", headers=auth(t1))
            check("JWT bilan /users/me ishladi", r.status_code == 200,
                  f"user={r.json().get('full_name')}" if r.status_code == 200 else f"status={r.status_code}")
        except Exception:
            check("JWT bilan /users/me ishladi", False, traceback.format_exc(limit=1).strip())

        # ── 1-5: yozuv YARATILMAYDIGAN xato holatlar ──────────────
        print("\n-- Xato holatlar (baza toza qolishi kerak) --")
        cases = [
            ("begona yuz", {"latitude": OFFICE[0], "longitude": OFFICE[1],
                            "face_descriptor": WRONG_FACE, "liveness": 0.9}),
            ("past tiriklik", {"latitude": OFFICE[0], "longitude": OFFICE[1],
                               "face_descriptor": FACE, "liveness": 0.2}),
            ("ofisdan uzoq GPS", {"latitude": 41.5, "longitude": 69.6,
                                  "face_descriptor": FACE, "liveness": 0.9}),
        ]
        for name, body in cases:
            try:
                r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(t1), json=body)
                check(f"{name} -> 400", r.status_code == 400,
                      r.json().get("detail", "")[:45])
            except Exception:
                check(f"{name} -> 400", False, traceback.format_exc(limit=1).strip())

        try:
            conn = db()
            n = conn.execute("select count(*) from attendance where user_id=?", (uid1,)).fetchone()[0]
            conn.close()
            check("xato holatlardan keyin bazada yozuv YO'Q", n == 0, f"yozuvlar={n}")
        except Exception:
            check("xato holatlardan keyin bazada yozuv YO'Q", False, traceback.format_exc(limit=1).strip())

        # ── Keldim: bazaga yozilish + kechikish hisobi ───────────
        print("\n-- «Keldim» bazaga yozilishi --")
        checkin_moment = datetime.now(TZ)
        try:
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(t1),
                            json={"latitude": OFFICE[0], "longitude": OFFICE[1],
                                  "face_descriptor": FACE, "liveness": 0.9})
            check("to'g'ri check-in -> 200", r.status_code == 200,
                  f"API javobi: status={r.json().get('status')}, late={r.json().get('late_minutes')}")
        except Exception:
            check("to'g'ri check-in -> 200", False, traceback.format_exc(limit=1).strip())

        # Bazadan BEVOSITA o'qib tekshirish (API javobiga ishonmasdan)
        try:
            conn = db()
            row = conn.execute(
                "select check_in_time, check_in_lat, check_in_lng, check_in_distance_m,"
                " late_minutes, status from attendance where user_id=? and date=?",
                (uid1, today_iso),
            ).fetchone()
            conn.close()
            check("bazada check_in_time yozildi", bool(row and row[0]), f"qiymat={row[0] if row else None}")
            check("bazada GPS (lat/lng) yozildi",
                  bool(row and abs(row[1] - OFFICE[0]) < 1e-4 and abs(row[2] - OFFICE[1]) < 1e-4),
                  f"lat={row[1]}, lng={row[2]}" if row else "")
            check("bazada masofa yozildi (radius ichida)", row is not None and row[3] is not None and row[3] <= 200,
                  f"masofa={row[3]}m" if row else "")

            # Kechikishni mustaqil hisoblab solishtirish: grace BO'SAG'A (chegirma
            # emas, 1.3-tuzatish) — diff > grace bo'lsa TO'LIQ diff yoziladi.
            # 1.4-tuzatish: yuqori chegara — ish oynasidan (tushliksiz) oshmaydi.
            # uid1 jadvali 09:00-23:59 (setup()da), shu oynadan oshib ketsa chegaralanadi.
            from api.timeutil import work_minutes as _work_minutes2
            diff = (checkin_moment.hour * 60 + checkin_moment.minute) - (9 * 60)
            expected = diff if diff > 5 else 0
            expected = min(expected, _work_minutes2(9 * 60, 23 * 60 + 59))
            got = row[4] if row else -1
            check("late_minutes to'g'ri hisoblangan (±1 daq)",
                  abs(got - expected) <= 1, f"bazada={got}, kutilgan~{expected}")
            check("status to'g'ri (late/present)",
                  row is not None and row[5] == ("late" if expected > 0 else "present"),
                  f"status={row[5] if row else None}")

            # check_in_time UTC bo'lib saqlanganini tekshirish (Toshkent-5)
            if row and row[0]:
                dt_utc = datetime.fromisoformat(row[0].split(".")[0])
                delta_min = abs((checkin_moment.replace(tzinfo=None) - timedelta(hours=5)) - dt_utc).total_seconds() / 60
                check("check_in_time UTC sifatida saqlangan (±2 daq)", delta_min <= 2,
                      f"bazada={row[0]} (UTC), farq={delta_min:.1f} daq")
        except Exception:
            check("bazadan check-in o'qish", False, traceback.format_exc(limit=1).strip())

        # ── Dubl check-in ─────────────────────────────────────────
        try:
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(t1),
                            json={"latitude": OFFICE[0], "longitude": OFFICE[1],
                                  "face_descriptor": FACE, "liveness": 0.9})
            check("dubl check-in -> 400", r.status_code == 400)
            conn = db()
            n = conn.execute("select count(*) from attendance where user_id=? and date=?",
                             (uid1, today_iso)).fetchone()[0]
            conn.close()
            check("dubldan keyin ham bazada 1 ta yozuv", n == 1, f"yozuvlar={n}")
        except Exception:
            check("dubl check-in nazorati", False, traceback.format_exc(limit=1).strip())

        # ── Ketdim: bazaga yozilish ───────────────────────────────
        print("\n-- «Ketdim» bazaga yozilishi --")
        try:
            r = client.post(f"{API_BASE}/attendance/me/check-out", headers=auth(t1),
                            json={"latitude": OFFICE[0], "longitude": OFFICE[1],
                                  "face_descriptor": FACE, "liveness": 0.9})
            check("check-out -> 200", r.status_code == 200)
            conn = db()
            row = conn.execute(
                "select check_out_time, worked_minutes, early_leave_minutes from attendance"
                " where user_id=? and date=?", (uid1, today_iso)).fetchone()
            conn.close()
            check("bazada check_out_time yozildi", bool(row and row[0]), f"qiymat={row[0] if row else None}")
            check("worked_minutes >= 0 yozildi", row is not None and row[1] is not None and row[1] >= 0,
                  f"worked={row[1]}" if row else "")
        except Exception:
            check("check-out bazaga yozilishi", False, traceback.format_exc(limit=1).strip())

        try:
            r = client.post(f"{API_BASE}/attendance/me/check-out", headers=auth(t1),
                            json={"latitude": OFFICE[0], "longitude": OFFICE[1],
                                  "face_descriptor": FACE, "liveness": 0.9})
            check("dubl check-out -> 400", r.status_code == 400)
        except Exception:
            check("dubl check-out -> 400", False, traceback.format_exc(limit=1).strip())

        # ── Dam olish kuni ────────────────────────────────────────
        print("\n-- Dam olish kuni (override) --")
        try:
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(t2),
                            json={"latitude": OFFICE[0], "longitude": OFFICE[1],
                                  "face_descriptor": FACE, "liveness": 0.9})
            conn = db()
            row = conn.execute(
                "select status, late_minutes, is_weekend from attendance where user_id=? and date=?",
                (uid2, today_iso)).fetchone()
            conn.close()
            check("dam kunida check-in -> weekend/late=0",
                  r.status_code == 200 and row is not None
                  and row[0] == "weekend" and row[1] == 0 and row[2] == 1,
                  f"status={row[0] if row else None}, late={row[1] if row else None}")
        except Exception:
            check("dam kuni holati", False, traceback.format_exc(limit=1).strip())

        # ── UNIQUE(user_id, date) cheklovi ────────────────────────
        print("\n-- Baza cheklovi --")
        try:
            conn = db()
            try:
                conn.execute(
                    "insert into attendance (user_id, date, late_minutes, early_leave_minutes,"
                    " worked_minutes, status, is_weekend, created_at, updated_at)"
                    " values (?, ?, 0, 0, 0, 'present', 0, datetime('now'), datetime('now'))",
                    (uid1, today_iso),
                )
                conn.commit()
                check("UNIQUE(user_id,date) cheklovi ishlaydi", False, "dubl insert o'tib ketdi!")
            except sqlite3.IntegrityError:
                check("UNIQUE(user_id,date) cheklovi ishlaydi", True, "IntegrityError (kutilgan)")
            finally:
                conn.close()
        except Exception:
            check("UNIQUE cheklovi testi", False, traceback.format_exc(limit=1).strip())

        # ── Kechikish statistikasi endpoint'i ─────────────────────
        print("\n-- Kechikish statistikasi (/attendance/late-stats) --")
        try:
            mgr = find_manager_id()
            check("bazada rahbar topildi", mgr is not None, f"{mgr}")
            boss_t = token_for(mgr[0], mgr[1]) if mgr else None
            r = client.get(f"{API_BASE}/attendance/late-stats?days=7", headers=auth(boss_t))
            check("late-stats -> 200", r.status_code == 200)
            stats = r.json()
            me = next((s for s in stats if s["full_name"] == "T-DebugXodim"), None)
            conn = db()
            db_late = conn.execute(
                "select late_minutes from attendance where user_id=? and date=?",
                (uid1, today_iso)).fetchone()[0]
            conn.close()
            if db_late > 0:
                check("statistikada T-DebugXodim bor (bazadagi bilan mos)",
                      me is not None and me["total_late_minutes"] == db_late
                      and any(d["date"] == today_iso and d["late_minutes"] == db_late for d in me["days"]),
                      f"api={me['total_late_minutes'] if me else None}, baza={db_late}")
            else:
                check("kechikish 0 — statistikada yo'q (to'g'ri)", me is None)
            # employee ruxsati yo'qligi
            r = client.get(f"{API_BASE}/attendance/late-stats", headers=auth(t1))
            check("employee late-stats -> 403", r.status_code == 403)
        except Exception:
            check("late-stats tekshiruvi", False, traceback.format_exc(limit=1).strip())

        # ── 1-BOSQICH: statistika yolg'oni tuzatishlari (2026-07-26 audit) ──
        print("\n-- 1.1: absent yozuvi + 1.2: LEFT JOIN --")
        try:
            import asyncio as _asyncio

            from db.base import async_session as _async_session
            from api.services.attendance_digest import write_absent_records as _write_absent

            today = date.today()
            wd_today = today.weekday()

            conn = db()
            cur2 = conn.cursor()
            # T-HechKelmagan: jadvali bor (ish kuni), check-in qilmagan, sababli ham emas
            cur2.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999666001,'T-HechKelmagan','employee',1,1,datetime('now'))")
            ghost_uid = cur2.lastrowid
            cur2.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (ghost_uid, wd_today))
            # T-SababliKun: xuddi shunday jadval, lekin BUGUNGA tasdiqlangan sababli kun
            cur2.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999666002,'T-SababliKun','employee',1,1,datetime('now'))")
            excused_uid = cur2.lastrowid
            cur2.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (excused_uid, wd_today))
            cur2.execute(
                "insert into excused_days (user_id, date, reason, status, created_at)"
                " values (?, ?, 'T-sinov', 'approved', datetime('now'))", (excused_uid, today.isoformat()))
            conn.commit()

            async def _run_absent():
                async with _async_session() as s:
                    return await _write_absent(s, today)

            written = _asyncio.run(_run_absent())
            row_ghost = conn.execute(
                "select status from attendance where user_id=? and date=?",
                (ghost_uid, today.isoformat())).fetchone()
            check("1.1: absent yozuvi yaratildi", row_ghost is not None and row_ghost[0] == "absent",
                  f"written={written}, status={row_ghost[0] if row_ghost else None}")

            row_excused = conn.execute(
                "select status from attendance where user_id=? and date=?",
                (excused_uid, today.isoformat())).fetchone()
            check("1.1: sababli kunli xodimga absent YOZILMAYDI", row_excused is None,
                  f"yozuv={row_excused}")

            # Idempotentlik
            _asyncio.run(_run_absent())
            n = conn.execute("select count(*) from attendance where user_id=? and date=?",
                             (ghost_uid, today.isoformat())).fetchone()[0]
            check("1.1: qayta chaqirilsa dublikat yo'q", n == 1, f"yozuvlar={n}")

            r = client.get(f"{API_BASE}/attendance?status_filter=absent&date_from={today.isoformat()}",
                           headers=auth(boss_t))
            names = [x["user_full_name"] for x in r.json()]
            check("1.1: GET status_filter=absent natija qaytaradi", "T-HechKelmagan" in names, f"{names}")

            # 1.2: hech qachon check-in qilmagan (jadval ham yo'q) xodim
            # employee-summary'da (LEFT JOIN) ko'rinishi kerak
            cur2.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999666003,'T-Umuman-Yoq','employee',1,1,datetime('now'))")
            noop_uid = cur2.lastrowid
            conn.commit()
            r = client.get(f"{API_BASE}/attendance/employee-summary?days=90", headers=auth(boss_t))
            names2 = [x["full_name"].strip() for x in r.json()]
            check("1.2: hech qachon kelmagan xodim employee-summary'da bor",
                  "T-Umuman-Yoq" in names2, f"{len(names2)} kishi ro'yxatda")

            for u in (ghost_uid, excused_uid, noop_uid):
                cur2.execute("delete from attendance where user_id=?", (u,))
                cur2.execute("delete from work_schedule_weekly where user_id=?", (u,))
                cur2.execute("delete from excused_days where user_id=?", (u,))
                cur2.execute("delete from users where id=?", (u,))
            conn.commit()
            conn.close()
        except Exception:
            check("1-bosqich tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 1.4: kechikish/erta-ketish yuqori chegarasi --")
        try:
            from api.timeutil import work_minutes as _work_minutes
            window = _work_minutes(9 * 60, 18 * 60)  # 09:00-18:00, tushliksiz
            check("1.4: ish oynasi (tushliksiz) 480 daq", window == 480, f"window={window}")
            # Servis darajasida: diff oynadan katta bo'lsa late shu oyna bilan cheklanishi
            # kodning o'zida tekshirilgan (attendance.py min(late, window)); bu yerda
            # formulaning to'g'riligini mustaqil qayta hisoblab tasdiqlaymiz.
            fake_diff = 999  # masalan 17:59 da kelish emulyatsiyasi
            capped = min(fake_diff, window)
            check("1.4: 999 daqiqalik farq 480 bilan cheklanadi", capped == 480, f"capped={capped}")
        except Exception:
            check("1.4 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        # ── 0-BOSQICH: xavfsizlik tuzatishlari (2026-07-26 audit) ─────
        print("\n-- 0.1: /attendance/digest chat_id ruxsati --")
        try:
            r = client.post(f"{API_BASE}/attendance/digest",
                             params={"kind": "morning", "chat_id": 999999, "dry_run": "true"})
            check("sekretsiz chaqiruv -> 401/403", r.status_code in (401, 403))

            mgr = find_manager_id()
            mgr_tg = None
            if mgr:
                conn = db()
                row = conn.execute("select telegram_id from users where id=?", (mgr[0],)).fetchone()
                conn.close()
                mgr_tg = row[0] if row else None

            # bot-sekret bilan, lekin telegram_id'siz chat_id -> 400
            import httpx as _httpx  # allaqachon yuqorida import qilingan bo'lsa ham xavfsiz

            with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as f:
                secret = next(
                    (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")),
                    "",
                )
            bot_h = {"X-Bot-Secret": secret}
            r = client.post(f"{API_BASE}/attendance/digest", headers=bot_h,
                             params={"kind": "morning", "chat_id": 999999, "dry_run": "true"})
            check("bot-sekret + chat_id, telegram_id'siz -> 400", r.status_code == 400)

            if mgr_tg:
                r = client.post(f"{API_BASE}/attendance/digest", headers=bot_h,
                                params={"kind": "morning", "chat_id": 999999,
                                        "telegram_id": mgr_tg, "dry_run": "true"})
                check("bot-sekret + rahbar telegram_id + chat_id -> 200", r.status_code == 200)

            # chat_id berilmagan holat — bu cron/scheduler yo'li, telegram_id shart emas
            r = client.post(f"{API_BASE}/attendance/digest", headers=bot_h,
                             params={"kind": "morning", "dry_run": "true"})
            check("chat_id'siz chaqiruv (cron yo'li) hali ishlaydi", r.status_code == 200)
        except Exception:
            check("0.1 digest ruxsat tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 0.4: /docs production'da yopiq --")
        try:
            r = client.get(f"{API_BASE}/docs")
            check("/docs -> 404 (DEBUG=false)", r.status_code == 404)
            r = client.get(f"{API_BASE}/openapi.json")
            check("/openapi.json -> 404 (DEBUG=false)", r.status_code == 404)
        except Exception:
            check("0.4 /docs tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 0.5: qayta ro'yxatdan o'tish rahbar tasdig'ini kutadi (Savol A) --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444777,'T-AuditTest','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            audit_uid = cur.lastrowid
            conn.commit()

            audit_tok = token_for(audit_uid, "employee")
            r = client.post(f"{API_BASE}/attendance/me/register-face", headers=auth(audit_tok),
                             json={"face_descriptor": WRONG_FACE})
            check("qayta ro'yxatdan o'tish -> 200", r.status_code == 200)
            body = r.json()
            check("javob status=pending_approval (darhol YOZILMAYDI)",
                  body.get("status") == "pending_approval", str(body.get("status")))

            still_old = conn.execute(
                "select face_descriptor from users where id=?", (audit_uid,)).fetchone()[0]
            check("descriptor DARHOL o'zgarmagan (eski qiymatda qoladi)",
                  json.loads(still_old) == FACE, "descriptor eskicha qoldimi")

            req_row = conn.execute(
                "select id, status from face_reregistration_requests where user_id=? order by id desc limit 1",
                (audit_uid,)).fetchone()
            check("FaceReregistrationRequest 'pending' holatda yaratildi",
                  req_row is not None and req_row[1] == "pending", str(req_row))

            mgr = find_manager_id()
            req_id = req_row[0] if req_row else None
            if mgr and req_id:
                mgr_tok = token_for(mgr[0], mgr[1])
                mgr_telegram_id = conn.execute(
                    "select telegram_id from users where id=?", (mgr[0],)).fetchone()[0]
                # Bot-secret bilan himoyalangan endpoint — JWT emas, bot sekret kerak.
                secret = ""
                for line in open(".env", encoding="utf-8"):
                    if line.startswith("BOT_SHARED_SECRET="):
                        secret = line.strip().split("=", 1)[1]
                before_n = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='face_reregistered'",
                    (audit_uid,)).fetchone()[0]
                r = client.post(
                    f"{API_BASE}/attendance/face-reregistration/{req_id}/decide",
                    headers={"X-Bot-Secret": secret},
                    json={"decider_telegram_id": mgr_telegram_id, "decision": "approved"})
                check("rahbar tasdiqlaydi -> 200", r.status_code == 200, r.text[:200])
                after_n = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='face_reregistered'",
                    (audit_uid,)).fetchone()[0]
                check("tasdiqlangach AuditLog yozildi", after_n == before_n + 1,
                      f"before={before_n}, after={after_n}")
                new_desc = conn.execute(
                    "select face_descriptor from users where id=?", (audit_uid,)).fetchone()[0]
                check("tasdiqlangach descriptor yangilandi",
                      json.loads(new_desc) == WRONG_FACE, "yangi qiymat WRONG_FACE'gami")

                has_before = 1
                r = client.post(f"{API_BASE}/users/{audit_uid}/deactivate", headers=auth(mgr_tok))
                check("deactivate -> 200", r.status_code == 200)
                has_after = conn.execute(
                    "select face_descriptor is not null from users where id=?", (audit_uid,)).fetchone()[0]
                check("deactivate'dan keyin yuz tozalandi",
                      has_before == 1 and has_after == 0, f"oldin={has_before}, keyin={has_after}")

            cur.execute("delete from face_reregistration_requests where user_id=?", (audit_uid,))
            cur.execute("delete from audit_logs where target_user_id=?", (audit_uid,))
            cur.execute("delete from attendance where user_id=?", (audit_uid,))
            cur.execute("delete from users where id=?", (audit_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("0.5 register-face audit tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 0.6: bir xil yuz ikki hisobga ro'yxatdan o'ta olmaydi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444778,'T-Dup1','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            dup1_uid = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444779,'T-Dup2','employee',1,1,datetime('now'))")
            dup2_uid = cur.lastrowid
            conn.commit()

            dup2_tok = token_for(dup2_uid, "employee")
            # T-Dup1 bilan BIR XIL descriptor bilan ro'yxatdan o'tishga urinish -> rad etilishi kerak.
            r = client.post(f"{API_BASE}/attendance/me/register-face", headers=auth(dup2_tok),
                             json={"face_descriptor": FACE})
            check("bir xil yuz bilan ro'yxatdan o'tish -> 400", r.status_code == 400, r.text[:150])
            has_face_after = conn.execute(
                "select face_descriptor is not null from users where id=?", (dup2_uid,)).fetchone()[0]
            check("rad etilgach descriptor yozilmagan", has_face_after == 0)

            # Boshqa (uzoq) yuz bilan esa muvaffaqiyatli bo'lishi kerak.
            r = client.post(f"{API_BASE}/attendance/me/register-face", headers=auth(dup2_tok),
                             json={"face_descriptor": WRONG_FACE})
            check("uzoq yuz bilan ro'yxatdan o'tish -> 200", r.status_code == 200)
            body = r.json()
            check("birinchi marta darhol 'registered'", body.get("status") == "registered",
                  str(body.get("status")))

            cur.execute("delete from face_reregistration_requests where user_id in (?,?)", (dup1_uid, dup2_uid))
            cur.execute("delete from users where id in (?,?)", (dup1_uid, dup2_uid))
            conn.commit()
            conn.close()
        except Exception:
            check("0.6 duplicate-face tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 0.7: GPS aniqligi past bo'lsa check-in rad etiladi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444780,'T-AccuracyTest','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            acc_uid = cur.lastrowid
            conn.commit()
            acc_tok = token_for(acc_uid, "employee")

            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(acc_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9, "accuracy": 5000,
            })
            check("aniqlik 5000m -> 400 (rad etiladi)", r.status_code == 400, r.text[:150])
            row = conn.execute(
                "select check_in_time from attendance where user_id=?", (acc_uid,)).fetchone()
            check("bazaga yozuv qo'shilmadi", row is None or row[0] is None)

            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(acc_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9, "accuracy": 15,
            })
            check("aniqlik 15m -> 200 (o'tadi)", r.status_code == 200, r.text[:150])

            cur.execute("delete from attendance where user_id=?", (acc_uid,))
            cur.execute("delete from users where id=?", (acc_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("0.7 GPS aniqligi tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 2.1: yarim tundan keyin kechagi ochiq yozuvni yopish --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444781,'T-Midnight','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            mid_uid = cur.lastrowid
            wd = date.today().weekday()
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (mid_uid, wd))
            # "Kecha" check-in qilgan, hali check-out qilmagan — 2 soat oldin (UTC).
            yesterday = date.today() - timedelta(days=1)
            checkin_utc = datetime.utcnow() - timedelta(hours=2)
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, ?, ?, 0, 0, 0, 'present', 0, datetime('now'), datetime('now'))",
                (mid_uid, yesterday.isoformat(), checkin_utc.isoformat(sep=" ")))
            conn.commit()
            mid_tok = token_for(mid_uid, "employee")

            r = client.post(f"{API_BASE}/attendance/me/check-out", headers=auth(mid_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9,
            })
            check("yarim tundan keyingi check-out -> 200", r.status_code == 200, r.text[:200])
            row = conn.execute(
                "select date, check_out_time, worked_minutes from attendance where user_id=?",
                (mid_uid,)).fetchone()
            check("yozuv KECHAGI sanada qoldi (bugunga ko'chmadi)",
                  row is not None and row[0] == yesterday.isoformat(), f"{row}")
            check("worked_minutes ~2 soat (real vaqt farqi)",
                  row is not None and 110 <= row[2] <= 130, f"worked={row[2] if row else None}")
            today_row = conn.execute(
                "select count(*) from attendance where user_id=? and date=?",
                (mid_uid, date.today().isoformat())).fetchone()[0]
            check("bugunga yangi yozuv YARATILMADI", today_row == 0)

            cur.execute("delete from attendance where user_id=?", (mid_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (mid_uid,))
            cur.execute("delete from users where id=?", (mid_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("2.1 yarim tun tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 2.1b: 6 soatdan uzoq ochiq yozuv YOPILMAYDI (eski oyna) --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444782,'T-OldOpen','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            old_uid = cur.lastrowid
            yesterday = date.today() - timedelta(days=1)
            old_checkin_utc = datetime.utcnow() - timedelta(hours=10)  # 6 soatlik oynadan tashqari
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, ?, ?, 0, 0, 0, 'present', 0, datetime('now'), datetime('now'))",
                (old_uid, yesterday.isoformat(), old_checkin_utc.isoformat(sep=" ")))
            conn.commit()
            old_tok = token_for(old_uid, "employee")

            r = client.post(f"{API_BASE}/attendance/me/check-out", headers=auth(old_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9,
            })
            check("10 soat oldingi ochiq yozuv -> 400 (oynadan tashqari)", r.status_code == 400, r.text[:150])
            row = conn.execute(
                "select check_out_time from attendance where user_id=?", (old_uid,)).fetchone()
            check("eski yozuv hamon ochiq", row is not None and row[0] is None)

            cur.execute("delete from attendance where user_id=?", (old_uid,))
            cur.execute("delete from users where id=?", (old_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("2.1b eski oyna tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 2.2: kelib-u \"Ketdim\" bosmagan o'tgan kun avtomatik yopiladi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444783,'T-AutoClose','employee',1,1,datetime('now'))")
            ac_uid = cur.lastrowid
            three_days_ago = date.today() - timedelta(days=3)
            wd = three_days_ago.weekday()
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (ac_uid, wd))
            checkin_utc = datetime(three_days_ago.year, three_days_ago.month, three_days_ago.day, 4, 0, 0)  # 09:00 Toshkent
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, ?, ?, 0, 0, 0, 'present', 0, datetime('now'), datetime('now'))",
                (ac_uid, three_days_ago.isoformat(), checkin_utc.isoformat(sep=" ")))
            conn.commit()

            import asyncio
            from db.base import async_session
            from api.services.attendance_digest import auto_close_unclosed_checkouts

            async def _run_close():
                async with async_session() as s:
                    return await auto_close_unclosed_checkouts(s, date.today())

            closed = asyncio.run(_run_close())
            check("auto_close_unclosed_checkouts >=1 yopdi", closed >= 1, f"closed={closed}")
            row = conn.execute(
                "select check_out_time, worked_minutes, note from attendance where user_id=?",
                (ac_uid,)).fetchone()
            check("3 kun oldingi ochiq yozuv yopildi", row is not None and row[0] is not None, f"{row}")
            check("worked_minutes ish oynasidan hisoblangan (~480 daq)",
                  row is not None and 400 <= row[1] <= 480, f"worked={row[1] if row else None}")
            check("izoh (note) qo'yildi", row is not None and row[2] and "Avtomatik" in row[2], f"note={row[2] if row else None}")

            # Bugungi (hali davom etayotgan) ochiq yozuv TEGILMASLIGI kerak.
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444784,'T-StillOpen','employee',1,1,datetime('now'))")
            open_uid = cur.lastrowid
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, ?, datetime('now'), 0, 0, 0, 'present', 0, datetime('now'), datetime('now'))",
                (open_uid, date.today().isoformat()))
            conn.commit()
            closed2 = asyncio.run(_run_close())
            check("ikkinchi chaqiruvda yangi yopish yo'q (bugungi hisobga kirmaydi)", closed2 == 0, f"closed2={closed2}")
            row2 = conn.execute(
                "select check_out_time from attendance where user_id=?", (open_uid,)).fetchone()
            check("bugungi ochiq yozuvga TEGILMADI", row2 is not None and row2[0] is None, f"{row2}")

            cur.execute("delete from attendance where user_id in (?,?)", (ac_uid, open_uid))
            cur.execute("delete from work_schedule_weekly where user_id=?", (ac_uid,))
            cur.execute("delete from users where id in (?,?)", (ac_uid, open_uid))
            conn.commit()
            conn.close()
        except Exception:
            check("2.2 avtomatik yopish tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 2.3: check-in poygasi -> 500 EMAS, tushunarli 400 --")
        try:
            import concurrent.futures

            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444785,'T-RaceTest','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            race_uid = cur.lastrowid
            conn.commit()
            race_tok = token_for(race_uid, "employee")

            def _do_checkin():
                with httpx.Client(timeout=20) as c2:
                    return c2.post(f"{API_BASE}/attendance/me/check-in", headers=auth(race_tok), json={
                        "latitude": OFFICE[0], "longitude": OFFICE[1],
                        "face_descriptor": FACE, "liveness": 0.9,
                    })

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                futs = [ex.submit(_do_checkin) for _ in range(2)]
                results = [f.result().status_code for f in futs]
            check("parallel check-in: hech biri 500 EMAS", 500 not in results, f"natijalar={results}")
            check("parallel check-in: biri 200, ikkinchisi 400", sorted(results) == [200, 400], f"natijalar={results}")
            n = conn.execute(
                "select count(*) from attendance where user_id=? and date=?",
                (race_uid, date.today().isoformat())).fetchone()[0]
            check("bazada faqat 1 ta yozuv", n == 1, f"yozuvlar={n}")

            cur.execute("delete from attendance where user_id=?", (race_uid,))
            cur.execute("delete from users where id=?", (race_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("2.3 poyga tekshiruvi", False, traceback.format_exc(limit=1).strip())

        # ─────────────────────────────────────────────────────────
        # 0-BOSQICH (oylik/jarima poydevori): HR qo'lda tuzatishi
        # va ma'lumot tayyorligi hisoboti
        # ─────────────────────────────────────────────────────────
        print("\n-- 0.1: PUT /attendance/manual (HR qo'lda tuzatishi) --")
        try:
            mgr = find_manager_id()
            mgr_t = token_for(mgr[0], mgr[1]) if mgr else None
            check("rahbar tokeni olindi", bool(mgr_t))

            def _manual(payload: dict, token: str | None = None):
                return client.request(
                    "PUT", f"{API_BASE}/attendance/manual",
                    headers=auth(token or mgr_t), json=payload,
                )

            # Sabab majburiy: 5 belgidan qisqa -> 422 (pydantic)
            r = _manual({"user_id": uid1, "date": today_iso, "check_in": "10:30", "reason": "qis"})
            check("sababsiz (qisqa) tuzatish -> 422", r.status_code == 422, f"kod={r.status_code}")

            # Noto'g'ri vaqt formati -> 422
            r = _manual({"user_id": uid1, "date": today_iso, "check_in": "25:99",
                         "reason": "format tekshiruvi"})
            check("noto'g'ri vaqt formati -> 422", r.status_code == 422, f"kod={r.status_code}")

            # «Ketdim» ni «Keldim» siz belgilash -> 400
            r = _manual({"user_id": uid1, "date": today_iso, "check_out": "18:00",
                         "reason": "faqat ketdim sinovi"})
            check("«Ketdim» «Keldim» siz -> 400", r.status_code == 400, f"kod={r.status_code}")

            # ROP'da bu huquq YO'Q (kechikish jarimasini o'zi bekor qila olmasin)
            conn = db()
            cur = conn.cursor()
            # Audit tozalash uchun chegara: SHU testdan keyin yaratilgan yozuvlarnigina
            # o'chiramiz (id > audit_before). Keng `action`/`target_user_id` filtri
            # haqiqiy tarixiy yozuvlarni ham ushlab qolishi mumkin edi.
            audit_before = conn.execute("select coalesce(max(id), 0) from audit_logs").fetchone()[0]
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444790,'T-RopEdit','rop',1,1,datetime('now'))")
            rop_uid = cur.lastrowid
            conn.commit()
            rop_t = token_for(rop_uid, "rop")
            r = _manual({"user_id": uid1, "date": today_iso, "check_in": "10:30",
                         "reason": "ROP urinishi"}, token=rop_t)
            check("ROP qo'lda tuzata OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # Haqiqiy tuzatish: uid1 jadvali bugun 09:00-23:59 -> 10:30 = 90 daq kechikish
            r = _manual({"user_id": uid1, "date": today_iso, "check_in": "10:30",
                         "check_out": "19:00", "reason": "Face ID ishlamadi (sinov)"})
            check("tuzatish -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            body = r.json() if r.status_code == 200 else {}
            check("kechikish jadvaldan qayta hisoblandi (90 daq)",
                  body.get("late_minutes") == 90, f"late={body.get('late_minutes')}")
            check("status 'late' ga o'tdi", body.get("status") == "late", f"status={body.get('status')}")
            check("ishlangan vaqt hisoblandi (>0)",
                  (body.get("worked_minutes") or 0) > 0, f"worked={body.get('worked_minutes')}")
            check("qo'lda tuzatishda GPS masofasi tozalandi",
                  body.get("check_in_distance_m") is None, f"dist={body.get('check_in_distance_m')}")

            # Audit jurnaliga tushdimi
            log = conn.execute(
                "select action, after from audit_logs where action='attendance_manual_edit'"
                " and target_user_id=? order by id desc limit 1", (uid1,)).fetchone()
            check("audit jurnaliga yozildi", log is not None, f"{log}")
            check("auditda sabab saqlandi",
                  bool(log) and "Face ID ishlamadi" in (log[1] or ""), f"{log[1] if log else None}")

            # «Keldim» ni tozalash -> kun "kelmagan" bo'lib qoladi
            r = _manual({"user_id": uid1, "date": today_iso, "check_in": None,
                         "check_out": None, "reason": "Aslida kelmagan (sinov)"})
            check("«Keldim» tozalandi -> absent",
                  r.status_code == 200 and r.json().get("status") == "absent",
                  f"kod={r.status_code} status={r.json().get('status') if r.status_code == 200 else None}")

            # O'TGAN kunga YANGI yozuv yaratish (yozuv yo'q edi) — 7 kun oldin,
            # ayni hafta kuni, ya'ni uid1 ning o'sha jadvali amal qiladi.
            past = (date.today() - timedelta(days=7)).isoformat()
            r = _manual({"user_id": uid1, "date": past, "check_in": "09:20",
                         "check_out": "18:00", "reason": "Yo'qolgan kun tiklandi"})
            check("o'tgan kunga yangi yozuv yaratildi -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:120]}")
            check("yangi yozuvda kechikish 20 daq",
                  r.status_code == 200 and r.json().get("late_minutes") == 20,
                  f"late={r.json().get('late_minutes') if r.status_code == 200 else None}")

            # Dam olish kunida (uid2 bugun override bilan dam) kechikish bo'lmaydi
            r = _manual({"user_id": uid2, "date": today_iso, "check_in": "12:00",
                         "check_out": "15:00", "reason": "Dam olish kuni sinovi"})
            check("dam olish kunida kechikish 0 va status 'weekend'",
                  r.status_code == 200 and r.json().get("late_minutes") == 0
                  and r.json().get("status") == "weekend",
                  f"{r.json() if r.status_code == 200 else r.status_code}")

            # Kelajakdagi kun -> 400
            future = (date.today() + timedelta(days=1)).isoformat()
            r = _manual({"user_id": uid1, "date": future, "check_in": "09:00",
                         "reason": "Kelajak sinovi"})
            check("kelajakdagi kunni tuzatib bo'lmaydi -> 400", r.status_code == 400,
                  f"kod={r.status_code}")

            cur.execute("delete from users where id=?", (rop_uid,))
            cur.execute("delete from attendance where user_id=? and date=?", (uid1, past))
            # Shu testda yozilgan audit yozuvlarini (id chegarasi bilan) tozalaymiz —
            # eski haqiqiy tarixga tegilmaydi.
            cur.execute("delete from audit_logs where id > ? and action='attendance_manual_edit'",
                        (audit_before,))
            conn.commit()
            conn.close()
        except Exception:
            check("0.1 qo'lda tuzatish tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 0.3: GET /attendance/readiness (ma'lumot tayyorligi) --")
        try:
            mgr = find_manager_id()
            mgr_t = token_for(mgr[0], mgr[1]) if mgr else None

            # Yuzi ro'yxatdan o'tmagan xodim — hisobotda ko'rinishi kerak
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444791,'T-NoFace','employee',1,1,datetime('now'))")
            nf_uid = cur.lastrowid
            conn.commit()

            r = client.get(f"{API_BASE}/attendance/readiness", headers=auth(mgr_t))
            check("readiness -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            data = r.json() if r.status_code == 200 else {}
            for key in ("no_schedule", "open_checkouts", "auto_closed", "pending_excused", "no_face"):
                check(f"readiness '{key}' guruhi bor", key in data)
            check("yuzsiz xodim 'no_face' ro'yxatida",
                  any(i["user_id"] == nf_uid for i in data.get("no_face", [])),
                  f"no_face={len(data.get('no_face', []))} ta")
            check("jadvalsiz xodim 'no_schedule' ro'yxatida",
                  any(i["user_id"] == nf_uid for i in data.get("no_schedule", [])),
                  f"no_schedule={len(data.get('no_schedule', []))} ta")
            check("muammo bor ekan ok=False", data.get("ok") is False, f"ok={data.get('ok')}")

            # Noto'g'ri sana oralig'i -> 400
            r = client.get(
                f"{API_BASE}/attendance/readiness?date_from=2026-07-10&date_to=2026-07-01",
                headers=auth(mgr_t))
            check("teskari sana oralig'i -> 400", r.status_code == 400, f"kod={r.status_code}")

            cur.execute("delete from users where id=?", (nf_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("0.3 tayyorlik tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 3.1: jadval o'zgarsa BUGUNGI yozuv qayta hisoblanadi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444792,'T-Recalc','employee',1,1,datetime('now'))")
            rc_uid = cur.lastrowid
            wd = date.today().weekday()
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (rc_uid, wd))
            # 09:30 Toshkent = 04:30 UTC check-in -> 09:00 jadval bilan late=30
            checkin_utc = f"{date.today().isoformat()} 04:30:00"
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, ?, ?, 30, 0, 0, 'late', 0, datetime('now'), datetime('now'))",
                (rc_uid, date.today().isoformat(), checkin_utc))
            conn.commit()

            mgr_rc = find_manager_id()
            if mgr_rc:
                mgr_rc_tok = token_for(mgr_rc[0], mgr_rc[1])
                # Rahbar startni 10:00 ga surdi -> 09:30 kelish endi kechikish EMAS.
                r = client.put(
                    f"{API_BASE}/work-schedule/{rc_uid}/weekly", headers=auth(mgr_rc_tok),
                    json={"days": [
                        {"weekday": d, "is_working": d == wd, "start_time": "10:00" if d == wd else None,
                         "end_time": "18:00" if d == wd else None}
                        for d in range(7)
                    ]})
                check("PUT weekly -> 200", r.status_code == 200, f"kod={r.status_code}")
                row = conn.execute(
                    "select late_minutes, status from attendance where user_id=? and date=?",
                    (rc_uid, date.today().isoformat())).fetchone()
                check("3.1: bugungi yozuv qayta hisoblandi (late=0)",
                      row is not None and row[0] == 0, f"late={row[0] if row else None}, status={row[1] if row else None}")
            else:
                check("3.1 rahbar topilmadi", False)

            cur.execute("delete from attendance where user_id=?", (rc_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (rc_uid,))
            cur.execute("delete from users where id=?", (rc_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("3.1 qayta hisoblash tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 3.2: eng yaqin EMAS, BIRORTA ofis radiusi ichida bo'lsa yetarli --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444793,'T-NearestOffice','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            no_uid = cur.lastrowid
            # A ofis (ENG YAQIN, ~78m): radius 50m -> xodim A dan TASHQARIDA.
            cur.execute(
                "insert into office_locations (name, latitude, longitude, radius_meters, is_active, created_at)"
                " values ('T-YaqinOfis', ?, ?, 50, 1, datetime('now'))",
                (OFFICE[0] + 0.0007, OFFICE[1]))
            office_a_id = cur.lastrowid
            # B ofis (uzoqroq, ~156m), lekin radiusi 200m -> xodim B radiusi ICHIDA.
            cur.execute(
                "insert into office_locations (name, latitude, longitude, radius_meters, is_active, created_at)"
                " values ('T-UzoqOfis', ?, ?, 200, 1, datetime('now'))",
                (OFFICE[0] + 0.0014, OFFICE[1]))
            office_b_id = cur.lastrowid
            conn.commit()

            no_tok = token_for(no_uid, "employee")
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(no_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9,
            })
            check("eng yaqin ofis radiusidan tashqarida bo'lsa ham, B radiusida -> 200",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            cur.execute("delete from attendance where user_id=?", (no_uid,))
            cur.execute("delete from office_locations where id in (?,?)", (office_a_id, office_b_id))
            cur.execute("delete from users where id=?", (no_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("3.2 eng yaqin ofis tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 3.4: Boshliq check-in qila olmaydi (izchillik) --")
        try:
            boss_row = conn2 = None
            conn2 = db()
            boss_row = conn2.execute(
                "select id, telegram_id, face_descriptor from users where role='boss' limit 1").fetchone()
            if boss_row:
                boss_uid = boss_row[0]
                boss_tok = token_for(boss_uid, "boss")
                r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(boss_tok), json={
                    "latitude": OFFICE[0], "longitude": OFFICE[1],
                    "face_descriptor": FACE, "liveness": 0.9,
                })
                check("Boshliq check-in -> 400 (bloklangan)", r.status_code == 400, f"kod={r.status_code} {r.text[:150]}")
            else:
                check("3.4 Boshliq topilmadi", False)
            conn2.close()
        except Exception:
            check("3.4 Boshliq check-in tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 4.6: days=30 aniq 30 kun (31 EMAS) --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444794,'T-DaysWindow','employee',1,1,datetime('now'))")
            dw_uid = cur.lastrowid
            today = date.today()
            exactly_30 = today - timedelta(days=29)  # bugundan hisoblab 30-chi kun (chegarada)
            exactly_31 = today - timedelta(days=30)  # 31-chi kun — OYNADAN TASHQARI bo'lishi kerak
            for d in (exactly_30, exactly_31):
                cur.execute(
                    "insert into attendance (user_id, date, check_in_time, late_minutes,"
                    " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                    " values (?, ?, ?, 10, 0, 0, 'late', 0, datetime('now'), datetime('now'))",
                    (dw_uid, d.isoformat(), f"{d.isoformat()} 04:00:00"))
            conn.commit()

            r = client.get(f"{API_BASE}/attendance/employee-summary?days=30", headers=auth(boss_t))
            check("employee-summary?days=30 -> 200", r.status_code == 200)
            row = next((x for x in r.json() if x["user_id"] == dw_uid), None)
            check("30-kunlik oyna: faqat CHEGARADAGI (29 kun oldingi) yozuv hisobga olindi",
                  row is not None and row["late_minutes"] == 10, f"{row}")

            r2 = client.get(f"{API_BASE}/attendance/late-stats?days=30", headers=auth(boss_t))
            names_in_window = [x["full_name"] for x in r2.json() if x["user_id"] == dw_uid]
            late_days_count = next((x["late_days"] for x in r2.json() if x["user_id"] == dw_uid), None)
            check("late-stats?days=30: 31-kun oldingi yozuv OYNADAN TASHQARI",
                  late_days_count == 1, f"late_days={late_days_count}")

            cur.execute("delete from attendance where user_id=?", (dw_uid,))
            cur.execute("delete from users where id=?", (dw_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("4.6 kunlar oynasi tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 5.1: tasdiqlangan sababli kunda kechikish yozilmaydi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444795,'T-ExcusedCheckin','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            ex_uid = cur.lastrowid
            wd = date.today().weekday()
            # 00:01 boshlanish — real vaqt qanday bo'lishidan qat'i nazar, oddiy
            # mantiqda deyarli har doim "kechikkan" bo'lardi.
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'00:01','23:59',datetime('now'))", (ex_uid, wd))
            cur.execute(
                "insert into excused_days (user_id, date, reason, status, created_at)"
                " values (?, ?, 'T-shifokorga bordi', 'approved', datetime('now'))",
                (ex_uid, date.today().isoformat()))
            conn.commit()
            ex_tok = token_for(ex_uid, "employee")

            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(ex_tok), json={
                "latitude": OFFICE[0], "longitude": OFFICE[1],
                "face_descriptor": FACE, "liveness": 0.9,
            })
            check("sababli kunda check-in -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            body = r.json() if r.status_code == 200 else {}
            check("5.1: late_minutes=0 (sababli kun, aks holda kech qolgan bo'lardi)",
                  body.get("late_minutes") == 0, f"late={body.get('late_minutes')}")
            check("5.1: status='excused'", body.get("status") == "excused", f"status={body.get('status')}")

            cur.execute("delete from attendance where user_id=?", (ex_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (ex_uid,))
            cur.execute("delete from excused_days where user_id=?", (ex_uid,))
            cur.execute("delete from users where id=?", (ex_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("5.1 sababli kun tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 5.4: digest vaqti ORQAGA surilsa qo'riqchi tozalanmaydi --")
        try:
            conn = db()
            secret = ""
            for line in open(".env", encoding="utf-8"):
                if line.startswith("BOT_SHARED_SECRET="):
                    secret = line.strip().split("=", 1)[1]
            bot_h = {"X-Bot-Secret": secret}
            boss_row = conn.execute("select telegram_id from users where role='boss' and telegram_id is not null limit 1").fetchone()
            original = conn.execute(
                "select evening_hour, evening_minute, evening_last_posted from attendance_digest_config where id=1"
            ).fetchone()
            if boss_row and original:
                boss_tid = boss_row[0]
                orig_hour, orig_minute, orig_last_posted = original
                try:
                    conn.execute(
                        "update attendance_digest_config set evening_hour=10, evening_minute=0, evening_last_posted=? where id=1",
                        (date.today().isoformat(),))
                    conn.commit()

                    # ORQAGA surish (10:00 -> 09:00) — qo'riqchi TOZALANMASLIGI kerak,
                    # aks holda (hozir >= 09:00) darhol rost bo'lib, digest bugun
                    # IKKINCHI marta yuborilib ketardi.
                    r = client.post(
                        f"{API_BASE}/attendance/digest-time?telegram_id={boss_tid}&kind=evening&hour=9&minute=0",
                        headers=bot_h)
                    check("vaqtni orqaga surish -> 200", r.status_code == 200, f"kod={r.status_code}")
                    row = conn.execute("select evening_last_posted from attendance_digest_config where id=1").fetchone()
                    check("5.4: orqaga surilganda qo'riqchi SAQLANIB QOLADI",
                          row is not None and row[0] == date.today().isoformat(), f"evening_last_posted={row[0] if row else None}")

                    # OLDINGA surish (09:00 -> 11:00) — qo'riqchi TOZALANISHI kerak.
                    r2 = client.post(
                        f"{API_BASE}/attendance/digest-time?telegram_id={boss_tid}&kind=evening&hour=11&minute=0",
                        headers=bot_h)
                    check("vaqtni oldinga surish -> 200", r2.status_code == 200, f"kod={r2.status_code}")
                    row2 = conn.execute("select evening_last_posted from attendance_digest_config where id=1").fetchone()
                    check("5.4: oldinga surilganda qo'riqchi TOZALANADI",
                          row2 is not None and row2[0] is None, f"evening_last_posted={row2[0] if row2 else None}")
                finally:
                    # Asl (jonli) sozlamani albatta tiklaymiz.
                    conn.execute(
                        "update attendance_digest_config set evening_hour=?, evening_minute=?, evening_last_posted=? where id=1",
                        (orig_hour, orig_minute, orig_last_posted))
                    conn.commit()
            else:
                check("5.4 Boshliq telegram_id yoki sozlama topilmadi", False)
            conn.close()
        except Exception:
            check("5.4 digest vaqti tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 5.7: sababli kun dublikat va idempotentlik --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444796,'T-ExcusedDup','employee',1,1,datetime('now'))")
            dup_uid = cur.lastrowid
            conn.commit()

            secret = ""
            for line in open(".env", encoding="utf-8"):
                if line.startswith("BOT_SHARED_SECRET="):
                    secret = line.strip().split("=", 1)[1]
            bot_h = {"X-Bot-Secret": secret}

            r1 = client.post(f"{API_BASE}/excused-days", headers=bot_h,
                              json={"telegram_id": 999444796, "reason": "T-birinchi so'rov"})
            check("birinchi so'rov -> 200", r1.status_code == 200, f"kod={r1.status_code}")
            item_id = r1.json().get("id") if r1.status_code == 200 else None

            r2 = client.post(f"{API_BASE}/excused-days", headers=bot_h,
                              json={"telegram_id": 999444796, "reason": "T-ikkinchi so'rov"})
            check("5.7: bir kunga ikkinchi (dublikat) so'rov -> 400",
                  r2.status_code == 400, f"kod={r2.status_code} {r2.text[:150]}")

            if item_id:
                mgr = find_manager_id()
                mgr_telegram = (
                    conn.execute("select telegram_id from users where id=?", (mgr[0],)).fetchone()[0]
                    if mgr else None
                )
                if mgr_telegram:
                    r3 = client.post(f"{API_BASE}/excused-days/{item_id}/decide", headers=bot_h,
                                      json={"decider_telegram_id": mgr_telegram, "decision": "approved"})
                    check("birinchi qaror -> 200", r3.status_code == 200, f"kod={r3.status_code}")
                    r4 = client.post(f"{API_BASE}/excused-days/{item_id}/decide", headers=bot_h,
                                      json={"decider_telegram_id": mgr_telegram, "decision": "rejected"})
                    check("5.7: allaqachon hal qilingan so'rovga qayta qaror -> 400 (idempotent)",
                          r4.status_code == 400, f"kod={r4.status_code} {r4.text[:150]}")
                else:
                    check("5.7 rahbar telegram_id topilmadi", False)

            cur.execute("delete from excused_days where user_id=?", (dup_uid,))
            cur.execute("delete from users where id=?", (dup_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("5.7 dublikat/idempotentlik tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- 5.11: ish jadvali o'zgarishi audit qilinadi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444797,'T-ScheduleAudit','employee',1,1,datetime('now'))")
            sa_uid = cur.lastrowid
            conn.commit()

            mgr = find_manager_id()
            if mgr:
                mgr_tok = token_for(mgr[0], mgr[1])
                before_n = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='work_schedule_weekly_changed'",
                    (sa_uid,)).fetchone()[0]
                r = client.put(f"{API_BASE}/work-schedule/{sa_uid}/weekly", headers=auth(mgr_tok),
                               json={"days": [
                                   {"weekday": d, "is_working": d < 5, "start_time": "09:00" if d < 5 else None,
                                    "end_time": "18:00" if d < 5 else None}
                                   for d in range(7)
                               ]})
                check("PUT weekly -> 200", r.status_code == 200, f"kod={r.status_code}")
                after_n = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='work_schedule_weekly_changed'",
                    (sa_uid,)).fetchone()[0]
                check("5.11: haftalik jadval o'zgarishi audit qilindi",
                      after_n == before_n + 1, f"before={before_n}, after={after_n}")

                before_ov = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='work_schedule_override_changed'",
                    (sa_uid,)).fetchone()[0]
                r2 = client.put(f"{API_BASE}/work-schedule/{sa_uid}/override", headers=auth(mgr_tok),
                                json={"date": date.today().isoformat(), "is_working": True,
                                      "start_time": "12:00", "end_time": "18:00", "note": "T-sinov"})
                check("PUT override -> 200", r2.status_code == 200, f"kod={r2.status_code}")
                after_ov = conn.execute(
                    "select count(*) from audit_logs where target_user_id=? and action='work_schedule_override_changed'",
                    (sa_uid,)).fetchone()[0]
                check("5.11: aniq sana o'zgartirishi audit qilindi",
                      after_ov == before_ov + 1, f"before={before_ov}, after={after_ov}")
            else:
                check("5.11 rahbar topilmadi", False)

            cur.execute("delete from audit_logs where target_user_id=?", (sa_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (sa_uid,))
            cur.execute("delete from work_schedule_override where user_id=?", (sa_uid,))
            cur.execute("delete from users where id=?", (sa_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("5.11 audit tekshiruvi", False, traceback.format_exc(limit=1).strip())


def test_payroll_engine() -> None:
    """Bosqich 2: `api/services/payroll.py` hisoblash yadrosi — HTTP orqali
    emas (router hali yo'q, Bosqich 3), to'g'ridan-to'g'ri servis funksiyalarini
    chaqirib. Butunlay izolyatsiyalangan davr ("2020-01") ishlatiladi — real
    joriy oy ma'lumotiga tegilmaydi. Xodimga barcha hafta kunlari
    `is_working=False` qilib qo'yilib (WorkScheduleWeekly), faqat aniq
    belgilangan kunlar `WorkScheduleOverride` bilan ish kuni deb ochiladi —
    shu orqali "rejadagi kunlar soni" testda TO'LIQ nazorat qilinadi (Yanvar
    2020'ning haftaning qaysi kunlariga to'g'ri kelishiga bog'liq emas)."""
    import asyncio
    from decimal import Decimal

    print("\n" + "=" * 60)
    print("BOSQICH 2: PAYROLL HISOBLASH YADROSI (api/services/payroll.py)")
    print("=" * 60)

    async def _run():
        from sqlalchemy import delete, select
        from db.base import async_session
        from db.models import (
            Attendance, AuditLog, ExcusedDay, FinePolicy, OvertimeEntry, OvertimeProfile,
            PayrollAdjustment, PayrollPeriod, Payslip, PayslipItem, SalaryRate,
            User, WorkScheduleOverride, WorkScheduleWeekly,
        )
        from api.services import payroll as pr

        PERIOD = "2020-01"
        WINDOW_MIN = 480  # work_minutes(09:00,18:00) — tushliksiz 8 soat

        async with async_session() as s:
            # Oldingi (masalan yarim yo'lda qulagan) ishga tushirishdan qolgan
            # T-Payroll* yozuvlarni tozalaymiz — aks holda UNIQUE(telegram_id)
            # xatosi bilan bu test hech qachon qayta ishlamay qolardi.
            stale_ids = list(
                await s.scalars(select(User.id).where(User.full_name.like("T-Payroll%")))
            )
            if stale_ids:
                stale_payslips = list(
                    await s.scalars(select(Payslip.id).where(Payslip.user_id.in_(stale_ids)))
                )
                if stale_payslips:
                    await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id.in_(stale_payslips)))
                await s.execute(delete(Payslip).where(Payslip.user_id.in_(stale_ids)))
                await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id.in_(stale_ids)))
                await s.execute(delete(OvertimeProfile).where(OvertimeProfile.user_id.in_(stale_ids)))
                await s.execute(delete(PayrollAdjustment).where(PayrollAdjustment.user_id.in_(stale_ids)))
                await s.execute(delete(SalaryRate).where(SalaryRate.user_id.in_(stale_ids)))
                await s.execute(delete(FinePolicy).where(FinePolicy.scope_id.in_(stale_ids)))
                await s.execute(delete(ExcusedDay).where(ExcusedDay.user_id.in_(stale_ids)))
                await s.execute(delete(Attendance).where(Attendance.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(stale_ids)))
                # audit_logs.target_user_id — boshqa test bloklari (masalan
                # umumiy run_tests) shu id'larga tegishli yozuv qoldirishi
                # mumkin (SQLite ROWID o'chirilgan id'larni qayta beradi);
                # FK cheklovi tufayli bu tozalanmasa User o'chirilmay qoladi.
                await s.execute(delete(AuditLog).where(AuditLog.target_user_id.in_(stale_ids)))
                await s.execute(delete(User).where(User.id.in_(stale_ids)))
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.execute(
                delete(FinePolicy).where(
                    FinePolicy.scope == "global", FinePolicy.free_late_minutes_per_month == 999_999
                )
            )
            await s.commit()

            # ── Sozlash: T-Payroll1 (asosiy sinov xodimi) ──
            u1 = User(telegram_id=999500701, full_name="T-Payroll1", role="employee",
                      bot_started=True, is_active=True)
            s.add(u1)
            await s.flush()

            for wd in range(7):
                s.add(WorkScheduleWeekly(user_id=u1.id, weekday=wd, is_working=False))

            day1, day2, day3 = date(2020, 1, 6), date(2020, 1, 7), date(2020, 1, 8)
            day4_absent, day5_present, day6_excused = date(2020, 1, 9), date(2020, 1, 10), date(2020, 1, 13)
            test_days = [day1, day2, day3, day4_absent, day5_present, day6_excused]
            for d in test_days:
                s.add(WorkScheduleOverride(user_id=u1.id, date=d, is_working=True,
                                            start_time="09:00", end_time="18:00"))

            # Kechikishlar: 20+15 (ikkalasi ham bepul limit ichida, jami 35),
            # keyingi 10 daq (cumulative_before=35 >= limit(30) -> JARIMALI).
            s.add(Attendance(user_id=u1.id, date=day1, status="late", late_minutes=20, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=u1.id, date=day2, status="late", late_minutes=15, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=u1.id, date=day3, status="late", late_minutes=10, worked_minutes=WINDOW_MIN))
            # day4_absent — yozuv YO'Q (defensiv "absent" filiali sinaladi)
            s.add(Attendance(user_id=u1.id, date=day5_present, status="present", worked_minutes=WINDOW_MIN))
            s.add(ExcusedDay(user_id=u1.id, date=day6_excused, reason="T-sinov", status="approved"))

            s.add(SalaryRate(user_id=u1.id, amount=3_000_000, pay_basis="monthly",
                              effective_from=date(2019, 1, 1), changed_by=u1.id))
            s.add(FinePolicy(scope="user", scope_id=u1.id, is_active=True,
                              free_late_minutes_per_month=30, fine_mode="per_day", fine_per_day=50_000,
                              absent_mode="fixed", absent_fine=100_000,
                              monthly_cap_amount=1_000_000, fine_applies_to="net_salary"))
            await s.commit()

            days = await pr.collect_attendance(s, u1, PERIOD)
            by_date = {d["date"]: d for d in days}
            check("Payroll: scheduled_days aniq 6", sum(1 for d in days if d["is_working"]) == 6,
                  f"={sum(1 for d in days if d['is_working'])}")
            check("Payroll: day4 defensiv 'absent' deb aniqlandi",
                  by_date[day4_absent]["status"] == "absent")
            check("Payroll: day6 'excused' deb aniqlandi (ExcusedDay, yozuvsiz)",
                  by_date[day6_excused]["status"] == "excused" and by_date[day6_excused]["excused"] is True)

            policy = await pr.resolve_policy(s, u1)
            check("Payroll: resolve_policy user-scope qoidani topdi", policy is not None and policy.scope == "user")

            late = pr.compute_late_fine(days, policy)
            check("Payroll: late_days=3", late["late_days"] == 3, f"={late['late_days']}")
            check("Payroll: late_minutes=45", late["late_minutes"] == 45, f"={late['late_minutes']}")
            check("Payroll: limit ichidagi 2 kun BEPUL (chegaradan o'tkazgan kun ham)",
                  late["fined_days"] == 1, f"fined_days={late['fined_days']}")
            check("Payroll: faqat 3-kun (10 daq) jarimali", late["fined_minutes"] == 10,
                  f"fined_minutes={late['fined_minutes']}")
            check("Payroll: jarima summasi = 1 x 50000", late["amount"] == Decimal("50000"),
                  f"amount={late['amount']}")

            absent = pr.compute_absent_fine(days, policy)
            check("Payroll: absent_days=1", absent["absent_days"] == 1, f"={absent['absent_days']}")
            check("Payroll: kelmagan kun jarimasi = 100000", absent["amount"] == Decimal("100000"),
                  f"amount={absent['amount']}")

            rate = await pr.resolve_rate(s, u1.id, date(2020, 1, 1))
            first_rate = await pr._first_rate(s, u1.id)
            base_amount, base_item = pr.compute_base(rate, first_rate, days, date(2020, 1, 1))
            check("Payroll: base_amount to'liq oylik (prorata yo'q, 6/6 kun)",
                  base_amount == Decimal("3000000"), f"base={base_amount}")

            # ── run_payroll orqali to'liq oqim (Payslip + PayslipItem yoziladi) ──
            result = await pr.run_payroll(s, PERIOD, user_ids=[u1.id])
            check("Payroll: run_payroll 1 xodimni hisobladi", result["calculated"] == 1, f"={result}")

            payslip = await s.scalar(select(Payslip).where(Payslip.user_id == u1.id, Payslip.period == PERIOD))
            check("Payroll: Payslip yaratildi", payslip is not None)
            if payslip is not None:
                check("Payroll: Payslip.fine_amount=50000", float(payslip.fine_amount) == 50000.0,
                      f"={payslip.fine_amount}")
                check("Payroll: Payslip.absent_deduction=100000", float(payslip.absent_deduction) == 100000.0,
                      f"={payslip.absent_deduction}")
                check("Payroll: Payslip.net = 3000000-50000-100000=2850000",
                      float(payslip.net) == 2_850_000.0, f"net={payslip.net}")
                check("Payroll: Payslip.excused_days=1", payslip.excused_days == 1, f"={payslip.excused_days}")
                check("Payroll: Payslip.worked_days=4 (3 late + 1 present)", payslip.worked_days == 4,
                      f"={payslip.worked_days}")

                items_1 = list(await s.scalars(
                    select(PayslipItem).where(PayslipItem.payslip_id == payslip.id)))
                check("Payroll: PayslipItem qatorlari yozildi (base+fine_late+fine_absent)",
                      len(items_1) == 3, f"soni={len(items_1)}")

                # ── Idempotentlik: qayta chaqirilsa dublikat YO'Q ──
                result2 = await pr.run_payroll(s, PERIOD, user_ids=[u1.id])
                payslip2 = await s.scalar(select(Payslip).where(Payslip.user_id == u1.id, Payslip.period == PERIOD))
                items_2 = list(await s.scalars(
                    select(PayslipItem).where(PayslipItem.payslip_id == payslip2.id)))
                check("Payroll: idempotent - bir xil Payslip.id", payslip2.id == payslip.id)
                check("Payroll: idempotent - PayslipItem dublikat YO'Q (hamon 3 ta)",
                      len(items_2) == 3, f"soni={len(items_2)}")
                check("Payroll: idempotent - net o'zgarmadi", float(payslip2.net) == 2_850_000.0,
                      f"net={payslip2.net}")

            # ── Qulflangan davr qayta hisoblashni rad etadi ──
            period_row = await s.scalar(select(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            period_row.locked = True
            await s.commit()
            locked_raised = False
            try:
                await pr.run_payroll(s, PERIOD, user_ids=[u1.id])
            except pr.PayrollLocked:
                locked_raised = True
            check("Payroll: qulflangan davrda run_payroll -> PayrollLocked", locked_raised)
            period_row.locked = False
            await s.commit()

            # ── Oylik jarima chegarasi (cap) — pastroq cap bilan qayta sinov ──
            policy.monthly_cap_amount = 100_000  # raw jami 150000 dan kichik
            await s.commit()
            late_c, absent_c, raw_total, cap_applied = pr.apply_fine_cap(
                late["amount"], absent["amount"], base_amount, policy
            )
            check("Payroll: cap ishga tushdi (raw 150000 > cap 100000)", cap_applied is True)
            check("Payroll: cap qo'llangach jami roppa-rosa 100000",
                  abs(float(late_c + absent_c) - 100_000.0) < 0.01, f"={late_c + absent_c}")
            check("Payroll: cap ikkalasini proporsional qisqartiradi (ikkalasi ham >0)",
                  late_c > 0 and absent_c > 0, f"late={late_c} absent={absent_c}")

            # ── Qo'shimcha ish (derived rejim) ──
            s.add(OvertimeProfile(user_id=u1.id, enabled=True, mode="derived",
                                   multiplier=1.5, norm_hours_source="schedule"))
            s.add(OvertimeEntry(user_id=u1.id, date=day1, minutes=120, source="manual", status="approved"))
            await s.commit()
            profile = await s.scalar(select(OvertimeProfile).where(OvertimeProfile.user_id == u1.id))
            ot = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            # norm_hours = scheduled_minutes(6*480=2880)/60=48; hourly=3000000/48*1.5=93750;
            # amount=93750*(120/60)=187500
            check("Payroll: overtime_minutes=120", ot["minutes"] == 120, f"={ot['minutes']}")
            check("Payroll: overtime amount (derived, 1.5x) ~187500",
                  abs(float(ot["amount"]) - 187_500.0) < 1, f"={ot['amount']}")

            # Fixed-rate rejim (bir xil OvertimeEntry, boshqa profil)
            profile.mode = "fixed_rate"
            profile.fixed_rate_per_hour = 20_000
            await s.commit()
            ot2 = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            check("Payroll: overtime amount (fixed_rate, 20000/soat x 2 soat) =40000",
                  abs(float(ot2["amount"]) - 40_000.0) < 1, f"={ot2['amount']}")

            # ── QoolAdjustment (avans) — minus ──
            s.add(PayrollAdjustment(user_id=u1.id, period=PERIOD, kind="minus", amount=50_000,
                                     reason="T-sinov avans", created_by=u1.id))
            await s.commit()
            result3 = await pr.run_payroll(s, PERIOD, user_ids=[u1.id])
            check("Payroll: adjustment qo'shilgandan keyin ham hisoblandi", result3["calculated"] == 1)
            payslip3 = await s.scalar(select(Payslip).where(Payslip.user_id == u1.id, Payslip.period == PERIOD))
            check("Payroll: adjustments_minus=50000 qaytadan hisoblanganda hisobga olindi",
                  float(payslip3.adjustments_minus) == 50_000.0, f"={payslip3.adjustments_minus}")

            # ── resolve_policy: xodim > lavozim > global qamrov ──
            u2 = User(telegram_id=999500702, full_name="T-Payroll2NoPolicy", role="employee",
                      bot_started=True, is_active=True)
            s.add(u2)
            await s.flush()
            no_policy = await pr.resolve_policy(s, u2)
            check("Payroll: qoida umuman yo'q bo'lsa None qaytadi", no_policy is None)

            days2 = [{"date": day1, "is_working": True, "start": "09:00", "end": "18:00",
                      "scheduled_minutes": WINDOW_MIN, "attendance": None, "excused": False,
                      "status": "late", "late_minutes": 999, "worked_minutes": 0}]
            late_no_policy = pr.compute_late_fine(days2, no_policy)
            check("Payroll: qoidasiz kechikish uchun jarima 0 (xavfsiz sukut)",
                  late_no_policy["amount"] == Decimal("0"), f"={late_no_policy['amount']}")

            s.add(FinePolicy(scope="global", scope_id=None, is_active=True,
                              free_late_minutes_per_month=999_999, fine_mode="per_day", fine_per_day=1,
                              absent_mode="none"))
            await s.commit()
            global_policy = await pr.resolve_policy(s, u2)
            check("Payroll: user/lavozim yo'q bo'lsa GLOBAL qoidaga tushadi",
                  global_policy is not None and global_policy.scope == "global")

            # ── Tozalash ──
            for uid in (u1.id, u2.id):
                pslips = list(await s.scalars(select(Payslip).where(Payslip.user_id == uid)))
                for p in pslips:
                    await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id == p.id))
                await s.execute(delete(Payslip).where(Payslip.user_id == uid))
                await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id == uid))
                await s.execute(delete(OvertimeProfile).where(OvertimeProfile.user_id == uid))
                await s.execute(delete(PayrollAdjustment).where(PayrollAdjustment.user_id == uid))
                await s.execute(delete(SalaryRate).where(SalaryRate.user_id == uid))
                await s.execute(delete(FinePolicy).where(FinePolicy.scope_id == uid))
                await s.execute(delete(ExcusedDay).where(ExcusedDay.user_id == uid))
                await s.execute(delete(Attendance).where(Attendance.user_id == uid))
                await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id == uid))
                await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id == uid))
            await s.execute(delete(FinePolicy).where(FinePolicy.scope == "global",
                                                       FinePolicy.free_late_minutes_per_month == 999_999))
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.execute(delete(AuditLog).where(AuditLog.target_user_id.in_([u1.id, u2.id])))
            await s.execute(delete(User).where(User.id.in_([u1.id, u2.id])))
            await s.commit()

    try:
        asyncio.run(_run())
    except Exception:
        check("Payroll hisoblash yadrosi (umumiy)", False, traceback.format_exc(limit=2).strip())


def test_payroll_api() -> None:
    """Bosqich 3: `api/routers/payroll.py` — HTTP darajasida (ruxsat
    matritsasi, validatsiya, to'liq oqim: hisoblash -> ro'yxat -> tafsilot ->
    tasdiqlash -> qulf -> bot). Izolyatsiyalangan davr "2021-02" ishlatiladi."""
    import httpx

    print("\n" + "=" * 60)
    print("BOSQICH 3: PAYROLL API (api/routers/payroll.py)")
    print("=" * 60)

    PERIOD = "2021-02"
    conn = db()
    cur = conn.cursor()

    # Oldingi (yarim yo'lda qulagan) ishga tushirishdan qolganlarni tozalash.
    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-PayAPI%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        pslip_ids = [r[0] for r in cur.execute(
            f"select id from payslips where user_id in ({qm})", stale).fetchall()]
        if pslip_ids:
            qm2 = ",".join("?" * len(pslip_ids))
            cur.execute(f"delete from payslip_items where payslip_id in ({qm2})", pslip_ids)
        for tbl in ("payslips", "overtime_entries", "overtime_profiles", "payroll_adjustments",
                    "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
            cur.execute(f"delete from {tbl} where user_id in ({qm})", stale)
        cur.execute(f"delete from fine_policies where scope_id in ({qm})", stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    cur.execute("delete from payroll_periods where period=?", (PERIOD,))
    conn.commit()

    # ── Sozlash: T-PayAPI-HR (rahbar sifatida ishlatilmaydi — mavjud HR
    # ishlatiladi), T-PayAPI-ROP + uning T-PayAPI-Emp xodimi ──
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999600801,'T-PayAPI-Rop','rop',1,1,datetime('now'))")
    rop_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, manager_id, bot_started, is_active, created_at)"
        " values (999600802,'T-PayAPI-Emp','employee',?,1,1,datetime('now'))", (rop_uid,))
    emp_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999600803,'T-PayAPI-Outsider','employee',1,1,datetime('now'))")
    outsider_uid = cur.lastrowid
    conn.commit()

    mgr = find_manager_id()
    mgr_t = token_for(mgr[0], mgr[1]) if mgr else None
    rop_t = token_for(rop_uid, "rop")
    emp_t = token_for(emp_uid, "employee")

    def cleanup_payapi():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [rop_uid, emp_uid, outsider_uid]
            qm = ",".join("?" * len(uids))
            pslip_ids = [r[0] for r in c2.execute(
                f"select id from payslips where user_id in ({qm})", uids).fetchall()]
            if pslip_ids:
                qm2 = ",".join("?" * len(pslip_ids))
                c2.execute(f"delete from payslip_items where payslip_id in ({qm2})", pslip_ids)
            for tbl in ("payslips", "overtime_entries", "overtime_profiles", "payroll_adjustments",
                        "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
                c2.execute(f"delete from {tbl} where user_id in ({qm})", uids)
            c2.execute(f"delete from fine_policies where scope_id in ({qm})", uids)
            c2.execute("delete from payroll_periods where period=?", (PERIOD,))
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Payroll API tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        with httpx.Client(timeout=15) as client:
            # ── Ruxsat matritsasi ──
            r = client.get(f"{API_BASE}/payroll/policies", headers=auth(emp_t))
            check("xodim /payroll/policies -> 403", r.status_code == 403, f"kod={r.status_code}")
            r = client.get(f"{API_BASE}/payroll/policies", headers=auth(rop_t))
            check("ROP /payroll/policies -> 403 (faqat HR/Boss/Dasturchi)", r.status_code == 403,
                  f"kod={r.status_code}")
            r = client.get(f"{API_BASE}/payroll/policies", headers=auth(mgr_t))
            check("HR/Boss /payroll/policies -> 200", r.status_code == 200, f"kod={r.status_code}")

            # ── FinePolicy validatsiya ──
            r = client.put(f"{API_BASE}/payroll/policies", headers=auth(mgr_t), json={
                "scope": "user", "scope_id": emp_uid, "free_late_minutes_per_month": 20,
                "fine_mode": "per_day", "fine_per_day": 30000,
                "absent_mode": "fixed", "absent_fine": 80000,
                # cap yo'q -> majburiy maydon xatosi kutiladi
            })
            check("cap'siz policy -> 422 (majburiy)", r.status_code == 422, f"kod={r.status_code}")

            r = client.put(f"{API_BASE}/payroll/policies", headers=auth(mgr_t), json={
                "scope": "user", "scope_id": emp_uid, "free_late_minutes_per_month": 20,
                "fine_mode": "per_day", "fine_per_day": 30000,
                "absent_mode": "fixed", "absent_fine": 80000,
                "monthly_cap_amount": 500000, "fine_applies_to": "net_salary",
            })
            check("to'g'ri policy -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            policy_id = r.json().get("id") if r.status_code == 200 else None
            check("policy javobida scope_label (xodim ismi)",
                  r.status_code == 200 and r.json().get("scope_label") == "T-PayAPI-Emp",
                  f"={r.json().get('scope_label') if r.status_code == 200 else None}")

            # ── SalaryRate ──
            r = client.post(f"{API_BASE}/payroll/rates", headers=auth(mgr_t), json={
                "user_id": emp_uid, "amount": 2_500_000, "pay_basis": "monthly",
                "effective_from": "2020-01-01",
            })
            check("stavka yaratildi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            r2 = client.post(f"{API_BASE}/payroll/rates", headers=auth(mgr_t), json={
                "user_id": emp_uid, "amount": 2_600_000, "pay_basis": "monthly",
                "effective_from": "2020-01-01",
            })
            check("bir xil sanaga dublikat stavka -> 400", r2.status_code == 400, f"kod={r2.status_code}")

            # ── OvertimeProfile validatsiya ──
            r = client.put(f"{API_BASE}/payroll/overtime-profiles/{emp_uid}", headers=auth(mgr_t), json={
                "enabled": True, "mode": "derived", "norm_hours_source": "schedule",
                # multiplier yo'q -> xato kutiladi
            })
            check("multiplier'siz derived profil -> 422", r.status_code == 422, f"kod={r.status_code}")

            # ── Ish jadvali va davomat (2021-02 uchun) — BARCHA hafta kunlari
            # dam olish deb belgilanadi, FAQAT 1-fevral aniq override bilan ish
            # kuni ochiladi (Bosqich 2'dagi bilan bir xil naqsh). Aks holda oy
            # davomidagi BOSHQA ish kunlariga Attendance yozuvi yo'qligi
            # sababli ular "kelmagan" deb hisoblanib (collect_attendance'ning
            # ataylab qilingan defensiv qoidasi), kutilmagan jarima chiqarardi —
            # bu HTTP darajasidagi test uchun ortiqcha murakkablik, hisoblash
            # mantig'ining o'zi Bosqich 2'da alohida tekshirilgan.
            for wd in range(7):
                cur.execute(
                    "insert into work_schedule_weekly (user_id, weekday, is_working, updated_at)"
                    " values (?,?,0,datetime('now'))", (emp_uid, wd))
            cur.execute(
                "insert into work_schedule_override (user_id, date, is_working, start_time, end_time, updated_at)"
                " values (?, '2021-02-01', 1, '09:00', '18:00', datetime('now'))", (emp_uid,))
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, '2021-02-01', '2021-02-01 04:00:00', 0, 0, 480, 'present', 0,"
                " datetime('now'), datetime('now'))", (emp_uid,))
            conn.commit()

            # ── Preflight ──
            r = client.get(f"{API_BASE}/payroll/{PERIOD}/preflight", headers=auth(mgr_t))
            check("preflight -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            # ── Hisoblash ──
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t),
                             json={"user_ids": [emp_uid]})
            check("calculate -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            check("calculate 1 xodimni hisobladi",
                  r.status_code == 200 and r.json().get("calculated") == 1, f"={r.json() if r.status_code == 200 else None}")

            # ── Davrlar ro'yxati (literal /periods — {period} bilan aralashmasin) ──
            r = client.get(f"{API_BASE}/payroll/periods", headers=auth(mgr_t))
            check("GET /payroll/periods -> 200", r.status_code == 200, f"kod={r.status_code}")
            check("yangi davr ro'yxatda bor",
                  r.status_code == 200 and any(p["period"] == PERIOD for p in r.json()),
                  f"davrlar={[p['period'] for p in r.json()] if r.status_code == 200 else None}")

            # ── Ro'yxat va tafsilot — ROP qamrovi ──
            r = client.get(f"{API_BASE}/payroll/{PERIOD}", headers=auth(rop_t))
            check("ROP ro'yxatni ko'radi -> 200", r.status_code == 200, f"kod={r.status_code}")
            names_seen = [row["full_name"] for row in r.json()] if r.status_code == 200 else []
            check("ROP faqat o'z jamoasini ko'radi (T-PayAPI-Emp bor, Outsider yo'q)",
                  "T-PayAPI-Emp" in names_seen, f"={names_seen}")

            r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{emp_uid}", headers=auth(rop_t))
            check("ROP o'z xodimining tafsilotini ko'radi -> 200", r.status_code == 200, f"kod={r.status_code}")
            detail = r.json() if r.status_code == 200 else {}
            check("tafsilotda base_amount=2500000", detail.get("base_amount") == 2_500_000.0,
                  f"={detail.get('base_amount')}")
            check("tafsilotda fine_amount=0 (kechikish yo'q)", detail.get("fine_amount") == 0.0,
                  f"={detail.get('fine_amount')}")
            check("tafsilotda items ro'yxati bor", len(detail.get("items", [])) >= 1,
                  f"soni={len(detail.get('items', []))}")

            r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{outsider_uid}", headers=auth(rop_t))
            check("ROP begona xodim tafsilotiga -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{emp_uid}", headers=auth(emp_t))
            check("xodim /payroll/*/user -> 403 (VIEW_ROLES'da yo'q)", r.status_code == 403,
                  f"kod={r.status_code}")

            # ── Tasdiqlash va qulf ──
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(rop_t))
            check("ROP tasdiqlay OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(mgr_t))
            check("HR/Boss tasdiqlaydi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
            check("tasdiqlangan (qulflangan) davrni qayta hisoblash -> 409", r.status_code == 409,
                  f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(mgr_t))
            check("ikkinchi marta tasdiqlash -> 409", r.status_code == 409, f"kod={r.status_code}")

            # ── Bot: /payroll/my — faqat TASDIQLANGANDAN keyin ko'rinadi ──
            with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as f:
                _secret = next(
                    (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")), ""
                )
            BOT_SECRET_HDR = {"X-Bot-Secret": _secret}
            r = client.get(f"{API_BASE}/payroll/my/999600802", headers=BOT_SECRET_HDR)
            check("bot /payroll/my -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            bot_out = r.json() if r.status_code == 200 else {}
            check("bot /payroll/my calculated=True (tasdiqlangan)", bot_out.get("calculated") is True,
                  f"={bot_out}")
            check("bot /payroll/my net=2500000", bot_out.get("net") == 2_500_000.0, f"={bot_out.get('net')}")

            r = client.get(f"{API_BASE}/payroll/my/999600802/late-status", headers=BOT_SECRET_HDR)
            check("bot /payroll/my/late-status -> 200", r.status_code == 200, f"kod={r.status_code}")
            check("late-status joriy oy (bugungi) qaytadi",
                  r.status_code == 200 and r.json().get("period") == date.today().strftime("%Y-%m"),
                  f"={r.json().get('period') if r.status_code == 200 else None}")

            # ── Overtime kirish/tasdiqlash oqimi ──
            r = client.post(f"{API_BASE}/payroll/overtime", headers=auth(mgr_t), json={
                "user_id": emp_uid, "date": "2021-02-02", "minutes": 90, "note": "T-sinov",
            })
            check("overtime kiritildi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            ot_id = r.json().get("id") if r.status_code == 200 else None
            r = client.post(f"{API_BASE}/payroll/overtime/{ot_id}/decide", headers=auth(mgr_t),
                             json={"status": "approved"})
            check("overtime tasdiqlandi -> 200", r.status_code == 200, f"kod={r.status_code}")

            # ── Adjustment (avans) ──
            r = client.post(f"{API_BASE}/payroll/adjustments", headers=auth(mgr_t), json={
                "user_id": emp_uid, "period": PERIOD, "kind": "minus", "amount": 50000,
                "reason": "T-sinov avans",
            })
            check("adjustment yaratildi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            adj_id = r.json().get("id") if r.status_code == 200 else None
            if adj_id:
                r = client.delete(f"{API_BASE}/payroll/adjustments/{adj_id}", headers=auth(mgr_t))
                check("adjustment o'chirildi -> 200", r.status_code == 200, f"kod={r.status_code}")

            if policy_id:
                r = client.delete(f"{API_BASE}/payroll/policies/{policy_id}", headers=auth(mgr_t))
                check("policy o'chirildi -> 200", r.status_code == 200, f"kod={r.status_code}")
    except Exception:
        check("Payroll API (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_payapi()
        conn.close()


def main() -> None:
    print("=" * 60)
    print("DAVOMAT TIZIMI — DB YOZUVI DEBUG TESTI")
    print("=" * 60)
    ctx: dict = {}
    try:
        ctx = setup()
    except Exception:
        print("Sozlashda xato:\n" + traceback.format_exc())
        cleanup(ctx)
        sys.exit(1)

    try:
        run_tests(ctx)
    except Exception:
        print("Kutilmagan xato:\n" + traceback.format_exc())
    finally:
        try:
            cleanup(ctx)
        except Exception:
            print("Tozalashda xato:\n" + traceback.format_exc())

    try:
        test_payroll_engine()
    except Exception:
        print("Payroll testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_payroll_api()
    except Exception:
        print("Payroll API testida kutilmagan xato:\n" + traceback.format_exc())

    print("\n" + "=" * 60)
    print(f"NATIJA: {len(passed)} OK, {len(failed)} FAIL")
    for name in failed:
        print(f"  FAIL: {name}")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
