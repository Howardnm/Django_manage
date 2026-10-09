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
    直接客户公司档案 (如：延锋、马瑞利、华阳)。
    客户编码是 SAP 主数据唯一键；公司全称允许重名。
    """
    customer_code = models.CharField("客户编码", max_length=20, unique=True, null=True, blank=True)
    company_name = models.CharField("公司全称", max_length=100)
    company_name_2 = models.CharField("客户名称2", max_length=80, blank=True)
    short_name = models.CharField("搜索词 1", max_length=40, blank=True)
    search_term_2 = models.CharField("搜索词 2", max_length=40, blank=True)
    account_group = models.CharField("客户账户组", max_length=10, blank=True)
    account_group_name = models.CharField("账户组描述", max_length=20, blank=True)
    customer_series = models.CharField("客户系", max_length=20, blank=True)
    industry = models.CharField("行业", max_length=50, blank=True)
    trade_partner = models.CharField("贸易伙伴", max_length=10, blank=True)
    vendor_code = models.CharField("供应商编码", max_length=20, blank=True)
    address_number = models.CharField("内部地址号", max_length=20, blank=True)
    business_license_code = models.CharField("统一社会信用代码", max_length=50, blank=True)

    country_code = models.CharField("国家", max_length=4, blank=True)
    country_name = models.CharField("国家名称", max_length=40, blank=True)
    region_code = models.CharField("地区", max_length=10, blank=True)
    region_name = models.CharField("地区名称", max_length=40, blank=True)
    city = models.CharField("城市", max_length=60, blank=True)
    street = models.CharField("街道/门牌号", max_length=80, blank=True)
    house_number = models.CharField("门牌号", max_length=20, blank=True)
    postal_code = models.CharField("邮政编码", max_length=10, blank=True)
    address = models.CharField("公司办公地址", max_length=200, blank=True)
    phone = models.CharField("电话号1", max_length=30, blank=True)
    phone_2 = models.CharField("电话号2", max_length=30, blank=True)
    email = models.CharField("电子邮件地址", max_length=100, blank=True)
    customer_source = models.CharField("客户来源", max_length=50, blank=True)

    sales_region = models.CharField("区域", max_length=20, blank=True)
    sales_manager_name = models.CharField("销售主管", max_length=30, blank=True)
    sales_person_name = models.CharField("销售人员", max_length=30, blank=True)

    posting_blocked = models.BooleanField("全部记账冻结", default=False, blank=True)
    sales_area_blocked = models.BooleanField("全部销售区域冻结", default=False, blank=True)
    group_deleted = models.BooleanField("集团级删除", default=False, blank=True)
    sales_order_block = models.CharField("销售订单冻结", max_length=4, blank=True)
    delivery_block = models.CharField("交货冻结", max_length=4, blank=True)
    billing_block = models.CharField("出具发票冻结", max_length=4, blank=True)
    sap_created_by = models.CharField("集团级创建者", max_length=20, blank=True)
    sap_created_on = models.DateField("集团级创建日期", null=True, blank=True)

    logo = models.ImageField("公司Logo", upload_to='customer/logos/', blank=True, null=True)
    description = models.TextField("客户简介", blank=True)
    created_at = models.DateTimeField("录入时间", auto_now_add=True)

    def __str__(self):
        label = self.short_name or self.company_name
        return f"{self.customer_code} {label}" if self.customer_code else label

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
    estimated_order_volume = models.DecimalField("预估市场订单用量 (吨/年)", max_digits=10, decimal_places=2, null=True, blank=True)

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
