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


class SAPBusinessError(SAPError):
    """
    SAP 业务错误：RFC 调用本身成功（无通信异常），但 SAP 返回 E/A 级业务消息。

    与 SAPResultParseError 的区别：后者是结构性的（返回的 payload 形状不对），
    本异常是业务性的（payload 完全合法，但 SAP 明确拒绝了这次查询，
    例如「工厂不存在」「无授权」）。上层据此可区分「该修参数」与「该改代码」。
    """

    def __init__(self, function: str, messages: list = None):
        self.function = function
        self.messages = list(messages or [])
        first = self.messages[0] if self.messages else None
        self.rtype = first.type if first else ""
        self.rtmsg = first.text if first else ""
        text = "; ".join(str(m) for m in self.messages) or "SAP 返回错误"
        super().__init__(f"[{function}] {text}")


class DoesNotExist(SAPError):
    """查询结果为空（用于 get() 方法）"""
    pass


class MultipleObjectsReturned(SAPError):
    """查询结果多于一条（用于 get() 方法）"""
    pass
