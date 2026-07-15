from django.conf import settings
from django.db import models
from django.utils import timezone


class Attendance(models.Model):
    """Bir kunlik davomat yozuvi. user + date unique.

    `late_minutes`, `early_leave_minutes`, `worked_minutes` AVTOMATIK
    hisoblanadi — `save()` chaqirilganda check_in_time / check_out_time
    asosida qayta yangilanadi (admin paneldan ham, API dan ham).
    """

    class Status(models.TextChoices):
        PRESENT = "present", "Keldi"
        LATE = "late", "Kechikdi"
        ABSENT = "absent", "Kelmadi"
        LEAVE = "leave", "Ta'tilda"
        WEEKEND = "weekend", "Dam olish kuni"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="attendances",
    )
    date = models.DateField("Sana", default=timezone.localdate)

    check_in_time = models.DateTimeField("Kelgan vaqti", null=True, blank=True)
    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_distance_m = models.PositiveIntegerField(null=True, blank=True)

    check_out_time = models.DateTimeField("Ketgan vaqti", null=True, blank=True)
    check_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    late_minutes = models.PositiveIntegerField("Kechikish (daq)", default=0)
    early_leave_minutes = models.PositiveIntegerField("Erta ketish (daq)", default=0)
    worked_minutes = models.PositiveIntegerField("Ishlangan (daq)", default=0)

    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.PRESENT,
    )
    is_weekend = models.BooleanField("Dam olish kuni", default=False)
    note = models.TextField("Izoh", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Davomat"
        verbose_name_plural = "Davomat yozuvlari"
        unique_together = [("user", "date")]
        ordering = ["-date", "-check_in_time"]

    def __str__(self) -> str:
        return f"{self.user} — {self.date}"

    # ───────────────────────────────────────────────
    # AVTOMATIK HISOBLASH
    # ───────────────────────────────────────────────
    def recalculate(self) -> None:
        """check_in_time / check_out_time asosida hamma raqamlarni qayta hisoblaydi."""
        from .utils import (
            compute_late_minutes, compute_early_minutes,
            compute_worked_minutes, is_weekend,
        )
        shift = getattr(self.user, "shift", None)

        # Dam olish kuni? (hodimning shaxsiy ish kunlari bo'yicha)
        self.is_weekend = is_weekend(self.date, self.user.work_day_set())

        # Kechikish
        if self.check_in_time and shift:
            self.late_minutes = compute_late_minutes(
                self.check_in_time, shift.start_time, shift.grace_minutes,
            )
        else:
            self.late_minutes = 0

        # Erta ketish
        if self.check_out_time and shift:
            self.early_leave_minutes = compute_early_minutes(
                self.check_out_time, shift.end_time,
            )
        else:
            self.early_leave_minutes = 0

        # Ishlangan vaqt (smenada tanaffus bo'lsa u ayiriladi)
        self.worked_minutes = compute_worked_minutes(self.check_in_time, self.check_out_time, shift)

        # Status
        if self.is_weekend:
            self.status = self.Status.WEEKEND
        elif not self.check_in_time:
            self.status = self.Status.ABSENT
        elif self.late_minutes > 0:
            self.status = self.Status.LATE
        else:
            self.status = self.Status.PRESENT

    def save(self, *args, **kwargs):
        # Har bir save oldidan avtomatik hisoblash
        self.recalculate()
        super().save(*args, **kwargs)
