from django.db import models
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.functional import cached_property
from django.utils import timezone
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size


# 1. 预研项目阶段 (枚举)
class ResearchStage(models.TextChoices):
    INIT = 'INIT', '① 项目立项'
    LITERATURE = 'LITERATURE', '② 文献/市场调研'
    PLANNING = 'PLANNING', '③ 方案制定'
    EXPERIMENT = 'EXPERIMENT', '④ 实验验证'
    ANALYSIS = 'ANALYSIS', '⑤ 结果分析'
    CONCLUSION = 'CONCLUSION', '⑥ 结项/归档'
    TERMINATED = 'TERMINATED', '❌ 终止'


# 2. 预研项目主体
class ResearchProject(models.Model):
    """
    预研项目 (Basic Research Project)
    用于管理新材料、新技术的探索性研究项目
    """
    name = models.CharField("项目名称", max_length=100)
    code = models.CharField("项目编号", max_length=50, unique=True, blank=True, help_text="自动生成，如：RP20231001-01")
    manager = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="项目负责人")
    description = models.TextField("项目背景/描述", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    # 进度相关字段 (冗余字段，用于列表展示)
    current_stage = models.CharField("当前阶段", max_length=20, choices=ResearchStage.choices, default=ResearchStage.INIT)
    progress_percent = models.PositiveIntegerField("进度百分比", default=0)
    is_terminated = models.BooleanField("是否终止", default=False)
    latest_remark = models.CharField("最新进展", max_length=200, blank=True, help_text="自动同步当前活跃节点的备注")

    class Meta:
        verbose_name = "预研项目"
        verbose_name_plural = "预研项目管理"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['current_stage']),
            models.Index(fields=['manager']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.code} {self.name}" if self.code else self.name

    # 自动生成项目编号
    def save(self, *args, **kwargs):
        if not self.code:
            # 生成规则：RP + 年月日 + - + 2位流水号
            today_str = timezone.now().strftime('%Y%m%d')
            prefix = f"RP{today_str}"
            
            # 查找当天已有的最大流水号
            last_obj = ResearchProject.objects.filter(code__startswith=prefix).order_by('code').last()
            
            if last_obj:
                try:
                    last_seq = int(last_obj.code.split('-')[-1])
                    new_seq = last_seq + 1
                except ValueError:
                    new_seq = 1
            else:
                new_seq = 1
            
            self.code = f"{prefix}-{new_seq:02d}"
        
        super().save(*args, **kwargs)

    @cached_property
    def cached_nodes(self):
        """获取当前项目的节点列表。将节点按 order 正序排序缓存到内存中"""
        return sorted(self.nodes.all(), key=lambda x: x.order)

    # --- 业务逻辑封装 ---
    def add_iteration_node(self, stage_code, after_node_order):
        """
        在指定的 order 之后插入一个新节点 (用于实验失败重来)
        :param stage_code: 新节点的阶段代码
        :param after_node_order: 在哪个排序号之后插入
        """
        with transaction.atomic():
            from django.db.models import F
            # 1. 把所有排在后面的节点，order 全部 +1
            self.nodes.filter(order__gt=after_node_order).update(order=F('order') + 1)
            
            # 2. 计算轮次
            current_count = self.nodes.filter(stage=stage_code).count()
            new_round = current_count + 1
            
            # 3. 创建新节点
            ResearchProjectNode.objects.create(
                project=self,
                stage=stage_code,
                order=after_node_order + 1,
                round=new_round,
                status='PENDING',
                remark=f"第 {new_round} 轮实验/调整：\n"
            )

    def terminate_project(self, current_node_order, reason):
        """终止项目"""
        with transaction.atomic():
            # 1. 删除后续所有未开始的节点
            self.nodes.filter(order__gt=current_node_order, status='PENDING').delete()

            # 2. 插入一个“终止”节点作为结局
            ResearchProjectNode.objects.create(
                project=self,
                stage=ResearchStage.TERMINATED,
                order=current_node_order + 1,
                round=1,
                status='TERMINATED',
                remark=f"终止原因：{reason}"
            )
            
            self.is_terminated = True
            self.save(update_fields=['is_terminated'])


# 3. 预研项目进度节点
class ResearchProjectNode(models.Model):
    STATUS_CHOICES = [
        ('PENDING', '未开始'),
        ('DOING', '进行中'),
        ('DONE', '已完成'),
        ('FAILED', '实验调整/迭代'),
        ('TERMINATED', '已终止'),
    ]

    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='nodes')
    stage = models.CharField("阶段", max_length=20, choices=ResearchStage.choices)
    round = models.PositiveIntegerField("轮次", default=1)
    order = models.IntegerField("排序权重", default=0)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default='PENDING')
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    remark = models.TextField("备注/批注", blank=True, null=True)

    class Meta:
        verbose_name = "预研进度节点"
        ordering = ['order']

    def __str__(self):
        return f"{self.project.name} - {self.get_stage_display()}"

    # --- 逻辑判断属性 ---
    @property
    def is_active(self):
        return self.status not in ['DONE', 'TERMINATED', 'FAILED']

    @property
    def can_update_status(self):
        # 【修复】允许对状态为 FAILED 的节点进行更新，以便修改备注
        return self.status not in ['TERMINATED']

    @property
    def can_report_failure(self):
        # 允许失败的阶段：实验验证
        return self.is_active and (self.stage == ResearchStage.EXPERIMENT)

    # --- UI 辅助属性 ---
    @property
    def status_css_class(self):
        mapping = {
            'PENDING': 'bg-secondary-lt',
            'DOING': 'bg-blue-lt',
            'DONE': 'bg-green-lt',
            'FAILED': 'bg-yellow-lt',
            'TERMINATED': 'bg-red text-white',
        }
        return mapping.get(self.status, 'bg-secondary-lt')

    @property
    def row_active_class(self):
        """控制步骤条是否点亮"""
        if self.status not in ['DONE', 'FAILED']:
            return "active"
        return ""

    # --- 业务操作封装 ---
    def perform_failure_logic(self, reason):
        """处理申报不合格的逻辑"""
        with transaction.atomic():
            self.status = 'FAILED'
            self.remark = reason
            self.save()

        # 如果是实验阶段失败，自动插入新一轮实验
        if self.stage == ResearchStage.EXPERIMENT:
            self.project.add_iteration_node(ResearchStage.EXPERIMENT, self.order)


# 4. 预研项目附件
class ResearchProjectFile(models.Model):
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name='files')
    file = models.FileField("附件", upload_to=upload_file_path, validators=[validate_file_size])
    name = models.CharField("附件名称", max_length=100, blank=True, help_text="如果不填，默认使用文件名")
    description = models.CharField("描述", max_length=200, blank=True)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="上传人")

    class Meta:
        verbose_name = "预研项目附件"
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.name or self.file.name

    def save(self, *args, **kwargs):
        if not self.name and self.file:
            self.name = self.file.name.split('/')[-1]
        super().save(*args, **kwargs)
