from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import (
    OEM, 
    Customer, ProjectRepository, ProjectFile, OEMStandardFile, ExternalMemberActivity
)


# ==========================================
# 1. 外部会员行为监控
# ==========================================
@admin.register(ExternalMemberActivity)
class ExternalMemberActivityAdmin(admin.ModelAdmin):
    list_display = ('member_info', 'action', 'target_name', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('member_token', 'target_name')
    readonly_fields = ('member_token', 'action', 'target_name', 'timestamp')

    def member_info(self, obj):
        customer = Customer.objects.filter(member_token=obj.member_token).first()
        if customer: return format_html('<span class="badge bg-blue-lt">客户: {}</span>', customer.company_name)
        oem = OEM.objects.filter(member_token=obj.member_token).first()
        if oem: return format_html('<span class="badge bg-azure-lt">主机厂: {}</span>', oem.name)
        if obj.member_token and obj.member_token.startswith('staff_'): return format_html('<span class="badge bg-green-lt">内部员工</span>')
        return f"未知令牌: {obj.member_token[:8]}"
    
    member_info.short_description = '身份来源'


# ==========================================
# 2. OEM管理 (用户画像)
# ==========================================
@admin.register(OEM)
class OEMAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'user', 'is_active', 'view_activity_link')
    search_fields = ('name', 'short_name')
    autocomplete_fields = ['user']
    
    def view_activity_link(self, obj):
        url = reverse('admin:app_repository_externalmemberactivity_changelist') + f"?q={obj.member_token}"
        return format_html('<a href="{}">查看手册行为</a>', url)
    view_activity_link.short_description = '手册活跃度'


@admin.register(OEMStandardFile)
class OEMStandardFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'oem', 'file_type', 'version', 'uploaded_at')
    list_filter = ('file_type', 'oem')
    search_fields = ('name', 'oem__name')


# ==========================================
# 3. 客户库管理 (用户画像)
# ==========================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'short_name', 'user', 'is_active', 'view_activity_link')
    search_fields = ('company_name', 'short_name', 'contact_name')
    autocomplete_fields = ['user']
    actions = ['reset_password']

    def view_activity_link(self, obj):
        url = reverse('admin:app_repository_externalmemberactivity_changelist') + f"?q={obj.member_token}"
        return format_html('<a href="{}">查看手册行为</a>', url)
    view_activity_link.short_description = '手册活跃度'

    @admin.action(description="重置选中客户的密码 (Sunwill@123)")
    def reset_password(self, request, queryset):
        for obj in queryset:
            if obj.user:
                obj.user.set_password('Sunwill@123')
                obj.user.save()
        self.message_user(request, "选中的客户密码已重置为: Sunwill@123")


# ==========================================
# 4. 项目档案管理 (直接基于 User 进行权限隔离)
# ==========================================
class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    fields = ('file', 'name', 'file_type', 'version', 'description')
    extra = 1


@admin.register(ProjectRepository)
class ProjectRepositoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'customer', 'oem', 'salesperson', 'material', 'updated_at')
    search_fields = ('project__name', 'customer__company_name', 'oem__name', 'product_name')
    list_filter = ('salesperson', 'updated_at')
    autocomplete_fields = ['project', 'customer', 'oem', 'material', 'salesperson'] # salesperson 也是 autocomplete 了
    inlines = [ProjectFileInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # 如果不是超级管理员，则判断当前用户是否被指定为负责业务员
        return qs.filter(salesperson=request.user)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "customer":
                customer_ids = ProjectRepository.objects.filter(salesperson=request.user).values_list('customer_id', flat=True).distinct()
                kwargs["queryset"] = Customer.objects.filter(id__in=customer_ids)
            elif db_field.name == "oem":
                oem_ids = ProjectRepository.objects.filter(salesperson=request.user).values_list('oem_id', flat=True).distinct()
                kwargs["queryset"] = OEM.objects.filter(id__in=oem_ids)
            elif db_field.name == "salesperson":
                from django.contrib.auth.models import User
                kwargs["queryset"] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'repository', 'file_type', 'version', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('repository__project__name', 'name', 'description')
    autocomplete_fields = ['repository']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(repository__salesperson=request.user)
