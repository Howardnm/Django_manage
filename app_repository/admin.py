from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import (
    OEM, Customer, ProjectRepository, ProjectRepositoryFieldChange,
    ExternalMemberActivity, GradeFactor
)

User = get_user_model()

# ==========================================
# 0. 等级因子配置
# ==========================================
@admin.register(GradeFactor)
class GradeFactorAdmin(admin.ModelAdmin):
    list_display = ('name', 'factor', 'description')
    search_fields = ('name',)
    list_editable = ('factor',)


# ==========================================
# 0. 关联账号内联 (核心重构：在公司页管理账号)
# ==========================================
class UserContactInline(admin.TabularInline):
    model = User
    fields = ('username', 'first_name', 'phone', 'user_type', 'is_active')
    extra = 0
    show_change_link = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('department')

class CustomerUserInline(UserContactInline):
    fk_name = 'associated_customer'
    verbose_name = "关联客户联系人"

class OEMUserInline(UserContactInline):
    fk_name = 'associated_oem'
    verbose_name = "关联主机厂对接人"


# ==========================================
# 1. 外部会员行为监控
# ==========================================
@admin.register(ExternalMemberActivity)
class ExternalMemberActivityAdmin(admin.ModelAdmin):
    list_display = ('member_identity', 'action_label', 'target_name', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('member_token', 'target_name')
    readonly_fields = ('member_token', 'action', 'target_name', 'timestamp')

    def member_identity(self, obj):
        user = User.objects.filter(member_token=obj.member_token).select_related('associated_customer', 'associated_oem').first()
        if user:
            if user.associated_customer:
                return format_html('<span class="badge bg-blue-lt">客户: {} ({})</span>', user.associated_customer.company_name, user.get_full_name() or user.username)
            if user.associated_oem:
                return format_html('<span class="badge bg-azure-lt">主机厂: {} ({})</span>', user.associated_oem.name, user.get_full_name() or user.username)
            return format_html('<span class="badge bg-green-lt">内部员工: {}</span>', user.username)
        return f"未知令牌: {obj.member_token[:8]}"

    def action_label(self, obj):
        color = 'red' if 'DOWNLOAD' in obj.action else 'azure'
        return format_html('<span class="badge bg-{}-lt">{}</span>', color, obj.action)

    member_identity.short_description = '访问者身份'
    action_label.short_description = '行为'


# ==========================================
# 2. OEM管理 (公司级)
# ==========================================
@admin.register(OEM)
class OEMAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'website', 'contact_count', 'created_at')
    search_fields = ('name', 'short_name')
    inlines = [OEMUserInline]

    def contact_count(self, obj):
        return obj.members.count()
    contact_count.short_description = '关联账号数'


# ==========================================
# 3. 客户公司管理
# ==========================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'short_name', 'contact_count', 'created_at')
    search_fields = ('company_name', 'short_name')
    inlines = [CustomerUserInline]

    def contact_count(self, obj):
        return obj.members.count()
    contact_count.short_description = '关联账号数'


# ==========================================
# 4. 项目商务档案管理
# ==========================================
@admin.register(ProjectRepository)
class ProjectRepositoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'customer', 'oem', 'salesperson',
                    'target_cost', 'competitor_price', 'estimated_order_volume',
                    'approval_status', 'updated_at')
    search_fields = ('project__name', 'customer__company_name', 'oem__name', 'product_name')
    list_filter = ('salesperson', 'updated_at')
    autocomplete_fields = ['project', 'customer', 'oem', 'salesperson']
    readonly_fields = ('approval_status',)

    def approval_status(self, obj):
        if obj.workflow_instance and obj.workflow_instance.status == 'RUNNING':
            return format_html(
                '<span class="badge bg-purple-lt">审批中</span>'
            )
        return '-'
    approval_status.short_description = '审批状态'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        return qs.filter(salesperson=request.user)


# ==========================================
# 4.1 档案字段变更记录
# ==========================================
@admin.register(ProjectRepositoryFieldChange)
class ProjectRepositoryFieldChangeAdmin(admin.ModelAdmin):
    list_display = ('repository', 'status_badge', 'submitted_by',
                    'customer', 'oem', 'product_name',
                    'target_cost', 'competitor_price', 'estimated_order_volume',
                    'created_at', 'resolved_at')
    list_filter = ('status', 'created_at')
    search_fields = ('repository__project__name', 'submitted_by__username',
                     'submission_comment', 'product_name',
                     'customer__company_name', 'oem__name')
    readonly_fields = ('created_at', 'resolved_at')
    autocomplete_fields = ['repository', 'submitted_by', 'customer', 'oem', 'salesperson']

    def status_badge(self, obj):
        css = {
            'PENDING': 'bg-purple-lt',
            'APPROVED': 'bg-green-lt',
            'REJECTED': 'bg-red-lt',
        }.get(obj.status, 'bg-secondary-lt')
        return format_html(
            '<span class="badge {}">{}</span>', css, obj.get_status_display()
        )
    status_badge.short_description = '状态'
