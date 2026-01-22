from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from app_repository.models import MaterialType, TestConfig, MaterialLibrary
from app_raw_material.models import RawMaterial
from app_process.models import ProcessProfile
from common_utils.upload_file_path import upload_file_path
from common_utils.validators import validate_file_size  # 引入文件大小验证器

# 1. 实验配方主表
class LabFormula(models.Model):
    """
    实验配方 (Lab Formula)
    对应一次具体的改性实验
    """
    # 【修改】允许为空，由后端自动生成
    code = models.CharField("实验单号", max_length=50, unique=True, blank=True, help_text="自动生成，如：L20231001-01")
    name = models.CharField("配方名称", max_length=100, blank=False)
    
    # 关联
    material_type = models.ForeignKey(MaterialType, on_delete=models.PROTECT, verbose_name="基材类型")
    process = models.ForeignKey(ProcessProfile, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="生产工艺")
    
    # 关联到成品材料库 (如果这个配方成功量产，可以关联到一个 MaterialLibrary 对象)
    # 多对多：一个成品材料可能对应多个历史实验配方
    related_materials = models.ManyToManyField(MaterialLibrary, blank=True, related_name='formulas', verbose_name="关联成品材料")
    
    # 【新增】成本字段
    cost_predicted = models.DecimalField("BOM预测成本 (元/kg)", max_digits=10, decimal_places=2, default=0, help_text="根据原材料成本自动计算")
    cost_actual = models.DecimalField("BOM实际成本 (元/kg)", max_digits=10, decimal_places=2, null=True, blank=True, help_text="手动录入实际配方成本")

    creator = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="实验员")
    created_at = models.DateTimeField("录入日期", auto_now_add=True)
    description = models.TextField("实验目的/描述", blank=True)

    def __str__(self):
        return f"{self.code} {self.name}"

    # 【新增】自动生成单号逻辑
    def save(self, *args, **kwargs):
        if not self.code:
            # 生成规则：L + 年月日 + - + 2位流水号
            today_str = timezone.now().strftime('%Y%m%d')
            prefix = f"L{today_str}"
            
            # 查找当天已有的最大流水号
            # 注意：这里使用了 startswith 过滤，可能会有并发问题，但在低频场景下可接受
            # 更严谨的做法是使用数据库序列或 Redis 自增
            last_formula = LabFormula.objects.filter(code__startswith=prefix).order_by('code').last()
            
            if last_formula:
                try:
                    # 取出最后两位数字并 +1
                    last_seq = int(last_formula.code.split('-')[-1])
                    new_seq = last_seq + 1
                except ValueError:
                    new_seq = 1
            else:
                new_seq = 1
            
            self.code = f"{prefix}-{new_seq:02d}"
            
        super().save(*args, **kwargs)

    # 【修改】计算预测成本的方法 (加权平均)
    def calculate_cost(self):
        """
        计算配方的每公斤理论成本。
        逻辑：总金额 / 总份数
        兼容总比例不等于 100% 的情况 (例如按份数录入)
        """
        total_amount = Decimal('0.00') # 总金额
        total_parts = Decimal('0.00')  # 总份数 (比例之和)
        
        # 预加载 raw_material 以避免 N+1
        bom_lines = self.bom_lines.select_related('raw_material').all()
        
        for line in bom_lines:
            # 累加总份数
            total_parts += line.percentage
            
            # 如果原材料有成本价，则累加金额
            if line.raw_material.cost_price:
                amount = line.raw_material.cost_price * line.percentage
                total_amount += amount
        
        # 计算加权平均单价
        if total_parts > 0:
            avg_cost = total_amount / total_parts
        else:
            avg_cost = Decimal('0.00')
            
        # 更新字段并保存
        self.cost_predicted = avg_cost
        self.save(update_fields=['cost_predicted'])
        return avg_cost

    # 【新增】获取关键物性指标字典 (用于列表展示)
    def get_key_properties(self):
        """
        返回格式：
        {
            'ISO': [{'name': '拉伸', 'value': 50, 'unit': 'MPa'}, ...],
            'ASTM': [...]
        }
        """
        data = {'ISO': [], 'ASTM': [], 'OTHER': []}
        # 关键指标关键词
        key_keywords = ['灰分', '熔融', '拉伸', '弯曲', '冲击', '热变形', '阻燃']
        
        # 预加载 test_config
        results = self.test_results.select_related('test_config').all()
        
        for res in results:
            name = res.test_config.name
            # 只筛选关键指标
            if any(k in name for k in key_keywords):
                item = {
                    'name': name,
                    'value': res.value,
                    'unit': res.test_config.unit,
                    'standard': res.test_config.standard
                }
                
                if 'ISO' in res.test_config.standard:
                    data['ISO'].append(item)
                elif 'ASTM' in res.test_config.standard:
                    data['ASTM'].append(item)
                else:
                    data['OTHER'].append(item)
        return data

    class Meta:
        verbose_name = "实验配方"
        verbose_name_plural = "实验配方库"
        ordering = ['-created_at']


