class SapConnectionError(Exception):
    """SAP连接异常"""


class SapRfcError(Exception):
    """RFC调用异常"""


class SapConfigError(Exception):
    """SAP配置异常"""


class SapTimeoutError(Exception):
    """RFC调用超时"""
