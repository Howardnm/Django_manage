from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'description', 'created_at')
    search_fields = ('name', 'code')
    ordering = ('name',)


@admin.register(User)
class MyUserAdmin(UserAdmin):
    """
    自定义用户 Admin，支持新字段展示与编辑。
    """
    # 核心修正：移除 list_display 中不存在的 company 字段，增加公司归属字段
    list_display = ('username', 'email', 'user_type', 'user_level', 'department', 'get_groups', 'phone', 'is_staff')
    list_filter = ('user_type', 'is_staff', 'is_superuser', 'is_active', 'department')
    
    # 在详情页管理 4D 权限和公司归属
    fieldsets = UserAdmin.fieldsets + (
        ('4D 权限架构', {
            'fields': ('user_type', 'user_level', 'department'),
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
            'fields': ('user_type', 'department', 'phone'),
        }),
    )

    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('username',)
    readonly_fields = ('member_token',) # 令牌设为只读，由系统自动维护

    @admin.display(description='用户组')
    def get_groups(self, obj):
        groups = obj.groups.all()
        if not groups:
            return '—'
        return ', '.join(g.name for g in groups)
