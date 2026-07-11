from decimal import Decimal
from django.conf import settings
from django.db import models


class Bonus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="bonuses")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bonus"
        verbose_name_plural = "Bonuslar"


class Penalty(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="penalties")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    period = models.CharField(max_length=7, help_text="YYYY-MM")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Jarima"
        verbose_name_plural = "Jarimalar"


class MonthlyPayroll(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="payrolls")
    period = models.CharField(max_length=7, help_text="YYYY-MM")

    base_salary = models.DecimalField("Asosiy oylik", max_digits=12, decimal_places=2, default=Decimal("0"))
    per_day_rate = models.DecimalField("Kunlik stavka", max_digits=12, decimal_places=2, default=Decimal("0"))
    absence_deduction = models.DecimalField("Kelmagan kun ayirmasi", max_digits=12, decimal_places=2, default=Decimal("0"))
    weekend_extra = models.DecimalField("Dam olish qo'shimchasi", max_digits=12, decimal_places=2, default=Decimal("0"))
    bonus_total = models.DecimalField("Bonus", max_digits=12, decimal_places=2, default=Decimal("0"))
    penalty_total = models.DecimalField("Jarima", max_digits=12, decimal_places=2, default=Decimal("0"))
    late_penalty_total = models.DecimalField("Kechikish jarimasi", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("Yakuniy summa", max_digits=12, decimal_places=2, default=Decimal("0"))

    work_days_total = models.PositiveIntegerField("Oydagi ish kunlari", default=0)
    worked_days = models.PositiveIntegerField("Ishlangan kunlar", default=0)
    weekend_days = models.PositiveIntegerField("Dam olish ishlagan", default=0)
    late_minutes = models.PositiveIntegerField("Kechikish (daq)", default=0)
    absent_days = models.PositiveIntegerField("Kelmagan kunlar", default=0)

    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_payrolls",
    )
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Oylik hisob-kitob"
        verbose_name_plural = "Oylik hisob-kitoblar"
        unique_together = [("user", "period")]
        ordering = ["-period"]

    def __str__(self) -> str:
        return f"{self.user} — {self.period}"
