from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsHRRole
from .models import LeaveRequest
from .serializers import LeaveRequestSerializer


class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.select_related("user", "reviewed_by").all()
    serializer_class = LeaveRequestSerializer
    filterset_fields = ["user", "status", "type"]

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_hr_role:
            qs = qs.filter(user=self.request.user)
        return qs

    def perform_create(self, serializer):
        if not self.request.user.is_hr_role:
            serializer.save(user=self.request.user)
        else:
            serializer.save()

    @action(detail=True, methods=["post"], url_path="approve",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def approve(self, request, pk=None):
        leave = self.get_object()
        leave.status = LeaveRequest.Status.APPROVED
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        leave.review_comment = request.data.get("comment", "")
        leave.save()
        # is_on_leave endi faqat kesh/ko'rsatish uchun — qarorlar (check-in,
        # oylik) LeaveRequest oralig'iga tayanadi. Bayroq faqat ta'til hali
        # tugamagan bo'lsa qo'yiladi (o'tmishdagi ta'til hodimni "abadiy
        # ta'tilda" qilib qo'ymasin).
        if leave.end_date >= timezone.localdate():
            leave.user.is_on_leave = True
            leave.user.save(update_fields=["is_on_leave"])
        return Response(LeaveRequestSerializer(leave).data)

    @action(detail=True, methods=["post"], url_path="reject",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def reject(self, request, pk=None):
        leave = self.get_object()
        leave.status = LeaveRequest.Status.REJECTED
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        leave.review_comment = request.data.get("comment", "")
        leave.save()
        return Response(LeaveRequestSerializer(leave).data)

    @action(detail=True, methods=["post"], url_path="finish",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def finish(self, request, pk=None):
        leave = self.get_object()
        leave.user.is_on_leave = False
        leave.user.save(update_fields=["is_on_leave"])
        return Response({"detail": "Ta'til yakunlandi."})
