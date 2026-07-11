from django.contrib import admin
from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "check_in_time", "check_out_time",
                    "late_minutes", "worked_minutes", "status")
    list_filter = ("status", "is_weekend", "date")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    date_hierarchy = "date"
