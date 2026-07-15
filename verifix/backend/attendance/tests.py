"""Davomat hisob-kitob yordamchilari sinovi."""
from datetime import datetime, time, timedelta

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
