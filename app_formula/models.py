from django.db import models
from django.conf import settings
from django.utils import timezone
from app_material.models import MaterialType, TestConfig, MaterialLibrary
from app_raw_material.models import RawMaterial
from app_process.models import ProcessProfile
from app_basic_research.models import ResearchProject



# 1. 实验配方主表
class LabFormula(models.Model):
    """
    实验配方 (Lab Formula)
    对应一次具体的改性实验
    """
    # 【修改】允许为空，由后端自动生成
    code = models.CharField("实验单号", max_length=50, blank=True, help_text="自动生成，如：L20231001-01，同批次配方共享同一单号")
    name = models.CharField("配方名称", max_length=100, blank=False, db_index=True)

    # 关联
    material_type = models.ForeignKey(MaterialType, on_delete=models.PROTECT, verbose_name="基材类型")
    process = models.ForeignKey(ProcessProfile, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="生产工艺")

    # 关联预研项目
    research_projects = models.ManyToManyField(ResearchProject, blank=True, verbose_name="所属预研项目", related_name="formulas")

    # 关联商业项目及阶段节点
    project = models.ForeignKey('app_project.Project', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联商业项目", related_name="formulas")
    project_node = models.ForeignKey('app_project.ProjectNode', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联项目阶段节点", related_name="formulas", help_text="研发/小试/中试/量产等阶段节点")

    # 成熟配方标记
    is_mature = models.BooleanField("成熟配方", default=False, help_text="勾选后该配方将纳入项目关联材料的成熟配方集，供后续项目参考")

    # 客户竞品标记
    is_competitor = models.BooleanField("客户竞品", default=False, help_text="客户竞品配方（由竞品工单自动创建，跳过挤出直达注塑）")

    # 版本号
    version = models.PositiveIntegerField("版本号", default=1, help_text="同一项目+节点的配方版本序号")

    # 成本不落库：预测成本与近N月均价成本都由 BOM 行 × 原材料实时价格算出，
    # 口径的唯一实现在 services/cost_service.py。
    # （历史上这里有 cost_predicted / _unit_cost 两个列，靠 RawMaterial 的价格
    #   信号级联维护；因为「直接写价格记录」不走那条信号，物化值与实时值长期
    #   不自洽，已连同信号一并删除。）

    # ── 成本核算 ──
    # 唯一实现在 app_formula/services/cost_service.py（Σ 加权与 LOCF 时间线）。
    # 下列方法都只是薄委托，勿在此重新实现算术。

    def cost_calculator(self):
        """取本配方用的成本计算器。

        优先复用已预热的 `_cost_calculator`（由 FormulaCostCalculator.prime() 挂载，
        批量页面用它共享同一份价格数据）；没有则按单个配方临时建一个。
        """
        calculator = getattr(self, '_cost_calculator', None)
        if calculator is None:
            from app_formula.services import FormulaCostCalculator
            calculator = FormulaCostCalculator.for_formulas([self])
        return calculator

    def cost(self, basis='latest', plant=None):
        """唯一只读成本入口。

        Args:
            basis: 'latest' → 用最新单价加权（预测成本口径）
                   'avg'    → 用近N月均价加权
            plant: None 为全局口径；传 Plant 则只算该工厂，缺价即返回 None。
        Returns:
            Decimal（元/kg）或 None（任一行缺价 / 无有效 BOM 行）。
        """
        calculator = self.cost_calculator()
        if basis == 'avg':
            return calculator.unit_cost(self, plant)
        return calculator.predicted_cost(self, plant)

    @property
    def unit_cost(self):
        """近N月均价成本 — 按 BOM 份数加权平均；无 BOM 行或任一行缺价 → None。"""
        if self.pk is None:
            return None
        return self.cost(basis='avg')

    @property
    def total_cost(self):
        """合计成本 — 主BOM预测成本 + 色粉预测成本（元/kg，均为最新单价口径）。

        相加规则与缺价处理见 FormulaCostCalculator.total_cost()：
        没有色粉配比表按 0 计；任一部分缺价 → None。
        """
        if self.pk is None:
            return None
        return self.cost_calculator().total_cost(self)

    # 材料颜色信息
    material_color_name = models.CharField("材料颜色名称", max_length=100, blank=True, help_text="例如：哑光黑、亮白、透明蓝")
    pantone_code = models.CharField("潘通色彩编号", max_length=50, blank=True, help_text="例如：PANTONE 19-4052 Classic Blue")
    rgb_value = models.CharField("RGB色值", max_length=7, blank=True, help_text="十六进制颜色值，例如 #FF5733")

    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="实验员")
    created_at = models.DateTimeField("录入日期", auto_now_add=True)
    description = models.TextField("实验目的/描述", blank=True)

    @property
    def stage_display(self):
        if self.project_node:
            return self.project_node.get_stage_display()
        return "-"

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

    def get_price_trend(self, plant=None):
        """构建配方单位成本时间线（LOCF 算法）。

        Args:
            plant: None 为全局口径；传 Plant 则只用该工厂的报价。
        Returns:
            [[timestamp_ms, unit_cost], ...] 按日期升序；任一原材料在某个日期前
            无报价 → 该日期整点不输出。

        合并了原先的 get_price_trend / get_price_trend_for_plant 两份拷贝，
        日期的价格取「日均值」而非「当日最后一条记录」，同一天多条报价时走势确定。
        """
        return self.cost_calculator().trend(self, plant)

    def get_price_trend_by_plant(self, plants=None):
        """返回 {plant: [[ts, cost], ...], ...}，用于多线图表。

        只保留至少 2 个数据点的工厂。复用同一个成本计算器，避免
        「每工厂 × 每 BOM 行」各打一次查询。
        """
        if plants is None:
            from app_raw_material.models import Plant
            plants = Plant.objects.filter(is_active=True)
        return self.cost_calculator().trend_by_plant(self, plants)

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
        results = self.test_results.select_related('test_config').filter(production_order__isnull=True)

        for res in results:
            name = res.test_config.name
            # 只筛选关键指标
            if any(k in name for k in key_keywords):
                # 兼容非数值类型
                val = res.value_text if res.test_config.data_type != 'NUMBER' else res.value

                item = {
                    'name': name,
                    'value': val,
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
        unique_together = ('code', 'version')


# 2. BOM 表 (Bill of Materials) — 抽象基类
class AbstractBOMEntry(models.Model):
    FEEDING_CHOICES = [
        ('1_MAIN', '主喂料 (Main)'),
        ('2_SIDE_1', '侧喂料1 (Side 1)'),
        ('3_SIDE_2', '侧喂料2 (Side 2)'),
        ('4_LIQUID', '液体注塑 (Liquid)'),
    ]

    WEIGHING_CHOICES = [
        ('A', 'A秤 (主料1)'),
        ('B', 'B秤 (主料2)'),
        ('C', 'C秤 (辅料/助剂)'),
        ('D', 'D秤 (色粉/微量)'),
        ('E', 'E秤 (其他)'),
    ]

    feeding_port = models.CharField("喂料口", max_length=20, choices=FEEDING_CHOICES, default='1_MAIN')
    weighing_scale = models.CharField("分秤", max_length=5, choices=WEIGHING_CHOICES, default='A', help_text="用于生产投料区分")
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.PROTECT, verbose_name="原材料")
    percentage = models.DecimalField("比例/份数", max_digits=8, decimal_places=3, help_text="百分比/份数")
    is_pre_mix = models.BooleanField("是否共混", default=False, help_text="是否需要在挤出前进行预混合")
    pre_mix_order = models.PositiveIntegerField("共混顺序", default=0, help_text="数字越小越先加入")
    pre_mix_time = models.PositiveIntegerField("共混时间 (秒)", default=0, help_text="该步骤的混合时长")

    class Meta:
        abstract = True


class FormulaBOM(AbstractBOMEntry):
    """配方 BOM 明细行"""
    formula = models.ForeignKey(LabFormula, on_delete=models.CASCADE, related_name='bom_lines')
    is_tail = models.BooleanField("是否尾料", default=False, help_text="是否为上一批次的尾料回掺")

    class Meta:
        verbose_name = "BOM明细"
        ordering = ['feeding_port', 'weighing_scale', 'raw_material__category__order', 'raw_material__name']


# 3. 实验物性结果 (Test Result)
# 这里我们复用 app_repository 中的 TestConfig，但数据是属于 LabFormula 的
class FormulaTestResult(models.Model):
    formula = models.ForeignKey(LabFormula, on_delete=models.CASCADE, related_name='test_results')
    test_config = models.ForeignKey(TestConfig, on_delete=models.PROTECT, verbose_name="测试项目")
    production_order = models.ForeignKey(
        'app_trial_production.ProductionOrder',
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="来源工单",
        help_text="从哪个生产工单回写的结果；为空表示手动录入",
    )

    # 【修改】改为 DecimalField，保留3位小数
    value = models.DecimalField("测试数值", max_digits=10, decimal_places=3, null=True, blank=True)

    # 【新增】文本型数据 (用于存储非数字结果，如阻燃等级 V-0)
    value_text = models.CharField("文本结果", max_length=50, blank=True)

    # 【新增】测试日期
    test_date = models.DateField("测试日期", null=True, blank=True)
    remark = models.CharField("备注", max_length=50, blank=True)

    # production_order 为 NULL 时 = 'MANUAL'，否则 = FK 值的字符串形式
    unique_key = models.CharField(max_length=100, blank=True, default='')

    def save(self, *args, **kwargs):
        if self.production_order_id:
            self.unique_key = str(self.production_order_id)
        else:
            self.unique_key = 'MANUAL'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "实验测试结果"
        indexes = [
            models.Index(fields=['formula']),
            models.Index(fields=['test_config']),
            models.Index(fields=['value_text']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['formula', 'test_config', 'unique_key'],
                name='uq_test_result',
            ),
        ]


# 4. 色粉配比表 (Color Powder BOM) - 配色部门填写，与配方1:1绑定
class ColorPowderBOM(models.Model):
    """色粉配比主表 - 与配方1:1绑定，配色部门在试产后填写"""
    formula = models.OneToOneField(
        LabFormula, on_delete=models.CASCADE,
        related_name='color_powder_bom', verbose_name="关联配方")
    filled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="填表人")
    remark = models.TextField("备注", blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "色粉配比表"
        verbose_name_plural = "色粉配比表"

    def __str__(self):
        return f"{self.formula.code} 色粉配比"

    @property
    def cost(self):
        """每 kg 主配方需要添加的色粉成本（元）= Σ(份数 × 最新单价) / 100。

        返回 Decimal 或 None。实现在 app_formula/services/cost_service.py；
        口径变更说明：旧实现返回 float，且会跳过缺价条目后返回「部分和」，
        现在返回 Decimal，任一非 0 份数的条目缺价即返回 None。
        """
        return self.powder_cost()

    def powder_cost(self, plant=None):
        """色粉成本；plant 为 None 用全局口径，传 Plant 则限定该工厂。"""
        calculator = getattr(self, '_cost_calculator', None)
        if calculator is None:
            from app_formula.services import FormulaCostCalculator
            calculator = FormulaCostCalculator.for_powder(self)
        return calculator.powder_cost(self, plant)


class ColorPowderBOMEntry(AbstractBOMEntry):
    """色粉配比明细行 — 继承 AbstractBOMEntry，与 FormulaBOM 结构对齐"""
    color_powder_bom = models.ForeignKey(
        ColorPowderBOM, on_delete=models.CASCADE,
        related_name='entries', verbose_name="所属色粉配比表")

    class Meta:
        verbose_name = "色粉配比明细"
