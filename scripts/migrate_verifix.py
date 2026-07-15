"""verifix (hodim_crm Django) bazasidan yagona backendga bir martalik ko'chirish.

Ko'chiriladi:
  - office_locations  (verifix accounts_officelocation -> app office_locations)
  - users.face_descriptor / face_registered_at  (faqat USER_MAP dagi mosliklarga,
    maqsad foydalanuvchida yuz hali YO'Q bo'lsa)
  - attendance tarixi (faqat USER_MAP dagi foydalanuvchilar; bir kunga bitta,
    mavjud bo'lsa o'tkazib yuboriladi)

Idempotent: qayta ishga tushirilsa dublikat yaratmaydi (nom/sana bo'yicha tekshiradi).

Ishlatish (loyiha ildizidan):
  .venv/Scripts/python.exe scripts/migrate_verifix.py            # dry-run (faqat hisobot)
  .venv/Scripts/python.exe scripts/migrate_verifix.py --apply    # haqiqiy yozish
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIX_DB = ROOT / "verifix" / "backend" / "db.sqlite3"
APP_DB = ROOT / "app.db"

# verifix accounts_user.id -> app users.id
# (username/ism bo'yicha qo'lda tasdiqlangan mosliklar; test userlar kiritilmagan)
USER_MAP = {
    1: 1,  # admin (Bosh Admin)  -> Boss
    3: 7,  # n                   -> Nurullo IT (dasturchi)
    5: 9,  # kamola              -> Kamola (rop)
}
# Ataylab ko'chirilmaydi: 2 (hodim/test), 4 (testhodim/test)


def main() -> None:
    apply = "--apply" in sys.argv
    mode = "APPLY (yoziladi)" if apply else "DRY-RUN (faqat hisobot, --apply bilan yozing)"
    print(f"Rejim: {mode}")
    if not VERIFIX_DB.exists():
        sys.exit(f"verifix bazasi topilmadi: {VERIFIX_DB}")

    src = sqlite3.connect(VERIFIX_DB)
    dst = sqlite3.connect(APP_DB)

    # 1) Ofislar (nom bo'yicha idempotent)
    print("\n--- Ofislar ---")
    for oid, name, lat, lng, radius, active in src.execute(
        "select id, name, latitude, longitude, radius_meters, is_active from accounts_officelocation"
    ):
        exists = dst.execute("select id from office_locations where name=?", (name,)).fetchone()
        if exists:
            print(f"  o'tkazildi (bor): {name}")
            continue
        print(f"  qo'shiladi: {name} ({lat}, {lng}, r={radius}m, faol={bool(active)})")
        if apply:
            dst.execute(
                "insert into office_locations (name, latitude, longitude, radius_meters, is_active, created_at)"
                " values (?, ?, ?, ?, ?, datetime('now'))",
                (name, lat, lng, radius, active),
            )

    # 2) Yuz deskriptorlari (USER_MAP bo'yicha, maqsadda yuz yo'q bo'lsa)
    print("\n--- Yuz (Face ID) ---")
    for src_id, dst_id in USER_MAP.items():
        row = src.execute(
            "select username, face_descriptor, face_registered_at from accounts_user where id=?",
            (src_id,),
        ).fetchone()
        if not row:
            print(f"  verifix user {src_id} topilmadi — o'tkazildi")
            continue
        username, desc, reg_at = row
        target = dst.execute(
            "select full_name, face_descriptor from users where id=?", (dst_id,)
        ).fetchone()
        if not target:
            print(f"  app user {dst_id} topilmadi — o'tkazildi ({username})")
            continue
        full_name, existing = target
        if not desc:
            print(f"  {username}: yuz yo'q — o'tkazildi")
            continue
        if existing:
            print(f"  {username} -> {full_name}: maqsadda yuz allaqachon bor — o'tkazildi")
            continue
        print(f"  {username} -> {full_name}: yuz ko'chiriladi ({len(desc)} belgi)")
        if apply:
            dst.execute(
                "update users set face_descriptor=?, face_registered_at=? where id=?",
                (desc, reg_at, dst_id),
            )

    # 3) Davomat tarixi (USER_MAP bo'yicha; user+sana bor bo'lsa o'tkazadi)
    print("\n--- Davomat tarixi ---")
    copied = skipped = unmapped = 0
    for r in src.execute(
        "select user_id, date, check_in_time, check_in_lat, check_in_lng, check_in_distance_m,"
        " check_out_time, check_out_lat, check_out_lng, late_minutes, early_leave_minutes,"
        " worked_minutes, status, is_weekend, note, created_at, updated_at"
        " from attendance_attendance"
    ):
        src_uid, date = r[0], r[1]
        dst_uid = USER_MAP.get(src_uid)
        if dst_uid is None:
            unmapped += 1
            continue
        exists = dst.execute(
            "select id from attendance where user_id=? and date=?", (dst_uid, date)
        ).fetchone()
        if exists:
            skipped += 1
            continue
        copied += 1
        print(f"  ko'chiriladi: user {src_uid}->{dst_uid}, {date} ({r[12]})")
        if apply:
            dst.execute(
                "insert into attendance (user_id, date, check_in_time, check_in_lat, check_in_lng,"
                " check_in_distance_m, check_out_time, check_out_lat, check_out_lng, late_minutes,"
                " early_leave_minutes, worked_minutes, status, is_weekend, note, created_at, updated_at)"
                " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, coalesce(?, datetime('now')), coalesce(?, datetime('now')))",
                (dst_uid, *r[1:]),
            )
    print(f"  jami: ko'chiriladi={copied}, bor edi={skipped}, moslanmagan={unmapped}")

    if apply:
        dst.commit()
        print("\nYOZILDI.")
    else:
        print("\nDRY-RUN tugadi — hech narsa yozilmadi. Qo'llash: --apply")
    src.close()
    dst.close()


if __name__ == "__main__":
    main()
