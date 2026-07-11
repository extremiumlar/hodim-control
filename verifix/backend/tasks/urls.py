from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import TaskViewSet, TaskProofViewSet


router = DefaultRouter()
router.register("proofs", TaskProofViewSet)
router.register("", TaskViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
