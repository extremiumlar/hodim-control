from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import UserViewSet, DepartmentViewSet, ShiftViewSet, OfficeLocationViewSet


router = DefaultRouter()
router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
router.register("shifts", ShiftViewSet)
router.register("offices", OfficeLocationViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
