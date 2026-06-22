"""
向后兼容模块 — 实际实现已迁移至 common_utils.state_machine。
所有现有 import 路径在此过渡期间继续有效。
"""
from common_utils.state_machine import StateMachine, InvalidStateTransition  # noqa: F401
