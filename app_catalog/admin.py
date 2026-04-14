from django.contrib import admin
from .models import CatalogCategory, CatalogProduct, MirrorScenario, MirrorCharacteristic, VisitorLog

# 1. 手册分类管理
@admin.register(CatalogCategory)
class CatalogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'remote_type_id', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('name',)

# 2. 镜像场景管理
@admin.register(MirrorScenario)
class MirrorScenarioAdmin(admin.ModelAdmin):
    list_display = ('name', 'remote_id')
    readonly_fields = ('remote_id',)
    search_fields = ('name',)

# 3. 镜像特征管理
@admin.register(MirrorCharacteristic)
class MirrorCharacteristicAdmin(admin.ModelAdmin):
    list_display = ('name', 'remote_id')
    readonly_fields = ('remote_id',)
    search_fields = ('name',)

# 4. 手册产品管理
@admin.register(CatalogProduct)
class CatalogProductAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'category', 'is_published', 'is_featured', 'view_count', 'download_count', 'published_at')
    list_filter = ('is_published', 'is_featured', 'category', 'scenarios', 'characteristics')
    search_fields = ('display_name', 'remote_material_id')
    list_editable = ('is_published', 'is_featured')
    
    readonly_fields = ('remote_material_id', 'view_count', 'download_count', 'published_at')
    filter_horizontal = ('scenarios', 'characteristics')
    
    fieldsets = (
        ('核心身份', {
            'fields': ('remote_material_id', 'display_name', 'category')
        }),
        ('发布状态', {
            'fields': ('is_published', 'is_featured')
        }),
        ('本地镜像数据', {
            'fields': ('description', 'scenarios', 'characteristics'),
            'description': '这些数据通过主系统 Webhook 自动同步，手动修改可能在下次同步时被覆盖。'
        }),
        ('统计信息', {
            'fields': ('view_count', 'download_count', 'published_at'),
            'classes': ('collapse',),
        }),
    )

    actions = ['make_published', 'make_unpublished', 'toggle_featured']

    @admin.action(description="批量发布选中牌号")
    def make_published(self, request, queryset):
        queryset.update(is_published=True)
        self.message_user(request, "选中的牌号已发布。")

    @admin.action(description="批量取消发布")
    def make_unpublished(self, request, queryset):
        queryset.update(is_published=False)
        self.message_user(request, "选中的牌号已取消发布。")

    @admin.action(description="批量切换推荐状态")
    def toggle_featured(self, request, queryset):
        for obj in queryset:
            obj.is_featured = not obj.is_featured
            obj.save()
        self.message_user(request, "推荐状态已切换。")

# 5. 访客日志管理
@admin.register(VisitorLog)
class VisitorLogAdmin(admin.ModelAdmin):
    list_display = ('product', 'visitor_ip', 'action', 'timestamp')
    list_filter = ('action', 'timestamp')
    readonly_fields = ('product', 'visitor_ip', 'user_agent', 'action', 'timestamp')
    search_fields = ('product__display_name', 'visitor_ip') # 增加搜索功能
    date_hierarchy = 'timestamp' # 增加日期层级导航
