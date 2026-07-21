from django import forms
from django.core.exceptions import ValidationError
from .models import Project, ProjectNode, ProjectMember, NodeScoreRule, ProjectSalesMember, FailureReason, FeedbackType
from django.contrib.auth import get_user_model
from django.db.models import Sum
from common_utils.filters import TablerFormMixin # 从 common_utils 导入通用的 TablerFormMixin
from common_utils.forms import UserPickerWidget

User = get_user_model()

class ProjectForm(TablerFormMixin, forms.ModelForm):
    submission_comment = forms.CharField(
        label="提交意见",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': '请说明本次编辑项目信息的原因（如：项目名称变更、等级调整等）',
        }),
        required=False,
        help_text="编辑项目基本信息需填写变更原因并提交审批，审批通过后生效",
    )

    class Meta:
        model = Project
        fields = ['code', 'name', 'grade', 'material', 'description']
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': '请输入项目编码，留空则自动生成'}),
            'name': forms.TextInput(attrs={'placeholder': '请输入项目名称'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'material'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': '请输入项目背景、目标等详细描述...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app_material.models.material import MaterialLibrary
        if not self.data:
            instance = kwargs.get('instance')
            if instance and instance.material_id:
                self.fields['material'].queryset = MaterialLibrary.objects.filter(pk=instance.material_id)
            else:
                self.fields['material'].queryset = MaterialLibrary.objects.none()

        # 编辑已有项目 + 配置了审批流程 → submission_comment 必填
        instance = kwargs.get('instance')
        if instance and instance.pk:
            from .models import ProjectConfig
            if ProjectConfig.get().default_project_edit_approval_workflow_id:
                self.fields['submission_comment'].required = True


# 确保 ProjectNodeUpdateForm 也继承 TablerFormMixin
class ProjectNodeUpdateForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectNode
        fields = ['status', 'remark']
        widgets = {
            # status 字段会通过 TablerFormMixin 自动获得 form-select 样式
            'status': forms.Select(),
            'remark': forms.Textarea(attrs={'rows': 12, 'placeholder': '填写备注信息...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 【优化】使用模型类方法获取用户可选的状态选项
        self.fields['status'].choices = ProjectNode.get_user_selectable_choices()


# 【新增】项目成员管理表单
class ProjectMemberForm(TablerFormMixin, forms.ModelForm):
    user = forms.CharField(
        widget=UserPickerWidget(multi=False, title='选择协同成员'),
        required=True,
    )

    class Meta:
        model = ProjectMember
        fields = ['user', 'role', 'workload_share']
        widgets = {
            'workload_share': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '1.0'}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)

        # 【修改】显式设置工作量权重的初始值为 0.00
        if not self.instance.pk:
            self.initial['workload_share'] = 0.00

    def clean_user(self):
        """将 UserPickerWidget 返回的用户 ID 字符串转为 User 实例"""
        user_id = self.cleaned_data.get('user')
        if not user_id:
            raise ValidationError('请选择一位成员')
        try:
            return User.objects.get(pk=int(user_id), is_active=True)
        except (ValueError, TypeError, User.DoesNotExist):
            raise ValidationError('所选用户不存在或已禁用')

    def clean_workload_share(self):
        workload = self.cleaned_data.get('workload_share')

        if self.project:
            # 计算当前项目已有的总权重
            existing_total = ProjectMember.objects.filter(project=self.project)

            # 如果是编辑现有成员，要排除掉当前成员的旧权重
            if self.instance.pk:
                existing_total = existing_total.exclude(pk=self.instance.pk)

            total_sum = existing_total.aggregate(Sum('workload_share'))['workload_share__sum'] or 0

            # 校验：已有总和 + 准备录入的权重
            if total_sum + workload > 1.0:
                available = 1.0 - total_sum
                raise forms.ValidationError(
                    f"总工作量不能超过 100%。当前剩余可用配额仅剩: {available:.2f} ({(available*100):.0f}%)"
                )

        return workload


# 【新增】销售成员表单
class ProjectSalesMemberForm(TablerFormMixin, forms.ModelForm):
    user = forms.CharField(
        widget=UserPickerWidget(multi=False, title='选择销售成员'),
        required=True,
    )

    class Meta:
        model = ProjectSalesMember
        fields = ['user', 'workload_share']
        widgets = {
            'workload_share': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '1.0'}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['workload_share'] = 0.00

    def clean_user(self):
        """将 UserPickerWidget 返回的用户 ID 字符串转为 User 实例"""
        user_id = self.cleaned_data.get('user')
        if not user_id:
            raise ValidationError('请选择一位成员')
        try:
            return User.objects.get(pk=int(user_id), is_active=True)
        except (ValueError, TypeError, User.DoesNotExist):
            raise ValidationError('所选用户不存在或已禁用')

    def clean_workload_share(self):
        workload = self.cleaned_data.get('workload_share')

        if self.project:
            existing_total = ProjectSalesMember.objects.filter(project=self.project)
            if self.instance.pk:
                existing_total = existing_total.exclude(pk=self.instance.pk)

            total_sum = existing_total.aggregate(Sum('workload_share'))['workload_share__sum'] or 0

            if total_sum + workload > 1.0:
                available = 1.0 - total_sum
                raise forms.ValidationError(
                    f"销售总工作量不能超过 100%。当前剩余可用配额仅剩: {available:.2f} ({(available*100):.0f}%)"
                )

        return workload


# 【新增】绩效评分规则表单
class NodeScoreRuleForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = NodeScoreRule
        fields = ['name', 'score_value', 'rule_type', 'trigger_stage', 'trigger_status', 'is_multiple_rounds', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# ---- 不合格原因管理 ----

class FailureReasonForm(TablerFormMixin, forms.ModelForm):
    """不合格原因管理表单"""
    class Meta:
        model = FailureReason
        fields = ['name', 'code', 'order', 'is_active', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


# ---- 客户意见类型管理 ----

class FeedbackTypeForm(TablerFormMixin, forms.ModelForm):
    """客户意见类型管理表单"""
    class Meta:
        model = FeedbackType
        fields = ['name', 'code', 'order', 'is_active', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
