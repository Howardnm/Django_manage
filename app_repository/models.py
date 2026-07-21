import os
import uuid
from django.db import models
from django.conf import settings
from app_project.models import Project, ProjectNode



# ==========================================
# 0. 基础配置 - 等级因子
# ==========================================
class GradeFactor(models.Model):
    """
    项目等级因子配置 (如：A级-1.5, B级-1.2)
    """
    name = models.CharField("等级名称", max_length=20, unique=True)
    factor = models.DecimalField("等级因子", max_digits=5, decimal_places=2, default=1.00)
    description = models.TextField("等级说明/标准", blank=True)

    def __str__(self):
        return f"{self.name} (因子: {self.factor})"

    class Meta:
        verbose_name = "等级因子"
        verbose_name_plural = "0. 等级因子配置"


# ==========================================
# 1. 主机厂 (OEM) - 顶级业务实体
# ==========================================
class OEM(models.Model):
    """
    主机厂公司档案 (如：吉利汽车、长城汽车)
    """
    name = models.CharField("主机厂全称", max_length=100, unique=True)
    short_name = models.CharField("品牌简称", max_length=20, blank=True)
    logo = models.ImageField("品牌Logo", upload_to='oem/logos/', blank=True, null=True)
    description = models.TextField("公司简介/备注", blank=True)
    website = models.URLField("官方网站", blank=True)
    
    # 统计信息
    view_count = models.PositiveIntegerField("查阅次数", default=0)
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    def __str__(self): return self.short_name or self.name
    class Meta:
        verbose_name = "主机厂"
        verbose_name_plural = "1. 主机厂名录"


# ==========================================
# 2. 客户公司 (Tier 1/2) - 业务实体
# ==========================================
class Customer(models.Model):
    """
    直接客户公司档案 (如：延锋、马瑞利、华阳)
    """
    company_name = models.CharField("公司全称", max_length=100, unique=True)
    short_name = models.CharField("公司简称", max_length=20, blank=True)
    logo = models.ImageField("公司Logo", upload_to='customer/logos/', blank=True, null=True)
    
    address = models.CharField("公司办公地址", max_length=200, blank=True)
    business_license_code = models.CharField("统一社会信用代码", max_length=50, blank=True)
    description = models.TextField("客户简介", blank=True)
    
    created_at = models.DateTimeField("录入时间", auto_now_add=True)
    
    def __str__(self): return self.short_name or self.company_name
    class Meta:
        verbose_name = "客户公司"
        verbose_name_plural = "2. 客户名录"


# ==========================================
# 3. 项目档案共享字段 — 抽象基类
# ==========================================
class AbstractProjectRepositoryFields(models.Model):
    """
    项目档案的共享业务字段 — 抽象基类，不创建数据库表。
    ProjectRepository 与 ProjectRepositoryFieldChange 均继承此类，
    确保字段定义一致，新增字段只需在一处维护。
    """
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="直接客户 (Tier1)")
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="终端主机厂 (OEM)")
    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="负责业务员")

    product_name = models.CharField("客户产品名称", max_length=100, blank=True)
    product_code = models.CharField("产品代码/零件号", max_length=100, blank=True)

    target_cost = models.DecimalField("目标成本 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    competitor_price = models.DecimalField("竞品售价 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_order_volume = models.DecimalField("预估市场订单用量 (kg/年)", max_digits=10, decimal_places=2, null=True, blank=True)

    # 项目计划时间节点
    first_sample_date = models.DateField("第一次客户送样时间", null=True, blank=True)
    first_trial_date = models.DateField("第一次客户小试时间", null=True, blank=True)
    first_trial_cycle_days = models.PositiveIntegerField("第一次小试完成周期 (天)", null=True, blank=True)
    pilot_date = models.DateField("中试进行时间", null=True, blank=True)
    mass_production_date = models.DateField("量产进行时间", null=True, blank=True)

    class Meta:
        abstract = True


# ==========================================
# 4. 项目商务档案 - 核心关联
# ==========================================
class ProjectRepository(AbstractProjectRepositoryFields):
    """
    项目档案：在此处关联具体的 项目、客户公司、主机厂。
    """
    # 覆盖基类 FK 字段，显式定义 related_name
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='repo_records', verbose_name="直接客户 (Tier1)")
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=True, related_name='repo_records', verbose_name="终端主机厂 (OEM)")
    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_repos', verbose_name="负责业务员")

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='repository', verbose_name="关联项目")

    # 活跃审批追踪
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="活跃审批流程", help_text="当前正在进行的档案变更审批")

    updated_at = models.DateTimeField("最后更新", auto_now=True)

    def __str__(self): return f"{self.project.name} 档案"
    class Meta:
        verbose_name = "项目档案"
        verbose_name_plural = "3. 项目商务档案"
        ordering = ['-updated_at']


# ==========================================
# 4.1 档案字段变更记录 — 审批申请 & 历史追踪
# ==========================================
class ProjectRepositoryFieldChange(AbstractProjectRepositoryFields):
    """项目档案财务字段变更记录 — 既是审批申请，也是历史记录"""

    STATUS_CHOICES = [
        ('PENDING', '待审批'),
        ('APPROVED', '已通过'),
        ('REJECTED', '已拒绝'),
    ]

    repository = models.ForeignKey(ProjectRepository, on_delete=models.CASCADE, related_name='field_changes', verbose_name="关联档案")

    # 提交信息
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='repo_field_changes', verbose_name="提交人")
    submission_comment = models.TextField("提交意见", help_text="请说明编辑档案的原因")

    # 审批追踪
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='PENDING')
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联审批流程")

    # 时间戳
    created_at = models.DateTimeField("提交时间", auto_now_add=True)
    resolved_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "档案字段变更记录"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['repository', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.repository} — {self.get_status_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


# 外部行为回流记录
class ExternalMemberActivity(models.Model):
    member_token = models.CharField("会员令牌", max_length=100, db_index=True)
    action = models.CharField("操作类型", max_length=50)
    target_name = models.CharField("目标牌号", max_length=100)
    timestamp = models.DateTimeField("发生时间")
    class Meta:
        verbose_name = "外部行为日志"
        ordering = ['-timestamp']
