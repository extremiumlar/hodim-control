"""Oylik hisobida tasdiqlangan ta'til kunlari sinovi."""
from datetime import date, datetime, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Shift, User
from attendance.models import Attendance
from leave.models import LeaveRequest
from .services import compute_payroll


def _aware(d: date, t: time) -> datetime:
    return timezone.make_aware(datetime.combine(d, t), timezone.get_current_timezone())


class LeavePayrollTests(TestCase):
    """Tasdiqlangan ta'til (vacation/sick/other) kunlari oylikdan ayirilmasligi,
    to'lovsiz (unpaid) esa kelmagan kun kabi ayirilishi."""

    PERIOD = "2026-06"  # iyun 2026: 22 ish kuni (Du-Ju)

    def setUp(self):
        self.user = User.objects.create_user(
            username="t_leave", password="x", base_salary=Decimal("2200000"),
        )

    def _leave(self, leave_type: str, status: str = LeaveRequest.Status.APPROVED):
        # 2026-06-10 (chorshanba) — 2026-06-12 (juma): 3 ish kuni
        return LeaveRequest.objects.create(
            user=self.user, type=leave_type, status=status,
            start_date=date(2026, 6, 10), end_date=date(2026, 6, 12),
        )

    def test_approved_vacation_not_deducted(self):
        base_absent = compute_payroll(self.user, self.PERIOD).absent_days
        self._leave(LeaveRequest.Type.VACATION)
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.absent_days, base_absent - 3)

    def test_approved_vacation_increases_total(self):
        total_before = compute_payroll(self.user, self.PERIOD).total
        self._leave(LeaveRequest.Type.VACATION)
        total_after = compute_payroll(self.user, self.PERIOD).total
        self.assertGreater(total_after, total_before)

    def test_unpaid_leave_still_deducted(self):
        base_absent = compute_payroll(self.user, self.PERIOD).absent_days
        self._leave(LeaveRequest.Type.UNPAID)
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.absent_days, base_absent)

    def test_pending_leave_not_excused(self):
        base_absent = compute_payroll(self.user, self.PERIOD).absent_days
        self._leave(LeaveRequest.Type.VACATION, status=LeaveRequest.Status.PENDING)
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.absent_days, base_absent)

    def test_weekend_overlap_not_counted(self):
        # 2026-06-13 (shanba) — 2026-06-14 (yakshanba): ish kuni emas, uzr ham emas
        base_absent = compute_payroll(self.user, self.PERIOD).absent_days
        LeaveRequest.objects.create(
            user=self.user, type=LeaveRequest.Type.VACATION,
            status=LeaveRequest.Status.APPROVED,
            start_date=date(2026, 6, 13), end_date=date(2026, 6, 14),
        )
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.absent_days, base_absent)


class AttendancePayrollTests(TestCase):
    """Davomat yozuvlari asosidagi oylik komponentlari."""

    PERIOD = "2026-06"

    def setUp(self):
        self.user = User.objects.create_user(
            username="t_pay", password="x", base_salary=Decimal("2200000"),
        )

    def _present(self, d: date):
        Attendance.objects.create(
            user=self.user, date=d,
            check_in_time=_aware(d, time(9, 0)),
            check_out_time=_aware(d, time(18, 0)),
        )

    def test_present_day_reduces_absent(self):
        base_absent = compute_payroll(self.user, self.PERIOD).absent_days
        self._present(date(2026, 6, 10))  # chorshanba
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.absent_days, base_absent - 1)

    def test_weekend_work_adds_extra(self):
        total_before = compute_payroll(self.user, self.PERIOD).total
        self._present(date(2026, 6, 14))  # yakshanba — dam olish kuni
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.weekend_days, 1)
        self.assertGreater(payroll.total, total_before)
        # weekend_extra = kunlik_stavka * 150%
        per_day = payroll.base_salary / payroll.work_days_total
        self.assertAlmostEqual(
            float(payroll.weekend_extra), float(per_day * Decimal("1.5")), places=0
        )

    def test_late_minutes_penalized(self):
        self.user.late_penalty_per_minute = Decimal("1000")
        self.user.shift = Shift.objects.create(
            name="Grace'siz", start_time=time(9, 0), end_time=time(18, 0), grace_minutes=0,
        )
        self.user.save()
        d = date(2026, 6, 10)
        Attendance.objects.create(
            user=self.user, date=d,
            check_in_time=_aware(d, time(9, 10)),  # 10 daq kechikish
            check_out_time=_aware(d, time(18, 0)),
        )
        payroll = compute_payroll(self.user, self.PERIOD)
        self.assertEqual(payroll.late_minutes, 10)
        self.assertEqual(payroll.late_penalty_total, Decimal("10000.00"))
