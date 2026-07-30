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

        # Face ID modellari (~4.4 MB siqilgan holda) uchun kesh muddati.
        # /assets/*.js ga LiteSpeed KENGAYTMA bo'yicha max-age qo'yadi, model
        # shard fayllarida esa kengaytma YO'Q (face_recognition_model-shard1)
        # — shuning uchun ularga hech qanday Cache-Control tushmaydi va kesh
        # brauzer evristikasiga qolib ketadi (deploydan keyin oyna juda qisqa).
        #
        # DIQQAT: fayl nomlarida hash YO'Q. Model fayllari o'zgarsa xodimda
        # 30 kungacha eski model qolishi mumkin — bu Face ID'ni buzadi
        # (descriptorlar boshqa modelniki bo'ladi). Modelni almashtirish
        # baribir hamma xodimni qayta ro'yxatdan o'tkazishni talab qiladi
        # (MOBIL_ILOVA_REJASI.md 4.2), ya'ni rejalashtirilgan migratsiya —
        # o'shanda YO'L ham o'zgartirilsin (masalan /models/v2/), aks holda
        # eski kesh yangi model bilan aralashadi.
        MODEL_CACHE = "public, max-age=2592000"  # 30 kun, /assets bilan bir xil

        class SPAStaticFiles(StaticFiles):
            """React Router uchun: mavjud bo'lmagan yo'lda 404 o'rniga index.html
            qaytaradi (masalan /attendance to'g'ridan-to'g'ri ochilganda).
            Yuz modellariga esa uzoq kesh sarlavhasini qo'yadi."""

            async def get_response(self, path, scope):
                try:
                    response = await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404:
                        return await super().get_response("index.html", scope)
                    raise
                # Starlette `path`ni os.path.normpath bilan quradi — Windows'da
                # u "models\\..." bo'ladi, Linux'da "models/...". Serverda
                # Linux, lekin OS'ga bog'liq tekshiruv yozmaymiz (lokal sinov
                # ham ishlasin).
                if path.replace("\\", "/").startswith("models/"):
                    response.headers["Cache-Control"] = MODEL_CACHE
                return response

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
