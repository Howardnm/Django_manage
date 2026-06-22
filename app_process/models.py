from django.db import models
from django.conf import settings
from app_material.models import MaterialType



# 【新增】机台型号库
class MachineModel(models.Model):
    brand = models.CharField("品牌", max_length=50, help_text="如：科倍隆, 南京科亚, 瑞亚")
    model_name = models.CharField("型号", max_length=50, unique=True, help_text="如：ZSK-26, TE-35")
    machine_code = models.IntegerField("机台号", null=True, blank=True)
    suitable_materials = models.ManyToManyField(MaterialType, blank=True, verbose_name="适用材料类型", related_name="machines")
    screw_diameter = models.FloatField("螺杆直径 (mm)", default=0)
    ld_ratio = models.FloatField("长径比 (L/D)", default=40, help_text="如：40, 44, 48")
    motor_power = models.FloatField("电机功率 (kW)", default=0, null=True, blank=True)
    max_speed = models.IntegerField("最高转速 (rpm)", default=600, null=True, blank=True)
    max_torque = models.FloatField("最高扭矩 (Nm)", default=0, null=True, blank=True)
    description = models.TextField("备注", blank=True)

    def __str__(self):
        code_str = f"[{self.machine_code}] " if self.machine_code else ""
        return f"{code_str}{self.brand} - {self.model_name} (D{self.screw_diameter})"

    class Meta:
        verbose_name = "机台型号"
        verbose_name_plural = "机台型号库"
        ordering = ['machine_code']


# 【新增】螺杆组合库
class ScrewCombination(models.Model):
    name = models.CharField("组合名称", max_length=100, help_text="建议命名格式：基材+辅料 功能-版本号，如：PP+滑石粉 高剪切组合-V1")
    combination_code = models.IntegerField("螺杆组合号", null=True, blank=True, help_text="数字编号，如：101")
    machines = models.ManyToManyField(MachineModel, verbose_name="适用机台", related_name="screw_combinations")
    suitable_materials = models.ManyToManyField(MaterialType, blank=True, verbose_name="适用材料类型", related_name="screw_combinations")
    description = models.TextField("组合描述", blank=True, help_text="详细描述螺杆排列逻辑，如：输送-熔融-剪切-排气")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        code_str = f"[{self.combination_code}] " if self.combination_code else ""
        return f"{code_str}{self.name}"

    class Meta:
        verbose_name = "螺杆组合"
        verbose_name_plural = "螺杆组合库"
        ordering = ['combination_code', '-created_at']


