from rest_framework import serializers
from .models import Bonus, Penalty, MonthlyPayroll


class BonusSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Bonus
        fields = ["id", "user", "user_name", "amount", "reason", "period", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class PenaltySerializer(BonusSerializer):
    class Meta(BonusSerializer.Meta):
        model = Penalty


class MonthlyPayrollSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyPayroll
        fields = [
            "id", "user", "user_name", "period",
            "base_salary", "per_day_rate", "absence_deduction",
            "weekend_extra", "bonus_total",
            "penalty_total", "late_penalty_total", "total",
            "work_days_total", "worked_days", "weekend_days",
            "late_minutes", "absent_days",
            "is_approved", "approved_by", "approved_by_name", "generated_at",
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return obj.approved_by.get_full_name() or obj.approved_by.username
        return ""
