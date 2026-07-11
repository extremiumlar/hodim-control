from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import LeaveRequestViewSet

router = DefaultRouter()
router.register("", LeaveRequestViewSet)

urlpatterns = [path("", include(router.urls))]
