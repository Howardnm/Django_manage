import os
import uuid
from django.db import models
from django.conf import settings
from app_project.models import Project, ProjectNode
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size


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


class OEMStandardFile(models.Model):
    """主机厂标准文件 (如：Q/JL 材质规范)"""
    oem = models.ForeignKey(OEM, on_delete=models.CASCADE, related_name='standard_files', verbose_name="所属主机厂")
    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=[('MATERIAL', '材料标准'), ('TEST', '测试标准'), ('QUALITY', '质量协议'), ('OTHER', '其他标准')], default='MATERIAL')
    description = models.TextField("备注/详细说明", blank=True)
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="上传人")
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        if not self.name and self.file:
            self.name = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self): return self.name
    class Meta:
        verbose_name = "主机厂标准"
        ordering = ['-uploaded_at']


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
# 3. 项目商务档案 - 核心关联
# ==========================================
class ProjectRepository(models.Model):
    """
    项目档案：在此处关联具体的 项目、客户公司、主机厂。
    """
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='repository', verbose_name="关联项目")
    
    # 商业三要素：在此处产生交集
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="直接客户 (Tier1)")
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="终端主机厂 (OEM)")
    
    salesperson = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name='managed_project_repos', verbose_name="负责业务员")
    
    product_name = models.CharField("客户产品名称", max_length=100, blank=True)
    product_code = models.CharField("产品代码/零件号", max_length=100, blank=True)

    target_cost = models.DecimalField("目标成本 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True)
    competitor_price = models.DecimalField("竞品售价 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True)

    updated_at = models.DateTimeField("最后更新", auto_now=True)

    def __str__(self): return f"{self.project.name} 档案"
    class Meta:
        verbose_name = "项目档案"
        verbose_name_plural = "3. 项目商务档案"
        ordering = ['-updated_at']


class ProjectFile(models.Model):
    repository = models.ForeignKey(ProjectRepository, on_delete=models.CASCADE, related_name='files', verbose_name="所属档案")
    node = models.ForeignKey(ProjectNode, on_delete=models.SET_NULL, null=True, blank=True, related_name='files', verbose_name="关联节点")
    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=[('DRAWING_2D', '2D图纸'), ('DRAWING_3D', '3D数模'), ('STANDARD', '技术标准'), ('REPORT', '检测/测试报告'), ('QUOTE', '报价/商务'), ('OTHER', '其他资料')], default='OTHER')
    description = models.TextField("备注/详细说明", blank=True)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        if not self.name and self.file:
            self.name = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.name} (V{self.version})"
    class Meta:
        verbose_name = "项目文件"
        verbose_name_plural = "项目文件库"
        ordering = ['-uploaded_at']

# 外部行为回流记录
class ExternalMemberActivity(models.Model):
    member_token = models.CharField("会员令牌", max_length=100, db_index=True)
    action = models.CharField("操作类型", max_length=50)
    target_name = models.CharField("目标牌号", max_length=100)
    timestamp = models.DateTimeField("发生时间")
    class Meta:
        verbose_name = "外部行为日志"
        ordering = ['-timestamp']
