"""测试辅助：不连真实 SAP 的假连接管理器。

FakeConnMgr 模拟 ConnectionManager.call_rfc 返回预先给定的原始响应，
用于对 SAPGateway / RfcQuery / parse_response 做纯本地回归测试。
"""

from typing import Any, Dict, List, Tuple


class FakeConnMgr:
    """记录调用参数并返回固定原始响应的假连接管理器。"""

    def __init__(self, raw_response: Dict[str, Any] = None, responses: List[Dict[str, Any]] = None):
        self.raw_response = raw_response or {}
        # 按调用顺序逐个返回。用完后回到 raw_response。
        self.responses = list(responses) if responses else []
        # (function_name, params) 调用记录
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.closed = 0

    def call_rfc(self, function_name: str, **params):
        self.calls.append((function_name, params))
        if self.responses:
            return self.responses.pop(0)
        return self.raw_response

    def close(self):
        self.closed += 1