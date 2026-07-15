"""Oylik hisobida tasdiqlangan ta'til kunlari sinovi."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from leave.models import LeaveRequest
from .services import compute_payroll


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
