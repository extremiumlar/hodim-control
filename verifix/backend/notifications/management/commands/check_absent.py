"""Cron orqali chaqiriladigan command: kelmagan hodimlarni xabar qiladi.

Misol: `python manage.py check_absent --threshold 09:30`
"""
from datetime import time
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from attendance.models import Attendance
from notifications.telegram import notify_absent


class Command(BaseCommand):
    help = "Hozirgacha check-in qilmagan hodimlarni Telegramga xabar qiladi."

    def add_arguments(self, parser):
        parser.add_argument("--threshold", type=str, default="09:30",
                            help="Soat HH:MM, bu vaqtdan keyin tekshiriladi.")

    def handle(self, *args, **options):
        threshold = options["threshold"]
        now = timezone.localtime()
        h, m = map(int, threshold.split(":"))
        if now.time() < time(h, m):
            self.stdout.write(f"Hali {threshold} bo'lmagan, hech narsa qilinmadi.")
            return
        today = timezone.localdate()
        absent = User.objects.filter(is_active=True, is_on_leave=False).exclude(
            attendances__date=today, attendances__check_in_time__isnull=False,
        )
        count = 0
        for u in absent:
            if today.isoweekday() not in u.work_day_set():
                continue  # bu hodim uchun dam olish kuni
            notify_absent(u, threshold)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} ta hodim haqida xabar yuborildi."))
