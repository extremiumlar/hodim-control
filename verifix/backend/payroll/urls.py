from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import BonusViewSet, PenaltyViewSet, MonthlyPayrollViewSet


router = DefaultRouter()
router.register("bonuses", BonusViewSet)
router.register("penalties", PenaltyViewSet)
router.register("payrolls", MonthlyPayrollViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
