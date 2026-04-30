# Create your models here.
from django.db import models
from django.conf import settings
from django.utils.text import Truncator  # 导入文字截断器
from django.db import transaction  # 用于事务处理，保证排序修改的安全性
from django.utils.functional import cached_property  # 引入缓存装饰器


# 1. 定义标准流程阶段 (枚举) - 这相当于“类型库”
class ProjectStage(models.TextChoices):
    INIT = 'INIT', '① 项目立项'
    COLLECT = 'COLLECT', '② 收集资料'
    FEASIBILITY = 'FEASIBILITY', '③ 可行性评估'
    PRICING = 'PRICING', '④ 客户定价'
    RND = 'RND', '⑤ 研发阶段'  # 可能多次
    PILOT = 'PILOT', '⑥ 客户小试'  # 可能多次
    MID_TEST = 'MID_TEST', '⑦ 客户中试'  # 可能多次
    MASS_PROD = 'MASS_PROD', '⑧ 客户量产意向'
    ORDER = 'ORDER', '⑨ 客户下单情况'
    FEEDBACK = 'FEEDBACK', '🎗️客户意见'


# 2. 项目主体模型
class Project(models.Model):
    name = models.CharField("项目名称", max_length=100)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="项目负责人")
    description = models.TextField("项目描述", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    
    # 【新增】项目等级关联
    grade = models.ForeignKey('app_repository.GradeFactor', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="项目等级")

    # 进度冗余字段
    current_stage = models.CharField("当前阶段", max_length=20, choices=ProjectStage.choices, default=ProjectStage.INIT)
    progress_percent = models.PositiveIntegerField("进度百分比", default=0)
    is_terminated = models.BooleanField("是否终止", default=False)
    latest_remark = models.CharField("最新进展", max_length=200, blank=True, help_text="自动同步当前活跃节点的备注")
    
    # 【核心优化】新增：项目质量分冗余字段 (用于绩效统计性能优化)
    quality_score = models.DecimalField("项目质量得分", max_digits=5, decimal_places=2, default=0.00)

    # 【联动工作流】默认审批流程
    approval_workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="默认审批流程")

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
        if self.progress_percent == 100: return "bg-success"
        if self.is_paused: return "bg-warning"
        return "bg-primary"

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

    def handle_customer_feedback(self, current_node, feedback_type, content):
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


# 3. 进度节点模型
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
    final_score = models.DecimalField("节点绩效得分", max_digits=5, decimal_places=2, default=0.00)

    # 【联动工作流】关联审批实例
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联审批流程")

    class Meta:
        verbose_name = "项目进度节点"
        ordering = ['order']

    def __str__(self):
        return f"{self.project.name}-{self.get_stage_display()}"

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
    def can_report_failure(self):
        project_current_node = self.project.current_active_node
        is_current_node = (project_current_node and project_current_node.pk == self.pk)
        allowed_stages = [ProjectStage.RND, ProjectStage.PILOT, ProjectStage.MID_TEST]
        return is_current_node and self.is_active and (self.stage in allowed_stages)

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

    def perform_failure_logic(self, reason):
        with transaction.atomic():
            self.status = 'FAILED'
            self.remark = reason
            self.save()
        project = self.project
        if self.stage in ['RND', 'PILOT', 'MID_TEST']:
            project.add_iteration_node(ProjectStage.RND, self.order)
            if self.stage == 'MID_TEST':
                project.add_iteration_node(ProjectStage.MID_TEST, self.order + 1)
            if self.stage in ['PILOT', 'MID_TEST']:
                project.add_iteration_node(ProjectStage.PILOT, self.order + 1)


# 4. 项目协同成员模型
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
    workload_share = models.DecimalField("工作量占比 (0-1.0)", max_digits=3, decimal_places=2, default=1.00)

    class Meta:
        verbose_name = "项目成员"
        unique_together = ('project', 'user')


# 5. 评分规则配置模型
class NodeScoreRule(models.Model):
    name = models.CharField("规则名称", max_length=100)
    score_value = models.PositiveIntegerField("对应得分", default=0)
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
