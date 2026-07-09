from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from lxml import etree
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
    canceled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="canceled_workflows",
        verbose_name="取消人"
    )
    cancel_reason = models.TextField("取消原因", blank=True, default="")

    class Meta:
        verbose_name = "流程实例"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.definition.name} - {self.get_status_display()} ({self.started_at.strftime('%Y-%m-%d %H:%M')})"

    # ── 模板辅助属性 ──────────────────────────────────────────

    @property
    def status_css_class(self):
        """状态徽章 CSS 类名"""
        return {
            'RUNNING': 'bg-primary',
            'COMPLETED': 'bg-success',
            'REJECTED': 'bg-danger',
            'CANCELED': 'bg-secondary',
        }.get(self.status, 'bg-secondary')

    def is_cancelable_by(self, user):
        """判断当前用户是否可取消此流程"""
        return self.status == 'RUNNING' and (
            self.started_by == user or user.is_superuser
        )

    @property
    def returnable_tasks(self):
        """返回可被退回的目标任务列表（所有已完成的前序任务）"""
        return list(self.tasks.filter(
            status__in=['COMPLETED', 'RETURNED']
        ).select_related('assigned_to').order_by('created_at'))


class WorkflowTask(models.Model):
    """流程任务：分配给具体用户的待办事项"""
    STATUS_CHOICES = [
        ('PENDING', '待处理'),
        ('COMPLETED', '已通过'),
        ('REJECTED', '已驳回'),
        ('RETURNED', '已退回'),
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
    
    # 表单分步填写：该任务对应表单的哪个步骤（从 camunda:formStep 解析）
    form_step = models.PositiveSmallIntegerField("表单步骤号", null=True, blank=True)

    # BPMN 元素 ID (task_spec.bpmn_id)
    spiff_task_id = models.CharField("BPMN任务ID", max_length=100, db_index=True)
    
    # SpiffWorkflow 内部任务实例 ID (唯一标识每个运行中的任务，支持多实例)
    spiff_instance_id = models.CharField("Spiff任务实例ID", max_length=100, db_index=True, unique=True, null=True, blank=True)
    
    due_date = models.DateTimeField("截止日期", null=True, blank=True)
    remark = models.TextField("审批备注", blank=True, null=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    completed_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "流程任务"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=['status', 'assigned_to'], name='wf_task_status_assignee_idx'),
        ]

    @property
    def display_name(self):
        """从 BPMN XML 解析 userTask 的 name 属性作为显示名称。"""
        try:
            nsmap = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}
            root = etree.fromstring(self.instance.definition.bpmn_xml.encode('utf-8'))
            for ut in root.xpath('//bpmn:userTask', namespaces=nsmap):
                if ut.get('id') == self.spiff_task_id:
                    return ut.get('name') or self.task_name
        except Exception:
            pass
        return self.task_name

    def __str__(self):
        if self.assigned_to:
            return f"{self.display_name} - {self.assigned_to.username}"
        elif self.candidate_users.exists() or self.candidate_groups:
            return f"{self.display_name} - 待签收"
        return f"{self.display_name} - 未指派"

    @property
    def returnable_targets(self):
        """当前任务可退回的前序任务列表，按 BPMN 节点去重，始终包含发起人"""
        raw = WorkflowTask.objects.filter(
            instance=self.instance,
            status='COMPLETED',
            created_at__lt=self.created_at,
        ).select_related('assigned_to').order_by('created_at')
        seen = {}
        for t in raw:
            seen[t.spiff_task_id] = t
        targets = sorted(seen.values(), key=lambda t: t.created_at)
        return [{
            'pk': 0,
            'display_name': '发起人（重新填写）',
            'assigned_to': self.instance.started_by,
            'is_initiator': True,
        }] + [{
            'pk': t.pk,
            'display_name': t.display_name,
            'assigned_to': t.assigned_to,
            'is_initiator': False,
        } for t in targets]

    # ── 模板辅助属性 ──────────────────────────────────────────

    @property
    def pending_days(self):
        """待处理天数（仅 PENDING 状态有效）"""
        if self.status != 'PENDING' or not self.created_at:
            return 0
        from django.utils import timezone
        delta = timezone.now() - self.created_at
        return max(1, delta.days)

    @property
    def status_css_class(self):
        """状态徽章 CSS 类名"""
        return {
            'PENDING': 'bg-primary',
            'COMPLETED': 'bg-success',
            'REJECTED': 'bg-danger',
            'RETURNED': 'bg-warning',
            'CANCELED': 'bg-secondary',
        }.get(self.status, 'bg-secondary')


