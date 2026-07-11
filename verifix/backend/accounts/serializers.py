from rest_framework import serializers
from .models import User, Department, Shift, OfficeLocation


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "description"]


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = ["id", "name", "start_time", "end_time", "grace_minutes", "work_days"]


class OfficeLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfficeLocation
        fields = [
            "id", "name", "latitude", "longitude", "radius_meters",
            "is_active",
        ]


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    shift_name = serializers.CharField(source="shift.name", read_only=True)
    office_name = serializers.CharField(source="office.name", read_only=True)
    full_name = serializers.SerializerMethodField()
    has_face = serializers.BooleanField(read_only=True)
    face_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "full_name",
            "role", "phone", "telegram_id",
            "department", "department_name",
            "shift", "shift_name",
            "office", "office_name",
            "work_days",
            "base_salary", "weekend_rate", "late_penalty_per_minute",
            "is_active", "is_on_leave", "date_joined",
            "has_face", "face_registered_at", "face_photo_url",
        ]
        read_only_fields = ["date_joined", "has_face", "face_registered_at", "face_photo_url"]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_face_photo_url(self, obj):
        if obj.face_photo:
            request = self.context.get("request")
            url = obj.face_photo.url
            return request.build_absolute_uri(url) if request else url
        return None


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=6)

    class Meta:
        model = User
        fields = [
            "id", "username", "password", "email", "first_name", "last_name",
            "role", "phone", "telegram_id",
            "department", "shift", "office", "work_days",
            "base_salary", "weekend_rate", "late_penalty_per_minute",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class MeSerializer(UserSerializer):
    """Yetkazib beruvchi /me/ endpointi uchun."""
    pass
