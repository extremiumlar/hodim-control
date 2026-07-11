from rest_framework import serializers
from .models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id", "user", "user_name", "date",
            "check_in_time", "check_in_lat", "check_in_lng",
            "check_in_distance_m",
            "check_out_time", "check_out_lat", "check_out_lng",
            "late_minutes", "early_leave_minutes", "worked_minutes",
            "status", "status_display", "is_weekend", "note",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class CheckInRequestSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    face_descriptor = serializers.ListField(
        child=serializers.FloatField(), min_length=128, max_length=128, required=False,
    )
    liveness = serializers.FloatField(required=False, default=0.0, min_value=0.0, max_value=1.0)
