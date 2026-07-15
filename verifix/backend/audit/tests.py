"""Audit middleware sinovi — maxfiy ma'lumot tozalash va yozish tartibi."""
from django.test import TestCase

from .middleware import _sanitize_body
from .models import AuditLog


class SanitizeBodyTests(TestCase):
    """_sanitize_body: maxfiy kalitlar yashiriladi, JSON bo'lmagani belgilanadi."""

    def test_password_masked(self):
        out = _sanitize_body(b'{"password": "sir123", "username": "ali"}', "application/json")
        self.assertIn('"password": "***"', out)
        self.assertIn('"username": "ali"', out)

    def test_face_descriptor_masked(self):
        out = _sanitize_body(b'{"face_descriptor": [0.1, 0.2], "liveness": 0.9}', "application/json")
        self.assertIn('"face_descriptor": "***"', out)
        self.assertIn('"liveness": 0.9', out)

    def test_token_fields_masked(self):
        out = _sanitize_body(b'{"access": "a.b.c", "refresh": "d.e.f"}', "application/json")
        self.assertNotIn("a.b.c", out)
        self.assertNotIn("d.e.f", out)

    def test_non_json_marked(self):
        self.assertEqual(_sanitize_body(b"xom matn", "application/json"), "<non-json body>")

    def test_multipart_not_read(self):
        self.assertEqual(_sanitize_body(b"...", "multipart/form-data; boundary=x"), "<multipart body>")

    def test_json_list_kept(self):
        self.assertEqual(_sanitize_body(b"[1, 2]", "application/json"), "[1, 2]")


class MiddlewareFlowTests(TestCase):
    """Middleware: body view'dan oldin o'qiladi (payload bo'sh emas), maxfiy
    endpointlar umuman yozilmaydi, GET yozilmaydi."""

    def test_json_post_logged_with_masked_payload(self):
        self.client.post(
            "/api/leave/requests/",
            data='{"password": "sir", "type": "vacation"}',
            content_type="application/json",
        )
        log = AuditLog.objects.latest("id")
        self.assertEqual(log.path, "/api/leave/requests/")
        self.assertIn('"password": "***"', log.payload)
        self.assertIn('"type": "vacation"', log.payload)

    def test_set_password_path_skipped(self):
        before = AuditLog.objects.count()
        self.client.post(
            "/api/accounts/users/1/set-password/",
            data='{"password": "yangi"}',
            content_type="application/json",
        )
        self.assertEqual(AuditLog.objects.count(), before)

    def test_register_face_path_skipped(self):
        before = AuditLog.objects.count()
        self.client.post(
            "/api/accounts/users/register-face/",
            data='{"face_descriptor": [0.1]}',
            content_type="application/json",
        )
        self.assertEqual(AuditLog.objects.count(), before)

    def test_multipart_post_logged_without_body(self):
        self.client.post("/api/leave/requests/", data={"note": "t"})  # test client default multipart
        log = AuditLog.objects.latest("id")
        self.assertEqual(log.payload, "<multipart body>")

    def test_get_not_logged(self):
        before = AuditLog.objects.count()
        self.client.get("/api/leave/requests/")
        self.assertEqual(AuditLog.objects.count(), before)
