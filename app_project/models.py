# Create your models here.
from django.db import models
from django.conf import settings
from django.utils.text import Truncator  # 导入文字截断器
from django.db import transaction  # 用于事务处理，保证排序修改的安全性
from django.utils.functional import cached_property  # 引入缓存装饰器


# 1. 定义标准流程阶段 (枚举) - 这相当于"类型库"
class ProjectStage(models.TextChoices):
    INIT = 'INIT', '① 项目立项'
    COLLECT = 'COLLECT', '② 收集资料'
    FEASIBILITY = 'FEASIBILITY', '③ 可行性评估'
    PRICING = 'PRICING', '④ 客户定价'
    RND = 'RND', '⑤ 研发阶段'  # 可能多次
    PILOT = 'PILOT', '⑥ 客户小试'  # 可能多次
    MID_TEST = 'MID_TEST', '⑦ 客户中试'  # 可能多次
    MASS_PROD = 'MASS_PROD', '⑧ 客户量产下单'
    ORDER = 'ORDER', '⑨ 开发周期完成'
    FEEDBACK = 'FEEDBACK', '🎗️客户意见'


# 2. 项目基本信息共享字段 — 抽象基类
class AbstractProjectFields(models.Model):
    """Project 与 ProjectFieldChange 共享的业务字段，不创建数据库表"""
    code = models.CharField("项目编码", max_length=50, blank=True)
    name = models.CharField("项目名称", max_length=100)
    grade = models.ForeignKey('app_repository.GradeFactor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="项目等级")
    material = models.ForeignKey('app_material.MaterialLibrary', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用成品材料")
    description = models.TextField("项目描述", blank=True)

    class Meta:
        abstract = True


# 3. 项目主体模型
class Project(AbstractProjectFields):
    # 覆盖基类字段：添加 unique 约束
    code = models.CharField("项目编码", max_length=50, unique=True, blank=True, help_text="唯一项目编码，留空则自动生成")
    # 覆盖基类字段：保留已有 related_name
    material = models.ForeignKey('app_material.MaterialLibrary', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用成品材料", related_name='projects')

    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="项目负责人")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    # 进度冗余字段
    current_stage = models.CharField("当前阶段", max_length=20, choices=ProjectStage.choices, default=ProjectStage.INIT)
    progress_percent = models.PositiveIntegerField("进度百分比", default=0)
    is_terminated = models.BooleanField("是否终止", default=False)
    latest_remark = models.CharField("最新进展", max_length=200, blank=True, help_text="自动同步当前活跃节点的备注")

    # 项目质量分冗余字段 (用于绩效统计性能优化)
    quality_score = models.DecimalField("项目研发质量得分", max_digits=5, decimal_places=2, default=0.00)
    # 销售质量分（独立评定标准）
    sales_quality_score = models.DecimalField("项目销售质量得分", max_digits=5, decimal_places=2, default=0.00)

    # 【联动工作流】默认审批流程（项目节点提交）
    approval_workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="默认审批流程")
    # 【联动工作流】活跃的项目信息变更审批流程（并发门控）
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="活跃审批流程", help_text="当前正在进行的项目信息变更审批")

    class Meta:
        verbose_name = "项目"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['manager']),
            models.Index(fields=['name']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @cached_property
    def cached_nodes(self):
        return sorted(self.nodes.all(), key=lambda x: x.order)

    def user_can_manage_content(self, user):
        """当前用户是否可向本项目新增内容（如创建表单、上传附件），仅项目负责人或超管。"""
        return bool(user and (user.is_superuser or user.pk == self.manager_id))

    @cached_property
    def current_active_node(self):
        for node in self.cached_nodes:
            if node.status in ['DOING', 'PENDING', 'PAUSED', 'AWAITING_APPROVAL']:
                return node
        return None

    @property
    def is_paused(self):
        node = self.current_active_node
        return node.status == 'PAUSED' if node else False

    @property
    def progress_bar_css_class(self):
        if self.is_terminated: return "bg-danger"
        if self.is_completed: return "bg-success"
        if self.is_paused: return "bg-warning"
        return "bg-primary"

    @property
    def is_completed(self):
        return self.progress_percent == 100

    @property
    def status_css_class(self):
        if self.is_terminated:
            return 'badge bg-red-lt'
        if self.is_completed:
            return 'badge bg-green-lt'
        if self.is_paused:
            return 'badge bg-warning-lt'
        return 'text-blue small fw-bold'

    @property
    def status_label(self):
        if self.is_terminated:
            return '已终止'
        if self.is_completed:
            return '已完成'
        if self.is_paused:
            return '暂停中'
        return self.get_current_stage_display()

    # --- 业务逻辑封装 ---
    def add_iteration_node(self, stage_code, after_node_order):
        with transaction.atomic():
            from django.db.models import F
            self.nodes.filter(order__gt=after_node_order).update(order=F('order') + 1)
            current_count = self.nodes.filter(stage=stage_code).count()
            new_round = current_count + 1
            ProjectNode.objects.create(
                project=self,
                stage=stage_code,
                order=after_node_order + 1,
                round=new_round,
                status='PENDING',
                remark=f"第 {new_round} 轮调整：\n"
            )

    def handle_customer_feedback(self, current_node, feedback_type, content, feedback_type_obj_id=None):
        with transaction.atomic():
            if feedback_type == 'STOP':
                current_node.status = 'TERMINATED'
                current_node.save()
                self.terminate_project(current_node.order, content)
            else:
                self.add_iteration_node(ProjectStage.FEEDBACK, current_node.order)
                feedback_node = self.nodes.filter(order=current_node.order + 1).first()
                if feedback_node:
                    feedback_node.status = 'FEEDBACK'
                    feedback_node.remark = content
                    if feedback_type_obj_id:
                        feedback_node.feedback_type_id = feedback_type_obj_id
                    feedback_node.save()

    def terminate_project(self, current_node_order, reason):
        with transaction.atomic():
            self.nodes.filter(order__gt=current_node_order, status='PENDING').delete()
            ProjectNode.objects.create(
                project=self,
                stage=ProjectStage.FEEDBACK,
                order=current_node_order + 1,
                round=1,
                status='TERMINATED',
                remark=f"终止原因：{reason}"
            )


# 4. 项目信息变更记录（审批申请 + 永久历史记录）
class ProjectFieldChange(AbstractProjectFields):
    """项目基本信息编辑的变更记录，审批通过后才写入 Project 表"""

    STATUS_CHOICES = [
        ('PENDING', '待审批'),
        ('APPROVED', '已通过'),
        ('REJECTED', '已拒绝'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='field_changes', verbose_name="关联项目")

    # 提交元数据
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_field_changes', verbose_name="提交人")
    submission_comment = models.TextField("提交意见", help_text="请说明本次编辑项目信息的原因")

    # 审批跟踪
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联审批流程")

    # 时间戳
    created_at = models.DateTimeField("提交时间", auto_now_add=True)
    resolved_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "项目信息变更记录"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.project.name} — {self.get_status_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


# 5. 进度节点模型
class ProjectNode(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '未开始'),
        ('DOING', '进行中'),
        ('PAUSED', '暂停'),
        ('AWAITING_APPROVAL', '待审批'),
        ('DONE', '已完成'),
        ('FEEDBACK', '客户意见'),
        ('FAILED', '异常/节点迭代'),
        ('TERMINATED', '已终止'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='nodes')
    stage = models.CharField("阶段", max_length=20, choices=ProjectStage.choices)
    round = models.PositiveIntegerField("轮次", default=1)
    order = models.IntegerField("排序权重", default=0)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    remark = models.TextField("备注/批注", blank=True, null=True)
    
    # 绩效得分
    final_score = models.DecimalField("节点研发绩效得分", max_digits=5, decimal_places=2, default=0.00)
    sales_final_score = models.DecimalField("节点销售绩效得分", max_digits=5, decimal_places=2, default=0.00)

    # 【联动工作流】关联审批实例
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联审批流程")

    # 不合格原因关联
    failure_reason = models.ForeignKey('FailureReason', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="不合格原因", help_text="申报异常时选择的不合格原因类型")

    # 客户意见类型关联
    feedback_type = models.ForeignKey('FeedbackType', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="客户意见类型", help_text="客户反馈时选择的意见分类")

    class Meta:
        verbose_name = "项目进度节点"
        ordering = ['order']

    def __str__(self):
        return f"{self.project.name} — {self.get_stage_display()}（第{self.round}轮）"

    @classmethod
    def get_user_selectable_choices(cls):
        """【优化】返回用户在界面上可选的状态子集"""
        # 仅保留：未开始、进行中、暂停、已完成
        allowed = ['PENDING', 'DOING', 'PAUSED', 'DONE']
        return [(v, l) for v, l in cls.STATUS_CHOICES if v in allowed]

    @property
    def is_active(self):
        return self.status not in ['DONE', 'TERMINATED', 'FAILED', 'FEEDBACK']

    @property
    def is_active_status(self):
        return self.status in ['DONE', 'DOING', 'PAUSED', 'AWAITING_APPROVAL']

    @property
    def can_update_status(self):
        project_current_node = self.project.current_active_node
        is_current_node = (project_current_node and project_current_node.pk == self.pk)
        return is_current_node and self.status not in ['DONE', 'TERMINATED', 'FAILED', 'FEEDBACK', 'AWAITING_APPROVAL']

    @property
    def can_manage_content(self):
        """当前节点是否允许新增表单/上传资料（审批期间也允许，终态隐藏）"""
        project_current_node = self.project.current_active_node
        is_current_node = (project_current_node and project_current_node.pk == self.pk)
        return is_current_node and self.status not in ['DONE', 'TERMINATED', 'FAILED', 'FEEDBACK']

    @property
    def can_report_failure(self):
        project_current_node = self.project.current_active_node
        is_current_node = (project_current_node and project_current_node.pk == self.pk)
        allowed_stages = [ProjectStage.RND, ProjectStage.PILOT, ProjectStage.MID_TEST]
        return is_current_node and self.is_active and (self.stage in allowed_stages) and self.status != 'AWAITING_APPROVAL'

    @property
    def can_add_feedback(self):
        project_current_node = self.project.current_active_node
        is_current_node = (project_current_node and project_current_node.pk == self.pk)
        return is_current_node and (self.status not in ['TERMINATED', 'DONE', 'FAILED', 'AWAITING_APPROVAL']) and (self.stage != ProjectStage.FEEDBACK)

    @property
    def status_css_class(self):
        mapping = {
            'PENDING': 'bg-secondary-lt',
            'DOING': 'bg-blue-lt',
            'PAUSED': 'bg-warning-lt',
            'AWAITING_APPROVAL': 'bg-purple-lt',
            'DONE': 'bg-green-lt',
            'FEEDBACK': 'bg-yellow text-white',
            'FAILED': 'bg-red-lt',
            'TERMINATED': 'bg-red text-white',
        }
        return mapping.get(self.status, 'bg-secondary-lt')

    @property
    def title_status_css_class(self):
        mapping = {
            'PENDING': 'text-secondary',
            'DOING': 'text-primary',
            'PAUSED': 'text-warning',
            'AWAITING_APPROVAL': 'text-purple',
            'DONE': 'text-primary',
            'FEEDBACK': 'badge bg-yellow text-white',
            'FAILED': 'text-primary',
            'TERMINATED': 'text-primary'
        }
        return mapping.get(self.status, 'text-secondary')

    @property
    def row_active_class(self):
        if self.status not in ['DONE', 'FAILED', 'FEEDBACK']: return "active"
        return ""

    @property
    def is_feedback_stage(self):
        return self.stage == ProjectStage.FEEDBACK

    @property
    def is_awaiting_approval(self):
        return self.status == 'AWAITING_APPROVAL'

    @property
    def has_been_updated(self):
        return self.status != 'PENDING'

    FORMULA_STAGES = ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']

    @property
    def can_be_mature(self):
        return self.stage == ProjectStage.MASS_PROD

    @property
    def can_add_formula(self):
        return self.can_update_status and self.stage in self.FORMULA_STAGES

    @property
    def formula_button_label(self):
        if self.stage == 'MASS_PROD':
            return '新增成熟配方'
        return '新增配方'

    @property
    def formula_name(self):
        if self.stage == 'MASS_PROD':
            return f'{self.project.name} — 量产成熟配方'
        return f'{self.project.name} — {self.get_stage_display()} 第{self.round}轮'

    def perform_failure_logic(self, reason, failure_reason=None):
        with transaction.atomic():
            self.status = 'FAILED'
            self.remark = reason
            if failure_reason:
                self.failure_reason = failure_reason
            self.save()
        project = self.project
        if self.stage in ['RND', 'PILOT', 'MID_TEST']:
            project.add_iteration_node(ProjectStage.RND, self.order)
            if self.stage == 'MID_TEST':
                project.add_iteration_node(ProjectStage.MID_TEST, self.order + 1)
            if self.stage in ['PILOT', 'MID_TEST']:
                project.add_iteration_node(ProjectStage.PILOT, self.order + 1)


# 6. 项目协同成员模型
class ProjectMember(models.Model):
    ROLE_CHOICES = [
        ('LEAD', '项目主导'),
        ('RND', '实验研发'),
        ('PROCESS', '工艺支持'),
        ('SALES', '商务跟进'),
        ('ASSIST', '辅助/资料'),
    ]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members', verbose_name="关联项目")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="成员用户")
    role = models.CharField("成员角色", max_length=20, choices=ROLE_CHOICES, default='RND')
    workload_share = models.DecimalField("工作量占比", max_digits=5, decimal_places=2, default=100.00, help_text="工作量占比百分比 (0-100)")

    class Meta:
        verbose_name = "项目成员"
        unique_together = ('project', 'user')


# 6.1 项目销售成员模型（独立管理，独立工作量池）
class ProjectSalesMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sales_members', verbose_name="关联项目")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="销售成员")
    workload_share = models.DecimalField("销售工作量占比", max_digits=5, decimal_places=2, default=0.00, help_text="销售工作量占比百分比 (0-100)")

    class Meta:
        verbose_name = "项目销售成员"
        verbose_name_plural = verbose_name
        unique_together = ('project', 'user')

    def __str__(self):
        return f"{self.project.name} - {self.user.username} (销售)"


# 6.2 成员成绩快照模型
class MemberScoreSnapshot(models.Model):
    """成员成绩快照 — 绩效看板的唯一数据源。

    每次成员得分变更（节点终态变化 / 评分规则变更 / 成员占比或增减 / 等级因子变更）
    都落一条快照，记录该成员在某个项目上、某条轨（研发/销售）的即时成绩，
    以及当时的底层因子（质量分/占比/等级因子）用于审计回溯。
    """
    TRACK_CHOICES = [('RD', '研发'), ('SALES', '销售')]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='score_snapshots', verbose_name="关联项目")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+', verbose_name="成员用户")
    track = models.CharField("成绩轨", max_length=10, choices=TRACK_CHOICES)

    snapshot_at = models.DateTimeField("快照时间", db_index=True, help_text="本次成绩自何时起生效")

    effective_score = models.DecimalField("有效贡献分", max_digits=9, decimal_places=2, default=0.00, help_text="含等级因子加权")
    workload_score = models.DecimalField("基础工作量分", max_digits=9, decimal_places=2, default=0.00, help_text="不含等级因子")

    # 审计冗余 — 回溯本次成绩所用的底层因子
    quality_score = models.DecimalField("项目质量分", max_digits=5, decimal_places=2, default=0.00)
    workload_share = models.DecimalField("工作量占比", max_digits=5, decimal_places=2, default=0.00, help_text="百分比 0-100")
    grade_factor = models.DecimalField("等级因子", max_digits=5, decimal_places=2, default=1.00)

    class Meta:
        verbose_name = "成员成绩快照"
        indexes = [
            models.Index(fields=['user', 'track', '-snapshot_at'], name='app_project_user_track_idx'),
            models.Index(fields=['project', 'track', '-snapshot_at'], name='app_project_proj_track_idx'),
        ]

    def __str__(self):
        return f"{self.project.name} - {self.user.username} ({self.get_track_display()}) @ {self.snapshot_at}"


# 7. 项目全局配置（单例）
class ProjectConfig(models.Model):
    """项目全局配置，仅允许超级管理员修改。"""
    default_approval_workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='默认审批流程（项目节点）')
    default_repository_approval_workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='默认审批流程（项目档案）', related_name='repo_configs', help_text='编辑项目档案时使用的审批流程，留空则编辑直接生效')
    default_project_edit_approval_workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='默认审批流程（项目信息编辑）', related_name='project_edit_configs', help_text='编辑项目基本信息时使用的审批流程，留空则编辑直接生效')

    class Meta:
        verbose_name = "项目全局配置"

    def __str__(self):
        return "项目全局配置"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# 8. 不合格原因库（lookup 模型）
