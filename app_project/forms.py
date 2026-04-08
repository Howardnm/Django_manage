from django import forms
from .models import Project, ProjectNode, ProjectMember, NodeScoreRule
from django.contrib.auth.models import User
from django.db.models import Sum
from common_utils.filters import TablerFormMixin # 从 common_utils 导入通用的 TablerFormMixin


class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label='密码')
    confirm_password = forms.CharField(widget=forms.PasswordInput, label='确认密码')

    class Meta:
        model = User
        fields = ['username', 'password', 'confirm_password']

    # 自定义表单级别的验证方法，名称必须是clean
    def clean(self):
        cleaned_data = super().clean()  # 调用父类的clean方法，获取清理后的数据
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("密码和确认密码不匹配。")
        return cleaned_data


class ProjectForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '请输入项目名称'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': '请输入项目背景、目标等详细描述...'}),
        }


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


# 【新增】项目成员管理表单
class ProjectMemberForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = ProjectMember
        fields = ['user', 'role', 'workload_share']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-select-search'}),
            'workload_share': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '1.0'}),
        }

    def __init__(self, *args, **kwargs):
        self.project = kwargs.pop('project', None)
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_active=True).order_by('username')
        
        # 【修改】显式设置工作量权重的初始值为 0.00
        if not self.instance.pk:
            self.initial['workload_share'] = 0.00

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


# 【新增】绩效评分规则表单
class NodeScoreRuleForm(TablerFormMixin, forms.ModelForm):
    class Meta:
        model = NodeScoreRule
        fields = ['name', 'score_value', 'trigger_stage', 'trigger_status', 'is_multiple_rounds', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
