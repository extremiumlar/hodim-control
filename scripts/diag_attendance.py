"""Jonli baza forensikasi — davomat ma'lumotidagi anomaliyalarni topish."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DB = "D:/Project/hodimlar_tizimi/app.db"
TZ = ZoneInfo("Asia/Tashkent")
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=" * 70)
print("1. DAVOMAT YOZUVLARI (to'liq)")
print("=" * 70)
rows = c.execute("""
    select a.*, u.full_name, u.role
    from attendance a join users u on u.id = a.user_id
    order by a.date
""").fetchall()
for r in rows:
    cin = r["check_in_time"]
    cout = r["check_out_time"]
    # UTC -> Toshkent
    def loc(v):
        if not v:
            return "—"
        dt = datetime.fromisoformat(v.split(".")[0]).replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ).strftime("%H:%M")
    print(f"  {r['date']} | {r['full_name']:12} ({r['role']:9}) | "
          f"kel={loc(cin)} ket={loc(cout)} | late={r['late_minutes']:4} "
          f"erta={r['early_leave_minutes']:4} ishl={r['worked_minutes']:4} | "
          f"status={r['status']} weekend={r['is_weekend']} dist={r['check_in_distance_m']}")

print()
print("=" * 70)
print("2. ANOMALIYALAR")
print("=" * 70)

# A. Check-out yo'q yozuvlar (ochiq qolgan kunlar)
open_days = c.execute("""
    select a.date, u.full_name from attendance a join users u on u.id=a.user_id
    where a.check_in_time is not null and a.check_out_time is null
""").fetchall()
print(f"A. Ochiq qolgan kunlar (Ketdim bosilmagan): {len(open_days)}")
for r in open_days:
    print(f"     {r['date']} — {r['full_name']}")

# B. worked_minutes = 0 lekin check-out bor
weird = c.execute("""
    select a.date, u.full_name, a.worked_minutes from attendance a join users u on u.id=a.user_id
    where a.check_out_time is not null and a.worked_minutes = 0
