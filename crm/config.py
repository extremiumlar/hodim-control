import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CRM_TYPE = os.getenv("CRM_TYPE", "none")
CRM_API_KEY = os.getenv("CRM_API_KEY", "")
CRM_WEBHOOK_SECRET = os.getenv("CRM_WEBHOOK_SECRET", "")
CRM_AMOCRM_SUBDOMAIN = os.getenv("CRM_AMOCRM_SUBDOMAIN", "")
# Uysot pipeline'idagi "Tashrif" bosqichining pipeStatusId'si (Uysot dashboard'ida
# sozlanadi, hisobdan hisobga farq qiladi). Bo'sh bo'lsa — tashriflar hisoblanmaydi (0).
CRM_UYSOT_VISIT_PIPE_STATUS_ID = os.getenv("CRM_UYSOT_VISIT_PIPE_STATUS_ID", "")
# Operator AI sabab tekshiruvi uchun: "hali ishlanmagan/ochiq lid" deb hisoblanadigan
# bosqich ID'lari (vergul bilan, masalan "101,102"). Operator "lid tugadi" desa, shu
# bosqichlarda unga biriktirilgan lidlar CRM'dan sanaladi. Bo'sh — tekshiruv o'chiq.
CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS = [
    int(x) for x in os.getenv("CRM_UYSOT_OPEN_LEAD_PIPE_STATUS_IDS", "").replace(";", ",").split(",")
    if x.strip().isdigit()
]
# Issiq lid: lid qo'ng'iroqsiz, lekin QONUNIY sabab bilan yopilgan bo'lishi mumkin
# (spam/dublikat/noto'g'ri raqam va h.k.) — shu holatda eskalatsiya davom etishi
# noto'g'ri. Bu bosqich ID'lariga tushgan lid "resolved_no_call" deb belgilanadi,
# eskalatsiya to'xtaydi. Bo'sh — funksiya o'chiq (xatti-harakat o'zgarmaydi).
# Sizning Uysot voronkangizdagi mos bosqich ID'larini (Rad etildi/Spam/Noto'g'ri
# raqam va h.k.) shu yerga to'ldiring — /pipe/all javobidan yoki dashboard'dan.
CRM_UYSOT_HOT_LEAD_TERMINAL_PIPE_STATUS_IDS = [
    int(x) for x in os.getenv("CRM_UYSOT_HOT_LEAD_TERMINAL_PIPE_STATUS_IDS", "").replace(";", ",").split(",")
    if x.strip().isdigit()
]

# Diff-engine (kunlik statistika, lead_diff.py): chegaralangan tez skan qancha
# kun orqaga yaratilgan lidlarni qamrab olishi kerak — undan eskilari kamdan-kam
# faol bo'ladi. Tungi to'liq solishtiruv (reconcile) baribir BUTUN bazani
# qamraydi, shuning uchun bu faqat tezkor skanning kengligi.
#
# Standart 30 kun — jonli tekshiruvda (2026-07-21) o'lchandi: 14 kun/920 lid/33s,
# 30 kun/1762 lid/63s, 60 kun/2722 lid/97s, 180 kun/7456 lid/270s. LEAD_DIFF_
# INTERVAL_MINUTES (5 daqiqa) ichiga bemalol sig'ishi uchun 30 kun tanlandi;
# kattaroq qilsangiz interval ham kattalashtirilishi kerak (scheduler/config.py).
CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS = int(os.getenv("CRM_UYSOT_LEAD_DIFF_LOOKBACK_DAYS", "30"))
