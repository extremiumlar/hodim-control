from datetime import timedelta
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsHRRole
from .models import Attendance
from .serializers import AttendanceSerializer, CheckInRequestSerializer
from .services import perform_check_in, perform_check_out, CheckInError, CheckInPayload


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Attendance.objects.select_related("user", "user__department").all()
    serializer_class = AttendanceSerializer
    filterset_fields = ["user", "date", "status", "is_weekend"]
    ordering_fields = ["date", "check_in_time"]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if not u.is_hr_role:
            qs = qs.filter(user=u)
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        ser = CheckInRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            att = perform_check_in(
                request.user,
                CheckInPayload(
                    latitude=ser.validated_data["latitude"],
                    longitude=ser.validated_data["longitude"],
                    face_descriptor=ser.validated_data.get("face_descriptor"),
                    liveness=float(ser.validated_data.get("liveness", 0) or 0),
                ),
            )
        except CheckInError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        # Notify on late
        if att.late_minutes > 0:
            from notifications.telegram import notify_late_check_in
            notify_late_check_in(att)
        return Response(AttendanceSerializer(att).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="check-out")
    def check_out(self, request):
        ser = CheckInRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            att = perform_check_out(
                request.user,
                CheckInPayload(
                    latitude=ser.validated_data["latitude"],
                    longitude=ser.validated_data["longitude"],
                    face_descriptor=ser.validated_data.get("face_descriptor"),
                    liveness=float(ser.validated_data.get("liveness", 0) or 0),
                ),
            )
        except CheckInError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if att.early_leave_minutes > 0:
            from notifications.telegram import notify_early_leave
            notify_early_leave(att)
        return Response(AttendanceSerializer(att).data)

    @action(detail=False, methods=["get"], url_path="today")
    def today(self, request):
        """Bugungi davomat (foydalanuvchi uchun)."""
        today = timezone.localdate()
        att = Attendance.objects.filter(user=request.user, date=today).first()
        if not att:
            return Response({"detail": "Bugun hali check-in qilinmagan."}, status=204)
        return Response(AttendanceSerializer(att).data)

    @action(detail=False, methods=["get"], url_path="live",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def live(self, request):
        """Hozir ofisda kim borligi (admin uchun)."""
        today = timezone.localdate()
        present = Attendance.objects.filter(
            date=today,
            check_in_time__isnull=False,
            check_out_time__isnull=True,
        ).select_related("user")
        absent = User.objects.filter(
            is_active=True, is_on_leave=False
        ).exclude(
            attendances__date=today, attendances__check_in_time__isnull=False,
        ).values("id", "first_name", "last_name", "username")
        return Response({
            "in_office": AttendanceSerializer(present, many=True).data,
            "absent": list(absent),
            "on_leave": list(User.objects.filter(is_on_leave=True).values(
                "id", "first_name", "last_name", "username"
            )),
        })

    @action(detail=False, methods=["get"], url_path="stats",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def stats(self, request):
        """Haftalik / oylik statistika."""
        days = int(request.query_params.get("days", 30))
        since = timezone.localdate() - timedelta(days=days)

        qs = Attendance.objects.filter(date__gte=since)
        by_day = (
            qs.values("date")
              .annotate(
                  total=Count("id"),
                  late=Count("id", filter=Q(status="late")),
                  present=Count("id", filter=Q(status="present")),
                  absent=Count("id", filter=Q(status="absent")),
              )
              .order_by("date")
        )
        late_top = (
            qs.values("user__id", "user__first_name", "user__last_name", "user__username")
              .annotate(
                  late_count=Count("id", filter=Q(status="late")),
                  late_total_min=Sum("late_minutes"),
              )
              .order_by("-late_total_min")[:10]
        )
        worked_top = (
            qs.values("user__id", "user__first_name", "user__last_name", "user__username")
              .annotate(worked=Sum("worked_minutes"))
              .order_by("-worked")[:10]
        )
        return Response({
            "by_day": list(by_day),
            "late_top": list(late_top),
            "worked_top": list(worked_top),
        })

    @action(detail=False, methods=["get"], url_path="dashboard",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def dashboard(self, request):
        """Boshliq paneli uchun to'liq ma'lumot (bitta so'rovda)."""
        today = timezone.localdate()
        month_start = today.replace(day=1)

        active_users = User.objects.filter(is_active=True)
        total_employees = active_users.count()
        on_leave = active_users.filter(is_on_leave=True).count()

        today_qs = Attendance.objects.filter(date=today)
        present_now = today_qs.filter(
            check_in_time__isnull=False, check_out_time__isnull=True).count()
        checked_in_today = today_qs.filter(check_in_time__isnull=False).count()
        late_today = today_qs.filter(status="late").count()
        left_today = today_qs.filter(check_out_time__isnull=False).count()

        # Kelmaganlar (bugun, dam olish kunida bo'lmaganlar)
        not_checked_in = active_users.filter(is_on_leave=False).exclude(
            attendances__date=today, attendances__check_in_time__isnull=False,
        ).count()

        # Davomat foizi (oy boshidan): kutilgan = har hodimning o'z ish kunlari
        # (work_day_set) bo'yicha oy boshidan bugungacha bo'lgan ish kunlari
        # yig'indisi; haqiqiy = faqat ish kunidagi check-in'lar. Ilgari maxraj
        # kalendar kunlar (today.day), surat esa dam olish yozuvlarini ham
        # sanagani uchun foiz noto'g'ri chiqardi.
        month_qs = Attendance.objects.filter(date__gte=month_start, date__lte=today)
        month_present = month_qs.filter(check_in_time__isnull=False).count()
        month_late_min = month_qs.aggregate(s=Sum("late_minutes"))["s"] or 0
        month_worked_min = month_qs.aggregate(s=Sum("worked_minutes"))["s"] or 0

        month_days = [
            month_start + timedelta(days=i) for i in range((today - month_start).days + 1)
        ]
        expected_workdays = sum(
            sum(1 for d in month_days if d.isoweekday() in u.work_day_set())
            for u in active_users
        )
        actual_workday_checkins = month_qs.filter(
            is_weekend=False, check_in_time__isnull=False
        ).count()
        attendance_rate = (
            round(100 * actual_workday_checkins / expected_workdays, 1)
            if expected_workdays else 0
        )

        # So'nggi harakatlar (oxirgi 15 check-in/out)
        recent = (
            Attendance.objects.filter(date=today, check_in_time__isnull=False)
            .select_related("user", "user__department")
            .order_by("-check_in_time")[:15]
        )
        recent_data = [{
            "id": a.id,
            "user_name": a.user.get_full_name() or a.user.username,
            "department": a.user.department.name if a.user.department else "",
            "check_in_time": a.check_in_time,
            "check_out_time": a.check_out_time,
            "late_minutes": a.late_minutes,
            "status": a.status,
            "status_display": a.get_status_display(),
        } for a in recent]

        # Hozir ofisda
        in_office = (
            Attendance.objects.filter(
                date=today, check_in_time__isnull=False, check_out_time__isnull=True)
            .select_related("user", "user__department")
            .order_by("check_in_time")
        )
        in_office_data = [{
            "id": a.id,
            "user_name": a.user.get_full_name() or a.user.username,
            "department": a.user.department.name if a.user.department else "",
            "check_in_time": a.check_in_time,
            "late_minutes": a.late_minutes,
        } for a in in_office]

        return Response({
            "today": today.isoformat(),
            "summary": {
                "total_employees": total_employees,
                "present_now": present_now,
                "checked_in_today": checked_in_today,
                "late_today": late_today,
                "left_today": left_today,
                "not_checked_in": not_checked_in,
                "on_leave": on_leave,
                "attendance_rate": attendance_rate,
                "month_late_minutes": month_late_min,
                "month_worked_hours": round(month_worked_min / 60, 1),
            },
            "in_office": in_office_data,
            "recent": recent_data,
        })

    @action(detail=False, methods=["get"], url_path="employee-summary",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def employee_summary(self, request):
        """Har bir hodimning davr bo'yicha umumiy statistikasi (jadval uchun)."""
        days = int(request.query_params.get("days", 30))
        since = timezone.localdate() - timedelta(days=days)

        rows = (
            Attendance.objects.filter(date__gte=since)
            .values(
                "user__id", "user__first_name", "user__last_name",
                "user__username", "user__department__name",
            )
            .annotate(
                present_days=Count("id", filter=Q(check_in_time__isnull=False)),
                late_count=Count("id", filter=Q(status="late")),
                late_minutes=Sum("late_minutes"),
                early_minutes=Sum("early_leave_minutes"),
                worked_minutes=Sum("worked_minutes"),
            )
            .order_by("-late_minutes")
        )
        return Response(list(rows))