class ApprovalHistory(models.Model):
    """审批历史：记录所有的操作轨迹"""
    ACTION_CHOICES = [
        ('START', '流程发起'),
        ('APPROVE', '审批通过'),
        ('REJECT', '审批驳回'),
        ('RETURN', '退回重审'),
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
    return_target_task = models.ForeignKey(
        WorkflowTask,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='returned_from',
        verbose_name='退回到任务'
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


class WorkflowTaskConfig(models.Model):
    """BPMN userTask 节点配置注册表。关联 task_id 与组织角色，实现审批人自动解析。

    所有字段在 Admin 中均可自由编辑。task_id 是用户自主命名的标识符，
    需要在 BPMN XML 的 userTask id 属性中保持一致。

    完整配置流程：
        ① 先在 app_user →「组织角色」中定义角色（如：组长、部门经理）
        ② 再到 app_user →「组织角色指派」中将人员指派到具体组织单元
        ③ 最后在此处创建 Task 节点配置，关联 task_id 与组织角色
        ④ 在 BPMN 编辑器中将 userTask 的 id 设为相同的 task_id
    """

    class ResolutionMode(models.TextChoices):
        ASSIGNEE_MAP = 'assignee_map', '① 动态指派 — 由代码层在启动流程时传入具体审批人'
        ORG_ROLE = 'org_role', '② 按组织角色自动查找 — 根据发起人的工作组/部门/子公司自动匹配'
        STATIC_GROUP = 'static_group', '③ 静态候选组 — 使用固定的审核组，组成员签收任务'
        STATIC_USER = 'static_user', '④ 静态指派用户 — 指定固定的审批人（与组织架构无关）'

    task_id = models.CharField(
        "Task ID", max_length=100, unique=True,
        help_text=(
            "① 自由命名的节点标识符，用于关联 BPMN XML 中的 userTask。\n"
            "② #命名建议：使用有意义的英文标识，如 'Task_group_leader_approval'、'Task_dept_manager_review'。\n"
            "③ 修改此字段后，请同步更新 BPMN XML 中对应 userTask 的 id 属性。\n"
            "④ #操作指引：先在纸上规划好审批链中每个节点的名称，再逐个在此创建配置。"
        ))
    display_name = models.CharField(
        "显示名称", max_length=100,
        help_text=(
            "① 在 Admin 列表和任务详情中展示的可读名称。\n"
            "② 例如：'组长审批'、'部门经理审批'、'基地总经理审批'。"
        ))
    resolution_mode = models.CharField(
        "审批人解析模式", max_length=20,
        choices=ResolutionMode.choices, default=ResolutionMode.ORG_ROLE,
        help_text=(
            "① 决定引擎如何为这个节点查找审批人。\n"
            "② ★ 推荐：'按组织角色自动查找' — 零代码，人员变动只需修改组织角色指派。\n"
            "③ '静态候选组' — 适合固定审核组场景（如法务审核组、财务审核组）。\n"
            "④ '动态指派' — 适合审批人需要由业务代码动态计算的场景。"
        ))

    # org_role 模式专属
    org_role = models.ForeignKey(
        'app_user.OrgRole', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="绑定的组织角色",
        help_text=(
            "① ★ 当解析模式为「按组织角色自动查找」时必填。\n"
            "② 选择该节点对应的组织角色（如：组长、部门经理）。\n"
            "③ 引擎运行时会根据发起人的组织归属，自动查找该角色在对应层级中的负责人。\n"
            "④ #操作指引：先在 app_user →「组织角色」中创建角色，再回到此处选择。"
        ))

    # static_group 模式专属
    review_group = models.ForeignKey(
        'app_user.ReviewGroup', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="候选审核组",
        help_text=(
            "① 当解析模式为「静态候选组」时必填。\n"
            "② 选择固定的审核组。该组成员将收到候选任务，需要主动签收。\n"
            "③ #操作指引：先在 app_user →「[审批] 审核组」中创建审核组并添加成员。"
        ))

    # static_user 模式专属
    static_assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="固定审批人",
        help_text=(
            "① 当解析模式为「静态指派用户」时必填。\n"
            "② 选择一个固定用户作为该节点的审批人，与发起人的组织归属无关。\n"
            "③ #适用场景：某个审批节点永远由同一个人处理（如总经理最终审批）。\n"
            "④ #操作指引：只有在审批人绝对固定、不随组织架构变化时才使用此模式。"
        ))

    # 关联的工作流定义
    workflow_definitions = models.ManyToManyField(
        'WorkflowDefinition', blank=True, verbose_name="所属流程定义",
        help_text=(
            "① 可选。关联此 task_id 被哪些流程定义使用。\n"
            "② 用于在 Admin 中快速查看某个流程包含哪些审批节点。\n"
            "③ 不填不影响引擎运行（引擎只按 task_id 精确匹配）。"
        ))

    description = models.TextField(
        "说明", blank=True,
        help_text="可选。详细描述该节点的审批职责、审批要点或注意事项。")
    is_active = models.BooleanField(
        "启用", default=True,
        help_text=(
            "① 取消勾选后，该配置将不再生效，引擎会跳过此模式回退到 BPMN 属性解析。\n"
            "② 用于临时禁用某个节点的组织角色配置，而非直接删除。"
        ))
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "Task 节点配置"
        verbose_name_plural = "Task 节点配置"
        ordering = ['task_id']

    def __str__(self):
        return f"{self.task_id} — {self.display_name}"
