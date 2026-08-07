"""Django Admin 配置。注册全部 app_user 模型的管理界面。"""

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.shortcuts import render
from .models import (
    User, Department, Subsidiary, OrgRole, OrgRoleAssignment,
    ReviewGroup, WorkGroup, PermissionGroup,
    UserRole, RoleGroup, ModuleAccessConfig,
    SidebarModule, SidebarSubItem,
)

admin.site.unregister(Group)


class PermissionGroupForm(forms.ModelForm):
    """自定义表单，显式声明 user_set 反向 M2M 字段。"""
    user_set = forms.ModelMultipleChoiceField(
        queryset=User.objects.all().order_by('username'),
        required=False,
        widget=FilteredSelectMultiple('用户', False),
    )

    class Meta:
        model = PermissionGroup
        fields = '__all__'


@admin.register(PermissionGroup)
class PermissionGroupAdmin(GroupAdmin):
    """PermissionGroup（auth.Group 代理）的 Admin 配置。

    分组详情页可同时管理：组成员 + Django 权限码。
    """
    form = PermissionGroupForm
    fieldsets = (
        (None, {'fields': ('name',)}),
        ('组成员', {'fields': ('user_set',)}),
        ('权限码', {'fields': ('permissions',)}),
    )
    filter_horizontal = ('permissions',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj:
            form.base_fields['user_set'].initial = obj.user_set.all()
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.user_set.set(form.cleaned_data.get('user_set', []))


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Department 的 Admin 配置：列表显示 name/code/description/created_at，支持搜索和排序。"""
    list_display = ('name', 'code', 'description', 'created_at')
    search_fields = ('name', 'code')
    ordering = ('name',)


@admin.register(Subsidiary)
class SubsidiaryAdmin(admin.ModelAdmin):
    """Subsidiary 的 Admin 配置：列表显示 name/code/description/created_at，支持搜索和排序。"""
    list_display = ('name', 'code', 'description', 'created_at')
    search_fields = ('name', 'code')
    ordering = ('name',)
    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'description'),
        }),
    )


class OrgRoleAssignmentInline(admin.TabularInline):
    """OrgRole 的内联指派编辑器。在角色详情页直接管理所有指派。"""
    model = OrgRoleAssignment
    extra = 1
    fields = ('user', 'workgroup', 'department', 'subsidiary', 'is_primary')
    autocomplete_fields = ('user',)
    verbose_name = "角色人员指派"
    verbose_name_plural = "角色人员指派（在此直接添加/编辑该角色在各组织单元中的负责人）"


@admin.register(OrgRole)
class OrgRoleAdmin(admin.ModelAdmin):
    """OrgRole 的 Admin 配置。支持内联编辑角色指派 + 组织架构总览矩阵。

    操作指引：
        第一步：在此创建组织角色（如「组长」「部门经理」）
        第二步：在下方 inline 表格中将人员指派到具体的组织单元
        第三步：到 app_workflow →「Task 节点配置」中关联 task_id 与组织角色
        第四步：点击右上角「组织架构总览」查看完整的指派矩阵
    """
    list_display = ('code', 'name', 'scope', 'allow_escalation', 'description', 'created_at')
    list_filter = ('scope',)
    search_fields = ('code', 'name')
    ordering = ('scope', 'name')
    inlines = [OrgRoleAssignmentInline]
    fieldsets = (
        ('角色基本信息', {
            'fields': ('code', 'name', 'scope', 'allow_escalation'),
        }),
        ('补充说明', {
            'fields': ('description',),
        }),
    )

    # ── 自定义 URL ──────────────────────────────────────────

    def get_urls(self):
        """注入自定义 URL：说明页 + 组织架构总览矩阵。"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('overview/', self.admin_site.admin_view(self.org_role_overview_view),
                 name='app_user_org_role_overview'),
            path('org-matrix/', self.admin_site.admin_view(self.org_structure_matrix_view),
                 name='app_user_org_structure_matrix'),
        ]
        return custom_urls + urls

    def org_role_overview_view(self, request):
        """组织角色体系说明页。"""
        context = {
            **self.admin_site.each_context(request),
            'title': '组织角色体系 — 说明',
            'opts': self.model._meta,
        }
        return render(request, 'admin/app_user/org_role_overview.html', context)

    def org_structure_matrix_view(self, request):
        """组织架构总览矩阵视图 — 按作用域分段展示。

        三个独立区块：
            — 子公司/基地级角色 × 子公司列
            — 部门级角色 × 部门列
            — 工作组级角色 × 工作组列
        每个角色只展示其作用域匹配的组织单元，不会出现无关列。
        """
        # ── 预加载所有指派 ──
        all_assignments = list(OrgRoleAssignment.objects.select_related(
            'role', 'user', 'subsidiary', 'department', 'workgroup',
        ))
        assignment_map = {}
        for a in all_assignments:
            if a.subsidiary:
                assignment_map[(a.role.code, 'subsidiary', a.subsidiary_id)] = a
            if a.department:
                assignment_map[(a.role.code, 'department', a.department_id)] = a
            if a.workgroup:
                assignment_map[(a.role.code, 'workgroup', a.workgroup_id)] = a

        # ── 构建三个作用域的独立数据 ──
        scope_configs = [
            {
                'scope': 'subsidiary',
                'label': '子公司 / 基地级角色',
                'units': [
                    {'type': 'subsidiary', 'name': s.name, 'id': s.id,
                     'full_path': str(s), 'get_type_display': '子公司/基地'}
                    for s in Subsidiary.objects.all().order_by('name')
                ],
            },
            {
                'scope': 'department',
                'label': '部门级角色',
                'units': [
                    {'type': 'department', 'name': d.name, 'id': d.id,
                     'full_path': str(d), 'get_type_display': '部门'}
                    for d in Department.objects.all().order_by('name')
                ],
            },
            {
                'scope': 'workgroup',
                'label': '工作组级角色',
                'units': [
                    {'type': 'workgroup', 'name': wg.name, 'id': wg.id,
                     'full_path': f'{wg.department.name} ＞ {wg.name}',
                     'get_type_display': '工作组'}
                    for wg in WorkGroup.objects.filter(is_active=True)
                    .select_related('department').order_by('department__name', 'name')
                ],
            },
        ]

        # ── 为每个作用域构建角色行 ──
        total_assignments = 0
        total_cells = 0
        assigned_cells = 0

        for cfg in scope_configs:
            roles = list(OrgRole.objects.filter(scope=cfg['scope']).order_by('name'))
            cfg['roles'] = roles
            cfg['has_data'] = len(roles) > 0 and len(cfg['units']) > 0
            cfg['rows'] = []

            for role in roles:
                cells = []
                for unit in cfg['units']:
                    key = (role.code, unit['type'], unit['id'])
                    assignment = assignment_map.get(key)
                    cells.append({'assignment': assignment})
                    total_cells += 1
                    if assignment:
                        assigned_cells += 1

                cfg['rows'].append({
                    'name': role.name,
                    'code': role.code,
                    'scope': role.scope,
                    'allow_escalation': role.allow_escalation,
                    'get_scope_display': role.get_scope_display(),
                    'cells': cells,
                    'columns': cfg['units'],
                })
                total_assignments += OrgRoleAssignment.objects.filter(role=role).count()

        # ── 统计 ──
        stats = {
            'total_roles': OrgRole.objects.count(),
            'total_assignments': OrgRoleAssignment.objects.count(),
            'total_units': sum(len(c['units']) for c in scope_configs),
            'coverage': round(assigned_cells / max(total_cells, 1) * 100),
        }

        context = {
            **self.admin_site.each_context(request),
            'title': '组织架构总览 — 角色指派矩阵',
            'scope_configs': scope_configs,
            'stats': stats,
            'opts': self.model._meta,
        }
        return render(request, 'admin/app_user/org_structure_matrix.html', context)

    # ── Changelist 入口按钮 ──────────────────────────────────

    def changelist_view(self, request, extra_context=None):
        """在列表页顶部注入快捷入口。"""
        from django.urls import reverse
        from django.utils.html import format_html
        extra_context = extra_context or {}
        overview_url = reverse('admin:app_user_org_role_overview')
        extra_context['matrix_url'] = reverse('admin:app_user_org_structure_matrix')
        self.message_user(
            request,
            format_html(
                '💡 <a href="{}" style="font-weight:600;">点击查看「组织角色体系」说明</a>'
                ' &nbsp;|&nbsp;'
                '<a href="{}">组织架构总览矩阵</a>',
                overview_url,
                extra_context['matrix_url'],
            ),
            level='info',
        )
        return super().changelist_view(request, extra_context)


