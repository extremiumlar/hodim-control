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
