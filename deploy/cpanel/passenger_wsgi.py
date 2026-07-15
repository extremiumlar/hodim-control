"""cPanel "Setup Python App" (Passenger) kirish nuqtasi.

Passenger Python ilovani WSGI sifatida ishga tushiradi, FastAPI esa ASGI —
a2wsgi.ASGIMiddleware ASGI ilovani WSGI callable'ga o'raydi.

Ikki rejim (avtomatik aniqlanadi):

1) ASOSIY DOMEN (webdist/ mavjud): bitta domendan ham API, ham sayt.
   - /api/*  → FastAPI API (masalan /api/auth/token → api /auth/token)
   - /*      → React SPA (webdist/ dan statik + noma'lum yo'llar index.html'ga)
   React VITE_API_BASE_URL=/api bilan build qilinadi, .env'da
   API_BASE_URL=https://domen.uz/api (bot self-call va webhook uchun).

2) SUBDOMEN (webdist/ yo'q): faqat API root'da (api.domen.uz).

cPanel: bu fayl ilova ildizida (passenger_wsgi.py), startup file = passenger_wsgi.py,
entry point = application.

MUHIM: a2wsgi.ASGIMiddleware fon event-loop thread'ini o'z __init__'ida (import
vaqtida) yaratadi. Passenger esa ilovani "smart spawning" bilan master jarayonda
oldindan yuklab, keyin ishchi jarayonlarga FORK qiladi. Thread'lar fork'dan omon
qolmaydi — natijada ishchida loop thread o'lik bo'lib, bazaga har await abadiy
osiladi. Shuning uchun ASGIMiddleware'ni import vaqtida emas, BIRINCHI SO'ROVDA
(ishchi jarayonda, fork'dan keyin) lazily yaratamiz."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import app as api_app  # noqa: E402

WEBDIST = ROOT / "webdist"


def _build_target():
    """Passenger'ga beriladigan ASGI ilovani quradi (o'ram'siz)."""
    if (WEBDIST / "index.html").exists():
        # ── Asosiy domen rejimi: API /api ostida, sayt / da ──
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        from starlette.exceptions import HTTPException as StarletteHTTPException

        class SPAStaticFiles(StaticFiles):
            """React Router uchun: mavjud bo'lmagan yo'lda 404 o'rniga index.html
            qaytaradi (masalan /attendance to'g'ridan-to'g'ri ochilganda)."""

            async def get_response(self, path, scope):
                try:
                    return await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404:
                        return await super().get_response("index.html", scope)
                    raise

        root_app = FastAPI()
        root_app.mount("/api", api_app)  # /api oldin tekshiriladi
        root_app.mount("/", SPAStaticFiles(directory=str(WEBDIST), html=True), name="spa")
        return root_app
    # ── Subdomen rejimi: faqat API ──
    return api_app


_wrapped = None


def application(environ, start_response):
    """Passenger kirish nuqtasi. ASGIMiddleware (va uning event-loop thread'i)
    birinchi so'rovda, ishchi jarayonning ichida yaratiladi — fork'dan keyin,
    shuning uchun thread tirik bo'ladi."""
    global _wrapped
    if _wrapped is None:
        from a2wsgi import ASGIMiddleware

        _wrapped = ASGIMiddleware(_build_target())
    return _wrapped(environ, start_response)
