"""Davomat hisob-kitob yordamchilari sinovi."""
from datetime import datetime, time, timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Shift, User
from leave.models import LeaveRequest
from .models import Attendance
from .services import CheckInError, CheckInPayload, perform_check_in
from .utils import compute_early_minutes, compute_late_minutes, compute_worked_minutes


def _local_dt(y, m, d, hh, mm):
    return timezone.make_aware(datetime(y, m, d, hh, mm), timezone.get_current_timezone())


class WorkedMinutesTests(TestCase):
    """worked_minutes smenadagi tanaffusni (tushlik) ayirishi."""

    def setUp(self):
        self.shift = Shift.objects.create(
            name="Kunduzgi", start_time=time(9, 0), end_time=time(18, 0),
            break_start=time(13, 0), break_end=time(14, 0),
        )
        self.no_break_shift = Shift.objects.create(
            name="Tanaffussiz", start_time=time(9, 0), end_time=time(18, 0),
        )

    def test_full_day_minus_break(self):
        # 09:00-18:00, tanaffus 13:00-14:00 -> 8 soat
        got = compute_worked_minutes(
            _local_dt(2026, 6, 10, 9, 0), _local_dt(2026, 6, 10, 18, 0), self.shift
        )
        self.assertEqual(got, 480)

    def test_partial_break_overlap(self):
        # 09:00-13:30 -> tanaffusning 30 daqiqasi ayiriladi = 240
        got = compute_worked_minutes(
            _local_dt(2026, 6, 10, 9, 0), _local_dt(2026, 6, 10, 13, 30), self.shift
        )
        self.assertEqual(got, 240)

    def test_no_break_shift_keeps_raw_span(self):
        got = compute_worked_minutes(
            _local_dt(2026, 6, 10, 9, 0), _local_dt(2026, 6, 10, 18, 0), self.no_break_shift
        )
        self.assertEqual(got, 540)

    def test_no_shift_keeps_raw_span(self):
        got = compute_worked_minutes(
            _local_dt(2026, 6, 10, 9, 0), _local_dt(2026, 6, 10, 18, 0)
        )
        self.assertEqual(got, 540)

    def test_recalculate_uses_shift_break(self):
        user = User.objects.create_user(username="t_break", password="x", shift=self.shift)
        att = Attendance.objects.create(
            user=user, date=timezone.localdate(),
            check_in_time=_local_dt(2026, 6, 10, 9, 0),
            check_out_time=_local_dt(2026, 6, 10, 18, 0),
        )
        self.assertEqual(att.worked_minutes, 480)


class RecalcOnSaveTests(TestCase):
    """save() faqat check_in/check_out o'zgarganda qayta hisoblashi — smena
    keyin o'zgarsa tarixiy yozuvlar buzilmasligi."""

    def setUp(self):
        self.shift = Shift.objects.create(
            name="Kunduzgi", start_time=time(9, 0), end_time=time(18, 0),
        )
        self.user = User.objects.create_user(username="t_recalc", password="x", shift=self.shift)
        self.att = Attendance.objects.create(
            user=self.user, date=timezone.localdate(),
            check_in_time=_local_dt(2026, 6, 10, 9, 30),  # 25 daq kechikish (grace=5)
            check_out_time=_local_dt(2026, 6, 10, 18, 0),
        )

    def test_note_edit_keeps_history_after_shift_change(self):
        self.assertEqual(self.att.late_minutes, 25)
        # Smena keyinchalik o'zgartirildi — tarixiy yozuv o'zgarmasligi kerak
        self.shift.start_time = time(8, 0)
        self.shift.save()
        self.att.refresh_from_db()
        self.att.note = "tahrir"
        self.att.save()
        self.att.refresh_from_db()
        self.assertEqual(self.att.late_minutes, 25)  # 85 ga oshib ketmadi

    def test_time_change_still_recalculates(self):
        self.att.check_in_time = _local_dt(2026, 6, 10, 10, 0)
        self.att.save()
        self.att.refresh_from_db()
        self.assertEqual(self.att.late_minutes, 55)

    def test_forced_recalc(self):
        self.shift.start_time = time(8, 0)
        self.shift.save()
        self.att.refresh_from_db()
        self.att.user.refresh_from_db()
        self.att.save(recalc=True)
        self.att.refresh_from_db()
        self.assertEqual(self.att.late_minutes, 85)


