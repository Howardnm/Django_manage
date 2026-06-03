from django.db import models
from django.conf import settings


class ExtrusionRecord(models.Model):
    """挤出生产记录 - 记录实际运行参数，字段结构与 ProcessProfile 对齐"""
    production_order = models.OneToOneField(
        'app_trial_production.ProductionOrder', on_delete=models.CASCADE,
        related_name='extrusion_record', verbose_name="关联工单")

    # 温度
    temp_zone_1 = models.IntegerField("一区温度(℃)", default=0)
    temp_zone_2 = models.IntegerField("二区温度(℃)", default=0)
    temp_zone_3 = models.IntegerField("三区温度(℃)", default=0)
    temp_zone_4 = models.IntegerField("四区温度(℃)", default=0)
    temp_zone_5 = models.IntegerField("五区温度(℃)", default=0)
    temp_zone_6 = models.IntegerField("六区温度(℃)", default=0)
    temp_zone_7 = models.IntegerField("七区温度(℃)", default=0)
    temp_zone_8 = models.IntegerField("八区温度(℃)", default=0)
    temp_zone_9 = models.IntegerField("九区温度(℃)", default=0)
    temp_zone_10 = models.IntegerField("十区温度(℃)", default=0)
    temp_zone_11 = models.IntegerField("十一区温度(℃)", default=0)
    temp_zone_12 = models.IntegerField("十二区温度(℃)", default=0)
    temp_head = models.IntegerField("机头温度(℃)", default=0)

    # 主机参数
    screw_speed = models.IntegerField("螺杆转速(rpm)", default=0)
    torque = models.FloatField("扭矩(%)", default=0)
    current = models.FloatField("电流(A)", null=True, blank=True)
    melt_pressure = models.FloatField("熔体压力(MPa)", default=0)
    melt_temp = models.IntegerField("熔体温度(℃)", default=0)
    vacuum = models.FloatField("真空度(MPa)", default=-0.08)

    # 喂料
    main_feeder_speed = models.FloatField("主喂料(rpm/Hz)", default=0)
    side_feeder_speed = models.FloatField("侧喂料(rpm/Hz)", default=0)
    liquid_pump_speed = models.FloatField("液体泵速", null=True, blank=True)

    # 产能与后处理
    throughput = models.FloatField("产量(kg/h)", default=0)
    cooling_method = models.CharField("切粒方式", max_length=20,
        choices=[
            ('WATER_STRAND', '水冷拉条'), ('WATER_RING', '水环热切'),
            ('UNDERWATER', '水下切粒'), ('AIR_STRAND', '风冷拉条'),
            ('AIR_FACE', '风冷热切'),
        ], default='WATER_STRAND')
    strand_count = models.IntegerField("料条根数", default=0)
    water_temp = models.IntegerField("水温(℃)", default=25)
    water_bath_length = models.FloatField("过水长度(m)", default=0)
    air_knife_pressure = models.FloatField("风刀压力(MPa)", null=True, blank=True)
    pelletizing_speed = models.FloatField("切粒机转速(rpm/Hz)", default=0)
    screen_mesh = models.CharField("过滤网目数", max_length=50, blank=True)

    remark = models.TextField("备注", blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="记录人")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "挤出生产记录"
        verbose_name_plural = "挤出生产记录"


class ProductionOutput(models.Model):
    """生产产出记录"""
    production_order = models.OneToOneField(
        'app_trial_production.ProductionOrder', on_delete=models.CASCADE,
        related_name='production_output', verbose_name="关联工单")
    total_output = models.DecimalField("总产出(kg)", max_digits=10, decimal_places=2)
    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "生产产出"
        verbose_name_plural = "生产产出"

    def __str__(self):
        return f"{self.production_order.code} 产出 {self.total_output}kg"
