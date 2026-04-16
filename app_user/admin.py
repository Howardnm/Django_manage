from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class MyUserAdmin(UserAdmin):
    """
    自定义用户 Admin，支持新字段展示与编辑
    """
    list_display = ('username', 'email', 'user_type', 'company', 'phone', 'is_staff')
    list_filter = ('user_type', 'is_staff', 'is_superuser', 'is_active', 'groups')
    
    # 在编辑页面的“个人信息”部分增加自定义字段
    fieldsets = UserAdmin.fieldsets + (
        ('业务扩展信息', {
            'fields': ('user_type', 'user_level', 'job_title', 'company', 'phone', 'address', 'description'),
        }),
    )
    
    # 在创建页面的字段 (可选)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('业务扩展信息', {
            'fields': ('user_type', 'company', 'phone'),
        }),
    )

    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone', 'company')
    ordering = ('username',)