class AutoCheckoutTests(TestCase):
    """auto_checkout buyrug'i: unutilgan check-out'lar smena oxiri bilan yopiladi."""

    def setUp(self):
        self.shift = Shift.objects.create(
            name="Kunduzgi", start_time=time(9, 0), end_time=time(18, 0),
            break_start=time(13, 0), break_end=time(14, 0),
        )
        self.day = timezone.localdate() - timedelta(days=1)

    def _att(self, username, shift):
        user = User.objects.create_user(username=username, password="x", shift=shift)
        return Attendance.objects.create(
            user=user, date=self.day,
            check_in_time=timezone.make_aware(
                datetime.combine(self.day, time(9, 0)), timezone.get_current_timezone()
            ),
        )

    def test_sets_shift_end_and_recalculates(self):
        att = self._att("t_auto1", self.shift)
        call_command("auto_checkout", date=str(self.day))
        att.refresh_from_db()
        self.assertIsNotNone(att.check_out_time)
        self.assertEqual(timezone.localtime(att.check_out_time).time(), time(18, 0))
        self.assertEqual(att.worked_minutes, 480)  # tanaffus ham ayirilgan
        self.assertIn("avto check-out", att.note)

    def test_user_without_shift_skipped(self):
        att = self._att("t_auto2", None)
        call_command("auto_checkout", date=str(self.day))
        att.refresh_from_db()
        self.assertIsNone(att.check_out_time)

    def test_already_checked_out_untouched(self):
        att = self._att("t_auto3", self.shift)
        original_out = timezone.make_aware(
            datetime.combine(self.day, time(17, 0)), timezone.get_current_timezone()
        )
        att.check_out_time = original_out
        att.save()
        call_command("auto_checkout", date=str(self.day))
        att.refresh_from_db()
        self.assertEqual(att.check_out_time, original_out)


class NightShiftTests(TestCase):
    """Tungi (yarim tundan oshuvchi) smenada kechikish/erta ketish hisobi."""

    def test_day_shift_unchanged(self):
        # 09:00-18:00: 09:15 kelish, grace=5 -> 10 daq (eski xatti-harakat)
        got = compute_late_minutes(
            _local_dt(2026, 6, 10, 9, 15), time(9, 0), 5, shift_end=time(18, 0)
        )
        self.assertEqual(got, 10)

    def test_night_shift_late_before_midnight(self):
        # 22:00-06:00: 22:10 kelish (grace'siz) -> 10 daq kechikish
        got = compute_late_minutes(
            _local_dt(2026, 6, 10, 22, 10), time(22, 0), 0, shift_end=time(6, 0)
        )
        self.assertEqual(got, 10)

    def test_night_shift_late_after_midnight(self):
        # 00:30 da kelish — smena kecha 22:00 da boshlangan -> 150 daq
        got = compute_late_minutes(
            _local_dt(2026, 6, 11, 0, 30), time(22, 0), 0, shift_end=time(6, 0)
        )
        self.assertEqual(got, 150)

    def test_night_shift_early_leave_before_midnight(self):
        # 23:00 da ketish — tugash ertaga 06:00 -> 420 daq erta
        got = compute_early_minutes(
            _local_dt(2026, 6, 10, 23, 0), time(6, 0), shift_start=time(22, 0)
        )
        self.assertEqual(got, 420)

    def test_night_shift_early_leave_after_midnight(self):
        # 05:00 da ketish — tugash bugun 06:00 -> 60 daq erta
        got = compute_early_minutes(
            _local_dt(2026, 6, 11, 5, 0), time(6, 0), shift_start=time(22, 0)
        )
        self.assertEqual(got, 60)


class LeaveGateTests(TestCase):
    """Check-in ta'til tekshiruvi SANAGA (LeaveRequest oralig'i) tayanishi —
    is_on_leave bayrog'i emas."""

    def setUp(self):
        self.user = User.objects.create_user(username="t_leave_gate", password="x")
        self.payload = CheckInPayload(latitude=0.0, longitude=0.0)

    def test_active_leave_blocks_check_in(self):
        today = timezone.localdate()
        LeaveRequest.objects.create(
            user=self.user, status=LeaveRequest.Status.APPROVED,
            start_date=today - timedelta(days=1), end_date=today + timedelta(days=1),
        )
        with self.assertRaisesMessage(CheckInError, "ta'tildasiz"):
            perform_check_in(self.user, self.payload)

    def test_expired_leave_does_not_block(self):
        # Kecha tugagan ta'til + unutilgan is_on_leave=True — check-in ta'til
        # to'sig'idan o'tadi (keyingi xato smena yo'qligi haqida bo'ladi).
        today = timezone.localdate()
        LeaveRequest.objects.create(
            user=self.user, status=LeaveRequest.Status.APPROVED,
            start_date=today - timedelta(days=10), end_date=today - timedelta(days=1),
        )
        self.user.is_on_leave = True
        self.user.save(update_fields=["is_on_leave"])
        with self.assertRaisesMessage(CheckInError, "smena biriktirilmagan"):
            perform_check_in(self.user, self.payload)

    def test_pending_leave_does_not_block(self):
        today = timezone.localdate()
        LeaveRequest.objects.create(
            user=self.user, status=LeaveRequest.Status.PENDING,
            start_date=today, end_date=today,
        )
        with self.assertRaisesMessage(CheckInError, "smena biriktirilmagan"):
            perform_check_in(self.user, self.payload)
