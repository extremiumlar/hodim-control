import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.services import cron_jobs
from api.deps import get_current_user, get_db, rate_limit, verify_bot_secret
from api.schemas import (
    AppLoginConfirmOut,
    AppLoginConfirmRequest,
    AppLoginPollOut,
    AppLoginPollRequest,
    AppLoginRequestCodeIn,
    AppLoginUseScreenIn,
    AppLoginRequestCodeOut,
    AppLoginStartOut,
    AppLoginStartRequest,
    DevLoginRequest,
    TokenOut,
    UserOut,
)
from api.services.push import send_login_code
from api.security import create_access_token, verify_telegram_login
from db.models import (
    AppLoginStatus,
    AppLoginToken,
    AuditLog,
    LoginAttempt,
    Role,
    User,
    UsedTelegramLoginHash,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Mobil ilova kirishi (deep-link + bir martalik token) — MOBIL_ILOVA_REJASI.md
# 4.1-band. Token shu vaqt ichida tasdiqlanmasa yaroqsiz bo'ladi.
APP_LOGIN_TOKEN_TTL_MINUTES = 5

# Juftlik kodini necha marta noto'g'ri yozish mumkin. Kod 4 raqamli (10 000
# variant) — 3 urinishda topish ehtimoli 0.03%, ya'ni amalda imkonsiz, lekin
# haqiqiy foydalanuvchi bir-ikki marta adashsa ham qayta urina oladi.
MAX_PAIRING_ATTEMPTS = 3

# Barcha faol foydalanuvchilar saytga kira oladi: rahbarlar (boss/rop/hr/dasturchi)
# to'liq boshqaruv panelini, xodimlar (employee) esa faqat o'z davomat (Face ID
# check-in) sahifasini ko'radi. Ruxsat har bir endpointda rol bo'yicha tekshiriladi
# (manager endpointlari employee'ga 403 beradi).
SITE_ROLES = {r.value for r in Role}


async def _issue_token(user: User) -> TokenOut:
    token = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


# UX2-qoldiq #13: WebView tokeni atigi shu muddat yashaydi — ilova uni har
# ochilishda yangidan oladi. 30 daqiqa: eng uzun stsenariy (yuz ro'yxati +
# sekin tarmoq) uchun ham bemalol yetadi.
WEBVIEW_TOKEN_TTL_MINUTES = 30


@router.post("/webview-token")
async def issue_webview_token(user: User = Depends(get_current_user)) -> dict:
    """Mobil ilova WebView'i uchun QISQA muddatli token (30 daq).

    Ilova 30 kunlik asosiy JWT'ni SecureStore'da saqlaydi, lekin WebView
    localStorage'iga endi uni emas, shu qisqa nusxani kiritadi — WebView
    orqali token sizib chiqsa ham (masalan kelajakdagi XSS), zarar oynasi
    bir necha daqiqa bilan cheklanadi (audit B3-5 / P15)."""
    return {
        "access_token": create_access_token(
            user.id, user.role, expires_minutes=WEBVIEW_TOKEN_TTL_MINUTES
        ),
        "expires_in_minutes": WEBVIEW_TOKEN_TTL_MINUTES,
    }


@router.post(
    "/telegram-login", response_model=TokenOut,
    dependencies=[Depends(rate_limit("telegram-login", 15, 900))],
)
async def telegram_login(data: dict[str, Any], db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not verify_telegram_login(data):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Telegram tekshiruvi muvaffaqiyatsiz")

    # Replay himoyasi: imzoning o'zi 24 soatlik `auth_date` oynasida amal qiladi
    # (verify_telegram_login) — demak shu oyna ichida ushlab olingan hash bilan
    # qayta so'rov yuborish mumkin edi (masalan brauzer tarixidan eski Login
    # Widget URL'i qayta ochilsa). Har bir hash faqat BIR MARTA qabul qilinadi.
    db.add(UsedTelegramLoginHash(hash=data["hash"]))
    try:
        await db.commit()
    except IntegrityError:
        # Poyga holati: ikkita so'rov bir xil hash bilan deyarli bir vaqtda
        # kelsa — UNIQUE cheklovi ikkinchisini shu yerda ushlaydi.
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bu login havolasi allaqachon ishlatilgan")

    telegram_id = int(data["id"])
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)


@router.post(
    "/dev-login", response_model=TokenOut,
    dependencies=[Depends(rate_limit("dev-login", 20, 3600))],
)
async def dev_login(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    if not settings.debug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Topilmadi")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Saytga kirish uchun ruxsatingiz yo'q")

    return await _issue_token(user)


@router.post("/bot-token", response_model=TokenOut, dependencies=[Depends(verify_bot_secret)])
async def bot_token(payload: DevLoginRequest, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """Bot orqali Dasturchi buyruqlari (`/norm_set`, `/unlock` va h.k.,
    OYLIK_JARIMA_REJASI.md 11.5-band) uchun ko'prik: bot X-Bot-Secret bilan
    himoyalangan (tashqi hech kim chaqira olmaydi), lekin `/admin/*` va
    boshqa web-darajasidagi endpointlar JWT kutadi — bot uchun bevosita
    kirish yo'q. Shu endpoint TELEGRAM_ID orqali haqiqiy foydalanuvchini
    aniqlab, xuddi shu foydalanuvchi web'dan kirgandagi kabi JWT beradi —
    LEKIN faqat `dasturchi` roli uchun (boshqa rollarga bot orqali to'liq
    web huquqi berilmasin)."""
    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role != Role.dasturchi.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Faqat Dasturchi uchun")
    return await _issue_token(user)


@router.post(
    "/app-login/start", response_model=AppLoginStartOut,
    # Endpoint autentifikatsiyasiz (ilova hali kirmagan) — cheklovsiz bo'lsa
    # istalgan kishi cheksiz token/qator yasab, bazani shishira olardi.
    dependencies=[Depends(rate_limit("app-login-start", 10, 900))],
)
async def app_login_start(
    payload: AppLoginStartRequest | None = None, db: AsyncSession = Depends(get_db)
) -> AppLoginStartOut:
    """Mobil ilova yoki sayt kirish ekrani ochilganda chaqiradi: yangi bir
    martalik token yaratadi va foydalanuvchi botga o'tishi uchun deep-link
    qaytaradi (4.1-band).

    Bilan birga JUFTLIK KODI yaratiladi. Yetkazish kliyentga bog'liq:
    mobil ilova (body'siz — eski versiyalar ham shu) kodni O'Z EKRANIDA
    ko'rsatadi; sayt esa `client: "web"` yuboradi va kod bot ochilganda
    foydalanuvchining mobil ilovasiga PUSH bilan boradi
    (`/app-login/request-code`). Sababi
    `db/models.py: AppLoginToken.pairing_code` va `code_delivery` izohlarida."""
    token = secrets.token_urlsafe(32)
    # 4 raqam — yozish oson, taxmin qilish esa 3 urinish chegarasi bilan
    # amalda imkonsiz (0.03%). `secrets` — tasodifiylik bashorat qilinmasin.
    pairing_code = f"{secrets.randbelow(10000):04d}"
    code_delivery = "push" if payload and payload.client == "web" else "screen"
    expires_at = datetime.utcnow() + timedelta(minutes=APP_LOGIN_TOKEN_TTL_MINUTES)
    db.add(
        AppLoginToken(
            token=token,
            expires_at=expires_at,
            pairing_code=pairing_code,
            code_delivery=code_delivery,
        )
    )
    await db.commit()

    bot_username = settings.telegram_login_bot_username
    deep_link = f"https://t.me/{bot_username}?start=applogin_{token}"
    return AppLoginStartOut(
        login_token=token,
        deep_link=deep_link,
        expires_at=expires_at,
        pairing_code=pairing_code,
    )


@router.post(
    "/app-login/request-code",
    response_model=AppLoginRequestCodeOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def app_login_request_code(
    payload: AppLoginRequestCodeIn, db: AsyncSession = Depends(get_db)
) -> AppLoginRequestCodeOut:
    """Bot `/start applogin_<token>` qabul qilgan zahoti chaqiradi — kod
    qayerdan yetkazilishini hal qiladi va kerak bo'lsa yuboradi.

    Sayt oqimida (`code_delivery="push"`) kod foydalanuvchining mobil
    ilovasiga push bilan ketadi — SHU YERDA, chunki foydalanuvchi kimligi
    (telegram_id) faqat bot ochilganda ma'lum bo'ladi (`/app-login/start`
    autentifikatsiyasiz, u paytda kimga yuborishni bilib bo'lmaydi).

    Push qurilma topilmasa token "screen" rejimiga tushiriladi — sayt poll
    orqali buni ko'rib kodni sahifada o'zi ko'rsatadi. Aks holda mobil
    ilovasiz foydalanuvchi (masalan, ilova o'rnatmagan rahbar) saytga umuman
    kira olmay qolardi."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.status != AppLoginStatus.pending.value or row.expires_at < datetime.utcnow():
        return AppLoginRequestCodeOut(status="invalid")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginRequestCodeOut(status="no_account")

    if row.code_delivery != "push":
        return AppLoginRequestCodeOut(status="screen")

    sent = await send_login_code(db, user, row.pairing_code)
    if sent > 0:
        return AppLoginRequestCodeOut(status="sent")

    row.code_delivery = "screen"
    await db.commit()
    return AppLoginRequestCodeOut(status="screen_fallback")


@router.post(
    "/app-login/use-screen",
    response_model=AppLoginRequestCodeOut,
    dependencies=[Depends(verify_bot_secret)],
)
async def app_login_use_screen(
    payload: AppLoginUseScreenIn, db: AsyncSession = Depends(get_db)
) -> AppLoginRequestCodeOut:
    """«Kod kelmadi» — kodni sayt sahifasida ko'rsatishga o'tish.

    NEGA KERAK (2026-08-21, jonli muammo): push FCM tomonidan qabul
    qilinib (HTTP 200), telefonga YETIB BORMASLIGI mumkin — ilova
    o'chirilgan, bildirishnoma ruxsati olib qo'yilgan, batareya
    cheklovi yoki eski APK'da kanal yo'q. Bunday holda bot «yuborildi»
    deb turardi, kod esa hech qayerda ko'rinmasdi va foydalanuvchi
    saytga UMUMAN kira olmasdi — chiqish yo'li yo'q edi.

    Xavfsizlik darajasi O'ZGARMAYDI: bu aynan `screen_fallback` yo'li,
    u qurilma topilmaganda allaqachon avtomatik ishlaydi. Farqi —
    endi uni foydalanuvchi o'zi ham boshlay oladi. Kodni ko'rish uchun
    login boshlangan BRAUZER sessiyasi kerak, tasdiqlash uchun esa
    Telegram — ikki omil o'z joyida qoladi."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.status != AppLoginStatus.pending.value or row.expires_at < datetime.utcnow():
        return AppLoginRequestCodeOut(status="invalid")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginRequestCodeOut(status="no_account")

    row.code_delivery = "screen"
    db.add(
        AuditLog(
            actor_id=user.id,
            action="app_login_switched_to_screen",
            target_user_id=user.id,
            before={"code_delivery": "push"},
            after={"code_delivery": "screen", "izoh": "foydalanuvchi «kod kelmadi» dedi"},
        )
    )
    await db.commit()
    return AppLoginRequestCodeOut(status="screen_fallback")


@router.post(
    "/app-login/confirm", response_model=AppLoginConfirmOut, dependencies=[Depends(verify_bot_secret)]
)
async def app_login_confirm(
    payload: AppLoginConfirmRequest, db: AsyncSession = Depends(get_db)
) -> AppLoginConfirmOut:
    """Bot `/start applogin_<token>` qabul qilib, foydalanuvchi ILOVADAGI
    JUFTLIK KODINI yozgach chaqiradi. Faqat bot chaqira oladi (X-Bot-Secret) —
    ilova to'g'ridan-to'g'ri `telegram_id` yubora olmaydi, aks holda boshqa
    birovning hisobiga kirish so'ralishi mumkin edi.

    Kod tekshiruvi shu yerda (botda emas): bot faqat foydalanuvchi yozgan
    matnni uzatadi, qaror esa serverda qabul qilinadi va urinishlar ham shu
    yerda sanaladi."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.status != AppLoginStatus.pending.value or row.expires_at < datetime.utcnow():
        return AppLoginConfirmOut(status="invalid")

    user = await db.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginConfirmOut(status="no_account")

    # Kod tekshiruvi — HISOB EGALLASHGA QARSHI ASOSIY HIMOYA.
    # `row.pairing_code` bo'sh bo'lishi mumkin (migratsiyadan oldingi eski
    # qator) — bunday token HECH QACHON tasdiqlanmasin, aks holda bo'sh kod
    # yuborish yetarli bo'lib qolardi. `compare_digest` — doimiy vaqt.
    submitted = (payload.pairing_code or "").strip()
    if not row.pairing_code or not submitted or not hmac.compare_digest(submitted, row.pairing_code):
        row.failed_attempts += 1
        attempts_left = MAX_PAIRING_ATTEMPTS - row.failed_attempts
        if attempts_left <= 0:
            # Token kuydi: 4 raqamni cheksiz taxmin qilib bo'lmasin.
            row.status = AppLoginStatus.used.value
            row.used_at = datetime.utcnow()
            await db.commit()
            return AppLoginConfirmOut(status="invalid", attempts_left=0)
        await db.commit()
        return AppLoginConfirmOut(status="wrong_code", attempts_left=attempts_left)

    row.telegram_id = payload.telegram_id
    row.status = AppLoginStatus.confirmed.value
    row.confirmed_at = datetime.utcnow()
    await db.commit()
    return AppLoginConfirmOut(status="ok")


@router.post(
    "/app-login/poll", response_model=AppLoginPollOut,
    # Ilova bir necha soniyada bir chaqiradi, shuning uchun cheklov bo'sh —
    # maqsad brute-force emas (token 256-bitli), balki bazani so'rov bilan
    # ko'mib tashlashning oldini olish.
    dependencies=[Depends(rate_limit("app-login-poll", 200, 900))],
)
async def app_login_poll(
    payload: AppLoginPollRequest, db: AsyncSession = Depends(get_db)
) -> AppLoginPollOut:
    """Ilova login ekranida bir necha soniyada bir chaqirib turadi. Token
    tasdiqlangan zahoti JWT beriladi va token BIR MARTALIK sifatida
    iste'mol qilinadi (qayta pollansa "expired" qaytadi)."""
    row = await db.scalar(select(AppLoginToken).where(AppLoginToken.token == payload.login_token))
    if not row or row.expires_at < datetime.utcnow() or row.status == AppLoginStatus.used.value:
        return AppLoginPollOut(status="expired")

    if row.status == AppLoginStatus.pending.value:
        return AppLoginPollOut(status="pending", code_delivery=row.code_delivery)

    user = await db.scalar(select(User).where(User.telegram_id == row.telegram_id))
    if not user or not user.is_active or user.role not in SITE_ROLES:
        return AppLoginPollOut(status="expired")

    row.status = AppLoginStatus.used.value
    row.used_at = datetime.utcnow()
    await db.commit()
    return AppLoginPollOut(status="confirmed", token=await _issue_token(user))


@router.post("/login-security-cleanup", dependencies=[Depends(verify_bot_secret)])
async def login_security_cleanup(db: AsyncSession = Depends(get_db)) -> dict:
    """Scheduler tick (Telegram login xavfsizlik arxitekturasi): replay-himoya
    hash'lari va rate-limit urinish yozuvlarini tozalaydi — ikkalasi ham vaqt
    o'tgach umuman kerak bo'lmaydi, jadval cheksiz o'sib ketmasin.

    Hash'lar 25 soatdan (24 soatlik `auth_date` oynasidan xavfsizlik zahirasi
    bilan) oshganda o'chiriladi — imzo o'zi shu vaqtda allaqachon yaroqsiz
    bo'lib qoladi. Urinish yozuvlari 1 soatdan oshganda — eng uzun oyna
    (dev-login, 3600s) shundan qisqa."""
    # Mantiq `api/services/cron_jobs.py` da (Bosqich 4b) — chegaralar va
    # javob kalitlari o'zgarmadi, faqat joyi ko'chdi.
    return await cron_jobs.cleanup_login_security(db)
