from rest_framework import serializers
from .models import Task, TaskProof


class TaskProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskProof
        fields = ["id", "task", "file", "note", "uploaded_at"]
        read_only_fields = ["uploaded_at"]


class TaskSerializer(serializers.ModelSerializer):
    proofs = TaskProofSerializer(many=True, read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "title", "description",
            "assigned_to", "assigned_to_name",
            "created_by", "created_by_name",
            "due_date", "priority", "priority_display",
            "status", "status_display", "kpi_points",
            "completed_at", "approved_at", "review_comment",
            "created_at", "updated_at", "proofs",
        ]
        read_only_fields = ["created_by", "completed_at", "approved_at"]

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() or obj.assigned_to.username

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return ""
