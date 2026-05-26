class WorkflowError(Exception):
    """工作流引擎通用异常基类"""


class WorkflowParseError(WorkflowError):
    """BPMN XML 解析失败"""


class TaskNotFoundError(WorkflowError):
    """未找到匹配的可执行任务"""


class InvalidActionError(WorkflowError):
    """无效的审批动作"""


class CancelNotAllowedError(WorkflowError):
    """流程不允许取消 (已结束或状态不允许)"""