class FailureReason(models.Model):
    """预定义的不合格原因类型，供节点申报异常时选择关联"""
    name = models.CharField("原因名称", max_length=50, unique=True)
    code = models.CharField("原因编码", max_length=20, blank=True, help_text="如：FORMULA_FAIL, COLOR_DEVIATION")
    order = models.PositiveIntegerField("排序权重", default=0, help_text="数字越小越靠前")
    description = models.TextField("原因说明", blank=True, help_text="详细说明该不合格原因的含义")
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        verbose_name = "不合格原因"
        verbose_name_plural = "不合格原因库"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


# 8.1 客户意见类型库（lookup 模型）
class FeedbackType(models.Model):
    """预定义的客户意见类型，供节点客户反馈时选择关联"""
    name = models.CharField("意见类型名称", max_length=50, unique=True)
    code = models.CharField("类型编码", max_length=20, blank=True, help_text="如：COLOR_ADJUST, PERF_CHANGE")
    order = models.PositiveIntegerField("排序权重", default=0, help_text="数字越小越靠前")
    description = models.TextField("类型说明", blank=True, help_text="详细说明该意见类型的使用场景")
    is_active = models.BooleanField("是否启用", default=True)

    class Meta:
        verbose_name = "客户意见类型"
        verbose_name_plural = "客户意见类型库"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


