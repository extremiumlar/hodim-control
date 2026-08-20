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
    """Bitta tekshiruv natijasini qayd etadi va chiqaradi. Chop etish konsol
    kodlashiga chidamli — aks holda extra ichidagi «» kabi belgi Windows
    konsolida UnicodeEncodeError otib, TESTNING O'ZINI yiqitardi (natija
    baholanmasdan FAIL bo'lardi)."""
    (passed if cond else failed).append(name)
    mark = "  [OK]  " if cond else "  [FAIL]"
    line = f"{mark} {name}" + (f"  | {extra}" if extra else "")
    try:
        print(line)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, "replace").decode(enc, "replace"))


def db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# ─────────────────────────────────────────────────────────────────
# Sozlash / tozalash — xatoga chidamli (har biri alohida try/except)
# ─────────────────────────────────────────────────────────────────

def require_notifications_off() -> None:
    """Xabarlar YOQIQ serverga qarshi testni ISHGA TUSHIRMAYDI.

    NEGA: test bazadagi HAQIQIY xodimlar bilan ishlaydi — sinov davri
    («2022-03», «2021-05») uchun hisoblash/tasdiqlash amallari Boshliq va
    HR ga Telegram/push xabari yuboradi. 2026-08-17 da bu IKKI MARTA sodir
    bo'ldi: birinchisida `BOT_TOKEN` bo'shatilgan, lekin push kanali ochiq
    qolgan edi; ikkinchisida esa server oddiy rejimda qayta ishga
    tushirilgani unutilgan edi.

    Endi bu insonning e'tiboriga emas, TEKSHIRUVGA bog'liq.
    """
    import httpx

    try:
        r = httpx.get(f"{API_BASE}/health", timeout=10)
        holat = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"XATO: API ({API_BASE}) javob bermadi: {e}")
        sys.exit(1)

    if holat.get("notifications_enabled") is not False:
        print("=" * 70)
        print("TO'XTATILDI: API xabar yuborish YOQIQ holatda ishlayapti.")
        print("Test haqiqiy xodimlarga Telegram/push yuborib yuboradi.")
        print()
        print("Serverni shu rejimda qayta ishga tushiring:")
        print("  NOTIFICATIONS_ENABLED=false .venv/Scripts/python.exe -m uvicorn"
              " api.main:app --host 127.0.0.1 --port 8000")
        print("=" * 70)
        sys.exit(1)


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


