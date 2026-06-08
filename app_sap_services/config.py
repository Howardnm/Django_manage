"""
SAP 连接配置 — 从 Django settings 读取。
"""
from dataclasses import dataclass, field
from typing import Dict
from django.conf import settings
from .exceptions import SAPConfigError


@dataclass
class SAPConfig:
    """SAP 连接配置数据类"""

    sap_lib_path: str
    ashost: str
    sysnr: str
    client: str
    user: str
    passwd: str
    lang: str = 'ZH'
    max_idle_seconds: int = 300
    max_retries: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_django_settings(cls) -> 'SAPConfig':
        cfg = getattr(settings, 'SAP_SERVICES_CONFIG', None)
        if not cfg:
            raise SAPConfigError(
                "Django settings 中缺少 SAP_SERVICES_CONFIG 配置。\n"
                "请在 settings.py 中添加 SAP_SERVICES_CONFIG 字典。"
            )
        conn = cfg.get('connection', {})
        return cls(
            sap_lib_path=cfg['sap_lib_path'],
            ashost=conn['ashost'],
            sysnr=conn['sysnr'],
            client=conn['client'],
            user=conn['user'],
            passwd=conn['passwd'],
            lang=conn.get('lang', 'ZH'),
            max_idle_seconds=cfg.get('max_idle_seconds', 300),
            max_retries=cfg.get('max_retries', 3),
            retry_delay=cfg.get('retry_delay', 1.0),
        )

    def to_connection_params(self) -> Dict[str, str]:
        return {
            'ashost': self.ashost,
            'sysnr': self.sysnr,
            'client': self.client,
            'user': self.user,
            'passwd': self.passwd,
            'lang': self.lang,
        }
