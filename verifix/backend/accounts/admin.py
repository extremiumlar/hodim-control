from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, Department, Shift, OfficeLocation


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "role", "department", "shift", "is_on_leave", "is_active")
    list_filter = ("role", "department", "is_on_leave", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "phone")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Hodim ma'lumotlari", {
            "fields": (
                "role", "phone", "telegram_id",
                "department", "shift", "office", "work_days",
                "base_salary", "weekend_rate", "late_penalty_per_minute",
                "is_on_leave",
            )
        }),
    )


admin.site.register(Department)
admin.site.register(Shift)
admin.site.register(OfficeLocation)
