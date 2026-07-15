"""POST/PUT/PATCH/DELETE so'rovlarini audit jurnaliga yozadi."""
import json

# Payload'da hech qachon ochiq saqlanmasligi kerak bo'lgan kalitlar
SENSITIVE_KEYS = {"password", "new_password", "face_descriptor", "photo", "token", "access", "refresh"}


def _sanitize_body(raw: bytes, content_type: str) -> str:
    """Audit uchun xavfsiz payload: JSON bo'lsa maxfiy kalitlar "***" bilan
    almashtiriladi; multipart (rasm/fayl) umuman o'qilmaydi; JSON bo'lmagan
    body uchun belgigina yoziladi — parol/deskriptor/rasm jurnalga tushmaydi."""
    if content_type.startswith("multipart/form-data"):
        return "<multipart body>"
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return "<non-json body>"
    if isinstance(data, dict):
        for key in SENSITIVE_KEYS & set(data.keys()):
            data[key] = "***"
        return json.dumps(data, ensure_ascii=False)[:2000]
    return json.dumps(data, ensure_ascii=False)[:2000]


class AuditMiddleware:
    LOG_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP_PATHS = ("/api/auth/", "/admin/jsi18n/")
    # Yo'lida shu bo'laklar bo'lgan endpointlar butunlay yozilmaydi — ularda
    # faqat maxfiy ma'lumot (parol, yuz deskriptori/rasmi) bo'ladi.
    SKIP_PATH_PARTS = ("set-password", "register-face", "reset-face")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (request.method in self.LOG_METHODS
                    and request.path.startswith("/api/")
                    and not any(request.path.startswith(p) for p in self.SKIP_PATHS)
                    and not any(part in request.path for part in self.SKIP_PATH_PARTS)):
                from .models import AuditLog
                user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
                ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                      or request.META.get("REMOTE_ADDR"))
                payload = ""
                try:
                    payload = _sanitize_body(
                        request.body[:2000], request.META.get("CONTENT_TYPE", "") or ""
                    )
                except Exception:
                    pass
                AuditLog.objects.create(
                    user=user,
                    method=request.method,
                    path=request.path[:255],
                    status_code=response.status_code,
                    ip=ip,
                    payload=payload,
                )
        except Exception:
            pass
        return response
