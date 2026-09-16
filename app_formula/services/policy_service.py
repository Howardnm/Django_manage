"""实验单编辑分级策略 —— 按关联生产工单的状态决定实验单哪些部分可改。

一个「实验单」= 共享同一 ``LabFormula.code`` 的一组配方版本。

分级依据：该实验单关联的**全部生产工单中"最靠后"的状态**。状态流转见
``app_trial_production/apps.py`` 的 ``StateMachine`` 注册表；注意审批被驳回
即 ``WORKFLOW_RUNNING → DRAFT``，因此"驳回后重新编辑"无需特殊分支。

    级别  关联工单状态                              版本增删  内容(BOM/基础信息)
    L1    无工单 / DRAFT / CANCELED                  ✅        ✅
    L2    WORKFLOW_RUNNING / ACCEPTED                ❌        ✅
    L3    EXTRUDING 及之后                           ❌        ❌（整页只读）

L3 的测试数据补录走配方过程页的「均值回写」，不在编辑页开口子——这样
``LabFormulaUpdateView`` 在 L3 只有一条"拒绝写入"的路径，不必维护半开的表单。
"""
from django.db import transaction
from django.db.models import Max

from app_formula.models import LabFormula
from app_trial_production.models import ProductionOrder


class FormulaVersionError(Exception):
    """实验单版本结构不可变更。

    已知业务异常：视图按「直接向用户展示 str(e)」处理，不记堆栈。
    """


