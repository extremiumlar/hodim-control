from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "method", "path", "status_code", "ip")
    list_filter = ("method", "status_code")
    search_fields = ("path", "user__username")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
