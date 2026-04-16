import os
import uuid
from django.db import models
from django.contrib.auth.models import User
from app_project.models import Project, ProjectNode
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size


# ==========================================
# 1. 主机厂 (OEM) - 用户画像
# ==========================================
class OEM(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='oem_profile', verbose_name="关联系统账号")
    member_token = models.UUIDField("成员唯一令牌", default=uuid.uuid4, editable=False, unique=True)
    is_active = models.BooleanField("账号启用状态", default=True)

    name = models.CharField("主机厂名称", max_length=100, unique=True)
    short_name = models.CharField("简称", max_length=20, blank=True)
    description = models.TextField("描述/备注", blank=True)
    website = models.URLField("官方网站", blank=True)
    contact_name = models.CharField("主要联系人", max_length=50, blank=True)
    contact_phone = models.CharField("联系电话", max_length=50, blank=True)
    contact_email = models.EmailField("电子邮箱", blank=True)
    address = models.CharField("公司地址", max_length=200, blank=True)
    
    def __str__(self): return self.short_name or self.name
    class Meta:
        verbose_name = "主机厂"
        verbose_name_plural = "主机厂库"


class OEMStandardFile(models.Model):
    oem = models.ForeignKey(OEM, on_delete=models.CASCADE, related_name='standard_files', verbose_name="所属主机厂")
    name = models.CharField("文件名称", max_length=100, blank=True)
    file = models.FileField("文件附件", upload_to=upload_file_path, validators=[validate_file_size])
    file_type = models.CharField("文件类型", max_length=20, choices=[('MATERIAL', '材料标准'), ('TEST', '测试标准'), ('QUALITY', '质量协议'), ('OTHER', '其他标准')], default='MATERIAL')
    description = models.TextField("备注/详细说明", blank=True)
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="上传人")
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)
    version = models.PositiveIntegerField("版本号", default=1)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.file:
            self.name = os.path.basename(self.file.name)
            self.__class__.objects.filter(pk=self.pk).update(name=self.name)

    def __str__(self): return f"{self.name} (V{self.version})"
    class Meta:
        verbose_name = "主机厂标准文件"
        verbose_name_plural = "主机厂标准文件库"
        ordering = ['-uploaded_at']


# ==========================================
# 2. 客户库 - 用户画像
# ==========================================
class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                related_name='customer_profile', verbose_name="关联系统账号")
    member_token = models.UUIDField("成员唯一令牌", default=uuid.uuid4, editable=False, unique=True)
    is_active = models.BooleanField("账号启用状态", default=True)

    company_name = models.CharField("公司全称", max_length=100, unique=True)
    short_name = models.CharField("简称", max_length=20, blank=True)
    address = models.CharField("地址", max_length=200, blank=True)
    contact_name = models.CharField("商务联系人", max_length=50, blank=True)
    phone = models.CharField("手机", max_length=20, blank=True)
    email = models.EmailField("邮箱", blank=True)
    
    def __str__(self): return self.short_name or self.company_name
    class Meta:
        verbose_name = "客户"
        verbose_name_plural = "客户库"


# ==========================================
# 3. 外部会员行为回流记录
# ==========================================
class ExternalMemberActivity(models.Model):
    member_token = models.CharField("会员令牌", max_length=100, db_index=True)
    action = models.CharField("操作类型", max_length=50)
    target_name = models.CharField("目标牌号", max_length=100)
    timestamp = models.DateTimeField("发生时间")
    def __str__(self): return f"{self.member_token} - {self.action} - {self.target_name}"
    class Meta:
        verbose_name = "外部行为日志"
        verbose_name_plural = "外部行为审计"
        ordering = ['-timestamp']


# ==========================================
# 4. 项目档案 - 核心业务模型
# ==========================================
class ProjectRepository(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='repository', verbose_name="关联项目")
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="直接客户 (Tier1)")
    oem = models.ForeignKey(OEM, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="终端主机厂 (OEM)")
    
    # 【核心调整】：salesperson 现在直接指向 User 模型 (即内部系统用户)
    salesperson = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                    related_name='managed_project_repos', verbose_name="负责业务员")
    
    product_name = models.CharField("客户产品名称", max_length=100, blank=True)
    product_code = models.CharField("产品代码/零件号", max_length=100, blank=True)
    material = models.ForeignKey('app_material.MaterialLibrary', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="选用材料")
    updated_at = models.DateTimeField("最后更新", auto_now=True)

    def __str__(self): return f"{self.project.name} 档案"
    class Meta:
        verbose_name = "项目档案"
        verbose_name_plural = "项目档案"
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
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and self.file:
            self.name = os.path.basename(self.file.name)
            self.__class__.objects.filter(pk=self.pk).update(name=self.name)

    def __str__(self): return f"{self.name} (V{self.version})"
    class Meta:
        verbose_name = "项目文件"
        verbose_name_plural = "项目文件库"
        ordering = ['-uploaded_at']