# 2. 挤出工艺参数抽象基类 — 由工艺app统一管理，ProcessProfile 和 ExtrusionTask 共享字段结构
class AbstractExtrusionParams(models.Model):
    """挤出工艺参数抽象基类 — 定义挤出生产中的全部可记录参数"""

    COOLING_CHOICES = [
        ('WATER_STRAND', '水冷拉条 (Water Strand)'),
        ('WATER_RING', '水环热切 (Water Ring)'),
        ('UNDERWATER', '水下切粒 (Underwater)'),
        ('AIR_STRAND', '风冷拉条 (Air Strand)'),
        ('AIR_FACE', '风冷热切 (Air Face)'),
    ]

    # ── A. 温度控制 (13 个区段) ──
    temp_zone_1 = models.IntegerField("一区温度 (℃)", default=0, help_text="下料口")
    temp_zone_2 = models.IntegerField("二区温度 (℃)", default=0)
    temp_zone_3 = models.IntegerField("三区温度 (℃)", default=0)
    temp_zone_4 = models.IntegerField("四区温度 (℃)", default=0)
    temp_zone_5 = models.IntegerField("五区温度 (℃)", default=0)
    temp_zone_6 = models.IntegerField("六区温度 (℃)", default=0)
    temp_zone_7 = models.IntegerField("七区温度 (℃)", default=0)
    temp_zone_8 = models.IntegerField("八区温度 (℃)", default=0)
    temp_zone_9 = models.IntegerField("九区温度 (℃)", default=0)
    temp_zone_10 = models.IntegerField("十区温度 (℃)", default=0)
    temp_zone_11 = models.IntegerField("十一区温度 (℃)", default=0)
    temp_zone_12 = models.IntegerField("十二区温度 (℃)", default=0)
    temp_head = models.IntegerField("机头温度 (℃)", default=0)

    # ── B. 主机运行参数 ──
    screw_speed = models.IntegerField("螺杆转速 (rpm)", default=0)
    torque = models.FloatField("主机扭矩 (%)", default=0, help_text="负载百分比")
    current = models.FloatField("主机电流 (A)", default=0, null=True, blank=True)
    melt_pressure = models.FloatField("熔体压力 (MPa)", default=0, help_text="机头压力")
    melt_temp = models.IntegerField("熔体实测温度 (℃)", default=0, help_text="手测或传感器读数")
    vacuum = models.FloatField("真空度 (MPa)", default=-0.08)

    # ── C. 喂料系统 ──
    main_feeder_speed = models.FloatField("主喂料转速 (rpm/Hz)", default=0)
    side_feeder_speed = models.FloatField("侧喂料转速 (rpm/Hz)", default=0, help_text="玻纤/填料")
    liquid_pump_speed = models.FloatField("液体泵注速度", default=0, null=True, blank=True)

    # ── D. 产能与后处理 ──
    throughput = models.FloatField("总产量 (kg/h)", default=0)
    cooling_method = models.CharField("切粒方式", max_length=20, choices=COOLING_CHOICES, default='WATER_STRAND')
    strand_count = models.IntegerField("料条根数", default=0, help_text="机头出料孔数")
    water_temp = models.IntegerField("冷却水温 (℃)", default=25, help_text="水槽温度")
    water_bath_length = models.FloatField("过水长度 (m)", default=0, help_text="料条在水中的长度")
    air_knife_pressure = models.FloatField("风刀压力 (MPa)", default=0, null=True, blank=True, help_text="吹干风力")
    pelletizing_speed = models.FloatField("切粒机转速 (rpm/Hz)", default=0)
    screen_mesh = models.CharField("过滤网目数", max_length=50, blank=True, help_text="如：80/100")

    class Meta:
        abstract = True

    # ── 便捷字段列表（统一定义，避免子类重复维护）──
    TEMP_FIELDS = [
        'temp_zone_1', 'temp_zone_2', 'temp_zone_3', 'temp_zone_4',
        'temp_zone_5', 'temp_zone_6', 'temp_zone_7', 'temp_zone_8',
        'temp_zone_9', 'temp_zone_10', 'temp_zone_11', 'temp_zone_12',
        'temp_head',
    ]
    PARAM_FIELDS = [
        'screw_speed', 'torque', 'current', 'melt_pressure', 'melt_temp', 'vacuum',
        'main_feeder_speed', 'side_feeder_speed', 'liquid_pump_speed',
        'throughput', 'cooling_method', 'strand_count', 'water_temp',
        'water_bath_length', 'air_knife_pressure', 'pelletizing_speed', 'screen_mesh',
    ]
    ALL_PARAM_FIELDS = TEMP_FIELDS + PARAM_FIELDS


# 3. 工艺参数包 (Process Profile)
class ProcessProfile(AbstractExtrusionParams):

    name = models.CharField("工艺方案名称", max_length=100, help_text="如：PA66+30GF 标准挤出工艺")
    process_type_name = models.CharField("工艺类型", max_length=50, default="双螺杆挤出", help_text="如：双螺杆挤出、其他")
    material_types = models.ManyToManyField(MaterialType, blank=True, verbose_name="适用材料类型", related_name="process_profiles")
    machine = models.ForeignKey(MachineModel, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="适用机台")

    # 【新增】负责人关联
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="创建人", null=True, blank=True)

    # --- E. 其他 ---
    screw_combination = models.ForeignKey(ScrewCombination, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="螺杆组合")
    qc_check_points = models.TextField("QC检查/更换要点", blank=True, help_text="如：每2小时检查真空口是否堵塞，每班次更换过滤网")
    description = models.TextField("工艺备注", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "工艺方案"
        verbose_name_plural = "工艺方案库"
