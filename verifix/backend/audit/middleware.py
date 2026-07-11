"""POST/PUT/PATCH/DELETE so'rovlarini audit jurnaliga yozadi."""
import json


class AuditMiddleware:
    LOG_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP_PATHS = ("/api/auth/", "/admin/jsi18n/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (request.method in self.LOG_METHODS
                    and request.path.startswith("/api/")
                    and not any(request.path.startswith(p) for p in self.SKIP_PATHS)):
                from .models import AuditLog
                user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
                ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
                      or request.META.get("REMOTE_ADDR"))
                payload = ""
                try:
                    body = request.body[:2000].decode("utf-8", errors="ignore")
                    payload = body
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
