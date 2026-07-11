from django.contrib import admin
from .models import Task, TaskProof


class TaskProofInline(admin.TabularInline):
    model = TaskProof
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "assigned_to", "status", "priority", "due_date", "kpi_points")
    list_filter = ("status", "priority")
    search_fields = ("title", "description")
    inlines = [TaskProofInline]


admin.site.register(TaskProof)
