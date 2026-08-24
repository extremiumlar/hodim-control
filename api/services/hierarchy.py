"""Kim kimni boshqaradi — YAGONA MANBA (yangi TZ 3.16 / S-44).

═══════════════════════════════════════════════════════════════
⚠️ NEGA BU MODUL BOR
═══════════════════════════════════════════════════════════════
S-44 gacha bir xil qoida UCH JOYDA takrorlangan edi:
  • `api/routers/norms.py::can_manage_norms`
  • `api/deps.py::scoped_user_ids`
  • `api/routers/payroll.py::can_view_payroll`

Uchalasi ham «`manager_id` MENMI yoki lavozim mening ROLIMNI
ko'rsatganmi?» deb tekshirardi. Bitta joyda qoida o'zgarsa
qolgan ikkitasi ESKI qoidada qolib ketardi va xodim bir modulda
ko'rinib, boshqasida ko'rinmasdi — buni topish juda qiyin, chunki
har bir modul alohida to'g'ri ishlayotgandek tuyuladi.

═══════════════════════════════════════════════════════════════
⚠️ IKKI MANBA VA ULARNING TARTIBI
═══════════════════════════════════════════════════════════════
1. `users.manager_id` — ODAM darajasidagi ierarxiya. ASOSIY manba.
   Endi ZANJIR bo'ylab hisoblanadi: rahbarimning rahbari ham meni
   boshqaradi. Ilgari faqat BEVOSITA rahbar tekshirilardi, ya'ni
   ikki bo'g'in yuqoridagi rahbar «begona» edi.

2. `positions.managed_by_roles` — LAVOZIM darajasidagi ISTISNO.
   TZ: «faqat rol darajasidagi istisno uchun qolsin».

   ⚠️ ISTISNO OLIB TASHLANMADI va olib tashlanmasligi kerak.
   2026-08-24 dagi JONLI o'lchov: 14 faol xodimning HECH BIRIDA
   `manager_id` yo'q va faol `rop` roli ham yo'q. Ya'ni bugun
   butun huquq modeli AYNAN shu istisnoga tayanadi. Uni olib
   tashlash HR ni butun tizimdan uzib qo'yardi.

   Shuning uchun tartib: avval IERARXIYA, u javob bermasa
   ISTISNO. Ierarxiya to'ldirilgani sayin istisnoning roli
   o'z-o'zidan kamayadi — bir kunda emas, bosqichma-bosqich.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Role, User

#  ⚠️ Ikkinchi to'siq — halqa qo'riqchisi bo'lsa ham. `manager_id`
#  qo'lda tahrirlanishi mumkin (A→B→A) va o'sha paytda zanjir
#  bo'ylab yurish CHEKSIZ aylanardi. Passenger'da konkurentlik = 1,
#  ya'ni bitta osilgan so'rov BUTUN saytni to'xtatadi.
MAX_DEPTH = 50

#  Hamma joyda ko'radigan/boshqaradigan rollar.
FULL_ACCESS_ROLES = (Role.boss.value, Role.dasturchi.value)

#  ⚠️ BOSHQARUV QOBILIYATI BO'LGAN ROLLAR. Ierarxiya KIMGA nisbatan
#  huquq borligini belgilaydi, ROL esa umuman boshqaruvchi ekanini.
#
#  NEGA IKKALASI KERAK: `manager_id` ni HR qo'yadi. Agar ierarxiya
#  yolg'iz o'zi huquq bersa, oddiy xodimni boshqa xodimga rahbar
#  qilib qo'yish unga JIMGINA norma qo'yish huquqini berardi — ya'ni
#  kadrlar maydonini tahrirlash ruxsat darajasini oshirardi.
#  Bu S-44 da ESKI/YANGI mantiqni solishtirganda topildi: 900
#  kombinatsiyadan 10 tasi aynan shu tarzda farq qilgan edi.
MANAGING_ROLES = (
    Role.hr.value,
    Role.rop.value,
    Role.boss.value,
    Role.dasturchi.value,
)


def _chain_from_map(
    manager_of: dict[int, int | None], user_id: int
) -> set[int]:
    """Bitta xodimning BARCHA rahbarlari (bevositadan yuqoriga).

    ⚠️ Halqa va chuqurlik qo'riqchisi bilan — bazada A→B→A bo'lsa
    ham funksiya qaytadi, cheksiz aylanmaydi."""
    zanjir: set[int] = set()
    joriy = manager_of.get(user_id)
    qadam = 0
    while joriy is not None and joriy not in zanjir and qadam < MAX_DEPTH:
        zanjir.add(joriy)
        joriy = manager_of.get(joriy)
        qadam += 1
    return zanjir


async def _manager_map(db: AsyncSession) -> dict[int, int | None]:
    """`user_id -> manager_id` — BITTA so'rov.

    ⚠️ Zanjirni bazada rekursiv so'rov bilan yurish ham mumkin edi,
    lekin xodimlar soni kichik (o'nlab) va bitta `SELECT` arzonroq.
    Muhimi: N ta xodim uchun N ta so'rov QILINMAYDI."""
    return {
        row[0]: row[1]
        for row in await db.execute(select(User.id, User.manager_id))
    }


async def chain_ids(db: AsyncSession, user_id: int) -> set[int]:
    """Shu xodimni boshqaradigan BARCHA rahbarlar (zanjir bo'ylab)."""
    return _chain_from_map(await _manager_map(db), user_id)


async def chain_map(db: AsyncSession, user_ids: list[int]) -> dict[int, set[int]]:
    """Ko'p xodim uchun zanjirlar — BITTA so'rov bilan.

    Ro'yxat sahifalari uchun: har xodimga alohida so'rov yuborilsa
    50 xodimli sahifa 50 ta so'rov qilardi."""
    xarita = await _manager_map(db)
    return {uid: _chain_from_map(xarita, uid) for uid in user_ids}


def role_exception(actor: User, target: User) -> bool:
    """LAVOZIM darajasidagi istisno: «bu lavozimni falon rol boshqaradi».

    ⚠️ Bu ISTISNO, asosiy qoida emas (modul izohiga qarang). Ierarxiya
    javob bermagandagina ishlatiladi."""
    position = target.position
    return bool(
        position
        and position.managed_by_roles
        and actor.role in position.managed_by_roles
    )


def is_orphan(target: User) -> bool:
    """«Yetim» xodim: na rahbari, na boshqaruvchi-rolli lavozimi bor.

    Bunday xodimni na ierarxiya, na istisno qamrab oladi — u
    zaxira sifatida HR ga biriktiriladi, aks holda uni faqat
    Boshliq/Dasturchi ko'rardi."""
    position = target.position
    return target.manager_id is None and not (
        position and position.managed_by_roles
    )


def manages_with_chain(actor: User, target: User, chain: set[int]) -> bool:
    """Boshqaruv huquqi — YAGONA QOIDA (zanjir oldindan hisoblangan).

    Tartib ATAYLAB shunday:
      1. Boshliq/Dasturchi — hamma joyda;
      2. IERARXIYA — actor target ning rahbarlar zanjirida bormi;
      3. ROL ISTISNOSI — lavozim shu rolni ko'rsatganmi;
      4. HR zaxirasi — «yetim» xodim.

    ⚠️ 2-band YANGI: ilgari faqat BEVOSITA rahbar («manager_id ==
    actor.id») tekshirilardi. Endi zanjir bo'ylab — rahbarimning
    rahbari ham meni boshqaradi. Bu KENGAYTIRISH, ya'ni ilgari
    ruxsat berilgan holatlar hamon ruxsat etiladi."""
    if actor.role in FULL_ACCESS_ROLES:
        return True
    #  ⚠️ Boshqaruvchi bo'lmagan rol bu yerdan NARIGA O'TMAYDI —
    #  ierarxiya ham, istisno ham unga huquq bermaydi (yuqoridagi
    #  `MANAGING_ROLES` izohiga qarang).
    if actor.role not in MANAGING_ROLES:
        return False
    if actor.id in chain:
        return True
    if role_exception(actor, target):
        return True
    if actor.role == Role.hr.value and is_orphan(target):
        return True
    return False


async def manages(db: AsyncSession, actor: User, target: User) -> bool:
    """`manages_with_chain` ning bitta xodim uchun qulay ko'rinishi."""
    return manages_with_chain(actor, target, await chain_ids(db, target.id))


async def subordinate_ids(db: AsyncSession, manager_id: int) -> set[int]:
    """Shu rahbarga (zanjir bo'ylab) bo'ysunadigan BARCHA xodimlar.

    ⚠️ Bevosita bo'ysunuvchilar EMAS — butun shox. Rahbarning
    rahbari ham butun shoxni ko'rishi kerak."""
    xarita = await _manager_map(db)
    return {
        uid
        for uid in xarita
        if uid != manager_id and manager_id in _chain_from_map(xarita, uid)
    }
