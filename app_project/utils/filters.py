import django_filters
from django.db.models import Q
from app_project.models import Project, ProjectNode
from django import forms  # 引入 forms 用于定义 widget


class ProjectFilter(django_filters.FilterSet):
    # 1. 搜索框 (自定义 Widget 样式)
    # CharFilter 对应文本输入
    # method 指向一个自定义函数，因为我们要跨字段搜索 (name OR manager OR description)
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '搜名称/负责人/描述...'
        })
    )

    # 2. 排序 (Sort 参数)
    # OrderingFilter 自动处理排序，甚至支持 url?sort=-name (自动转倒序)
    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('name', 'name'),
            ('manager__username', 'manager'),  # 前端参数叫manager，对应数据库manager__username
        ),
        field_labels={
            'created_at': '创建时间',
            'name': '项目名称',
        },
        # 加上这句，它在模版 for field in filter.form 循环时，就会渲染成 <input type="hidden">
        # 这样既不会在界面上显示下拉框，提交表单时又能带上当前的 sort 值
        widget = forms.HiddenInput
    )

    # 3. 负责人筛选 (Manager 参数)
    # method 指向自定义函数，处理 'me' 这种特殊逻辑
    manager = django_filters.ChoiceFilter(
        method='filter_manager',
        label='负责人',
        # 定义下拉框选项
        choices=[('me', '只看我的')],
        # 定义空选项的显示文字
        empty_label="所有负责人",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 4. (未来扩展) 比如按状态筛选，一行代码搞定：
    # 3. 以后如果你想加“状态”筛选，只需要解开这行注释，HTML页面会自动出现下拉框
    status = django_filters.ChoiceFilter(
        choices=ProjectNode.STATUS_CHOICES,
        field_name='nodes__status',
        label='状态',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Project
        # fields 列表里的字段会自动生成默认的精确匹配查询
        fields = ['q', 'manager']  # 决定显示的顺序

    def filter_search(self, queryset, name, value):
        """自定义搜索逻辑"""
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(manager__username__icontains=value) |
            Q(description__icontains=value)
        )

    def filter_manager(self, queryset, name, value):
        """自定义负责人筛选逻辑"""
        if value == 'me':
            # self.request 是在 View 实例化 FilterSet 时传入的
            return queryset.filter(manager=self.request.user)
        return queryset
