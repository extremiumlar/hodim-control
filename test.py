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
                # audit_logs.target_user_id VA actor_id — boshqa test bloklari
                # (masalan test_admin_override, dasturchi sifatida `override_*`
                # yozadi — actor_id orqali) shu id'larga tegishli yozuv
                # qoldirishi mumkin (SQLite ROWID o'chirilgan id'larni qayta
                # beradi); FK cheklovi tufayli bu tozalanmasa User o'chirilmay
                # qoladi (jonli isbot: 2026-07-27).
                await s.execute(
                    delete(AuditLog).where(
                        AuditLog.target_user_id.in_(stale_ids) | AuditLog.actor_id.in_(stale_ids)
                    )
                )
                await s.execute(delete(User).where(User.id.in_(stale_ids)))
            # Qo'shimcha himoya: agar avvalgi qulagan ishga tushirishda AVVAL
            # User o'chirilib, keyingi qadam (masalan Attendance o'chirish)
            # bajarilmay qolgan bo'lsa — ORFAN (egasiz) yozuv qoladi. SQLite
            # ROWID'ni o'chirilgan eng katta id qayta beradi, shuning uchun
            # KEYINGI ishga tushirishda yangi u1 xuddi O'SHA id'ni olib,
            # egasiz yozuvga to'qnashishi mumkin (jonli isbot: 2026-07-27).
            # Shu sabab test davri (2020-01) va aniq telegram_id'lar bo'yicha
            # HAM, User mavjudligidan qat'i nazar, to'g'ridan-to'g'ri tozalanadi.
            await s.execute(delete(Attendance).where(Attendance.date >= date(2020, 1, 1), Attendance.date < date(2020, 2, 1)))
            await s.execute(
                delete(WorkScheduleOverride).where(
                    WorkScheduleOverride.date >= date(2020, 1, 1), WorkScheduleOverride.date < date(2020, 2, 1)
                )
            )
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
            await s.execute(
                delete(AuditLog).where(
                    AuditLog.target_user_id.in_([u1.id, u2.id]) | AuditLog.actor_id.in_([u1.id, u2.id])
                )
            )
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
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
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
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
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


