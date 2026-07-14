from django.contrib import admin
from .models import PriceAvgConfig, RawMaterialType, Supplier, RawMaterial, RawMaterialProperty, RawMaterialPriceRecord

@admin.register(RawMaterialType)
class RawMaterialTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'order', 'description')
    search_fields = ('name', 'code')
    ordering = ('order', 'name')

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'sales_contact', 'sales_phone', 'tech_contact', 'tech_phone', 'created_at')
    search_fields = ('name', 'sales_contact', 'tech_contact')
    filter_horizontal = ('product_categories',)
    list_filter = ('created_at',)

class RawMaterialPropertyInline(admin.TabularInline):
    model = RawMaterialProperty
    extra = 1
    autocomplete_fields = ['test_config']


class RawMaterialPriceRecordInline(admin.TabularInline):
    model = RawMaterialPriceRecord
    extra = 1
    fields = ('price', 'date', 'source')


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_name', 'warehouse_code', 'category', 'supplier', 'latest_price', 'created_at')
    search_fields = ('name', 'model_name', 'warehouse_code')
    list_filter = ('category', 'supplier', 'created_at')
    filter_horizontal = ('suitable_materials',)
    inlines = [RawMaterialPropertyInline, RawMaterialPriceRecordInline]
    autocomplete_fields = ['category', 'supplier']

@admin.register(RawMaterialProperty)
class RawMaterialPropertyAdmin(admin.ModelAdmin):
    list_display = ('raw_material', 'test_config', 'value', 'value_text', 'test_date')
    search_fields = ('raw_material__name', 'test_config__name')
    list_filter = ('test_config', 'test_date')
    autocomplete_fields = ['raw_material', 'test_config']


@admin.register(PriceAvgConfig)
class PriceAvgConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not PriceAvgConfig.objects.exists()


@admin.register(RawMaterialPriceRecord)
class RawMaterialPriceRecordAdmin(admin.ModelAdmin):
    list_display = ('raw_material', 'price', 'date', 'source', 'created_at')
    search_fields = ('raw_material__name', 'raw_material__model_name', 'source')
    list_filter = ('date', 'raw_material__category')
    autocomplete_fields = ['raw_material']