class FormulaEditPolicy:
    """实验单编辑分级策略 —— 唯一实现，禁止在视图/模板里重复这套判断。"""

    # ── 级别常量 ──
    TIER_L1 = 'L1'  # 审批前：可改内容 + 可增删版本
    TIER_L2 = 'L2'  # 审批中~已发单：可改内容，版本结构冻结
    TIER_L3 = 'L3'  # 投产中及之后：整页只读

    # 工单状态 → 所属级别。新增状态若未登记，resolve() 按最严的 L3 处理。
    _STATUS_TIER = {
        ProductionOrder.Status.DRAFT: TIER_L1,
        ProductionOrder.Status.CANCELED: TIER_L1,
        ProductionOrder.Status.WORKFLOW_RUNNING: TIER_L2,
        ProductionOrder.Status.ACCEPTED: TIER_L2,
        ProductionOrder.Status.EXTRUDING: TIER_L3,
        ProductionOrder.Status.INJECTION_MOLDING: TIER_L3,
        ProductionOrder.Status.TESTING: TIER_L3,
        ProductionOrder.Status.COMPLETED: TIER_L3,
    }
    _TIER_RANK = {TIER_L1: 1, TIER_L2: 2, TIER_L3: 3}

    # 允许「版本结构变更」的级别（L1 结构变更时连带删除这些工单）
    _REMOVABLE_STATUSES = frozenset([ProductionOrder.Status.DRAFT, ProductionOrder.Status.CANCELED])

    # 重编号时的中转区间起点 —— 必须高于任何现实中的版本号
    _RENUMBER_BASE = 100000

    # ── 查询 ──

    @staticmethod
    def orders_for(formulas):
        """返回引用了这批配方版本的全部生产工单（去重）。"""
        return ProductionOrder.objects.filter(
            formula_details__formula__in=formulas,
        ).distinct()

    @classmethod
    def unrestricted(cls) -> dict:
        """无限制策略 —— 供新建页/复制页使用。

        这两类页面操作的是尚不存在或全新的实验单，不可能被任何工单引用。
        `form.html` 由三个视图共用，若不提供该默认值，模板里的
        ``{% if edit_policy.can_edit_content %}`` 会把它们误判成只读。
        """
        return {
            'tier': cls.TIER_L1,
            'can_edit_content': True,
            'can_manage_versions': True,
            'removable_order_codes': [],
            'blocking_order_codes': [],
            'banner': None,
        }

    @classmethod
    def resolve(cls, formulas) -> dict:
        """一次算清本页的编辑策略，避免模板里 N+1 查询。

        Args:
            formulas: 同一实验单（同 code）下的配方版本集合。

        Returns:
            {
              'tier': 'L1'|'L2'|'L3',
              'can_edit_content': bool,       # 基础信息/描述/关联/BOM
              'can_manage_versions': bool,    # 版本增删（仅 L1）
              'removable_order_codes': [str], # L1 结构变更时会被连带删除的工单号
              'blocking_order_codes': [str],  # 造成 L2/L3 锁定的工单号
              'banner': None | {'css', 'title', 'message'},  # 页面顶部提示条，文案在此生成
            }
        """
        formulas = list(formulas)
        orders = list(cls.orders_for(formulas)) if formulas else []

        tier = cls.TIER_L1
        removable, blocking = [], []
        for order in orders:
            order_tier = cls._STATUS_TIER.get(order.status, cls.TIER_L3)
            if cls._TIER_RANK[order_tier] > cls._TIER_RANK[tier]:
                tier = order_tier
            if order.status in cls._REMOVABLE_STATUSES:
                removable.append(order.code)
            else:
                blocking.append(order.code)

        is_l1 = tier == cls.TIER_L1
        return {
            'tier': tier,
            'can_edit_content': tier in (cls.TIER_L1, cls.TIER_L2),
            'can_manage_versions': is_l1,
            # 只有 L1 才谈得上"连带删除"，L2/L3 下这些工单不存在
            'removable_order_codes': removable if is_l1 else [],
            'blocking_order_codes': blocking,
            'banner': cls._banner(tier, blocking),
        }

    # ── 版本结构变更（仅 L1）──

    @classmethod
    def staging_version(cls, offset: int) -> int:
        """新增版本落库时的临时高位版本号。

        ``unique_together('code','version')`` 要求落库时就得有个不冲突的值，
        而最终编号要等所有列都处理完才能确定；收尾由 ``renumber()`` 统一重排。
        """
        return cls._RENUMBER_BASE + offset

    @classmethod
    def delete_removable_orders(cls, formulas) -> list[str]:
        """删除引用了这批配方的可删工单（DRAFT / CANCELED），返回被删工单号列表。

        实验单版本结构变更时调用：这些工单建立在旧的版本结构上，整体作废比
        逐个绕开 3 个 PROTECT 外键干净得多 —— ``order.delete()`` 会级联清掉
        ``ProductionOrderFormulaDetail``、``MoldRequirement`` 及其配方明细、
        ``TestingTask`` 及其 ``TrialTestResult`` 等全部引用路径。

        Raises:
            FormulaVersionError: 存在已提交审批或更靠后的工单。
        """
        blocking = [
            o.code for o in cls.orders_for(formulas)
            if o.status not in cls._REMOVABLE_STATUSES
        ]
        if blocking:
            raise FormulaVersionError(
                f'该实验单已被工单 {"、".join(blocking)} 引用且已提交审批，不能增删配方版本。'
            )

        removable = list(cls.orders_for(formulas).filter(status__in=cls._REMOVABLE_STATUSES))
        codes = [o.code for o in removable]
        if not removable:
            return codes

        with transaction.atomic():
            for order in removable:
                # 判定与删除之间工单可能被并发推进（如刚好提交审批），删除前提再断言一次
                if order.status not in cls._REMOVABLE_STATUSES:
                    raise FormulaVersionError(
                        f'工单 {order.code} 的状态刚刚发生变化，请刷新页面后重试。'
                    )
                # 走工单模块的删除服务：单纯的 order.delete() 在 MySQL 上会因
                # nullable CASCADE 外键撞 CheckConstraint，原因详见该方法注释。
                from app_trial_production.services import ProductionOrderService
                ProductionOrderService.delete_draft(order)
        return codes

    @classmethod
    def renumber(cls, formulas_in_column_order) -> list[LabFormula]:
        """把版本号按列顺序重排为连续的 1..N。

        分两阶段写库，规避 ``unique_together = ('code', 'version')``：
        先把这批配方整体挪到高位区间，再逐个落到最终编号 —— 否则
        「v3 → v2」会直接撞上尚未处理的那条 v2。

        只改 ``version`` 字段，不动对象标识，因此工单等 FK 引用不受影响。

        Returns:
            与入参同序的配方列表（已同步内存中的 version）。列表中的 None 会被跳过。
        """
        formulas = [f for f in formulas_in_column_order if f is not None]
        if not formulas:
            return []

        # 中转区间必须严格高于该实验单现有的最大版本号，否则新建的版本
        # （建库时用的临时高位号）会和中转编号撞在一起。
        current_max = LabFormula.objects.filter(code=formulas[0].code).aggregate(
            m=Max('version'))['m'] or 0
        staging_base = max(current_max, cls._RENUMBER_BASE) + 1

        with transaction.atomic():
            for offset, formula in enumerate(formulas):
                LabFormula.objects.filter(pk=formula.pk).update(
                    version=staging_base + offset)
            for offset, formula in enumerate(formulas):
                LabFormula.objects.filter(pk=formula.pk).update(version=offset + 1)
                formula.version = offset + 1
        return formulas

    @staticmethod
    def _banner(tier, blocking_codes) -> dict | None:
        """页面顶部提示条文案 —— 分级规则的解释只写这一处。"""
        codes = '、'.join(blocking_codes) if blocking_codes else '—'
        if tier == FormulaEditPolicy.TIER_L2:
            return {
                'css': 'alert-warning',
                'title': '版本结构已冻结',
                'message': (
                    f'该实验单已被工单 {codes} 引用且已提交审批或已发单。'
                    'BOM 与基础信息仍可修改（工单显示会同步更新），但不能增删配方版本。'
                ),
            }
        if tier == FormulaEditPolicy.TIER_L3:
            return {
                'css': 'alert-danger',
                'title': '该实验单已投产，已整体锁定',
                'message': (
                    f'引用工单 {codes} 已进入挤出或之后的状态，本页所有字段只读。'
                    '如需补录测试数据，请使用配方过程页的「均值回写」。'
                ),
            }
        return None