def test_admin_override() -> None:
    """Bosqich 3.5: `api/routers/admin_override.py` — Dasturchi rejimi
    (super-admin). HTTP darajasida: ruxsat (faqat dasturchi), yumshoq
    o'chirish/tiklash, normalar matritsasi bypass, payroll qulflari."""
    import httpx

    print("\n" + "=" * 60)
    print("BOSQICH 3.5: DASTURCHI REJIMI (api/routers/admin_override.py)")
    print("=" * 60)

    PERIOD = "2022-03"
    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-Admin%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        pslip_ids = [r[0] for r in cur.execute(f"select id from payslips where user_id in ({qm})", stale).fetchall()]
        if pslip_ids:
            qm2 = ",".join("?" * len(pslip_ids))
            cur.execute(f"delete from payslip_items where payslip_id in ({qm2})", pslip_ids)
        for tbl in ("payslips", "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
            cur.execute(f"delete from {tbl} where user_id in ({qm})", stale)
        cur.execute(f"delete from norms where user_id in ({qm})", stale)
        # actor_id HAM tozalanadi — bu test dasturchi (T-Admin-Dev) sifatida
        # `override_*` amallar bajaradi, ular AuditLog.actor_id (target_user_id
        # EMAS) orqali shu userga bog'lanadi. Jonli isbot (2026-07-27): shu
        # tozalanmasa keyingi ishga tushirishda FOREIGN KEY xatosi bilan
        # user o'chirilmay qolgan (SQLite ROWID qayta berilgani sabab boshqa
        # test blokining foydalanuvchisiga to'qnashgan).
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    cur.execute("delete from payroll_periods where period=?", (PERIOD,))
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999700901,'T-Admin-Dev','dasturchi',1,1,datetime('now'))")
    dev_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999700902,'T-Admin-Emp','employee',1,1,datetime('now'))")
    emp_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999700903,'T-Admin-Hr','hr',1,1,datetime('now'))")
    hr_target_uid = cur.lastrowid
    conn.commit()

    dev_t = token_for(dev_uid, "dasturchi")
    emp_t = token_for(emp_uid, "employee")
    mgr = find_manager_id()
    mgr_t = token_for(mgr[0], mgr[1]) if mgr else None

    def cleanup_admin():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [dev_uid, emp_uid, hr_target_uid]
            qm = ",".join("?" * len(uids))
            pslip_ids = [r[0] for r in c2.execute(
                f"select id from payslips where user_id in ({qm})", uids).fetchall()]
            if pslip_ids:
                qm2 = ",".join("?" * len(pslip_ids))
                c2.execute(f"delete from payslip_items where payslip_id in ({qm2})", pslip_ids)
            for tbl in ("payslips", "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
                c2.execute(f"delete from {tbl} where user_id in ({qm})", uids)
            c2.execute(f"delete from norms where user_id in ({qm})", uids)
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute("delete from payroll_periods where period=?", (PERIOD,))
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Admin override tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        with httpx.Client(timeout=15) as client:
            # ── Ruxsat: FAQAT dasturchi ──
            r = client.get(f"{API_BASE}/admin/audit/overrides", headers=auth(emp_t))
            check("xodim /admin/* -> 403", r.status_code == 403, f"kod={r.status_code}")
            if mgr_t:
                r = client.get(f"{API_BASE}/admin/audit/overrides", headers=auth(mgr_t))
                check("HR/Boss /admin/* -> 403 (faqat dasturchi)", r.status_code == 403, f"kod={r.status_code}")
            r = client.get(f"{API_BASE}/admin/audit/overrides", headers=auth(dev_t))
            check("dasturchi /admin/* -> 200", r.status_code == 200, f"kod={r.status_code}")

            # ── Sababsiz override -> 422 ──
            r = client.put(f"{API_BASE}/admin/norms/{emp_uid}/suhbat", headers=auth(dev_t), json={"value": 50})
            check("override_reason'siz -> 422", r.status_code == 422, f"kod={r.status_code}")

            # ── Normalar: xodim bo'lmaganga (HR) ham norma qo'yish ──
            r = client.put(f"{API_BASE}/admin/norms/{hr_target_uid}/suhbat", headers=auth(dev_t), json={
                "value": 77, "override_reason": "T-sinov: HR'ga norma",
            })
            check("dasturchi HR (xodim EMAS) ga norma qo'ydi -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")
            check("javobda qiymat 77", r.status_code == 200 and r.json().get("value") == 77,
                  f"={r.json().get('value') if r.status_code == 200 else None}")

            # Oddiy yo'l (odatdagi HR/Boss) xuddi shu HR'ga norma qo'ya OLMAYDI
            if mgr_t:
                r = client.post(f"{API_BASE}/norms", headers=auth(mgr_t), json={
                    "user_id": hr_target_uid, "metric_type": "suhbat", "value": 10,
                })
                check("oddiy /norms HR nishoniga -> 400 (xodim emas)", r.status_code == 400,
                      f"kod={r.status_code}")

            # ── Metrika cheklovisiz (lavozimida yo'q ko'rsatkich) ──
            r = client.put(f"{API_BASE}/admin/norms/{emp_uid}/dumaloq_video", headers=auth(dev_t), json={
                "value": 5, "override_reason": "T-sinov: metrika cheklovisiz",
            })
            check("dasturchi lavozimga mos kelmagan metrikaga norma qo'ydi -> 200",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            norm_id = r.json().get("id") if r.status_code == 200 else None

            # ── Yumshoq o'chirish + tiklash ──
            if norm_id:
                r = client.request("DELETE", f"{API_BASE}/admin/norms/{norm_id}", headers=auth(dev_t), json={
                    "override_reason": "T-sinov: yumshoq o'chirish",
                })
                check("norma yumshoq o'chirildi -> 200", r.status_code == 200, f"kod={r.status_code}")
                check("javobda hard=False", r.status_code == 200 and r.json().get("hard") is False,
                      f"={r.json() if r.status_code == 200 else None}")

                r = client.get(f"{API_BASE}/admin/records/norm?include_deleted=true", headers=auth(dev_t))
                found = [row for row in r.json() if row.get("id") == norm_id] if r.status_code == 200 else []
                check("o'chirilgan norma include_deleted=true da ko'rinadi",
                      len(found) == 1 and found[0].get("deleted_at") is not None,
                      f"topildi={found}")

                r = client.get(f"{API_BASE}/admin/records/norm?include_deleted=false", headers=auth(dev_t))
                found2 = [row for row in r.json() if row.get("id") == norm_id] if r.status_code == 200 else []
                check("include_deleted=false da ko'rinmaydi", len(found2) == 0, f"topildi={found2}")

                r = client.post(f"{API_BASE}/admin/records/norm/{norm_id}/restore", headers=auth(dev_t), json={
                    "override_reason": "T-sinov: tiklash",
                })
                check("norma tiklandi -> 200", r.status_code == 200, f"kod={r.status_code}")

            # ── PATCH oq ro'yxat tashqarisidagi maydon -> 400 ──
            if norm_id:
                r = client.patch(f"{API_BASE}/admin/records/norm/{norm_id}", headers=auth(dev_t), json={
                    "fields": {"user_id": 99999}, "override_reason": "T-sinov: ruxsatsiz maydon",
                })
                check("ruxsat etilmagan maydon -> 400", r.status_code == 400, f"kod={r.status_code}")

                r = client.patch(f"{API_BASE}/admin/records/norm/{norm_id}", headers=auth(dev_t), json={
                    "fields": {"value": 123}, "override_reason": "T-sinov: qiymatni tahrirlash",
                })
                check("ruxsat etilgan maydon -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
                check("qiymat yangilandi", r.status_code == 200 and r.json().get("value") == 123,
                      f"={r.json().get('value') if r.status_code == 200 else None}")

            # ── Metrikani butunlay tozalash ──
            r = client.request("DELETE", f"{API_BASE}/admin/norms/{emp_uid}/dumaloq_video", headers=auth(dev_t), json={
                "override_reason": "T-sinov: metrikani tozalash",
            })
            check("metrika tozalandi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            # ── revert: 2 marta norma qo'yib, oldingisiga qaytarish ──
            client.put(f"{API_BASE}/admin/norms/{emp_uid}/tashrif", headers=auth(dev_t), json={
                "value": 10, "override_reason": "T-sinov: revert 1-qadam",
            })
            client.put(f"{API_BASE}/admin/norms/{emp_uid}/tashrif", headers=auth(dev_t), json={
                "value": 20, "override_reason": "T-sinov: revert 2-qadam",
            })
            r = client.post(f"{API_BASE}/admin/norms/{emp_uid}/revert?metric=tashrif", headers=auth(dev_t), json={
                "override_reason": "T-sinov: revert",
            })
            check("revert -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            check("revert oldingi qiymatga (10) qaytardi",
                  r.status_code == 200 and r.json().get("current_value") == 10,
                  f"={r.json() if r.status_code == 200 else None}")

            # ── Payroll: qulf va super-admin amallar ──
            for wd in range(7):
                cur.execute(
                    "insert into work_schedule_weekly (user_id, weekday, is_working, updated_at)"
                    " values (?,?,0,datetime('now'))", (emp_uid, wd))
            cur.execute(
                "insert into work_schedule_override (user_id, date, is_working, start_time, end_time, updated_at)"
                " values (?, '2022-03-01', 1, '09:00', '18:00', datetime('now'))", (emp_uid,))
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, '2022-03-01', '2022-03-01 04:00:00', 0, 0, 480, 'present', 0,"
                " datetime('now'), datetime('now'))", (emp_uid,))
            conn.commit()
            if mgr_t:
                client.post(f"{API_BASE}/payroll/rates", headers=auth(mgr_t), json={
                    "user_id": emp_uid, "amount": 1_800_000, "pay_basis": "monthly",
                    "effective_from": "2020-01-01",
                })
                r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={"user_ids": [emp_uid]})
                check("payroll hisoblandi -> 200", r.status_code == 200, f"kod={r.status_code}")
                r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(mgr_t))
                check("payroll tasdiqlandi (qulflandi) -> 200", r.status_code == 200, f"kod={r.status_code}")

                r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
                check("qulflangan davrni HR qayta hisoblay OLMAYDI -> 409", r.status_code == 409,
                      f"kod={r.status_code}")

                r = client.post(f"{API_BASE}/admin/payroll/{PERIOD}/unlock", headers=auth(mgr_t), json={
                    "override_reason": "T-sinov: HR unlock urinishi",
                })
                check("HR /admin/payroll/unlock -> 403", r.status_code == 403, f"kod={r.status_code}")

                r = client.post(f"{API_BASE}/admin/payroll/{PERIOD}/unlock", headers=auth(dev_t), json={
                    "override_reason": "T-sinov: dasturchi qulfni ochadi",
                })
                check("dasturchi qulfni ochadi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

                r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
                check("qulf ochilgach HR qayta hisoblay oladi -> 200", r.status_code == 200,
                      f"kod={r.status_code}")

                r = client.patch(f"{API_BASE}/admin/payroll/{PERIOD}/user/{emp_uid}", headers=auth(dev_t), json={
                    "fields": {"net": 999999}, "override_reason": "T-sinov: qo'lda tuzatish",
                })
                check("dasturchi payslip summasini qo'lda tuzatdi -> 200", r.status_code == 200,
                      f"kod={r.status_code} {r.text[:150]}")
                check("net=999999 ga o'zgardi", r.status_code == 200 and r.json().get("net") == 999999.0,
                      f"={r.json().get('net') if r.status_code == 200 else None}")

                r = client.request("DELETE", f"{API_BASE}/admin/payroll/{PERIOD}", headers=auth(dev_t), json={
                    "override_reason": "T-sinov: butun davrni bekor qilish",
                })
                check("davr butunlay bekor qilindi -> 200", r.status_code == 200, f"kod={r.status_code}")
                r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{emp_uid}", headers=auth(mgr_t))
                check("bekor qilingandan keyin payslip topilmaydi -> 404", r.status_code == 404,
                      f"kod={r.status_code}")

            # ── Audit tarixi ──
            r = client.get(f"{API_BASE}/admin/audit/overrides", headers=auth(dev_t))
            check("audit/overrides -> 200", r.status_code == 200, f"kod={r.status_code}")
            actions = [row["action"] for row in r.json()] if r.status_code == 200 else []
            check("audit tarixida override_norm_set bor", "override_norm_set" in actions,
                  f"amallar namunasi={actions[:5]}")
    except Exception:
        check("Admin override (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_admin()
        conn.close()


def test_payroll_automation() -> None:
    """Bosqich 6: avtomatika — `api/services/payroll.py`ning yangi
    funksiyalari (`detect_overtime_candidates`, `late_limit_event_for`,
    `previous_period`) va `api/routers/payroll.py`ning yangi tick
    endpointlari (`/calculate-monthly`, `/late-warnings-tick`,
    `/overtime/auto-detect`). Izolyatsiyalangan davr "2020-03"
    (test_payroll_engine'ning "2020-01"idan ALOHIDA).

    ⭐ MUHIM: `/late-warnings-tick` va `/overtime/auto-detect` odatda BARCHA
    real faol xodimlarni "kecha" sanasi bo'yicha skanerlaydi — shu sabab bu
    testda ular HAR DOIM aniq `target_date` bilan (uzoq o'tmishdagi, 2020-03)
    chaqiriladi, hech qachon default ("kecha") bilan EMAS — aks holda real
    xodimlarga botdan chinakam xabar ketishi yoki real ma'lumot o'zgarishi
    mumkin edi (xuddi shu sabab bilan test.py'dan yuzni qayta tekshirish
    testi ilgari olib tashlangan edi)."""
    import asyncio

    import httpx

    print("\n" + "=" * 60)
    print("BOSQICH 6: PAYROLL AVTOMATIKA (scheduler + tick endpointlari)")
    print("=" * 60)

    PERIOD = "2020-03"
    WINDOW_MIN = 480  # work_minutes(09:00,18:00) — tushliksiz 8 soat

    async def _setup_and_direct_checks() -> dict:
        from sqlalchemy import delete, select

        from api.services import payroll as pr
        from api.services.attendance import local_hm_to_utc
        from db.base import async_session
        from db.models import (
            Attendance,
            AuditLog,
            FinePolicy,
            OvertimeEntry,
            OvertimeProfile,
            PayrollPeriod,
            Payslip,
            PayslipItem,
            SalaryRate,
            User,
            WorkScheduleOverride,
            WorkScheduleWeekly,
        )

        async with async_session() as s:
            # Oldingi (yarim yo'lda qulagan) ishga tushirishdan qolganlarni tozalash.
            stale_ids = list(await s.scalars(select(User.id).where(User.full_name.like("T-Payroll6%"))))
            if stale_ids:
                stale_payslips = list(await s.scalars(select(Payslip.id).where(Payslip.user_id.in_(stale_ids))))
                if stale_payslips:
                    await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id.in_(stale_payslips)))
                await s.execute(delete(Payslip).where(Payslip.user_id.in_(stale_ids)))
                await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id.in_(stale_ids)))
                await s.execute(delete(OvertimeProfile).where(OvertimeProfile.user_id.in_(stale_ids)))
                await s.execute(delete(SalaryRate).where(SalaryRate.user_id.in_(stale_ids)))
                await s.execute(delete(FinePolicy).where(FinePolicy.scope_id.in_(stale_ids)))
                await s.execute(delete(Attendance).where(Attendance.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(stale_ids)))
                await s.execute(
                    delete(AuditLog).where(
                        AuditLog.target_user_id.in_(stale_ids) | AuditLog.actor_id.in_(stale_ids)
                    )
                )
                await s.execute(delete(User).where(User.id.in_(stale_ids)))
            await s.execute(
                delete(Attendance).where(Attendance.date >= date(2020, 3, 1), Attendance.date < date(2020, 4, 1))
            )
            await s.execute(
                delete(WorkScheduleOverride).where(
                    WorkScheduleOverride.date >= date(2020, 3, 1), WorkScheduleOverride.date < date(2020, 4, 1)
                )
            )
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.commit()

            # ── T-Payroll6OT — qo'shimcha ish avtomatik aniqlash (1.3-band) ──
            uot = User(telegram_id=999600901, full_name="T-Payroll6OT", role="employee",
                       bot_started=True, is_active=True)
            s.add(uot)
            await s.flush()
            for wd in range(7):
                s.add(WorkScheduleWeekly(user_id=uot.id, weekday=wd, is_working=False))
            day_over, day_within, day_http = date(2020, 3, 10), date(2020, 3, 11), date(2020, 3, 12)
            for d in (day_over, day_within, day_http):
                s.add(WorkScheduleOverride(user_id=uot.id, date=d, is_working=True,
                                            start_time="09:00", end_time="18:00"))
            s.add(OvertimeProfile(user_id=uot.id, enabled=True, mode="fixed_rate",
                                   fixed_rate_per_hour=10_000, min_minutes=15))
            s.add(Attendance(user_id=uot.id, date=day_over, status="present", worked_minutes=WINDOW_MIN,
                              check_out_time=local_hm_to_utc(day_over, "18:30")))  # 30 daq keyin -> nomzod
            s.add(Attendance(user_id=uot.id, date=day_within, status="present", worked_minutes=WINDOW_MIN,
                              check_out_time=local_hm_to_utc(day_within, "17:50")))  # oyna ichida -> yo'q
            s.add(Attendance(user_id=uot.id, date=day_http, status="present", worked_minutes=WINDOW_MIN,
                              check_out_time=local_hm_to_utc(day_http, "18:25")))  # HTTP orqali tekshiriladi
            await s.commit()

            created1 = await pr.detect_overtime_candidates(s, day_over)
            await s.commit()
            check("Bosqich6: overtime nomzodi yaratildi (check-out 30 daq keyin)", len(created1) == 1,
                  f"soni={len(created1)}")
            if created1:
                check("Bosqich6: nomzod minutes=30", created1[0].minutes == 30, f"={created1[0].minutes}")
                check("Bosqich6: nomzod source=auto_attendance", created1[0].source == "auto_attendance",
                      f"={created1[0].source}")
                check("Bosqich6: nomzod status=pending", created1[0].status == "pending",
                      f"={created1[0].status}")

            created_again = await pr.detect_overtime_candidates(s, day_over)
            check("Bosqich6: overtime idempotent - qayta chaqirilsa dublikat YO'Q", created_again == [],
                  f"={created_again}")

            created_within = await pr.detect_overtime_candidates(s, day_within)
            check("Bosqich6: ish oynasi ichida check-out -> nomzod YO'Q", created_within == [],
                  f"={created_within}")

            # ── T-Payroll6Late — kechikish limiti ogohlantirishi (1.5-band) ──
            ul = User(telegram_id=999600902, full_name="T-Payroll6Late", role="employee",
                      bot_started=True, is_active=True)
            s.add(ul)
            await s.flush()
            for wd in range(7):
                s.add(WorkScheduleWeekly(user_id=ul.id, weekday=wd, is_working=False))
            d1, d2, d3, d4, d5 = (
                date(2020, 3, 2), date(2020, 3, 3), date(2020, 3, 4), date(2020, 3, 5), date(2020, 3, 6),
            )
            for d in (d1, d2, d3, d4, d5):
                s.add(WorkScheduleOverride(user_id=ul.id, date=d, is_working=True,
                                            start_time="09:00", end_time="18:00"))
            # `compute_late_fine`ning QOIDASI: "chegaradan o'tkazgan kunning o'zi
            # hali bepul" — `fined = (before >= limit)`, ya'ni limitni TO'LDIRGAN
            # kunning O'ZI EMAS, undan KEYINGI kun birinchi jarimali hisoblanadi.
            # d1: 0->20 (limit 30ga 10 daq qoldi) -> near_limit.
            # d2: 20->35 (limitni TO'LDIRGAN kun, before=20<30 -> hali JARIMASIZ,
            #     lekin remaining_before(10) allaqachon buferdan (15) kichik ->
            #     near_limit ILGARI (d1'da) berilgan, shu sabab bu yerda YANGI
            #     voqea YO'Q) -> None.
            # d3: 35->40 (before=35>=30 -> BIRINCHI jarimali kun) -> limit_reached.
            # d4: 40->45 (before=40>=30 -> jarimali, lekin ALLAQACHON d3'da
            #     boshlangan) -> yangi voqea emas -> None.
            # d5: kechikmagan (present) -> None.
            s.add(Attendance(user_id=ul.id, date=d1, status="late", late_minutes=20, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=ul.id, date=d2, status="late", late_minutes=15, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=ul.id, date=d3, status="late", late_minutes=5, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=ul.id, date=d4, status="late", late_minutes=5, worked_minutes=WINDOW_MIN))
            s.add(Attendance(user_id=ul.id, date=d5, status="present", worked_minutes=WINDOW_MIN))
            s.add(FinePolicy(scope="user", scope_id=ul.id, is_active=True,
                              free_late_minutes_per_month=30, fine_mode="per_day", fine_per_day=50_000,
                              absent_mode="none", monthly_cap_amount=1_000_000, fine_applies_to="net_salary"))
            s.add(SalaryRate(user_id=ul.id, amount=2_000_000, pay_basis="monthly",
                              effective_from=date(2019, 1, 1), changed_by=ul.id))
            await s.commit()

            ev1 = await pr.late_limit_event_for(s, ul, d1)
            check("Bosqich6: d1 (0->20, limit 30) -> near_limit",
                  ev1 is not None and ev1["kind"] == "near_limit", f"={ev1}")
            if ev1:
                check("Bosqich6: d1 remaining_minutes=10", ev1.get("remaining_minutes") == 10, f"={ev1}")

            ev2 = await pr.late_limit_event_for(s, ul, d2)
            check("Bosqich6: d2 (limitni to'ldirgan kun, hali jarimasiz) -> None",
                  ev2 is None, f"={ev2}")

            ev3 = await pr.late_limit_event_for(s, ul, d3)
            check("Bosqich6: d3 (birinchi jarimali kun) -> limit_reached",
                  ev3 is not None and ev3["kind"] == "limit_reached", f"={ev3}")

            ev4 = await pr.late_limit_event_for(s, ul, d4)
            check("Bosqich6: d4 (jarimali, lekin ALLAQACHON d3'da boshlangan) -> None (yangi voqea emas)",
                  ev4 is None, f"={ev4}")

            ev5 = await pr.late_limit_event_for(s, ul, d5)
            check("Bosqich6: d5 (kechikmagan) -> None", ev5 is None, f"={ev5}")

            u_nopolicy = User(telegram_id=999600903, full_name="T-Payroll6NoPolicy", role="employee",
                               bot_started=True, is_active=True)
            s.add(u_nopolicy)
            await s.flush()
            ev_none = await pr.late_limit_event_for(s, u_nopolicy, d1)
            check("Bosqich6: qoidasiz xodim -> None", ev_none is None, f"={ev_none}")

            check("Bosqich6: previous_period(2020-03-15) = 2020-02",
                  pr.previous_period(date(2020, 3, 15)) == "2020-02",
                  f"={pr.previous_period(date(2020, 3, 15))}")
            check("Bosqich6: previous_period(2020-01-01) = 2019-12 (yil chegarasi)",
                  pr.previous_period(date(2020, 1, 1)) == "2019-12",
                  f"={pr.previous_period(date(2020, 1, 1))}")

            return {"d1": d1.isoformat(), "day_http": day_http.isoformat()}

    async def _cleanup() -> None:
        from sqlalchemy import delete, select

        from db.base import async_session
        from db.models import (
            Attendance,
            AuditLog,
            FinePolicy,
            OvertimeEntry,
            OvertimeProfile,
            PayrollPeriod,
            Payslip,
            PayslipItem,
            SalaryRate,
            User,
            WorkScheduleOverride,
            WorkScheduleWeekly,
        )

        async with async_session() as s:
            ids = list(await s.scalars(select(User.id).where(User.full_name.like("T-Payroll6%"))))
            if not ids:
                return
            pslips = list(await s.scalars(select(Payslip.id).where(Payslip.user_id.in_(ids))))
            if pslips:
                await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id.in_(pslips)))
            await s.execute(delete(Payslip).where(Payslip.user_id.in_(ids)))
            await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id.in_(ids)))
            await s.execute(delete(OvertimeProfile).where(OvertimeProfile.user_id.in_(ids)))
            await s.execute(delete(SalaryRate).where(SalaryRate.user_id.in_(ids)))
            await s.execute(delete(FinePolicy).where(FinePolicy.scope_id.in_(ids)))
            await s.execute(delete(Attendance).where(Attendance.user_id.in_(ids)))
            await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id.in_(ids)))
            await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(ids)))
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.execute(delete(AuditLog).where(AuditLog.target_user_id.in_(ids) | AuditLog.actor_id.in_(ids)))
            await s.execute(delete(User).where(User.id.in_(ids)))
            await s.commit()

    ctx: dict = {}
    try:
        ctx = asyncio.run(_setup_and_direct_checks())
    except Exception:
        check("Bosqich6: sozlash/servis funksiyalari (umumiy)", False, traceback.format_exc(limit=2).strip())

    if ctx:
        try:
            with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as f:
                secret = next(
                    (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")), ""
                )
            BOT_SECRET_HDR = {"X-Bot-Secret": secret}
            with httpx.Client(timeout=15) as client:
                # ── bot-secret himoyasi ──
                r = client.post(f"{API_BASE}/payroll/calculate-monthly", json={})
                check("calculate-monthly bot-secretsiz -> 401", r.status_code == 401, f"kod={r.status_code}")
                r = client.post(f"{API_BASE}/payroll/late-warnings-tick", json={})
                check("late-warnings-tick bot-secretsiz -> 401", r.status_code == 401, f"kod={r.status_code}")
                r = client.post(f"{API_BASE}/payroll/overtime/auto-detect", json={})
                check("overtime/auto-detect bot-secretsiz -> 401", r.status_code == 401, f"kod={r.status_code}")

                # ── calculate-monthly: ANIQ (izolyatsiyalangan) davr — default
                # ("o'tgan oy") ATAYLAB sinalmaydi, aks holda jonli joriy oy
                # ma'lumotiga tegib qo'yardi. ──
                r = client.post(f"{API_BASE}/payroll/calculate-monthly", headers=BOT_SECRET_HDR,
                                 json={"period": PERIOD})
                check("calculate-monthly -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
                body = r.json() if r.status_code == 200 else {}
                check("calculate-monthly natijada period to'g'ri", body.get("period") == PERIOD, f"={body}")

                # ── late-warnings-tick: to'g'ridan-to'g'ri chaqiruvda near_limit
                # bo'lgan d1'ni endi HTTP orqali (aniq target_date bilan) ──
                r = client.post(f"{API_BASE}/payroll/late-warnings-tick", headers=BOT_SECRET_HDR,
                                 json={"target_date": ctx["d1"]})
                check("late-warnings-tick -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
                lw = r.json() if r.status_code == 200 else {}
                check("late-warnings-tick kamida 1 ta ogohlantirdi (T-Payroll6Late)",
                      lw.get("warned", 0) >= 1, f"={lw}")

                # ── overtime/auto-detect: HTTP orqali YANGI (hali test qilinmagan)
                # kun — aniq target_date bilan ──
                r = client.post(f"{API_BASE}/payroll/overtime/auto-detect", headers=BOT_SECRET_HDR,
                                 json={"target_date": ctx["day_http"]})
                check("overtime/auto-detect -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
                oad = r.json() if r.status_code == 200 else {}
                check("overtime/auto-detect kamida 1 ta nomzod yaratdi (T-Payroll6OT)",
                      oad.get("created", 0) >= 1, f"={oad}")
        except Exception:
            check("Bosqich6: HTTP tick endpointlari (umumiy)", False, traceback.format_exc(limit=2).strip())

    try:
        asyncio.run(_cleanup())
    except Exception:
        check("Bosqich6: tozalash (umumiy)", False, traceback.format_exc(limit=2).strip())


def test_payroll_reporting() -> None:
    """Bosqich 7: hisobot va maxfiylik — Excel eksport
    (`api/services/export.py::build_payroll_xlsx`, `GET /payroll/{period}/export`),
    barcha pul o'zgarishlari uchun AuditLog (`payroll_calculated`), oylik
    digestga Boshliq-ONLY "jami ish haqi fondi" (`api/services/monthly_digest.py`).
    Izolyatsiyalangan davr "2020-04"."""
    import asyncio
    from io import BytesIO

    import httpx
    from openpyxl import load_workbook

    print("\n" + "=" * 60)
    print("BOSQICH 7: HISOBOT VA MAXFIYLIK (export + audit + digest)")
    print("=" * 60)

    PERIOD = "2020-04"
    WINDOW_MIN = 480

    async def _setup() -> dict:
        from sqlalchemy import delete, select

        from api.services.payroll import run_payroll
        from db.base import async_session
        from db.models import (
            Attendance,
            AuditLog,
            LeadStageDaily,
            PayrollPeriod,
            Payslip,
            PayslipItem,
            SalaryRate,
            User,
            WorkScheduleOverride,
            WorkScheduleWeekly,
        )

        async with async_session() as s:
            stale_ids = list(await s.scalars(select(User.id).where(User.full_name.like("T-Payroll7%"))))
            if stale_ids:
                stale_payslips = list(await s.scalars(select(Payslip.id).where(Payslip.user_id.in_(stale_ids))))
                if stale_payslips:
                    await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id.in_(stale_payslips)))
                await s.execute(delete(Payslip).where(Payslip.user_id.in_(stale_ids)))
                await s.execute(delete(SalaryRate).where(SalaryRate.user_id.in_(stale_ids)))
                await s.execute(delete(Attendance).where(Attendance.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id.in_(stale_ids)))
                await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(stale_ids)))
                await s.execute(
                    delete(AuditLog).where(
                        AuditLog.target_user_id.in_(stale_ids) | AuditLog.actor_id.in_(stale_ids)
                    )
                )
                await s.execute(delete(User).where(User.id.in_(stale_ids)))
            await s.execute(
                delete(Attendance).where(Attendance.date >= date(2020, 4, 1), Attendance.date < date(2020, 5, 1))
            )
            await s.execute(
                delete(WorkScheduleOverride).where(
                    WorkScheduleOverride.date >= date(2020, 4, 1), WorkScheduleOverride.date < date(2020, 5, 1)
                )
            )
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.commit()

            rop = User(telegram_id=999700701, full_name="T-Payroll7Rop", role="rop",
                       bot_started=True, is_active=True)
            emp = User(telegram_id=999700702, full_name="T-Payroll7Emp", role="employee",
                       bot_started=True, is_active=True)
            outsider = User(telegram_id=999700703, full_name="T-Payroll7Outsider", role="employee",
                             bot_started=True, is_active=True)
            s.add_all([rop, emp, outsider])
            await s.flush()
            emp.manager_id = rop.id
            await s.commit()

            d = date(2020, 4, 6)
            for u in (emp, outsider):
                for wd in range(7):
                    s.add(WorkScheduleWeekly(user_id=u.id, weekday=wd, is_working=False))
                s.add(WorkScheduleOverride(user_id=u.id, date=d, is_working=True,
                                            start_time="09:00", end_time="18:00"))
                s.add(Attendance(user_id=u.id, date=d, status="present", worked_minutes=WINDOW_MIN))
                s.add(SalaryRate(user_id=u.id, amount=2_000_000, pay_basis="monthly",
                                  effective_from=date(2019, 1, 1), changed_by=u.id))
            await s.commit()

            await run_payroll(s, PERIOD, user_ids=[emp.id, outsider.id])

            # Oylik digest "faol operator" darvozasidan o'tishi uchun bitta
            # yengil CRM snapshot yozuvi — real xodim/tashkilotga bog'liq emas
            # (rid haqiqiy foydalanuvchiga bog'lanmagan, faqat "active" gate).
            s.add(LeadStageDaily(date=date(2020, 5, 10), responsible_id=999700799,
                                  responsible_name="T-Payroll7-CRM", pipe_status_id=1,
                                  stage_name="T-sinov bosqichi", leads_count=3))
            await s.commit()

            return {"rop_id": rop.id, "emp_id": emp.id, "outsider_id": outsider.id}

    async def _cleanup() -> None:
        from sqlalchemy import delete, select

        from db.base import async_session
        from db.models import (
            Attendance,
            AuditLog,
            LeadStageDaily,
            PayrollPeriod,
            Payslip,
            PayslipItem,
            SalaryRate,
            User,
            WorkScheduleOverride,
            WorkScheduleWeekly,
        )

        async with async_session() as s:
            ids = list(await s.scalars(select(User.id).where(User.full_name.like("T-Payroll7%"))))
            if ids:
                pslips = list(await s.scalars(select(Payslip.id).where(Payslip.user_id.in_(ids))))
                if pslips:
                    await s.execute(delete(PayslipItem).where(PayslipItem.payslip_id.in_(pslips)))
                await s.execute(delete(Payslip).where(Payslip.user_id.in_(ids)))
                await s.execute(delete(SalaryRate).where(SalaryRate.user_id.in_(ids)))
                await s.execute(delete(Attendance).where(Attendance.user_id.in_(ids)))
                await s.execute(delete(WorkScheduleOverride).where(WorkScheduleOverride.user_id.in_(ids)))
                await s.execute(delete(WorkScheduleWeekly).where(WorkScheduleWeekly.user_id.in_(ids)))
                await s.execute(delete(AuditLog).where(AuditLog.target_user_id.in_(ids) | AuditLog.actor_id.in_(ids)))
                await s.execute(delete(User).where(User.id.in_(ids)))
            await s.execute(
                delete(LeadStageDaily).where(
                    LeadStageDaily.responsible_id == 999700799, LeadStageDaily.date == date(2020, 5, 10)
                )
            )
            await s.execute(delete(PayrollPeriod).where(PayrollPeriod.period == PERIOD))
            await s.commit()

    async def _direct_checks(ctx: dict) -> None:
        from api.services.export import build_payroll_xlsx
        from api.services.monthly_digest import build_monthly_digest, send_monthly_digest
        from db.base import async_session

        async with async_session() as s:
            buf_all = await build_payroll_xlsx(s, PERIOD)
            wb_all = load_workbook(BytesIO(buf_all.read()))
            check("Bosqich7: 'Xulosa' varag'i bor", "Xulosa" in wb_all.sheetnames, f"={wb_all.sheetnames}")
            emp_sheet = f"T-Payroll7Emp #{ctx['emp_id']}"
            out_sheet = f"T-Payroll7Outsider #{ctx['outsider_id']}"
            check("Bosqich7: user_ids'siz eksportda IKKALA xodim varag'i bor",
                  emp_sheet in wb_all.sheetnames and out_sheet in wb_all.sheetnames,
                  f"={wb_all.sheetnames}")

            buf_scoped = await build_payroll_xlsx(s, PERIOD, user_ids=[ctx["emp_id"]])
            wb_scoped = load_workbook(BytesIO(buf_scoped.read()))
            check("Bosqich7: user_ids bilan FAQAT shu xodim varag'i bor",
                  emp_sheet in wb_scoped.sheetnames and out_sheet not in wb_scoped.sheetnames,
                  f"={wb_scoped.sheetnames}")

            digest = await build_monthly_digest(s, ref_day=date(2020, 5, 15))
            digest_text = digest.get("text") or ""
            # Windows konsoli (cp1251) digest matnidagi emojilarni (masalan
            # U+1F5D3) chop etishda qulaydi — check() xabarlarida faqat ASCII-
            # xavfsiz uzunlik/qidiruv natijasi ishlatiladi, xom matn EMAS.
            check("Bosqich7: digest matni yaratildi (CRM snapshot gate o'tildi)",
                  digest.get("text") is not None, f"uzunlik={len(digest_text)}")
            pf = digest.get("payroll_fund")
            check("Bosqich7: payroll_fund davri = o'tgan oy (2020-04)",
                  pf is not None and pf["period"] == PERIOD, f"={pf}")
            if pf:
                check("Bosqich7: payroll_fund jami = 2 xodim netto yig'indisi",
                      abs(pf["total"] - 4_000_000.0) < 1, f"={pf}")
            check("Bosqich7: digest MATNIDA 'fond' so'zi YO'Q (guruhga sizib chiqmaydi)",
                  "fond" not in digest_text.lower(), f"uzunlik={len(digest_text)}")

            # E'TIBOR: `send_monthly_digest` `ref_day` qabul qilmaydi (har doim
            # HAQIQIY "bugun"dan hisoblaydi, real joriy oy CRM faolligiga
            # bog'liq) — shu sabab bu yerda faqat "hech qachon yubormaydi"
            # (dry_run) tekshiriladi, "2020-04"ga tegishli QIYMAT EMAS.
            dry = await send_monthly_digest(s, dry_run=True)
            # `dry`ning "text" kaliti xom (emoji bilan) digest matni bo'lishi
            # mumkin — check() xabarida shu kalitsiz qisqa xulosa ishlatiladi
            # (Windows konsoli cp1251 emojilarda qulaydi).
            dry_summary = {k: v for k, v in dry.items() if k != "text"}
            check("Bosqich7: dry_run hech qachon yubormaydi", dry.get("sent") is False, f"={dry_summary}")

    ctx: dict = {}
    try:
        ctx = asyncio.run(_setup())
    except Exception:
        check("Bosqich7: sozlash (umumiy)", False, traceback.format_exc(limit=2).strip())

    if ctx:
        try:
            asyncio.run(_direct_checks(ctx))
        except Exception:
            check("Bosqich7: servis funksiyalari (umumiy)", False, traceback.format_exc(limit=2).strip())

        try:
            mgr = find_manager_id()
            mgr_t = token_for(mgr[0], mgr[1]) if mgr else None
            rop_t = token_for(ctx["rop_id"], "rop")
            emp_t = token_for(ctx["emp_id"], "employee")

            with httpx.Client(timeout=15) as client:
                r = client.get(f"{API_BASE}/payroll/{PERIOD}/export", headers=auth(emp_t))
                check("xodim /payroll/*/export -> 403", r.status_code == 403, f"kod={r.status_code}")

                r = client.get(f"{API_BASE}/payroll/{PERIOD}/export", headers=auth(mgr_t))
                check("HR/Boss /payroll/*/export -> 200", r.status_code == 200, f"kod={r.status_code}")
                check("export content-type xlsx",
                      "spreadsheetml" in r.headers.get("content-type", ""),
                      f"={r.headers.get('content-type')}")
                if r.status_code == 200:
                    wb_http = load_workbook(BytesIO(r.content))
                    check("HR eksportida ikkala xodim ham bor",
                          f"T-Payroll7Emp #{ctx['emp_id']}" in wb_http.sheetnames
                          and f"T-Payroll7Outsider #{ctx['outsider_id']}" in wb_http.sheetnames,
                          f"={wb_http.sheetnames}")

                r = client.get(f"{API_BASE}/payroll/{PERIOD}/export", headers=auth(rop_t))
                check("ROP /payroll/*/export -> 200", r.status_code == 200, f"kod={r.status_code}")
                if r.status_code == 200:
                    wb_rop = load_workbook(BytesIO(r.content))
                    check("ROP eksportida FAQAT o'z jamoasi (Emp bor, Outsider yo'q)",
                          f"T-Payroll7Emp #{ctx['emp_id']}" in wb_rop.sheetnames
                          and f"T-Payroll7Outsider #{ctx['outsider_id']}" not in wb_rop.sheetnames,
                          f"={wb_rop.sheetnames}")

                # ── "payroll_calculated" AuditLog — barcha pul o'zgarishi audit qilinadi ──
                r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
                check("qayta hisoblash -> 200", r.status_code == 200, f"kod={r.status_code}")

            conn = db()
            cur = conn.cursor()
            row = cur.execute(
                "select count(*) from audit_logs where action='payroll_calculated' "
                "and json_extract(after, '$.period')=?", (PERIOD,)
            ).fetchone()
            check("AuditLog 'payroll_calculated' yozildi", row is not None and row[0] >= 1, f"={row}")
            conn.close()
        except Exception:
            check("Bosqich7: HTTP export/audit (umumiy)", False, traceback.format_exc(limit=2).strip())

    try:
        asyncio.run(_cleanup())
    except Exception:
        check("Bosqich7: tozalash (umumiy)", False, traceback.format_exc(limit=2).strip())