@admin.register(OrgRoleAssignment)
class OrgRoleAssignmentAdmin(admin.ModelAdmin):
    """OrgRoleAssignment 的 Admin 配置。列表显示角色-用户-组织单元映射。

    操作指引：
        在此将具体用户指派为某个组织单元的某个角色负责人。
        例如：张三 在「配方组」担任「组长」；李四 在「研发中心」担任「部门经理」。
    """
    list_display = ('role', 'user', 'get_org_unit', 'is_primary', 'created_at')
    list_filter = ('role', 'is_primary')
    search_fields = ('user__username', 'role__name', 'role__code')
    autocomplete_fields = ('user',)
    fieldsets = (
        ('角色与人员', {
            'fields': ('role', 'user'),
        }),
        ('组织单元归属', {
            'fields': ('subsidiary', 'department', 'workgroup'),
        }),
        ('指派属性', {
            'fields': ('is_primary',),
        }),
    )

    @admin.display(description='组织单元')
    def get_org_unit(self, obj):
        """返回该指派关联的组织单元名称。"""
        return str(obj.workgroup or obj.department or obj.subsidiary or '—')

    def changelist_view(self, request, extra_context=None):
        from django.urls import reverse
        from django.utils.html import format_html
        self.message_user(
            request,
            format_html(
                '💡 <a href="{}" style="font-weight:600;">点击查看「组织角色体系」说明</a>',
                reverse('admin:app_user_org_role_overview'),
            ),
            level='info',
        )
        return super().changelist_view(request, extra_context)


