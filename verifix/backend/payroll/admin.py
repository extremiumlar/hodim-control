from django.contrib import admin
from .models import Bonus, Penalty, MonthlyPayroll

admin.site.register(Bonus)
admin.site.register(Penalty)


@admin.register(MonthlyPayroll)
class MonthlyPayrollAdmin(admin.ModelAdmin):
    list_display = ("user", "period", "total", "is_approved", "generated_at")
    list_filter = ("period", "is_approved")
    search_fields = ("user__username", "user__first_name", "user__last_name")
