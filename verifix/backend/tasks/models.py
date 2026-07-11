from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        IN_PROGRESS = "in_progress", "Bajarilmoqda"
        DONE = "done", "Bajarildi"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Rad etildi"

    class Priority(models.TextChoices):
        LOW = "low", "Past"
        NORMAL = "normal", "O'rta"
        HIGH = "high", "Yuqori"

    title = models.CharField("Sarlavha", max_length=255)
    description = models.TextField("Tavsif", blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="tasks", verbose_name="Hodim",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="created_tasks", verbose_name="Bergan kishi",
    )

    due_date = models.DateField("Muddati", null=True, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)

    kpi_points = models.PositiveIntegerField("KPI ball", default=10)

    completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField("Sharh", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vazifa"
        verbose_name_plural = "Vazifalar"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class TaskProof(models.Model):
    """Vazifani bajarganlik isboti (foto / fayl)."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="proofs")
    file = models.FileField(upload_to="task_proofs/%Y/%m/")
    note = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Isbot"
        verbose_name_plural = "Isbotlar"
        ordering = ["-uploaded_at"]