class AdminUserCreationForm(UserCreationForm):
    """Admin 新增用户表单：邮箱必填且唯一（作为登录账号）。"""
    email = forms.EmailField(label="邮箱", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        """邮箱转小写并校验唯一性。Raises: ValidationError。Returns: 归一化后的邮箱。"""
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("该邮箱已被使用")
        return email


@admin.register(User)
class MyUserAdmin(UserAdmin):
    """自定义 User Admin。展示 L1~L5 五层权限字段，按权限模型分层组织 fieldsets。"""
    # L1 角色 / L2 等级 / L3 权限组 / L4 部门 / L5 工作组
    list_display = (
        'username', 'email',
        'user_type',           # L1: 角色白名单
        'user_level',          # L2: 用户等级
        'get_groups',          # L3: Django 权限组（权限码容器）
        'subsidiary',          # 子公司/基地归属
        'department',          # L4: 部门数据隔离
        'get_work_groups',     # L5: 工作组数据隔离
        'phone', 'is_staff',
    )
    list_filter = ('user_type', 'is_staff', 'is_superuser', 'is_active', 'subsidiary', 'department')
    
    # 在详情页管理 5D 权限和公司归属
    fieldsets = UserAdmin.fieldsets + (
        ('权限层级配置 (L1 角色 / L2 等级 / L4 部门)', {
            'fields': ('user_type', 'user_level', 'subsidiary', 'department'),
        }),
        ('业务归属 (External)', {
            'fields': ('associated_customer', 'associated_oem', 'member_token'),
        }),
        ('个人详细资料', {
            'fields': ('job_title', 'phone', 'address', 'description'),
        }),
    )
    
    # 账号创建时的快捷字段
    add_form = AdminUserCreationForm  # 新增用户时邮箱必填且唯一
    add_fieldsets = (
        (None, {
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('初始业务分配', {
            'fields': ('user_type', 'subsidiary', 'department', 'phone'),
        }),
    )

    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('username',)
    readonly_fields = ('member_token',) # 令牌设为只读，由系统自动维护

    @admin.display(description='[L3] 权限组')
    def get_groups(self, obj):
        """返回用户所属权限组的逗号分隔列表。Returns: 组名字符串或 '—'。"""
        groups = obj.groups.all()
        if not groups:
            return '—'
        return ', '.join(g.name for g in groups)

    @admin.display(description='[L5] 工作组')
    def get_work_groups(self, obj):
        """返回用户所属工作组的逗号分隔列表。Returns: 工作组名字符串或 '—'。"""
        wgs = obj.work_groups.filter(is_active=True)
        if not wgs:
            return '—'
        return ', '.join(wg.name for wg in wgs)


@admin.register(ReviewGroup)
class ReviewGroupAdmin(admin.ModelAdmin):
    """ReviewGroup 的 Admin 配置。"""
    list_display = ('name', 'department', 'is_active', 'member_count', 'created_at', 'updated_at')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'description')
    ordering = ('name',)
    filter_horizontal = ('members',)
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'description', 'is_active'),
        }),
        ('成员与范围', {
            'fields': ('members', 'department'),
        }),
    )

    @admin.display(description='成员数')
    def member_count(self, obj):
        """返回审核组成员数。Returns: 整数。"""
        return obj.members.count()

    def changelist_view(self, request, extra_context=None):
        from django.urls import reverse
        from django.utils.html import format_html
        self.message_user(
            request,
            format_html(
                '💡 <a href="{}" style="font-weight:600;">点击查看「组织角色体系」说明</a>',
                reverse('admin:app_user_org_role_overview'),
            ),
            level='info',
        )
        return super().changelist_view(request, extra_context)


