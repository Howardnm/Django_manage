"""
SAP 返回消息（E_RTYPE / E_RTMSG 与 BAPIRET2 表）的识别与分级。

不少 Z 开头的 RFC 在调用成功时也会通过 Export 参数回传一个业务消息，
典型形态是 E_RTYPE（类型）+ E_RTMSG（文本）。RfcSchema 子类声明
msg_type_field / msg_text_field 后，parse_response 会自动检查：
E（错误）与 A（终止）级消息抛 SAPBusinessError，W（警告）记日志。

为什么需要它：这类 RFC 的业务错误不会抛异常，若不检查就会被当成
「查询结果为空」，让上层无法区分「真的没有数据」和「SAP 拒绝了这次查询」。
"""

from dataclasses import dataclass

# 消息类型 → 处理级别（SAP 标准：S 成功, E 错误, W 警告, I 信息, A 终止）
FATAL_TYPES = ("E", "A")        # 抛出 SAPBusinessError
WARN_TYPES = ("W",)             # 记 warning 日志，不抛


def normalize_type(value) -> str:
    """
    归一化消息类型为标准单字符。

    容忍 SAP 侧的各种写法：'e' / 'E ' / 'error' → 'E'。

    Args:
        value: 原始消息类型值（str / None / 其他）

    Returns:
        单个大写字符；空值返回空串
    """
    if value is None:
        return ""
    s = str(value).strip().upper()
    return s[:1] if s else ""


@dataclass(frozen=True)
class SapMessage:
    """单条 SAP 业务消息。

    Attributes:
        type: 归一化后的消息类型（S/E/W/I/A 或空串）。
        text: 消息文本。
        source: 消息来源的字段名或表名，便于定位。
    """

    type: str
    text: str
    source: str = ""

    @property
    def is_fatal(self) -> bool:
        """是否属于会中止流程的错误级消息。"""
        return self.type in FATAL_TYPES

    def __str__(self):
        return f"[{self.type or '?'}] {self.text}"
