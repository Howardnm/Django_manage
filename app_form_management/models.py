from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()


class FormTemplate(models.Model):
    """表单模板 — form_config 存储 form-create-designer 生成的 JSON rule"""
    name = models.CharField(max_length=100, verbose_name='表单名称')
    group = models.CharField(max_length=100, blank=True, default='', verbose_name='分组', help_text='用于在创建表单页面中将模板分组展示')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    is_active = models.BooleanField(default=True, verbose_name='启用')
    form_config = models.JSONField(default=list, blank=True, verbose_name='表单字段配置JSON', help_text='form-create-designer 生成的 rule 数组')
    form_option = models.JSONField(default=dict, blank=True, verbose_name='表单全局配置JSON', help_text='form-create option，如 labelPosition、labelWidth 等')
    workflow = models.ForeignKey('app_workflow.WorkflowDefinition', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联审批流程', help_text='提交表单时自动启动该审批流程')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '表单模板'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def has_workflow(self):
        """是否关联审批流程"""
        return self.workflow_id is not None

    @property
    def is_multi_step(self):
        """是否为多步骤表单"""
        return len(self.step_groups) > 1

    @property
    def step_groups(self):
        """从 form_config 中提取步骤分组信息。
        返回 [{'step': 1, 'label': '基本信息', 'description': ''}, ...]
        """
        rules = self.form_config or []
        if not rules:
            return []
        step_map = {}
        step_labels = {}
        step_descs = {}
        max_step = 0
        for r in rules:
            props = r.get('props') or {}
            step = props.get('step')
            if step is None:
                step = 1
            else:
                step = int(step)
            if step > max_step:
                max_step = step
            step_map.setdefault(step, [])
            step_map[step].append(r)
            if props.get('stepLabel') and step not in step_labels:
                step_labels[step] = props['stepLabel']
            if props.get('stepDesc') and step not in step_descs:
                step_descs[step] = props['stepDesc']
        if max_step <= 1:
            return [{'step': 1, 'label': '表单填写', 'description': ''}]
        return [{
            'step': i,
            'label': step_labels.get(i) or f'第{i}步',
            'description': step_descs.get(i, ''),
        } for i in range(1, max_step + 1)]

    @property
    def step_group_json(self):
        """步骤分组 JSON，直接注入模板"""
        import json
        return json.dumps(self.step_groups, ensure_ascii=False)

    def get_step_fields(self, step):
        """获取指定步骤的所有字段名列表，用于审批时校验和过滤数据"""
        return [
            r.get('field') for r in (self.form_config or [])
            if r.get('field') and int((r.get('props') or {}).get('step', 1)) == step
        ]

    def get_field_step_map(self):
        """返回 {field_name: step_number} 映射"""
        return {
            r.get('field'): int((r.get('props') or {}).get('step', 1))
            for r in (self.form_config or [])
            if r.get('field')
        }

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
        verbose_name = '表单提交'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    @property
    def current_approval_node(self):
        """当前审批节点名称（流程运行时）"""
        if not self.workflow_instance_id or self.workflow_instance.status != 'RUNNING':
            return ''
        task = self.workflow_instance.tasks.filter(status='PENDING').order_by('created_at').first()
        return task.display_name if task else ''

    @property
    def current_approver(self):
        """当前审批人（流程运行时）"""
        if not self.workflow_instance_id or self.workflow_instance.status != 'RUNNING':
            return ''
        task = self.workflow_instance.tasks.filter(status='PENDING').order_by('created_at').first()
        if not task:
            return ''
        if task.assigned_to:
            return task.assigned_to.username
        return '待签收'

    @property
    def status_css_class(self):
        """状态徽章 CSS 类名"""
        return 'bg-primary' if self.status == 'SUBMITTED' else 'bg-secondary'

    def __str__(self):
        return f'{self.template.name} - {self.submitted_by} ({self.get_status_display()})'
