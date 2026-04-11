from django.contrib import admin
from ..models import CatalogCategory, CatalogProduct

@admin.register(CatalogCategory)
class CatalogCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'remote_type_id', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('name', 'remote_type_id')

@admin.register(CatalogProduct)
class CatalogProductAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'remote_material_id', 'category', 'is_published', 'is_featured', 'view_count', 'download_count')
    list_filter = ('category', 'is_published', 'is_featured')
    search_fields = ('display_name', 'remote_material_id')
    autocomplete_fields = ['category']
    actions = ['make_published', 'make_unpublished']

    def make_published(self, request, queryset):
        queryset.update(is_published=True)
    make_published.short_description = "批量发布"

    def make_unpublished(self, request, queryset):
        queryset.update(is_published=False)
    make_unpublished.short_description = "取消发布"