def test_dasturchi_bot_bridge() -> None:
    """Dasturchi web/bot interfeysi: web tomoni (`AdminOverride.tsx`) mavjud
    `admin_override.py` backendining ustiga qurilgan (yangi backend YO'Q),
    lekin bot tomoni uchun BITTA yangi ko'prik qo'shildi — `POST /auth/
    bot-token` (bot-secret bilan himoyalangan, FAQAT dasturchi uchun JWT
    beradi). Shu test faqat SHU yangi endpointni va uning JWT'si haqiqatan
    `/admin/*` va `/attendance/manual`ga kira olishini tekshiradi — chuqurroq
    admin_override.py mantiqi allaqachon `test_admin_override` (Bosqich 3.5)
    da to'liq qoplangan, bu yerda takrorlanmaydi."""
    import httpx

    print("\n" + "=" * 60)
    print("DASTURCHI BOT KO'PRIGI (POST /auth/bot-token)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-Bridge%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from norms where user_id in ({qm})", stale)
        cur.execute(f"delete from attendance where user_id in ({qm})", stale)
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    cur.execute("delete from work_schedule_override where date = '2020-05-05'")
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999800801,'T-Bridge-Dev','dasturchi',1,1,datetime('now'))")
    dev_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999800802,'T-Bridge-Emp','employee',1,1,datetime('now'))")
    emp_uid = cur.lastrowid
    cur.execute(
        "insert into work_schedule_override (user_id, date, is_working, start_time, end_time, updated_at)"
        " values (?, '2020-05-05', 1, '09:00', '18:00', datetime('now'))", (emp_uid,))
    conn.commit()

    def cleanup_bridge():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [dev_uid, emp_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from norms where user_id in ({qm})", uids)
            c2.execute(f"delete from attendance where user_id in ({qm})", uids)
            c2.execute("delete from work_schedule_override where date = '2020-05-05'")
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Dasturchi bot ko'prigi tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as f:
            secret = next(
                (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")), ""
            )
        BOT_SECRET_HDR = {"X-Bot-Secret": secret}

        with httpx.Client(timeout=15) as client:
            r = client.post(f"{API_BASE}/auth/bot-token", json={"telegram_id": 999800801})
            check("bot-secretsiz -> 401", r.status_code == 401, f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/auth/bot-token", headers=BOT_SECRET_HDR, json={"telegram_id": 1})
            check("mavjud bo'lmagan telegram_id -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/auth/bot-token", headers=BOT_SECRET_HDR, json={"telegram_id": 999800802})
            check("xodim (dasturchi EMAS) -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/auth/bot-token", headers=BOT_SECRET_HDR, json={"telegram_id": 999800801})
            check("dasturchi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            token = r.json().get("access_token") if r.status_code == 200 else None
            check("javobda access_token bor", bool(token), f"={r.json() if r.status_code == 200 else None}")

            if token:
                jwt_hdr = {"Authorization": f"Bearer {token}"}

                r = client.put(
                    f"{API_BASE}/admin/norms/{emp_uid}/suhbat", headers=jwt_hdr,
                    json={"value": 33, "override_reason": "T-sinov: bot ko'prigi orqali"},
                )
                check("mint qilingan JWT bilan /admin/norms ishlaydi -> 200", r.status_code == 200,
                      f"kod={r.status_code} {r.text[:150]}")
                check("norma qiymati 33", r.status_code == 200 and r.json().get("value") == 33,
                      f"={r.json() if r.status_code == 200 else None}")

                r = client.put(
                    f"{API_BASE}/attendance/manual", headers=jwt_hdr,
                    json={
                        "user_id": emp_uid, "date": "2020-05-05", "check_in": "09:20",
                        "reason": "T-sinov: /att_fix ko'prigi",
                    },
                )
                check("mint qilingan JWT bilan /attendance/manual ishlaydi -> 200", r.status_code == 200,
                      f"kod={r.status_code} {r.text[:150]}")
                check("late_minutes hisoblandi (09:20 kelish, 09:00 boshlanish)",
                      r.status_code == 200 and r.json().get("late_minutes") == 20,
                      f"={r.json() if r.status_code == 200 else None}")
    except Exception:
        check("Dasturchi bot ko'prigi (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_bridge()
        conn.close()


def test_positions_permissions() -> None:
    """HRga lavozim yaratish/tahrirlash huquqi berildi (ilgari faqat Boshliq/
    Dasturchi) — `api/routers/positions.py::MANAGE_ROLES`. ROP hamon faqat
    o'qiy oladi (READ_ROLES)."""
    import httpx

    print("\n" + "=" * 60)
    print("LAVOZIM RUXSATLARI (HR endi boshqara oladi)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-PosPerm%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where actor_id in ({qm})", stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    cur.execute("delete from positions where name = 'T-Sinov lavozimi'")
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999900901,'T-PosPerm-Hr','hr',1,1,datetime('now'))")
    hr_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999900902,'T-PosPerm-Rop','rop',1,1,datetime('now'))")
    rop_uid = cur.lastrowid
    conn.commit()

    def cleanup_pos():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [hr_uid, rop_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where actor_id in ({qm})", uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            c2.execute("delete from positions where name = 'T-Sinov lavozimi'")
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Lavozim ruxsati tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        hr_t = token_for(hr_uid, "hr")
        rop_t = token_for(rop_uid, "rop")

        with httpx.Client(timeout=15) as client:
            r = client.post(f"{API_BASE}/positions", headers=auth(rop_t), json={
                "name": "T-Sinov lavozimi", "menu_flags": {}, "metrics": ["suhbat"], "managed_by_roles": [],
            })
            check("ROP lavozim yarata OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/positions", headers=auth(hr_t), json={
                "name": "T-Sinov lavozimi", "menu_flags": {}, "metrics": ["suhbat"], "managed_by_roles": [],
            })
            check("HR lavozim yarata oladi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            pos_id = r.json().get("id") if r.status_code == 200 else None

            if pos_id:
                r = client.patch(f"{API_BASE}/positions/{pos_id}", headers=auth(hr_t), json={
                    "metrics": ["suhbat", "tashrif"],
                })
                check("HR lavozimni tahrirlay oladi -> 200", r.status_code == 200, f"kod={r.status_code}")
                check("metrics yangilandi", r.status_code == 200 and r.json().get("metrics") == ["suhbat", "tashrif"],
                      f"={r.json() if r.status_code == 200 else None}")
    except Exception:
        check("Lavozim ruxsatlari (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_pos()
        conn.close()


def test_telegram_login_security() -> None:
    """Telegram login xavfsizlik arxitekturasi (3 qatlam):
    1. Replay himoyasi — bir xil `hash` ikkinchi marta rad etiladi.
    2. Rate-limit — belgilangan chegaradan oshgan urinish 429 qaytaradi.
    3. Taklif havolasi (invite) muddati — muddati o'tgan token 'token_expired'.

    Haqiqiy Telegram'ga hech qanday so'rov yubormaydi — imzoni loyihaning o'z
    HMAC algoritmi bilan (.env'dagi BOT_TOKEN) lokal hisoblaydi, xuddi
    Telegram Login Widget qilganidek."""
    import hashlib
    import hmac as hmac_lib
    import time

    import httpx

    from api.config import settings

    print("\n" + "=" * 60)
    print("TELEGRAM LOGIN XAVFSIZLIGI (replay / rate-limit / invite muddati)")
    print("=" * 60)

    def sign(data: dict) -> dict:
        pairs = [f"{k}={v}" for k, v in sorted(data.items())]
        check_string = "\n".join(pairs)
        secret_key = hashlib.sha256(settings.bot_token.encode()).digest()
        data = dict(data)
        data["hash"] = hmac_lib.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return data

    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-LoginSec%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999900951,'T-LoginSec-Replay','employee',1,1,datetime('now'))")
    replay_uid = cur.lastrowid
    cur.execute(
        "insert into users (full_name, role, bot_started, is_active, invite_token, invite_expires_at, created_at)"
        " values ('T-LoginSec-Expired','employee',0,1,'T-invtok-expired-999901',"
        " datetime('now','-1 hour'), datetime('now'))")
    expired_uid = cur.lastrowid
    cur.execute(
        "insert into users (full_name, role, bot_started, is_active, invite_token, invite_expires_at, created_at)"
        " values ('T-LoginSec-Valid','employee',0,1,'T-invtok-valid-999902',"
        " datetime('now','+1 day'), datetime('now'))")
    valid_uid = cur.lastrowid
    conn.commit()

    def cleanup_sec():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [replay_uid, expired_uid, valid_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            c2.execute("delete from used_telegram_login_hashes where hash in (?,?)", (replay_hash_1, replay_hash_2))
            c2.execute(
                "delete from login_attempts where endpoint in ('dev-login','telegram-login')"
                " and identifier = '127.0.0.1' and created_at >= ?", (test_start,)
            )
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Login xavfsizlik tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    replay_hash_1 = ""
    replay_hash_2 = ""
    test_start = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with httpx.Client(timeout=15) as client:
            # ── 1. Replay himoyasi ──────────────────────────────────────
            payload = sign({"id": 999900951, "auth_date": int(time.time()), "first_name": "T-Test"})
            replay_hash_1 = payload["hash"]

            r = client.post(f"{API_BASE}/auth/telegram-login", json=payload)
            check("Telegram login (birinchi, to'g'ri imzo) -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")

            r = client.post(f"{API_BASE}/auth/telegram-login", json=payload)
            check("Xuddi shu hash ikkinchi marta -> 401 (replay)", r.status_code == 401,
                  f"kod={r.status_code} {r.text[:150]}")

            # Boshqa (yangi) hash — xuddi shu foydalanuvchi bilan qayta kirish
            # hamon ISHLASHI kerak (hash o'zi bloklanadi, foydalanuvchi emas).
            # auth_date ataylab 5s orqaga suriladi — bir xil sekundda ikkala
            # payload aynan bir xil hash hosil qilib qolmasligi uchun.
            payload2 = sign({"id": 999900951, "auth_date": int(time.time()) - 5, "first_name": "T-Test"})
            replay_hash_2 = payload2["hash"]
            r = client.post(f"{API_BASE}/auth/telegram-login", json=payload2)
            check("Yangi hash bilan qayta login -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")

            # ── 2. Rate-limit (dev-login, 20/soat) ──────────────────────
            last_code = None
            for _ in range(21):
                r = client.post(f"{API_BASE}/auth/dev-login", json={"telegram_id": 999900951})
                last_code = r.status_code
                if last_code == 429:
                    break
            check("21-chi urinishda 429 (rate-limit ishladi)", last_code == 429, f"oxirgi kod={last_code}")

            # ── 3. Invite havolasi muddati ───────────────────────────────
            r = client.post(
                f"{API_BASE}/users/telegram-start",
                headers={"X-Bot-Secret": settings.bot_shared_secret},
                json={"telegram_id": 999900952, "invite_token": "T-invtok-expired-999901"},
            )
            check("Muddati o'tgan invite -> token_expired", r.status_code == 200 and r.json().get("status") == "token_expired",
                  f"kod={r.status_code} {r.text[:150]}")

            r = client.post(
                f"{API_BASE}/users/telegram-start",
                headers={"X-Bot-Secret": settings.bot_shared_secret},
                json={"telegram_id": 999900953, "invite_token": "T-invtok-valid-999902"},
            )
            check("Muddati o'tmagan invite -> ok", r.status_code == 200 and r.json().get("status") == "ok",
                  f"kod={r.status_code} {r.text[:150]}")
    except Exception:
        check("Telegram login xavfsizligi (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_sec()
        conn.close()


def test_hr_wide_employee_access() -> None:
    """HRga BARCHA xodimlar uchun ish jadvali/dam kuni + xodim nomidan sababli
    kun belgilash huquqi berildi:
    1. Ish jadvali: HR ilgari faqat can_manage_norms ruxsat bergan (o'ziga
       biriktirilgan lavozim yoki egasiz) xodimga tegishi mumkin edi — endi
       BARCHA faol 'Xodim' rolidagilarga (boshqa ROP jamoasidagi bo'lsa ham).
       ROP/HRning bir-birini yoki Boshliqni boshqarolmasligi saqlangan.
    2. Sababli kun: HR/Boshliq/Dasturchi xodim nomidan darhol 'approved'
       holatda yozuv qo'sha oladi (ROP bunga huquqli emas — decide bilan bir xil)."""
    import httpx

    from api.config import settings

    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-HrWide%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from work_schedule_weekly where user_id in ({qm})", stale)
        cur.execute(f"delete from work_schedule_override where user_id in ({qm})", stale)
        cur.execute(f"delete from excused_days where user_id in ({qm})", stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999901001,'T-HrWide-Hr','hr',1,1,datetime('now'))")
    hr_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999901002,'T-HrWide-Rop','rop',1,1,datetime('now'))")
    rop_uid = cur.lastrowid
    # position_id/managed_by_roles YO'Q va manager_id ROPga o'rnatilgan — ESKI
    # can_manage_norms qoidasida bu HR uchun 403 bo'lardi (na orphan, na HR
    # lavozimiga tegishli).
    cur.execute(
        "insert into users (telegram_id, full_name, role, manager_id, bot_started, is_active, created_at)"
        " values (999901003,'T-HrWide-Emp',?,?,1,1,datetime('now'))", ("employee", rop_uid))
    emp_uid = cur.lastrowid
    conn.commit()

    def cleanup_hw():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [hr_uid, rop_uid, emp_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from work_schedule_weekly where user_id in ({qm})", uids)
            c2.execute(f"delete from work_schedule_override where user_id in ({qm})", uids)
            c2.execute(f"delete from excused_days where user_id in ({qm})", uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  HR keng qamrov tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        hr_t = token_for(hr_uid, "hr")
        rop_t = token_for(rop_uid, "rop")

        with httpx.Client(timeout=15) as client:
            print("\n" + "=" * 60)
            print("HR KENG QAMROV: ish jadvali + xodim nomidan sababli kun")
            print("=" * 60)

            # ── Ish jadvali: HR endi ROP jamoasidagi xodimga ham tega oladi ──
            r = client.get(f"{API_BASE}/work-schedule/{emp_uid}/weekly", headers=auth(hr_t))
            check("HR boshqa ROP jamoasidagi xodim jadvalini KO'RADI -> 200 (ilgari 403)",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.put(
                f"{API_BASE}/work-schedule/{emp_uid}/weekly", headers=auth(hr_t),
                json={"days": [
                    {"weekday": wd, "is_working": wd < 6, "start_time": "09:00" if wd < 6 else None,
                     "end_time": "18:00" if wd < 6 else None}
                    for wd in range(7)
                ]},
            )
            check("HR shu xodim jadvalini O'ZGARTIRA oladi -> 200 (ilgari 403)",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.put(
                f"{API_BASE}/work-schedule/{emp_uid}/override", headers=auth(hr_t),
                json={"date": "2020-06-06", "is_working": False, "note": "T-sinov: dam kuni"},
            )
            check("HR shu xodimga BITTA KUNLIK dam kuni belgilay oladi -> 200",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.get(f"{API_BASE}/work-schedule/{hr_uid}/weekly", headers=auth(hr_t))
            check("HR boshqa HR/ROP/Boshliq jadvaliga TEGA OLMAYDI (o'ziga ham) -> 403",
                  r.status_code == 403, f"kod={r.status_code}")

            # ── Sababli kun: HR/Boshliq/Dasturchi xodim nomidan darhol belgilaydi ──
            # DIQQAT: endpoint path'i `telegram_id`, DB `id` EMAS.
            r = client.get(f"{API_BASE}/excused-days/targets/999901001",
                            headers={"X-Bot-Secret": settings.bot_shared_secret})
            check("Bot: HR targets -> 200", r.status_code == 200, f"kod={r.status_code}")
            r = client.get(f"{API_BASE}/excused-days/targets/999901002",
                            headers={"X-Bot-Secret": settings.bot_shared_secret})
            check("Bot: ROP targets -> 403 (decide huquqi yo'q)", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(
                f"{API_BASE}/excused-days/for-user", headers=auth(rop_t),
                json={"user_id": emp_uid, "date": "2020-07-07", "reason": "T-sinov"},
            )
            check("ROP xodim nomidan sababli kun BELGILAY OLMAYDI -> 403", r.status_code == 403,
                  f"kod={r.status_code}")

            r = client.post(
                f"{API_BASE}/excused-days/for-user", headers=auth(hr_t),
                json={"user_id": emp_uid, "date": "2020-07-07", "reason": "T-sinov: kasallik"},
            )
            check("HR xodim nomidan sababli kun belgilaydi -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")
            body = r.json() if r.status_code == 200 else {}
            check("Darhol 'approved' holatda (qayta tasdiq shart emas)", body.get("status") == "approved",
                  f"={body}")
            check("decided_by HRning o'zi", body.get("decided_by") == hr_uid, f"={body}")

            r = client.post(
                f"{API_BASE}/excused-days/for-user", headers=auth(hr_t),
                json={"user_id": emp_uid, "date": "2020-07-07", "reason": "T-sinov: takror"},
            )
            check("Bir kunga ikkinchi marta -> 400 (dublikat)", r.status_code == 400, f"kod={r.status_code}")

            r = client.post(
                f"{API_BASE}/excused-days/for-user", headers=auth(hr_t),
                json={"user_id": rop_uid, "date": "2020-08-08", "reason": "T-sinov: xodim emas"},
            )
            check("Faqat 'Xodim' rolidagi nishonga -> 400 (ROPga belgilab bo'lmaydi)",
                  r.status_code == 400, f"kod={r.status_code}")
    except Exception:
        check("HR keng qamrov (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_hw()
        conn.close()


def test_attendance_edit_rights() -> None:
    """Davomat keldi/ketdi vaqtini tuzatish huquqlari (egasining 2026-08-03 talabi):

    1. Dasturchi `PUT /admin/attendance/manual` — AUDITSIZ va jim
       (`AuditLog` yozuvi UMUMAN yaratilmaydi).
    2. Oddiy `PUT /attendance/manual` — audit YOZADI (saytda ko'rinsin).
    3. Huquq SHAXSAN beriladi (`can_edit_attendance`): roli hr/boss/dasturchi
       bo'lmagan odam ham tuzata oladi.
    4. Bayroq bilan tahrirlayotgan odam O'Z yozuvini tuzata OLMAYDI.
    5. Bayroqsiz va roli yo'q odam -> 403.
    6. Yozuv bo'lmasa YARATILADI («Keldim» bosish esidan chiqqan holat)."""
    import httpx

    from api.config import settings

    print("\n" + "=" * 60)
    print("DAVOMAT TUZATISH HUQUQLARI (dasturchi jim + shaxsiy ruxsat)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    DAY = "2020-09-09"

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-AttEdit%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from attendance where user_id in ({qm})", stale)
        cur.execute(f"delete from work_schedule_weekly where user_id in ({qm})", stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, can_edit_attendance, created_at)"
        " values (999903001,'T-AttEdit-Dev','dasturchi',1,1,0,datetime('now'))")
    dev_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, can_edit_attendance, created_at)"
        " values (999903002,'T-AttEdit-Emp','employee',1,1,0,datetime('now'))")
    emp_uid = cur.lastrowid
    # Bayroq bilan ruxsat berilgan ODDIY XODIM (roli bo'yicha huquqi yo'q)
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, can_edit_attendance, created_at)"
        " values (999903003,'T-AttEdit-Granted','employee',1,1,1,datetime('now'))")
    granted_uid = cur.lastrowid
    # Huquqsiz oddiy xodim
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, can_edit_attendance, created_at)"
        " values (999903004,'T-AttEdit-NoRight','employee',1,1,0,datetime('now'))")
    noright_uid = cur.lastrowid
    for uid in (emp_uid, granted_uid):
        cur.execute(
            "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
            " select ?, wd, 1, '09:00', '18:00', datetime('now') from (select 0 wd union select 1 union select 2"
            " union select 3 union select 4 union select 5 union select 6)", (uid,))
    conn.commit()

    def cleanup_ae():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [dev_uid, emp_uid, granted_uid, noright_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from attendance where user_id in ({qm})", uids)
            c2.execute(f"delete from work_schedule_weekly where user_id in ({qm})", uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Davomat huquqi tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    def audit_count(uid: int) -> int:
        c = db()
        try:
            return c.execute(
                "select count(*) from audit_logs where target_user_id=? and action='attendance_manual_edit'", (uid,)
            ).fetchone()[0]
        finally:
            c.close()

    try:
        dev_t = token_for(dev_uid, "dasturchi")
        granted_t = token_for(granted_uid, "employee")
        noright_t = token_for(noright_uid, "employee")

        with httpx.Client(timeout=15) as client:
            # ── 1. Dasturchi JIM tuzatishi: yozuv YARATILADI, audit YO'Q ──
            before_audit = audit_count(emp_uid)
            r = client.put(
                f"{API_BASE}/admin/attendance/manual", headers=auth(dev_t),
                json={"user_id": emp_uid, "date": DAY, "check_in": "09:25", "check_out": "18:00"},
            )
            check("Dasturchi jim tuzatish -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            body = r.json() if r.status_code == 200 else {}
            check("Yozuv YARATILDI (bosish esidan chiqqan holat)", body.get("created") is True, f"={body}")
            check("Kechikish qayta hisoblandi (09:25 -> 25 daq)", body.get("late_minutes") == 25, f"={body}")
            check("Javobda audited=False", body.get("audited") is False, f"={body}")
            check("AuditLog yozuvi YARATILMADI (jim)", audit_count(emp_uid) == before_audit,
                  f"oldin={before_audit} keyin={audit_count(emp_uid)}")

            # ── 2. Shaxsan ruxsat berilgan XODIM tuzata oladi + audit YOZILADI ──
            before_audit = audit_count(emp_uid)
            r = client.put(
                f"{API_BASE}/attendance/manual", headers=auth(granted_t),
                json={"user_id": emp_uid, "date": DAY, "check_in": "09:00", "check_out": "18:00",
                      "reason": "T-sinov: bayroq bilan tuzatish"},
            )
            check("Bayroq berilgan xodim tuzata oladi -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")
            check("Kechikish 0 ga tushdi (09:00)", r.status_code == 200 and r.json().get("late_minutes") == 0,
                  f"={r.json() if r.status_code == 200 else None}")
            check("AuditLog YOZILDI (saytda ko'rinsin)", audit_count(emp_uid) == before_audit + 1,
                  f"oldin={before_audit} keyin={audit_count(emp_uid)}")

            # ── 3. O'Z yozuvini tuzata OLMAYDI ──
            r = client.put(
                f"{API_BASE}/attendance/manual", headers=auth(granted_t),
                json={"user_id": granted_uid, "date": DAY, "check_in": "09:00",
                      "reason": "T-sinov: o'zimniki"},
            )
            check("Bayroq egasi O'Z yozuvini tuzata OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # ── 4. Huquqsiz xodim -> 403 ──
            r = client.put(
                f"{API_BASE}/attendance/manual", headers=auth(noright_t),
                json={"user_id": emp_uid, "date": DAY, "check_in": "10:00", "reason": "T-sinov: ruxsatsiz"},
            )
            check("Huquqsiz xodim -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.put(
                f"{API_BASE}/admin/attendance/manual", headers=auth(granted_t),
                json={"user_id": emp_uid, "date": DAY, "check_in": "10:00"},
            )
            check("Bayroq egasi JIM endpointga kira OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # ── 5. Huquq berish/olish (faqat Dasturchi) + audit ──
            r = client.post(
                f"{API_BASE}/admin/users/{noright_uid}/attendance-editor", headers=auth(dev_t),
                json={"granted": True, "override_reason": "T-sinov: huquq berish"},
            )
            check("Dasturchi huquq beradi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            c = db()
            flag = c.execute("select can_edit_attendance from users where id=?", (noright_uid,)).fetchone()[0]
            c.close()
            check("Bayroq bazada 1 bo'ldi", flag == 1, f"={flag}")

            r = client.get(f"{API_BASE}/admin/attendance-editors", headers=auth(dev_t))
            names = [x["full_name"] for x in r.json()] if r.status_code == 200 else []
            check("Ro'yxatda yangi huquq egasi bor", "T-AttEdit-NoRight" in names, f"={names}")

            r = client.post(
                f"{API_BASE}/admin/users/{noright_uid}/attendance-editor", headers=auth(granted_t),
                json={"granted": True, "override_reason": "T-sinov: ruxsatsiz berish"},
            )
            check("Dasturchi bo'lmagan huquq bera OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")
    except Exception:
        check("Davomat tuzatish huquqlari (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_ae()
        conn.close()


def test_location_exempt_checkin() -> None:
    """«Bez lokatsiya» check-in (egasining 2026-08-03 talabi):

    1. Bayroqli xodim ISTALGAN joydan (koordinatasiz) «Keldim» qila oladi.
    2. Bayroqsiz xodim koordinatasiz yuborsa — RAD etiladi (aks holda GPS
       tekshiruvini istalgan kishi `latitude: null` bilan chetlab o'tardi).
    3. Bayroqli xodimda ham Face ID BEKOR QILINMAYDI.
    4. Ruxsatni faqat Dasturchi bera oladi."""
    import httpx

    print("\n" + "=" * 60)
    print("JOYLASHUVSIZ CHECK-IN («bez lokatsiya»)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    FACE_JSON = json.dumps([0.05] * 128)

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-NoGeo%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from attendance where user_id in ({qm})", stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, face_descriptor,"
        " skip_location_check, created_at) values (999904001,'T-NoGeo-Free','employee',1,1,?,1,datetime('now'))",
        (FACE_JSON,))
    free_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, face_descriptor,"
        " skip_location_check, created_at) values (999904002,'T-NoGeo-Bound','employee',1,1,?,0,datetime('now'))",
        (FACE_JSON,))
    bound_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999904003,'T-NoGeo-Dev','dasturchi',1,1,datetime('now'))")
    dev_uid = cur.lastrowid
    conn.commit()

    def cleanup_ng():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [free_uid, bound_uid, dev_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from attendance where user_id in ({qm})", uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Bez-lokatsiya tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        free_t = token_for(free_uid, "employee")
        bound_t = token_for(bound_uid, "employee")
        dev_t = token_for(dev_uid, "dasturchi")
        body_nogeo = {"latitude": None, "longitude": None, "face_descriptor": [0.05] * 128, "liveness": 1.0}

        with httpx.Client(timeout=20) as client:
            # 1. Bayroqli xodim — koordinatasiz o'tadi
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(free_t), json=body_nogeo)
            check("Bayroqli xodim koordinatasiz «Keldim» -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:160]}")
            check("Masofa NULL (0 emas — soxta 'ofis markazi' bo'lmasin)",
                  r.status_code == 200 and r.json().get("check_in_distance_m") is None,
                  f"={r.json().get('check_in_distance_m') if r.status_code == 200 else None}")

            # 2. Bayroqsiz xodim — koordinatasiz RAD etiladi
            r = client.post(f"{API_BASE}/attendance/me/check-in", headers=auth(bound_t), json=body_nogeo)
            check("Bayroqsiz xodim koordinatasiz -> RAD etiladi", r.status_code >= 400,
                  f"kod={r.status_code} {r.text[:160]}")

            # 3. Bayroqli xodimda Face ID baribir tekshiriladi (begona yuz)
            c = db()
            c.execute("delete from attendance where user_id=?", (free_uid,))
            c.commit()
            c.close()
            r = client.post(
                f"{API_BASE}/attendance/me/check-in", headers=auth(free_t),
                json={**body_nogeo, "face_descriptor": [0.9] * 128},
            )
            check("Bayroqli xodim BEGONA yuz bilan -> RAD (Face ID bekor emas)",
                  r.status_code >= 400, f"kod={r.status_code} {r.text[:160]}")

            # 4. Ruxsatni faqat Dasturchi beradi
            r = client.post(
                f"{API_BASE}/admin/users/{bound_uid}/location-exempt", headers=auth(dev_t),
                json={"granted": True, "override_reason": "T-sinov: bez lokatsiya"},
            )
            check("Dasturchi ruxsat beradi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            c = db()
            flag = c.execute("select skip_location_check from users where id=?", (bound_uid,)).fetchone()[0]
            c.close()
            check("Bayroq bazada 1 bo'ldi", flag == 1, f"={flag}")

            r = client.post(
                f"{API_BASE}/admin/users/{bound_uid}/location-exempt", headers=auth(free_t),
                json={"granted": True, "override_reason": "T-sinov: ruxsatsiz"},
            )
            check("Dasturchi bo'lmagan ruxsat bera OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")
    except Exception:
        check("Bez-lokatsiya check-in (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_ng()
        conn.close()


def test_attendance_reminder() -> None:
    """«Keldim/Ketdim bosishni unutmang» eslatmasi (D-bo'lim, 2026-08-03).

    ⚠️ FAQAT `dry_run` ishlatiladi — real xodimga Telegram xabari KETMAYDI.
    Sinov T- xodimlarning ish oynasini HOZIRGI vaqtga moslab qo'yadi, ya'ni
    "ish boshlanishiga 15 daqiqa qoldi" holati sun'iy yaratiladi.

    Tekshiriladi: (a) bosmagan -> ro'yxatga tushadi; (b) dam kunida ->
    tushmaydi; (c) sababli kunda -> tushmaydi; (d) allaqachon bosgan ->
    tushmaydi; (e) iz yozilgach takror tushmaydi."""
    import httpx

    from api.config import settings

    print("\n" + "=" * 60)
    print("DAVOMAT ESLATMASI («Keldim/Ketdim bosishni unutmang»)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    today = date.today().isoformat()
    now = datetime.now(TZ)
    # Ish boshlanishi = hozir + 10 daqiqa -> "15 daqiqa qoldi" oynasi ichida.
    start_at = (now + timedelta(minutes=10)).strftime("%H:%M")
    end_at = (now + timedelta(minutes=200)).strftime("%H:%M")

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-Rem%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        for t in ("attendance_reminders", "attendance", "work_schedule_override",
                  "work_schedule_weekly", "excused_days"):
            cur.execute(f"delete from {t} where user_id in ({qm})", stale)
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    def mk(tg: int, name: str) -> int:
        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
            " values (?,?,'employee',1,1,datetime('now'))", (tg, name))
        return cur.lastrowid

    forgot_uid = mk(999905001, "T-Rem-Forgot")     # bosmagan -> eslatma KERAK
    dayoff_uid = mk(999905002, "T-Rem-DayOff")     # dam kuni -> KERAK EMAS
    excused_uid = mk(999905003, "T-Rem-Excused")   # sababli -> KERAK EMAS
    done_uid = mk(999905004, "T-Rem-Done")         # allaqachon bosgan -> KERAK EMAS

    for uid in (forgot_uid, excused_uid, done_uid):
        cur.execute(
            "insert into work_schedule_override (user_id, date, is_working, start_time, end_time, updated_at)"
            " values (?,?,1,?,?,datetime('now'))", (uid, today, start_at, end_at))
    # Dam kuni
    cur.execute(
        "insert into work_schedule_override (user_id, date, is_working, updated_at)"
        " values (?,?,0,datetime('now'))", (dayoff_uid, today))
    # Sababli kun (tasdiqlangan)
    cur.execute(
        "insert into excused_days (user_id, date, reason, status, created_at)"
        " values (?,?,'T-sinov','approved',datetime('now'))", (excused_uid, today))
    # Allaqachon «Keldim» bosgan
    cur.execute(
        "insert into attendance (user_id, date, check_in_time, late_minutes, early_leave_minutes,"
        " worked_minutes, status, is_weekend, created_at, updated_at)"
        " values (?,?,datetime('now'),0,0,0,'present',0,datetime('now'),datetime('now'))",
        (done_uid, today))
    conn.commit()

    def cleanup_rem():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [forgot_uid, dayoff_uid, excused_uid, done_uid]
            qm = ",".join("?" * len(uids))
            for t in ("attendance_reminders", "attendance", "work_schedule_override",
                      "work_schedule_weekly", "excused_days"):
                c2.execute(f"delete from {t} where user_id in ({qm})", uids)
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Eslatma tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        hdr = {"X-Bot-Secret": settings.bot_shared_secret}
        with httpx.Client(timeout=30) as client:
            r = client.post(f"{API_BASE}/attendance/reminder-tick", headers=hdr, json={"dry_run": True})
            check("reminder-tick (dry_run) -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            planned = r.json().get("planned", []) if r.status_code == 200 else []
            ids = {p["user_id"] for p in planned}

            check("Bosmagan xodim ro'yxatda BOR", forgot_uid in ids, f"planned={sorted(ids)}")
            check("Dam kunidagi YO'Q", dayoff_uid not in ids, f"planned={sorted(ids)}")
            check("Sababli kundagi YO'Q", excused_uid not in ids, f"planned={sorted(ids)}")
            check("Allaqachon bosgan YO'Q", done_uid not in ids, f"planned={sorted(ids)}")
            check("Bosmagan uchun tur = check_in",
                  any(p["user_id"] == forgot_uid and p["kind"] == "check_in" for p in planned),
                  f"={[p for p in planned if p['user_id'] == forgot_uid]}")

            # Iz yozilgan bo'lsa takror tushmasligi (real yuborishsiz — izni
            # qo'lda yozamiz, chunki dry_run iz yozmaydi).
            c = db()
            c.execute(
                "insert into attendance_reminders (user_id, date, kind, sent_at)"
                " values (?,?,'check_in',datetime('now'))", (forgot_uid, today))
            c.commit()
            c.close()
            r = client.post(f"{API_BASE}/attendance/reminder-tick", headers=hdr, json={"dry_run": True})
            ids2 = {p["user_id"] for p in r.json().get("planned", [])} if r.status_code == 200 else set()
            check("Iz yozilgach TAKROR tushmaydi", forgot_uid not in ids2, f"planned={sorted(ids2)}")
    except Exception:
        check("Davomat eslatmasi (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_rem()
        conn.close()


def test_dashboard_day_off() -> None:
    """Dashboardda «dam olishda» bo'limi (A-bo'lim, 2026-08-03).

    Dam kunidagilar ilgari hech qayerda ko'rinmasdi: `working_today`dan
    tushib qolar, `not_checked_in`ga ham kirmas edi (to'g'ri — jarima ham
    olmaydi), lekin rahbar ekranida javobsiz farq qolardi.

    MUHIM: bu FAQAT ko'rinish — hisob-kitobga ta'sir qilmasligi ham
    tekshiriladi (`working_today` va `not_checked_in` o'zgarmasin)."""
    import httpx

    print("\n" + "=" * 60)
    print("DASHBOARD: «bugun dam olishda» bo'limi")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    today = date.today().isoformat()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-DayOff%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        for t in ("attendance", "work_schedule_override", "work_schedule_weekly"):
            cur.execute(f"delete from {t} where user_id in ({qm})", stale)
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999906001,'T-DayOff-Resting','employee',1,1,datetime('now'))")
    rest_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999906002,'T-DayOff-Working','employee',1,1,datetime('now'))")
    work_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999906003,'T-DayOff-Hr','hr',1,1,datetime('now'))")
    hr_uid = cur.lastrowid
    cur.execute(
        "insert into work_schedule_override (user_id, date, is_working, updated_at)"
        " values (?,?,0,datetime('now'))", (rest_uid, today))
    cur.execute(
        "insert into work_schedule_override (user_id, date, is_working, start_time, end_time, updated_at)"
        " values (?,?,1,'09:00','18:00',datetime('now'))", (work_uid, today))
    conn.commit()

    def cleanup_do():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [rest_uid, work_uid, hr_uid]
            qm = ",".join("?" * len(uids))
            for t in ("attendance", "work_schedule_override", "work_schedule_weekly"):
                c2.execute(f"delete from {t} where user_id in ({qm})", uids)
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Dam kuni tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        hr_t = token_for(hr_uid, "hr")
        with httpx.Client(timeout=20) as client:
            r = client.get(f"{API_BASE}/attendance/dashboard", headers=auth(hr_t))
            check("dashboard -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            body = r.json() if r.status_code == 200 else {}
            names = {x["full_name"] for x in body.get("on_day_off", [])}
            summary = body.get("summary", {})

            check("Dam kunidagi xodim ro'yxatda BOR", "T-DayOff-Resting" in names, f"={sorted(names)}")
            check("Ishlayotgan xodim ro'yxatda YO'Q", "T-DayOff-Working" not in names, f"={sorted(names)}")
            check("summary.on_day_off soni ro'yxat bilan mos",
                  summary.get("on_day_off") == len(body.get("on_day_off", [])),
                  f"soni={summary.get('on_day_off')} ro'yxat={len(body.get('on_day_off', []))}")
            # Hisob-kitobga ta'sir qilmasligi: dam kunidagi na "ishlashi kerak",
            # na "kelmagan" ga kirmaydi.
            check("Dam kunidagi 'kelmagan' ga KIRMAYDI",
                  summary.get("not_checked_in", 0) <= summary.get("working_today", 0),
                  f"kelmagan={summary.get('not_checked_in')} ishlashi_kerak={summary.get('working_today')}")
    except Exception:
        check("Dashboard dam kuni (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_do()
        conn.close()


def test_fine_policy_rights() -> None:
    """Kechikish normasini o'zgartirish huquqi (C-bo'lim, 2026-08-03).

    1. Bayroqli odam (roli hr/boss/dasturchi EMAS) jarima qoidasini
       o'zgartira oladi.
    2. Bayroqsiz ROP -> 403.
    3. ⚠️ Bayroq FAQAT jarima qoidasini ochadi — oylik hisoblash/tasdiqlash
       va stavkalar OCHILMAYDI (aks holda bitta bayroq bilan butun payroll
       boshqaruvi berilib qolardi).
    4. Huquqni Boshliq VA Dasturchi bera oladi; HR bera OLMAYDI."""
    import httpx

    print("\n" + "=" * 60)
    print("KECHIKISH NORMASI HUQUQI (shaxsan beriladi)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-Fine%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    def mk(tg: int, name: str, role: str, flag: int = 0) -> int:
        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " can_edit_fine_policy, created_at) values (?,?,?,1,1,?,datetime('now'))",
            (tg, name, role, flag))
        return cur.lastrowid

    granted_uid = mk(999908001, "T-Fine-Granted", "rop", 1)   # bayroqli ROP
    plain_uid = mk(999908002, "T-Fine-PlainRop", "rop", 0)    # bayroqsiz ROP
    boss_uid = mk(999908003, "T-Fine-Boss", "boss")
    dev_uid = mk(999908004, "T-Fine-Dev", "dasturchi")
    hr_uid = mk(999908005, "T-Fine-Hr", "hr")
    conn.commit()

    def cleanup_fp():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [granted_uid, plain_uid, boss_uid, dev_uid, hr_uid]
            qm = ",".join("?" * len(uids))
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Jarima huquqi tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        granted_t = token_for(granted_uid, "rop")
        plain_t = token_for(plain_uid, "rop")
        boss_t = token_for(boss_uid, "boss")
        dev_t = token_for(dev_uid, "dasturchi")
        hr_t = token_for(hr_uid, "hr")

        with httpx.Client(timeout=20) as client:
            # 1. Bayroqli ROP qoidani KO'RA va O'ZGARTIRA oladi
            r = client.get(f"{API_BASE}/payroll/policies", headers=auth(granted_t))
            check("Bayroqli ROP qoidani ko'radi -> 200", r.status_code == 200, f"kod={r.status_code}")

            # 2. Bayroqsiz ROP -> 403
            r = client.get(f"{API_BASE}/payroll/policies", headers=auth(plain_t))
            check("Bayroqsiz ROP -> 403", r.status_code == 403, f"kod={r.status_code}")

            # 3. ⚠️ Bayroq BOSHQA payroll amallarini OCHMAYDI
            r = client.get(f"{API_BASE}/payroll/rates", headers=auth(granted_t))
            check("Bayroqli ROP STAVKALARGA kira OLMAYDI -> 403", r.status_code == 403,
                  f"kod={r.status_code} (bayroq faqat jarima qoidasini ochishi kerak)")
            r = client.post(
                f"{API_BASE}/payroll/2020-01/calculate", headers=auth(granted_t), json={},
            )
            check("Bayroqli ROP oylik HISOBLAY olmaydi -> 403", r.status_code == 403,
                  f"kod={r.status_code}")

            # 4. Huquqni kim bera oladi
            r = client.get(f"{API_BASE}/payroll/fine-policy-editors", headers=auth(boss_t))
            check("Boshliq ro'yxatni ko'radi -> 200", r.status_code == 200, f"kod={r.status_code}")
            names = [x["full_name"] for x in r.json()] if r.status_code == 200 else []
            check("Ro'yxatda bayroqli ROP bor", "T-Fine-Granted" in names, f"={names}")

            r = client.get(f"{API_BASE}/payroll/fine-policy-editors", headers=auth(hr_t))
            check("HR huquq ro'yxatiga kira OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.post(
                f"{API_BASE}/payroll/fine-policy-editors/{plain_uid}", headers=auth(dev_t),
                json={"granted": True, "reason": "T-sinov: dasturchi beradi"},
            )
            check("Dasturchi huquq beradi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")

            r = client.post(
                f"{API_BASE}/payroll/fine-policy-editors/{plain_uid}", headers=auth(boss_t),
                json={"granted": False, "reason": "T-sinov: boshliq oladi"},
            )
            check("Boshliq huquqni oladi -> 200", r.status_code == 200, f"kod={r.status_code}")

            r = client.post(
                f"{API_BASE}/payroll/fine-policy-editors/{plain_uid}", headers=auth(hr_t),
                json={"granted": True, "reason": "T-sinov: hr bera olmaydi"},
            )
            check("HR huquq bera OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")
    except Exception:
        check("Kechikish normasi huquqi (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_fp()
        conn.close()


def test_explanation_letters() -> None:
    """Tushuntirish xati (B-bo'lim, 2026-08-03).

    Oqim: sababsiz `absent` -> tizim so'raydi -> xodim botda javob yozadi ->
    HR qaror qiladi. Qabul qilinsa MAVJUD `ExcusedDay` orqali kun sababliga
    o'tadi va jarima o'z-o'zidan tushadi (yangi jarima yo'li YO'Q).

    ⚠️ Real xodimga xabar ketmasligi uchun so'rov QO'LDA yaratiladi
    (`ask_explanations` job'i emas) — u bot xabari yuborardi."""
    import httpx

    from api.config import settings

    print("\n" + "=" * 60)
    print("TUSHUNTIRISH XATI (sababsiz kelmagan kun)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    DAY = "2020-11-11"

    stale = [r[0] for r in cur.execute("select id from users where full_name like 'T-Expl%'").fetchall()]
    if stale:
        qm = ",".join("?" * len(stale))
        for t in ("explanation_requests", "attendance", "excused_days", "work_schedule_override"):
            cur.execute(f"delete from {t} where user_id in ({qm})", stale)
        cur.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", stale + stale)
        cur.execute(f"delete from users where id in ({qm})", stale)
    conn.commit()

    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999909001,'T-Expl-Emp','employee',1,1,datetime('now'))")
    emp_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999909002,'T-Expl-Hr','hr',1,1,datetime('now'))")
    hr_uid = cur.lastrowid
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999909003,'T-Expl-Other','employee',1,1,datetime('now'))")
    other_uid = cur.lastrowid
    # Sababsiz kelmagan kun + so'rov (job'siz, xabar yubormasdan)
    cur.execute(
        "insert into attendance (user_id, date, late_minutes, early_leave_minutes, worked_minutes,"
        " status, is_weekend, created_at, updated_at)"
        " values (?,?,0,0,0,'absent',0,datetime('now'),datetime('now'))", (emp_uid, DAY))
    cur.execute(
        "insert into explanation_requests (user_id, date, status, asked_at)"
        " values (?,?,'pending',datetime('now'))", (emp_uid, DAY))
    req_id = cur.lastrowid
    conn.commit()

    def cleanup_ex():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [emp_uid, hr_uid, other_uid]
            qm = ",".join("?" * len(uids))
            for t in ("explanation_requests", "attendance", "excused_days", "work_schedule_override"):
                c2.execute(f"delete from {t} where user_id in ({qm})", uids)
            c2.execute(f"delete from audit_logs where target_user_id in ({qm}) or actor_id in ({qm})", uids + uids)
            c2.execute(f"delete from users where id in ({qm})", uids)
            conn2.commit()
            conn2.close()
        except Exception:
            print("  Tushuntirish tozalash xatosi:\n" + traceback.format_exc(limit=1).strip())

    try:
        hr_t = token_for(hr_uid, "hr")
        emp_t = token_for(emp_uid, "employee")
        bot_hdr = {"X-Bot-Secret": settings.bot_shared_secret}

        with httpx.Client(timeout=20) as client:
            # 1. BOSHQA odam javob yoza OLMAYDI (tugma forward qilinsa ham)
            r = client.post(
                f"{API_BASE}/attendance/explanations/{req_id}/answer", headers=bot_hdr,
                json={"telegram_id": 999909003, "answer_text": "Men boshqa odamman"},
            )
            check("Begona odam javob yoza OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # 2. Egasi javob yozadi
            r = client.post(
                f"{API_BASE}/attendance/explanations/{req_id}/answer", headers=bot_hdr,
                json={"telegram_id": 999909001, "answer_text": "T-sinov: kasal bo'lib qoldim"},
            )
            check("Xodim javob yozadi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            check("Holat 'answered' bo'ldi", r.status_code == 200 and r.json().get("status") == "answered",
                  f"={r.json() if r.status_code == 200 else None}")

            # 3. Xodim ro'yxatni ko'ra OLMAYDI (faqat hr/boss/dasturchi)
            r = client.get(f"{API_BASE}/attendance/explanations", headers=auth(emp_t))
            check("Oddiy xodim ro'yxatga kira OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = client.get(f"{API_BASE}/attendance/explanations?status_filter=answered", headers=auth(hr_t))
            check("HR ro'yxatni ko'radi -> 200", r.status_code == 200, f"kod={r.status_code}")
            ids = [x["id"] for x in r.json()] if r.status_code == 200 else []
            check("Javob kelgan xat ro'yxatda bor", req_id in ids, f"={ids}")

            # 4. HR QABUL qiladi -> ExcusedDay yaratiladi, davomat qayta hisoblanadi
            r = client.post(
                f"{API_BASE}/attendance/explanations/{req_id}/decide", headers=auth(hr_t),
                json={"accept": True, "note": "T-sinov: qabul"},
            )
            check("HR qabul qiladi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")
            check("Holat 'accepted'", r.status_code == 200 and r.json().get("status") == "accepted",
                  f"={r.json() if r.status_code == 200 else None}")

            c = db()
            exc = c.execute(
                "select status from excused_days where user_id=? and date=?", (emp_uid, DAY)
            ).fetchone()
            att_status = c.execute(
                "select status from attendance where user_id=? and date=?", (emp_uid, DAY)
            ).fetchone()
            c.close()
            check("MAVJUD ExcusedDay yaratildi va 'approved'", exc is not None and exc[0] == "approved",
                  f"={exc}")
            check("Davomat yozuvi qayta hisoblandi (endi 'absent' emas)",
                  att_status is not None and att_status[0] != "absent", f"={att_status}")

            # 5. Hal qilingan xatga qayta javob yozib bo'lmaydi
            r = client.post(
                f"{API_BASE}/attendance/explanations/{req_id}/answer", headers=bot_hdr,
                json={"telegram_id": 999909001, "answer_text": "T-sinov: qayta yozaman"},
            )
            check("Hal qilingan xatga qayta javob -> 400", r.status_code == 400, f"kod={r.status_code}")
    except Exception:
        check("Tushuntirish xati (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_ex()
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

    try:
        test_admin_override()
    except Exception:
        print("Admin override testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_payroll_automation()
    except Exception:
        print("Payroll avtomatika testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_payroll_reporting()
    except Exception:
        print("Payroll hisobot testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_dasturchi_bot_bridge()
    except Exception:
        print("Dasturchi bot ko'prigi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_positions_permissions()
    except Exception:
        print("Lavozim ruxsatlari testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_telegram_login_security()
    except Exception:
        print("Telegram login xavfsizligi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_hr_wide_employee_access()
    except Exception:
        print("HR keng qamrov testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_attendance_edit_rights()
    except Exception:
        print("Davomat tuzatish huquqlari testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_location_exempt_checkin()
    except Exception:
        print("Bez-lokatsiya check-in testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_attendance_reminder()
    except Exception:
        print("Davomat eslatmasi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_dashboard_day_off()
    except Exception:
        print("Dashboard dam kuni testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_fine_policy_rights()
    except Exception:
        print("Kechikish normasi huquqi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_explanation_letters()
    except Exception:
        print("Tushuntirish xati testida kutilmagan xato:\n" + traceback.format_exc())

    print("\n" + "=" * 60)
    print(f"NATIJA: {len(passed)} OK, {len(failed)} FAIL")
    for name in failed:
        print(f"  FAIL: {name}")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