""").fetchall()
print(f"B. check-out bor, lekin ishlangan vaqt 0: {len(weird)}")
for r in weird:
    print(f"     {r['date']} — {r['full_name']}")

# C. Juda katta kechikish (ish oynasidan oshgan)
huge = c.execute("select a.date,u.full_name,a.late_minutes from attendance a join users u on u.id=a.user_id where a.late_minutes > 240").fetchall()
print(f"C. 4 soatdan ko'p kechikish (shubhali): {len(huge)}")
for r in huge:
    print(f"     {r['date']} — {r['full_name']}: {r['late_minutes']} daq ({r['late_minutes']//60}s {r['late_minutes']%60}d)")

# D. Juda katta erta ketish
huge_e = c.execute("select a.date,u.full_name,a.early_leave_minutes from attendance a join users u on u.id=a.user_id where a.early_leave_minutes > 240").fetchall()
print(f"D. 4 soatdan ko'p erta ketish: {len(huge_e)}")
for r in huge_e:
    print(f"     {r['date']} — {r['full_name']}: {r['early_leave_minutes']} daq")

# E. GPS masofa
dist = c.execute("select a.date,u.full_name,a.check_in_distance_m from attendance a join users u on u.id=a.user_id where a.check_in_distance_m is not null order by a.check_in_distance_m desc").fetchall()
print(f"E. GPS masofalari (eng uzoq 5 ta):")
for r in dist[:5]:
    print(f"     {r['full_name']}: {r['check_in_distance_m']} m")

print()
print("=" * 70)
print("3. ISH JADVALI HOLATI")
print("=" * 70)
tracked = c.execute("select id, full_name, role from users where is_active=1 and role != 'boss'").fetchall()
for u in tracked:
    wk = c.execute("select count(*) from work_schedule_weekly where user_id=?", (u["id"],)).fetchone()[0]
    ov = c.execute("select count(*) from work_schedule_override where user_id=?", (u["id"],)).fetchone()[0]
    mark = "  " if wk else "⚠️"
    print(f"  {mark} {u['full_name']:12} ({u['role']:9}): weekly={wk} override={ov}"
          + ("  ← DEFAULT ishlatiladi (Du-Ju 09:00-18:00)" if not wk else ""))

print()
print("=" * 70)
print("4. FACE DESCRIPTOR SIFATI")
print("=" * 70)
faces = c.execute("select id, full_name, face_descriptor, face_registered_at from users where face_descriptor is not null").fetchall()
descs = {}
for u in faces:
    try:
        d = json.loads(u["face_descriptor"])
        n = len(d)
        has_nan = any(x != x or x in (float("inf"), float("-inf")) for x in d)
        norm = sum(x * x for x in d) ** 0.5
        descs[u["full_name"]] = d
        print(f"  {u['full_name']:12}: {n} o'lcham, norma={norm:.3f}, NaN/Inf={has_nan}, "
              f"ro'yxat={u['face_registered_at'][:16] if u['face_registered_at'] else 'NULL'}")
    except Exception as e:
        print(f"  {u['full_name']:12}: BUZUQ JSON — {e}")

# Deskriptorlar orasidagi masofa (bir xil odam ikki hisobda emasmi?)
import itertools
print("  Deskriptorlar orasidagi o'xshashlik (1.0 = bir xil odam!):")
for (n1, d1), (n2, d2) in itertools.combinations(descs.items(), 2):
    if len(d1) == len(d2):
        dist = sum((a - b) ** 2 for a, b in zip(d1, d2)) ** 0.5
        sim = max(0.0, 1.0 - dist)
        flag = "  ⚠️ CHEGARADAN YUQORI (0.5)" if sim >= 0.5 else ""
        print(f"     {n1} ↔ {n2}: {sim:.3f}{flag}")

print()
print("=" * 70)
print("5. SXEMA vs MODEL (drift)")
print("=" * 70)
for tbl in ("attendance", "office_locations", "attendance_digest_config"):
    cols = [(r[1], r[2], r[3]) for r in c.execute(f"PRAGMA table_info({tbl})")]
    print(f"  {tbl}: {len(cols)} ustun")
    idx = [r[1] for r in c.execute(f"PRAGMA index_list({tbl})")]
    print(f"     indekslar: {idx}")

print()
print("=" * 70)
print("6. DIGEST SOZLAMASI")
print("=" * 70)
cfg = c.execute("select * from attendance_digest_config").fetchall()
if not cfg:
    print("  ⚠️ Sozlama qatori YO'Q (birinchi tick'da yaratiladi)")
for r in cfg:
    print(f"  ertalab {r['morning_hour']:02d}:{r['morning_minute']:02d} "
          f"(yoqiq={bool(r['morning_enabled'])}, oxirgi={r['morning_last_posted']})")
    print(f"  kechqurun {r['evening_hour']:02d}:{r['evening_minute']:02d} "
          f"(yoqiq={bool(r['evening_enabled'])}, oxirgi={r['evening_last_posted']})")

print()
print("=" * 70)
print("7. OFISLAR")
print("=" * 70)
for r in c.execute("select * from office_locations"):
    print(f"  {r['name']:20} ({r['latitude']}, {r['longitude']}) r={r['radius_meters']}m faol={bool(r['is_active'])}")
# Ofislar bir-biriga yaqinmi (3.2 bugi uchun)?
offs = c.execute("select name, latitude, longitude, radius_meters from office_locations where is_active=1").fetchall()
import math
def hav(a, b, c_, d):
    R = 6371000
    p1, p2 = math.radians(a), math.radians(c_)
    dp, dl = math.radians(c_ - a), math.radians(d - b)
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(x), math.sqrt(1-x))
print("  Ofislar orasidagi masofa:")
for o1, o2 in itertools.combinations(offs, 2):
    d = hav(o1["latitude"], o1["longitude"], o2["latitude"], o2["longitude"])
    overlap = d < (o1["radius_meters"] + o2["radius_meters"])
    print(f"     {o1['name']} ↔ {o2['name']}: {d/1000:.1f} km" + ("  ⚠️ RADIUSLAR KESISHADI" if overlap else ""))

c.close()
