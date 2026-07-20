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

            # Kechikishni mustaqil hisoblab solishtirish: (hozir - 09:00) - grace(5)
            expected = (checkin_moment.hour * 60 + checkin_moment.minute) - (9 * 60) - 5
            expected = max(0, expected)
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

    print("\n" + "=" * 60)
    print(f"NATIJA: {len(passed)} OK, {len(failed)} FAIL")
    for name in failed:
        print(f"  FAIL: {name}")
    print("=" * 60)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