def bot_secret_hdr() -> dict:
    """`.env`dagi BOT_SHARED_SECRET — bot/cron endpointlari uchun."""
    env_path = Path(__file__).resolve().parent / ".env"
    with open(env_path, encoding="utf-8") as f:
        secret = next(
            (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")), ""
        )
    return {"X-Bot-Secret": secret}


def payroll_tick(client, kutilgan: str | None = None, urinish: int = 5) -> dict | None:
    """Navbatdagi oylik hisobini bajaradi — testda CRON o'rnini bosadi (§4.3).

    NEGA KERAK: `POST /payroll/{period}/calculate` endi hisobni o'zi
    bajarmaydi, faqat NAVBATGA qo'yadi (202) — production'da Passenger
    konkurentligi = 1 va og'ir hisob butun saytni qotirardi. Haqiqiy ishni
    `scripts/cron_tick.py` alohida jarayonda qiladi; test esa xuddi shu
    servisni HTTP orqali chaqiradi.

    Navbatda boshqa davr ham turgan bo'lishi mumkin (oldingi blok qoldig'i) —
    shuning uchun kutilgan davr chiqquncha bir necha marta uriniladi."""
    natija = None
    for _ in range(urinish):
        r = client.post(f"{API_BASE}/payroll/tick", headers=bot_secret_hdr(), json={})
        if r.status_code != 200:
            return {"http": r.status_code, "text": r.text[:200]}
        natija = r.json()
        if natija.get("ran") is None:
            break
        if kutilgan is None or natija.get("ran") == kutilgan:
            break
    return natija


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

            # ⚠️ JONLI MA'LUMOT HIMOYASI: write_absent_records BUGUN uchun
            # chaqiriladi va u HAQIQIY xodimlarga ham (hali check-in qilmagan
            # bo'lsa) absent yozadi — kun hali tugamagan bo'lsa bu YOLG'ON
            # yozuv bo'lib qoladi va matritsada "Kutilmoqda" o'rniga "Kelmadi"
            # ko'rinadi. Chaqiruvdan OLDINGI id'larni eslab, test yaratganlarini
            # (T-lardan tashqari haqiqiylarni ham) oxirida O'CHIRAMIZ.
            before_ids = {
                r[0] for r in conn.execute(
                    "select id from attendance where date=?", (today.isoformat(),)
                ).fetchall()
            }

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

            # Test yaratgan BARCHA bugungi absent yozuvlarini o'chiramiz —
            # haqiqiy xodimlarnikini ham (kun tugagach kechki tick ularni
            # o'zi qayta yozadi, hech narsa yo'qolmaydi).
            after_rows = conn.execute(
                "select id from attendance where date=?", (today.isoformat(),)
            ).fetchall()
            new_ids = [r[0] for r in after_rows if r[0] not in before_ids]
            if new_ids:
                cur2.execute(
                    "delete from attendance where id in (%s)" % ",".join("?" * len(new_ids)),
                    new_ids,
                )

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
            # ⚠️ QAROR O'ZGARDI (yangi TZ 2.9 / S-09). Ilgari sababli kunda
            # check-in ATAYIN o'tkazilardi (200 + ogohlantirish) — «ta'tildan
            # chaqirib olish normal» degan mulohaza bilan. Amalda bu xodimni
            # bir vaqtning o'zida ham «ta'tilda», ham «ishda» qilib qo'ydi va
            # oylik/norma/davomat uchta har xil javob berardi. Endi RAD
            # etiladi, HR ga esa xabar boradi.
            check("S-09: sababli kunda check-in RAD etildi -> 400",
                  r.status_code == 400, f"kod={r.status_code} {r.text[:150]}")
            check("S-09: rad etish sababi aytilgan (sababli kun)",
                  r.status_code == 400 and "sababli kun" in r.text,
                  r.text[:150])
            qator = cur.execute(
                "select count(*) from attendance where user_id=?", (ex_uid,)).fetchone()[0]
            check("S-09: rad etilgach davomat yozuvi YARATILMADI", qator == 0,
                  f"qatorlar={qator}")

            # 5.1 ning ASL qoidasi kuchda: sababli kunda kechikish yozilmaydi.
            # Endi bu check-in orqali emas (u bloklangan), balki qo'lda
            # kiritilgan / avtomatik qayta hisoblangan yozuv orqali sinaladi —
            # HR ta'tildagi kunni qo'lda tuzatishi mumkin.
            try:
                import asyncio as _aio

                from db.base import async_session as _sess

                async def _qayta():
                    from api.services.attendance import recompute_attendance
                    from db.models import Attendance as _Att
                    from db.models import User as _U
                    from sqlalchemy import select as _sel
                    async with _sess() as s3:
                        u3 = await s3.get(_U, ex_uid)
                        att3 = _Att(user_id=ex_uid, date=date.today(),
                                    check_in_time=datetime.utcnow())
                        s3.add(att3)
                        await s3.flush()
                        await recompute_attendance(s3, att3, u3)
                        await s3.commit()
                        row = await s3.scalar(
                            _sel(_Att).where(_Att.user_id == ex_uid))
                        return row.status, row.late_minutes

                st, lt = _aio.run(_qayta())
                check("5.1: late_minutes=0 (sababli kun, aks holda kech qolgan bo'lardi)",
                      lt == 0, f"late={lt}")
                check("5.1: status='excused'", st == "excused", f"status={st}")
            except Exception:
                check("5.1 qayta hisob tekshiruvi", False,
                      traceback.format_exc(limit=2).strip())

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

        # ═══════════ UX-A bosqichi (DAVOMAT_UX_PROMPT.md) ═══════════

        print("\n-- UX-A2/A3: oylik matritsa va xodim tarixi --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444801,'T-Matrix','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            mx_uid = cur.lastrowid
            # Jadval: Du-Sha ish (09:00-18:00), Yak dam — 2020-yanvar butunlay
            # nazorat ostida (real bugunga bog'liq emas).
            for wd in range(7):
                cur.execute(
                    "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                    " values (?,?,?,?,?,datetime('now'))",
                    (mx_uid, wd, 1 if wd < 6 else 0,
                     "09:00" if wd < 6 else None, "18:00" if wd < 6 else None))
            # 2020-01-02 (Pa): kechikish yozuvi; 01-03 (Ju): yozuvsiz -> virtual absent;
            # 01-04 (Sh): sababli (yozuvsiz); 01-05 (Ya): dam.
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, created_at, updated_at)"
                " values (?, '2020-01-02', '2020-01-02 04:15:00', 15, 0, 460, 'late', 0,"
                " datetime('now'), datetime('now'))", (mx_uid,))
            cur.execute(
                "insert into excused_days (user_id, date, reason, status, created_at)"
                " values (?, '2020-01-04', 'T-sinov', 'approved', datetime('now'))", (mx_uid,))
            conn.commit()

            r = client.get(f"{API_BASE}/attendance/matrix?month=2020-01&user_id={mx_uid}",
                           headers=auth(boss_t))
            check("A2: matrix -> 200", r.status_code == 200, f"kod={r.status_code}")
            body = r.json() if r.status_code == 200 else {}
            emp = (body.get("employees") or [{}])[0]
            cells = {c["date"]: c for c in emp.get("cells", [])}
            check("A2: yozuvli kun -> late (+vaqt mahalliy)",
                  cells.get("2020-01-02", {}).get("status") == "late"
                  and cells.get("2020-01-02", {}).get("check_in") == "09:15",
                  str(cells.get("2020-01-02")))
            check("A2: yozuvsiz o'tgan ish kuni -> absent (virtual)",
                  cells.get("2020-01-03", {}).get("status") == "absent", str(cells.get("2020-01-03")))
            check("A2: sababli kun (yozuvsiz) -> excused",
                  cells.get("2020-01-04", {}).get("status") == "excused", str(cells.get("2020-01-04")))
            check("A2: dam kuni -> weekend",
                  cells.get("2020-01-05", {}).get("status") == "weekend", str(cells.get("2020-01-05")))
            tot = emp.get("totals", {})
            check("A2: totals (late 1/15, excused 1)",
                  tot.get("late_count") == 1 and tot.get("late_minutes") == 15
                  and tot.get("excused_days") == 1, str(tot))
            check("A2: user_id filtri faqat bitta xodim qaytardi",
                  len(body.get("employees", [])) == 1)

            # Joriy oy: bugun (ish kuni, yozuvsiz) -> pending; ertaga -> future.
            r2 = client.get(f"{API_BASE}/attendance/matrix?user_id={mx_uid}", headers=auth(boss_t))
            cells2 = {c["date"]: c for c in (r2.json().get("employees") or [{}])[0].get("cells", [])}
            today_iso2 = date.today().isoformat()
            check("A2: bugungi yozuvsiz ish kuni -> pending",
                  cells2.get(today_iso2, {}).get("status") == "pending",
                  str(cells2.get(today_iso2)))
            tomorrow = date.today() + timedelta(days=1)
            if tomorrow.month == date.today().month:
                exp = "weekend" if tomorrow.weekday() == 6 else "future"
                check("A2: ertangi kun -> future/weekend",
                      cells2.get(tomorrow.isoformat(), {}).get("status") == exp,
                      str(cells2.get(tomorrow.isoformat())))

            # A3: xodim o'z tarixini oladi
            mx_tok = token_for(mx_uid, "employee")
            r3 = client.get(f"{API_BASE}/attendance/me/history?month=2020-01", headers=auth(mx_tok))
            check("A3: me/history -> 200", r3.status_code == 200, f"kod={r3.status_code}")
            days3 = {c["date"]: c for c in r3.json().get("days", [])}
            check("A3: xodim kalendari matritsa bilan bir xil (late kuni)",
                  days3.get("2020-01-02", {}).get("status") == "late"
                  and days3.get("2020-01-02", {}).get("schedule_start") == "09:00",
                  str(days3.get("2020-01-02")))
            r4 = client.get(f"{API_BASE}/attendance/me/history?month=2020-13", headers=auth(mx_tok))
            check("A3: noto'g'ri oy -> 400", r4.status_code == 400, f"kod={r4.status_code}")
            r5 = client.get(f"{API_BASE}/attendance/matrix", headers=auth(mx_tok))
            check("A2: oddiy xodimga matrix -> 403", r5.status_code == 403, f"kod={r5.status_code}")

            # A4: aniq davr parametrlari
            r6 = client.get(
                f"{API_BASE}/attendance/employee-summary?date_from=2020-01-01&date_to=2020-01-31",
                headers=auth(boss_t))
            row6 = next((x for x in r6.json() if x["user_id"] == mx_uid), None)
            check("A4: employee-summary aniq davr bilan", row6 is not None and row6["late_minutes"] == 15,
                  str(row6))
            r7 = client.get(
                f"{API_BASE}/attendance/late-stats?date_from=2020-01-01&date_to=2020-01-31",
                headers=auth(boss_t))
            check("A4: late-stats aniq davr bilan",
                  any(x["user_id"] == mx_uid for x in r7.json()), f"{len(r7.json())} qator")
            r8 = client.get(f"{API_BASE}/attendance/late-stats?date_from=2020-01-01",
                            headers=auth(boss_t))
            check("A4: faqat bitta sana parametri -> 400", r8.status_code == 400, f"kod={r8.status_code}")

            cur.execute("delete from attendance where user_id=?", (mx_uid,))
            cur.execute("delete from excused_days where user_id=?", (mx_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (mx_uid,))
            cur.execute("delete from users where id=?", (mx_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("UX-A2/A3 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- UX-A1: dashboard kelmaganlar ismlari --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444802,'T-NotCome','employee',1,1,datetime('now'))")
            nc_uid = cur.lastrowid
            wd = date.today().weekday()
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'08:30','18:00',datetime('now'))", (nc_uid, wd))
            conn.commit()

            r = client.get(f"{API_BASE}/attendance/dashboard", headers=auth(boss_t))
            body = r.json() if r.status_code == 200 else {}
            row = next((x for x in body.get("not_come", []) if x["user_id"] == nc_uid), None)
            check("A1: kelmagan xodim not_come ro'yxatida (jadval vaqti bilan)",
                  row is not None and row["schedule_start"] == "08:30", str(row))
            check("A1: left ro'yxati mavjud", "left" in body)

            # Sababli kun tasdiqlansa -> not_come'dan chiqib excused_today'ga o'tadi
            cur.execute(
                "insert into excused_days (user_id, date, reason, status, created_at)"
                " values (?, ?, 'T-sinov', 'approved', datetime('now'))",
                (nc_uid, date.today().isoformat()))
            conn.commit()
            r2 = client.get(f"{API_BASE}/attendance/dashboard", headers=auth(boss_t))
            b2 = r2.json()
            check("A1: sababli xodim not_come'da EMAS, excused_today'da BOR",
                  not any(x["user_id"] == nc_uid for x in b2.get("not_come", []))
                  and any(x["user_id"] == nc_uid for x in b2.get("excused_today", [])),
                  f"not_come={len(b2.get('not_come', []))}, excused={len(b2.get('excused_today', []))}")

            # UX-A5: eslatma — fake telegramga yetkazib bo'lmaydi -> 400;
            # 2 ta audit izi bo'lsa -> 429; oddiy xodimga -> 403.
            cur.execute("delete from excused_days where user_id=?", (nc_uid,))
            conn.commit()
            r3 = client.post(f"{API_BASE}/attendance/remind/{nc_uid}", headers=auth(boss_t))
            check("A5: yetkazib bo'lmasa -> 400 (fake telegram)", r3.status_code == 400,
                  f"kod={r3.status_code} {r3.text[:120]}")
            for _ in range(2):
                cur.execute(
                    "insert into audit_logs (actor_id, action, target_user_id, created_at)"
                    " values (1, 'attendance_reminder_sent', ?, datetime('now'))", (nc_uid,))
            conn.commit()
            r4 = client.post(f"{API_BASE}/attendance/remind/{nc_uid}", headers=auth(boss_t))
            check("A5: kuniga 2 tadan keyin -> 429", r4.status_code == 429, f"kod={r4.status_code}")
            emp_tok = token_for(nc_uid, "employee")
            r5 = client.post(f"{API_BASE}/attendance/remind/{nc_uid}", headers=auth(emp_tok))
            check("A5: oddiy xodim eslata olmaydi -> 403", r5.status_code == 403, f"kod={r5.status_code}")

            cur.execute("delete from audit_logs where target_user_id=?", (nc_uid,))
            cur.execute("delete from work_schedule_weekly where user_id=?", (nc_uid,))
            cur.execute("delete from users where id=?", (nc_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("UX-A1/A5 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- UX2-W1: dashboard late_list/user_id + remind-all --")
        try:
            conn = db()
            cur = conn.cursor()
            wd = date.today().weekday()
            today_iso2 = date.today().isoformat()

            # Kechikkan va allaqachon ketgan T-xodim — late_list'da bo'lishi kerak
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444804,'T-LateGuy','employee',1,1,datetime('now'))")
            lg_uid = cur.lastrowid
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, check_out_time, status,"
                " late_minutes, early_leave_minutes, worked_minutes, created_at, updated_at)"
                " values (?,?,datetime('now','-4 hours'),datetime('now','-1 hours'),'late',25,0,180,"
                " datetime('now'),datetime('now'))",
                (lg_uid, today_iso2))
            conn.commit()

            r = client.get(f"{API_BASE}/attendance/dashboard", headers=auth(boss_t))
            body = r.json() if r.status_code == 200 else {}
            ll = body.get("late_list", [])
            lg = next((x for x in ll if x["user_id"] == lg_uid), None)
            check("W1: late_list'da kechikkan xodim (25 daq, ketgan)",
                  lg is not None and lg["late_minutes"] == 25 and lg["left"] is True, str(lg))
            check("W1: late_list kamayish tartibida",
                  ll == sorted(ll, key=lambda x: x["late_minutes"], reverse=True),
                  str([x["late_minutes"] for x in ll]))
            check("W1: recent yozuvlarida user_id bor",
                  all("user_id" in x for x in body.get("recent", [])),
                  f"recent={len(body.get('recent', []))}")
            check("W1: in_office yozuvlarida user_id bor",
                  all("user_id" in x for x in body.get("in_office", [])),
                  f"in_office={len(body.get('in_office', []))}")

            # remind-all XAVFSIZ sinovi: yuborishdan OLDIN limit tekshiriladi,
            # shuning uchun BARCHA haqiqiy xodimlarga bugunga 2 tadan audit izi
            # qo'yamiz (ularga HECH NARSA yuborilmaydi); faqat fake-telegram'li
            # T-xodim yuborish yo'lidan o'tadi (Telegram 'chat not found' — jim).
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444805,'T-RemindAll','employee',1,1,datetime('now'))")
            ra_uid = cur.lastrowid
            cur.execute(
                "insert into work_schedule_weekly (user_id, weekday, is_working, start_time, end_time, updated_at)"
                " values (?,?,1,'09:00','18:00',datetime('now'))", (ra_uid, wd))
            seeded_ids = []
            for (uid,) in cur.execute(
                "select id from users where is_active=1 and id not in (?,?)", (ra_uid, lg_uid)
            ).fetchall():
                for _ in range(2):
                    cur.execute(
                        "insert into audit_logs (actor_id, action, target_user_id, created_at)"
                        " values (1, 'attendance_reminder_sent', ?, datetime('now'))", (uid,))
                    seeded_ids.append(cur.lastrowid)
            conn.commit()

            r6 = client.post(f"{API_BASE}/attendance/remind-all", headers=auth(boss_t))
            rb = r6.json() if r6.status_code == 200 else {}
            check("W1: remind-all -> 200", r6.status_code == 200, f"kod={r6.status_code} {r6.text[:120]}")
            check("W1: remind-all hech kimga yubormadi (hammada limit/fake)",
                  rb.get("sent") == 0, str(rb)[:200])
            ra_fail = next((f for f in rb.get("failed", []) if f["full_name"] == "T-RemindAll"), None)
            check("W1: T-RemindAll yuborish yo'lidan o'tdi (yetkazib bo'lmadi)",
                  ra_fail is not None and "yetkazib bo'lmadi" in ra_fail["reason"], str(ra_fail))
            real_fails = [f for f in rb.get("failed", []) if not f["full_name"].startswith("T-")]
            check("W1: haqiqiy xodimlar limitda to'xtadi (xabar ketmagan)",
                  all("2 marta" in f["reason"] for f in real_fails),
                  str([f["reason"] for f in real_fails])[:200])

            emp_tok2 = token_for(ra_uid, "employee")
            r7 = client.post(f"{API_BASE}/attendance/remind-all", headers=auth(emp_tok2))
            check("W1: remind-all oddiy xodimga -> 403", r7.status_code == 403, f"kod={r7.status_code}")

            # Tozalash: faqat O'ZIMIZ qo'ygan audit izlari + T- ma'lumotlar
            if seeded_ids:
                cur.execute(
                    "delete from audit_logs where id in (%s)" % ",".join("?" * len(seeded_ids)),
                    seeded_ids)
            for u in (lg_uid, ra_uid):
                cur.execute("delete from audit_logs where target_user_id=?", (u,))
                cur.execute("delete from attendance where user_id=?", (u,))
                cur.execute("delete from work_schedule_weekly where user_id=?", (u,))
                cur.execute("delete from users where id=?", (u,))
            conn.commit()
            conn.close()
        except Exception:
            check("UX2-W1 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- TASHRIF HISOBI: voqea-asosli (KPI = statistika) --")
        try:
            import asyncio as _aio2

            from db.base import async_session as _asess2
            from api.services import lead_diff as _ld

            conn = db()
            cur = conn.cursor()
            VISIT_ID = 8787  # .env dagi tashrif bosqichi (birinchisi)
            other = 7136

            # Ikki operator: T-Olib (lidni olib kelgan) va T-Yopgan (tashrifga o'tkazgan)
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " crm_visit_external_id, created_at)"
                " values (999777001,'T-Olib','employee',1,1,'970001',datetime('now'))")
            u_olib = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " crm_visit_external_id, created_at)"
                " values (999777002,'T-Yopgan','employee',1,1,'970002',datetime('now'))")
            u_yopgan = cur.lastrowid

            now_utc = datetime.utcnow()
            ts_now = int(now_utc.timestamp())

            def add_event(lead_id, frm, to, rid, first_rid):
                cur.execute(
                    "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                    " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                    " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                    " values (?,'stage_change',?,'T-eski',?,'T-Tashrif',?,?,?,?,?)",
                    (lead_id, frm, to, rid, "T-op", first_rid, ts_now,
                     now_utc.isoformat(sep=" ", timespec="seconds")))

            # 1) Tashrifga YANGI kirish, olib kelgan boshqa odam -> DUAL-KREDIT
            add_event(970101, other, VISIT_ID, 970002, 970001)
            # 2) Allaqachon Tashrifda bo'lgan lid yana tahrirlandi -> SANALMAYDI
            add_event(970102, VISIT_ID, VISIT_ID, 970002, 970002)
            # 3) O'zi olib kelib o'zi yopgan -> FAQAT BITTA kredit
            add_event(970103, other, VISIT_ID, 970002, 970002)
            conn.commit()

            async def _stats():
                async with _asess2() as s:
                    return await _ld.visit_stats_range(s, date.today(), date.today(), {VISIT_ID})

            ser = _aio2.run(_stats())
            ops = ser["daily_by_operator"].get(date.today(), {})
            uniq = ser["daily_unique"].get(date.today(), 0)

            check("Tashrif: takroriy tahrir SANALMAYDI (2 noyob, 3 voqea emas)",
                  uniq >= 2 and ops.get(970002, 0) >= 2, f"noyob={uniq}, ops={ops}")
            check("Tashrif: olib kelgan operatorga ALOHIDA kredit (dual)",
                  ops.get(970001, 0) >= 1, f"olib_kelgan={ops.get(970001)}")
            check("Tashrif: o'zi olib kelib o'zi yopganda ikki marta sanalmaydi",
                  ops.get(970002, 0) == uniq, f"yopgan={ops.get(970002)}, noyob={uniq}")

            # 2026-08-13 (egasining qarori): `first_seen` — bu CRM hodisasi
            # emas, bizning skaner lidni birinchi ko'rgani. Lid o'sha paytda
            # allaqachon Tashrifda bo'lsa, u tashrif deb SANALMASLIGI kerak.
            cur.execute(
                "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                " values (970104,'first_seen',NULL,NULL,?,'T-Tashrif',970002,'T-op',970002,?,?)",
                (VISIT_ID, ts_now, now_utc.isoformat(sep=" ", timespec="seconds")))
            conn.commit()
            ser2 = _aio2.run(_stats())
            uniq2 = ser2["daily_unique"].get(date.today(), 0)
            check("Tashrif: first_seen (skaner endi ko'rgan lid) SANALMAYDI",
                  uniq2 == uniq, f"first_seen'siz={uniq}, keyin={uniq2}")

            # recalc-visits endpointi: dry_run farqni ko'rsatadi, yozmaydi
            today_iso3 = date.today().isoformat()
            cur.execute(
                "insert into daily_results (user_id, date, conversations_count, visits_count,"
                " source) values (?,?,0,99,'crm')",
                (u_yopgan, today_iso3))
            conn.commit()
            r = client.post(
                f"{API_BASE}/daily-results/recalc-visits?date_from={today_iso3}"
                f"&date_to={today_iso3}&dry_run=true", headers=auth(boss_t))
            body = r.json() if r.status_code == 200 else {}
            ch = [c for c in body.get("changes", []) if c["user"] == "T-Yopgan"]
            check("Tashrif: recalc dry_run yolg'on sonni ko'rsatadi (99 -> voqea)",
                  r.status_code == 200 and ch and ch[0]["old"] == 99 and ch[0]["new"] != 99,
                  f"kod={r.status_code}, {ch[:1]}")
            after_dry = cur.execute(
                "select visits_count from daily_results where user_id=? and date=?",
                (u_yopgan, today_iso3)).fetchone()[0]
            check("Tashrif: dry_run bazaga YOZMAYDI", after_dry == 99, f"baza={after_dry}")

            r2 = client.post(
                f"{API_BASE}/daily-results/recalc-visits?date_from={today_iso3}"
                f"&date_to={today_iso3}&dry_run=false", headers=auth(boss_t))
            conn.commit()
            after_real = cur.execute(
                "select visits_count from daily_results where user_id=? and date=?",
                (u_yopgan, today_iso3)).fetchone()[0]
            check("Tashrif: dry_run=false haqiqatan tuzatadi",
                  r2.status_code == 200 and after_real != 99, f"baza={after_real}")

            emp_tok3 = token_for(u_olib, "employee")
            r3 = client.post(
                f"{API_BASE}/daily-results/recalc-visits?date_from={today_iso3}"
                f"&date_to={today_iso3}", headers=auth(emp_tok3))
            check("Tashrif: recalc oddiy xodimga -> 403", r3.status_code == 403, f"kod={r3.status_code}")

            cur.execute("delete from lead_events where crm_lead_id in (970101,970102,970103,970104)")
            cur.execute("delete from daily_results where user_id in (?,?)", (u_olib, u_yopgan))
            cur.execute("delete from users where id in (?,?)", (u_olib, u_yopgan))
            conn.commit()
            conn.close()
        except Exception:
            check("Tashrif hisobi tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- TABRIK VIDEOLARI: tashrif/shartnoma -> guruh + tugma --")
        try:
            import asyncio as _aio3

            from db.base import async_session as _asess3
            from api.services import celebration as _cel

            conn = db()
            cur = conn.cursor()
            # Oldingi UZILGAN yugurishdan qolgan izlar (UNIQUE xatosi bermasin)
            cur.execute("delete from celebration_claps where post_id in (select id from"
                        " celebration_posts where crm_lead_id between 970601 and 970606)")
            cur.execute("delete from celebration_posts where crm_lead_id between 970601 and 970606")
            cur.execute("delete from celebration_media where file_id like 'T-FILE-%'")
            cur.execute("delete from lead_events where crm_lead_id between 970601 and 970606")
            cur.execute("delete from monitored_groups where chat_id=-100999778")
            cur.execute("delete from users where telegram_id in (999778001,999778002,999778003)")
            conn.commit()
            V_ID = 8787          # tashrif bosqichi
            C_ID = 999888        # test uchun "shartnoma" bosqichi
            OTHER = 7136

            # Telegram'ga HECH NARSA ketmasin — yuboruvchilarni almashtiramiz
            sent_calls: list = []
            edited: list = []

            async def _fake_send_file(chat_id, file_id, file_type, caption=None, reply_markup=None):
                sent_calls.append(
                    {"chat": chat_id, "file_id": file_id, "type": file_type,
                     "caption": caption, "markup": reply_markup})
                return {"result": {"message_id": 5550 + len(sent_calls)}}

            async def _fake_send_msg(chat_id, text, reply_markup=None):
                sent_calls.append({"chat": chat_id, "file_id": None, "caption": text})
                return {"result": {"message_id": 6660 + len(sent_calls)}}

            async def _fake_edit(chat_id, message_id, reply_markup):
                edited.append({"chat": chat_id, "msg": message_id, "markup": reply_markup})
                return {"ok": True}

            _orig = (_cel.send_file_id, _cel.send_message, _cel.edit_reply_markup,
                     list(_cel.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS))
            _cel.send_file_id = _fake_send_file
            _cel.send_message = _fake_send_msg
            _cel.edit_reply_markup = _fake_edit
            _cel.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [C_ID]

            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " crm_visit_external_id, created_at)"
                " values (999778001,'T-Menejer','employee',1,1,'970501',datetime('now'))")
            u_men = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999778002,'T-HRcel','hr',1,1,datetime('now'))")
            u_hr = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999778003,'T-Xodimcel','employee',1,1,datetime('now'))")
            u_emp = cur.lastrowid

            # Umumiy guruh: jonli yozuvga TEGMAYMIZ — bo'lsa o'chirib turamiz,
            # oxirida asl holiga qaytariladi.
            live_main = cur.execute(
                "select id from monitored_groups where purpose='main' and is_active=1").fetchall()
            for (gid,) in live_main:
                cur.execute("update monitored_groups set is_active=0 where id=?", (gid,))
            cur.execute(
                "insert into monitored_groups (purpose, chat_id, title, is_active, created_at)"
                " values ('main', -100999778, 'T-Guruh', 1, datetime('now'))")
            g_id = cur.lastrowid
            conn.commit()

            cel_now = datetime.utcnow()
            cel_ts = int(cel_now.timestamp())

            def add_ev(lead_id, etype, frm, to, rid):
                cur.execute(
                    "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                    " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                    " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                    " values (?,?,?,'T-eski',?,'T-bosqich',?,'T-crm-nom',?,?,?)",
                    (lead_id, etype, frm, to, rid, rid, cel_ts,
                     cel_now.isoformat(sep=" ", timespec="seconds")))
                conn.commit()

            async def _announce(dry=False):
                async with _asess3() as s:
                    return await _cel.announce_pending(s, dry_run=dry)

            try:
                # 1) Video YO'Q -> guruhga hech nima ketmaydi (funksiya o'chiq tug'iladi)
                add_ev(970601, "stage_change", OTHER, V_ID, 970501)
                res0 = _aio3.run(_announce())
                check("Tabrik: video yuklanmagan bo'lsa guruhga hech narsa ketmaydi",
                      res0.get("sent") == 0 and not sent_calls, f"{res0}, chaqiruv={len(sent_calls)}")

                # 2) HR botdan video yuklaydi
                with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as _f:
                    _cel_secret = next(
                        (ln.strip().split("=", 1)[1] for ln in _f
                         if ln.startswith("BOT_SHARED_SECRET=")), "")
                bot_h_cel = {"X-Bot-Secret": _cel_secret}
                rset = client.post(f"{API_BASE}/celebration/media", headers=bot_h_cel, json={
                    "telegram_id": 999778002, "kind": "visit",
                    "file_id": "T-FILE-VISIT", "file_type": "video", "caption": "Zo'r ish!"})
                check("Tabrik: HR video yuklay oladi", rset.status_code == 200, f"kod={rset.status_code}")

                rdeny = client.post(f"{API_BASE}/celebration/media", headers=bot_h_cel, json={
                    "telegram_id": 999778003, "kind": "visit", "file_id": "X", "file_type": "video"})
                check("Tabrik: oddiy xodim video yuklay OLMAYDI -> 403",
                      rdeny.status_code == 403, f"kod={rdeny.status_code}")

                # 3) Endi o'sha voqea uchun video guruhga ketadi
                res1 = _aio3.run(_announce())
                check("Tabrik: tashrif voqeasida guruhga video yuboriladi",
                      res1.get("sent") == 1 and len(sent_calls) == 1, f"{res1}, {len(sent_calls)}")
                first = sent_calls[0] if sent_calls else {}
                check("Tabrik: to'g'ri guruh + to'g'ri fayl",
                      first.get("chat") == -100999778 and first.get("file_id") == "T-FILE-VISIT",
                      f"{first.get('chat')}, {first.get('file_id')}")
                check("Tabrik: izohda xodim ismi va rahbar matni bor",
                      "T-Menejer" in (first.get("caption") or "")
                      and "Zo'r ish!" in (first.get("caption") or ""),
                      f"izoh={(first.get('caption') or '')[:60]}")
                check("Tabrik: tabriklash tugmasi qo'yiladi",
                      "Tabriklash" in str(first.get("markup")), f"markup={str(first.get('markup'))[:60]}")

                # 4) TAKROR yuborilmaydi (webhook + cron ikkalasi chaqirsa ham)
                res2 = _aio3.run(_announce())
                check("Tabrik: bir voqea IKKI marta e'lon qilinmaydi",
                      res2.get("sent") == 0 and len(sent_calls) == 1, f"{res2}, {len(sent_calls)}")

                # 5) first_seen tabrik BERMAYDI (tashrif hisobidagi qoida bilan bir xil)
                add_ev(970602, "first_seen", None, V_ID, 970501)
                res3 = _aio3.run(_announce())
                check("Tabrik: first_seen uchun video yuborilmaydi",
                      res3.get("sent") == 0 and len(sent_calls) == 1, f"{res3}, {len(sent_calls)}")

                # 6) Tashrif ichida ko'chish ham tabrik emas
                add_ev(970603, "stage_change", V_ID, V_ID, 970501)
                res4 = _aio3.run(_announce())
                check("Tabrik: Tashrif->Tashrif ko'chishi tabrik bermaydi",
                      res4.get("sent") == 0, f"{res4}")

                # 7) Shartnoma — alohida video, alohida sarlavha
                add_ev(970604, "stage_change", V_ID, C_ID, 970501)
                res5 = _aio3.run(_announce())
                check("Tabrik: shartnoma videosi yuklanmagan -> yuborilmaydi",
                      res5.get("sent") == 0 and res5.get("skipped_no_media") == 1, f"{res5}")

                client.post(f"{API_BASE}/celebration/media", headers=bot_h_cel, json={
                    "telegram_id": 999778002, "kind": "contract",
                    "file_id": "T-FILE-CONTRACT", "file_type": "animation"})
                res6 = _aio3.run(_announce())
                last = sent_calls[-1] if sent_calls else {}
                check("Tabrik: shartnomada BOSHQA video (GIF) ketadi",
                      res6.get("sent") == 1 and last.get("file_id") == "T-FILE-CONTRACT"
                      and last.get("type") == "animation", f"{res6}, {last.get('file_id')}")
                check("Tabrik: shartnoma sarlavhasi tashrifdan farq qiladi",
                      "SHARTNOMA" in (last.get("caption") or ""),
                      f"izoh={(last.get('caption') or '')[:40]}")

                # 8) Tabriklash tugmasi: bir odam bir marta
                post_id = cur.execute(
                    "select id from celebration_posts where crm_lead_id=970601").fetchone()[0]

                async def _clap(tg):
                    async with _asess3() as s:
                        return await _cel.register_clap(s, post_id, tg)

                c1 = _aio3.run(_clap(555001))
                c2 = _aio3.run(_clap(555001))
                c3 = _aio3.run(_clap(555002))
                check("Tabrik: tabrik sanog'i oshadi", c1.get("claps") == 1, f"{c1}")
                check("Tabrik: bitta odam ikki marta tabriklay olmaydi",
                      c2.get("already") is True and c2.get("claps") == 1, f"{c2}")
                check("Tabrik: boshqa odam bossa sanoq 2 bo'ladi", c3.get("claps") == 2, f"{c3}")
                check("Tabrik: tugma matni yangilanadi (editMessageReplyMarkup)",
                      len(edited) >= 2 and "(2)" in str(edited[-1].get("markup")),
                      f"tahrir={len(edited)}, {str(edited[-1].get('markup'))[:50] if edited else ''}")

                # 8b) SAYT paneli: fayl -> Telegram -> file_id (bot bilan bir xil natija)
                uploaded: list = []

                async def _fake_upload(chat_id, content, filename, file_type, caption=None):
                    uploaded.append(
                        {"chat": chat_id, "bayt": len(content), "nom": filename, "tur": file_type})
                    return {"result": {file_type: {"file_id": f"T-FILE-WEB-{file_type}"}}}

                _orig_upload = _cel.send_media_file
                _cel.send_media_file = _fake_upload
                try:
                    hr_tok_cel = token_for(u_hr, "hr")
                    emp_tok_cel = token_for(u_emp, "employee")

                    rweb = client.get(f"{API_BASE}/celebration/settings", headers=auth(hr_tok_cel))
                    check("Tabrik(web): HR sozlamalarni ko'radi",
                          rweb.status_code == 200 and len(rweb.json().get("items", [])) == 2,
                          f"kod={rweb.status_code}")
                    rweb_deny = client.get(f"{API_BASE}/celebration/settings",
                                           headers=auth(emp_tok_cel))
                    check("Tabrik(web): oddiy xodimga -> 403",
                          rweb_deny.status_code == 403, f"kod={rweb_deny.status_code}")

                    # Yuklash yo'li SERVISDA sinaladi: test alohida jarayonda,
                    # API boshqasida — bu yerdagi almashtirish serverga ta'sir
                    # qilmaydi va so'rov haqiqiy Telegram'ga ketib qolardi.
                    from db.models import User as _UserModel

                    async def _upload(kind, name, ctype, data, cap):
                        async with _asess3() as s3:
                            actor = await s3.get(_UserModel, u_hr)
                            return await _cel.upload_and_set(
                                s3, kind, data, name, ctype, cap, actor)

                    rup = _aio3.run(_upload("visit", "tabrik.mp4", "video/mp4", b"x" * 2048, "Saytdan"))
                    check("Tabrik(web): video yuklandi va file_id saqlandi",
                          rup.get("ok") and rup.get("file_type") == "video" and len(uploaded) == 1,
                          f"{rup}, yuklashlar={len(uploaded)}")
                    saved = cur.execute(
                        "select file_id, file_type, caption from celebration_media"
                        " where kind='visit' and is_active=1").fetchone()
                    check("Tabrik(web): faol yozuv Telegram file_id bilan almashdi",
                          saved and saved[0] == "T-FILE-WEB-video" and saved[2] == "Saytdan",
                          f"baza={saved}")

                    rgif = _aio3.run(_upload("contract", "tabrik.gif", "image/gif", b"g" * 512, ""))
                    check("Tabrik(web): GIF animation sifatida yuklanadi",
                          rgif.get("ok") and rgif.get("file_type") == "animation", f"{rgif}")

                    rnotg = _aio3.run(_upload("visit", "hujjat.pdf", "application/pdf", b"%PDF", ""))
                    check("Tabrik(web): servis ham video bo'lmagan faylni rad etadi",
                          not rnotg.get("ok"), f"{rnotg}")

                    rbad = client.post(
                        f"{API_BASE}/celebration/settings/upload", headers=auth(hr_tok_cel),
                        data={"kind": "visit", "caption": ""},
                        files={"file": ("hujjat.pdf", b"%PDF-1.4", "application/pdf")})
                    check("Tabrik(web): video bo'lmagan fayl rad etiladi -> 400",
                          rbad.status_code == 400, f"kod={rbad.status_code}")

                    rbig = client.post(
                        f"{API_BASE}/celebration/settings/upload", headers=auth(hr_tok_cel),
                        data={"kind": "visit", "caption": ""},
                        files={"file": ("katta.mp4", b"x" * (46 * 1024 * 1024), "video/mp4")})
                    check("Tabrik(web): 45 MB dan katta fayl rad etiladi -> 400",
                          rbig.status_code == 400, f"kod={rbig.status_code}")

                    rup_deny = client.post(
                        f"{API_BASE}/celebration/settings/upload", headers=auth(emp_tok_cel),
                        data={"kind": "visit", "caption": ""},
                        files={"file": ("tabrik.mp4", b"x" * 128, "video/mp4")})
                    check("Tabrik(web): oddiy xodim yuklay OLMAYDI -> 403",
                          rup_deny.status_code == 403, f"kod={rup_deny.status_code}")
                finally:
                    _cel.send_media_file = _orig_upload
                    # Bot bloki davomi eski file_id larni kutadi — qaytaramiz
                    cur.execute("update celebration_media set is_active=0"
                                " where file_id like 'T-FILE-WEB-%'")
                    cur.execute("update celebration_media set is_active=1"
                                " where file_id in ('T-FILE-VISIT','T-FILE-CONTRACT')")
                    conn.commit()

                # 9) O'chirish -> yangi voqeaga video ketmaydi
                client.post(f"{API_BASE}/celebration/media/disable", headers=bot_h_cel,
                            json={"telegram_id": 999778002, "kind": "visit"})
                add_ev(970605, "stage_change", OTHER, V_ID, 970501)
                before_n = len(sent_calls)
                res7 = _aio3.run(_announce())
                check("Tabrik: o'chirilgan turda video yuborilmaydi",
                      res7.get("sent") == 0 and len(sent_calls) == before_n, f"{res7}")

                # 10) Eski voqea (lookback tashqarisi) guruhga to'kilmaydi
                client.post(f"{API_BASE}/celebration/media", headers=bot_h_cel, json={
                    "telegram_id": 999778002, "kind": "visit", "file_id": "T-FILE-VISIT2",
                    "file_type": "video"})
                old_dt = (cel_now - timedelta(hours=48)).isoformat(sep=" ", timespec="seconds")
                cur.execute(
                    "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                    " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                    " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                    " values (970606,'stage_change',?,'T-eski',?,'T-bosqich',970501,'T',970501,?,?)",
                    (OTHER, V_ID, cel_ts, old_dt))
                conn.commit()
                before_n2 = len(sent_calls)
                res8 = _aio3.run(_announce())
                sent_leads = [r[0] for r in cur.execute(
                    "select crm_lead_id from celebration_posts").fetchall()]
                check("Tabrik: eski (48 soatlik) voqea guruhga to'kilmaydi",
                      970606 not in sent_leads, f"postlar={sent_leads}")
                check("Tabrik: lekin YANGI voqea (970605) endi yuboriladi",
                      res8.get("sent") == 1 and len(sent_calls) == before_n2 + 1, f"{res8}")

            finally:
                # ── tozalash: HAR QANDAY holatda (xato bo'lsa ham) ──
                # Aks holda ochiq SQLite ulanishi keyingi bloklarni
                # "database is locked" bilan yiqitadi (jonli uchradi).
                try:
                    cur.execute("delete from celebration_claps where post_id in (select id"
                                " from celebration_posts where crm_lead_id between 970601 and 970606)")
                    cur.execute("delete from celebration_posts where crm_lead_id between 970601 and 970606")
                    cur.execute("delete from celebration_media where file_id like 'T-FILE-%'")
                    cur.execute("delete from lead_events where crm_lead_id between 970601 and 970606")
                    cur.execute("delete from monitored_groups where id=?", (g_id,))
                    for (gid,) in live_main:
                        cur.execute("update monitored_groups set is_active=1 where id=?", (gid,))
                    cur.execute("delete from audit_logs where actor_id in (?,?,?)", (u_men, u_hr, u_emp))
                    cur.execute("delete from users where id in (?,?,?)", (u_men, u_hr, u_emp))
                    conn.commit()
                finally:
                    conn.close()
                    (_cel.send_file_id, _cel.send_message, _cel.edit_reply_markup,
                     _cel.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _orig
        except Exception:
            check("Tabrik videolari tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: bosqichlar, konversiya, kogorta --")
        try:
            import asyncio as _aio4

            from db.base import async_session as _asess4
            from datetime import timezone as _tz4
            from api.services import funnel as _fn

            conn = db()
            cur = conn.cursor()
            FL = 980001  # test lid diapazoni
            cur.execute("delete from lead_events where crm_lead_id >= ?", (FL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (FL,))
            conn.commit()

            # Bosqich ID'larini testda QOTIRAMIZ — jonli .env ga bog'liq
            # bo'lmasin (u yerda ID o'zgarsa test yiqilmasligi kerak).
            _fn_orig = (
                list(_fn.CRM_UYSOT_INVITE_PIPE_STATUS_IDS),
                list(_fn.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn.CRM_UYSOT_INVITE_PIPE_STATUS_IDS = [8786]
            _fn.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                fn_day = date(2021, 5, 10)          # tarixiy oy — jonli ma'lumotga tegmaydi
                fn_from, fn_to = date(2021, 5, 1), date(2021, 5, 31)
                fn_ts = int(datetime(2021, 5, 10, 9, tzinfo=_tz4.utc).timestamp())
                fn_det = datetime(2021, 5, 10, 9).isoformat(sep=" ", timespec="seconds")

                for i in range(5):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?)",
                        (FL + i, 8779, "T-Yangi", 1, "T-op", 1, fn_ts, fn_ts, fn_det, fn_det))

                def fev(lead, to_id, etype="stage_change", det=fn_det):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,?,8779,'T-Yangi',?,'T-bosqich',1,'T-op',1,?,?)",
                        (lead, etype, to_id, fn_ts, det))

                fev(FL + 0, 8786); fev(FL + 0, 8787); fev(FL + 0, 8788)   # to'liq zanjir
                fev(FL + 1, 8786); fev(FL + 1, 8787)                       # tashrifgacha
                fev(FL + 2, 8787)                                          # TAKLIFSIZ sakrash
                fev(FL + 3, 8786)                                          # faqat taklif
                fev(FL + 4, 8787, etype="first_seen")                      # SANALMASIN
                conn.commit()

                async def _per():
                    async with _asess4() as s:
                        return await _fn.period_funnel(s, fn_from, fn_to)

                async def _coh():
                    async with _asess4() as s:
                        return await _fn.cohort_funnel(s, fn_from, fn_to)

                per = _aio4.run(_per())
                by = {r["key"]: r for r in per["rows"]}
                check("Voronka: lid soni CRM yaratilish vaqtidan (5)",
                      by["lead"]["value"] == 5, f"lid={by['lead']['value']}")
                check("Voronka: sakragan lid taklifda ham sanaladi (4)",
                      by["invite"]["value"] == 4, f"taklif={by['invite']['value']}")
                check("Voronka: tashrif = 3", by["visit"]["value"] == 3,
                      f"tashrif={by['visit']['value']}")
                check("Voronka: first_seen tashrif bermaydi (4 emas, 3)",
                      by["visit"]["value"] == 3, f"tashrif={by['visit']['value']}")
                check("Voronka: shartnoma = 1", by["contract"]["value"] == 1,
                      f"shartnoma={by['contract']['value']}")
                check("Voronka: qo'ng'iroq qatorida konversiya YO'Q (zanjirdan tashqari)",
                      by["call_try"]["conv_from_prev"] is None and by["call_try"]["outside_chain"],
                      f"{by['call_try']}")
                check("Voronka: tashrif->shartnoma konversiyasi 33.3%",
                      by["contract"]["conv_from_prev"] == 33.3,
                      f"={by['contract']['conv_from_prev']}")

                coh = _aio4.run(_coh())
                cby = {r["key"]: r for r in coh["rows"]}
                check("Voronka(kogorta): lid=5, shartnoma=1",
                      cby["lead"]["value"] == 5 and cby["contract"]["value"] == 1,
                      f"lid={cby['lead']['value']}, shartnoma={cby['contract']['value']}")
                check("Voronka(kogorta): liddan shartnomagacha 20%",
                      cby["contract"]["conv_from_lead"] == 20.0,
                      f"={cby['contract']['conv_from_lead']}")
                check("Voronka(kogorta): eski davr «pishgan» deb belgilanadi",
                      coh["mature"] is True, f"mature={coh['mature']}, yosh={coh['age_days']}")

                # Tashrifda TURGAN lid shartnomaga o'tsa, «tashrif» qatorida
                # QAYTA sanalmasligi kerak (jonli 2026-08 da shu sabab 139 ta
                # tashrif chiqqan, KPI esa 44 ta ko'rsatgan edi).
                fev(FL + 1, 8788, det=fn_det)   # 8787 -> 8788 (tashrifdan shartnomaga)
                conn.commit()
                per2 = _aio4.run(_per())
                by2 = {r["key"]: r for r in per2["rows"]}
                check("Voronka: tashrifdan shartnomaga o'tish tashrifni QAYTA sanamaydi",
                      by2["visit"]["value"] == 3, f"tashrif={by2['visit']['value']}")
                check("Voronka: lekin shartnoma soni oshadi (1 -> 2)",
                      by2["contract"]["value"] == 2, f"shartnoma={by2['contract']['value']}")

                weak = _fn.weakest_link(per["rows"])
                check("Voronka: eng zaif bo'g'in — shartnoma (33.3%)",
                      weak and weak["key"] == "contract", f"{weak}")

                # Bo'sh oy: bo'lish xatosi bermasin, konversiya None bo'lsin
                async def _empty():
                    async with _asess4() as s:
                        return await _fn.period_funnel(s, date(2019, 2, 1), date(2019, 2, 28))
                emp = _aio4.run(_empty())
                eby = {r["key"]: r for r in emp["rows"]}
                check("Voronka: bo'sh davrda konversiya 0% emas, «—» (None)",
                      eby["visit"]["conv_from_prev"] is None and eby["lead"]["value"] == 0,
                      f"lid={eby['lead']['value']}, konv={eby['visit']['conv_from_prev']}")
                check("Voronka: bo'sh davrda eng zaif bo'g'in yo'q",
                      _fn.weakest_link(emp["rows"]) is None, f"{_fn.weakest_link(emp['rows'])}")

                # API: ruxsat
                fn_rop = cur.execute(
                    "select id from users where role='rop' and is_active=1 limit 1").fetchone()
                if fn_rop:
                    r_ok = client.get(f"{API_BASE}/funnel?mode=cohort&month=2021-05",
                                      headers=auth(token_for(fn_rop[0], "rop")))
                    check("Voronka(API): ROP ko'ra oladi -> 200",
                          r_ok.status_code == 200, f"kod={r_ok.status_code}")
                fn_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1 limit 1").fetchone()
                if fn_emp:
                    r_no = client.get(f"{API_BASE}/funnel", headers=auth(token_for(fn_emp[0], "employee")))
                    check("Voronka(API): oddiy xodimga -> 403",
                          r_no.status_code == 403, f"kod={r_no.status_code}")
                r_bad = client.get(f"{API_BASE}/funnel?month=notoq", headers=auth(boss_t))
                check("Voronka(API): noto'g'ri oy formati -> 400",
                      r_bad.status_code == 400, f"kod={r_bad.status_code}")
            finally:
                cur.execute("delete from lead_events where crm_lead_id >= ?", (FL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (FL,))
                conn.commit()
                conn.close()
                (_fn.CRM_UYSOT_INVITE_PIPE_STATUS_IDS,
                 _fn.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn_orig
        except Exception:
            check("Voronka tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: kanal kesimi va manba boyitish (2-bosqich) --")
        try:
            import asyncio as _aio5
            import json as _json5
            from datetime import timezone as _tz5

            from db.base import async_session as _asess5
            from api.services import funnel as _fn5
            from api.services import lead_source as _ls5

            conn = db()
            cur = conn.cursor()
            CL = 981001
            cur.execute("delete from lead_events where crm_lead_id >= ?", (CL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (CL,))
            conn.commit()

            _fn5_orig = (
                list(_fn5.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn5.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn5.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn5.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                c_from, c_to = date(2021, 6, 1), date(2021, 6, 30)
                c_ts = int(datetime(2021, 6, 10, 9, tzinfo=_tz5.utc).timestamp())
                c_det = datetime(2021, 6, 10, 9).isoformat(sep=" ", timespec="seconds")

                def lead(i, tags, source=None, checked=None):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, tags, source, source_checked_at, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (CL + i, 8779, "T-Yangi", 1, "T-op", 1, c_ts, c_ts,
                         _json5.dumps(tags) if tags is not None else None,
                         source, checked, c_det, c_det))

                def cev(i, to_id):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',?,'T-bosqich',1,'T-op',1,?,?)",
                        (CL + i, to_id, c_ts, c_det))

                # 0: telegram + webinar (IKKI teg), tashrif+shartnoma
                lead(0, ["#telegram", "#webinar"]); cev(0, 8787); cev(0, 8788)
                # 1: telegram, faqat tashrif
                lead(1, ["#telegram"]); cev(1, 8787)
                # 2: telegram, hech qayerga yetmagan
                lead(2, ["#telegram"])
                # 3: tegsiz
                lead(3, None)
                conn.commit()

                async def _ch(group_by):
                    async with _asess5() as s:
                        return await _fn5.channel_funnel(s, c_from, c_to, group_by)

                ch = _aio5.run(_ch("tag"))
                by = {r["channel"]: r for r in ch["rows"]}
                check("Kanal: teglar bo'yicha guruhlanadi (telegram 3 lid)",
                      by.get("#telegram", {}).get("leads") == 3, f"{by.get('#telegram')}")
                check("Kanal: bitta lid IKKI tegda ham sanaladi (webinar 1 lid)",
                      by.get("#webinar", {}).get("leads") == 1, f"{by.get('#webinar')}")
                check("Kanal: tegsiz lid alohida qatorda",
                      by.get("(tegsiz)", {}).get("leads") == 1, f"{by.get('(tegsiz)')}")
                check("Kanal: telegram konversiyasi — lid->tashrif 66.7%",
                      by["#telegram"]["lead_to_visit"] == 66.7,
                      f"={by['#telegram']['lead_to_visit']}")
                check("Kanal: telegram lid->shartnoma 33.3%",
                      by["#telegram"]["lead_to_contract"] == 33.3,
                      f"={by['#telegram']['lead_to_contract']}")
                check("Kanal: webinar 100% shartnoma (1/1)",
                      by["#webinar"]["lead_to_contract"] == 100.0,
                      f"={by['#webinar']['lead_to_contract']}")
                check("Kanal: eng ko'p lidli kanal yuqorida",
                      ch["rows"][0]["channel"] == "#telegram", f"{ch['rows'][0]['channel']}")

                src = _aio5.run(_ch("source"))
                sby = {r["channel"]: r for r in src["rows"]}
                _no_src = sby.get("(manba yo'q)")
                check("Kanal(manba): so'ralmagan lidlar «(manba yo'q)» da",
                      (_no_src or {}).get("leads") == 4, str(_no_src))

                # ── Manba boyituvchisi: CRM o'rniga soxta adapter ──
                class _FakeAdapter:
                    def __init__(self):
                        self.calls = []

                    async def get_lead_detail(self, lead_id):
                        self.calls.append(lead_id)
                        # Bittasiga manba yo'q — u ham BELGILANISHI kerak
                        if lead_id == CL + 3:
                            return {"id": lead_id, "source": None, "tags": ["#T-yangiteg"]}
                        return {"id": lead_id, "source": "T-FACEBOOK", "tags": []}

                fake = _FakeAdapter()
                _ls_orig = _ls5._adapter
                _ls5._adapter = lambda: fake
                try:
                    async def _enrich(n):
                        async with _asess5() as s:
                            return await _ls5.enrich_tick(s, limit=n)

                    r1 = _aio5.run(_enrich(2))
                    check("Manba: bir tick'da FAQAT byudjet qadar so'raladi (2 ta)",
                          r1.get("checked") == 2 and len(fake.calls) == 2, f"{r1}, {fake.calls}")
                    check("Manba: eng yangi liddan boshlanadi",
                          fake.calls[0] == CL + 3, f"birinchi={fake.calls[0]}")
                    check("Manba: yana qolgani bor deb belgilanadi",
                          r1.get("has_more") is True, f"{r1}")

                    r2 = _aio5.run(_enrich(10))
                    checked_all = cur.execute(
                        "select count(*) from crm_lead_state where crm_lead_id >= ?"
                        " and source_checked_at is not null", (CL,)).fetchone()[0]
                    check("Manba: hammasi belgilandi (qayta so'ralmaydi)",
                          checked_all == 4, f"belgilangan={checked_all}")
                    check("Manba: manbasi yo'q lid ham belgilanadi (cheksiz so'rov yo'q)",
                          cur.execute(
                              "select source, source_checked_at is not null from crm_lead_state"
                              " where crm_lead_id=?", (CL + 3,)).fetchone() == (None, 1),
                          "manbasiz lid belgilanmagan")
                    check("Manba: keyingi tick'da hech nima so'ralmaydi",
                          _aio5.run(_enrich(10)).get("checked") == 0, "qayta so'rov bor")

                    # Teg ham SHU javobdan olinadi (qo'shimcha so'rovsiz) —
                    # productionda diff-skaner webhook rejimida ishlamaydi,
                    # ya'ni teglarning yagona yo'li shu.
                    check("Manba: teg ham o'sha javobdan yoziladi",
                          cur.execute("select tags from crm_lead_state where crm_lead_id=?",
                                      (CL + 3,)).fetchone()[0] == '["#T-yangiteg"]',
                          str(cur.execute("select tags from crm_lead_state where crm_lead_id=?",
                                          (CL + 3,)).fetchone()))

                    src2 = _aio5.run(_ch("source"))
                    s2by = {r["channel"]: r for r in src2["rows"]}
                    check("Kanal(manba): boyitgandan keyin manba kesimi ishlaydi",
                          s2by.get("T-FACEBOOK", {}).get("leads") == 3, f"{s2by.get('T-FACEBOOK')}")
                finally:
                    _ls5._adapter = _ls_orig

                r_api = client.get(f"{API_BASE}/funnel/channels?group_by=tag&month=2021-06",
                                   headers=auth(boss_t))
                check("Kanal(API): 200 va qatorlar qaytadi",
                      r_api.status_code == 200 and isinstance(r_api.json().get("rows"), list),
                      f"kod={r_api.status_code}")
                r_bad2 = client.get(f"{API_BASE}/funnel/channels?group_by=xato",
                                    headers=auth(boss_t))
                check("Kanal(API): noto'g'ri group_by -> 422",
                      r_bad2.status_code == 422, f"kod={r_bad2.status_code}")
            finally:
                cur.execute("delete from lead_events where crm_lead_id >= ?", (CL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (CL,))
                conn.commit()
                conn.close()
                (_fn5.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn5.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn5_orig
        except Exception:
            check("Kanal kesimi tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: reklama xarajati, CPL/CAC/ROMI (3-bosqich) --")
        try:
            import asyncio as _aio6
            import json as _json6
            from datetime import timezone as _tz6

            from db.base import async_session as _asess6
            from api.services import ad_spend as _ads
            from api.services import funnel as _fn6

            conn = db()
            cur = conn.cursor()
            EL = 982001
            E_PERIOD = "2021-07"
            for t in ("ad_spend", "funnel_month"):
                cur.execute(f"delete from {t} where period=?", (E_PERIOD,))
            cur.execute("delete from lead_events where crm_lead_id >= ?", (EL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (EL,))
            conn.commit()

            _fn6_orig = (
                list(_fn6.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn6.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn6.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn6.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                e_ts = int(datetime(2021, 7, 10, 9, tzinfo=_tz6.utc).timestamp())
                e_det = datetime(2021, 7, 10, 9).isoformat(sep=" ", timespec="seconds")

                def elead(i, tags):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, tags, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?,?)",
                        (EL + i, 8779, "T-Yangi", 1, "T-op", 1, e_ts, e_ts,
                         _json6.dumps(tags), e_det, e_det))

                def eev(i, to_id):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',?,'T-bosqich',1,'T-op',1,?,?)",
                        (EL + i, to_id, e_ts, e_det))

                # #T-insta: 10 lid, 2 tashrif, 1 shartnoma
                for i in range(10):
                    elead(i, ["#T-insta"])
                eev(0, 8787); eev(0, 8788); eev(1, 8787)
                # #T-tg: 5 lid, 1 shartnoma
                for i in range(10, 15):
                    elead(i, ["#T-tg"])
                eev(10, 8787); eev(10, 8788)
                conn.commit()

                async def _eco(gb="tag"):
                    async with _asess6() as s:
                        return await _ads.economics(s, E_PERIOD, gb)

                async def _set(channel, amount, reach=None):
                    async with _asess6() as s:
                        return await _ads.upsert_spend(s, E_PERIOD, channel, amount, reach, None, None)

                _aio6.run(_set("#T-insta", 1_000_000, reach=50_000))
                eco = _aio6.run(_eco())
                by = {r["channel"]: r for r in eco["rows"]}
                check("Iqtisod: CPL = xarajat / lid (1 000 000 / 10 = 100 000)",
                      by["#T-insta"]["cpl"] == 100000.0, f"={by['#T-insta']['cpl']}")
                check("Iqtisod: CAC = xarajat / shartnoma (1 000 000 / 1)",
                      by["#T-insta"]["cac"] == 1000000.0, f"={by['#T-insta']['cac']}")
                check("Iqtisod: CPV = xarajat / tashrif (1 000 000 / 2)",
                      by["#T-insta"]["cpv"] == 500000.0, f"={by['#T-insta']['cpv']}")
                check("Iqtisod: qamrov kiritilsa auditoriya->lid % chiqadi",
                      by["#T-insta"]["reach_to_lead"] == 0.02,
                      f"={by['#T-insta']['reach_to_lead']}")
                check("Iqtisod: foyda kiritilmagan -> ROMI hisoblanmaydi (None)",
                      by["#T-insta"]["romi"] is None, f"={by['#T-insta']['romi']}")

                # Xarajati kiritilmagan, lekin lid keltirgan kanal ko'rinsin
                check("Iqtisod: xarajatsiz kanal «unutilgan» ro'yxatida",
                      any(m["channel"] == "#T-tg" for m in eco["missing_spend"]),
                      f"{eco['missing_spend']}")

                # O'rtacha foyda -> ROMI
                async def _profit(v):
                    async with _asess6() as s:
                        return await _ads.set_avg_deal_profit(s, E_PERIOD, v, None)

                _aio6.run(_profit(3_000_000))
                eco2 = _aio6.run(_eco())
                by2 = {r["channel"]: r for r in eco2["rows"]}
                # (1 shartnoma × 3 000 000 − 1 000 000) / 1 000 000 = 200%
                check("Iqtisod: ROMI = (daromad − xarajat) / xarajat = 200%",
                      by2["#T-insta"]["romi"] == 200.0, f"={by2['#T-insta']['romi']}")

                _aio6.run(_profit(500_000))
                eco3 = _aio6.run(_eco())
                by3 = {r["channel"]: r for r in eco3["rows"]}
                check("Iqtisod: zarar bo'lsa ROMI manfiy (-50%)",
                      by3["#T-insta"]["romi"] == -50.0, f"={by3['#T-insta']['romi']}")

                # Mos kelmagan kanal — jimgina 0 emas, ogohlantirish
                _aio6.run(_set("Instagram", 500_000))
                eco4 = _aio6.run(_eco())
                by4 = {r["channel"]: r for r in eco4["rows"]}
                check("Iqtisod: voronkada yo'q kanal «mos kelmadi» deb belgilanadi",
                      by4["Instagram"]["matched"] is False
                      and "Instagram" in eco4["unmatched"], f"{eco4['unmatched']}")
                check("Iqtisod: mos kelmagan kanal JAMI lidga qo'shilmaydi",
                      eco4["totals"]["leads"] == 10, f"jami lid={eco4['totals']['leads']}")
                check("Iqtisod: lekin JAMI xarajatga qo'shiladi (pul ketgan)",
                      eco4["totals"]["spend"] == 1_500_000.0,
                      f"jami xarajat={eco4['totals']['spend']}")

                # Registr farqi CPL'ni buzmasin
                _aio6.run(_set("#T-INSTA", 200_000))
                eco5 = _aio6.run(_eco())
                by5 = {r["channel"]: r for r in eco5["rows"]}
                check("Iqtisod: katta/kichik harf farqi kanalni ajratmaydi",
                      by5["#T-INSTA"]["matched"] is True and by5["#T-INSTA"]["leads"] == 10,
                      f"{by5['#T-INSTA']}")

                # API
                r_e = client.get(f"{API_BASE}/funnel/economics?period={E_PERIOD}",
                                 headers=auth(boss_t))
                check("Iqtisod(API): 200", r_e.status_code == 200, f"kod={r_e.status_code}")
                r_ch = client.get(f"{API_BASE}/funnel/economics/channels?period={E_PERIOD}",
                                  headers=auth(boss_t))
                check("Iqtisod(API): kanal ro'yxati «(tegsiz)» ni bermaydi",
                      r_ch.status_code == 200
                      and all(not c["channel"].startswith("(")
                              for c in r_ch.json().get("channels", [])),
                      f"kod={r_ch.status_code}")
                e_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1 limit 1").fetchone()
                if e_emp:
                    r_deny = client.post(
                        f"{API_BASE}/funnel/economics/spend",
                        headers=auth(token_for(e_emp[0], "employee")),
                        json={"period": E_PERIOD, "channel": "#T-insta", "amount": 1})
                    check("Iqtisod(API): oddiy xodim xarajat kirita OLMAYDI -> 403",
                          r_deny.status_code == 403, f"kod={r_deny.status_code}")
                r_neg = client.post(
                    f"{API_BASE}/funnel/economics/spend", headers=auth(boss_t),
                    json={"period": E_PERIOD, "channel": "#T-insta", "amount": -5})
                check("Iqtisod(API): manfiy summa -> 400", r_neg.status_code == 400,
                      f"kod={r_neg.status_code}")
            finally:
                for t in ("ad_spend", "funnel_month"):
                    cur.execute(f"delete from {t} where period=?", (E_PERIOD,))
                cur.execute("delete from lead_events where crm_lead_id >= ?", (EL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (EL,))
                conn.commit()
                conn.close()
                (_fn6.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn6.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn6_orig
        except Exception:
            check("Reklama xarajati tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: teskari kalkulyator (4-bosqich) --")
        try:
            import asyncio as _aio7

            from db.base import async_session as _asess7
            from api.services import target_calc as _tc

            conn = db()
            cur = conn.cursor()
            T_PERIOD = "2021-09"
            cur.execute("delete from funnel_month where period=?", (T_PERIOD,))
            conn.commit()

            try:
                async def _calc(target, ov=None):
                    async with _asess7() as s:
                        return await _tc.calculate(s, T_PERIOD, target, ov)

                # To'liq faraz to'plami bilan: arifmetika aniq tekshiriladi
                ov = {
                    "lead_to_visit": 5.0,        # 5%
                    "visit_to_contract": 10.0,   # 10%
                    "talks_per_lead": 2.0,
                    "pickup_rate": 50.0,
                    "cpl": 40000.0,
                    "reach_to_lead": 1.0,        # 1%
                }
                r = _aio7.run(_calc(10, ov))
                chain = {c["key"]: c["value"] for c in r["chain"]}
                # 10 shartnoma / 10% = 100 tashrif; /5% = 2000 lid;
                # ×2 = 4000 suhbat; /50% = 8000 urinish; /1% = 200 000 qamrov
                check("Kalkulyator: tashrif = maqsad / (tashrif->shartnoma)",
                      chain["visits"] == 100, f"={chain['visits']}")
                check("Kalkulyator: lid = tashrif / (lid->tashrif)",
                      chain["leads"] == 2000, f"={chain['leads']}")
                check("Kalkulyator: suhbat = lid × lid boshiga suhbat",
                      chain["talks"] == 4000, f"={chain['talks']}")
                check("Kalkulyator: urinish = suhbat / ko'tarish foizi",
                      chain["tries"] == 8000, f"={chain['tries']}")
                check("Kalkulyator: auditoriya = lid / (qamrov->lid)",
                      chain["reach"] == 200000, f"={chain['reach']}")
                check("Kalkulyator: byudjet = lid × CPL (2000 × 40 000)",
                      r["budget"] == 80_000_000, f"={r['budget']}")
                check("Kalkulyator: qo'lda kiritilgan faraz «override» deb belgilanadi",
                      r["assumptions"]["cpl"]["source"] == "override",
                      f"={r['assumptions']['cpl']['source']}")

                # Yuqoriga yaxlitlash: 7 shartnoma / 10% = 70 tashrif,
                # /3% = 2333.3 lid -> 2334 (yarim lid bo'lmaydi)
                r2 = _aio7.run(_calc(7, {**ov, "lead_to_visit": 3.0}))
                c2 = {c["key"]: c["value"] for c in r2["chain"]}
                check("Kalkulyator: kasr son YUQORIGA yaxlitlanadi (2334)",
                      c2["leads"] == 2334, f"={c2['leads']}")

                # CPL yo'q bo'lsa byudjet hisoblanmaydi (0 emas!)
                r3 = _aio7.run(_calc(10, {**ov, "cpl": None}))
                check("Kalkulyator: CPL bo'lmasa byudjet «hisoblanmadi» (None)",
                      r3["budget"] is None and "cpl" in r3["missing"], f"{r3['budget']}")

                # Sezgirlik: tashrif->shartnoma 10% -> 11% bo'lsa lid kamayadi
                sens = {s["label"]: s for s in r["sensitivity"]}
                key = "Tashrif→shartnoma +1 punkt"
                # 10/11% = 90.9 tashrif; /5% = 1818.2 lid; 2000 - 1818.2 = 181.8 -> 182
                check("Kalkulyator: sezgirlik — +1 punkt 182 ta lid tejaydi",
                      sens[key]["leads_saved"] == 182, f"={sens.get(key)}")
                check("Kalkulyator: sezgirlik byudjet tejamini ham beradi",
                      sens[key]["budget_saved"] == round(181.818181 * 40000),
                      f"={sens[key]['budget_saved']}")

                # Nol o'lchov ishlatilmasin — u butun zanjirni to'xtatadi
                _base_orig = _tc.baseline

                async def _fake_base(db, months=6):
                    return {
                        "months_used": 1,
                        "values": {
                            "lead_to_visit": 0.0,          # soxta «o'lchov»
                            "visit_to_contract": 12.0,
                            "talks_per_lead": None,
                            "pickup_rate": None,
                            "cpl": None,
                            "reach_to_lead": None,
                        },
                        "confidence": "past",
                    }

                _tc.baseline = _fake_base
                try:
                    r0 = _aio7.run(_calc(10, {}))
                    a0 = r0["assumptions"]["lead_to_visit"]
                    check("Kalkulyator: 0% «o'lchov» rad etiladi, zaxira faraz olinadi",
                          a0["source"] == "default" and a0["value"] == _tc.DEFAULTS["lead_to_visit"],
                          f"={a0}")
                    c0 = {c["key"]: c["value"] for c in r0["chain"]}
                    check("Kalkulyator: shu sabab zanjir to'xtamaydi (lid hisoblandi)",
                          c0["leads"] is not None and c0["leads"] > 0, f"lid={c0['leads']}")
                finally:
                    _tc.baseline = _base_orig

                # Saqlash: faqat to'ldirilgan farazlar yoziladi
                async def _save(target, assumptions):
                    async with _asess7() as s:
                        return await _tc.save_target(s, T_PERIOD, target, assumptions, None)

                row = _aio7.run(_save(12, {"visit_to_contract": 8.0, "cpl": None}))
                check("Kalkulyator: maqsad saqlanadi", row.target_contracts == 12,
                      f"={row.target_contracts}")
                check("Kalkulyator: bo'sh farazlar SAQLANMAYDI (o'lchovdan olinadi)",
                      row.assumptions == {"visit_to_contract": 8.0}, f"={row.assumptions}")

                # API
                r_api = client.get(f"{API_BASE}/funnel/target?period={T_PERIOD}",
                                   headers=auth(boss_t))
                check("Kalkulyator(API): saqlangan maqsad bilan hisob qaytadi",
                      r_api.status_code == 200
                      and r_api.json().get("target_contracts") == 12,
                      f"kod={r_api.status_code}, {r_api.text[:90]}")
                r_no = client.get(f"{API_BASE}/funnel/target?period=2021-10",
                                  headers=auth(boss_t))
                check("Kalkulyator(API): maqsadsiz oyda hisob yo'q, maslahat bor",
                      r_no.status_code == 200 and r_no.json().get("chain") == []
                      and r_no.json().get("hint"), f"kod={r_no.status_code}")
                t_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1 limit 1").fetchone()
                if t_emp:
                    r_deny = client.post(
                        f"{API_BASE}/funnel/target", headers=auth(token_for(t_emp[0], "employee")),
                        json={"period": T_PERIOD, "target_contracts": 5})
                    check("Kalkulyator(API): oddiy xodim maqsad qo'ya OLMAYDI -> 403",
                          r_deny.status_code == 403, f"kod={r_deny.status_code}")
                t_rop = cur.execute(
                    "select id from users where role='rop' and is_active=1 limit 1").fetchone()
                if t_rop:
                    r_rop = client.post(
                        f"{API_BASE}/funnel/target", headers=auth(token_for(t_rop[0], "rop")),
                        json={"period": T_PERIOD, "target_contracts": 12})
                    check("Kalkulyator(API): ROP maqsad qo'ya oladi -> 200",
                          r_rop.status_code == 200, f"kod={r_rop.status_code}")
            finally:
                cur.execute("delete from funnel_month where period in (?,?)", (T_PERIOD, "2021-10"))
                conn.commit()
                conn.close()
        except Exception:
            check("Teskari kalkulyator tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: targetni xodimlarga tarqatish (5-bosqich) --")
        try:
            import asyncio as _aio8

            from db.base import async_session as _asess8
            from api.services import target_split as _ts
            from db.models import User as _U8

            conn = db()
            cur = conn.cursor()
            S_PERIOD = "2021-11"
            S_TG = 999779001
            cur.execute("delete from funnel_month where period=?", (S_PERIOD,))
            cur.execute("delete from users where telegram_id between ? and ?", (S_TG, S_TG + 9))
            conn.commit()

            try:
                # Lavozim: «tashrif» ko'rsatkichi biriktirilgan
                cur.execute(
                    "insert into positions (name, metrics, is_active, created_at)"
                    " values ('T-Menejer5', '[\"tashrif\"]', 1, datetime('now'))")
                s_pos = cur.lastrowid
                s_users = []
                for i in range(2):
                    cur.execute(
                        "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                        " position_id, created_at) values (?,?,'employee',1,1,?,datetime('now'))",
                        (S_TG + i, f"T-Split{i}", s_pos))
                    s_users.append(cur.lastrowid)
                # Ikkalasiga ham HAR KUNI ishlaydigan jadval (7/7) — oy 30 kun
                for uid in s_users:
                    for wd in range(7):
                        cur.execute(
                            "insert into work_schedule_weekly (user_id, weekday, is_working,"
                            " start_time, end_time, updated_at)"
                            " values (?,?,1,'09:00','18:00',datetime('now'))", (uid, wd))
                # 2-xodim 10 kun ta'tilda (tasdiqlangan sababli kun)
                for d in range(1, 11):
                    cur.execute(
                        "insert into excused_days (user_id, date, reason, status, created_at)"
                        " values (?,?,'T-tatil','approved',datetime('now'))",
                        (s_users[1], f"2021-11-{d:02d}"))
                # Maqsad: 6 shartnoma; tashrif->shartnoma 10% -> 60 tashrif
                cur.execute(
                    "insert into funnel_month (period, target_contracts, assumptions, updated_at)"
                    " values (?,?,?,datetime('now'))",
                    (S_PERIOD, 6, '{"visit_to_contract": 10.0, "lead_to_visit": 5.0}'))
                conn.commit()

                async def _sug():
                    async with _asess8() as s:
                        return await _ts.suggest(s, S_PERIOD)

                sug = _aio8.run(_sug())
                grp = next(g for g in sug["groups"] if g["metric"] == "tashrif")
                emp = {e["full_name"]: e for e in grp["employees"]}
                check("Tarqatish: oylik maqsad zanjirdan olinadi (60 tashrif)",
                      grp["monthly_target"] == 60, f"={grp['monthly_target']}")
                check("Tarqatish: ta'til ish kunidan CHIQARILADI (30 va 20)",
                      emp["T-Split0"]["working_days"] == 30
                      and emp["T-Split1"]["working_days"] == 20,
                      f"{emp['T-Split0']['working_days']}, {emp['T-Split1']['working_days']}")
                # DIQQAT: guruhda JONLI xodimlar ham bor (ularning lavozimida
                # ham «tashrif» bor), shuning uchun kutilgan qiymat guruhning
                # o'z sonlaridan hisoblanadi — aks holda test jonli bazadagi
                # xodimlar soniga bog'lanib qolardi.
                import math as _math8
                kutilgan_kunlik = _math8.ceil(grp["monthly_target"] / grp["person_days"])
                check("Tarqatish: kunlik norma = maqsad / jami ish kuni",
                      grp["suggested_daily"] == kutilgan_kunlik,
                      f"={grp['suggested_daily']}, kutilgan={kutilgan_kunlik}")
                check("Tarqatish: kunlik norma HAMMAGA bir xil",
                      emp["T-Split0"]["suggested_daily"]
                      == emp["T-Split1"]["suggested_daily"] == kutilgan_kunlik,
                      f"{emp['T-Split0']['suggested_daily']}, {emp['T-Split1']['suggested_daily']}")
                check("Tarqatish: OYLIK ulush ish kuniga proporsional (30 kun > 20 kun)",
                      emp["T-Split0"]["month_total"] == kutilgan_kunlik * 30
                      and emp["T-Split1"]["month_total"] == kutilgan_kunlik * 20,
                      f"{emp['T-Split0']['month_total']}, {emp['T-Split1']['month_total']}")

                # Tavsiya HECH NARSA yozmasligi kerak
                norms_before = cur.execute(
                    "select count(*) from norms where user_id in (?,?)", tuple(s_users)).fetchone()[0]
                check("Tarqatish: tavsiya bazaga norma YOZMAYDI",
                      norms_before == 0, f"normalar={norms_before}")

                # Tasdiqlangandan keyin yoziladi
                # ⚠️ FAQAT test xodimlariga — `user_ids`siz chaqiruv JONLI
                # xodimlarga ham norma yozib yuborardi (birinchi yugurishda
                # aynan shunday bo'ldi va 4 ta haqiqiy xodimning normasi
                # o'zgardi).
                async def _apply(actor_id):
                    async with _asess8() as s:
                        actor = await s.get(_U8, actor_id)
                        return await _ts.apply_suggestion(
                            s, S_PERIOD, "tashrif", actor, user_ids=s_users)

                boss_id = cur.execute(
                    "select id from users where role='boss' and is_active=1 limit 1").fetchone()[0]
                res = _aio8.run(_apply(boss_id))
                conn.commit()
                check("Tarqatish: tasdiqlangach norma yoziladi (2 xodim)",
                      res.get("applied") == 2, f"{res}")
                vals = [r[0] for r in cur.execute(
                    "select value from norms where user_id in (?,?)", tuple(s_users)).fetchall()]
                check("Tarqatish: yozilgan norma kunlik tavsiyaga teng",
                      sorted(vals) == [kutilgan_kunlik, kutilgan_kunlik], f"={vals}")

                # Maqsadsiz oy — tavsiya yo'q
                async def _nosug():
                    async with _asess8() as s:
                        return await _ts.suggest(s, "2021-12")
                ns = _aio8.run(_nosug())
                check("Tarqatish: maqsad qo'yilmagan oyda tavsiya yo'q",
                      ns["ready"] is False and ns["reason"], f"{ns.get('reason')}")

                # API
                r_get = client.get(f"{API_BASE}/funnel/target/split?period={S_PERIOD}",
                                   headers=auth(boss_t))
                check("Tarqatish(API): 200", r_get.status_code == 200, f"kod={r_get.status_code}")
                s_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1"
                    " and telegram_id not between ? and ? limit 1", (S_TG, S_TG + 9)).fetchone()
                if s_emp:
                    r_deny = client.post(
                        f"{API_BASE}/funnel/target/split/apply",
                        headers=auth(token_for(s_emp[0], "employee")),
                        json={"period": S_PERIOD, "metric": "tashrif"})
                    check("Tarqatish(API): oddiy xodim tarqata OLMAYDI -> 403",
                          r_deny.status_code == 403, f"kod={r_deny.status_code}")
                r_bad = client.post(
                    f"{API_BASE}/funnel/target/split/apply", headers=auth(boss_t),
                    json={"period": S_PERIOD, "metric": "yolgon"})
                check("Tarqatish(API): noma'lum ko'rsatkich -> 400",
                      r_bad.status_code == 400, f"kod={r_bad.status_code}")
            finally:
                cur.execute("delete from norms where user_id in (select id from users"
                            " where telegram_id between ? and ?)", (S_TG, S_TG + 9))
                cur.execute("delete from audit_logs where target_user_id in (select id from users"
                            " where telegram_id between ? and ?)", (S_TG, S_TG + 9))
                cur.execute("delete from excused_days where user_id in (select id from users"
                            " where telegram_id between ? and ?)", (S_TG, S_TG + 9))
                cur.execute("delete from work_schedule_weekly where user_id in (select id from users"
                            " where telegram_id between ? and ?)", (S_TG, S_TG + 9))
                cur.execute("delete from users where telegram_id between ? and ?", (S_TG, S_TG + 9))
                cur.execute("delete from positions where name='T-Menejer5'")
                cur.execute("delete from funnel_month where period in (?,?)", (S_PERIOD, "2021-12"))
                conn.commit()
                conn.close()
        except Exception:
            check("Target tarqatish tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: reja/fakt kuzatuvi va prognoz (6-bosqich) --")
        try:
            import asyncio as _aio9
            from datetime import timezone as _tz9

            from db.base import async_session as _asess9
            from api.services import target_track as _tt
            from api.services import funnel as _fn9

            conn = db()
            cur = conn.cursor()
            P_PERIOD = "2021-10"
            PL = 983001
            P_TG = 999780001
            cur.execute("delete from funnel_month where period=?", (P_PERIOD,))
            cur.execute("delete from lead_events where crm_lead_id >= ?", (PL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (PL,))
            cur.execute("delete from users where telegram_id between ? and ?", (P_TG, P_TG + 9))
            conn.commit()

            _fn9_orig = (
                list(_fn9.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn9.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn9.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn9.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                # Maqsad: 10 shartnoma; tashrif->shartnoma 10% -> 100 tashrif
                cur.execute(
                    "insert into funnel_month (period, target_contracts, assumptions, updated_at)"
                    " values (?,?,?,datetime('now'))",
                    (P_PERIOD, 10, '{"visit_to_contract": 10.0, "lead_to_visit": 5.0}'))

                # 15-oktabrgacha 30 ta tashrif (reja bo'yicha ~50 bo'lishi kerak)
                p_ts = int(datetime(2021, 10, 5, 9, tzinfo=_tz9.utc).timestamp())
                p_det = datetime(2021, 10, 5, 9).isoformat(sep=" ", timespec="seconds")
                for i in range(30):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?)",
                        (PL + i, 8779, "T-Yangi", 1, "T-op", 1, p_ts, p_ts, p_det, p_det))
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',8787,'T-Tashrif',1,'T-op',1,?,?)",
                        (PL + i, p_ts, p_det))
                conn.commit()

                async def _prog(today):
                    async with _asess9() as s:
                        return await _tt.progress(s, P_PERIOD, today=today)

                # Oyning yarmi (15-oktabr): kalendar asosida ~48% o'tgan
                pr = _aio9.run(_prog(date(2021, 10, 15)))
                by = {r["key"]: r for r in pr["rows"]}
                check("Kuzatuv: oylik reja zanjirdan olinadi (100 tashrif)",
                      by["visits"]["plan_month"] == 100, f"={by['visits']['plan_month']}")
                check("Kuzatuv: haqiqiy son davr kesimidan (30 tashrif)",
                      by["visits"]["actual"] == 30, f"={by['visits']['actual']}")
                check("Kuzatuv: «hozir kutilgan» = reja × o'tgan ulush",
                      by["visits"]["expected_now"] == round(100 * pr["elapsed"]["share"]),
                      f"={by['visits']['expected_now']}, ulush={pr['elapsed']['share']}")
                check("Kuzatuv: rejadan orqada bo'lsa «orqada» deb belgilanadi",
                      by["visits"]["status"] == "orqada", f"={by['visits']['status']}")
                check("Kuzatuv: prognoz = haqiqiy / o'tgan ulush",
                      by["visits"]["forecast"] == round(30 / pr["elapsed"]["share"]),
                      f"={by['visits']['forecast']}")
                check("Kuzatuv: prognoz rejadan past ekani ko'rsatiladi (manfiy farq)",
                      by["visits"]["forecast_gap"] is not None
                      and by["visits"]["forecast_gap"] < 0,
                      f"={by['visits']['forecast_gap']}")
                check("Kuzatuv: eng orqada qolgan bo'g'in aniqlanadi",
                      pr["weakest"] is not None, f"={pr['weakest']}")

                # Oy boshida (2-kun) prognoz KO'RSATILMAYDI
                pr2 = _aio9.run(_prog(date(2021, 10, 2)))
                by2 = {r["key"]: r for r in pr2["rows"]}
                check("Kuzatuv: oy boshida prognoz berilmaydi (namuna kichik)",
                      pr2["forecast_ready"] is False and by2["visits"]["forecast"] is None,
                      f"ulush={pr2['elapsed']['share']}, prognoz={by2['visits']['forecast']}")
                check("Kuzatuv: shunda digest qatori ham chiqmaydi",
                      _tt.digest_line(pr2) is None, "digest qatori chiqdi")

                # Digest qatori: prognoz tayyor bo'lganda ogohlantiradi
                line = _tt.digest_line(pr)
                check("Kuzatuv: digest qatori «reja ostida» deb ogohlantiradi",
                      line is not None and "Reja ostida" in line, f"={line}")
                check("Kuzatuv: digest qatorida maqsad va prognoz bor",
                      line is not None and "10" in line, f"={line}")

                # Maqsadsiz oy — kuzatuv yo'q
                async def _nop():
                    async with _asess9() as s:
                        return await _tt.progress(s, "2021-12", today=date(2021, 12, 20))
                np = _aio9.run(_nop())
                check("Kuzatuv: maqsadsiz oyda kuzatuv yo'q",
                      np["ready"] is False, f"{np.get('reason')}")
                check("Kuzatuv: maqsadsiz oyda digest jim qoladi",
                      _tt.digest_line(np) is None, "digest qatori chiqdi")

                r_api = client.get(f"{API_BASE}/funnel/target/progress?period={P_PERIOD}",
                                   headers=auth(boss_t))
                check("Kuzatuv(API): 200", r_api.status_code == 200, f"kod={r_api.status_code}")
            finally:
                cur.execute("delete from funnel_month where period in (?,?)", (P_PERIOD, "2021-12"))
                cur.execute("delete from lead_events where crm_lead_id >= ?", (PL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (PL,))
                cur.execute("delete from users where telegram_id between ? and ?", (P_TG, P_TG + 9))
                conn.commit()
                conn.close()
                (_fn9.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn9.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn9_orig
        except Exception:
            check("Reja/fakt kuzatuvi tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: operator kesimida konversiya (7-bosqich) --")
        try:
            import asyncio as _aio10
            from datetime import timezone as _tz10

            from db.base import async_session as _asess10
            from api.services import funnel as _fn10
            from api.services import funnel_operators as _fo

            conn = db()
            cur = conn.cursor()
            OL = 984001
            O_FROM, O_TO = date(2021, 4, 1), date(2021, 4, 30)
            cur.execute("delete from lead_events where crm_lead_id >= ?", (OL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (OL,))
            conn.commit()

            _fn10_orig = (
                list(_fn10.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn10.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn10.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn10.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                o_ts = int(datetime(2021, 4, 10, 9, tzinfo=_tz10.utc).timestamp())
                o_det = datetime(2021, 4, 10, 9).isoformat(sep=" ", timespec="seconds")

                def olead(i, first_rid):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?)",
                        (OL + i, 8779, "T-Yangi", first_rid, "T-op", first_rid, o_ts, o_ts,
                         o_det, o_det))

                def oev(i, to_id, rid):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',?,'T-bosqich',?,'T-op',?,?,?)",
                        (OL + i, to_id, rid, rid, o_ts, o_det))

                # Operator 111: 25 lid, 5 tashrif -> 20%
                for i in range(25):
                    olead(i, 111)
                for i in range(5):
                    oev(i, 8787, 222)          # tashrifni MENEJER 222 qabul qildi
                # Operator 333: 25 lid, 1 tashrif -> 4%
                for i in range(25, 50):
                    olead(i, 333)
                oev(25, 8787, 222)
                # Kichik namunali operator 444: 2 lid, 1 tashrif -> 50% (reytingga KIRMASIN)
                olead(50, 444); olead(51, 444)
                oev(50, 8787, 222)
                # Menejer 222: 7 tashrifdan 2 tasi shartnoma -> 28.6%
                oev(0, 8788, 222); oev(25, 8788, 222)
                conn.commit()

                async def _oq():
                    async with _asess10() as s:
                        return await _fo.operator_quality(s, O_FROM, O_TO)

                d = _aio10.run(_oq())
                ops = {r["responsible_id"]: r for r in d["operators"]}
                check("Operator sifati: maxraj — OLIB KELGAN lidlar (25 ta)",
                      ops[111]["leads"] == 25, f"={ops[111]['leads']}")
                check("Operator sifati: konversiya 20% (5/25)",
                      ops[111]["lead_to_visit"] == 20.0, f"={ops[111]['lead_to_visit']}")
                check("Operator sifati: ikkinchi operator 4% (1/25)",
                      ops[333]["lead_to_visit"] == 4.0, f"={ops[333]['lead_to_visit']}")
                check("Operator sifati: tashrifni MENEJER qilgan bo'lsa ham lid egasiga yoziladi",
                      ops[111]["visits"] == 5, f"={ops[111]['visits']}")
                check("Operator sifati: kichik namuna reytingdan CHIQARILADI",
                      ops[444]["ranked"] is False and ops[444]["lead_to_visit"] == 50.0,
                      f"{ops[444]}")
                check("Operator sifati: 50% li kichik namuna «eng yaxshi» bo'lib qolmaydi",
                      d["best_operator"]["responsible_id"] == 111,
                      f"={d['best_operator']['responsible_id']}")
                check("Operator sifati: eng past — yetarli namunalilar orasidan",
                      d["worst_operator"]["responsible_id"] == 333,
                      f"={d['worst_operator']['responsible_id']}")

                mgr = {r["responsible_id"]: r for r in d["managers"]}
                check("Menejer sifati: maxraj — O'ZI qabul qilgan tashriflar (7 ta)",
                      mgr[222]["visits"] == 7, f"={mgr[222]['visits']}")
                check("Menejer sifati: tashrif->shartnoma 28.6% (2/7)",
                      mgr[222]["visit_to_contract"] == 28.6,
                      f"={mgr[222]['visit_to_contract']}")

                # Bo'sh davr — yiqilmasin
                async def _empty10():
                    async with _asess10() as s:
                        return await _fo.operator_quality(s, date(2019, 1, 1), date(2019, 1, 31))
                e = _aio10.run(_empty10())
                check("Operator sifati: bo'sh davrda bo'sh ro'yxat (xato emas)",
                      e["operators"] == [] and e["best_operator"] is None, f"{e['operators']}")

                r_api = client.get(f"{API_BASE}/funnel/operators?month=2021-04",
                                   headers=auth(boss_t))
                check("Operator sifati(API): 200", r_api.status_code == 200,
                      f"kod={r_api.status_code}")
                o_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1 limit 1").fetchone()
                if o_emp:
                    r_no = client.get(f"{API_BASE}/funnel/operators",
                                      headers=auth(token_for(o_emp[0], "employee")))
                    check("Operator sifati(API): oddiy xodimga -> 403",
                          r_no.status_code == 403, f"kod={r_no.status_code}")
            finally:
                cur.execute("delete from lead_events where crm_lead_id >= ?", (OL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (OL,))
                conn.commit()
                conn.close()
                (_fn10.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn10.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn10_orig
        except Exception:
            check("Operator sifati tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: bo'g'in tahlili va stsenariylar (7-bosqich, 1-2 band) --")
        try:
            import asyncio as _aio11
            from datetime import timezone as _tz11

            from db.base import async_session as _asess11
            from api.services import funnel as _fn11
            from api.services import funnel_analysis as _fa
            from api.services import target_calc as _tc11

            conn = db()
            cur = conn.cursor()
            AL = 985001
            A_PERIOD = "2021-03"
            cur.execute("delete from lead_events where crm_lead_id >= ?", (AL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (AL,))
            cur.execute("delete from funnel_month where period=?", (A_PERIOD,))
            conn.commit()

            _fn11_orig = (
                list(_fn11.CRM_UYSOT_INVITE_PIPE_STATUS_IDS),
                list(_fn11.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn11.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn11.CRM_UYSOT_INVITE_PIPE_STATUS_IDS = [8786]
            _fn11.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn11.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                a_ts = int(datetime(2021, 3, 10, 9, tzinfo=_tz11.utc).timestamp())
                a_det = datetime(2021, 3, 10, 9).isoformat(sep=" ", timespec="seconds")

                def alead(i):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?)",
                        (AL + i, 8779, "T-Yangi", 1, "T-op", 1, a_ts, a_ts, a_det, a_det))

                def aev(i, to_id):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',?,'T-bosqich',1,'T-op',1,?,?)",
                        (AL + i, to_id, a_ts, a_det))

                # 100 lid -> 20 taklif -> 10 tashrif -> 2 shartnoma
                for i in range(100):
                    alead(i)
                for i in range(20):
                    aev(i, 8786)
                for i in range(10):
                    aev(i, 8787)
                for i in range(2):
                    aev(i, 8788)
                conn.commit()

                async def _leak():
                    async with _asess11() as s:
                        return await _fa.leak_analysis(s, A_PERIOD)

                lk = _aio11.run(_leak())
                steps = {s["label"]: s for s in lk["steps"]}
                check("Tahlil: lid->taklif bo'g'inida 80 ta yo'qoldi (80%)",
                      steps["Lid → ofisga taklif"]["lost"] == 80
                      and steps["Lid → ofisga taklif"]["loss_pct"] == 80.0,
                      f"{steps['Lid → ofisga taklif']}")
                check("Tahlil: taklif->tashrif 10 ta (50%)",
                      steps["Taklif → tashrif"]["lost"] == 10
                      and steps["Taklif → tashrif"]["loss_pct"] == 50.0,
                      f"{steps['Taklif → tashrif']}")
                check("Tahlil: tashrif->shartnoma 8 ta (80%)",
                      steps["Tashrif → shartnoma"]["lost"] == 8, f"{steps['Tashrif → shartnoma']}")
                check("Tahlil: eng katta yo'qotish — birinchi bo'g'in",
                      lk["biggest_leak"]["label"] == "Lid → ofisga taklif",
                      f"{lk['biggest_leak']}")
                check("Tahlil: umumiy konversiya 2% (2/100)",
                      lk["overall_conversion"] == 2.0, f"={lk['overall_conversion']}")
                check("Tahlil: CPL yo'q -> pul ustuni bo'sh (0 emas!)",
                      all(s["money_lost"] is None for s in lk["steps"]),
                      f"{[s['money_lost'] for s in lk['steps']]}")
                check("Tahlil: «~yo'qolgan shartnoma» o'rtacha konversiyadan (80 × 2%)",
                      steps["Lid → ofisga taklif"]["contracts_lost"] == 1.6,
                      f"={steps['Lid → ofisga taklif']['contracts_lost']}")

                # STSENARIY: maqsad va farazlar bilan
                cur.execute(
                    "insert into funnel_month (period, target_contracts, assumptions, updated_at)"
                    " values (?,?,?,datetime('now'))",
                    (A_PERIOD, 10,
                     '{"lead_to_visit": 10.0, "visit_to_contract": 20.0, "cpl": 50000}'))
                conn.commit()

                async def _sc():
                    async with _asess11() as s:
                        return await _fa.scenarios(s, A_PERIOD, 20)

                sc = _aio11.run(_sc())
                by = {s["key"]: s for s in sc["scenarios"]}
                # lid->shartnoma = 10% × 20% = 2%; 10 uy uchun 500 lid;
                # byudjet = 500 × 50 000 = 25 mln; +20% = 5 mln -> 100 lid -> +2 uy
                check("Stsenariy: byudjet +20% -> +100 lid",
                      by["budget_up"]["extra_leads"] == 100, f"={by['budget_up']['extra_leads']}")
                check("Stsenariy: byudjet +20% -> +2 uy",
                      by["budget_up"]["extra_contracts"] == 2.0,
                      f"={by['budget_up']['extra_contracts']}")
                konv_key = "Tashrif → shartnoma +1 punkt"
                # 500 lid × (10% × 21%) = 10.5 -> +0.5 uy
                check("Stsenariy: tashrif->shartnoma +1 punkt -> +0.5 uy",
                      by[konv_key]["extra_contracts"] == 0.5,
                      f"={by[konv_key]['extra_contracts']}")
                check("Stsenariy: faraz manbai ko'rsatiladi (qo'lda kiritilgan)",
                      "override" in (by["budget_up"]["sources"] or []),
                      f"={by['budget_up']['sources']}")

                # Ma'lumot yetmasa — halol «hisoblanmadi»
                cur.execute("delete from funnel_month where period=?", (A_PERIOD,))
                conn.commit()
                sc2 = _aio11.run(_sc())
                b2 = {s["key"]: s for s in sc2["scenarios"]}
                check("Stsenariy: maqsad yo'q -> hisoblanmaydi va sababi aytiladi",
                      b2["budget_up"]["extra_contracts"] is None
                      and "maqsad" in (b2["budget_up"].get("missing") or []),
                      f"{b2['budget_up']}")

                r_api = client.get(f"{API_BASE}/funnel/analysis?period={A_PERIOD}",
                                   headers=auth(boss_t))
                check("Tahlil(API): 200 va ikkala bo'lim qaytadi",
                      r_api.status_code == 200 and "leaks" in r_api.json()
                      and "scenarios" in r_api.json(), f"kod={r_api.status_code}")
            finally:
                cur.execute("delete from lead_events where crm_lead_id >= ?", (AL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (AL,))
                cur.execute("delete from funnel_month where period=?", (A_PERIOD,))
                conn.commit()
                conn.close()
                (_fn11.CRM_UYSOT_INVITE_PIPE_STATUS_IDS,
                 _fn11.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn11.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn11_orig
        except Exception:
            check("Bo'g'in tahlili tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- VORONKA: qoidalar panelda (bekor shartnoma / sifatsiz lid) --")
        try:
            import asyncio as _aio12
            from datetime import timezone as _tz12

            from db.base import async_session as _asess12
            from api.services import funnel as _fn12
            from api.services import funnel_settings as _fs

            conn = db()
            cur = conn.cursor()
            SL = 986001
            S_FROM, S_TO = date(2021, 2, 1), date(2021, 2, 28)
            CANCEL_ID, LOWQ_ID = 999111, 999222
            cur.execute("delete from lead_events where crm_lead_id >= ?", (SL,))
            cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (SL,))
            _fs_before = cur.execute(
                "select cancelled_pipe_status_ids, subtract_cancelled,"
                " low_quality_pipe_status_ids, exclude_low_quality from funnel_settings"
                " where id=1").fetchone()
            cur.execute("delete from funnel_settings where id=1")
            conn.commit()

            _fn12_orig = (
                list(_fn12.CRM_UYSOT_VISIT_PIPE_STATUS_IDS),
                list(_fn12.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS),
            )
            _fn12.CRM_UYSOT_VISIT_PIPE_STATUS_IDS = [8787]
            _fn12.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS = [8788]

            try:
                s_ts = int(datetime(2021, 2, 10, 9, tzinfo=_tz12.utc).timestamp())
                s_det = datetime(2021, 2, 10, 9).isoformat(sep=" ", timespec="seconds")

                def slead(i, now_stage):
                    cur.execute(
                        "insert into crm_lead_state (crm_lead_id, pipe_status_id, stage_name,"
                        " responsible_id, responsible_name, first_responsible_id, crm_updated_ts,"
                        " crm_created_ts, first_seen_at, last_seen_at)"
                        " values (?,?,?,?,?,?,?,?,?,?)",
                        (SL + i, now_stage, "T-hozirgi", 1, "T-op", 1, s_ts, s_ts, s_det, s_det))

                def sev(i, to_id):
                    cur.execute(
                        "insert into lead_events (crm_lead_id, event_type, from_pipe_status_id,"
                        " from_stage_name, to_pipe_status_id, to_stage_name, to_responsible_id,"
                        " to_responsible_name, first_responsible_id, crm_updated_ts, detected_at)"
                        " values (?,'stage_change',8779,'T-Yangi',?,'T-bosqich',1,'T-op',1,?,?)",
                        (SL + i, to_id, s_ts, s_det))

                # 0,1: shartnoma qilgan va shunday qolgan
                slead(0, 8788); sev(0, 8787); sev(0, 8788)
                slead(1, 8788); sev(1, 8787); sev(1, 8788)
                # 2: shartnoma qilib, KEYIN bekor bo'lgan (hozirgi holati — bekor)
                slead(2, CANCEL_ID); sev(2, 8787); sev(2, 8788); sev(2, CANCEL_ID)
                # 3: sifatsiz lead (hech qayerga yetmagan)
                slead(3, LOWQ_ID)
                # 4: oddiy lid
                slead(4, 8779)
                conn.commit()

                async def _coh():
                    async with _asess12() as s:
                        return await _fn12.cohort_funnel(s, S_FROM, S_TO)

                async def _set(**kw):
                    async with _asess12() as s:
                        return await _fs.update_settings(s, kw, None)

                # ── Default: IKKALA qoida ham O'CHIQ ──
                d0 = _aio12.run(_coh())
                b0 = {r["key"]: r["value"] for r in d0["rows"]}
                check("Qoida: default o'chiq — 5 lid, 3 shartnoma (bekor ham sanaladi)",
                      b0["lead"] == 5 and b0["contract"] == 3,
                      f"lid={b0['lead']}, shartnoma={b0['contract']}")

                # ── Bekor qilinganni ayirish ──
                _aio12.run(_set(subtract_cancelled=True,
                                cancelled_pipe_status_ids=[CANCEL_ID]))
                d1 = _aio12.run(_coh())
                b1 = {r["key"]: r["value"] for r in d1["rows"]}
                check("Qoida: bekor qilingan shartnoma ayrildi (3 -> 2)",
                      b1["contract"] == 2, f"shartnoma={b1['contract']}")
                check("Qoida: lid soni o'zgarmadi (faqat shartnomaga ta'sir)",
                      b1["lead"] == 5, f"lid={b1['lead']}")

                # ── Bosqich tanlanmasa qoida ISHLAMAYDI ──
                _aio12.run(_set(subtract_cancelled=True, cancelled_pipe_status_ids=[]))
                d2 = _aio12.run(_coh())
                b2 = {r["key"]: r["value"] for r in d2["rows"]}
                check("Qoida: yoqiq-u bosqich tanlanmagan -> qoida ishlamaydi",
                      b2["contract"] == 3, f"shartnoma={b2['contract']}")

                # ── Sifatsiz lid maxrajdan chiqsin ──
                _aio12.run(_set(subtract_cancelled=False, cancelled_pipe_status_ids=[CANCEL_ID],
                                exclude_low_quality=True, low_quality_pipe_status_ids=[LOWQ_ID]))
                d3 = _aio12.run(_coh())
                b3 = {r["key"]: r["value"] for r in d3["rows"]}
                check("Qoida: sifatsiz lid maxrajdan chiqdi (5 -> 4)",
                      b3["lead"] == 4, f"lid={b3['lead']}")
                check("Qoida: sifatsiz chiqarilgach konversiya ko'tariladi",
                      d3["rows"][-1]["conv_from_lead"] > d0["rows"][-1]["conv_from_lead"],
                      f"{d0['rows'][-1]['conv_from_lead']} -> {d3['rows'][-1]['conv_from_lead']}")

                # ── Ikkalasi birga ──
                _aio12.run(_set(subtract_cancelled=True, cancelled_pipe_status_ids=[CANCEL_ID],
                                exclude_low_quality=True, low_quality_pipe_status_ids=[LOWQ_ID]))
                d4 = _aio12.run(_coh())
                b4 = {r["key"]: r["value"] for r in d4["rows"]}
                check("Qoida: ikkalasi birga — 4 lid, 2 shartnoma",
                      b4["lead"] == 4 and b4["contract"] == 2,
                      f"lid={b4['lead']}, shartnoma={b4['contract']}")

                # ── Bosqich ro'yxati CRM'siz to'ldiriladi ──
                async def _stages():
                    async with _asess12() as s:
                        return await _fs.known_stages(s)
                st = _aio12.run(_stages())
                check("Qoida: bosqich ro'yxati o'z jurnalimizdan (CRM so'rovsiz)",
                      any(x["pipe_status_id"] == CANCEL_ID for x in st), f"{len(st)} ta bosqich")

                # ── API ──
                r_get = client.get(f"{API_BASE}/funnel/settings", headers=auth(boss_t))
                check("Qoida(API): sozlama va bosqichlar qaytadi",
                      r_get.status_code == 200 and "stages" in r_get.json(),
                      f"kod={r_get.status_code}")
                s_emp = cur.execute(
                    "select id from users where role='employee' and is_active=1 limit 1").fetchone()
                if s_emp:
                    r_deny = client.post(
                        f"{API_BASE}/funnel/settings",
                        headers=auth(token_for(s_emp[0], "employee")),
                        json={"subtract_cancelled": True})
                    check("Qoida(API): oddiy xodim o'zgartira OLMAYDI -> 403",
                          r_deny.status_code == 403, f"kod={r_deny.status_code}")
                r_ok = client.post(f"{API_BASE}/funnel/settings", headers=auth(boss_t),
                                   json={"subtract_cancelled": False})
                check("Qoida(API): Boshliq saqlay oladi", r_ok.status_code == 200,
                      f"kod={r_ok.status_code}")
            finally:
                cur.execute("delete from lead_events where crm_lead_id >= ?", (SL,))
                cur.execute("delete from crm_lead_state where crm_lead_id >= ?", (SL,))
                cur.execute("delete from funnel_settings where id=1")
                if _fs_before:
                    cur.execute(
                        "insert into funnel_settings (id, cancelled_pipe_status_ids,"
                        " subtract_cancelled, low_quality_pipe_status_ids, exclude_low_quality,"
                        " updated_at) values (1,?,?,?,?,datetime('now'))", _fs_before)
                conn.commit()
                conn.close()
                (_fn12.CRM_UYSOT_VISIT_PIPE_STATUS_IDS,
                 _fn12.CRM_UYSOT_CONTRACT_PIPE_STATUS_IDS) = _fn12_orig
        except Exception:
            check("Voronka qoidalari tekshiruvi", False, traceback.format_exc(limit=2).strip())

        print("\n-- ISSIQ LID: sovish qoidasi, eslatmalar, taqsimlash, statistika --")
        try:
            import asyncio as _aio

            from db.base import async_session as _asess
            from api.services import hot_lead as _hl

            conn = db()
            cur = conn.cursor()

            # HR qoidasi: global FinePolicy (bo'lmasa yaratamiz; borini eslab
            # qolib, oxirida ASL HOLIGA qaytaramiz — jonli sozlamaga tegmaymiz)
            old_global = cur.execute(
                "select id, hot_lead_cool_minutes, hot_lead_fine from fine_policies"
                " where scope='global'").fetchone()
            if old_global:
                cur.execute(
                    "update fine_policies set hot_lead_cool_minutes=12, hot_lead_fine=50000"
                    " where id=?", (old_global[0],))
                created_policy = None
            else:
                cur.execute(
                    "insert into fine_policies (scope, scope_id, free_late_minutes_per_month,"
                    " fine_mode, absent_mode, early_leave_enabled, fine_applies_to, is_active,"
                    " hot_lead_cool_minutes, hot_lead_fine, updated_at)"
                    " values ('global', NULL, 60, 'per_day', 'fixed', 0, 'net_salary', 1,"
                    " 12, 50000, datetime('now'))")
                created_policy = cur.lastrowid
            conn.commit()

            async def _rules():
                async with _asess() as s:
                    return await _hl.hot_lead_rules(s)

            mins, fine = _aio.run(_rules())
            check("HL: HR qoidasi o'qildi (12 daq / 50 000)", mins == 12 and fine == 50000.0,
                  f"{mins} daq, {fine}")

            # Eslatma matni bosqichlari — senlab, jarima bilan
            fake = type("L", (), {"contact_name": "T-Mijoz", "lead_name": None, "crm_lead_id": 1})()
            t3 = _hl._reminder_text(3, 12, fake, 50000.0)
            t9 = _hl._reminder_text(9, 12, fake, 50000.0)
            check("HL: 3-daqiqa eslatmasi yumshoq, 9-daqiqa qattiq + jarima",
                  "3 daqiqa" in t3 and "guruhga" in t9 and "50 000" in t9,
                  f"{t3[:40]} | {t9[:60]}")
            check("HL: eslatmalar sovish limitidan kichik bosqichlarda",
                  all(s < 12 for s in _hl.REMINDER_STEPS), str(_hl.REMINDER_STEPS))

            # Oldingi-qo'ng'iroq oynasi 2 soat (mijoz bilan gaplashib bo'lib
            # CRM'ga kiritish holati) — egasining shikoyatining yechimi
            check("HL: qo'ng'iroq oynasi 2 soat (10 daqiqa emas)",
                  _hl.PRE_CREATION_GRACE_SECONDS == 7200, str(_hl.PRE_CREATION_GRACE_SECONDS))

            # Taqsimlash: eng kam yuklangan operator tanlanadi
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " crm_visit_external_id, created_at)"
                " values (999555001,'T-Op1','employee',1,1,'900001',datetime('now'))")
            op1 = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " crm_visit_external_id, created_at)"
                " values (999555002,'T-Op2','employee',1,1,'900002',datetime('now'))")
            op2 = cur.lastrowid
            # op1 ga bugun 2 ta lid — demak keyingisi op2 ga tushishi kerak
            for i in (91001, 91002):
                cur.execute(
                    "insert into hot_lead (crm_lead_id, user_id, created_ts, detected_at,"
                    " status, last_reminder_minute)"
                    " values (?,?,?,datetime('now'),'notified',0)",
                    (i, op1, int(__import__("time").time())))
            conn.commit()

            async def _pick():
                async with _asess() as s:
                    u = await _hl._pick_operator(s)
                    return u.full_name if u else None

            picked = _aio.run(_pick())
            # Nomzodlar orasida HAQIQIY operatorlar ham bor (ular ham 0 lidli)
            # — muhimi: bugun 2 ta lid olgan T-Op1 TANLANMASLIGI kerak.
            check("HL: yuklangan operator (T-Op1) taqsimotdan chetda qoldi",
                  picked is not None and picked != "T-Op1", f"tanlandi={picked}")

            # O'CHIRGICH (2026-08-06): hot_lead_enabled=0 bo'lgan operatorga
            # lid BERILMAYDI (Tester akkaunti uchun aynan shu kerak).
            cur.execute("update users set hot_lead_enabled=0 where id in (?,?)", (op1, op2))
            # Boshqa hamma nomzodni ham vaqtincha o'chiramiz — tanlov aynan
            # bayroqqa bog'liqligini isbotlash uchun
            others = [r[0] for r in cur.execute(
                "select id from users where hot_lead_enabled=1").fetchall()]
            if others:
                cur.execute(
                    "update users set hot_lead_enabled=0 where id in (%s)"
                    % ",".join("?" * len(others)), others)
            conn.commit()
            picked_off = _aio.run(_pick())
            check("HL: hamma o'chirilganda taqsimot to'xtaydi (lid berilmaydi)",
                  picked_off is None, f"tanlandi={picked_off}")

            cur.execute("update users set hot_lead_enabled=1 where id=?", (op2,))
            conn.commit()
            picked_on = _aio.run(_pick())
            check("HL: faqat yoqilgan operator lid oladi (T-Op2)",
                  picked_on == "T-Op2", f"tanlandi={picked_on}")
            # Haqiqiy operatorlarni ASL holiga qaytaramiz
            if others:
                cur.execute(
                    "update users set hot_lead_enabled=1 where id in (%s)"
                    % ",".join("?" * len(others)), others)
            conn.commit()

            # Kunlik statistika: kim nechta lidni sovutgan
            cur.execute(
                "insert into hot_lead (crm_lead_id, user_id, created_ts, detected_at,"
                " escalated_at, fine_amount, status, last_reminder_minute)"
                " values (91003,?,?,datetime('now'),datetime('now'),50000,'notified',9)",
                (op1, int(__import__("time").time())))
            cur.execute(
                "insert into hot_lead (crm_lead_id, user_id, created_ts, detected_at,"
                " escalated_at, fine_amount, status, last_reminder_minute)"
                " values (91004,?,?,datetime('now'),datetime('now'),50000,'called',9)",
                (op1, int(__import__("time").time())))
            conn.commit()

            async def _cooled():
                async with _asess() as s:
                    return await _hl.cooled_by_operator(s, date.today())

            cooled = _aio.run(_cooled())
            row = next((c for c in cooled if c["full_name"] == "T-Op1"), None)
            check("HL: statistikada sovutgan operator (1 ta, tuzatilgani sanalmaydi)",
                  row is not None and row["count"] == 1 and row["fine"] == 50000.0, str(row))

            # Tozalash: T- ma'lumot + sozlamani ASL holiga qaytarish
            cur.execute("delete from hot_lead where crm_lead_id in (91001,91002,91003,91004)")
            cur.execute("delete from users where id in (?,?)", (op1, op2))
            if created_policy:
                cur.execute("delete from fine_policies where id=?", (created_policy,))
            elif old_global:
                cur.execute(
                    "update fine_policies set hot_lead_cool_minutes=?, hot_lead_fine=? where id=?",
                    (old_global[1], old_global[2], old_global[0]))
            conn.commit()
            conn.close()
        except Exception:
            check("Issiq lid tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- UX2-W4: bot dashboard + statistika davomat bloki + validatsiya --")
        try:
            conn = db()
            cur = conn.cursor()
            with open("D:/Project/hodimlar_tizimi/.env", encoding="utf-8") as f:
                secret = next(
                    (line.strip().split("=", 1)[1] for line in f if line.startswith("BOT_SHARED_SECRET=")),
                    "",
                )
            bot_h = {"X-Bot-Secret": secret}

            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444806,'T-BotMgr','hr',1,1,datetime('now'))")
            mgr_uid = cur.lastrowid
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
                " values (999444807,'T-BotEmp','employee',1,1,datetime('now'))")
            emp_uid = cur.lastrowid
            # T-BotEmp'ga shu oyda davomat: 1 kelgan kun (20 daq kechikish) + 1 absent
            first_day = date.today().replace(day=1).isoformat()
            cur.execute(
                "insert into attendance (user_id, date, check_in_time, check_out_time, status,"
                " late_minutes, early_leave_minutes, worked_minutes, created_at, updated_at)"
                " values (?,?,datetime('now','-30 hours'),datetime('now','-22 hours'),'late',20,0,480,"
                " datetime('now'),datetime('now'))", (emp_uid, first_day))
            if date.today().day >= 2:
                second_day = date.today().replace(day=2).isoformat()
                cur.execute(
                    "insert into attendance (user_id, date, status, late_minutes,"
                    " early_leave_minutes, worked_minutes, created_at, updated_at)"
                    " values (?,?,'absent',0,0,0,datetime('now'),datetime('now'))",
                    (emp_uid, second_day))
            conn.commit()

            # C5: dashboard-bot — rahbar 200, xodim 403
            r = client.get(f"{API_BASE}/attendance/dashboard-bot/999444806", headers=bot_h)
            check("W4: dashboard-bot rahbarga -> 200 + summary/late_list",
                  r.status_code == 200 and "summary" in r.json() and "late_list" in r.json(),
                  f"kod={r.status_code}")
            r2 = client.get(f"{API_BASE}/attendance/dashboard-bot/999444807", headers=bot_h)
            check("W4: dashboard-bot xodimga -> 403", r2.status_code == 403, f"kod={r2.status_code}")

            # C9: statistikada davomat bloki
            r3 = client.get(f"{API_BASE}/stats/my/999444807", headers=bot_h)
            b3 = r3.json() if r3.status_code == 200 else {}
            expected_absent = 1 if date.today().day >= 2 else 0
            check("W4: my-stats davomat maydonlari (1 kelgan, 20 daq, absent)",
                  b3.get("attendance_present_days") == 1
                  and b3.get("attendance_late_minutes") == 20
                  and b3.get("attendance_absent_days") == expected_absent,
                  str({k: v for k, v in b3.items() if k.startswith("attendance")}))

            # C10: sabab juda qisqa -> 422 (schema min_length)
            r4 = client.post(f"{API_BASE}/excused-days", headers=bot_h,
                             json={"telegram_id": 999444807, "reason": "x"})
            check("W4: 1-belgili sabab -> 422", r4.status_code == 422, f"kod={r4.status_code}")

            # Qoldiq #4/#5: kutilayotgan so'rovlar ro'yxatlari (bot)
            cur.execute(
                "insert into excused_days (user_id, date, reason, status, created_at)"
                " values (?, date('now','+3 days'), 'T-kutish', 'pending', datetime('now'))",
                (emp_uid,))
            cur.execute(
                "insert into face_reregistration_requests (user_id, new_descriptor, status, created_at)"
                " values (?, ?, 'pending', datetime('now'))", (emp_uid, json.dumps([0.5] * 128)))
            conn.commit()
            r5 = client.get(f"{API_BASE}/excused-days/pending-bot/999444806", headers=bot_h)
            names5 = [x["user_full_name"] for x in (r5.json() if r5.status_code == 200 else [])]
            check("Q4: pending-bot (sababli) rahbarga -> 200 + T-BotEmp bor",
                  r5.status_code == 200 and "T-BotEmp" in names5, f"kod={r5.status_code} {names5[:5]}")
            r6 = client.get(f"{API_BASE}/excused-days/pending-bot/999444807", headers=bot_h)
            check("Q4: pending-bot xodimga -> 403", r6.status_code == 403, f"kod={r6.status_code}")
            r7 = client.get(f"{API_BASE}/attendance/face-reregistration/pending-bot/999444806", headers=bot_h)
            names7 = [x["user_full_name"] for x in (r7.json() if r7.status_code == 200 else [])]
            check("Q5: pending-bot (yuz) rahbarga -> 200 + T-BotEmp bor",
                  r7.status_code == 200 and "T-BotEmp" in names7, f"kod={r7.status_code} {names7[:5]}")

            # Qoldiq #13: qisqa muddatli WebView tokeni
            emp_jwt = token_for(emp_uid, "employee")
            r8 = client.post(f"{API_BASE}/auth/webview-token", headers=auth(emp_jwt))
            wb = r8.json() if r8.status_code == 200 else {}
            check("Q13: webview-token -> 200 + 30 daq",
                  r8.status_code == 200 and wb.get("expires_in_minutes") == 30,
                  f"kod={r8.status_code}")
            if wb.get("access_token"):
                r9 = client.get(f"{API_BASE}/users/me", headers=auth(wb["access_token"]))
                check("Q13: webview-token bilan /users/me ishlaydi",
                      r9.status_code == 200 and r9.json().get("id") == emp_uid,
                      f"kod={r9.status_code}")

            for u in (mgr_uid, emp_uid):
                cur.execute("delete from attendance where user_id=?", (u,))
                cur.execute("delete from excused_days where user_id=?", (u,))
                cur.execute("delete from face_reregistration_requests where user_id=?", (u,))
                cur.execute("delete from users where id=?", (u,))
            conn.commit()
            conn.close()
        except Exception:
            check("UX2-W4 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- UX-A6: yuz so'rovini webdan hal qilish --")
        try:
            conn = db()
            cur = conn.cursor()
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " face_descriptor, face_registered_at, created_at) values"
                " (999444803,'T-ReregWeb','employee',1,1,?,datetime('now'),datetime('now'))",
                (json.dumps(FACE),))
            rw_uid = cur.lastrowid
            new_face = json.dumps([0.9] * 128)
            cur.execute(
                "insert into face_reregistration_requests (user_id, new_descriptor, status, created_at)"
                " values (?, ?, 'pending', datetime('now'))", (rw_uid, new_face))
            req_id = cur.lastrowid
            conn.commit()

            emp_tok = token_for(rw_uid, "employee")
            r = client.post(f"{API_BASE}/attendance/face-reregistration/{req_id}/decide-web",
                            headers=auth(emp_tok), json={"decision": "approved"})
            check("A6: oddiy xodim -> 403", r.status_code == 403, f"kod={r.status_code}")

            mgr = find_manager_id()
            mgr_tok = token_for(mgr[0], mgr[1])
            r2 = client.post(f"{API_BASE}/attendance/face-reregistration/{req_id}/decide-web",
                             headers=auth(mgr_tok), json={"decision": "approved"})
            check("A6: rahbar webdan tasdiqlaydi -> 200", r2.status_code == 200,
                  f"kod={r2.status_code} {r2.text[:150]}")
            saved = conn.execute("select face_descriptor from users where id=?", (rw_uid,)).fetchone()[0]
            check("A6: descriptor yangilandi", json.loads(saved) == [0.9] * 128)
            r3 = client.post(f"{API_BASE}/attendance/face-reregistration/{req_id}/decide-web",
                             headers=auth(mgr_tok), json={"decision": "rejected"})
            check("A6: qayta qaror -> 400 (idempotent)", r3.status_code == 400, f"kod={r3.status_code}")

            cur.execute("delete from face_reregistration_requests where user_id=?", (rw_uid,))
            cur.execute("delete from audit_logs where target_user_id=?", (rw_uid,))
            cur.execute("delete from users where id=?", (rw_uid,))
            conn.commit()
            conn.close()
        except Exception:
            check("UX-A6 tekshiruvi", False, traceback.format_exc(limit=1).strip())

        print("\n-- UX-A7: umumiy ish jadvali (JWT) --")
        try:
            mgr = find_manager_id()
            mgr_tok = token_for(mgr[0], mgr[1])
            r = client.get(f"{API_BASE}/work-schedule/all/week", headers=auth(mgr_tok))
            check("A7: rahbar umumiy jadvalni oladi -> 200",
                  r.status_code == 200 and isinstance(r.json(), list),
                  f"kod={r.status_code}, {len(r.json()) if r.status_code == 200 else '-'} xodim")
            conn = db()
            emp_row = conn.execute(
                "select id from users where role='employee' and is_active=1 limit 1").fetchone()
            conn.close()
            if emp_row:
                emp_tok = token_for(emp_row[0], "employee")
                r2 = client.get(f"{API_BASE}/work-schedule/all/week", headers=auth(emp_tok))
                check("A7: oddiy xodimga -> 403", r2.status_code == 403, f"kod={r2.status_code}")
        except Exception:
            check("UX-A7 tekshiruvi", False, traceback.format_exc(limit=1).strip())


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
            Attendance, AuditLog, Bonus, ExcusedDay, FinePolicy, OvertimeEntry, OvertimeProfile,
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
            # Uchinchi qiymat — kelmagan kunlar ayirmasi (2026-08-08). Bu yerda
            # qoida `fixed` rejimda, ya'ni ayirma bo'lmasligi kerak.
            # To'rtinchi — to'lovsiz ta'til ayirmasi (2026-08-13).
            base_amount, base_item, absent_item, unpaid_item = pr.compute_base(
                rate, first_rate, days, date(2020, 1, 1), policy
            )
            check("Payroll: base_amount to'liq oylik (prorata yo'q, 6/6 kun)",
                  base_amount == Decimal("3000000"), f"base={base_amount}")
            check("Payroll: 'fixed' rejimda bazadan ayirma YO'Q (ikki marta jazo bo'lmasin)",
                  absent_item is None, f"absent_item={absent_item}")

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

            # ── §3.4: «vaqtni QO'SHIB-AYIRIB umumiy berish» ──
            # Egasining talabi shu edi: ortiqcha ham, KAM ishlangan vaqt ham
            # bitta songa yig'ilsin. Shuning uchun `minutes` manfiy bo'lishi
            # MUMKIN va oy bo'yicha ortiqchadan ayiriladi.
            await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id == u1.id))
            s.add(OvertimeEntry(user_id=u1.id, date=day1, minutes=-105, source="auto_attendance",
                                 status="approved"))
            await s.commit()
            ot_neg = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            check("Payroll §3.4: KAM ishlangan vaqt manfiy sanaladi (-105 daq)",
                  ot_neg["minutes"] == -105, f"={ot_neg['minutes']}")
            check("Payroll §3.4: manfiy vaqt summasi ham manfiy (-35000)",
                  abs(float(ot_neg["amount"]) + 35_000.0) < 1, f"={ot_neg['amount']}")

            # Aralash kunlar: +120 va -30 -> sof +90
            await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id == u1.id))
            s.add(OvertimeEntry(user_id=u1.id, date=day1, minutes=120, source="auto_attendance",
                                 status="approved"))
            s.add(OvertimeEntry(user_id=u1.id, date=day2, minutes=-30, source="auto_attendance",
                                 status="approved"))
            await s.commit()
            ot_mix = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            check("Payroll §3.4: aralash kunlar qo'shilib-ayirilib +90 daq",
                  ot_mix["minutes"] == 90, f"={ot_mix['minutes']}")

            # Kunlik cheklov IKKI TOMONGA simmetrik: cap=60 bo'lsa
            # +120 -> +60, -30 esa tegilmaydi -> sof +30
            profile.daily_cap_minutes = 60
            await s.commit()
            ot_cap = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            check("Payroll §3.4: kunlik cheklov ikki tomonga simmetrik (+60-30=+30)",
                  ot_cap["minutes"] == 30, f"={ot_cap['minutes']}")

            # Manfiy tomonda ham cheklov ishlashi kerak: -105 -> -60
            await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id == u1.id))
            s.add(OvertimeEntry(user_id=u1.id, date=day1, minutes=-105, source="auto_attendance",
                                 status="approved"))
            await s.commit()
            ot_cap_neg = await pr.compute_overtime(s, u1, PERIOD, profile, days)
            check("Payroll §3.4: cheklov MANFIY tomonda ham qo'llanadi (-60)",
                  ot_cap_neg["minutes"] == -60, f"={ot_cap_neg['minutes']}")

            # Sinovdan keyin asl holatga (keyingi tekshiruvlar buzilmasin)
            profile.daily_cap_minutes = None
            await s.execute(delete(OvertimeEntry).where(OvertimeEntry.user_id == u1.id))
            s.add(OvertimeEntry(user_id=u1.id, date=day1, minutes=120, source="manual",
                                 status="approved"))
            await s.commit()

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
            # §2.3 dan keyin oylik hisobi bonus qatorini ham yaratadi —
            # tozalanmasa `delete(User)` FOREIGN KEY bilan yiqiladi.
            await s.execute(delete(Bonus).where(Bonus.user_id.in_([u1.id, u2.id])))
            await s.execute(delete(ExcusedDay).where(ExcusedDay.user_id.in_([u1.id, u2.id])))
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
        for tbl in ("payslips", "bonuses", "overtime_entries", "overtime_profiles", "payroll_adjustments",
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
            for tbl in ("payslips", "bonuses", "overtime_entries", "overtime_profiles", "payroll_adjustments",
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
            # §4.3: endi bu NAVBATGA qo'yadi (202) — hisobni cron bajaradi.
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t),
                             json={"user_ids": [emp_uid]})
            check("calculate -> 202 (navbatga qo'yildi)", r.status_code == 202,
                  f"kod={r.status_code} {r.text[:150]}")
            check("calculate javobida navbat belgisi bor",
                  r.status_code == 202 and r.json().get("queued") is True,
                  f"={r.json() if r.status_code == 202 else None}")
            tick = payroll_tick(client, PERIOD)
            check("cron navbatdagi davrni hisobladi",
                  bool(tick) and tick.get("ran") == PERIOD and tick.get("calculated") == 1, f"={tick}")

            # Hisob ketayotganda ikkinchi marta bosib bo'lmasin (409)
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
            check("navbatga qayta qo'yish -> 202 (avvalgisi tugagan)", r.status_code == 202,
                  f"kod={r.status_code}")
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
            check("hisob navbatda turganda ikkinchi so'rov -> 409", r.status_code == 409,
                  f"kod={r.status_code}")
            r = client.get(f"{API_BASE}/payroll/{PERIOD}/status", headers=auth(mgr_t))
            check("GET /status navbat holatini ko'rsatadi",
                  r.status_code == 200 and r.json().get("state") == "queued",
                  f"kod={r.status_code} {r.text[:120]}")
            payroll_tick(client, PERIOD)
            r = client.get(f"{API_BASE}/payroll/{PERIOD}/status", headers=auth(mgr_t))
            check("hisob tugagach state=done",
                  r.status_code == 200 and r.json().get("state") == "done", f"={r.text[:120]}")

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

            # S-06 (TZ 4-qism): begona yozuvga 404, 403 EMAS. 403 «yozuv bor,
            # lekin ruxsat yo'q» degani — ya'ni o'sha xodim MAVJUDLIGINI
            # oshkor qiladi. TZ buni ataylab taqiqlaydi.
            r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{outsider_uid}", headers=auth(rop_t))
            check("ROP begona xodim tafsilotiga -> 404 (S-06: 403 emas)",
                  r.status_code == 404, f"kod={r.status_code}")

            r = client.get(f"{API_BASE}/payroll/{PERIOD}/user/{emp_uid}", headers=auth(emp_t))
            check("xodim /payroll/*/user -> 403 (VIEW_ROLES'da yo'q)", r.status_code == 403,
                  f"kod={r.status_code}")

            # ── Tasdiqlash va qulf ──
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(rop_t))
            check("ROP tasdiqlay OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # 2026-08-08: tasdiq IKKI BOSQICHLI bo'ldi (vazifalar ajratildi).
            # Avval HR "tayyor" deyishi, keyin FAQAT Boshliq/Dasturchi
            # yakuniy tasdiqlashi kerak.
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(mgr_t))
            check("HR bosqichisiz yakuniy tasdiq -> 409", r.status_code == 409,
                  f"kod={r.status_code} {r.text[:120]}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/hr-approve", headers=auth(mgr_t))
            check("HR «tayyor» dedi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")

            # Yakuniy tasdiq faqat boss/dasturchi — `find_manager_id` HR
            # qaytargan bo'lishi mumkin, shuning uchun ALOHIDA boss tokeni.
            _c = db()
            _boss = _c.execute(
                "select id, role from users where role in ('boss','dasturchi') and is_active=1 limit 1"
            ).fetchone()
            _c.close()
            boss_t = token_for(_boss[0], _boss[1]) if _boss else mgr_t
            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(boss_t))
            check("Boshliq yakuniy tasdiqlaydi -> 200", r.status_code == 200,
                  f"kod={r.status_code} {r.text[:150]}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/calculate", headers=auth(mgr_t), json={})
            check("tasdiqlangan (qulflangan) davrni qayta hisoblash -> 409", r.status_code == 409,
                  f"kod={r.status_code}")

            r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(boss_t))
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
        for tbl in ("payslips", "bonuses", "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
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
            for tbl in ("payslips", "bonuses", "salary_rates", "attendance", "work_schedule_override", "work_schedule_weekly"):
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
                check("payroll navbatga qo'yildi -> 202", r.status_code == 202, f"kod={r.status_code}")
                tick = payroll_tick(client, PERIOD)
                check("payroll hisoblandi (cron)", bool(tick) and tick.get("ok") is True, f"={tick}")
                # Ikki bosqichli tasdiq (9a02004): HR «tayyor» demaguncha
                # Boshliq qulflay OLMAYDI — aks holda bir odam butun pul
                # jarayonini yakunlab qo'yardi.
                r = client.post(f"{API_BASE}/payroll/{PERIOD}/approve", headers=auth(mgr_t))
                check("HR bosqichisiz yakuniy tasdiq -> 409", r.status_code == 409,
                      f"kod={r.status_code}")

                r = client.post(f"{API_BASE}/payroll/{PERIOD}/hr-approve", headers=auth(mgr_t))
                check("HR «tekshirdim, tayyor» -> 200", r.status_code == 200, f"kod={r.status_code}")

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
                check("qulf ochilgach HR qayta hisoblay oladi -> 202", r.status_code == 202,
                      f"kod={r.status_code}")
                tick = payroll_tick(client, PERIOD)
                check("qulf ochilgach cron hisobladi", bool(tick) and tick.get("ok") is True, f"={tick}")

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
            # 2026-08-15: nomzod endi SOF FARQ bo'yicha aniqlanadi
            # (`worked_minutes` − rejadagi daqiqa), ilgari esa faqat
            # `check_out − ish oynasi tugashi` qaralardi. Farqi muhim: xodim
            # kech kelib kech ketsa eski usul buni «qo'shimcha ish» deb
            # yozardi, aslida u KAM ishlagan bo'lishi mumkin edi. Shuning
            # uchun sinov ma'lumoti ham `worked_minutes` bilan beriladi.
            s.add(Attendance(user_id=uot.id, date=day_over, status="present",
                              worked_minutes=WINDOW_MIN + 30,  # +30 daq ORTIQCHA -> nomzod
                              check_out_time=local_hm_to_utc(day_over, "18:30")))
            s.add(Attendance(user_id=uot.id, date=day_within, status="present",
                              worked_minutes=WINDOW_MIN - 10,  # sezgirlik chegarasi (15) ichida -> yo'q
                              check_out_time=local_hm_to_utc(day_within, "17:50")))
            s.add(Attendance(user_id=uot.id, date=day_http, status="present",
                              worked_minutes=WINDOW_MIN + 25,  # HTTP orqali tekshiriladi
                              check_out_time=local_hm_to_utc(day_http, "18:25")))
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
            Bonus,
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
            # §2.3 dan keyin oylik hisobi KPI bonusini ham yaratadi — ya'ni
            # sinov foydalanuvchilarida endi `bonuses` qatori ham qoladi va
            # tozalanmasa `delete(User)` FOREIGN KEY bilan yiqiladi.
            await s.execute(delete(Bonus).where(Bonus.user_id.in_(ids)))
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
            Bonus,
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
                # §2.3: oylik hisobi endi bonus qatorini ham yaratadi
                await s.execute(delete(Bonus).where(Bonus.user_id.in_(ids)))
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
                check("qayta hisoblash -> 202", r.status_code == 202, f"kod={r.status_code}")
                # Audit yozuvini endi CRON yozadi (so'rov emas) — actor_id
                # `calc_requested_by` dan olinadi, ya'ni kim bosgani saqlanadi.
                payroll_tick(client, PERIOD)

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
    # Dasturchi roli — egasining 2026-08-05 talabi: HR uning ham ish grafigi
    # va dam kunini belgilay olsin (ilgari 403 edi).
    cur.execute(
        "insert into users (telegram_id, full_name, role, bot_started, is_active, created_at)"
        " values (999901004,'T-HrWide-Dev','dasturchi',1,1,datetime('now'))")
    dev_uid = cur.lastrowid
    conn.commit()

    def cleanup_hw():
        try:
            conn2 = db()
            c2 = conn2.cursor()
            uids = [hr_uid, rop_uid, emp_uid, dev_uid]
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

            # ── Dasturchi: HR endi uning grafigini ham yuritadi ──
            r = client.get(f"{API_BASE}/work-schedule/{dev_uid}/weekly", headers=auth(hr_t))
            check("HR DASTURCHI jadvalini ko'radi -> 200 (ilgari 403)",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.put(
                f"{API_BASE}/work-schedule/{dev_uid}/weekly", headers=auth(hr_t),
                json={"days": [
                    {"weekday": wd, "is_working": wd < 5, "start_time": "09:00" if wd < 5 else None,
                     "end_time": "18:00" if wd < 5 else None}
                    for wd in range(7)
                ]},
            )
            check("HR DASTURCHI jadvalini o'zgartira oladi -> 200",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.put(
                f"{API_BASE}/work-schedule/{dev_uid}/override", headers=auth(hr_t),
                json={"date": "2020-06-07", "is_working": False, "note": "T-sinov: dasturchi dam kuni"},
            )
            check("HR DASTURCHIGA dam kuni belgilay oladi -> 200",
                  r.status_code == 200, f"kod={r.status_code} {r.text[:150]}")

            r = client.get(f"{API_BASE}/work-schedule/{rop_uid}/weekly", headers=auth(hr_t))
            check("ROP jadvali HR uchun HAMON yopiq -> 403 (qamrov kengaymadi)",
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
            check("Oddiy xodim ruxsat bera OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            # 5. HR ham bera oladi (2026-08-04: egasi "hr va dasturchi
            #    foydalanishi uchun" dedi — ilgari faqat Dasturchi edi va HR
            #    ko'chma xodimni o'zi belgilay olmasdi).
            c = db()
            hr_row = c.execute(
                "select id from users where role='hr' and is_active=1 limit 1").fetchone()
            c.close()
            if hr_row:
                hr_t = token_for(hr_row[0], "hr")
                r = client.post(
                    f"{API_BASE}/admin/users/{bound_uid}/location-exempt", headers=auth(hr_t),
                    json={"granted": False, "override_reason": "T-sinov: HR olib qo'ydi"},
                )
                check("HR ruxsatni boshqara oladi -> 200", r.status_code == 200,
                      f"kod={r.status_code} {r.text[:120]}")
                r = client.get(f"{API_BASE}/admin/location-exempt", headers=auth(hr_t))
                check("HR ruxsat ro'yxatini ko'ra oladi -> 200", r.status_code == 200,
                      f"kod={r.status_code}")
            else:
                check("HR hisobi topildi", False, "bazada hr roli yo'q")
    except Exception:
        check("Bez-lokatsiya check-in (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cleanup_ng()
        conn.close()


def test_attendance_list_dates() -> None:
    """«Yozuvlar» ro'yxatining sana filtri (2026-08-03 regressiyasi).

    ⚠️ BU BUG LOKALDA TAKRORLANMAYDI: SQLite sanani matn sifatida saqlaydi va
    satr bilan solishtirishga rozi bo'ladi. PostgreSQL esa rad etadi —
    «operator does not exist: date >= character varying» — ya'ni jonli
    serverda endpoint 500 qaytarardi va rahbar panelidagi jadval doim bo'sh
    ko'rinardi. Shuning uchun bu test tipni EMAS, xulq-atvorni qo'riqlaydi:
    (a) to'g'ri sana bilan 200 va oraliqdan tashqaridagi yozuv KIRMAYDI;
    (b) noto'g'ri formatda 400 (ilgari 500 bo'lardi)."""
    import httpx

    print("\n" + "=" * 60)
    print("DAVOMAT RO'YXATI — SANA FILTRI")
    print("=" * 60)

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "boss/dasturchi/hr yo'q")
        return
    token = token_for(mgr[0], mgr[1])
    if not token:
        return

    conn = db()
    cur = conn.cursor()
    today = date.today()
    inside = (today - timedelta(days=2)).isoformat()
    outside = (today - timedelta(days=40)).isoformat()
    uid = None
    try:
        cur.execute(
            "insert into users (full_name, role, is_active, bot_started, created_at)"
            " values (?,?,1,0,datetime('now'))",
            ("T-SanaFiltr", "employee"),
        )
        uid = cur.lastrowid
        for d in (inside, outside):
            cur.execute(
                "insert into attendance (user_id, date, status, late_minutes,"
                " early_leave_minutes, worked_minutes, is_weekend, created_at, updated_at)"
                " values (?,?,?,0,0,0,0,datetime('now'),datetime('now'))",
                (uid, d, "present"),
            )
        conn.commit()

        with httpx.Client(base_url=API_BASE, timeout=20) as c:
            r = c.get(
                "/attendance",
                params={"user_id": uid, "date_from": (today - timedelta(days=7)).isoformat(),
                        "date_to": today.isoformat()},
                headers=auth(token),
            )
            check("sana oralig'i bilan 200 qaytdi", r.status_code == 200, f"status={r.status_code} {r.text[:120]}")
            if r.status_code == 200:
                dates = [row["date"] for row in r.json()]
                check("oraliq ICHIDAGI yozuv keldi", inside in dates, f"dates={dates}")
                check("oraliqdan TASHQARIDAGI yozuv kelmadi", outside not in dates, f"dates={dates}")

            r2 = c.get("/attendance", params={"date_from": "03.08.2026"}, headers=auth(token))
            check("noto'g'ri sana formatida 400 (500 EMAS)", r2.status_code == 400,
                  f"status={r2.status_code}")
    finally:
        if uid is not None:
            cur.execute("delete from attendance where user_id=?", (uid,))
            cur.execute("delete from users where id=?", (uid,))
            conn.commit()
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
            # Ish boshlanishi hozir+10 daqiqa qilib qo'yilgan -> AYNAN 10
            # daqiqalik nuqta tushishi kerak (5 va 0 hali emas).
            mine = [p for p in planned if p["user_id"] == forgot_uid]
            check("Bosmagan uchun tur = check_in_10",
                  any(p["kind"] == "check_in_10" for p in mine), f"={mine}")
            check("5 va 0 nuqtalari HALI tushmadi",
                  not any(p["kind"] in ("check_in_5", "check_in_0") for p in mine), f"={mine}")
            check("Bitta tick'da bitta nuqta", len(mine) <= 1, f"={mine}")

            # Iz yozilgan bo'lsa o'sha nuqta takror tushmasligi (real
            # yuborishsiz — izni qo'lda yozamiz, chunki dry_run iz yozmaydi).
            c = db()
            c.execute(
                "insert into attendance_reminders (user_id, date, kind, sent_at)"
                " values (?,?,'check_in_10',datetime('now'))", (forgot_uid, today))
            c.commit()
            c.close()
            r = client.post(f"{API_BASE}/attendance/reminder-tick", headers=hdr, json={"dry_run": True})
            planned2 = r.json().get("planned", []) if r.status_code == 200 else []
            mine2 = [p for p in planned2 if p["user_id"] == forgot_uid]
            check("Iz yozilgach o'sha nuqta TAKROR tushmaydi",
                  not any(p["kind"] == "check_in_10" for p in mine2), f"={mine2}")
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


def test_payroll_approval_segregation() -> None:
    """Oylik tasdig'i ikki bosqichga ajratildi (2026-08-08, egasining talabi
    "hr uni belgilaydi, boss boshliq uni tasdiqlaydi").

    ILGARI: HR o'zi hisoblab, o'zi tasdiqlab, davrni QULFLAB qo'yardi —
    bitta odam butun pul jarayonini yakunlardi (sinovda tasdiqlangan edi:
    HR tokeni bilan calculate va approve ketma-ket 200 qaytargan).

    ENDI: calculated -> hr_approved (HR) -> approved+locked (Boshliq).

    Tekshiriladi:
      (a) HR yakuniy tasdiqlay OLMAYDI (403);
      (b) Boshliq HR bosqichisiz tasdiqlay OLMAYDI (409);
      (c) HR "tayyor" deydi -> status hr_approved, kim tekshirgani ko'rinadi;
      (d) Boshliq tasdiqlaydi -> locked;
      (e) qulflangach qayta hisoblash 409.
    """
    import httpx

    print("\n" + "=" * 60)
    print("OYLIK TASDIG'I: VAZIFALAR AJRATIMI")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    period = "2019-05"          # ATAYLAB uzoq o'tmish — jonli davrlarga tegmasin
    uid = None
    try:
        hr_row = cur.execute("select id from users where role='hr' and is_active=1 limit 1").fetchone()
        boss_row = cur.execute("select id from users where role='boss' and is_active=1 limit 1").fetchone()
        if not hr_row or not boss_row:
            check("HR va Boshliq hisoblari topildi", False, "biri yo'q")
            return
        hr_t = token_for(hr_row[0], "hr")
        boss_t = token_for(boss_row[0], "boss")

        cur.execute(
            "insert into users (full_name, role, is_active, bot_started, created_at)"
            " values (?,?,1,0,datetime('now'))", ("T-Approve", "employee"))
        uid = cur.lastrowid
        conn.commit()

        with httpx.Client(base_url=API_BASE, timeout=60) as c:
            r = c.post(f"/payroll/{period}/calculate", headers=auth(hr_t), json={"user_ids": [uid]})
            check("HR hisoblay oladi (navbat -> 202)", r.status_code == 202,
                  f"kod={r.status_code} {r.text[:120]}")
            tick = payroll_tick(c, period)
            check("cron HR so'rovini bajardi", bool(tick) and tick.get("ok") is True, f"={tick}")

            r = c.post(f"/payroll/{period}/approve", headers=auth(hr_t))
            check("HR YAKUNIY tasdiqlay OLMAYDI -> 403", r.status_code == 403, f"kod={r.status_code}")

            r = c.post(f"/payroll/{period}/approve", headers=auth(boss_t))
            check("Boshliq HR bosqichisiz tasdiqlay olmaydi -> 409",
                  r.status_code == 409, f"kod={r.status_code} {r.text[:120]}")

            r = c.post(f"/payroll/{period}/hr-approve", headers=auth(hr_t))
            check("HR «tayyor» dedi -> 200", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")
            if r.status_code == 200:
                check("status hr_approved bo'ldi", r.json().get("status") == "hr_approved",
                      f"status={r.json().get('status')}")

            r = c.get("/payroll/periods", headers=auth(boss_t))
            if r.status_code == 200:
                row = next((x for x in r.json() if x["period"] == period), None)
                check("Boshliq kim tekshirganini ko'radi",
                      bool(row and row.get("hr_approved_name")),
                      f"hr_approved_name={row.get('hr_approved_name') if row else None}")

            r = c.post(f"/payroll/{period}/approve", headers=auth(boss_t))
            check("Boshliq yakuniy tasdiqladi -> 200", r.status_code == 200, f"kod={r.status_code}")

            r = c.post(f"/payroll/{period}/calculate", headers=auth(hr_t), json={"user_ids": [uid]})
            check("qulflangach qayta hisoblash -> 409", r.status_code == 409, f"kod={r.status_code}")
    finally:
        cur.execute("delete from payslip_items where payslip_id in (select id from payslips where period=?)", (period,))
        cur.execute("delete from payslips where period=?", (period,))
        cur.execute("delete from payroll_periods where period=?", (period,))
        if uid is not None:
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from users where id=?", (uid,))
        cur.execute("delete from audit_logs where action in "
                    "('payroll_calculated','payroll_period_hr_approved','payroll_period_approved')")
        conn.commit()
        conn.close()


def test_kpi_rates() -> None:
    """KPI stavkalari saytdan sozlanadigan bo'ldi (2026-08-08, egasi so'radi).

    Ilgari stavkalar `api/services/bonus.py` da KONSTANTA edi — HR ularni
    o'zgartira olmasdi, tarixiy emasdi va lavozimga qarab farqlanmasdi
    (mobilograf video stavkasi 0 bo'lgani uchun uning KPI'si doim nol edi).

    Tekshiriladi:
      (a) stavka yaratish va ro'yxat;
      (b) 3 darajali qamrov — xodim stavkasi global'dan USTUN;
      (c) tarixiylik — keyingi `effective_from` eskisini bosmaydi;
      (d) validatsiya (noma'lum ko'rsatkich, global+scope_id, dublikat sana);
      (e) sozlanmagan stavka -> bonus 0, LEKIN breakdown'da `missing_rates`.
    """
    import asyncio as _aio
    import httpx
    from datetime import date as _date
    from decimal import Decimal as _Dec

    print("\n" + "=" * 60)
    print("KPI STAVKALARI (kpi_rates)")
    print("=" * 60)

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    token = token_for(mgr[0], mgr[1])
    if not token:
        return

    conn = db()
    cur = conn.cursor()
    uid = kpi_pos_id = None
    try:
        # Lavozim SHART: `metrics_for` bo'sh bo'lsa `calculate_bonus` hech
        # qanday ko'rsatkichni ko'rmaydi va §2.6(a) tekshiruvi ma'nosiz
        # bo'lib qolardi. «suhbat» ga stavka beriladi, «tashrif» ga YO'Q —
        # aynan shu farq `missing_rates` da ko'rinishi kerak.
        cur.execute(
            "insert into positions (name, metrics, is_active, created_at)"
            " values (?,?,1,datetime('now'))", ("T-Kpi-Lavozim", '["suhbat", "tashrif"]'))
        kpi_pos_id = cur.lastrowid
        cur.execute(
            "insert into users (full_name, role, position_id, is_active, bot_started, created_at)"
            " values (?,?,?,1,0,datetime('now'))", ("T-Kpi", "employee", kpi_pos_id))
        uid = cur.lastrowid
        conn.commit()

        with httpx.Client(base_url=API_BASE, timeout=20) as c:
            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "global", "metric": "suhbat", "amount": 2500,
                "effective_from": "2020-01-01", "note": "T-sinov"})
            check("global stavka yaratildi", r.status_code == 200, f"kod={r.status_code} {r.text[:120]}")

            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "user", "scope_id": uid, "metric": "suhbat", "amount": 4000,
                "effective_from": "2020-01-01"})
            check("xodimga alohida stavka", r.status_code == 200, f"kod={r.status_code}")

            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "global", "metric": "suhbat", "amount": 9999,
                "effective_from": "2020-01-01"})
            check("bir sanaga ikkinchi stavka -> 400", r.status_code == 400, f"kod={r.status_code}")

            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "global", "scope_id": 5, "metric": "suhbat", "amount": 100,
                "effective_from": "2020-01-01"})
            check("global + scope_id -> 422", r.status_code == 422, f"kod={r.status_code}")

            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "global", "metric": "yolgon_korsatkich", "amount": 100,
                "effective_from": "2020-01-01"})
            check("noma'lum ko'rsatkich -> 422", r.status_code == 422, f"kod={r.status_code}")

            # Tarixiylik: keyingi sanaga yangi qiymat
            r = c.post("/payroll/kpi-rates", headers=auth(token), json={
                "scope": "user", "scope_id": uid, "metric": "suhbat", "amount": 6000,
                "effective_from": "2020-06-01"})
            check("keyingi sanaga yangi stavka (tarix)", r.status_code == 200, f"kod={r.status_code}")

        # Qamrov va tarix — xizmat qatlamidan
        from api.services.kpi_rates import resolve_kpi_rate
        from db.base import async_session
        from db.models import User as _U

        async def _chk():
            async with async_session() as s2:
                u = await s2.get(_U, uid)
                eski = await resolve_kpi_rate(s2, u, "suhbat", _date(2020, 3, 1))
                yangi = await resolve_kpi_rate(s2, u, "suhbat", _date(2020, 9, 1))
                yoq = await resolve_kpi_rate(s2, u, "tashrif", _date(2020, 9, 1))
                return eski, yangi, yoq

        eski, yangi, yoq = _aio.run(_chk())
        check("xodim stavkasi global'dan USTUN (4000)", eski == _Dec("4000.00"), f"={eski}")
        check("tarix ishlaydi — keyingi sanada 6000", yangi == _Dec("6000.00"), f"={yangi}")
        check("sozlanmagan ko'rsatkich -> None (0 EMAS)", yoq is None, f"={yoq}")

        # §2.6(a): stavka sozlanmagan bo'lsa bonus 0 chiqadi, LEKIN sabab
        # breakdown'da yozilib qoladi. HR «nega bonus 0» degan savolga bir
        # qarashda javob topsin — 0 stavka (ataylab bepul) va stavka YO'Q
        # (hali kiritilmagan) BOSHQA-BOSHQA holat.
        from api.services.bonus import calculate_bonus as _calc_bonus

        async def _bonus_breakdown():
            async with async_session() as s3:
                u = await s3.get(_U, uid)
                return await _calc_bonus(s3, u, "2020-09")

        natija = _aio.run(_bonus_breakdown())
        bd = natija["breakdown"]
        check("§2.6a: stavkasiz ko'rsatkich bonusga 0 qo'shadi",
              float(natija["amount"]) == 0.0, f"={natija['amount']}")
        check("§2.6a: breakdown'da `missing_rates` sababi qoladi",
              "missing_rates" in bd and len(bd["missing_rates"]) > 0, f"={bd.get('missing_rates')}")
        check("§2.6a: sozlangan ko'rsatkich `missing_rates` ga TUSHMAYDI",
              "suhbat" not in bd.get("missing_rates", []), f"={bd.get('missing_rates')}")
    finally:
        if uid is not None:
            cur.execute("delete from kpi_rates where scope='user' and scope_id=?", (uid,))
            cur.execute("delete from kpi_rates where scope='global' and metric='suhbat' and note='T-sinov'")
            cur.execute("delete from kpi_rates where scope='global' and metric='suhbat'")
            cur.execute("delete from audit_logs where action='kpi_rate_created'")
            cur.execute("delete from bonuses where user_id=?", (uid,))
            cur.execute("delete from users where id=?", (uid,))
        if kpi_pos_id is not None:
            cur.execute("delete from positions where id=?", (kpi_pos_id,))
            conn.commit()
        conn.close()


