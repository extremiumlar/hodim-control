"""Cron orqali chaqiriladigan command: "Ketdim"ni unutgan hodimlarni yopadi.

Kecha (yoki --date bilan berilgan sana) check-in bor, lekin check-out YO'Q
davomat yozuvlariga check_out_time sifatida hodim smenasining tugash vaqti
qo'yiladi (save() ichida worked/early avtomatik qayta hisoblanadi). Smenasiz
hodimlar o'tkazib yuboriladi. Hech narsa o'zgarmasa 0 chiqaradi.

Misol: `python manage.py auto_checkout` yoki `--date 2026-06-10`
"""
from datetime import date as date_cls, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.models import Attendance


class Command(BaseCommand):
    help = "Check-out qilinmagan davomatlarni smena oxiri bilan avtomatik yopadi."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None,
                            help="Sana (YYYY-MM-DD); berilmasa kecha olinadi.")

    def handle(self, *args, **options):
        target = (date_cls.fromisoformat(options["date"]) if options["date"]
                  else timezone.localdate() - timedelta(days=1))

        qs = Attendance.objects.filter(
            date=target, check_in_time__isnull=False, check_out_time__isnull=True,
        ).select_related("user", "user__shift")

        count = 0
        for att in qs:
            shift = att.user.shift
            if shift is None:
                continue  # smenasiz — qachon ketishi noma'lum, tegmaymiz
            end_date = att.date
            if shift.end_time < shift.start_time:
                end_date += timedelta(days=1)  # tungi smena keyingi kunda tugaydi
            att.check_out_time = timezone.make_aware(
                datetime.combine(end_date, shift.end_time),
                timezone.get_current_timezone(),
            )
            att.note = (att.note + "\n" if att.note else "") + "avto check-out"
            att.save()  # recalculate() worked/early ni hisoblaydi
            count += 1

        if count:
            self.stdout.write(self.style.SUCCESS(f"{count} ta davomat avto yopildi ({target})."))
        else:
            self.stdout.write(f"0 - {target} uchun yopilmagan davomat topilmadi.")
