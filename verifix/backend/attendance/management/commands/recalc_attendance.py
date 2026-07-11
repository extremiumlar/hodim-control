"""Hamma mavjud davomat yozuvlarini qayta hisoblaydi.

Ishlatish:
    python manage.py recalc_attendance              # hammasi
    python manage.py recalc_attendance --date 2026-05-27
    python manage.py recalc_attendance --user hodim
"""
from django.core.management.base import BaseCommand
from attendance.models import Attendance


class Command(BaseCommand):
    help = "Davomat yozuvlarining late/early/worked daqiqalarini qayta hisoblaydi."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="Faqat shu sana (YYYY-MM-DD)")
        parser.add_argument("--user", type=str, help="Faqat shu username")

    def handle(self, *args, **opts):
        qs = Attendance.objects.select_related("user", "user__shift")
        if opts.get("date"):
            qs = qs.filter(date=opts["date"])
        if opts.get("user"):
            qs = qs.filter(user__username=opts["user"])

        total = qs.count()
        self.stdout.write(f"{total} ta yozuv qayta hisoblanmoqda...")
        for att in qs:
            att.save()  # recalculate() chaqiriladi
        self.stdout.write(self.style.SUCCESS(f"✅ {total} ta yozuv yangilandi."))