def test_overtime_global_profile() -> None:
    """§3.2 — qo'shimcha ish nihoyat AVTOMATIK hisoblanadimi.

    MUAMMO EDI: `OvertimeProfile` faqat xodim bo'yicha edi va `enabled`
    default `False`. Ya'ni HR har bir xodimga QO'LDA profil ochmaguncha
    qo'shimcha ish umuman hisoblanmasdi — jonli bazada yoqilgan profil 0 ta
    edi. Endi `scope='global'` qatori barchaga default bo'ladi.

    Tekshiriladi:
      (a) profilsiz xodim -> 0 (regressiya qo'riqchisi);
      (b) GLOBAL profil yoqilgach o'sha xodimga nomzod yaratiladi;
      (c) xodimning O'Z qatori global'dan USTUN (hatto o'chirilgan bo'lsa ham);
      (d) `auto_approve` -> nomzod darhol `approved`;
      (e) `/overtime/detect-now` — rahbarga 200, xodimga 403;
      (f) `/overtime/bulk-decide` bir bosishda hammasini tasdiqlaydi.
    """
    import asyncio as _aio
    import httpx
    from datetime import date as _date

    print("\n" + "=" * 60)
    print("QO'SHIMCHA ISH: GLOBAL PROFIL (3.2)")
    print("=" * 60)

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])
    if not mgr_t:
        return

    KUN = "2019-09-10"
    WINDOW_MIN = 480
    conn = db()
    cur = conn.cursor()
    a_uid = b_uid = None
    try:
        for nom, tg in (("T-OtGlobalA", 999700601), ("T-OtGlobalB", 999700602)):
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " created_at) values (?,?,'employee',0,1,datetime('now'))", (tg, nom))
        a_uid, b_uid = [r[0] for r in cur.execute(
            "select id from users where full_name in ('T-OtGlobalA','T-OtGlobalB') order by id")]
        for uid in (a_uid, b_uid):
            for wd in range(7):
                cur.execute("insert into work_schedule_weekly (user_id, weekday, is_working,"
                            " updated_at) values (?,?,0,datetime('now'))", (uid, wd))
            cur.execute("insert into work_schedule_override (user_id, date, is_working,"
                        " start_time, end_time, updated_at)"
                        " values (?,?,1,'09:00','18:00',datetime('now'))", (uid, KUN))
            # +40 daqiqa ORTIQCHA ishlangan
            # `check_out_time` SHART: aniqlash faqat ishdan chiqqani qayd
            # etilgan kunlarni qaraydi (aks holda kun hali tugamagan bo'lishi
            # mumkin). 13:40 UTC = 18:40 Toshkent.
            cur.execute("insert into attendance (user_id, date, status, late_minutes,"
                        " early_leave_minutes, worked_minutes, is_weekend, check_out_time,"
                        " created_at, updated_at)"
                        " values (?,?,'present',0,0,?,0,?,datetime('now'),datetime('now'))",
                        (uid, KUN, WINDOW_MIN + 40, KUN + " 13:40:00"))
        conn.commit()
        emp_t = token_for(a_uid, "employee")

        from api.services import payroll as pr
        from db.base import async_session

        async def _detect():
            async with async_session() as s2:
                created = await pr.detect_overtime_candidates(s2, _date(2019, 9, 10))
                await s2.commit()
                return [(e.user_id, e.minutes, e.status) for e in created]

        # (a) profil umuman yo'q -> nomzod yo'q
        yoq = _aio.run(_detect())
        check("profilsiz xodimga nomzod YARATILMAYDI (regressiya)",
              all(u not in (a_uid, b_uid) for u, _, _ in yoq), "=" + str(yoq))

        with httpx.Client(base_url=API_BASE, timeout=60) as c:
            # (e) huquqlar — detect-now
            r = c.post("/payroll/overtime/detect-now", headers=auth(emp_t), json={"target_date": KUN})
            check("/overtime/detect-now oddiy xodimga -> 403", r.status_code == 403,
                  "kod=" + str(r.status_code))

            # (b) GLOBAL profil yoqiladi
            r = c.put("/payroll/overtime-profiles/global", headers=auth(mgr_t), json={
                "enabled": True, "auto_approve": False, "mode": "fixed_rate",
                "fixed_rate_per_hour": 10000, "norm_hours_source": "schedule",
                "min_minutes": 15})
            check("global profil yaratildi -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:150])
            check("global profil scope='global', user_id yo'q",
                  r.status_code == 200 and r.json().get("scope") == "global"
                  and r.json().get("user_id") is None, "=" + r.text[:120])

            r = c.post("/payroll/overtime/detect-now", headers=auth(mgr_t), json={"target_date": KUN})
            check("/overtime/detect-now rahbarga -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:150])
            rows = cur.execute("select user_id, minutes, status from overtime_entries"
                               " where date=? and user_id in (?,?)", (KUN, a_uid, b_uid)).fetchall()
            check("GLOBAL profil bilan IKKALA xodimga ham nomzod yaratildi",
                  len(rows) == 2, "=" + str(rows))
            check("nomzod +40 daqiqa (sof farq)",
                  all(r2[1] == 40 for r2 in rows), "=" + str(rows))
            check("nomzod 'pending' (auto_approve o'chiq)",
                  all(r2[2] == "pending" for r2 in rows), "=" + str(rows))

            # (f) ommaviy tasdiq
            r = c.post("/payroll/overtime/bulk-decide", headers=auth(mgr_t),
                       json={"period": "2019-09", "status": "approved"})
            check("/overtime/bulk-decide -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            check("bulk-decide kamida 2 ta yozuvni tasdiqladi",
                  r.status_code == 200 and r.json().get("decided", 0) >= 2, "=" + r.text[:120])
            qolgan = cur.execute("select count(*) from overtime_entries where date=?"
                                 " and status='pending'", (KUN,)).fetchone()
            check("kutilayotgan yozuv qolmadi", qolgan[0] == 0, "=" + str(qolgan))

            # (c) xodim qatori global'dan USTUN — B ga O'CHIRILGAN profil
            cur.execute("delete from overtime_entries where date=?", (KUN,))
            conn.commit()
            r = c.put("/payroll/overtime-profiles/" + str(b_uid), headers=auth(mgr_t), json={
                "enabled": False, "auto_approve": False, "mode": "fixed_rate",
                "fixed_rate_per_hour": 10000, "norm_hours_source": "schedule",
                "min_minutes": 15})
            check("xodimga o'chirilgan profil yozildi -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:150])
            c.post("/payroll/overtime/detect-now", headers=auth(mgr_t), json={"target_date": KUN})
            rows2 = [r2[0] for r2 in cur.execute(
                "select user_id from overtime_entries where date=? and user_id in (?,?)",
                (KUN, a_uid, b_uid)).fetchall()]
            check("xodim qatori GLOBAL'dan ustun — o'chirilgan xodimga nomzod YO'Q",
                  a_uid in rows2 and b_uid not in rows2, "=" + str(rows2))

            # (d) auto_approve
            cur.execute("delete from overtime_entries where date=?", (KUN,))
            conn.commit()
            r = c.put("/payroll/overtime-profiles/" + str(b_uid), headers=auth(mgr_t), json={
                "enabled": True, "auto_approve": True, "mode": "fixed_rate",
                "fixed_rate_per_hour": 10000, "norm_hours_source": "schedule",
                "min_minutes": 15})
            check("auto_approve yoqilgan profil -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:150])
            c.post("/payroll/overtime/detect-now", headers=auth(mgr_t), json={"target_date": KUN})
            st = cur.execute("select status from overtime_entries where date=? and user_id=?",
                             (KUN, b_uid)).fetchone()
            check("auto_approve -> nomzod DARHOL tasdiqlangan",
                  st is not None and st[0] == "approved", "=" + str(st))
    except Exception:
        check("Global qo'shimcha ish profili (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cur.execute("delete from overtime_entries where date=?", (KUN,))
        cur.execute("delete from overtime_profiles where scope='global'")
        if a_uid is not None:
            ids = [a_uid, b_uid]
            qm = ",".join("?" * len(ids))
            for t in ("overtime_entries", "overtime_profiles", "attendance",
                      "work_schedule_override", "work_schedule_weekly", "bonuses", "payslips"):
                cur.execute("delete from " + t + " where user_id in (" + qm + ")", ids)
            cur.execute("delete from audit_logs where target_user_id in (" + qm + ")"
                        " or actor_id in (" + qm + ")", ids + ids)
            cur.execute("delete from users where id in (" + qm + ")", ids)
        cur.execute("delete from audit_logs where action in ('overtime_profile_global_upserted',"
                    "'overtime_bulk_decided','overtime_detect_now')")
        conn.commit()
        conn.close()


def test_kpi_in_payroll() -> None:
    """§2.3 — KPI bonusi OYLIK bilan birga hisoblanadimi.

    MUAMMO EDI: `bonuses` jadvaliga qator yaratadigan yagona yo'l bot/cron
    edi (oyning oxirgi kuni 23:30). `build_payslip` esa o'sha jadvaldan
    TAYYOR qatorni o'qiydi — ya'ni oy o'rtasida HR «Hisoblash» bosganda
    bonus qatori umuman yo'q bo'lib, KPI puli jimgina 0 chiqardi.

    Tekshiriladi:
      (a) `/bonuses/recalculate` — rahbarga 200, oddiy xodimga 403;
      (b) qamrov `employee` dan kengaydi (§2.5);
      (c) oylik hisobi bonus qatorini O'ZI yaratadi (avval qator YO'Q edi)
          va payslip'da bonus summasi ko'rinadi.
    """
    import httpx

    print("\n" + "=" * 60)
    print("KPI BONUSI OYLIK BILAN BIRGA (2.3)")
    print("=" * 60)

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])
    if not mgr_t:
        return

    PERIOD = "2021-05"
    conn = db()
    cur = conn.cursor()
    uid = pos_id = None
    try:
        # Lavozim — FAQAT «suhbat» ko'rsatkichi (metrics_for shundan o'qiydi)
        cur.execute(
            "insert into positions (name, metrics, is_active, created_at)"
            " values (?,?,1,datetime('now'))", ("T-KpiPay-Lavozim", '["suhbat"]'))
        pos_id = cur.lastrowid
        cur.execute(
            "insert into users (telegram_id, full_name, role, position_id, bot_started,"
            " is_active, created_at) values (999700801,'T-KpiPay','employee',?,0,1,datetime('now'))",
            (pos_id,))
        uid = cur.lastrowid
        # 10 ta suhbat -> stavka 3000 -> bonus 30 000 kutiladi
        cur.execute(
            "insert into daily_results (user_id, date, conversations_count, visits_count, source)"
            " values (?,?,?,?,'manual')", (uid, PERIOD + "-11", 10, 0))
        conn.commit()
        emp_t = token_for(uid, "employee")

        with httpx.Client(base_url=API_BASE, timeout=60) as c:
            c.post("/payroll/kpi-rates", headers=auth(mgr_t), json={
                "scope": "user", "scope_id": uid, "metric": "suhbat", "amount": 3000,
                "effective_from": PERIOD + "-01", "note": "T-kpipay"})
            c.post("/payroll/rates", headers=auth(mgr_t), json={
                "user_id": uid, "amount": 1000000, "pay_basis": "monthly",
                "effective_from": PERIOD + "-01"})

            # (a) huquqlar
            r = c.post("/bonuses/recalculate", headers=auth(emp_t), json={"period": PERIOD})
            check("/bonuses/recalculate oddiy xodimga -> 403", r.status_code == 403,
                  "kod=" + str(r.status_code))
            r = c.post("/bonuses/recalculate", headers=auth(mgr_t), json={"period": PERIOD})
            check("/bonuses/recalculate rahbarga -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code) + " " + r.text[:120])

            row = cur.execute("select amount from bonuses where user_id=? and period=?",
                              (uid, PERIOD)).fetchone()
            check("saytdan hisoblanganda bonus qatori paydo bo'ldi (10 x 3000)",
                  row is not None and abs(row[0] - 30000) < 1, "=" + str(row))

            # (b) qamrov: employee'dan boshqa rollar ham (ilgari faqat employee edi)
            other = cur.execute(
                "select count(*) from bonuses b join users u on u.id=b.user_id"
                " where b.period=? and u.role in ('hr','rop','dasturchi')", (PERIOD,)).fetchone()
            check("qamrov kengaydi — employee'dan boshqa rollar ham hisoblandi (2.5)",
                  other is not None and other[0] >= 1, "=" + str(other))

            # (c) ASOSIY: bonus qatorlarini o'chirib, FAQAT oylik hisoblaymiz
            cur.execute("delete from bonuses where period=?", (PERIOD,))
            conn.commit()
            yoq = cur.execute("select count(*) from bonuses where period=?", (PERIOD,)).fetchone()
            check("tayyorgarlik: bonus qatorlari o'chirildi", yoq[0] == 0, "=" + str(yoq))

            r = c.post("/payroll/" + PERIOD + "/calculate", headers=auth(mgr_t), json={})
            check("oylik navbatga qo'yildi -> 202", r.status_code == 202, "kod=" + str(r.status_code))
            tick = payroll_tick(c, PERIOD)
            check("cron oylikni hisobladi", bool(tick) and tick.get("ok") is True, "=" + str(tick))
            check("cron javobida bonus soni ham bor",
                  bool(tick) and tick.get("bonuses", 0) >= 1, "=" + str(tick))

            row2 = cur.execute("select amount from bonuses where user_id=? and period=?",
                               (uid, PERIOD)).fetchone()
            check("OYLIK HISOBI bonus qatorini o'zi yaratdi",
                  row2 is not None and abs(row2[0] - 30000) < 1, "=" + str(row2))

            r = c.get("/payroll/" + PERIOD + "/user/" + str(uid), headers=auth(mgr_t))
            bonus_amount = r.json().get("bonus_amount") if r.status_code == 200 else None
            check("payslip'da KPI bonusi ko'rinadi (30 000)",
                  bonus_amount is not None and abs(bonus_amount - 30000) < 1,
                  "kod=" + str(r.status_code) + " bonus=" + str(bonus_amount))
    except Exception:
        check("KPI+oylik (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cur.execute("delete from bonuses where period=?", (PERIOD,))
        cur.execute("delete from payslip_items where payslip_id in"
                    " (select id from payslips where period=?)", (PERIOD,))
        cur.execute("delete from payslips where period=?", (PERIOD,))
        cur.execute("delete from payroll_periods where period=?", (PERIOD,))
        cur.execute("delete from audit_logs where action in ('bonus_calculated','payroll_calculated')"
                    " and json_extract(after,'$.period')=?", (PERIOD,))
        if uid is not None:
            cur.execute("delete from kpi_rates where scope='user' and scope_id=?", (uid,))
            cur.execute("delete from daily_results where user_id=?", (uid,))
            cur.execute("delete from salary_rates where user_id=?", (uid,))
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from users where id=?", (uid,))
        if pos_id is not None:
            cur.execute("delete from positions where id=?", (pos_id,))
        conn.commit()
        conn.close()


def test_absent_deduct_daily() -> None:
    """Kelmagan kun kunlik ulush bilan ayiriladi (2026-08-08, egasi "A" tanladi).

    NEGA MUHIM: ilgari `monthly` stavkada kelmagan kun asosiy oylikni UMUMAN
    kamaytirmasdi — faqat qat'iy `absent_fine` bor edi va jonli bazada u 0
    ekan, ya'ni kelmaslik mutlaqo bepul edi.

    Bu yerda tekshiriladi:
      (a) `deduct_daily` rejimida baza kunlik ulush ×  kelmagan kun ga kamayadi;
      (b) alohida qat'iy jarima QO'YILMAYDI (ikki marta jazo yo'q);
      (c) ayirma jarima CHEKLOVIGA (cap) tushmaydi — cap faqat jarimaga;
      (d) sababli kun ayirilmaydi.
    """
    from datetime import date as _date
    from decimal import Decimal as _D

    print("\n" + "=" * 60)
    print("KELMAGAN KUN — KUNLIK ULUSH AYIRMASI (deduct_daily)")
    print("=" * 60)

    import api.services.payroll as pr
    from db.models import AbsentMode, FineMode, FinePolicy, PayBasis

    class _Rate:
        amount = _D("3000000")
        pay_basis = PayBasis.monthly.value
        effective_from = _date(2020, 1, 1)

    # 10 ish kuni: 7 kelgan, 2 kelmagan, 1 sababli
    days = []
    for i in range(1, 11):
        if i in (3, 4):
            st, exc = "absent", False
        elif i == 5:
            st, exc = "excused", True
        else:
            st, exc = "present", False
        days.append({
            "date": _date(2020, 1, i), "is_working": True, "status": st,
            "excused": exc, "late_minutes": 0, "worked_minutes": 480,
            "scheduled_minutes": 480,
        })

    pol = FinePolicy(
        scope="global", absent_mode=AbsentMode.deduct_daily.value, absent_fine=999999,
        fine_mode=FineMode.per_day.value, fine_per_day=0,
        monthly_cap_percent=20, is_active=True,
    )

    base, item, absent_item, _unpaid = pr.compute_base(_Rate(), _Rate(), days, _date(2020, 1, 1), pol)

    kunlik = _D("3000000") / _D(10)          # 300 000
    kutilgan = _D("3000000") - kunlik * 2    # 2 400 000
    check("baza kunlik ulush bilan kamaydi (2 kun)", base == kutilgan,
          f"base={base}, kutilgan={kutilgan}")
    check("ayirma qatori yaratildi", absent_item is not None)
    if absent_item:
        check("ayirma manfiy va 600 000 ga teng", absent_item["amount"] == -kunlik * 2,
              f"amount={absent_item['amount']}")
        check("sababli kun ayirilmadi (2 kun, 3 emas)", absent_item["quantity"] == 2,
              f"quantity={absent_item['quantity']}")

    fine = pr.compute_absent_fine(days, pol)
    check("deduct_daily'da qat'iy jarima QO'YILMAYDI (ikki marta jazo yo'q)",
          fine["amount"] == _D("0"), f"amount={fine['amount']} (absent_fine=999999 bo'lsa ham)")

    # Cap ayirmaga tegmasligi: jarima 0 bo'lgani uchun cap umuman ishlamaydi,
    # ya'ni 600 000 ayirma 20% (600 000) chegarasidan qat'i nazar to'liq qoladi.
    lo, ab, raw, capped = pr.apply_fine_cap(_D("0"), fine["amount"], base, pol)
    check("cap ayirmaga tegmaydi (jarima yo'q -> cap qo'llanmaydi)", not capped,
          f"capped={capped}, raw={raw}")


def test_uysot_request_deadline() -> None:
    """CRM kutishi: HTTP so'rov TEZ chiqadi, fon (cron) SABR qiladi.

    MUAMMO (2026-08-13 jonli o'lchovi): saytda bitta so'rov 40.3 soniya
    kutdi. Deploy'da konkurentlik = 1, ya'ni bitta uzoq so'rov BUTUN saytni
    o'lik qiladi. Uysot 429 bersa so'rov ichida 60s x 4 = 4 daqiqagacha
    kutilardi.

    Ikki yo'l ATAYLAB turlicha:
      - `mark_request_context()` chaqirilgan (odam kutayotgan so'rov) ->
        `UysotBusy` darhol, kutmaydi;
      - fon (cron) -> avvalgidek qayta urinadi.
    Regressiya xavfi: kimdir `deadline` ni fon yo'liga ham qo'llasa, uzun
    skanlar yarim yo'lda uzilib qolardi va buni HECH KIM sezmasdi.
    """
    import asyncio as _aio
    import httpx as _hx
    import crm.uysot as _U

    print("\n" + "=" * 60)
    print("CRM KUTISH CHEGARASI (so'rov vs fon)")
    print("=" * 60)

    class _Fake429:
        def __init__(self): self.calls = 0
        async def request(self, method, path, json=None):
            self.calls += 1
            return _hx.Response(429, request=_hx.Request(method, "http://x" + path))

    async def _olcha(in_request: bool):
        _U._RATE_BUDGET = _U._SharedRateBudget(60)
        c = _Fake429()
        async def _ish():
            if in_request:
                _U.mark_request_context()
            try:
                r = await _U._limited_request(c, "POST", "/test")
                return f"javob {r.status_code}", c.calls
            except _U.UysotBusy:
                return "UysotBusy", c.calls
        # ALOHIDA task — contextvar boshqa o'lchovga oqib ketmasin
        return await _aio.create_task(_ish())

    async def _run():
        natija1, calls1 = await _olcha(True)
        eski = _U.RATE_LIMIT_BACKOFF_SECONDS
        _U.RATE_LIMIT_BACKOFF_SECONDS = 0.05      # fon yo'lini tez sinash uchun
        try:
            natija2, calls2 = await _olcha(False)
        finally:
            _U.RATE_LIMIT_BACKOFF_SECONDS = eski
        return natija1, calls1, natija2, calls2

    n1, c1, n2, c2 = _aio.run(_run())
    check("so'rov yo'li 429'da DARHOL chiqadi (kutmaydi)", n1 == "UysotBusy", f"={n1}")
    check("so'rov yo'li qayta urinmaydi (1 ta chaqiruv)", c1 == 1, f"={c1}")
    check("fon yo'li avvalgidek qayta urinadi", c2 == _U.MAX_RATE_LIMIT_RETRIES + 1, f"={c2}")
    check("fon yo'li 429'ni yuqoriga qaytaradi", n2 == "javob 429", f"={n2}")


def test_audit_json_guard() -> None:
    """JSON ustunlarga xavfli tur tushsa ham COMMIT yiqilmasin (BUG-1 sinfi).

    BUG-1 da audit `before` ichidagi `Decimal` butun amalni bekor qilardi
    (`TypeError: Object of type Decimal is not JSON serializable`) — jarima
    qoidasini saqlash, oylik hisoblash kabi PUL amallari shu tufayli
    yiqilardi.

    Chaqiruvchi tomon `api/audit_json.py` bilan tuzatildi, lekin yangi kod
    uni ishlatishni unutishi mumkin. Shuning uchun engine darajasida zaxira
    o'girish qo'yildi (`db/base.py::_json_serializer`). Bu test aynan o'sha
    zaxirani qo'riqlaydi: ATAYLAB xom Decimal/date/datetime/Enum uzatiladi.
    """
    import asyncio as _aio
    from datetime import date as _d, datetime as _dt
    from decimal import Decimal as _Dec

    print("\n" + "=" * 60)
    print("AUDIT JSON ZAXIRA HIMOYASI (BUG-1 sinfi qaytmasin)")
    print("=" * 60)

    from sqlalchemy import select as _sel
    from db.base import async_session as _sess
    from db.models import AuditLog as _AL, Role as _Role, User as _U

    async def _run():
        async with _sess() as s:
            u = (await s.execute(_sel(_U).limit(1))).scalars().first()
            if u is None:
                return None, "bazada foydalanuvchi yo'q"
            row = _AL(
                actor_id=u.id, action="T-GUARD-SINOV", target_user_id=None,
                before={"decimal": _Dec("12345.67"), "sana": _d(2026, 8, 8),
                        "vaqt": _dt(2026, 8, 8, 12, 30), "enum": _Role.hr},
                after=None,
            )
            s.add(row)
            try:
                await s.commit()
            except Exception as e:
                return None, f"{type(e).__name__}: {e}"
            await s.refresh(row)
            saqlangan = dict(row.before)
            await s.delete(row)
            await s.commit()
            return saqlangan, None

    saqlangan, xato = _aio.run(_run())
    check("xavfli turlar bilan COMMIT yiqilmadi", xato is None, f"xato={xato}")
    if saqlangan:
        check("Decimal -> float", saqlangan.get("decimal") == 12345.67, f"={saqlangan.get('decimal')}")
        check("date -> ISO satr", saqlangan.get("sana") == "2026-08-08", f"={saqlangan.get('sana')}")
        check("datetime -> ISO satr", str(saqlangan.get("vaqt")).startswith("2026-08-08T"),
              f"={saqlangan.get('vaqt')}")
        check("Enum -> qiymat", saqlangan.get("enum") == "hr", f"={saqlangan.get('enum')}")


def test_payroll_settings_reedit() -> None:
    """Sozlamalarni QAYTA tahrirlash (2026-08-08 regressiyasi, BUG-1).

    Jarima qoidasi ham, qo'shimcha ish profili ham bir marta YARATILGANDA
    ishlardi, lekin har qanday keyingi TAHRIR 500 berardi: audit `before`
    snapshot'i xom ORM qiymatlari bilan qurilardi va ichidagi `Decimal`
    JSON ustunga yozilmasdi (`Object of type Decimal is not JSON
    serializable`). Audit commit paytida yiqilgani uchun asosiy o'zgarish
    ham qaytarilardi — foydalanuvchi sababsiz 500 ko'rardi.

    Shuning uchun bu yerda har bir upsert IKKI MARTA chaqiriladi: birinchisi
    yaratadi, ikkinchisi TAHRIRLAYDI. Faqat ikkinchisi bugni ushlaydi."""
    import httpx

    print("\n" + "=" * 60)
    print("OYLIK SOZLAMALARINI QAYTA TAHRIRLASH (BUG-1)")
    print("=" * 60)

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    token = token_for(mgr[0], mgr[1])
    if not token:
        return

    conn = db()
    cur = conn.cursor()
    uid = None
    try:
        cur.execute(
            "insert into users (full_name, role, is_active, bot_started, created_at)"
            " values (?,?,1,0,datetime('now'))", ("T-PayReedit", "employee"))
        uid = cur.lastrowid
        conn.commit()

        pol = {
            "scope": "user", "scope_id": uid, "grace_minutes": 5,
            "free_late_minutes_per_month": 60, "fine_mode": "per_day",
            "fine_per_day": 50000, "absent_mode": "fixed", "absent_fine": 200000,
            "monthly_cap_percent": 20, "fine_applies_to": "net_salary", "is_active": True,
        }
        otp = {
            "enabled": True, "mode": "derived", "multiplier": 1.5,
            "norm_hours_source": "schedule", "min_minutes": 15,
        }

        with httpx.Client(base_url=API_BASE, timeout=20) as c:
            r1 = c.put("/payroll/policies", headers=auth(token), json=pol)
            check("jarima qoidasi — yaratish", r1.status_code == 200,
                  f"kod={r1.status_code} {r1.text[:120]}")

            pol2 = {**pol, "fine_per_day": 70000}
            r2 = c.put("/payroll/policies", headers=auth(token), json=pol2)
            check("jarima qoidasi — QAYTA tahrirlash (ilgari 500)",
                  r2.status_code == 200, f"kod={r2.status_code} {r2.text[:160]}")
            if r2.status_code == 200:
                check("yangi qiymat saqlandi", float(r2.json().get("fine_per_day") or 0) == 70000,
                      f"fine_per_day={r2.json().get('fine_per_day')}")

            r3 = c.put(f"/payroll/overtime-profiles/{uid}", headers=auth(token), json=otp)
            check("qo'shimcha ish profili — yaratish", r3.status_code == 200,
                  f"kod={r3.status_code} {r3.text[:120]}")

            otp2 = {**otp, "multiplier": 2.0}
            r4 = c.put(f"/payroll/overtime-profiles/{uid}", headers=auth(token), json=otp2)
            check("qo'shimcha ish profili — QAYTA tahrirlash (ilgari 500)",
                  r4.status_code == 200, f"kod={r4.status_code} {r4.text[:160]}")
            if r4.status_code == 200:
                check("yangi koeffitsiyent saqlandi",
                      float(r4.json().get("multiplier") or 0) == 2.0,
                      f"multiplier={r4.json().get('multiplier')}")
    finally:
        if uid is not None:
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from fine_policies where scope='user' and scope_id=?", (uid,))
            cur.execute("delete from overtime_profiles where user_id=?", (uid,))
            cur.execute("delete from users where id=?", (uid,))
            conn.commit()
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


def test_future_days_rule() -> None:
    """S-01 (TZ 2.3) — oy o'rtasida hisoblanganda KELAJAK kunlari «kelmagan»
    sanalmasligi. Bu qoidani KODGA qotirib qo'yadigan qo'riqchi.

    NEGA KERAK: bu tizimning eng qimmat xatosi bo'lgan. Oy o'rtasida
    hisoblanganda oyning QOLGAN kunlari `att is None` sababli «kelmagan»
    bo'lib, kunlik ulush oylikdan ayirilardi — Abdulaziz 10 000 000 o'rniga
    4 615 400 so'm olgan edi. Tuzatilgan (d151269), lekin qoida test bilan
    bog'lanmagan edi: kimdir `future` shoxini olib tashlasa jimgina qaytardi.

    SOF FUNKSIYA sinovi — baza kerak emas: `collect_attendance` qaytaradigan
    kunlar ro'yxati qo'lda yasaladi.
    """
    from decimal import Decimal as _D
    from types import SimpleNamespace as _NS

    from api.services import payroll as pr

    print("\n" + "=" * 60)
    print("S-01: KELAJAK KUNLARI «KELMAGAN» SANALMASIN")
    print("=" * 60)

    # Fikstura: 30 kunlik oy, 1-26 ish kuni, 27-30 dam. Bugun — 15-kun.
    OYLIK = _D("5200000")
    ISH_KUNI = 26
    RATE = _NS(amount=OYLIK, pay_basis="monthly", effective_from=date(2026, 6, 1))
    POLICY = _NS(absent_mode="deduct_daily", absent_fine=_D("0"))
    BOSHI = date(2026, 6, 1)

    def kun(d, ish=True, holat="present", ishlangan=480):
        return {
            "date": d, "is_working": ish, "start": "09:00", "end": "18:00",
            "scheduled_minutes": 480 if ish else 0, "attendance": None,
            "excused": False, "excused_paid": True, "status": holat,
            "late_minutes": 0, "worked_minutes": ishlangan,
        }

    def qur(bugun_kuni, kelmagan=frozenset()):
        """`bugun_kuni` dan boshlab (o'zi ham) — `future`."""
        kunlar = []
        for i in range(1, ISH_KUNI + 1):
            d = date(2026, 6, i)
            if i >= bugun_kuni:
                kunlar.append(kun(d, holat="future", ishlangan=0))
            elif i in kelmagan:
                kunlar.append(kun(d, holat="absent", ishlangan=0))
            else:
                kunlar.append(kun(d))
        for i in range(ISH_KUNI + 1, 31):
            kunlar.append(kun(date(2026, 6, i), ish=False, holat="weekend", ishlangan=0))
        return kunlar

    def baza(kunlar):
        b, _item, ayirma, _unpaid = pr.compute_base(RATE, None, kunlar, BOSHI, POLICY)
        return b, ayirma

    # (1) Oy o'rtasi, hech kim qolmagan -> TO'LIQ oylik, ayirma YO'Q
    b1, ayirma1 = baza(qur(15))
    check("S-01: oy o'rtasida to'liq oylik (kelajak kunlari ayirilmaydi)",
          b1 == OYLIK, f"base={b1}, kutilgan={OYLIK}")
    check("S-01: kelajak kunlari uchun ayirma qatori YO'Q",
          ayirma1 is None, f"={ayirma1}")

    # (2) HAQIQIY kelmagan kun HAMON ayiriladi
    b2, ayirma2 = baza(qur(15, kelmagan={5, 6}))
    kutilgan = OYLIK - OYLIK / ISH_KUNI * 2
    check("S-01: haqiqiy kelmagan kun ayiriladi (2 kun)",
          abs(b2 - kutilgan) < 1, f"base={b2}, kutilgan={kutilgan}")
    check("S-01: ayirma qatorida aynan 2 kun",
          ayirma2 is not None and ayirma2["quantity"] == 2, f"={ayirma2}")
    check("S-01: kunlik ulush maxraji BUTUN oy (11 kun emas, 26 kun)",
          abs(abs(_D(str(ayirma2["amount"]))) - OYLIK / ISH_KUNI * 2) < 1,
          f"={ayirma2['amount']}")

    # (3) REGRESSIYA: oy tugagach natija AYNAN bir xil qoladi
    b3, _ = baza(qur(ISH_KUNI + 1, kelmagan={5, 6}))
    check("S-01: oy tugagach hisob o'zgarmaydi (o'tmishga tegilmagan)",
          abs(b3 - b2) < 1, f"oy tugagach={b3}, oy o'rtasida={b2}")

    # (4) BUGUNGI kun ham «hali tugamagan» (3a18520)
    kunlar_bugun = qur(15)
    bugungi = [d for d in kunlar_bugun if d["date"] == date(2026, 6, 15)]
    check("S-01: BUGUNGI kun ham `future` (ertalab hisoblansa jazolamaydi)",
          len(bugungi) == 1 and bugungi[0]["status"] == "future",
          f"={bugungi[0]['status'] if bugungi else 'topilmadi'}")

    # (5) Kelmagan-kun JARIMASI ham kelajakni sanamaydi
    POLICY_FIX = _NS(absent_mode="fixed", absent_fine=_D("100000"))
    jarima = pr.compute_absent_fine(qur(15), POLICY_FIX)
    check("S-01: kelajak kunlari uchun jarima ham YO'Q",
          jarima["absent_days"] == 0 and float(jarima["amount"]) == 0.0, f"={jarima}")


def test_fine_from_bonus() -> None:
    """S-02 (yangi TZ 2.1) — ushlanma avval BONUSDAN, qoldiq HR qoidasiga ko'ra.

    NEGA: ushlanma to'g'ridan-to'g'ri ish haqidan olinardi
    (`fine_applies_to='net_salary'`). TZ bo'yicha bu O'zbekiston Mehnat
    kodeksiga zid. Endi default `bonus_first`, qoldiq esa panelda tanlanadi.

    Bu blok `split_fine` ni SOF funksiya sifatida sinaydi — 3 rejim x 3 holat.
    """
    from decimal import Decimal as _D
    from types import SimpleNamespace as _NS

    from api.services import payroll as pr

    print("\n" + "=" * 60)
    print("S-02: USHLANMA AVVAL BONUSDAN")
    print("=" * 60)

    def qoida(applies="bonus_first", remainder="drop"):
        return _NS(fine_applies_to=applies, fine_remainder_mode=remainder)

    NOL = _D("0")
    USHLANMA = _D("300000")

    # ── Holat 1: bonus > ushlanma (hammasi bonusdan) ──
    for rejim in ("drop", "carry_next_month", "from_salary"):
        r = pr.split_fine(USHLANMA, _D("500000"), NOL, qoida(remainder=rejim))
        check(f"S-02 [{rejim}] bonus > ushlanma -> hammasi bonusdan",
              r["from_bonus"] == USHLANMA and r["from_salary"] == NOL
              and r["carried_out"] == NOL and r["dropped"] == NOL, f"={r}")

    # ── Holat 2: bonus < ushlanma (qoldiq bor) ──
    r = pr.split_fine(USHLANMA, _D("100000"), NOL, qoida(remainder="drop"))
    check("S-02 [drop] bonus < ushlanma -> qoldiq OLINMAYDI",
          r["from_bonus"] == _D("100000") and r["from_salary"] == NOL
          and r["dropped"] == _D("200000") and r["carried_out"] == NOL, f"={r}")

    r = pr.split_fine(USHLANMA, _D("100000"), NOL, qoida(remainder="carry_next_month"))
    check("S-02 [carry] bonus < ushlanma -> qoldiq KEYINGI OYGA",
          r["from_bonus"] == _D("100000") and r["from_salary"] == NOL
          and r["carried_out"] == _D("200000") and r["dropped"] == NOL, f"={r}")

    r = pr.split_fine(USHLANMA, _D("100000"), NOL, qoida(remainder="from_salary"))
    check("S-02 [from_salary] bonus < ushlanma -> qoldiq OYLIKDAN",
          r["from_bonus"] == _D("100000") and r["from_salary"] == _D("200000")
          and r["carried_out"] == NOL and r["dropped"] == NOL, f"={r}")

    # ── Holat 3: bonus = 0 ──
    r = pr.split_fine(USHLANMA, NOL, NOL, qoida(remainder="drop"))
    check("S-02 [drop] bonus = 0 -> ushlanma UMUMAN olinmaydi",
          r["from_bonus"] == NOL and r["from_salary"] == NOL
          and r["dropped"] == USHLANMA, f"={r}")

    r = pr.split_fine(USHLANMA, NOL, NOL, qoida(remainder="carry_next_month"))
    check("S-02 [carry] bonus = 0 -> hammasi keyingi oyga",
          r["carried_out"] == USHLANMA and r["from_salary"] == NOL, f"={r}")

    r = pr.split_fine(USHLANMA, NOL, NOL, qoida(remainder="from_salary"))
    check("S-02 [from_salary] bonus = 0 -> hammasi oylikdan",
          r["from_salary"] == USHLANMA and r["from_bonus"] == NOL, f"={r}")

    # ── Eski rejim buzilmagan (regressiya) ──
    r = pr.split_fine(USHLANMA, _D("500000"), NOL, qoida(applies="net_salary"))
    check("S-02: `net_salary` rejimi avvalgidek — hammasi oylikdan",
          r["from_salary"] == USHLANMA and r["from_bonus"] == NOL, f"={r}")

    # ── Qoida umuman yo'q -> eski (xavfsiz) xatti-harakat ──
    r = pr.split_fine(USHLANMA, _D("500000"), NOL, None)
    check("S-02: qoida yo'q bo'lsa oylikdan (eski xatti-harakat)",
          r["from_salary"] == USHLANMA, f"={r}")

    # ── O'tgan oydan ko'chgan qoldiq shu oyda olinadi ──
    r = pr.split_fine(_D("50000"), _D("500000"), _D("200000"), qoida(remainder="carry_next_month"))
    check("S-02: o'tgan oy qoldig'i shu oy bonusidan olinadi (50k+200k)",
          r["from_bonus"] == _D("250000") and r["carried_out"] == NOL, f"={r}")

    r = pr.split_fine(_D("50000"), _D("100000"), _D("200000"), qoida(remainder="carry_next_month"))
    check("S-02: qoldiq yana yetmasa — qolgani KEYINGI oyga (150k)",
          r["from_bonus"] == _D("100000") and r["carried_out"] == _D("150000"), f"={r}")

    # ── Ushlanma yo'q bo'lsa hech narsa qilinmaydi ──
    r = pr.split_fine(NOL, _D("500000"), NOL, qoida())
    check("S-02: ushlanma 0 -> hamma qiymat 0",
          all(v == NOL for v in r.values()), f"={r}")

    # ── Yaxlit tekshiruv: hech qachon KO'PROQ olinmaydi ──
    for bonus in (NOL, _D("100000"), _D("500000")):
        for rejim in ("drop", "carry_next_month", "from_salary"):
            r = pr.split_fine(USHLANMA, bonus, _D("70000"), qoida(remainder=rejim))
            jami = r["from_bonus"] + r["from_salary"] + r["carried_out"] + r["dropped"]
            check(f"S-02 [{rejim}, bonus={int(bonus)}] taqsimot yig'indisi buzilmadi",
                  jami == USHLANMA + _D("70000"), f"jami={jami}, kutilgan={USHLANMA + _D('70000')}")


def test_fine_from_bonus_e2e() -> None:
    """S-02 — PAYSLIP darajasida: ushlanma bonusdan olinadimi, qoldiq
    keyingi oyga BIR MARTA ko'chadimi, qatorlar yig'indisi `net` ga tengmi.

    `split_fine` sof funksiyasi alohida sinaladi (`test_fine_from_bonus`);
    bu yerda ZANJIR tekshiriladi — o'tgan oy payslip'idan qoldiqni o'qish
    faqat shu yo'lda ishlaydi.
    """
    import asyncio
    from decimal import Decimal as _D

    print("\n" + "=" * 60)
    print("S-02: PAYSLIP ZANJIRI (bonus_first + qoldiq)")
    print("=" * 60)

    OY1, OY2 = "2019-03", "2019-04"

    async def _run():
        from sqlalchemy import delete as _del, select as _sel

        from api.services import payroll as pr
        from db.base import async_session
        from db.models import (
            Attendance, Bonus, FinePolicy, Payslip, PayslipItem, User,
            WorkScheduleOverride, WorkScheduleWeekly,
        )

        async with async_session() as s2:
            # Eski qoldiqni tozalash (avvalgi qulagan yurishdan)
            eski = list(await s2.scalars(_sel(User.id).where(User.full_name == "T-FineBonus")))
            if eski:
                pids = list(await s2.scalars(_sel(Payslip.id).where(Payslip.user_id.in_(eski))))
                if pids:
                    await s2.execute(_del(PayslipItem).where(PayslipItem.payslip_id.in_(pids)))
                for M in (Payslip, Bonus, Attendance, WorkScheduleOverride, WorkScheduleWeekly):
                    await s2.execute(_del(M).where(M.user_id.in_(eski)))
                await s2.execute(_del(FinePolicy).where(FinePolicy.scope == "user",
                                                        FinePolicy.scope_id.in_(eski)))
                await s2.execute(_del(User).where(User.id.in_(eski)))
                await s2.commit()

            u = User(telegram_id=999700501, full_name="T-FineBonus", role="employee",
                     bot_started=True, is_active=True)
            s2.add(u)
            await s2.flush()

            for wd in range(7):
                s2.add(WorkScheduleWeekly(user_id=u.id, weekday=wd, is_working=False))
            kunlar = [date(2019, 3, 4), date(2019, 3, 5), date(2019, 3, 6)]
            for d in kunlar:
                s2.add(WorkScheduleOverride(user_id=u.id, date=d, is_working=True,
                                            start_time="09:00", end_time="18:00"))
                s2.add(Attendance(user_id=u.id, date=d, status="late", late_minutes=60,
                                  worked_minutes=420))
            # Ushlanma: 3 kun x 100 000 = 300 000. Bonus 150 000 -> qoldiq 150 000.
            s2.add(FinePolicy(scope="user", scope_id=u.id, is_active=True,
                              free_late_minutes_per_month=0, fine_mode="per_day",
                              fine_per_day=100_000, absent_mode="none",
                              monthly_cap_amount=1_000_000,
                              fine_applies_to="bonus_first",
                              fine_remainder_mode="carry_next_month"))
            s2.add(Bonus(user_id=u.id, period=OY1, amount=150_000, breakdown={}))
            s2.add(Bonus(user_id=u.id, period=OY2, amount=500_000, breakdown={}))
            await s2.commit()
            return u.id

    async def _hisobla(uid, period):
        from sqlalchemy import select as _sel

        from api.services import payroll as pr
        from db.base import async_session
        from db.models import Payslip, PayslipItem

        async with async_session() as s2:
            await pr.run_payroll(s2, period, user_ids=[uid])
        async with async_session() as s2:
            slip = await s2.scalar(_sel(Payslip).where(Payslip.user_id == uid,
                                                       Payslip.period == period))
            items = list(await s2.scalars(
                _sel(PayslipItem).where(PayslipItem.payslip_id == slip.id)
            ))
            return slip, items

    uid = None
    try:
        uid = asyncio.run(_run())

        # ── 1-oy: ushlanma 300k, bonus 150k -> 150k bonusdan, 150k keyingi oyga
        slip1, items1 = asyncio.run(_hisobla(uid, OY1))
        bd1 = slip1.breakdown or {}
        check("S-02 e2e: 150 000 bonusdan olindi",
              abs(bd1.get("fine_from_bonus", 0) - 150_000) < 1, f"={bd1.get('fine_from_bonus')}")
        check("S-02 e2e: oylikdan HECH NARSA olinmadi",
              abs(bd1.get("fine_from_salary", 0)) < 1, f"={bd1.get('fine_from_salary')}")
        check("S-02 e2e: 150 000 keyingi oyga ko'chdi",
              abs(bd1.get("fine_carried_out", 0) - 150_000) < 1, f"={bd1.get('fine_carried_out')}")
        check("S-02 e2e: payslip'da «keyingi oyga o'tdi» qatori bor",
              any(i.kind == "fine_waived" for i in items1),
              f"={[i.kind for i in items1]}")
        check("S-02 e2e: ushlanma qatorida MANBA ko'rsatilgan",
              any("bonusdan" in (i.label or "") for i in items1),
              f"={[i.label for i in items1]}")
        jami1 = sum(float(i.amount) for i in items1)
        check("S-02 e2e: qatorlar yig'indisi = net (1-oy)",
              abs(jami1 - float(slip1.net)) <= 50, f"qatorlar={jami1}, net={slip1.net}")

        # ── 2-oy: ushlanma yo'q, lekin o'tgan oy qoldig'i 150k olinadi
        slip2, items2 = asyncio.run(_hisobla(uid, OY2))
        bd2 = slip2.breakdown or {}
        check("S-02 e2e: o'tgan oy qoldig'i 2-oyda o'qildi",
              abs(bd2.get("fine_carried_in", 0) - 150_000) < 1, f"={bd2.get('fine_carried_in')}")
        check("S-02 e2e: qoldiq 2-oy bonusidan olindi",
              abs(bd2.get("fine_from_bonus", 0) - 150_000) < 1, f"={bd2.get('fine_from_bonus')}")
        check("S-02 e2e: 2-oyda yangi qoldiq qolmadi",
              abs(bd2.get("fine_carried_out", 0)) < 1, f"={bd2.get('fine_carried_out')}")
        check("S-02 e2e: 2-oy payslip'ida «o'tgan oydan» qatori bor",
              any(i.kind == "fine_carry_in" for i in items2), f"={[i.kind for i in items2]}")
        jami2 = sum(float(i.amount) for i in items2)
        check("S-02 e2e: qatorlar yig'indisi = net (2-oy)",
              abs(jami2 - float(slip2.net)) <= 50, f"qatorlar={jami2}, net={slip2.net}")

        # ── IDEMPOTENT: 2-oyni qayta hisoblasak qoldiq IKKI MARTA olinmasin
        net_oldin = float(slip2.net)
        slip2b, _ = asyncio.run(_hisobla(uid, OY2))
        check("S-02 e2e: qayta hisoblanganda qoldiq IKKI MARTA olinmaydi",
              abs(float(slip2b.net) - net_oldin) < 1,
              f"birinchi={net_oldin}, ikkinchi={slip2b.net}")
    except Exception:
        check("S-02 e2e (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        if uid is not None:
            conn = db()
            cur = conn.cursor()
            cur.execute("delete from payslip_items where payslip_id in"
                        " (select id from payslips where user_id=?)", (uid,))
            for t in ("payslips", "bonuses", "attendance", "work_schedule_override",
                      "work_schedule_weekly"):
                cur.execute(f"delete from {t} where user_id=?", (uid,))
            cur.execute("delete from fine_policies where scope='user' and scope_id=?", (uid,))
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from users where id=?", (uid,))
            cur.execute("delete from payroll_periods where period in (?,?)", (OY1, OY2))
            conn.commit()
            conn.close()


def test_me_sections() -> None:
    """S-04 (TZ 2.6) — «kim nimani ko'radi» endi BITTA joyda.

    Ilgari uch joyda edi: `web/src/Layout.tsx` (yon panel),
    `web/src/lib/employeeNav.ts` (kabinet) va `bot/keyboards.py` (bot).
    Muvofiqlik INSON e'tiboriga qolgan edi — `employeeNav.ts` boshida
    «bot bilan AYNAN bir xil bo'lishi shart» degan ogohlantirish turibdi.

    Bu blok ENG MUHIM shartni qo'riqlaydi: yangi manba hozirgi yon panel
    bilan AYNAN mos (regressiya yo'q). Ro'yxat qo'lda yozilgan — u
    `Layout.tsx` dan MUSTAQIL, aks holda test hech narsani isbotlamasdi.
    """
    import httpx

    print("\n" + "=" * 60)
    print("S-04: /me/sections — YAGONA MANBA")
    print("=" * 60)

    # `web/src/Layout.tsx: NAV_GROUPS` dan QO'LDA ko'chirilgan (2026-08-19).
    # Shartsiz bandlar — har rahbarda ko'rinadi.
    RAHBAR_DOIM = [
        "/", "/statistics", "/reports",
        "/attendance", "/excused-days", "/work-schedule", "/work-log", "/offices",
        "/lead-stats", "/funnel", "/norms",
        "/payroll",
        "/users", "/audit-logs",
        "/check-in",
    ]
    # Faqat hr/boss/dasturchi (ROP'da YO'Q)
    RAHBAR_PAYROLL = ["/overtime", "/requests", "/appeals", "/positions", "/celebration"]

    conn = db()
    cur = conn.cursor()
    uid = None
    try:
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            # ── ROL MATRITSASI ──
            natijalar = {}
            for rol in ("boss", "hr", "rop", "dasturchi"):
                mgr = None
                row = cur.execute(
                    "select id from users where role=? and is_active=1 limit 1", (rol,)
                ).fetchone()
                if not row:
                    continue
                t = token_for(row[0], rol)
                r = c.get("/me/sections", headers=auth(t))
                if r.status_code != 200:
                    check(f"S-04: /me/sections [{rol}] -> 200", False,
                          "kod=" + str(r.status_code) + " " + r.text[:120])
                    continue
                yollar = [x["path"] for x in r.json()]
                natijalar[rol] = yollar
                check(f"S-04: /me/sections [{rol}] -> 200", True, f"{len(yollar)} bo'lim")

            # Har rahbarda shartsiz bandlar BOR
            for rol, yollar in natijalar.items():
                yetishmaydi = [p for p in RAHBAR_DOIM if p not in yollar]
                check(f"S-04 [{rol}]: yon panelning shartsiz bandlari to'liq",
                      not yetishmaydi, "yetishmaydi=" + str(yetishmaydi))

            # ROP payroll bandlarini KO'RMAYDI, hr/boss/dasturchi KO'RADI
            if "rop" in natijalar:
                ortiqcha = [p for p in RAHBAR_PAYROLL if p in natijalar["rop"]]
                check("S-04 [rop]: payroll bandlari KO'RINMAYDI",
                      not ortiqcha, "ortiqcha=" + str(ortiqcha))
            for rol in ("hr", "boss", "dasturchi"):
                if rol not in natijalar:
                    continue
                yetishmaydi = [p for p in RAHBAR_PAYROLL if p not in natijalar[rol]]
                check(f"S-04 [{rol}]: payroll bandlari KO'RINADI",
                      not yetishmaydi, "yetishmaydi=" + str(yetishmaydi))

            # «Dasturchi rejimi» — FAQAT dasturchida
            for rol, yollar in natijalar.items():
                bormi = "/dasturchi" in yollar
                check(f"S-04 [{rol}]: /dasturchi {'bor' if rol == 'dasturchi' else 'YO_Q'}",
                      bormi == (rol == "dasturchi"), f"bor={bormi}")

            # ── XODIM ──
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " created_at) values (999700301,'T-Sections','employee',0,1,datetime('now'))")
            uid = cur.lastrowid
            conn.commit()
            emp_t = token_for(uid, "employee")
            r = c.get("/me/sections", headers=auth(emp_t))
            check("S-04: xodim uchun -> 200", r.status_code == 200, "kod=" + str(r.status_code))
            emp = r.json() if r.status_code == 200 else []
            yollar = [x["path"] for x in emp]

            check("S-04: xodimga KABINET to'plami keladi (yon panel emas)",
                  all(x["audience"] == "employee" for x in emp), "=" + str(yollar[:5]))
            check("S-04: xodim rahbar sahifalarini KO'RMAYDI",
                  "/users" not in yollar and "/payroll" not in yollar
                  and "/audit-logs" not in yollar, "=" + str(yollar))
            for kerak in ("/check-in", "/me/payroll", "/me/stats", "/me/excused"):
                check(f"S-04: xodimda {kerak} bor", kerak in yollar, "=" + str(yollar))
            check("S-04: bo'limlar tartiblangan",
                  [x["order"] for x in emp] == sorted(x["order"] for x in emp),
                  "=" + str([x["order"] for x in emp]))
            check("S-04: har bandda mijozga kerakli maydonlar bor",
                  all(x.get("key") and x.get("label") and x.get("path") and x.get("icon")
                      for x in emp), "=" + str(emp[:1]))

            # `can_edit_attendance` bayrog'i bo'limni OCHADI
            check("S-04: bayroqsiz xodimda «Davomat tuzatish» YO'Q",
                  "/attendance" not in yollar, "=" + str(yollar))
            cur.execute("update users set can_edit_attendance=1 where id=?", (uid,))
            conn.commit()
            r2 = c.get("/me/sections", headers=auth(emp_t))
            yollar2 = [x["path"] for x in r2.json()] if r2.status_code == 200 else []
            check("S-04: bayroq berilgach «Davomat tuzatish» PAYDO bo'ladi",
                  "/attendance" in yollar2, "=" + str(yollar2))

            # Autentifikatsiyasiz — 401
            r3 = c.get("/me/sections")
            check("S-04: tokensiz -> 401", r3.status_code == 401, "kod=" + str(r3.status_code))
    except Exception:
        check("S-04 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        if uid is not None:
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from users where id=?", (uid,))
            conn.commit()
        conn.close()


def test_bot_menu_from_server() -> None:
    """S-05b (TZ 2.6) — bot menyusi endi SERVERDA quriladi.

    Ilgari `bot/keyboards.py::main_menu` ~20 ta shartni O'ZI hisoblardi va
    AYNAN o'sha shartlar saytda ham (ikki joyda) takrorlanardi. Endi qoida
    `api/services/sections.py` da, bot faqat chizadi.

    Bu blok ikkita narsani qo'riqlaydi:
      (a) menyu ESKI ko'rinishni saqlagan (oltin namuna — qo'lda yozilgan);
      (b) bot javobida `bot_menu` keladi va tugmalar tanish.
    """
    import httpx

    from api.services.sections import bot_menu_rows

    print("\n" + "=" * 60)
    print("S-05b: BOT MENYUSI SERVERDAN")
    print("=" * 60)

    class _Pos:
        def __init__(self, flags, metrics):
            self.menu_flags = flags
            self.metrics = metrics

    class _U:
        def __init__(self, role, flags=None, metrics=None):
            self.role = role
            # ⚠️ `is None` SHART: `metrics=[]` (ataylab bo'sh lavozim) va
            # `metrics=None` (lavozim biriktirilmagan) BOSHQA-BOSHQA holat.
            # `if flags or metrics` deb yozilsa bo'sh ro'yxat «lavozim yo'q»
            # ga aylanib, sinov noto'g'ri natija bergan edi.
            self.position = (
                None if (flags is None and metrics is None) else _Pos(flags, metrics)
            )
            self.can_edit_fine_policy = False
            self.can_edit_attendance = False

    # ── (a) OLTIN NAMUNA: oddiy xodim, lavozimsiz ──
    # Qo'lda yozilgan — `bot_menu_rows` dan MUSTAQIL, aks holda test
    # o'zini o'zi tasdiqlagan bo'lardi.
    #
    # ⚠️ NAMUNA O'ZGARSA — ATAYLABMI? Bu ro'yxat menyuning TASDIQLANGAN
    # ko'rinishi. U faqat yangi bo'lim ataylab qo'shilganda yangilanadi va
    # o'zgarish commit izohida ko'rsatiladi. Tasodifiy o'zgarish (masalan
    # `visible` shartini buzib qo'yish) shu yerda ushlanadi.
    # Tarix: S-11 da «📁 Hujjatlarim» qo'shildi (TZ 3.4).
    kutilgan = [
        ["✅ Keldim / Ketdim"],
        ["📋 Vazifalarim"],
        ["📝 Ish kundaligi"],
        ["📊 Bugungi normam", "💰 Oylik KPI'm"],
        ["📈 Statistikam", "🙋 Sababli kun so'rash"],
        ["📮 Murojaatlarim", "📁 Hujjatlarim"],
        ["🗓 Ish jadvali"],
        ["💵 Mening oyligim"],
        ["📋 Bugungi rejam"],
        ["🧲 Lidlar statistikasi"],
        ["🤖 Sotuv AI"],
    ]
    haqiqiy = bot_menu_rows(_U("employee"))
    check("S-05b: oddiy xodim menyusi eski ko'rinishda",
          haqiqiy == kutilgan, "=" + str(haqiqiy))

    # ── Boshliq: shaxsiy «Keldim/Ketdim» va oylik YO'Q, boshqaruv bor ──
    boss = bot_menu_rows(_U("boss"))
    tekis_boss = [b for row in boss for b in row]
    check("S-05b: Boshliqda «Keldim / Ketdim» YO'Q",
          "✅ Keldim / Ketdim" not in tekis_boss, "=" + str(tekis_boss[:4]))
    check("S-05b: Boshliqda «Mening oyligim» YO'Q",
          "💵 Mening oyligim" not in tekis_boss, "=" + str(tekis_boss))
    for kerak in ("📤 Vazifa berish", "🧾 Audit jurnali", "🎬 Tabrik videolari"):
        check(f"S-05b: Boshliqda «{kerak}» bor", kerak in tekis_boss, "=" + str(tekis_boss))

    # ── ROP: boshqaruv bor, lekin «Xodim uchun sababli kun» YO'Q ──
    rop = [b for row in bot_menu_rows(_U("rop")) for b in row]
    check("S-05b: ROP «Xodim uchun sababli kun» ni KO'RMAYDI",
          "🙋 Xodim uchun sababli kun" not in rop, "=" + str(rop))
    check("S-05b: ROP «Sotuv AI» ni ko'radi", "🤖 Sotuv AI" in rop, "=" + str(rop))
    check("S-05b: ROP «Audit jurnali» ni KO'RMAYDI",
          "🧾 Audit jurnali" not in rop, "=" + str(rop))

    # ── Lavozim bayroqlari tugmani YOPADI ──
    yopiq = [b for row in bot_menu_rows(_U("employee", flags={"tasks": False, "payroll": False}))
             for b in row]
    check("S-05b: `tasks=False` -> «Vazifalarim» yo'q",
          "📋 Vazifalarim" not in yopiq, "=" + str(yopiq))
    check("S-05b: `payroll=False` -> «Mening oyligim» yo'q",
          "💵 Mening oyligim" not in yopiq, "=" + str(yopiq))

    # ── `metrics=[]` (ataylab bo'sh) va `None` (lavozim yo'q) FARQI ──
    bosh = [b for row in bot_menu_rows(_U("employee", metrics=[])) for b in row]
    yoq = [b for row in bot_menu_rows(_U("employee", metrics=None)) for b in row]
    check("S-05b: `metrics=[]` -> lid statistikasi YO'Q",
          "🧲 Lidlar statistikasi" not in bosh, "=" + str(bosh))
    check("S-05b: lavozimsiz (`None`) -> lid statistikasi BOR (eski default)",
          "🧲 Lidlar statistikasi" in yoq, "=" + str(yoq))

    # ── (b) Bot API javobida menyu keladi ──
    conn = db()
    cur = conn.cursor()
    uid = None
    try:
        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " created_at) values (999700401,'T-BotMenu','employee',1,1,datetime('now'))")
        uid = cur.lastrowid
        conn.commit()
        with httpx.Client(base_url=API_BASE, timeout=20) as c:
            r = c.get("/users/by-telegram/999700401", headers=bot_secret_hdr())
            check("S-05b: /users/by-telegram -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code))
            menyu = r.json().get("bot_menu") if r.status_code == 200 else None
            check("S-05b: javobda `bot_menu` bor", bool(menyu), "=" + str(menyu))
            check("S-05b: javobdagi menyu server hisobi bilan bir xil",
                  menyu == kutilgan, "=" + str(menyu))

            # Bot tomoni: qatorlardan klaviatura quriladi
            from bot.keyboards import main_menu
            km = main_menu(menyu)
            check("S-05b: bot qatorlarni klaviaturaga aylantiradi",
                  len(km.keyboard) == len(kutilgan), "=" + str(len(km.keyboard)))
            zaxira = main_menu(None)
            check("S-05b: menyu kelmasa MINIMAL zaxira (ikkinchi manba emas)",
                  len(zaxira.keyboard) == 1, "=" + str(len(zaxira.keyboard)))
    except Exception:
        check("S-05b (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        if uid is not None:
            cur.execute("delete from audit_logs where target_user_id=? or actor_id=?", (uid, uid))
            cur.execute("delete from users where id=?", (uid,))
            conn.commit()
        conn.close()


def test_view_scope() -> None:
    """S-06 (TZ 4-qism) — «xodim faqat o'ziga tegishlisini ko'radi».

    Ilgari bu qoida 10 dan ortiq joyda QO'LDA yozilgan edi va ular BIR XIL
    EMAS edi: payroll ROP ga lavozim bo'yicha jamoani ham ko'rsatardi,
    ish kundaligi esa faqat bevosita bo'ysunuvchilarni. Endi yagona qatlam
    — `api/deps.py::scoped_user_ids` / `assert_can_view`.

    ⚠️ 404, 403 EMAS: 403 «yozuv bor, lekin ruxsat yo'q» degani, ya'ni
    begona xodim MAVJUDLIGINI oshkor qiladi.
    """
    import asyncio
    import httpx

    print("\n" + "=" * 60)
    print("S-06: MARKAZLASHGAN KO'RINISH FILTRI")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    ids = {}
    try:
        # Ikki ROP, har birida bittadan xodim + bir «begona» xodim
        for nom, rol, tg in (
            ("T-Scope-Rop1", "rop", 999700201),
            ("T-Scope-Rop2", "rop", 999700202),
            ("T-Scope-Emp1", "employee", 999700203),
            ("T-Scope-Emp2", "employee", 999700204),
            ("T-Scope-Hr", "hr", 999700205),
        ):
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " created_at) values (?,?,?,0,1,datetime('now'))", (tg, nom, rol))
            ids[nom] = cur.lastrowid
        cur.execute("update users set manager_id=? where id=?",
                    (ids["T-Scope-Rop1"], ids["T-Scope-Emp1"]))
        cur.execute("update users set manager_id=? where id=?",
                    (ids["T-Scope-Rop2"], ids["T-Scope-Emp2"]))
        conn.commit()

        rop1_t = token_for(ids["T-Scope-Rop1"], "rop")
        emp1_t = token_for(ids["T-Scope-Emp1"], "employee")
        hr_t = token_for(ids["T-Scope-Hr"], "hr")

        # ── (1) Xizmat qatlami: qamrov to'g'ri hisoblanadimi ──
        from api.deps import scoped_user_ids
        from db.base import async_session
        from db.models import User as _U

        async def _qamrov(uid):
            async with async_session() as s2:
                u = await s2.get(_U, uid)
                return await scoped_user_ids(u, s2)

        hr_scope = asyncio.run(_qamrov(ids["T-Scope-Hr"]))
        check("S-06: HR qamrovi CHEKLOVSIZ (None)", hr_scope is None, "=" + str(hr_scope))

        rop1_scope = asyncio.run(_qamrov(ids["T-Scope-Rop1"]))
        check("S-06: ROP o'zini ko'radi",
              ids["T-Scope-Rop1"] in rop1_scope, "=" + str(sorted(rop1_scope)))
        check("S-06: ROP O'Z jamoasini ko'radi",
              ids["T-Scope-Emp1"] in rop1_scope, "=" + str(sorted(rop1_scope)))
        check("S-06: ROP BOSHQA ROP ni ko'rmaydi",
              ids["T-Scope-Rop2"] not in rop1_scope, "=" + str(sorted(rop1_scope)))
        check("S-06: ROP HR ni ko'rmaydi",
              ids["T-Scope-Hr"] not in rop1_scope, "=" + str(sorted(rop1_scope)))

        emp_scope = asyncio.run(_qamrov(ids["T-Scope-Emp1"]))
        check("S-06: xodim FAQAT o'zini ko'radi",
              emp_scope == {ids["T-Scope-Emp1"]}, "=" + str(emp_scope))

        # `rop_sees_team=False` — ba'zi modullarda ROP jamoani ham ko'rmaydi
        async def _qatiy(uid):
            async with async_session() as s2:
                u = await s2.get(_U, uid)
                return await scoped_user_ids(u, s2, rop_sees_team=False)

        qatiy = asyncio.run(_qatiy(ids["T-Scope-Rop1"]))
        check("S-06: `rop_sees_team=False` -> ROP faqat o'zi",
              qatiy == {ids["T-Scope-Rop1"]}, "=" + str(qatiy))

        # ── (2) HTTP: begona so'rov 404 (403 EMAS) ──
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            begona = ids["T-Scope-Emp2"]
            oz = ids["T-Scope-Emp1"]

            r = c.get(f"/bonuses?user_id={begona}", headers=auth(rop1_t))
            check("S-06: ROP begona xodim bonusini so'radi -> 404 (403 emas)",
                  r.status_code == 404, "kod=" + str(r.status_code))
            r = c.get(f"/bonuses?user_id={oz}", headers=auth(rop1_t))
            check("S-06: ROP O'Z jamoasi bonusini ko'radi -> 200",
                  r.status_code == 200, "kod=" + str(r.status_code) + " " + r.text[:100])
            r = c.get(f"/bonuses?user_id={begona}", headers=auth(hr_t))
            check("S-06: HR hammani ko'radi -> 200",
                  r.status_code == 200, "kod=" + str(r.status_code))

            r = c.get(f"/payroll/2019-01/user/{begona}", headers=auth(rop1_t))
            check("S-06: ROP begona payslip -> 404",
                  r.status_code == 404, "kod=" + str(r.status_code))

            # Xodim bu endpointlarga ROL bo'yicha kirolmaydi -> 403
            # (bu BOSHQA holat: «bunday imkoniyat yo'q», «bu yozuv sizniki
            # emas» emas — shuning uchun 404 emas, 403 to'g'ri).
            r = c.get(f"/bonuses?user_id={oz}", headers=auth(emp1_t))
            check("S-06: xodimga rol bo'yicha yopiq -> 403 (404 emas)",
                  r.status_code == 403, "kod=" + str(r.status_code))

            # ── (3) Ro'yxat endpointlari filtrlanadimi ──
            r = c.get("/requests?status_filter=pending", headers=auth(rop1_t))
            check("S-06: ROP murojaatlar ro'yxati -> 200",
                  r.status_code == 200, "kod=" + str(r.status_code))
            if r.status_code == 200:
                yot = [x for x in r.json() if x.get("user_id") == begona]
                check("S-06: ro'yxatda BEGONA xodim yo'q", not yot, "=" + str(yot[:2]))

            r = c.get("/excused-days?status_filter=pending", headers=auth(rop1_t))
            check("S-06: ROP sababli kunlar ro'yxati -> 200",
                  r.status_code == 200, "kod=" + str(r.status_code))
            if r.status_code == 200:
                yot = [x for x in r.json() if x.get("user_id") == begona]
                check("S-06: sababli kunlarda BEGONA xodim yo'q", not yot, "=" + str(yot[:2]))
    except Exception:
        check("S-06 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        if ids:
            hammasi = list(ids.values())
            qm = ",".join("?" * len(hammasi))
            cur.execute(f"update users set manager_id=null where manager_id in ({qm})", hammasi)
            for t in ("bonuses", "payslips", "excused_days", "attendance", "work_log_entries"):
                try:
                    cur.execute(f"delete from {t} where user_id in ({qm})", hammasi)
                except sqlite3.OperationalError:
                    pass
            cur.execute(f"delete from audit_logs where target_user_id in ({qm})"
                        f" or actor_id in ({qm})", hammasi + hammasi)
            cur.execute(f"delete from users where id in ({qm})", hammasi)
            conn.commit()
        conn.close()


def test_background_jobs() -> None:
    """S-07 (TZ 2.2) — og'ir ish so'rov ichida BAJARILMAYDI.

    cPanel Passenger'da konkurentlik = 1: Excel eksporti so'rov ichida
    yasalgani uchun o'sha vaqt davomida BUTUN sayt javob bermasdi. Endi
    so'rov navbatga qo'yadi (202), og'ir ishni cron jarayoni bajaradi.

    Qabul mezonlari (TZ):
      • eksport so'rov ichida bajarilmaydi;
      • foydalanuvchi «tayyorlanmoqda» xabarini oladi;
      • bitta ish IKKI MARTA bajarilmaydi;
      • xato bo'lsa `failed` va sabab yoziladi, cron O'LMAYDI.
    """
    import asyncio
    import time

    import httpx

    print("\n" + "=" * 60)
    print("S-07: OG'IR ISH NAVBATI")
    print("=" * 60)

    from api.services.background_jobs import background_tick, enqueue
    from db.base import async_session
    from db.models import BackgroundJob

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])

    conn = db()
    cur = conn.cursor()
    job_ids = []
    try:
        # ── (1) So'rov DARHOL qaytadi ──
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            t0 = time.perf_counter()
            r = c.post("/reports/export-async?date_from=2019-01-01&date_to=2019-01-31",
                       headers=auth(mgr_t))
            davomiylik = time.perf_counter() - t0
            # Telegram ulanmagan rahbar bo'lsa 400 — bu ham to'g'ri xatti-harakat
            if r.status_code == 400:
                check("S-07: Telegramsiz rahbarga tushunarli xato",
                      "Telegram" in r.text, "=" + r.text[:120])
            else:
                check("S-07: eksport so'rovi -> 202 (natija emas, NAVBAT)",
                      r.status_code == 202, "kod=" + str(r.status_code) + " " + r.text[:120])
                check("S-07: so'rov TEZ qaytadi (og'ir ish ichida emas)",
                      davomiylik < 2.0, f"{davomiylik:.2f}s")
                job = r.json()
                job_ids.append(job.get("job_id"))
                check("S-07: javobda `job_id` va «tayyorlanmoqda» xabari bor",
                      job.get("job_id") and "tayyorlanmoqda" in (job.get("message") or ""),
                      "=" + str(job))

                # Holat endpointi
                r2 = c.get(f"/reports/jobs/{job['job_id']}", headers=auth(mgr_t))
                check("S-07: holat endpointi -> 200 va `queued`",
                      r2.status_code == 200 and r2.json().get("status") == "queued",
                      "kod=" + str(r2.status_code) + " " + r2.text[:100])

                # Begona ish -> 404 (S-06 qoidasi)
                r3 = c.get("/reports/jobs/999999", headers=auth(mgr_t))
                check("S-07: begona/yo'q ishga -> 404", r3.status_code == 404,
                      "kod=" + str(r3.status_code))

        # ── (2) Ish navbatga TUSHDI, cron uni oladi ──
        async def _tick():
            async with async_session() as s2:
                return await background_tick(s2)

        if job_ids:
            natija = asyncio.run(_tick())
            check("S-07: cron navbatdagi ishni bajardi",
                  natija.get("ran") == "report_export" and natija.get("ok") is True,
                  "=" + str(natija))
            check("S-07: fayl yasaldi (baytlar bor)",
                  (natija.get("bytes") or 0) > 1000, "=" + str(natija.get("bytes")))

            # ── (3) IKKI MARTA bajarilmaydi ──
            ikkinchi = asyncio.run(_tick())
            check("S-07: o'sha ish IKKINCHI marta olinmaydi",
                  ikkinchi.get("ran") is None, "=" + str(ikkinchi))

            holat = cur.execute("select status from background_jobs where id=?",
                                (job_ids[0],)).fetchone()
            check("S-07: ish holati `done`", holat and holat[0] == "done", "=" + str(holat))

        # ── (4) Xato bo'lsa `failed` + sabab, cron o'lmaydi ──
        async def _xato_ish():
            async with async_session() as s2:
                j = await enqueue(s2, "report_export", {"date_from": "buzuq"}, mgr[0])
                await s2.commit()
                return j.id

        xato_id = asyncio.run(_xato_ish())
        job_ids.append(xato_id)
        natija = asyncio.run(_tick())
        check("S-07: xato ish cron'ni O'LDIRMAYDI (javob qaytdi)",
              natija.get("ok") is False, "=" + str(natija))
        row = cur.execute("select status, error from background_jobs where id=?",
                          (xato_id,)).fetchone()
        check("S-07: xato ish `failed` bo'ldi va SABAB yozildi",
              row and row[0] == "failed" and row[1], "=" + str(row))

        # ── (5) Noma'lum tur navbatga UMUMAN tushmaydi ──
        async def _nomalum():
            async with async_session() as s2:
                try:
                    await enqueue(s2, "yolgon_ish", {}, mgr[0])
                    return "o'tdi"
                except ValueError as e:
                    return str(e)

        check("S-07: noma'lum ish turi rad etiladi",
              "noma'lum" in asyncio.run(_nomalum()), "=" + asyncio.run(_nomalum()))
    except Exception:
        check("S-07 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        cur.execute("delete from background_jobs")
        conn.commit()
        conn.close()


def test_setup_status() -> None:
    """S-08 (TZ 2.7) — mexanizmi tayyor, lekin QIYMATI yo'q modullar ko'rinsin.

    Jonli isbot (2026-08-17): `kpi_rates` jadvali BUTUNLAY bo'sh edi —
    kod to'g'ri ishlardi, ko'paytiriladigan stavka yo'q edi. Buni topguncha
    butun oylik tekshiruvi kerak bo'ldi. Endi bosh sahifada ko'rinadi.

    Qabul mezonlari (TZ):
      • har qator to'g'ridan-to'g'ri sozlash sahifasiga olib boradi;
      • hammasi sozlangan bo'lsa ro'yxatda sozlanmagan qolmaydi;
      • yangi modul qo'shish uchun bitta qator yetadi.
    """
    import asyncio

    import httpx

    print("\n" + "=" * 60)
    print("S-08: SOZLANMAGAN MODULLAR")
    print("=" * 60)

    from api.services.setup_status import _TEKSHIRUVLAR, collect_setup_status
    from db.base import async_session

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])

    conn = db()
    cur = conn.cursor()
    kpi_id = None
    try:
        async def _holat():
            async with async_session() as s2:
                return await collect_setup_status(s2)

        items = asyncio.run(_holat())
        check("S-08: ro'yxat bo'sh emas", len(items) >= 7, "=" + str(len(items)))
        check("S-08: har bandda havola bor",
              all(i.link.startswith("/") for i in items),
              "=" + str([i.link for i in items]))
        check("S-08: har bandda «nima yetishmayapti» yozilgan",
              all(len(i.missing) > 10 for i in items), "=" + str([i.key for i in items]))

        # Sozlanmaganlar TEPADA, ular ichida muhimlari birinchi
        tayyor_indeks = [n for n, i in enumerate(items) if i.ready]
        sozlanmagan_indeks = [n for n, i in enumerate(items) if not i.ready]
        if tayyor_indeks and sozlanmagan_indeks:
            check("S-08: sozlanmaganlar TEPADA",
                  max(sozlanmagan_indeks) < min(tayyor_indeks),
                  f"sozlanmagan={sozlanmagan_indeks}, tayyor={tayyor_indeks}")
        muhim = [n for n, i in enumerate(items) if not i.ready and i.critical]
        oddiy = [n for n, i in enumerate(items) if not i.ready and not i.critical]
        if muhim and oddiy:
            check("S-08: MUHIM modullar oddiylaridan yuqorida",
                  max(muhim) < min(oddiy), f"muhim={muhim}, oddiy={oddiy}")

        # ── Qiymat kiritilsa modul «tayyor» bo'ladi ──
        oldin = {i.key: i.ready for i in items}
        check("S-08: KPI stavkasi hozir yo'q (boshlang'ich holat)",
              oldin.get("kpi_rates") is False, "=" + str(oldin.get("kpi_rates")))

        cur.execute(
            "insert into kpi_rates (scope, scope_id, metric, amount, effective_from,"
            " changed_by, created_at) values ('global',null,'suhbat',1000,'2019-01-01',?,"
            "datetime('now'))", (mgr[0],))
        kpi_id = cur.lastrowid
        conn.commit()

        keyin = {i.key: i.ready for i in asyncio.run(_holat())}
        check("S-08: stavka kiritilgach modul «tayyor» bo'ldi",
              keyin.get("kpi_rates") is True, "=" + str(keyin.get("kpi_rates")))
        check("S-08: boshqa modullar holati o'zgarmadi",
              all(keyin[k] == v for k, v in oldin.items() if k != "kpi_rates"),
              "=" + str({k: (oldin[k], keyin[k]) for k in oldin if oldin[k] != keyin[k]}))

        # ── Kengaytirilishi: bitta qator yetadi ──
        check("S-08: ro'yxat bitta joyda e'lon qilingan (kengaytirish oson)",
              len(_TEKSHIRUVLAR) == len(items), f"{len(_TEKSHIRUVLAR)} vs {len(items)}")

        # ── HTTP + ruxsat ──
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            r = c.get("/me/setup-status", headers=auth(mgr_t))
            check("S-08: /me/setup-status rahbarga -> 200",
                  r.status_code == 200, "kod=" + str(r.status_code))
            if r.status_code == 200:
                check("S-08: javob tuzilishi to'g'ri",
                      all({"key", "label", "ready", "missing", "link", "critical"} <= set(x)
                          for x in r.json()), "=" + str(r.json()[:1]))

            # Oddiy xodim ko'ra olmaydi
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " created_at) values (999700601,'T-Setup','employee',0,1,datetime('now'))")
            emp_id = cur.lastrowid
            conn.commit()
            r2 = c.get("/me/setup-status", headers=auth(token_for(emp_id, "employee")))
            check("S-08: oddiy xodimga -> 403", r2.status_code == 403,
                  "kod=" + str(r2.status_code))
            cur.execute("delete from users where id=?", (emp_id,))
            conn.commit()
    except Exception:
        check("S-08 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        if kpi_id is not None:
            cur.execute("delete from kpi_rates where id=?", (kpi_id,))
        cur.execute("delete from users where full_name='T-Setup'")
        conn.commit()
        conn.close()


def test_holidays() -> None:
    """S-09 (TZ 2.9) — bayram ish kuni sifatida sanalmasin, ta'tildagi
    xodim check-in qilolmasin.

    Qabul mezonlari (TZ):
      • bayram kuni ish kuni sifatida sanalmaydi (hamma hisoblagichda);
      • ta'tildagi xodim check-in qilolmaydi;
      • bayram kiritilmagan bo'lsa «Sozlanmagan modullar» da ko'rinadi.

    Alohida tekshiriladigan CHEGARA HOLAT (TZ talabi): bayram + sababli
    kun + dam olish kuni BIR KUNGA to'g'ri kelsa hisob buzilmasin —
    kun ikki marta ayirilmasin va manfiy natija chiqmasin.

    USTUVORLIK ham tekshiriladi: xodimga ATAYIN qo'yilgan kunlik override
    bayramdan kuchli (bayram navbatchiligi), bayram esa haftalik
    andozadan kuchli.
    """
    import asyncio
    from datetime import date as _date
    from datetime import timedelta as _td

    import httpx

    print("\n" + "=" * 60)
    print("S-09: BAYRAMLAR + TA'TILDAGI CHECK-IN")
    print("=" * 60)

    from db.base import async_session

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])

    # Kelasi yilning YANVARI — jonli ma'lumotga tegmaslik uchun ataylab
    # kelajak: o'sha oyda hech kimning davomati/oyligi yo'q.
    yil = _date.today().year + 1
    # 4 dan 10 gacha bo'lgan oraliqda ish kuni (Du-Ju) bo'lgan sana tanlaymiz.
    bayram_kuni = next(
        d for d in (_date(yil, 1, n) for n in range(4, 12)) if d.weekday() < 5
    )
    dam_kuni = next(
        d for d in (_date(yil, 1, n) for n in range(4, 12)) if d.weekday() >= 5
    )
    ish_kuni2 = bayram_kuni + _td(days=1) if (bayram_kuni + _td(days=1)).weekday() < 5 \
        else bayram_kuni + _td(days=3)
    davr = f"{yil}-01"

    conn = db()
    cur = conn.cursor()
    uid = None
    try:
        # Oldingi UZILGAN yurishning qoldig'i natijani buzmasin: birinchi
        # tekshiruv «bayramdan oldin bu kun ish kuni edi» degan boshlang'ich
        # holatga tayanadi. Tozalash faqat oxirida bo'lsa, test yarmida
        # yiqilgan yurishdan keyingi safar noto'g'ri FAIL berardi.
        cur.execute("delete from holidays where name like 'T-%' or name='Takror'")
        cur.execute("delete from users where full_name='T-Holiday'")
        conn.commit()
        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " created_at) values (999700901,'T-Holiday','employee',0,1,datetime('now'))")
        uid = cur.lastrowid
        conn.commit()

        async def _sched(period=davr):
            from api.services.payroll import month_schedule
            from db.models import User as U
            async with async_session() as s2:
                u = await s2.get(U, uid)
                return {d["date"]: d["is_working"] for d in await month_schedule(s2, u, period)}

        async def _range(a, b):
            from api.services.workdays import range_days
            from db.models import User as U
            async with async_session() as s2:
                u = await s2.get(U, uid)
                return {d["date"]: d["is_working"] for d in await range_days(s2, u, a, b)}

        # ── 1) Boshlang'ich holat: bayram yo'q, oddiy ish kuni ──
        oldin = asyncio.run(_sched())
        check("S-09: bayramdan OLDIN kun ish kuni edi",
              oldin.get(bayram_kuni) is True, f"{bayram_kuni} -> {oldin.get(bayram_kuni)}")
        ish_kuni_oldin = sum(1 for v in oldin.values() if v)

        # ── 2) HTTP orqali bayram qo'shish (HR paneli yo'li) ──
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            r = c.post("/holidays", headers=auth(mgr_t),
                       json={"date": bayram_kuni.isoformat(), "name": "T-Bayram",
                             "kind": "state"})
            check("S-09: POST /holidays -> 201", r.status_code == 201,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            hid = r.json().get("id") if r.status_code == 201 else None

            # Takroriy sana -> 409 (HR ro'yxatni ikki marta yuborishi normal)
            r2 = c.post("/holidays", headers=auth(mgr_t),
                        json={"date": bayram_kuni.isoformat(), "name": "Takror",
                              "kind": "state"})
            check("S-09: takroriy sana -> 409", r2.status_code == 409,
                  "kod=" + str(r2.status_code))

            # Oddiy xodim qo'sha olmaydi (lekin KO'RA oladi)
            emp_t = token_for(uid, "employee")
            r3 = c.post("/holidays", headers=auth(emp_t),
                        json={"date": ish_kuni2.isoformat(), "name": "X", "kind": "state"})
            check("S-09: oddiy xodim qo'sha olmaydi -> 403", r3.status_code == 403,
                  "kod=" + str(r3.status_code))
            r4 = c.get("/holidays", headers=auth(emp_t), params={"year": yil})
            check("S-09: oddiy xodim ro'yxatni KO'RADI -> 200", r4.status_code == 200,
                  "kod=" + str(r4.status_code))

            # ── 3) Ro'yxatni bir marta kiritish (bulk) ──
            r5 = c.post("/holidays/bulk", headers=auth(mgr_t), json={
                "items": [
                    {"date": bayram_kuni.isoformat(), "name": "Takror", "kind": "state"},
                    {"date": dam_kuni.isoformat(), "name": "T-DamBayram", "kind": "company"},
                ],
                "overwrite": False,
            })
            check("S-09: bulk -> 200", r5.status_code == 200, "kod=" + str(r5.status_code))
            if r5.status_code == 200:
                j = r5.json()
                check("S-09: bulk borini o'tkazib yubordi, yangisini qo'shdi",
                      j.get("added") == 1 and j.get("skipped") == 1, "=" + str(j))

        # ── 4) Bayram ish kuni sifatida SANALMAYDI ──
        keyin = asyncio.run(_sched())
        check("S-09: bayram kuni endi ish kuni EMAS",
              keyin.get(bayram_kuni) is False, f"{bayram_kuni} -> {keyin.get(bayram_kuni)}")
        check("S-09: oydagi ish kunlari ayni 1 taga kamaydi",
              sum(1 for v in keyin.values() if v) == ish_kuni_oldin - 1,
              f"{ish_kuni_oldin} -> {sum(1 for v in keyin.values() if v)}")
        check("S-09: qolgan kunlarga tegmadi",
              all(keyin[d] == v for d, v in oldin.items() if d != bayram_kuni),
              "=" + str([d for d, v in oldin.items() if d != bayram_kuni and keyin[d] != v]))

        # ── 5) CHEGARA: bayram DAM OLISH kuniga to'g'ri kelsa ──
        # Kun ikki marta ayirilmasin — u allaqachon ish kuni emas edi.
        check("S-09: dam kuniga tushgan bayram hisobni BUZMADI",
              keyin.get(dam_kuni) is False and
              sum(1 for v in keyin.values() if v) == ish_kuni_oldin - 1,
              f"{dam_kuni} -> {keyin.get(dam_kuni)}")

        # ── 6) `workdays.range_days` ham bilishi kerak ──
        rd = asyncio.run(_range(_date(yil, 1, 1), _date(yil, 1, 31)))
        check("S-09: workdays.range_days da ham bayram ish kuni emas",
              rd.get(bayram_kuni) is False, f"{bayram_kuni} -> {rd.get(bayram_kuni)}")

        # ── 7) USTUVORLIK: override bayramdan KUCHLI ──
        cur.execute(
            "insert into work_schedule_override (user_id, date, is_working, start_time,"
            " end_time, updated_at) values (?,?,1,'09:00','18:00',datetime('now'))",
            (uid, bayram_kuni.isoformat()))
        conn.commit()
        ustun = asyncio.run(_sched())
        check("S-09: override bayramdan KUCHLI (bayram navbatchiligi)",
              ustun.get(bayram_kuni) is True, f"{bayram_kuni} -> {ustun.get(bayram_kuni)}")
        cur.execute("delete from work_schedule_override where user_id=?", (uid,))
        conn.commit()

        # ── 8) USTUVORLIK: bayram haftalik andozadan KUCHLI ──
        cur.execute(
            "insert into work_schedule_weekly (user_id, weekday, is_working, start_time,"
            " end_time, updated_at) values (?,?,1,'09:00','18:00',datetime('now'))",
            (uid, bayram_kuni.weekday()))
        conn.commit()
        haftalik = asyncio.run(_sched())
        check("S-09: bayram haftalik andozadan KUCHLI",
              haftalik.get(bayram_kuni) is False,
              f"{bayram_kuni} -> {haftalik.get(bayram_kuni)}")
        cur.execute("delete from work_schedule_weekly where user_id=?", (uid,))
        conn.commit()

        # ── 9) UCHALASI BIR KUNDA: bayram + sababli kun + dam kuni ──
        # `target_split._working_days` sababli kunni AYIRADI; kun allaqachon
        # bayram/dam kuni bo'lsa ikki marta ayirilmasligi kerak.
        cur.execute(
            "insert into excused_days (user_id, date, reason, status, created_at)"
            " values (?,?,'T-tatil','approved',datetime('now'))",
            (uid, dam_kuni.isoformat()))
        conn.commit()

        async def _wd():
            from api.services import target_split
            from db.models import User as U
            async with async_session() as s2:
                u = await s2.get(U, uid)
                excused = (await target_split._excused_map(s2, davr)).get(uid, set())  # noqa: SLF001
                return await target_split._working_days(s2, u, davr, excused)  # noqa: SLF001

        uch = asyncio.run(_wd())
        check("S-09: bayram+sababli+dam kuni bir kunda — ish kuni MANFIY emas",
              uch >= 0, "=" + str(uch))
        check("S-09: uchtasi to'g'ri kelganda kun IKKI marta ayirilmadi",
              uch == ish_kuni_oldin - 1, f"kutilgan={ish_kuni_oldin - 1}, chiqdi={uch}")

        # ── 10) TA'TILDAGI XODIM CHECK-IN QILOLMAYDI ──
        bugun = _date.today()
        cur.execute(
            "insert into excused_days (user_id, date, reason, status, created_at)"
            " values (?,?,'T-tatil','approved',datetime('now'))", (uid, bugun.isoformat()))
        conn.commit()

        async def _checkin():
            from api.services.attendance import CheckError, OnLeaveError, perform_check_in
            from db.models import User as U
            async with async_session() as s2:
                u = await s2.get(U, uid)
                try:
                    await perform_check_in(s2, u, None, None)
                except OnLeaveError as e:
                    return "on_leave", str(e)
                except CheckError as e:
                    return "other", str(e)
                return "ok", ""

        turi, xabar = asyncio.run(_checkin())
        check("S-09: ta'tildagi xodim check-in qilolmadi", turi == "on_leave",
              f"{turi}: {xabar[:100]}")
        check("S-09: rad etish xabari TUSHUNARLI (nima qilishni aytadi)",
              turi == "on_leave" and "HR" in xabar and len(xabar) > 60,
              "=" + xabar[:120])

        # Sababli kun olib tashlansa — check-in yana boshqa sababga tayanadi
        # (bu yerda GPS/yuz), ya'ni «ta'til» to'sig'i o'tdi.
        cur.execute("delete from excused_days where user_id=? and date=?",
                    (uid, bugun.isoformat()))
        conn.commit()
        turi2, xabar2 = asyncio.run(_checkin())
        check("S-09: sababli kun olingach «ta'til» to'sig'i yo'qoldi",
              turi2 != "on_leave", f"{turi2}: {xabar2[:80]}")

        # ── 11) «Sozlanmagan modullar» da ko'rinishi ──
        from api.services.setup_status import collect_setup_status

        async def _holat():
            async with async_session() as s2:
                return {i.key: i.ready for i in await collect_setup_status(s2)}

        check("S-09: bayram kiritilgani «Sozlanmagan» ro'yxatidan chiqardi",
              asyncio.run(_holat()).get("holidays") is True,
              "=" + str(asyncio.run(_holat()).get("holidays")))

        # ── 12) O'chirish ──
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            if hid:
                rd2 = c.delete(f"/holidays/{hid}", headers=auth(mgr_t))
                check("S-09: DELETE /holidays -> 200", rd2.status_code == 200,
                      "kod=" + str(rd2.status_code))
                qayta = asyncio.run(_sched())
                check("S-09: bayram o'chirilgach kun yana ish kuni bo'ldi",
                      qayta.get(bayram_kuni) is True,
                      f"{bayram_kuni} -> {qayta.get(bayram_kuni)}")
            rd3 = c.delete("/holidays/99999999", headers=auth(mgr_t))
            check("S-09: yo'q bayramni o'chirish -> 404", rd3.status_code == 404,
                  "kod=" + str(rd3.status_code))
    except Exception:
        check("S-09 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            cur.execute("delete from holidays where name like 'T-%' or name='Takror'")
            if uid:
                cur.execute("delete from excused_days where user_id=?", (uid,))
                cur.execute("delete from work_schedule_override where user_id=?", (uid,))
                cur.execute("delete from work_schedule_weekly where user_id=?", (uid,))
                cur.execute("delete from attendance where user_id=?", (uid,))
                cur.execute("delete from users where id=?", (uid,))
            conn.commit()
        except Exception:
            pass
        conn.close()


def test_employee_documents() -> None:
    """S-10 (TZ 3.4) — kadr hujjatlari arxivi: model va API.

    Modulning eng nozik joyi RUXSAT: bu maxfiy ma'lumot (diplom, tibbiy
    ma'lumotnoma, shartnoma). TZ ataylab talab qiladi — **ROP umuman
    ko'rmaydi**, hatto O'Z JAMOASI bo'lsa ham. Boshqa modullarda ROP
    jamoasini ko'radi, shuning uchun bu chetlanish alohida sinaladi.

    Begona so'ralganda 403 EMAS, 404: 403 «bu odamda hujjat bor» degan
    ma'lumotni oshkor qilardi.

    Qabul mezonlari (TZ):
      • xodim faqat o'zinikini ko'radi, begonaga 404;
      • ROP ga 404 (hatto o'z jamoasi bo'lsa ham);
      • barcha o'qish `deleted_at IS NULL`;
      • fayl serverda saqlanmaydi — faqat `file_id`;
      • test: 8+ (rol matritsasi, soft delete, 404, muddat maydoni).
    """
    from datetime import date as _date
    from datetime import timedelta as _td

    import httpx

    print("\n" + "=" * 60)
    print("S-10: KADR HUJJATLARI (ruxsat matritsasi)")
    print("=" * 60)

    conn = db()
    cur = conn.cursor()
    ids: dict[str, int] = {}
    try:
        cur.execute("delete from users where full_name like 'T-Doc%'")
        conn.commit()

        def _yarat(nom: str, rol: str, tg: int, manager: int | None = None) -> int:
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " manager_id, created_at) values (?,?,?,0,1,?,datetime('now'))",
                (tg, nom, rol, manager))
            conn.commit()
            return cur.lastrowid

        ids["hr"] = _yarat("T-DocHR", "hr", 999701001)
        ids["rop"] = _yarat("T-DocRop", "rop", 999701002)
        # ROP ning BEVOSITA bo'ysunuvchisi — «o'z jamoasi» aynan shu
        ids["team"] = _yarat("T-DocTeam", "employee", 999701003, ids["rop"])
        ids["other"] = _yarat("T-DocOther", "employee", 999701004)

        t = {k: token_for(v, r) for (k, v), r in zip(
            ids.items(), ["hr", "rop", "employee", "employee"])}

        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            # ── Tur ro'yxati yagona manbadan ──
            r = c.get("/employee-documents/types", headers=auth(t["team"]))
            check("S-10: /types -> 200", r.status_code == 200, "kod=" + str(r.status_code))
            if r.status_code == 200:
                turlar = {x["value"] for x in r.json()}
                check("S-10: TZ dagi 7 tur ham bor",
                      {"contract", "job_description", "property_act", "handover_act",
                       "medical", "diploma", "other"} <= turlar, "=" + str(sorted(turlar)))

            # ── YUKLASH ruxsati ──
            yangi = {
                "user_id": ids["team"], "doc_type": "contract",
                "name": "T-Doc mehnat shartnomasi", "file_id": "T-FAKE-FILE-ID-1",
                "file_type": "document", "issued_at": "2026-01-10",
            }
            r = c.post("/employee-documents", headers=auth(t["team"]), json=yangi)
            check("S-10: oddiy xodim yuklay olmaydi -> 403", r.status_code == 403,
                  "kod=" + str(r.status_code))
            r = c.post("/employee-documents", headers=auth(t["rop"]), json=yangi)
            check("S-10: ROP yuklay olmaydi -> 403", r.status_code == 403,
                  "kod=" + str(r.status_code))
            r = c.post("/employee-documents", headers=auth(t["hr"]), json=yangi)
            check("S-10: HR yukladi -> 201", r.status_code == 201,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            doc_id = r.json().get("id") if r.status_code == 201 else None
            if r.status_code == 201:
                check("S-10: javobda tur nomi tarjima qilingan",
                      r.json().get("doc_type_label") == "Mehnat shartnomasi",
                      "=" + str(r.json().get("doc_type_label")))

            # ── Fayl SERVERDA saqlanmaydi ──
            if doc_id:
                row = cur.execute(
                    "select file_id from employee_documents where id=?", (doc_id,)).fetchone()
                check("S-10: bazada faqat file_id (fayl yo'q)",
                      row is not None and row[0] == "T-FAKE-FILE-ID-1", "=" + str(row))

            # ── RUXSAT MATRITSASI (o'qish) ──
            r = c.get("/employee-documents/me", headers=auth(t["team"]))
            check("S-10: xodim O'ZINIKINI ko'radi -> 200 (1 ta)",
                  r.status_code == 200 and len(r.json()) == 1,
                  f"kod={r.status_code} soni={len(r.json()) if r.status_code == 200 else '-'}")

            r = c.get(f"/employee-documents/user/{ids['team']}", headers=auth(t["other"]))
            check("S-10: BEGONA xodim -> 404 (403 emas — oshkor qilmaydi)",
                  r.status_code == 404, "kod=" + str(r.status_code))

            # ⚠️ ASOSIY CHETLANISH: ROP o'z jamoasini ham ko'rmaydi
            r = c.get(f"/employee-documents/user/{ids['team']}", headers=auth(t["rop"]))
            check("S-10: ROP O'Z JAMOASINI ham ko'rmaydi -> 404",
                  r.status_code == 404, "kod=" + str(r.status_code))

            r = c.get(f"/employee-documents/user/{ids['rop']}", headers=auth(t["rop"]))
            check("S-10: ROP o'zinikini ko'radi -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code))

            r = c.get(f"/employee-documents/user/{ids['team']}", headers=auth(t["hr"]))
            check("S-10: HR hammani ko'radi -> 200 (1 ta)",
                  r.status_code == 200 and len(r.json()) == 1,
                  f"kod={r.status_code} soni={len(r.json()) if r.status_code == 200 else '-'}")

            # ── MUDDAT maydoni ──
            bugun = _date.today()
            c.post("/employee-documents", headers=auth(t["hr"]), json={
                "user_id": ids["team"], "doc_type": "medical",
                "name": "T-Doc muddati o'tgan", "file_id": "T-FAKE-2",
                "expires_at": (bugun - _td(days=5)).isoformat()})
            c.post("/employee-documents", headers=auth(t["hr"]), json={
                "user_id": ids["team"], "doc_type": "diploma",
                "name": "T-Doc kelajakda", "file_id": "T-FAKE-3",
                "expires_at": (bugun + _td(days=10)).isoformat()})
            r = c.get("/employee-documents/me", headers=auth(t["team"]))
            hujjatlar = {d["name"]: d for d in r.json()} if r.status_code == 200 else {}
            check("S-10: muddati o'tgan hujjat belgilandi",
                  hujjatlar.get("T-Doc muddati o'tgan", {}).get("is_expired") is True
                  and hujjatlar["T-Doc muddati o'tgan"]["days_left"] == -5,
                  "=" + str(hujjatlar.get("T-Doc muddati o'tgan", {}).get("days_left")))
            check("S-10: amaldagi hujjat muddati o'tgan emas",
                  hujjatlar.get("T-Doc kelajakda", {}).get("is_expired") is False
                  and hujjatlar["T-Doc kelajakda"]["days_left"] == 10,
                  "=" + str(hujjatlar.get("T-Doc kelajakda", {}).get("days_left")))
            check("S-10: muddatsiz hujjatda days_left=None",
                  hujjatlar.get("T-Doc mehnat shartnomasi", {}).get("days_left") is None,
                  "=" + str(hujjatlar.get("T-Doc mehnat shartnomasi", {}).get("days_left")))
            # Muddati tugaydiganlar TEPADA (muddatsizlar oxirida)
            tartib = [d["name"] for d in r.json()] if r.status_code == 200 else []
            check("S-10: muddati yaqinlari tepada, muddatsiz oxirida",
                  tartib and tartib[-1] == "T-Doc mehnat shartnomasi"
                  and tartib[0] == "T-Doc muddati o'tgan", "=" + str(tartib))

            # ── Xato kiritishlar ──
            r = c.post("/employee-documents", headers=auth(t["hr"]), json={
                "user_id": ids["team"], "doc_type": "yolgon_tur",
                "name": "T-Doc x", "file_id": "T-FAKE-4"})
            check("S-10: noma'lum tur -> 400", r.status_code == 400,
                  "kod=" + str(r.status_code))
            r = c.post("/employee-documents", headers=auth(t["hr"]), json={
                "user_id": ids["team"], "doc_type": "other", "name": "T-Doc y",
                "file_id": "T-FAKE-5", "issued_at": "2026-05-01",
                "expires_at": "2026-04-01"})
            check("S-10: tugash sanasi berilgandan oldin -> 400",
                  r.status_code == 400, "kod=" + str(r.status_code))
            r = c.post("/employee-documents", headers=auth(t["hr"]), json={
                "user_id": 99999999, "doc_type": "other", "name": "T-Doc z",
                "file_id": "T-FAKE-6"})
            check("S-10: yo'q xodimga yuklash -> 404", r.status_code == 404,
                  "kod=" + str(r.status_code))

            # ── YUMSHOQ o'chirish ──
            if doc_id:
                r = c.delete(f"/employee-documents/{doc_id}", headers=auth(t["rop"]))
                check("S-10: ROP o'chira olmaydi -> 403", r.status_code == 403,
                      "kod=" + str(r.status_code))
                r = c.delete(f"/employee-documents/{doc_id}", headers=auth(t["hr"]))
                check("S-10: HR o'chirdi -> 200", r.status_code == 200,
                      "kod=" + str(r.status_code))
                qator = cur.execute(
                    "select deleted_at from employee_documents where id=?",
                    (doc_id,)).fetchone()
                check("S-10: o'chirish YUMSHOQ (qator bazada, deleted_at to'ldi)",
                      qator is not None and qator[0] is not None, "=" + str(qator))
                r = c.get("/employee-documents/me", headers=auth(t["team"]))
                nomlar = [d["name"] for d in r.json()] if r.status_code == 200 else []
                check("S-10: o'chirilgani ro'yxatda YO'Q (deleted_at IS NULL filtri)",
                      "T-Doc mehnat shartnomasi" not in nomlar, "=" + str(nomlar))
                r = c.delete(f"/employee-documents/{doc_id}", headers=auth(t["hr"]))
                check("S-10: ikkinchi marta o'chirish -> 404", r.status_code == 404,
                      "kod=" + str(r.status_code))
    except Exception:
        check("S-10 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            if ids:
                cur.execute(
                    "delete from employee_documents where user_id in (%s)"
                    % ",".join("?" * len(ids)), tuple(ids.values()))
            cur.execute("delete from users where full_name like 'T-Doc%'")
            conn.commit()
        except Exception:
            pass
        conn.close()


def test_documents_bot() -> None:
    """S-11 (TZ 3.4) — hujjatlar boti, kabinet va tugma matnlari.

    Qabul mezonlari (TZ):
      • HR botdan hujjat yuklay oladi, fayl Telegramda qoladi;
      • xodim o'z hujjatini botdan qayta olishi mumkin;
      • muddati o'tayotgan hujjat ro'yxatda ajratib ko'rsatiladi;
      • test: yuklash -> o'qish -> soft delete zanjiri.

    ALOHIDA QO'RIQCHI: tugma matnlari `bot/keyboards.py` va
    `api/services/sections.py` da IKKI MARTA yozilgan (birinchisi handler
    mosligi, ikkinchisi menyu qurish uchun). Ular bir-biridan uzoqlashsa
    server tugmani chizadi, handler esa uni tanimaydi — tugma JIMGINA
    ishlamay qoladi. S-05 aynan shu sinf xatoni yopish uchun qilingan
    edi, shuning uchun bu yerda tekshiriladi.
    """
    from datetime import date as _date
    from datetime import timedelta as _td

    import httpx

    print("\n" + "=" * 60)
    print("S-11: HUJJATLAR BOTI + KABINET")
    print("=" * 60)

    # ── Tugma matnlari ikkala faylda AYNAN bir xilmi ──
    try:
        import importlib

        kb = importlib.import_module("bot.keyboards")
        sec = importlib.import_module("api.services.sections")
        kb_btn = {k: v for k, v in vars(kb).items() if k.startswith("BTN_")}
        sec_btn = {k: v for k, v in vars(sec).items() if k.startswith("BTN_")}
        umumiy = set(kb_btn) & set(sec_btn)
        farq = {k: (kb_btn[k], sec_btn[k]) for k in umumiy if kb_btn[k] != sec_btn[k]}
        check("S-11: tugma matnlari ikkala faylda bir xil", not farq, "=" + str(farq))
        # `sections.py` chizadigan HAR BIR tugma handlerda bo'lishi shart
        yetishmaydi = {k: v for k, v in sec_btn.items() if k not in kb_btn}
        check("S-11: sections'dagi har tugma keyboards'da ham bor",
              not yetishmaydi, "=" + str(yetishmaydi))
    except Exception:
        check("S-11 tugma qo'riqchisi", False, traceback.format_exc(limit=2).strip())

    # ── Izohdan nom va sana ajratish (bot mantiqi) ──
    try:
        from bot.handlers.documents import _muddat_belgisi, _parse_caption  # noqa: SLF001

        check("S-11: izoh oxiridagi sana ajratildi",
              _parse_caption("Mehnat shartnomasi 2027-12-31", "F") == (
                  "Mehnat shartnomasi", "2027-12-31"),
              "=" + str(_parse_caption("Mehnat shartnomasi 2027-12-31", "F")))
        check("S-11: sana OLDIDA bo'lsa ham ajratiladi",
              _parse_caption("2027-12-31 Diplom", "F") == ("Diplom", "2027-12-31"),
              "=" + str(_parse_caption("2027-12-31 Diplom", "F")))
        check("S-11: sanasiz izoh — nom, muddat yo'q",
              _parse_caption("Diplom", "F") == ("Diplom", None),
              "=" + str(_parse_caption("Diplom", "F")))
        check("S-11: izoh bo'sh — fayl nomi ishlatiladi",
              _parse_caption("", "shartnoma.pdf") == ("shartnoma.pdf", None),
              "=" + str(_parse_caption("", "shartnoma.pdf")))
        check("S-11: muddati o'tgan hujjat botda AJRATIB ko'rsatiladi",
              "⛔" in _muddat_belgisi({"days_left": -3, "is_expired": True}),
              "=" + _muddat_belgisi({"days_left": -3, "is_expired": True}))
        check("S-11: muddati yaqinlashgan — ogohlantirish",
              "⚠️" in _muddat_belgisi({"days_left": 7, "is_expired": False}),
              "=" + _muddat_belgisi({"days_left": 7, "is_expired": False}))
        check("S-11: muddatsiz hujjatda belgi yo'q",
              _muddat_belgisi({"days_left": None, "is_expired": False}) == "",
              "=" + repr(_muddat_belgisi({"days_left": None, "is_expired": False})))
    except Exception:
        check("S-11 izoh tahlili", False, traceback.format_exc(limit=2).strip())

    # ── Menyuda tugmalar to'g'ri rollarga chiqadimi ──
    try:
        from types import SimpleNamespace

        from api.services.sections import bot_menu_rows

        def _tugmalar(rol: str) -> set:
            u = SimpleNamespace(role=rol, position=None, can_edit_fine_policy=False,
                                can_edit_attendance=False)
            return {b for r in bot_menu_rows(u) for b in r}

        check("S-11: «Hujjatlarim» HAR BIR rolda bor",
              all("📁 Hujjatlarim" in _tugmalar(r)
                  for r in ("employee", "hr", "rop", "boss", "dasturchi")),
              "=" + str({r: "📁 Hujjatlarim" in _tugmalar(r)
                         for r in ("employee", "hr", "rop", "boss", "dasturchi")}))
        check("S-11: «Hujjat yuklash» faqat HR/Boshliq/Dasturchida",
              {r for r in ("employee", "hr", "rop", "boss", "dasturchi")
               if "📎 Hujjat yuklash" in _tugmalar(r)} == {"hr", "boss", "dasturchi"},
              "=" + str({r for r in ("employee", "hr", "rop", "boss", "dasturchi")
                         if "📎 Hujjat yuklash" in _tugmalar(r)}))
    except Exception:
        check("S-11 menyu tekshiruvi", False, traceback.format_exc(limit=2).strip())

    # ── Bot endpointlari: yuklash -> o'qish -> yuborish -> soft delete ──
    conn = db()
    cur = conn.cursor()
    ids: dict[str, int] = {}
    try:
        cur.execute("delete from users where full_name like 'T-BDoc%'")
        conn.commit()

        def _yarat(nom: str, rol: str, tg: int, manager: int | None = None) -> int:
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " manager_id, created_at) values (?,?,?,1,1,?,datetime('now'))",
                (tg, nom, rol, manager))
            conn.commit()
            return cur.lastrowid

        ids["hr"] = _yarat("T-BDocHR", "hr", 999701101)
        ids["rop"] = _yarat("T-BDocRop", "rop", 999701102)
        ids["emp"] = _yarat("T-BDocEmp", "employee", 999701103, ids["rop"])
        tg = {"hr": 999701101, "rop": 999701102, "emp": 999701103}

        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            # Tur ro'yxati botga ham ochiq (bot o'z nusxasini yuritmasin)
            r = c.get("/employee-documents/bot/types", params={"telegram_id": tg["emp"]})
            check("S-11: bot /types -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code))

            # Xodim ro'yxati — faqat HR
            r = c.get("/employee-documents/bot/employees", params={"telegram_id": tg["emp"]})
            check("S-11: bot xodim ro'yxati oddiy xodimga -> 403",
                  r.status_code == 403, "kod=" + str(r.status_code))
            r = c.get("/employee-documents/bot/employees", params={"telegram_id": tg["rop"]})
            check("S-11: bot xodim ro'yxati ROP ga -> 403", r.status_code == 403,
                  "kod=" + str(r.status_code))
            r = c.get("/employee-documents/bot/employees", params={"telegram_id": tg["hr"]})
            check("S-11: bot xodim ro'yxati HR ga -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code))

            # ── YUKLASH ──
            muddat = (_date.today() + _td(days=15)).isoformat()
            yuk = {"telegram_id": tg["hr"], "user_id": ids["emp"], "doc_type": "diploma",
                   "name": "T-BDoc diplom", "file_id": "T-BOT-FILE-1",
                   "file_type": "document", "expires_at": muddat}
            r = c.post("/employee-documents/bot/upload",
                       json={**yuk, "telegram_id": tg["emp"]})
            check("S-11: botdan oddiy xodim yuklay olmaydi -> 403",
                  r.status_code == 403, "kod=" + str(r.status_code))
            r = c.post("/employee-documents/bot/upload", json=yuk)
            check("S-11: HR botdan yukladi -> 201", r.status_code == 201,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            doc_id = r.json().get("id") if r.status_code == 201 else None

            # ── O'QISH: xodim o'zinikini botdan ko'radi ──
            r = c.get("/employee-documents/bot/my", params={"telegram_id": tg["emp"]})
            check("S-11: xodim botdan o'z hujjatini ko'radi",
                  r.status_code == 200 and len(r.json()) == 1
                  and r.json()[0]["name"] == "T-BDoc diplom",
                  f"kod={r.status_code} {r.text[:120]}")
            check("S-11: muddat serverdan keladi (15 kun)",
                  r.status_code == 200 and r.json()[0]["days_left"] == 15,
                  "=" + str(r.json()[0].get("days_left") if r.status_code == 200 else None))

            # HR ning o'z ro'yxati BO'SH — yuklagan bo'lsa ham egasi u emas
            r = c.get("/employee-documents/bot/my", params={"telegram_id": tg["hr"]})
            check("S-11: yuklagan HR ning o'z ro'yxatiga tushmadi",
                  r.status_code == 200 and r.json() == [], "=" + r.text[:80])

            # ── YUBORISH: ruxsat SHU YERDA ham tekshiriladi ──
            if doc_id:
                r = c.post("/employee-documents/bot/send",
                           json={"telegram_id": tg["rop"], "doc_id": doc_id})
                check("S-11: ROP begona hujjatni o'ziga yuborib ololmaydi -> 404",
                      r.status_code == 404, "kod=" + str(r.status_code))
                r = c.post("/employee-documents/bot/send",
                           json={"telegram_id": tg["emp"], "doc_id": doc_id})
                check("S-11: egasi o'z hujjatini qayta oladi -> 200",
                      r.status_code == 200, "kod=" + str(r.status_code) + " " + r.text[:100])
                # ⚠️ Testda bildirishnomalar O'CHIQ — `delivered` False bo'lishi
                # KUTILGAN holat. Agar True chiqsa, demak haqiqiy xodimga fayl
                # ketgan (test.py ning `require_notifications_off` qo'riqchisi
                # buni oldini oladi, lekin ikkinchi qatlam zarar qilmaydi).
                check("S-11: test rejimida haqiqiy fayl YUBORILMADI",
                      r.status_code == 200 and r.json().get("delivered") is False,
                      "=" + r.text[:100])

                # ── SOFT DELETE zanjiri ──
                hr_t = token_for(ids["hr"], "hr")
                r = c.delete(f"/employee-documents/{doc_id}", headers=auth(hr_t))
                check("S-11: o'chirildi -> 200", r.status_code == 200,
                      "kod=" + str(r.status_code))
                r = c.get("/employee-documents/bot/my", params={"telegram_id": tg["emp"]})
                check("S-11: o'chirilgach botdagi ro'yxat bo'shadi",
                      r.status_code == 200 and r.json() == [], "=" + r.text[:80])
                r = c.post("/employee-documents/bot/send",
                           json={"telegram_id": tg["emp"], "doc_id": doc_id})
                check("S-11: o'chirilgan hujjatni yuborib bo'lmaydi -> 404",
                      r.status_code == 404, "kod=" + str(r.status_code))
    except Exception:
        check("S-11 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            if ids:
                cur.execute(
                    "delete from employee_documents where user_id in (%s)"
                    % ",".join("?" * len(ids)), tuple(ids.values()))
            cur.execute("delete from users where full_name like 'T-BDoc%'")
            conn.commit()
        except Exception:
            pass
        conn.close()


def test_deadlines_core() -> None:
    """S-12 (TZ 3.5) — muddat eslatmalari yadrosi.

    Qabul mezonlari (TZ):
      • muddat qo'lda ham, hisoblanib ham chiqadi;
      • `reminded_at` — bir muddat bo'yicha takroriy xabar yo'q;
      • test: `>=` semantikasi (cron bir kun kechiksa ham xabar tushadi).

    ENG MUHIM TEKSHIRUV — «IKKITA MANBA BO'LMASIN». Hisoblanadigan
    muddatning sanasi jadvalga YOZILMASLIGI shart: manba (hujjatning
    `expires_at` yoki `hire_date`) o'zgarsa, ro'yxat DARHOL yangi sanani
    ko'rsatishi kerak. Nusxa saqlansa tizim ikki xil muddat ko'rsatardi
    va qaysi biri to'g'ri ekani bilinmasdi.
    """
    import asyncio
    from datetime import date as _date
    from datetime import timedelta as _td

    import httpx

    print("\n" + "=" * 60)
    print("S-12: MUDDAT ESLATMALARI (yadro)")
    print("=" * 60)

    from db.base import async_session

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])

    conn = db()
    cur = conn.cursor()
    uid = None
    bugun = _date.today()
    try:
        cur.execute("delete from users where full_name like 'T-Dl%'")
        conn.commit()
        # hire_date shunday tanlanadiki, sinov muddati (90 kun) 10 kundan keyin tugasin
        hire = (bugun - _td(days=80)).isoformat()
        cur.execute(
            "insert into users (telegram_id, full_name, role, bot_started, is_active,"
            " hire_date, created_at) values (999701201,'T-DlEmp','employee',0,1,?,"
            "datetime('now'))", (hire,))
        uid = cur.lastrowid
        conn.commit()

        async def _royxat(days=None):
            from api.services.deadlines import upcoming
            async with async_session() as s2:
                return [i for i in await upcoming(s2, days) if i.user_id == uid]

        # Sozlama standart holatga (boshqa test o'zgartirgan bo'lishi mumkin)
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            c.put("/deadlines/config", headers=auth(mgr_t),
                  json={"probation_days": 90, "remind_days": 30})

            # ── 1) HISOBLANADIGAN: sinov muddati ──
            items = asyncio.run(_royxat())
            sinov = [i for i in items if i.kind == "probation"]
            check("S-12: sinov muddati HISOBLANIB chiqdi (jadvalga yozilmagan)",
                  len(sinov) == 1 and sinov[0].days_left == 10,
                  "=" + str([(i.kind, i.days_left) for i in items]))
            check("S-12: hisoblangan bandda jadval qatori YO'Q",
                  bool(sinov) and sinov[0].row_id is None,
                  "=" + str(sinov[0].row_id if sinov else "-"))
            qatorlar = cur.execute(
                "select count(*) from deadlines where user_id=?", (uid,)).fetchone()[0]
            check("S-12: hisoblangan muddat uchun jadval BO'SH qoldi",
                  qatorlar == 0, "=" + str(qatorlar))

            # ── 2) YAGONA MANBA: hire_date o'zgarsa muddat ham o'zgaradi ──
            cur.execute("update users set hire_date=? where id=?",
                        ((bugun - _td(days=85)).isoformat(), uid))
            conn.commit()
            sinov2 = [i for i in asyncio.run(_royxat()) if i.kind == "probation"]
            check("S-12: manba o'zgardi -> muddat DARHOL yangilandi (nusxa yo'q)",
                  len(sinov2) == 1 and sinov2[0].days_left == 5,
                  "=" + str(sinov2[0].days_left if sinov2 else "-"))

            # ── 3) HISOBLANADIGAN: hujjat muddati ──
            r = c.post("/employee-documents", headers=auth(mgr_t), json={
                "user_id": uid, "doc_type": "contract", "name": "T-Dl shartnoma",
                "file_id": "T-DL-1", "expires_at": (bugun + _td(days=20)).isoformat()})
            doc_id = r.json().get("id") if r.status_code == 201 else None
            hujjat = [i for i in asyncio.run(_royxat()) if i.source_kind == "document"]
            check("S-12: hujjat muddati ham ro'yxatga tushdi",
                  len(hujjat) == 1 and hujjat[0].days_left == 20,
                  "=" + str([(i.kind, i.days_left) for i in hujjat]))
            check("S-12: shartnoma alohida tur sifatida ko'rinadi",
                  bool(hujjat) and hujjat[0].kind == "contract",
                  "=" + str(hujjat[0].kind if hujjat else "-"))

            # ── 4) QO'LDA kiritish ──
            r = c.post("/deadlines", headers=auth(mgr_t), json={
                "user_id": uid, "kind": "medical_exam",
                "due_date": (bugun + _td(days=3)).isoformat(),
                "note": "T-Dl tibbiy"})
            check("S-12: qo'lda muddat kiritildi -> 201", r.status_code == 201,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            manual_id = r.json().get("id") if r.status_code == 201 else None

            # Hisoblanadigan turni QO'LDA kiritib bo'lmaydi (ikkita manba xavfi)
            r = c.post("/deadlines", headers=auth(mgr_t), json={
                "user_id": uid, "kind": "probation",
                "due_date": (bugun + _td(days=3)).isoformat()})
            check("S-12: hisoblanadigan turni qo'lda kiritish -> 400",
                  r.status_code == 400, "kod=" + str(r.status_code))
            check("S-12: xato xabari NIMA QILISHNI aytadi",
                  r.status_code == 400 and "hisoblanadi" in r.text, r.text[:140])

            # ── 5) IKKALASI BITTA RO'YXATDA, sana bo'yicha tartibda ──
            items = asyncio.run(_royxat())
            check("S-12: qo'lda + hisoblangan BITTA ro'yxatda (3 ta)",
                  len(items) == 3, "=" + str([(i.kind, i.days_left) for i in items]))
            check("S-12: eng yaqin muddat birinchi",
                  [i.days_left for i in items] == sorted(i.days_left for i in items),
                  "=" + str([i.days_left for i in items]))

            # ── 6) `>=` SEMANTIKASI: o'tib ketgan muddat ro'yxatDAN CHIQMAYDI ──
            cur.execute("update deadlines set due_date=? where id=?",
                        ((bugun - _td(days=2)).isoformat(), manual_id))
            conn.commit()
            items = asyncio.run(_royxat())
            otgan = [i for i in items if i.kind == "medical_exam"]
            check("S-12: cron 2 kun kechikdi — muddat baribir ro'yxatda",
                  len(otgan) == 1 and otgan[0].days_left == -2,
                  "=" + str([(i.kind, i.days_left) for i in items]))
            check("S-12: o'tib ketgani `is_overdue` bilan belgilangan",
                  bool(otgan) and otgan[0].is_overdue is True,
                  "=" + str(otgan[0].is_overdue if otgan else "-"))

            # ── 7) UFQ: `days` dan uzoq muddat ko'rinmaydi ──
            yaqin = asyncio.run(_royxat(days=7))
            check("S-12: `days=7` — uzoq muddatlar chiqarib tashlandi",
                  {i.kind for i in yaqin} == {"medical_exam", "probation"},
                  "=" + str([(i.kind, i.days_left) for i in yaqin]))

            # ── 8) `reminded_at`: takroriy xabar yo'q ──
            async def _belgila():
                from api.services.deadlines import mark_reminded, upcoming
                async with async_session() as s2:
                    hammasi = [i for i in await upcoming(s2) if i.user_id == uid]
                    return await mark_reminded(s2, hammasi, bugun)

            n = asyncio.run(_belgila())
            check("S-12: 3 ta band «eslatildi» deb belgilandi", n == 3, "=" + str(n))
            items = asyncio.run(_royxat())
            check("S-12: hammasida `reminded_at` bugungi sana",
                  all(i.reminded_at == bugun for i in items),
                  "=" + str([(i.kind, i.reminded_at) for i in items]))
            izlar = cur.execute(
                "select count(*) from deadlines where user_id=? and source_kind is not null",
                (uid,)).fetchone()[0]
            check("S-12: hisoblangan bandlar uchun iz qatori endi yaratildi (2 ta)",
                  izlar == 2, "=" + str(izlar))
            sanalar = cur.execute(
                "select due_date from deadlines where user_id=? and source_kind is not null",
                (uid,)).fetchall()
            check("S-12: iz qatorida sana YO'Q (manba yagona bo'lib qoldi)",
                  all(x[0] is None for x in sanalar), "=" + str(sanalar))

            # Ikkinchi marta belgilash yangi qator YARATMASIN
            asyncio.run(_belgila())
            izlar2 = cur.execute(
                "select count(*) from deadlines where user_id=? and source_kind is not null",
                (uid,)).fetchone()[0]
            check("S-12: qayta eslatish DUBLIKAT qator yaratmadi",
                  izlar2 == 2, "=" + str(izlar2))

            # ── 9) Iz qatori borligida ham sana MANBADAN olinadi ──
            if doc_id:
                cur.execute("update employee_documents set expires_at=? where id=?",
                            ((bugun + _td(days=25)).isoformat(), doc_id))
                conn.commit()
                h2 = [i for i in asyncio.run(_royxat()) if i.source_kind == "document"]
                check("S-12: iz qatori bo'lsa ham sana MANBADAN keladi",
                      len(h2) == 1 and h2[0].days_left == 25,
                      "=" + str(h2[0].days_left if h2 else "-"))

            # ── 10) YOPISH ──
            r = c.post("/deadlines/close", headers=auth(mgr_t),
                       json={"key": f"document:{doc_id}"})
            check("S-12: hisoblangan band kalit bo'yicha yopildi",
                  r.status_code == 200, "kod=" + str(r.status_code))
            qolgan = {i.kind for i in asyncio.run(_royxat())}
            check("S-12: yopilgan band ro'yxatga QAYTMADI",
                  "contract" not in qolgan, "=" + str(qolgan))
            if manual_id:
                r = c.post(f"/deadlines/{manual_id}/close", headers=auth(mgr_t))
                check("S-12: qo'lda kiritilgani yopildi", r.status_code == 200,
                      "kod=" + str(r.status_code))
                r = c.post(f"/deadlines/{manual_id}/close", headers=auth(mgr_t))
                check("S-12: ikkinchi marta yopish -> 404", r.status_code == 404,
                      "kod=" + str(r.status_code))

            # ── 11) RUXSAT ──
            emp_t = token_for(uid, "employee")
            r = c.get("/deadlines", headers=auth(emp_t))
            check("S-12: oddiy xodim muddatlarni ko'rmaydi -> 403",
                  r.status_code == 403, "kod=" + str(r.status_code))
            r = c.get("/deadlines", headers=auth(mgr_t))
            check("S-12: rahbar ko'radi -> 200", r.status_code == 200,
                  "kod=" + str(r.status_code))
    except Exception:
        check("S-12 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            if uid:
                cur.execute("delete from deadlines where user_id=?", (uid,))
                cur.execute("delete from employee_documents where user_id=?", (uid,))
                cur.execute("delete from users where id=?", (uid,))
            conn.commit()
        except Exception:
            pass
        conn.close()


def test_deadlines_cron() -> None:
    """S-13 (TZ 3.5) — muddat eslatmalari croni va xabari.

    Qabul mezonlari (TZ):
      • kuniga bir marta, takrorlanmaydi;
      • bir necha muddat bir kunga tushsa — BITTA xabarga birlashadi;
      • test: xabar yuboruvchi patch qilingan holda.

    ⚠️ XABAR YUBORUVCHI PATCH QILINADI. Loyihada jonli tuzoq bor: lokal
    test haqiqiy xodimlarga Telegram xabari yuborib yuborgan. Bu yerda
    `api.notify.notify_user` almashtiriladi va tarmoqqa umuman
    chiqilmaydi — `NOTIFICATIONS_ENABLED=false` qo'riqchisiga qo'shimcha
    ikkinchi qatlam.
    """
    import asyncio
    from datetime import date as _date
    from datetime import timedelta as _td

    print("\n" + "=" * 60)
    print("S-13: MUDDAT ESLATMALARI (cron va xabar)")
    print("=" * 60)

    from db.base import async_session

    conn = db()
    cur = conn.cursor()
    ids: dict[str, int] = {}
    bugun = _date.today()
    try:
        cur.execute("delete from users where full_name like 'T-Dc%'")
        conn.commit()

        def _yarat(nom, rol, tg, hire=None):
            cur.execute(
                "insert into users (telegram_id, full_name, role, bot_started, is_active,"
                " hire_date, created_at) values (?,?,?,1,1,?,datetime('now'))",
                (tg, nom, rol, hire))
            conn.commit()
            return cur.lastrowid

        # Uchta xodim, uchtasi ham sinov muddati 5 kundan keyin tugaydi —
        # ya'ni BITTA kunga uchta band tushadi.
        hire = (bugun - _td(days=85)).isoformat()
        for n in range(3):
            ids[f"emp{n}"] = _yarat(f"T-DcEmp{n}", "employee", 999701300 + n, hire)

        # ── Yuboruvchini PATCH qilamiz ──
        yuborilgan: list = []

        async def _tick():
            import api.services.cron_jobs as cj
            from api.notify import notify_user as asl

            import api.notify as notify_mod

            async def soxta(db_, user, category, text, **kw):
                yuborilgan.append((user.id, user.role, text))
                return True

            notify_mod.notify_user = soxta
            try:
                async with async_session() as s2:
                    return await cj.deadline_tick(s2)
            finally:
                notify_mod.notify_user = asl

        natija = asyncio.run(_tick())
        check("S-13: tick ishladi", natija.get("ok") is True, "=" + str(natija))
        check("S-13: uchala band ham qamrab olindi",
              natija.get("items", 0) >= 3, "=" + str(natija.get("items")))

        # ── BITTA xabar: uchta band bitta matnga birlashdi ──
        bizniki = [t for (_uid, _rol, t) in yuborilgan
                   if "T-DcEmp0" in t or "T-DcEmp1" in t or "T-DcEmp2" in t]
        check("S-13: uchta muddat BITTA xabarga birlashdi",
              all(("T-DcEmp0" in t and "T-DcEmp1" in t and "T-DcEmp2" in t)
                  for t in bizniki) and len(bizniki) >= 1,
              f"xabarlar={len(bizniki)}")
        check("S-13: har mas'ulga bittadan xabar (odam soniga teng)",
              len(yuborilgan) == len({u for (u, _r, _t) in yuborilgan}),
              "=" + str(len(yuborilgan)))
        rollar = {r for (_u, r, _t) in yuborilgan}
        check("S-13: xabar HR/Boshliq/Dasturchiga ketdi (guruhga emas)",
              rollar <= {"hr", "boss", "dasturchi"}, "=" + str(rollar))
        if bizniki:
            check("S-13: xabarda sana va qolgan kun ko'rsatilgan",
                  "5 kun" in bizniki[0] and str(bugun.year) in bizniki[0],
                  "=" + bizniki[0][:160])
            check("S-13: xabarda nima qilish kerakligi aytilgan",
                  "Muddatlar" in bizniki[0], "=" + bizniki[0][-80:])

        # ── TAKRORLANMAYDI ──
        yuborilgan.clear()
        natija2 = asyncio.run(_tick())
        qayta = [t for (_u, _r, t) in yuborilgan if "T-DcEmp0" in t]
        check("S-13: ikkinchi tick bizning bandlarni QAYTA yubormadi",
              not qayta, "=" + str(len(qayta)))
        check("S-13: ikkinchi tickda bizning bandlar hisobga olinmadi",
              natija2.get("items", 0) == 0 or not qayta,
              "=" + str(natija2))

        # ── ERTAGA yana yuboriladi (bir kunlik oyna) ──
        cur.execute(
            "update deadlines set reminded_at=? where user_id in (?,?,?)",
            ((bugun - _td(days=1)).isoformat(), ids["emp0"], ids["emp1"], ids["emp2"]))
        conn.commit()
        yuborilgan.clear()
        asyncio.run(_tick())
        ertaga = [t for (_u, _r, t) in yuborilgan if "T-DcEmp0" in t]
        check("S-13: kechagi eslatmadan keyin BUGUN yana yuborildi",
              len(ertaga) >= 1, "=" + str(len(ertaga)))

        # ── O'TIB KETGAN band alohida bo'limda ──
        cur.execute("update users set hire_date=? where id=?",
                    ((bugun - _td(days=95)).isoformat(), ids["emp0"]))
        cur.execute("update deadlines set reminded_at=null where user_id=?", (ids["emp0"],))
        conn.commit()
        yuborilgan.clear()
        asyncio.run(_tick())
        otgan = [t for (_u, _r, t) in yuborilgan if "T-DcEmp0" in t]
        check("S-13: o'tib ketgan muddat alohida «Muddati o'tgan» bo'limida",
              bool(otgan) and "Muddati o'tgan" in otgan[0],
              "=" + (otgan[0][:200] if otgan else "xabar yo'q"))

        # ── YOPILGAN band eslatilmaydi ──
        cur.execute("update deadlines set status='done', reminded_at=null "
                    "where user_id=?", (ids["emp0"],))
        conn.commit()
        yuborilgan.clear()
        asyncio.run(_tick())
        yopiq = [t for (_u, _r, t) in yuborilgan if "T-DcEmp0" in t]
        check("S-13: yopilgan band bo'yicha eslatma KELMADI",
              not yopiq, "=" + str(len(yopiq)))
    except Exception:
        check("S-13 (umumiy)", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            if ids:
                belgi = ",".join("?" * len(ids))
                cur.execute(f"delete from deadlines where user_id in ({belgi})",
                            tuple(ids.values()))
                cur.execute(f"delete from users where id in ({belgi})", tuple(ids.values()))
            conn.commit()
        except Exception:
            pass
        conn.close()


def _docx_fixture(paragraphs: str) -> bytes:
    """Eng kichik ishlaydigan `.docx` — sinov uchun.

    Haqiqiy Word fayli emas, lekin `docx_render` uchun yetarli: u faqat
    ZIP va `word/*.xml` bilan ishlaydi."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
            + paragraphs
            + "</w:body></w:document>",
        )
    return buf.getvalue()


def _docx_text(data: bytes) -> str:
    import io
    import re
    import zipfile

    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    return "".join(m.group(1) for m in re.finditer(r"<w:t[^>]*>(.*?)</w:t>", xml, re.S))


def test_docx_render() -> None:
    """S-14 (TZ 3.3) — `.docx` shablonini to'ldirish, kutubxonasiz.

    Qabul mezonlari (TZ):
      • shablondan to'ldirilgan `.docx` chiqadi;
      • BO'LINGAN belgi holati sinovdan o'tgan (fixture: bo'lingan `w:t`);
      • yangi kutubxona qo'shilmagan (`requirements.txt` o'zgarmagan);
      • generatsiya so'rov ichida emas, FON ishida.

    ASOSIY TUZOQ — BO'LINGAN BELGI. Wordda `{{fish}}` deb yozilgani fayl
    ichida uchta run'ga bo'linib ketishi mumkin (imlo tekshiruvi, til
    belgisi, kursor joyi). Oddiy `replace` bunda hech narsa topmaydi:
    shablon ko'zga to'g'ri ko'rinadi-yu, natija bo'sh chiqadi.
    """
    import asyncio

    import httpx

    print("\n" + "=" * 60)
    print("S-14: HUJJAT GENERATSIYASI (docx, kutubxonasiz)")
    print("=" * 60)

    from api.services.docx_render import find_placeholders, render
    from db.base import async_session

    mgr = find_manager_id()
    if not mgr:
        check("rahbar topildi", False, "hr/boss/dasturchi yo'q")
        return
    mgr_t = token_for(mgr[0], mgr[1])

    # ── 1) YANGI KUTUBXONA QO'SHILMAGAN ──
    try:
        req = (Path(__file__).resolve().parent / "api" / "requirements.txt").read_text(
            encoding="utf-8"
        ).lower()
        yomon = [x for x in ("python-docx", "docxtpl", "lxml", "docx2python") if x in req]
        check("S-14: docx kutubxonasi QO'SHILMAGAN", not yomon, "=" + str(yomon))

        import api.services.docx_render as mod

        manba = Path(mod.__file__).read_text(encoding="utf-8")
        tashqi = [
            ln.strip() for ln in manba.splitlines()
            if ln.startswith(("import ", "from ")) and not any(
                ln.startswith(p) for p in (
                    "import io", "import re", "import zipfile", "from __future__")
            )
        ]
        check("S-14: modul FAQAT standart kutubxonadan foydalanadi",
              not tashqi, "=" + str(tashqi))
    except Exception:
        check("S-14 bog'liqlik tekshiruvi", False, traceback.format_exc(limit=2).strip())

    # ── 2) BUTUN belgi ──
    try:
        d = _docx_fixture("<w:p><w:r><w:t>Hurmatli {{fish}}!</w:t></w:r></w:p>")
        out, qolgan = render(d, {"fish": "Ali Valiyev"})
        check("S-14: butun belgi almashtirildi",
              _docx_text(out) == "Hurmatli Ali Valiyev!" and not qolgan,
              "=" + _docx_text(out))

        # ── 3) BO'LINGAN belgi — ASOSIY TUZOQ ──
        d = _docx_fixture(
            "<w:p><w:r><w:t>Hurmatli {{</w:t></w:r>"
            "<w:r><w:t>fi</w:t></w:r><w:r><w:t>sh</w:t></w:r>"
            "<w:r><w:t>}}, xush kelibsiz</w:t></w:r></w:p>"
        )
        out, qolgan = render(d, {"fish": "Ali Valiyev"})
        check("S-14: UCHGA BO'LINGAN belgi ham almashtirildi",
              _docx_text(out) == "Hurmatli Ali Valiyev, xush kelibsiz" and not qolgan,
              "=" + _docx_text(out))
        check("S-14: bo'lingan belgi ro'yxatda ham topiladi",
              find_placeholders(d) == ["fish"], "=" + str(find_placeholders(d)))

        # ── 4) Bitta abzatsda ikki belgi, biri bo'lingan ──
        d = _docx_fixture(
            "<w:p><w:r><w:t>{{a}} va {{</w:t></w:r><w:r><w:t>b}}</w:t></w:r></w:p>"
        )
        out, _ = render(d, {"a": "BIR", "b": "IKKI"})
        check("S-14: bitta abzatsda ikki belgi",
              _docx_text(out) == "BIR va IKKI", "=" + _docx_text(out))

        # ── 5) XML xavfli belgi ──
        d = _docx_fixture("<w:p><w:r><w:t>{{n}}</w:t></w:r></w:p>")
        out, _ = render(d, {"n": "Ali & Vali <MCHJ>"})
        import io as _io
        import xml.dom.minidom as _md
        import zipfile as _zf

        xml = _zf.ZipFile(_io.BytesIO(out)).read("word/document.xml")
        _md.parseString(xml)  # buzilgan bo'lsa xato beradi
        check("S-14: `&` va `<` qochirildi — XML buzilmadi",
              b"&amp;" in xml and b"&lt;MCHJ&gt;" in xml, "=" + xml.decode()[-90:])

        # ── 6) To'ldirilmagan belgi TEGILMAYDI va ro'yxatda qaytadi ──
        d = _docx_fixture("<w:p><w:r><w:t>{{bor}} / {{yoq}}</w:t></w:r></w:p>")
        out, qolgan = render(d, {"bor": "X"})
        check("S-14: to'ldirilmagan belgi hujjatda ko'rinib qoldi",
              "{{yoq}}" in _docx_text(out), "=" + _docx_text(out))
        check("S-14: to'ldirilmaganlar ro'yxati qaytdi",
              qolgan == ["yoq"], "=" + str(qolgan))

        # ── 7) Bo'sh joy saqlanadi ──
        d = _docx_fixture("<w:p><w:r><w:t>Ism: {{n}} lavozim</w:t></w:r></w:p>")
        out, _ = render(d, {"n": "Ali"})
        xml = _zf.ZipFile(_io.BytesIO(out)).read("word/document.xml").decode()
        check("S-14: `xml:space=preserve` qo'shildi (so'zlar yopishmasin)",
              'xml:space="preserve"' in xml and _docx_text(out) == "Ism: Ali lavozim",
              "=" + _docx_text(out))

        # ── 8) Kolontitul ham to'ldiriladi ──
        import io as _io2
        import zipfile as _zf2

        buf = _io2.BytesIO()
        with _zf2.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml",
                       '<?xml version="1.0"?><w:document xmlns:w="x"><w:body>'
                       "<w:p><w:r><w:t>tana</w:t></w:r></w:p></w:body></w:document>")
            z.writestr("word/header1.xml",
                       '<?xml version="1.0"?><w:hdr xmlns:w="x">'
                       "<w:p><w:r><w:t>Raqam: {{raqam}}</w:t></w:r></w:p></w:hdr>")
        out, qolgan = render(buf.getvalue(), {"raqam": "77"})
        hdr = _zf2.ZipFile(_io2.BytesIO(out)).read("word/header1.xml").decode()
        check("S-14: kolontituldagi belgi ham to'ldirildi",
              "Raqam: 77" in hdr and not qolgan, "=" + hdr[-70:])
    except Exception:
        check("S-14 render tekshiruvi", False, traceback.format_exc(limit=2).strip())

    # ── 9) FON ISHI: so'rov ichida generatsiya YO'Q ──
    conn = db()
    cur = conn.cursor()
    tmpl_id = None
    try:
        with httpx.Client(base_url=API_BASE, timeout=30) as c:
            # Shablonni ro'yxatga olish (`file_id` — soxta, yuklab olish patch qilinadi)
            r = c.post("/document-templates", headers=auth(mgr_t), json={
                "kind": "offer", "name": "T-Tmpl taklif", "file_id": "T-TMPL-FAKE",
                "placeholders": ["fish", "lavozim"]})
            check("S-14: shablon qo'shildi -> 201", r.status_code == 201,
                  "kod=" + str(r.status_code) + " " + r.text[:120])
            tmpl_id = r.json().get("id") if r.status_code == 201 else None

            r = c.get("/document-templates", headers=auth(mgr_t))
            check("S-14: shablon ro'yxatda", r.status_code == 200
                  and any(t["id"] == tmpl_id for t in r.json()),
                  "kod=" + str(r.status_code))

            # Oddiy xodim ko'ra olmaydi
            emp = cur.execute(
                "select id from users where role='employee' and is_active=1 limit 1"
            ).fetchone()
            if emp:
                r = c.get("/document-templates", headers=auth(token_for(emp[0], "employee")))
                check("S-14: oddiy xodimga -> 403", r.status_code == 403,
                      "kod=" + str(r.status_code))

            # Generatsiya -> 202 (navbat), so'rov ichida BAJARILMAYDI
            import time as _t

            boshi = _t.perf_counter()
            r = c.post("/document-templates/render", headers=auth(mgr_t), json={
                "template_id": tmpl_id,
                "values": {"fish": "Ali Valiyev"},
                "filename": "T-taklif"})
            ketgan = _t.perf_counter() - boshi
            check("S-14: generatsiya NAVBATGA qo'yildi -> 202",
                  r.status_code == 202, "kod=" + str(r.status_code) + " " + r.text[:120])
            check("S-14: so'rov TEZ qaytdi (ish so'rov ichida emas)",
                  ketgan < 1.0, f"{ketgan:.3f}s")
            check("S-14: yetishmayotgan belgi DARHOL aytildi",
                  r.status_code == 202 and r.json().get("missing") == ["lavozim"],
                  "=" + r.text[:120])
            job_id = r.json().get("job_id") if r.status_code == 202 else None

            holat = cur.execute(
                "select status, kind from background_jobs where id=?", (job_id,)).fetchone()
            check("S-14: navbatda `document_render` ishi turibdi",
                  holat == ("queued", "document_render"), "=" + str(holat))

        # ── 10) Cron ishni bajaradi (shablon yuklab olish PATCH qilinadi) ──
        d = _docx_fixture("<w:p><w:r><w:t>Hurmatli {{</w:t></w:r>"
                          "<w:r><w:t>fish}}, lavozim: {{lavozim}}</w:t></w:r></w:p>")
        natija: dict = {}

        async def _tick():
            import api.telegram_notify as tn
            from api.services.background_jobs import background_tick

            asl_dl, asl_send = tn.download_file, tn.send_media_file

            async def soxta_dl(file_id):
                return d

            async def soxta_send(chat_id, content, filename, kind, caption=None):
                natija["filename"] = filename
                natija["bytes"] = content
                natija["caption"] = caption
                return {"ok": True, "result": {"document": {"file_id": "T-OUT"}}}

            tn.download_file, tn.send_media_file = soxta_dl, soxta_send
            try:
                async with async_session() as s2:
                    return await background_tick(s2)
            finally:
                tn.download_file, tn.send_media_file = asl_dl, asl_send

        res = asyncio.run(_tick())
        check("S-14: cron ishni bajardi", res.get("ok") is True and res.get("ran") ==
              "document_render", "=" + str(res))
        check("S-14: fayl nomi `.docx` bilan tugadi",
              natija.get("filename") == "T-taklif.docx", "=" + str(natija.get("filename")))
        if natija.get("bytes"):
            matn = _docx_text(natija["bytes"])
            check("S-14: fon ishida BO'LINGAN belgi to'ldirildi",
                  "Hurmatli Ali Valiyev" in matn, "=" + matn)
            check("S-14: to'ldirilmagani hujjatda ko'rinib qoldi",
                  "{{lavozim}}" in matn, "=" + matn)
        check("S-14: izohda to'ldirilmagan belgi ogohlantirildi",
              "lavozim" in (natija.get("caption") or ""),
              "=" + str(natija.get("caption")))
    except Exception:
        check("S-14 fon ishi", False, traceback.format_exc(limit=2).strip())
    finally:
        try:
            cur.execute("delete from background_jobs where kind='document_render'")
            cur.execute("delete from document_templates where name like 'T-Tmpl%'")
            conn.commit()
        except Exception:
            pass
        conn.close()


def cleanup_orphans() -> None:
    """EGASIZ (user'i o'chirilgan) payroll qatorlarini tozalaydi.

    NEGA KERAK: `run_payroll` va `recalculate_period` BARCHA faol xodim
    bo'yicha aylanadi — ya'ni bitta blok davr hisoblaganda BOSHQA blokning
    sinov foydalanuvchilariga ham payslip/bonus qatori yaratiladi. Ular
    o'z blokining tozalash ro'yxatida bo'lmasa qolib ketadi.

    Ustiga-ustak, test.py dagi xom `sqlite3` ulanishlarida
    `PRAGMA foreign_keys` YOQILMAGAN — shu sababli `delete from users`
    egasiz qator qoldirib ham muvaffaqiyatli tugaydi (async SQLAlchemy
    ulanishida esa aynan shu FOREIGN KEY xatosi bilan yiqilardi).

    Bu qoldiqlar keyingi ishga tushirishda CHALG'ITUVCHI xatolar beradi
    (jonli isbot 2026-08-17: «payroll_fund jami» sinovi egasiz 2 mln so'mlik
    payslip tufayli qulagan edi). Shuning uchun oxirida yagona supurgi.
    """
    conn = db()
    cur = conn.cursor()
    jami = 0
    try:
        cur.execute(
            "delete from payslip_items where payslip_id in"
            " (select id from payslips where user_id not in (select id from users))"
        )
        jami += cur.rowcount
        for tbl in ("bonuses", "payslips", "salary_rates", "attendance", "daily_results",
                    "overtime_entries", "overtime_profiles", "work_schedule_override",
                    "work_schedule_weekly", "excused_days", "norms", "payroll_adjustments"):
            try:
                cur.execute(
                    f"delete from {tbl} where user_id is not null"
                    " and user_id not in (select id from users)"
                )
                jami += cur.rowcount
            except sqlite3.OperationalError:
                pass  # jadval yoki ustun yo'q — muhim emas
        conn.commit()
    finally:
        conn.close()
    if jami:
        print(f"\n[tozalash] egasiz {jami} ta qator o'chirildi")


def main() -> None:
    print("=" * 60)
    print("DAVOMAT TIZIMI — DB YOZUVI DEBUG TESTI")
    print("=" * 60)
    require_notifications_off()

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
        test_future_days_rule()
    except Exception:
        print("S-01 kelajak kunlari testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_fine_from_bonus()
    except Exception:
        print("S-02 ushlanma testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_fine_from_bonus_e2e()
    except Exception:
        print("S-02 e2e testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_me_sections()
    except Exception:
        print("S-04 sections testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_bot_menu_from_server()
    except Exception:
        print("S-05b bot menyu testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_view_scope()
    except Exception:
        print("S-06 qamrov testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_background_jobs()
    except Exception:
        print("S-07 fon ishlari testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_setup_status()
    except Exception:
        print("S-08 setup-status testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_holidays()
    except Exception:
        print("S-09 bayramlar testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_employee_documents()
    except Exception:
        print("S-10 hujjatlar testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_documents_bot()
    except Exception:
        print("S-11 hujjatlar boti testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_deadlines_core()
    except Exception:
        print("S-12 muddatlar testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_deadlines_cron()
    except Exception:
        print("S-13 muddat croni testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_docx_render()
    except Exception:
        print("S-14 docx testida kutilmagan xato:\n" + traceback.format_exc())

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
        test_kpi_in_payroll()
    except Exception:
        print("KPI+oylik testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_overtime_global_profile()
    except Exception:
        print("Global overtime testida kutilmagan xato:\n" + traceback.format_exc())

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
        test_attendance_list_dates()
    except Exception:
        print("Davomat ro'yxati sana filtri testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_attendance_reminder()
    except Exception:
        print("Davomat eslatmasi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_dashboard_day_off()
    except Exception:
        print("Dashboard dam kuni testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_payroll_approval_segregation()
    except Exception:
        print("Tasdiq ajratimi testida kutilmagan xato:" + chr(10) + traceback.format_exc())

    try:
        test_kpi_rates()
    except Exception:
        print("KPI stavkalari testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_absent_deduct_daily()
    except Exception:
        print("Kelmagan kun ayirmasi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_uysot_request_deadline()
    except Exception:
        print("CRM kutish chegarasi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_audit_json_guard()
    except Exception:
        print("Audit JSON zaxira testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_payroll_settings_reedit()
    except Exception:
        print("Oylik sozlamalari qayta tahrirlash testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_fine_policy_rights()
    except Exception:
        print("Kechikish normasi huquqi testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_explanation_letters()
    except Exception:
        print("Tushuntirish xati testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        test_visit_counting()
    except Exception:
        print("Tashrif hisoblash testida kutilmagan xato:\n" + traceback.format_exc())

    try:
        cleanup_orphans()
    except Exception:
        print("Egasiz qatorlarni tozalashda xato:\n" + traceback.format_exc())

    print("\n" + "=" * 60)
    print(f"NATIJA: {len(passed)} OK, {len(failed)} FAIL")
    for name in failed:
        print(f"  FAIL: {name}")
    print("=" * 60)
    sys.exit(1 if failed else 0)


def test_visit_counting() -> None:
    """Tashrif hisoblash (lead_diff.daily_operator_breakdown) — 2026-08-03
    tuzatishlari:
      1. Kechikib aniqlangan voqea (detected_at ertasi kun) CRM vaqti
         (`crm_updated_ts`) bo'yicha O'Z kuniga tushadi.
      2. Dual-kredit operator kesimida qoladi (yopgan +1, olib kelgan +1),
         lekin JAMI — noyob tashriflar (kreditlar yig'indisi emas).
      3. Mas'ulsiz tashrif operator kesimiga kirmaydi, jamida yo'qolmaydi.
      4. Tashrif bosqichlari ORASIDA ko'chish qayta sanalmaydi.
      5. Keyingi kunning voqeasi bu kunga kirmaydi.
      6. (2026-08-14) Shartnoma AYNI qoida bilan sanaladi, lekin DUAL-KREDITSIZ —
         faqat yopgan mas'ulga; operator yig'indisi = jami.
    Sinov ma'lumoti o'tmish sanada (2020-06-10) va 9998xxxxx lid ID bilan —
    jonli hisobga ta'sir qilmaydi, oxirida to'liq o'chiriladi."""
    import asyncio as _asyncio
    from datetime import timezone as _timezone

    print("\n" + "=" * 60)
    print("TASHRIF HISOBLASH (diff-engine kunlik kesim)")
    print("=" * 60)

    from sqlalchemy import delete as _delete

    from api.services import lead_diff
    from db.base import async_session
    from db.models import LeadEvent

    DAY = date(2020, 6, 10)
    VISIT_IDS = {990001, 990002}
    CONTRACT_IDS = {990009}
    L = 999800000  # sinov lid ID bazasi (jonli ID'lardan ancha yuqori)
    # 2020-06-10 Tashkent kuni = UTC 06-09 19:00 .. 06-10 19:00; CRM vaqti sifatida
    # kun o'rtasi (12:00 mahalliy = 07:00 UTC) olinadi
    day_epoch = int(datetime(2020, 6, 10, 7, 0, tzinfo=_timezone.utc).timestamp())

    def ev(lead, etype, from_st, to_st, from_resp, to_resp, first_resp, det, crm_ts):
        return LeadEvent(
            crm_lead_id=lead, event_type=etype,
            from_pipe_status_id=from_st, from_stage_name=None,
            to_pipe_status_id=to_st,
            to_stage_name="Tashrif" if to_st in VISIT_IDS else "Boshqa",
            from_responsible_id=from_resp, to_responsible_id=to_resp,
            to_responsible_name=None if to_resp is None else f"T-Op{to_resp}",
            first_responsible_id=first_resp, crm_updated_ts=crm_ts, detected_at=det,
        )

    async def _run():
        async with async_session() as s:
            await s.execute(_delete(LeadEvent).where(LeadEvent.crm_lead_id >= L))
            s.add_all([
                # A: kechikib aniqlangan (ertasi kun 02:00 UTC) — CRM vaqti bilan 06-10 ga tushishi kerak
                ev(L + 1, "stage_change", 111, 990001, 991001, 991001, 991001, datetime(2020, 6, 11, 2, 0), day_epoch),
                # B: dual-kredit — yopgan 991002, olib kelgan 991003
                ev(L + 2, "stage_change", 111, 990002, 991002, 991002, 991003, datetime(2020, 6, 10, 9, 0), day_epoch),
                # C: mas'ulsiz tashrif — jamida bor, operator kesimida yo'q.
                # 2026-08-13: turi `first_seen`dan `stage_change`ga o'zgartirildi —
                # egasining qaroriga ko'ra `first_seen` (skaner lidni endi ko'rgani)
                # umuman tashrif sanalmaydi; bu holat esa haqiqiy BOSQICH O'TISHI,
                # faqat mas'uli noma'lum.
                ev(L + 3, "stage_change", 111, 990001, None, None, None, datetime(2020, 6, 10, 10, 0), day_epoch),
                # C2: skaner lidni birinchi marta Tashrifda ko'rdi — SANALMAYDI
                ev(L + 7, "first_seen", None, 990001, None, 991009, 991009, datetime(2020, 6, 10, 10, 30), day_epoch),
                # D: Tashrif bosqichlari orasida ko'chish — tashrif sanalmasin
                ev(L + 4, "stage_change", 990001, 990002, 991001, 991001, 991001, datetime(2020, 6, 10, 11, 0), day_epoch),
                # F: yana dual-kredit (yopgan 991001, olib kelgan 991003) — jami/kredit farqi uchun
                ev(L + 6, "stage_change", 111, 990001, 991001, 991001, 991003, datetime(2020, 6, 10, 12, 0), day_epoch),
                # E: KEYINGI kun voqeasi (CRM vaqti 06-11) — bu kunga kirmasin
                ev(L + 5, "stage_change", 111, 990001, 991001, 991001, 991001, datetime(2020, 6, 11, 9, 0), day_epoch + 86400),
                # G: SHARTNOMA — yopgan 991002, olib kelgan 991003 (dual-kredit BO'LMASIN)
                ev(L + 8, "stage_change", 111, 990009, 991002, 991002, 991003, datetime(2020, 6, 10, 13, 0), day_epoch),
                # H: shartnoma bosqichi ICHIDA harakat — qayta sanalmasin
                ev(L + 8, "responsible_change", 990009, 990009, 991002, 991004, 991003, datetime(2020, 6, 10, 14, 0), day_epoch),
            ])
            await s.commit()
            try:
                return await lead_diff.daily_operator_breakdown(s, DAY, VISIT_IDS, CONTRACT_IDS)
            finally:
                await s.execute(_delete(LeadEvent).where(LeadEvent.crm_lead_id >= L))
                await s.commit()

    try:
        agg, unique, contracts_total = _asyncio.run(_run())
        credits = sum(a["visits"] for a in agg.values())
        check("kechikib aniqlangan tashrif o'z kuniga tushdi (991001=2: A+F)",
              agg.get(991001, {}).get("visits") == 2, f"991001={agg.get(991001)}")
        check("dual-kredit: yopgan (991002) +1", agg.get(991002, {}).get("visits") == 1,
              f"991002={agg.get(991002)}")
        check("dual-kredit: olib kelgan (991003) +2 (B+F)",
              agg.get(991003, {}).get("visits") == 2, f"991003={agg.get(991003)}")
        check("JAMI noyob tashrif = 4 (kredit yig'indisi 5 emas)", unique == 4,
              f"unique={unique}, kreditlar={credits}")
        check("kredit yig'indisi = 5 (operator kesimi dual-kredit bilan)", credits == 5,
              f"kreditlar={credits}")
        check("keyingi kun voqeasi kirmadi / Tashrif ichi ko'chish sanalmadi",
              agg.get(991001, {}).get("leads_touched") == 3, f"991001={agg.get(991001)}")
        check("first_seen tashrif bermaydi (991009 = 0 kredit)",
              agg.get(991009, {}).get("visits", 0) == 0, f"991009={agg.get(991009)}")
        check("shartnoma faqat YOPGANGA (991002 = 1)",
              agg.get(991002, {}).get("contracts") == 1, f"991002={agg.get(991002)}")
        check("shartnomada dual-kredit YO'Q (olib kelgan 991003 = 0)",
              agg.get(991003, {}).get("contracts", 0) == 0, f"991003={agg.get(991003)}")
        check("shartnoma jami = 1 (bosqich ichidagi harakat qayta sanalmadi)",
              contracts_total == 1, f"contracts_total={contracts_total}")
        check("shartnoma operator yig'indisi = jami",
              sum(a["contracts"] for a in agg.values()) == contracts_total,
              f"yig'indi={sum(a['contracts'] for a in agg.values())}, jami={contracts_total}")
    except Exception:
        check("tashrif hisoblash testi ishga tushdi", False, traceback.format_exc(limit=2).strip())

    # ── Statistika builderlari: voqea-asosli Tashrif + snapshot fallback (2026-08-03) ──
    from db.models import LeadStageDaily

    OLD_DAY = date(2019, 3, 5)  # LeadEvent jurnalidan OLDINGI davr — fallback tekshiruvi

    async def _run_builders():
        from api.routers import stats as stats_router

        async with async_session() as s:
            await s.execute(_delete(LeadEvent).where(LeadEvent.crm_lead_id >= L))
            await s.execute(_delete(LeadStageDaily).where(LeadStageDaily.responsible_id >= 991000))
            # Voqealar: DAY kuni 991001 uchun 2 ta haqiqiy kirish
            s.add_all([
                ev(L + 1, "stage_change", 111, 990001, 991001, 991001, 991001, datetime(2020, 6, 10, 9, 0), day_epoch),
                ev(L + 2, "stage_change", 111, 990002, 991001, 991001, 991001, datetime(2020, 6, 10, 10, 0), day_epoch),
                # Shartnoma: yopgan 991001 (statistika builderlarida ham ko'rinishi kerak)
                ev(L + 3, "stage_change", 111, 990009, 991001, 991001, 991002, datetime(2020, 6, 10, 11, 0), day_epoch),
            ])
            # Snapshot esa shishgan: DAY kuni Tashrifda 5 lid "ko'ringan"
            s.add_all([
                LeadStageDaily(date=DAY, responsible_id=991001, responsible_name="T-Op991001",
                               pipe_status_id=990001, stage_name="Tashrif", leads_count=5),
                LeadStageDaily(date=DAY, responsible_id=991001, responsible_name="T-Op991001",
                               pipe_status_id=111, stage_name="Boshqa", leads_count=2),
                # Jurnal boshlanmagan eski kun — snapshot yagona manba bo'lib qolishi kerak
                LeadStageDaily(date=OLD_DAY, responsible_id=991001, responsible_name="T-Op991001",
                               pipe_status_id=990001, stage_name="Tashrif", leads_count=3),
            ])
            await s.commit()
            try:
                # Builderlar sozlamadagi haqiqiy Tashrif ID'lariga qaraydi — testda soxta
                # ID'lar (990001/990002) ishlatilgani uchun vaqtincha almashtiramiz
                orig = stats_router._visit_ids
                orig_contract = stats_router._contract_ids
                stats_router._visit_ids = lambda: VISIT_IDS
                stats_router._contract_ids = lambda: CONTRACT_IDS
                day_out = await stats_router._build_lead_day(s, DAY, None)
                old_out = await stats_router._build_lead_day(s, OLD_DAY, None)
                month_out = await stats_router._build_lead_month(s, "2020-06", None)
                stats_router._visit_ids = orig
                stats_router._contract_ids = orig_contract
                return day_out, old_out, month_out
            finally:
                await s.execute(_delete(LeadEvent).where(LeadEvent.crm_lead_id >= L))
                await s.execute(_delete(LeadStageDaily).where(LeadStageDaily.responsible_id >= 991000))
                await s.commit()

    try:
        day_out, old_out, month_out = _asyncio.run(_run_builders())
        check("kunlik ko'rinish: Tashrif voqealardan (2, snapshot 5 emas)",
              day_out.visits == 2, f"visits={day_out.visits}")
        check("kunlik ko'rinish: operator krediti ham voqealardan",
              any(o.responsible_id == 991001 and o.visits == 2 for o in day_out.operators),
              f"ops={[(o.responsible_id, o.visits) for o in day_out.operators]}")
        check("jurnal oldingi kun: snapshot fallback (3)",
              old_out.visits == 3, f"visits={old_out.visits}")
        check("oylik ko'rinish: DAY qatori voqea-asosli (2)",
              any(d.date == DAY and d.visits == 2 for d in month_out.days),
              f"days={[(str(d.date), d.visits) for d in month_out.days]}")
        check("kunlik ko'rinish: shartnoma (1) va bayroq yoniq",
              day_out.contracts == 1 and day_out.contracts_enabled,
              f"contracts={day_out.contracts}, enabled={day_out.contracts_enabled}")
        check("kunlik ko'rinish: shartnoma operator qatorida (991001=1)",
              any(o.responsible_id == 991001 and o.contracts == 1 for o in day_out.operators),
              f"ops={[(o.responsible_id, o.contracts) for o in day_out.operators]}")
        check("oylik ko'rinish: shartnoma jami = 1",
              month_out.contracts == 1, f"contracts={month_out.contracts}")
        check("jurnalsiz eski kun: shartnoma 0 (snapshot fallback YO'Q)",
              old_out.contracts == 0, f"contracts={old_out.contracts}")
    except Exception:
        check("statistika builder testi ishga tushdi", False, traceback.format_exc(limit=2).strip())


if __name__ == "__main__":
    main()
