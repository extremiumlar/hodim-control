from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="audit_logs",
    )
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=255)
    status_code = models.PositiveSmallIntegerField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    payload = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit yozuvi"
        verbose_name_plural = "Audit jurnali"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.user} {self.method} {self.path}"
