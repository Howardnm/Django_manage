from django.contrib import admin
from .models import (
    OEM, Salesperson,
    Customer, ProjectRepository, ProjectFile, OEMStandardFile
)


# ==========================================
# 1. OEM管理
# ==========================================

@admin.register(OEM)
class OEMAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'description')
    search_fields = ('name', 'short_name')


@admin.register(OEMStandardFile)
class OEMStandardFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'oem', 'file_type', 'version', 'uploaded_at')
    list_filter = ('file_type', 'oem')
    search_fields = ('name', 'oem__name')


# ==========================================
# 1. 业务员管理
# ==========================================
@admin.register(Salesperson)
class SalespersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email')
    search_fields = ('name', 'phone', 'email')


# ==========================================
# 3. 客户库管理
# ==========================================
@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'short_name', 'contact_name', 'phone', 'tech_contact')
    search_fields = ('company_name', 'short_name', 'contact_name')


# ==========================================
# 4. 项目档案管理
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
    autocomplete_fields = ['project', 'customer', 'oem', 'salesperson', 'material']
    inlines = [ProjectFileInline]


@admin.register(ProjectFile)
class ProjectFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'repository', 'file_type', 'version', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('repository__project__name', 'name', 'description')
    autocomplete_fields = ['repository']
