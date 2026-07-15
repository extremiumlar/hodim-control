"""cPanel "Setup Python App" (Passenger) kirish nuqtasi — API subdomeni uchun.

Passenger Python ilovani WSGI sifatida ishga tushiradi, FastAPI esa ASGI.
a2wsgi.ASGIMiddleware FastAPI (ASGI) ilovasini WSGI callable'ga o'raydi —
Passenger uni to'g'ridan-to'g'ri ishlata oladi. Async SQLAlchemy (aiosqlite)
a2wsgi'ning doimiy event-loop'ida ishlaydi.

cPanel'da:
  1. Bu faylni ilova ildiziga (masalan ~/hodimlar) `passenger_wsgi.py` deb qo'ying.
  2. "Application startup file" = passenger_wsgi.py, "Entry point" = application.
  3. .env'da BOT_WEBHOOK_ENABLED=true bo'lsa bot ham shu ilova ichida (webhook)."""
import sys
from pathlib import Path

# Ilova ildizini (api/, bot/, db/, crm/, scripts/ shu yerda) import yo'liga qo'shamiz
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from a2wsgi import ASGIMiddleware  # noqa: E402
from api.main import app  # noqa: E402

# Passenger shu nomdagi ("application") WSGI callable'ni qidiradi
application = ASGIMiddleware(app)
