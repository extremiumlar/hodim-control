from crm.base import CRMAdapter


def get_crm_adapter(crm_type: str) -> CRMAdapter | None:
    """CRM_TYPE konfiguratsiyasiga qarab mos adapterni qaytaradi.
    Boshqa CRM qo'shilganda faqat shu funksiyaga bitta `elif` qo'shish kifoya."""
    if crm_type == "amocrm":
        from crm.amocrm import AmoCRMAdapter

        return AmoCRMAdapter()
    if crm_type == "onec":
        from crm.onec import OneCAdapter

        return OneCAdapter()
    if crm_type == "uysot":
        from crm.uysot import UysotAdapter

        return UysotAdapter()
    return None
