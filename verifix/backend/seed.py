"""Boshlang'ich ma'lumotlarni yaratadi: admin, ofis, smena, hodim.

Ishlatish:
    python manage.py shell < seed.py
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from accounts.models import Department, Shift, OfficeLocation

User = get_user_model()

# 1. Admin
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser(
        username="admin", email="admin@example.com", password="admin123",
        first_name="Bosh", last_name="Admin", role=User.Role.ADMIN,
    )
    print("Admin yaratildi: admin / admin123")

# 2. Bo'lim
dept, _ = Department.objects.get_or_create(name="Dasturchilar bo'limi")

# 3. Smena 09:00-18:00
shift, _ = Shift.objects.get_or_create(
    name="Standart 9-18",
    defaults={"start_time": "09:00", "end_time": "18:00", "grace_minutes": 5, "work_days": "1,2,3,4,5"},
)

# 4. Ofis (Toshkent markazi - misol uchun)
office, _ = OfficeLocation.objects.get_or_create(
    name="Bosh ofis",
    defaults={
        "latitude": Decimal("41.311081"),
        "longitude": Decimal("69.240562"),
        "radius_meters": 200,
        "is_active": True,
    },
)

# 5. Test hodim
if not User.objects.filter(username="hodim").exists():
    u = User.objects.create_user(
        username="hodim", password="hodim123",
        first_name="Test", last_name="Hodimov",
        role=User.Role.EMPLOYEE,
        department=dept, shift=shift, office=office,
        base_salary=Decimal("5000000"),
        weekend_rate=Decimal("150"),
        late_penalty_per_minute=Decimal("1000"),
    )
    print(f"Test hodim yaratildi: hodim / hodim123 (id={u.id})")

print("\nSeed tugadi. http://localhost:8000/admin ga kiring.")
