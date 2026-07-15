from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models


class Department(models.Model):
    name = models.CharField("Nomi", max_length=100, unique=True)
    description = models.TextField("Tavsif", blank=True)

    class Meta:
        verbose_name = "Bo'lim"
        verbose_name_plural = "Bo'limlar"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Shift(models.Model):
    """Hodimning ish smenasi (masalan 09:00 - 18:00)."""
    name = models.CharField("Nomi", max_length=100)
    start_time = models.TimeField("Boshlanish")
    end_time = models.TimeField("Tugash")
    grace_minutes = models.PositiveIntegerField(
        "Kechikishga ruxsat (daqiqa)", default=5,
        help_text="Shu daqiqadan keyin kechikish hisoblanadi.",
    )
    # Tanaffus (masalan tushlik 13:00-14:00) — ishlangan vaqt hisobidan
    # chiqariladi. Ikkalasi ham to'ldirilgandagina qo'llanadi.
    break_start = models.TimeField("Tanaffus boshlanishi", null=True, blank=True)
    break_end = models.TimeField("Tanaffus tugashi", null=True, blank=True)
    work_days = models.CharField(
        "Ish kunlari",
        max_length=20,
        default="1,2,3,4,5",
        help_text="Vergul bilan: 1=Du, 7=Ya",
    )

    class Meta:
        verbose_name = "Smena"
        verbose_name_plural = "Smenalar"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}-{self.end_time:%H:%M})"

    def work_day_set(self):
        return {int(x) for x in self.work_days.split(",") if x.strip().isdigit()}


class OfficeLocation(models.Model):
    """Ofis joyi: GPS markazi + radius."""
    name = models.CharField("Nomi", max_length=100)
    latitude = models.DecimalField("Kenglik", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("Uzunlik", max_digits=9, decimal_places=6)
    radius_meters = models.PositiveIntegerField("Radius (m)", default=150)
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Ofis joyi"
        verbose_name_plural = "Ofis joylari"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        HR = "hr", "HR / Manager"
        EMPLOYEE = "employee", "Hodim"

    role = models.CharField(
        "Rol", max_length=20, choices=Role.choices, default=Role.EMPLOYEE
    )
    phone = models.CharField("Telefon", max_length=20, blank=True)
    telegram_id = models.CharField("Telegram ID", max_length=50, blank=True)

    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employees", verbose_name="Bo'lim",
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employees", verbose_name="Smena",
    )
    office = models.ForeignKey(
        OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employees", verbose_name="Ofis",
    )

    work_days = models.CharField(
        "Ish kunlari",
        max_length=20,
        default="1,2,3,4,5",
        help_text="Vergul bilan: 1=Du, 2=Se, 3=Ch, 4=Pa, 5=Ju, 6=Sha, 7=Ya. "
                  "Masalan 5 kunlik: 1,2,3,4,5 | 6 kunlik: 1,2,3,4,5,6",
    )

    base_salary = models.DecimalField(
        "Asosiy oylik", max_digits=12, decimal_places=2, default=Decimal("0.00"),
    )
    weekend_rate = models.DecimalField(
        "Dam olish kuni stavkasi (%)", max_digits=5, decimal_places=2,
        default=Decimal("150.00"),
        help_text="Oddiy kun stavkasiga nisbatan foiz. 150 = 1.5x",
    )
    late_penalty_per_minute = models.DecimalField(
        "1 daqiqa kechikish jarimasi", max_digits=10, decimal_places=2,
        default=Decimal("0.00"),
    )
    is_on_leave = models.BooleanField("Ta'tilda", default=False)

    # ─── Face ID ──────────────────────────────────────
    face_descriptor = models.TextField(
        "Yuz kodi (128-dim JSON)", blank=True, default="",
        help_text="face-api.js 128-dim deskriptor JSON formatda.",
    )
    face_photo = models.ImageField(
        "Yuz rasmi", upload_to="face_photos/", null=True, blank=True,
    )
    face_registered_at = models.DateTimeField("Yuz ro'yxatdan o'tgan vaqt", null=True, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"
        ordering = ["first_name", "last_name", "id"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def has_face(self) -> bool:
        return bool(self.face_descriptor)

    def get_face_descriptor(self) -> list[float] | None:
        """JSON dan deskriptorni qaytaradi."""
        import json
        if not self.face_descriptor:
            return None
        try:
            arr = json.loads(self.face_descriptor)
            return arr if isinstance(arr, list) else None
        except Exception:
            return None

    def face_similarity(self, other: list[float]) -> float:
        """0..1 oraliqdagi o'xshashlik. 1 = mukammal mos kelish, 0 = boshqa odam.

        Hisoblash: 1 - euclidean_distance (face-api.js'da ~0-1 oraliqda).
        Distance > 1 bo'lsa 0 qaytaradi.
        """
        import math
        d = self.get_face_descriptor()
        if not d or not other or len(d) != len(other):
            return 0.0
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(d, other)))
        return max(0.0, 1.0 - dist)

    def work_day_set(self) -> set[int]:
        """Hodimning ish kunlari (ISO: 1=Du..7=Ya).

        Hodimda ko'rsatilgan bo'lsa o'shani, aks holda smena kunlarini oladi.
        """
        raw = self.work_days
        if not raw and self.shift:
            raw = self.shift.work_days
        if not raw:
            raw = "1,2,3,4,5"
        return {int(x) for x in raw.split(",") if x.strip().isdigit()}

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_hr_role(self) -> bool:
        return self.role in {self.Role.ADMIN, self.Role.HR} or self.is_superuser
