from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsHRRole
from .models import Bonus, Penalty, MonthlyPayroll
from .serializers import BonusSerializer, PenaltySerializer, MonthlyPayrollSerializer
from .services import compute_payroll, compute_payroll_for_all


class BonusViewSet(viewsets.ModelViewSet):
    queryset = Bonus.objects.select_related("user").all()
    serializer_class = BonusSerializer
    permission_classes = [permissions.IsAuthenticated, IsHRRole]
    filterset_fields = ["user", "period"]


class PenaltyViewSet(viewsets.ModelViewSet):
    queryset = Penalty.objects.select_related("user").all()
    serializer_class = PenaltySerializer
    permission_classes = [permissions.IsAuthenticated, IsHRRole]
    filterset_fields = ["user", "period"]


class MonthlyPayrollViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MonthlyPayroll.objects.select_related("user", "approved_by").all()
    serializer_class = MonthlyPayrollSerializer
    filterset_fields = ["user", "period", "is_approved"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_hr_role:
            qs = qs.filter(user=self.request.user)
        return qs

    @action(detail=False, methods=["post"], url_path="compute",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def compute(self, request):
        period = request.data.get("period") or timezone.localdate().strftime("%Y-%m")
        user_id = request.data.get("user")
        if user_id:
            user = User.objects.get(pk=user_id)
            p = compute_payroll(user, period)
            return Response(MonthlyPayrollSerializer(p).data)
        results = compute_payroll_for_all(period)
        return Response(MonthlyPayrollSerializer(results, many=True).data)

    @action(detail=True, methods=["post"], url_path="approve",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def approve(self, request, pk=None):
        p = self.get_object()
        p.is_approved = True
        p.approved_by = request.user
        p.save(update_fields=["is_approved", "approved_by"])
        return Response(MonthlyPayrollSerializer(p).data)
