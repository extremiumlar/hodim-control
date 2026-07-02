import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CRM_TYPE = os.getenv("CRM_TYPE", "none")
CRM_API_KEY = os.getenv("CRM_API_KEY", "")
CRM_WEBHOOK_SECRET = os.getenv("CRM_WEBHOOK_SECRET", "")
CRM_AMOCRM_SUBDOMAIN = os.getenv("CRM_AMOCRM_SUBDOMAIN", "")
