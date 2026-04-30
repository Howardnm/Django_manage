from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import re


class WorkflowDefinition(models.Model):
    """流程定义：存储 BPMN XML 配置"""
    name = models.CharField("流程名称", max_length=100)
    description = models.TextField("流程描述", blank=True)
    bpmn_xml = models.TextField("BPMN XML 内容")
    is_active = models.BooleanField("是否启用", default=True)
    
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name="创建者"
    )

    class Meta:
        verbose_name = "流程定义"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name

    @property
    def is_executable_bpmn(self):
        """
        判断 BPMN XML 中是否包含可执行的流程定义。
        使用简单的正则表达式进行初步判断，避免每次列表加载都进行完整的 XML 解析。
        """
        if not self.bpmn_xml:
            return False
        # 寻找包含 isExecutable="true" 的 process 标签
        return bool(re.search(r'<[^>]*process[^>]*isExecutable="true"', self.bpmn_xml))


class WorkflowInstance(models.Model):
    """流程实例：记录运行中的流程状态"""
    STATUS_CHOICES = [
        ('RUNNING', '运行中'),
        ('COMPLETED', '已完成'),
        ('REJECTED', '已拒绝'),
        ('CANCELED', '已取消'),
    ]

    definition = models.ForeignKey(
        WorkflowDefinition, 
        on_delete=models.CASCADE, 
        related_name="instances",
        verbose_name="所属流程"
    )
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='RUNNING')
    
    # 上下文数据，用于存储流程变量
    context_data = models.JSONField("上下文数据", default=dict, blank=True)
    # 存储 SpiffWorkflow 序列化后的状态数据，用于恢复流程进度
    spiff_workflow_data = models.JSONField("Spiff状态数据", null=True, blank=True)
    
    # 回调配置，用于流程完成或驳回时回调业务模块
    callback_config = models.JSONField("回调配置", default=dict, blank=True)

    # 关联业务对象 (使用 GenericForeignKey 实现通用审批)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="started_workflows",
        verbose_name="发起人"
    )
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    completed_at = models.DateTimeField("结束时间", null=True, blank=True)

    class Meta:
        verbose_name = "流程实例"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.definition.name} - {self.get_status_display()} ({self.started_at.strftime('%Y-%m-%d %H:%M')})"


class WorkflowTask(models.Model):
    """流程任务：分配给具体用户的待办事项"""
    STATUS_CHOICES = [
        ('PENDING', '待处理'),
        ('COMPLETED', '已通过'),
        ('REJECTED', '已驳回'),
        ('CANCELED', '已取消'),
    ]

    instance = models.ForeignKey(
        WorkflowInstance, 
        on_delete=models.CASCADE, 
        related_name="tasks",
        verbose_name="所属实例"
    )
    task_name = models.CharField("任务名称", max_length=100)
    
    # assigned_to 允许为空，因为任务可能先分配给候选人/组，再由用户签收
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, # 允许为空
        related_name="workflow_tasks",
        verbose_name="负责人"
    )
    
    # 【新增】候选用户 (多对多关系)
    candidate_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        related_name="candidate_workflow_tasks",
        blank=True,
        verbose_name="候选用户"
    )
    # 【新增】候选组 (存储组名列表，或关联到自定义的 Group 模型)
    candidate_groups = models.JSONField("候选组", default=list, blank=True)

    status = models.CharField("任务状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # BPMN 元素 ID (task_spec.bpmn_id)
    spiff_task_id = models.CharField("BPMN任务ID", max_length=100, db_index=True)
    
    # SpiffWorkflow 内部任务实例 ID (唯一标识每个运行中的任务，支持多实例)
    spiff_instance_id = models.CharField("Spiff任务实例ID", max_length=100, db_index=True, unique=True, null=True, blank=True)
    
    remark = models.TextField("审批备注", blank=True, null=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "流程任务"
        verbose_name_plural = verbose_name

    def __str__(self):
        if self.assigned_to:
            return f"{self.task_name} - {self.assigned_to.username}"
        elif self.candidate_users.exists() or self.candidate_groups:
            return f"{self.task_name} - 待签收"
        return f"{self.task_name} - 未指派"


class ApprovalHistory(models.Model):
    """审批历史：记录所有的操作轨迹"""
    ACTION_CHOICES = [
        ('START', '流程发起'),
        ('APPROVE', '审批通过'),
        ('REJECT', '审批驳回'),
        ('CANCEL', '流程取消'),
    ]

    instance = models.ForeignKey(
        WorkflowInstance, 
        on_delete=models.CASCADE, 
        related_name="history",
        verbose_name="所属实例"
    )
    task = models.ForeignKey(
        WorkflowTask, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="关联任务"
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        verbose_name="操作人"
    )
    action = models.CharField("操作类型", max_length=20, choices=ACTION_CHOICES)
    remark = models.TextField("操作备注", blank=True, null=True)
    timestamp = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        verbose_name = "审批历史"
        verbose_name_plural = verbose_name
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.instance.definition.name} - {self.get_action_display()} by {self.approver.username}"
