from django.dispatch import Signal

# 流程启动信号
# 提供参数: instance (WorkflowInstance)
workflow_started = Signal()

# 任务创建信号 (待办任务生成时)
# 提供参数: task (WorkflowTask)
task_created = Signal()

# 任务完成信号 (通过或驳回)
# 提供参数: task (WorkflowTask), user (User), action (APPROVE/REJECT)
task_completed = Signal()

# 流程结束信号 (整个流程实例完成或终止)
# 提供参数: instance (WorkflowInstance), status (COMPLETED/REJECTED/CANCELED)
workflow_completed = Signal()

# 任务退回信号 (审批任务被回退到前序节点)
# 提供参数: task (WorkflowTask), user (User), target_task (WorkflowTask)
task_returned = Signal()
