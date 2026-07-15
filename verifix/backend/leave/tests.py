"""Ta'til so'rovlari sinovi — approve'da is_on_leave bayrog'i mantiqiy qo'yilishi."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from .models import LeaveRequest


class ApproveFlagTests(TestCase):
    """approve: bayroq faqat hali tugamagan ta'tilda qo'yiladi — o'tmishdagi
    ta'tilni tasdiqlash xodimni "abadiy ta'tilda" qilib qo'ymaydi."""

    def setUp(self):
        self.hr = User.objects.create_user(username="t_hr", password="x", role=User.Role.HR)
        self.employee = User.objects.create_user(username="t_emp", password="x")
        self.client.force_login(self.hr)

    def _approve(self, start, end) -> None:
        leave = LeaveRequest.objects.create(user=self.employee, start_date=start, end_date=end)
        resp = self.client.post(f"/api/leave/{leave.id}/approve/")
        self.assertEqual(resp.status_code, 200)
        leave.refresh_from_db()
        self.assertEqual(leave.status, LeaveRequest.Status.APPROVED)
        self.employee.refresh_from_db()

    def test_current_leave_sets_flag(self):
        today = timezone.localdate()
        self._approve(today, today + timedelta(days=3))
        self.assertTrue(self.employee.is_on_leave)

    def test_past_leave_does_not_set_flag(self):
        today = timezone.localdate()
        self._approve(today - timedelta(days=10), today - timedelta(days=5))
        self.assertFalse(self.employee.is_on_leave)

    def test_reject_does_not_set_flag(self):
        today = timezone.localdate()
        leave = LeaveRequest.objects.create(
            user=self.employee, start_date=today, end_date=today + timedelta(days=3),
        )
        resp = self.client.post(f"/api/leave/{leave.id}/reject/")
        self.assertEqual(resp.status_code, 200)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_on_leave)