# 2. BOM 表 (Bill of Materials) - 配方明细
class FormulaBOM(models.Model):
    FEEDING_CHOICES = [
        ('1_MAIN', '主喂料 (Main)'),
        ('2_SIDE_1', '侧喂料1 (Side 1)'),
        ('3_SIDE_2', '侧喂料2 (Side 2)'),
        ('4_LIQUID', '液体注塑 (Liquid)'),
    ]
    
    # 【新增】分秤选项 (改性塑料行业标准)
    WEIGHING_CHOICES = [
        ('A', 'A秤 (主料1)'),
        ('B', 'B秤 (主料2)'),
        ('C', 'C秤 (辅料/助剂)'),
        ('D', 'D秤 (色粉/微量)'),
        ('E', 'E秤 (其他)'),
    ]

    formula = models.ForeignKey(LabFormula, on_delete=models.CASCADE, related_name='bom_lines')
    # 喂料口位置
    feeding_port = models.CharField("喂料口", max_length=20, choices=FEEDING_CHOICES, default='1_MAIN')
    
    # 【新增】分秤字段
    weighing_scale = models.CharField("分秤", max_length=5, choices=WEIGHING_CHOICES, default='A', help_text="用于生产投料区分")
    
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, verbose_name="原材料")
    percentage = models.DecimalField("比例/份数", max_digits=7, decimal_places=2, help_text="百分比/份数")
    is_tail = models.BooleanField("是否尾料", default=False, help_text="是否为上一批次的尾料回掺")
    # 共混工艺参数
    is_pre_mix = models.BooleanField("是否共混", default=False, help_text="是否需要在挤出前进行预混合")
    pre_mix_order = models.PositiveIntegerField("共混顺序", default=0, help_text="数字越小越先加入")
    pre_mix_time = models.PositiveIntegerField("共混时间 (秒)", default=0, help_text="该步骤的混合时长")

    class Meta:
        verbose_name = "BOM明细"
        # 【修改】排序规则：先按喂料口，再按分秤，再按原材料类型权重，最后按原材料名称
        ordering = ['feeding_port', 'weighing_scale', 'raw_material__category__order', 'raw_material__name']


# 3. 实验物性结果 (Test Result)
# 这里我们复用 app_repository 中的 TestConfig，但数据是属于 LabFormula 的
class FormulaTestResult(models.Model):
    formula = models.ForeignKey(LabFormula, on_delete=models.CASCADE, related_name='test_results')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    
    # 【修改】改为 DecimalField，保留3位小数
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3)
    
    # 【新增】测试日期
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)
    
    # 【新增】测试报告文件
    file_report = models.FileField("测试报告", upload_to=upload_file_path, blank=True, null=True, validators=[validate_file_size])

    class Meta:
        verbose_name = "实验测试结果"
        unique_together = ('formula', 'test_config')
