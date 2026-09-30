from django.contrib import admin

from .models import ChoiceOption, QuotationBOM, QuotationField, QuotationMaterialPrice, QuotationRequest


@admin.register(QuotationField)
class QuotationFieldAdmin(admin.ModelAdmin):
    list_display = ('key', 'label', 'field_type', 'group', 'order', 'required', 'default_value', 'is_active')
    list_filter = ('field_type', 'group', 'is_active', 'required')
    search_fields = ('key', 'label', 'hint')
    ordering = ('order', 'id')

    def has_delete_permission(self, request, obj=None):
        return False  # 只增不减：停用用 is_active

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ('key',)  # 创建后 key 只读，避免历史快照失效
        return ()


@admin.register(ChoiceOption)
class ChoiceOptionAdmin(admin.ModelAdmin):
    list_display = ('field', 'code', 'label', 'order', 'is_active')
    list_filter = ('field', 'is_active')
    search_fields = ('field__label', 'code', 'label')
    ordering = ('field__order', 'order', 'code')

    def has_delete_permission(self, request, obj=None):
        return False  # 只增不减


class QuotationBOMInline(admin.TabularInline):
    model = QuotationBOM
    extra = 0


class QuotationMaterialPriceInline(admin.TabularInline):
    model = QuotationMaterialPrice
    extra = 0
    fields = ('raw_material', 'price_tax_included', 'tax_rate', 'entered_by')


@admin.register(QuotationRequest)
class QuotationRequestAdmin(admin.ModelAdmin):
    list_display = ('code', 'finished_material', 'customer', 'business_group',
                    'subsidiary', 'status', 'created_at')
    list_filter = ('status', 'subsidiary', 'business_group')
    search_fields = ('code', 'finished_material__grade_name',
                     'finished_material__sap_material_code',
                     'customer__company_name', 'customer__short_name')
    inlines = [QuotationBOMInline, QuotationMaterialPriceInline]
    readonly_fields = ('workflow_instance', 'created_at', 'updated_at')


@admin.register(QuotationBOM)
class QuotationBOMAdmin(admin.ModelAdmin):
    list_display = ('request', 'formula', 'is_selected', 'selected_by')
    list_filter = ('is_selected',)
    search_fields = ('request__code', 'formula__name', 'formula__code')


@admin.register(QuotationMaterialPrice)
class QuotationMaterialPriceAdmin(admin.ModelAdmin):
    list_display = ('request', 'raw_material', 'price_tax_included', 'tax_rate', 'entered_by', 'entered_at')
    list_filter = ('raw_material__category',)
    search_fields = ('request__code', 'raw_material__name', 'raw_material__model_name')
