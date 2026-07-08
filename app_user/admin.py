"""Django Admin 配置。注册 User、Department、ReviewGroup、WorkGroup、PermissionGroup 的管理界面。

导出: PermissionGroupAdmin, DepartmentAdmin, MyUserAdmin, ReviewGroupAdmin, WorkGroupAdmin。
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import Group
from .models import User, Department, Subsidiary, ReviewGroup, WorkGroup, PermissionGroup

admin.site.unregister(Group)


@admin.register(PermissionGroup)
class PermissionGroupAdmin(GroupAdmin):
    """PermissionGroup（auth.Group 代理）的 Admin 配置。"""
    pass


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
    add_fieldsets = UserAdmin.add_fieldsets + (
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
