from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from accounts.permissions import IsHRRole
from .models import Task, TaskProof
from .serializers import TaskSerializer, TaskProofSerializer


class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.select_related("assigned_to", "created_by").prefetch_related("proofs").all()
    serializer_class = TaskSerializer
    filterset_fields = ["assigned_to", "status", "priority"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "due_date", "priority"]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if not u.is_hr_role:
            qs = qs.filter(assigned_to=u)
        return qs

    def perform_create(self, serializer):
        if not self.request.user.is_hr_role:
            raise permissions.PermissionDenied("Faqat HR/Admin vazifa berishi mumkin.")
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        task = self.get_object()
        if task.assigned_to_id != request.user.id and not request.user.is_hr_role:
            return Response({"detail": "Bu sizning vazifangiz emas."}, status=403)
        if task.status in {Task.Status.DONE, Task.Status.APPROVED}:
            return Response({"detail": "Vazifa allaqachon yakunlangan."}, status=400)
        task.status = Task.Status.DONE
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="approve",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def approve(self, request, pk=None):
        task = self.get_object()
        task.status = Task.Status.APPROVED
        task.approved_at = timezone.now()
        task.review_comment = request.data.get("comment", "")
        task.save()
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"], url_path="reject",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def reject(self, request, pk=None):
        task = self.get_object()
        task.status = Task.Status.REJECTED
        task.review_comment = request.data.get("comment", "")
        task.save()
        return Response(TaskSerializer(task).data)


class TaskProofViewSet(viewsets.ModelViewSet):
    queryset = TaskProof.objects.select_related("task", "task__assigned_to").all()
    serializer_class = TaskProofSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if not u.is_hr_role:
            qs = qs.filter(task__assigned_to=u)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data["task"]
        if task.assigned_to_id != self.request.user.id and not self.request.user.is_hr_role:
            raise permissions.PermissionDenied("Bu vazifa sizga tegishli emas.")
        serializer.save()
