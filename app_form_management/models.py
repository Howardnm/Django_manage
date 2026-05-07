from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class FormTemplate(models.Model):
    """表单模板 — form_config 存储 form-create-designer 生成的 JSON rule"""
    name = models.CharField(max_length=100, verbose_name='表单名称')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    is_active = models.BooleanField(default=True, verbose_name='启用')
    form_config = models.JSONField(default=list, blank=True, verbose_name='表单字段配置JSON', help_text='form-create-designer 生成的 rule 数组')
    form_option = models.JSONField(default=dict, blank=True, verbose_name='表单全局配置JSON', help_text='form-create option，如 labelPosition、labelWidth 等')
    workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联审批流程', help_text='提交表单时自动启动该审批流程')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'form_template'
        verbose_name = '表单模板'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.name

class FormSubmission(models.Model):
    """表单提交记录 — 通过 GenericForeignKey 关联任意模型"""
    STATUS_CHOICES = [
        ('DRAFT', '草稿'),
        ('SUBMITTED', '已提交'),
    ]

    template = models.ForeignKey(FormTemplate, on_delete=models.CASCADE, related_name='submissions', verbose_name='表单模板')

    # 通用外键 — content_type(哪类模块) + object_id(哪个实体) → target_object(实际对象)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, verbose_name='关联模块')
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='关联实体ID')
    target_object = GenericForeignKey('content_type', 'object_id')

    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='提交人')
    form_data = models.JSONField(default=dict, verbose_name='表单数据')
    workflow_instance = models.ForeignKey('app_workflow.WorkflowInstance', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联审批实例')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name='状态')
    remark = models.TextField(blank=True, default='', verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'form_submission'
        verbose_name = '表单提交'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.template.name} - {self.submitted_by} ({self.get_status_display()})'
