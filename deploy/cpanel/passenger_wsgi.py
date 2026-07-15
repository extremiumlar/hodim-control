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
entry point = application."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a2wsgi import ASGIMiddleware  # noqa: E402
from api.main import app as api_app  # noqa: E402

WEBDIST = ROOT / "webdist"

if (WEBDIST / "index.html").exists():
    # ── Asosiy domen rejimi: API /api ostida, sayt / da ──
    from fastapi import FastAPI  # noqa: E402
    from fastapi.staticfiles import StaticFiles  # noqa: E402
    from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402

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
    application = ASGIMiddleware(root_app)
else:
    # ── Subdomen rejimi: faqat API ──
    application = ASGIMiddleware(api_app)
