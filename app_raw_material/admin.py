from django.contrib import admin
from .models import Plant, PriceAvgConfig, RawMaterialType, Supplier, RawMaterial, RawMaterialProperty, RawMaterialPriceRecord, RawMaterialStockSnapshot

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
    fields = ('price', 'date', 'plant', 'source')


class RawMaterialStockSnapshotInline(admin.TabularInline):
    model = RawMaterialStockSnapshot
    extra = 0
    fields = ('plant', 'storage_location', 'batch', 'unrestricted_stock', 'safety_stock', 'synced_at')
    readonly_fields = ('synced_at',)


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'model_name', 'warehouse_code', 'category', 'supplier', 'latest_price', 'created_at')
    search_fields = ('name', 'model_name', 'warehouse_code')
    list_filter = ('category', 'supplier', 'created_at')
    filter_horizontal = ('suitable_materials',)
    inlines = [RawMaterialPropertyInline, RawMaterialPriceRecordInline, RawMaterialStockSnapshotInline]
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


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'created_at')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)


@admin.register(RawMaterialPriceRecord)
class RawMaterialPriceRecordAdmin(admin.ModelAdmin):
    list_display = ('raw_material', 'plant', 'price', 'date', 'source', 'created_at')
    search_fields = ('raw_material__name', 'raw_material__model_name', 'source')
    list_filter = ('date', 'plant', 'raw_material__category')
    autocomplete_fields = ['raw_material', 'plant']


@admin.register(RawMaterialStockSnapshot)
class RawMaterialStockSnapshotAdmin(admin.ModelAdmin):
    list_display = ('raw_material', 'plant', 'storage_location', 'batch',
                    'unrestricted_stock', 'safety_stock', 'synced_at')
    search_fields = ('raw_material__name', 'raw_material__model_name',
                     'storage_location', 'batch')
    list_filter = ('plant', 'storage_location', 'synced_at')
    autocomplete_fields = ['raw_material', 'plant']
    readonly_fields = ('sync_batch_id', 'synced_at')
