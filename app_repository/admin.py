from django.contrib import admin
from .models import MaterialType, ApplicationScenario, MaterialLibrary, Customer, ProjectRepository

@admin.register(MaterialLibrary)
class MaterialLibraryAdmin(admin.ModelAdmin):
    list_display = ('grade_name', 'manufacturer', 'category', 'density', 'file_tds')
    search_fields = ('grade_name', 'manufacturer')
    list_filter = ('category',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_name', 'phone')
    search_fields = ('company_name', 'contact_name')

# 注册其他模型
admin.site.register(MaterialType)
admin.site.register(ApplicationScenario)
# 项目档案通常在前端管理，但在后台留个入口方便查错
admin.site.register(ProjectRepository)