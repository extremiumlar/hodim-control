from rest_framework import serializers
from .models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    def get_user_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "user", "user_name", "type", "type_display",
            "start_date", "end_date", "reason",
            "status", "status_display",
            "reviewed_by", "reviewed_at", "review_comment", "created_at",
        ]
        read_only_fields = ["status", "reviewed_by", "reviewed_at", "review_comment", "created_at"]