# 9. 评分规则配置模型
class NodeScoreRule(models.Model):
    RULE_TYPES = [('RD', '研发'), ('SALES', '销售')]

    name = models.CharField("规则名称", max_length=100)
    score_value = models.PositiveIntegerField("对应得分", default=0)
    rule_type = models.CharField("规则类型", max_length=10, choices=RULE_TYPES, default='RD')
    trigger_stage = models.CharField("触发阶段", max_length=20, choices=ProjectStage.choices, blank=True, null=True)
    trigger_status = models.CharField("触发状态", max_length=20, choices=ProjectNode.STATUS_CHOICES)
    is_multiple_rounds = models.BooleanField("是否为多轮次 (返工)", default=False)
    description = models.TextField("规则描述/判定逻辑", blank=True)

    def __str__(self):
        return f"{self.name} ({self.score_value}分)"

    class Meta:
        verbose_name = "绩效评分规则"

    @property
    def status_css_class(self):
        """返回触发状态对应的彩色胶囊样式"""
        mapping = {
            'DONE': 'bg-green-lt',
            'FAILED': 'bg-red-lt',
            'TERMINATED': 'bg-dark-lt',
            'PENDING': 'bg-secondary-lt',
            'DOING': 'bg-blue-lt',
            'PAUSED': 'bg-warning-lt',
            'FEEDBACK': 'bg-yellow-lt',
            'AWAITING_APPROVAL': 'bg-purple-lt',
        }
        return mapping.get(self.trigger_status, 'bg-secondary-lt')
