from django.conf import settings
from django.db import models


class LeaveRequest(models.Model):
    class Type(models.TextChoices):
        VACATION = "vacation", "Ta'til"
        SICK = "sick", "Kasallik"
        UNPAID = "unpaid", "To'lovsiz"
        OTHER = "other", "Boshqa"

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="leave_requests",
    )
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.VACATION)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_leaves",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ta'til so'rovi"
        verbose_name_plural = "Ta'til so'rovlari"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} {self.start_date}—{self.end_date} ({self.get_status_display()})"
