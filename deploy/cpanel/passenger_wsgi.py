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

        # Face ID modellari (~6.8 MB — recognition shard1/2 + landmark + tiny) kesh muddati.
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

        # index.html'ga UZOQ KESH QO'YILMASIN.
        #
        # NEGA: /assets/* fayllari nomida hash bor va ularga 30 kunlik kesh
        # tushadi — bu to'g'ri, chunki mazmun o'zgarsa NOM ham o'zgaradi.
        # index.html esa aksincha: nomi doim bir xil, ichida esa o'sha hash'li
        # nomlar turadi. Unga hech qanday Cache-Control tushmasa, brauzer
        # evristikaga o'tadi (odatda Last-Modified'dan beri o'tgan vaqtning
        # ~10%) va uni serverdan SO'RAMASDAN keshdan beradi. Natijada:
        # deploy bo'ladi, lekin xodim eski index.html -> eski chunk'larni
        # ko'raveradi va "yangilik chiqmayapti" deydi. AYNAN SHU HOLAT
        # 03.08.2026 da HR panelida sodir bo'ldi.
        #
        # "no-cache" = "keshla, lekin har safar serverdan tasdiqla". ETag
        # bor, ya'ni o'zgarmagan bo'lsa 304 qaytadi — trafik ortmaydi,
        # faqat bitta yengil so'rov qo'shiladi.
        NO_STORE_HASHLESS = "no-cache"

        # Nomida hash BO'LMAGAN, ildizdan beriladigan fayllar. Service worker
        # ham shu ro'yxatda: brauzer uni odatda o'zi qayta tekshiradi, lekin
        # LiteSpeed .js kengaytmasiga max-age qo'yib yuborishi mumkin va
        # o'shanda push sozlamasi eski SW'da qotib qolardi.
        HASHLESS_FILES = {"index.html", "firebase-messaging-sw.js", "manifest.webmanifest"}

        class SPAStaticFiles(StaticFiles):
            """React Router uchun: mavjud bo'lmagan yo'lda 404 o'rniga index.html
            qaytaradi (masalan /attendance to'g'ridan-to'g'ri ochilganda).
            Yuz modellariga uzoq, hash'siz fayllarga esa qisqa kesh qo'yadi."""

            async def get_response(self, path, scope):
                try:
                    response = await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404:
                        # Fallback ham aynan index.html — kesh sarlavhasi
                        # shu yerda ham qo'yilishi SHART, aks holda
                        # /attendance kabi yo'llar keshda qotib qolardi.
                        response = await super().get_response("index.html", scope)
                        response.headers["Cache-Control"] = NO_STORE_HASHLESS
                        return response
                    raise
                # Starlette `path`ni os.path.normpath bilan quradi — Windows'da
                # u "models\\..." bo'ladi, Linux'da "models/...". Serverda
                # Linux, lekin OS'ga bog'liq tekshiruv yozmaymiz (lokal sinov
                # ham ishlasin).
                clean = path.replace("\\", "/")
                if clean.startswith("models/"):
                    response.headers["Cache-Control"] = MODEL_CACHE
                # `html=True` bo'lgani uchun "/" so'rovi bu yerga "." bo'lib
                # keladi, "/index.html" esa "index.html" bo'lib — ikkalasi ham
                # o'sha faylni beradi, ikkalasi ham qamralishi kerak.
                elif clean in HASHLESS_FILES or clean in (".", ""):
                    response.headers["Cache-Control"] = NO_STORE_HASHLESS
                return response

        # docs_url/redoc_url/openapi_url ATAYLAB o'chirilgan. `api/main.py`
        # ularni `settings.debug` ostida yopgan, LEKIN bu tashqi qobiq alohida
        # `FastAPI()` bo'lgani uchun o'zining STANDART /docs, /redoc,
        # /openapi.json yo'llarini sayt ILDIZIDA ochib qo'yardi — ya'ni
        # backenddagi ataylab qilingan cheklovni chetlab o'tardi.
        root_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @root_app.middleware("http")
        async def security_headers(request, call_next):  # noqa: ANN001, ANN202
            """Xavfsizlik sarlavhalari — SHU YERDA, chunki jonli deploy cPanel
            (Passenger) orqali va oldidagi nginx konfiguratsiyasi bizning
            nazoratimizda emas.

            CSP NEGA MUHIM: JWT `localStorage`da turadi va mobil ilova uni
            WebView'ga kiritadi (`mobile/components/EmbeddedWeb.tsx`) — ya'ni
            saytdagi istalgan HTML-inyeksiya darhol to'liq hisob o'g'irlashga
            aylanardi. CSP shu zanjirni uzadi.

            `setdefault` ishlatiladi: ichki ilova (`/api` yoki SPA) o'z
            sarlavhasini qo'ygan bo'lsa, uni bosib ketmasin.
            """
            response = await call_next(request)
            h = response.headers
            h.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                # Telegram Login Widget — saytdagi YAGONA tashqi skript
                "script-src 'self' https://telegram.org; "
                "frame-src https://oauth.telegram.org; "
                # data: — Face ID canvas'dan chiqadigan rasm; https: — avatarlar
                "img-src 'self' data: https:; "
                # Tailwind ichki (inline) uslublar qo'yadi
                "style-src 'self' 'unsafe-inline'; "
                "connect-src 'self'; "
                "object-src 'none'; base-uri 'self'; form-action 'self'; "
                # Clickjacking — sayt hech qayerga freym qilinmasin
                "frame-ancestors 'none'",
            )
            h.setdefault("X-Frame-Options", "DENY")
            h.setdefault("X-Content-Type-Options", "nosniff")
            h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            # camera/geolocation — DAVOMAT UCHUN SHART, olib tashlamang.
            h.setdefault(
                "Permissions-Policy", "camera=(self), geolocation=(self), microphone=()"
            )
            h.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
            return response

        root_app.mount("/api", api_app)  # /api oldin tekshiriladi

        # APK saytdan TARQATILMAYDI (2026-08-14, egasi qarori). Avval bu yerda
        # `/hodimlar-tizimi.apk` marshruti va server ildizida ~54 MB fayl bor
        # edi; disk kvotasi 1 GB bo'lgani uchun olib tashlandi. APK endi faqat
        # lokal kompyuterda quriladi va boshqa yo'l bilan tarqatiladi.
        # Endi bu manzil SPA fallback'ga tushadi (index.html, HTTP 200) —
        # eski havolani ochgan xodim yuklab olmaydi, saytni ko'radi.

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
