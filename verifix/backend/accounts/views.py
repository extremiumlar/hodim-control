from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import User, Department, Shift, OfficeLocation
from .serializers import (
    UserSerializer, UserCreateSerializer,
    DepartmentSerializer, ShiftSerializer, OfficeLocationSerializer,
    MeSerializer,
)
from .permissions import IsHRRole


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("department", "shift", "office").all()
    filterset_fields = ["role", "department", "is_active", "is_on_leave"]
    search_fields = ["username", "first_name", "last_name", "email", "phone"]
    ordering_fields = ["date_joined", "username", "first_name"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in {"list", "create", "destroy", "partial_update", "update"}:
            return [permissions.IsAuthenticated(), IsHRRole()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if not u.is_hr_role:
            qs = qs.filter(id=u.id)
        return qs

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        if request.method == "GET":
            return Response(MeSerializer(request.user).data)
        ser = MeSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @action(detail=False, methods=["post"], url_path="register-face",
            parser_classes=[__import__("rest_framework").parsers.MultiPartParser,
                           __import__("rest_framework").parsers.FormParser,
                           __import__("rest_framework").parsers.JSONParser])
    def register_face(self, request):
        """Hodim o'z yuzini ro'yxatdan o'tkazadi (rasm yuklash orqali).

        Multipart body:
          - face_descriptor: JSON ko'rinishidagi 128-dim massiv (string yoki list)
          - photo: rasm fayli (ixtiyoriy, ko'rsatish uchun saqlanadi)
        """
        import json
        from django.utils import timezone

        # face_descriptor JSON string yoki list bo'lishi mumkin
        raw = request.data.get("face_descriptor")
        if isinstance(raw, str):
            try:
                descriptor = json.loads(raw)
            except Exception:
                return Response({"detail": "face_descriptor JSON formatda emas."}, status=400)
        else:
            descriptor = raw

        if not isinstance(descriptor, list) or len(descriptor) != 128:
            return Response(
                {"detail": "face_descriptor 128 ta sondan iborat bo'lishi kerak."},
                status=400,
            )

        user = request.user
        user.face_descriptor = json.dumps(descriptor)
        user.face_registered_at = timezone.now()

        # Rasm yuborilgan bo'lsa - saqlaymiz (ko'rsatish uchun)
        photo = request.FILES.get("photo")
        update_fields = ["face_descriptor", "face_registered_at"]
        if photo:
            # Eskisini o'chiramiz
            if user.face_photo:
                try:
                    user.face_photo.delete(save=False)
                except Exception:
                    pass
            user.face_photo = photo
            update_fields.append("face_photo")

        user.save(update_fields=update_fields)
        return Response({
            "detail": "✅ Yuz muvaffaqiyatli ro'yxatdan o'tkazildi.",
            "has_face": True,
            "registered_at": user.face_registered_at,
        })

    @action(detail=True, methods=["delete", "post"], url_path="reset-face",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def reset_face(self, request, pk=None):
        """Admin hodimning yuzini o'chiradi (qaytadan ro'yxatdan o'tishi uchun)."""
        user = self.get_object()
        user.face_descriptor = ""
        user.face_registered_at = None
        user.save(update_fields=["face_descriptor", "face_registered_at"])
        return Response({"detail": "Yuz ma'lumotlari tozalandi."})

    @action(detail=True, methods=["post"], url_path="set-password",
            permission_classes=[permissions.IsAuthenticated, IsHRRole])
    def set_password(self, request, pk=None):
        user = self.get_object()
        pwd = request.data.get("password")
        if not pwd or len(pwd) < 6:
            return Response({"detail": "Parol kamida 6 ta belgi."}, status=400)
        user.set_password(pwd)
        user.save(update_fields=["password"])
        return Response({"detail": "Parol yangilandi."})


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsHRRole]


class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer
    permission_classes = [permissions.IsAuthenticated, IsHRRole]


class OfficeLocationViewSet(viewsets.ModelViewSet):
    queryset = OfficeLocation.objects.all()
    serializer_class = OfficeLocationSerializer
    permission_classes = [permissions.IsAuthenticated, IsHRRole]
