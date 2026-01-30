from django.contrib import admin
from .models import MachineModel, ScrewCombination, ProcessProfile

# 1. 机台型号 Admin
@admin.register(MachineModel)
class MachineModelAdmin(admin.ModelAdmin):
    list_display = ('machine_code', 'brand', 'model_name', 'screw_diameter', 'ld_ratio', 'max_speed')
    list_filter = ('brand', 'screw_diameter')
    search_fields = ('brand', 'model_name', 'machine_code')
    filter_horizontal = ('suitable_materials',)

# 2. 螺杆组合 Admin
@admin.register(ScrewCombination)
class ScrewCombinationAdmin(admin.ModelAdmin):
    list_display = ('combination_code', 'name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'combination_code', 'description')
    filter_horizontal = ('machines', 'suitable_materials')

# 3. 工艺方案 Admin
@admin.register(ProcessProfile)
class ProcessProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'process_type_name', 'machine', 'screw_combination', 'throughput', 'created_at')
    list_filter = ('process_type_name', 'machine', 'created_at')
    search_fields = ('name', 'description')
    filter_horizontal = ('material_types',)
    
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'process_type_name', 'material_types', 'machine', 'screw_combination', 'description')
        }),
        ('温度控制', {
            'fields': (
                ('temp_zone_1', 'temp_zone_2', 'temp_zone_3', 'temp_zone_4'),
                ('temp_zone_5', 'temp_zone_6', 'temp_zone_7', 'temp_zone_8'),
                ('temp_zone_9', 'temp_zone_10', 'temp_zone_11', 'temp_zone_12'),
                'temp_head'
            )
        }),
        ('主机运行', {
            'fields': (
                ('screw_speed', 'torque', 'current'),
                ('melt_pressure', 'melt_temp', 'vacuum')
            )
        }),
        ('喂料与后处理', {
            'fields': (
                ('main_feeder_speed', 'side_feeder_speed', 'liquid_pump_speed'),
                'throughput',
                ('cooling_method', 'strand_count', 'water_temp'),
                ('water_bath_length', 'air_knife_pressure', 'pelletizing_speed'),
                'screen_mesh'
            )
        }),
        ('QC检查', {
            'fields': ('qc_check_points',)
        }),
    )