@admin.register(WorkGroup)
class WorkGroupAdmin(admin.ModelAdmin):
    """WorkGroup 的 Admin 配置。"""
    list_display = ('name', 'department', 'is_active', 'member_count', 'created_at', 'updated_at')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'description')
    ordering = ('department', 'name',)
    filter_horizontal = ('members',)
    fieldsets = (
        ('基本信息', {'fields': ('name', 'department', 'description', 'is_active')}),
        ('组成员', {'fields': ('members',)}),
    )

    @admin.display(description='成员数')
    def member_count(self, obj):
        """返回工作组成员数。Returns: 整数。"""
        return obj.members.count()


# ============================================================
# 动态 RBAC 权限体系 — Admin 注册
# ============================================================
# 注意：RBAC 缓存失效统一由 app_user.signals 的 post_save / post_delete /
# m2m_changed 信号负责，覆盖 Admin 与 shell 等所有变更路径，
# 此处不再调用 IdentityService.invalidate_cache()，避免双重失效。

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_internal', 'sort_order', 'is_active')
    list_filter = ('is_internal', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('sort_order', 'code')


@admin.register(RoleGroup)
class RoleGroupAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    search_fields = ('code', 'name')
    filter_horizontal = ('roles',)


@admin.register(ModuleAccessConfig)
class ModuleAccessConfigAdmin(admin.ModelAdmin):
    list_display = ('module_code', 'module_name', 'min_level',
                    'enforce_dept_isolation', 'enforce_group_isolation',
                    'l4_bypass_min_level', 'l5_bypass_min_level', 'is_active')
    list_editable = ('l4_bypass_min_level', 'l5_bypass_min_level')
    list_filter = ('is_active', 'enforce_dept_isolation', 'enforce_group_isolation')
    search_fields = ('module_code', 'module_name')
    filter_horizontal = ('role_groups',)

    # ── 自定义 URL：权限体系说明页 ──

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('overview/', self.admin_site.admin_view(self.rbac_overview_view),
                 name='app_user_rbac_overview'),
        ]
        return custom_urls + urls

    def rbac_overview_view(self, request):
        """权限管控中心 — 全套权限体系说明页。"""
        context = {
            **self.admin_site.each_context(request),
            'title': '权限管控中心 — 全套权限体系说明',
            'opts': self.model._meta,
        }
        return render(request, 'admin/app_user/rbac_overview.html', context)

    def changelist_view(self, request, extra_context=None):
        """在列表页顶部注入说明页链接。"""
        from django.urls import reverse
        from django.utils.html import format_html
        extra_context = extra_context or {}
        overview_url = reverse('admin:app_user_rbac_overview')
        self.message_user(
            request,
            format_html(
                '💡 <a href="{}" style="font-weight:600;">点击查看「权限管控中心」全套权限体系说明</a>',
                overview_url,
            ),
            level='info',
        )
        return super().changelist_view(request, extra_context)


class SidebarSubItemInline(admin.TabularInline):
    model = SidebarSubItem
    extra = 0
    can_delete = False
    fields = ('name', 'url_name', 'role_groups', 'min_level', 'permissions', 'sort_order', 'is_active')
    # menu_modules.py 控制的字段只读；管理员只能调整 role_groups / min_level / sort_order / is_active
    filter_horizontal = ('role_groups',)

    def has_add_permission(self, request, obj=None):
        return False
    readonly_fields = ('name', 'url_name', 'permissions')


@admin.register(SidebarModule)
class SidebarModuleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'module_access', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    # menu_modules.py 控制的字段只读；管理员只能调整 sort_order / is_active
    readonly_fields = ('code', 'name', 'icon', 'url_name', 'module_access')
    inlines = [SidebarSubItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
