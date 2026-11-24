"""إعدادات التطبيق تُقرأ من متغيرات البيئة."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    verify_token: str        # رمز التحقق الذي تدخله في إعدادات Webhook في Meta
    app_secret: str          # App Secret من تطبيق Meta، يُستخدم للتحقق من توقيع الطلبات
    whatsapp_token: str      # رمز الوصول الدائم لـ WhatsApp Cloud API
    phone_number_id: str     # معرّف رقم WhatsApp Business
    manager_phone: str       # رقم المدير بصيغة دولية بدون +
    db_path: str             # مسار ملف SQLite
    graph_version: str       # إصدار Graph API
    port: int                # منفذ الخادم
    auto_reply: bool         # هل يرد الوكيل تلقائياً على الزبناء الجدد


def load_settings() -> Settings:
    return Settings(
        verify_token=os.environ.get("WHATSAPP_VERIFY_TOKEN", ""),
        app_secret=os.environ.get("META_APP_SECRET", ""),
        whatsapp_token=os.environ.get("WHATSAPP_TOKEN", ""),
        phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
        manager_phone=os.environ.get("MANAGER_PHONE", ""),
        db_path=os.environ.get("DB_PATH", "wassata.db"),
        graph_version=os.environ.get("GRAPH_VERSION", "v21.0"),
        port=int(os.environ.get("PORT", "8000")),
        auto_reply=os.environ.get("AUTO_REPLY", "true").lower() == "true",
    )
