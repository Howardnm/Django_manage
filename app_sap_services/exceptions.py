"""
SAP 服务模块异常层次结构。
所有异常继承自 SAPError，调用方可按需捕获特定子类。
"""


class SAPError(Exception):
    """SAP 服务模块所有异常的基类"""
    pass


class SAPConfigError(SAPError):
    """配置错误：缺少必要配置项、SDK 路径不存在等"""
    pass


class SAPConnectionError(SAPError):
    """连接错误：无法建立连接、连接断开、超时等"""
    pass


class SAPRfcError(SAPError):
    """RFC 调用错误：RFC 函数返回错误信息"""

    def __init__(self, function: str, message: str, params: dict = None):
        self.function = function
        self.params = params or {}
        # 截断参数值避免日志过长
        brief = {k: str(v)[:200] for k, v in self.params.items()}
        super().__init__(f"[{function}] {message}\nparams: {brief}")


class SAPFilterError(SAPError):
    """过滤条件构建错误：无效的 OPTION、缺少必要字段等"""
    pass


class SAPResultParseError(SAPError):
    """结果解析错误：返回格式不符合预期"""
    pass
