from django.core.management.base import BaseCommand
from app_project.models import NodeScoreRule, ProjectStage


class Command(BaseCommand):
    help = '初始化项目绩效评分规则（研发 + 销售双轨制）'

    def handle(self, *args, **options):
        # 格式: (名称, 分值, 规则类型, 触发阶段, 触发状态, 是否多轮)
        rules_data = [

            # ================================================================
            #  一、研发规则 (rule_type='RD')
            # ================================================================

            # --- 1. 正常流程完成（首轮 DONE）--- 逐阶段递进，分值逐步升高 ---
            ('项目立项完成',               10,  'RD', ProjectStage.INIT,        'DONE',       False),
            ('资料收集完成',               20,  'RD', ProjectStage.COLLECT,     'DONE',       False),
            ('可行性评估通过',             40,  'RD', ProjectStage.FEASIBILITY, 'DONE',       False),
            ('研发阶段成功',               60,  'RD', ProjectStage.RND,         'DONE',       False),
            ('客户小试合格',               80,  'RD', ProjectStage.PILOT,       'DONE',       False),
            ('客户中试合格',               90,  'RD', ProjectStage.MID_TEST,    'DONE',       False),
            ('量产意向达成',               95,  'RD', ProjectStage.MASS_PROD,   'DONE',       False),
            ('项目最终下单/量产',          100, 'RD', ProjectStage.ORDER,       'DONE',       False),

            # --- 2. 异常返工（首轮 FAILED）--- 节点异常触发迭代 ---
            ('研发不合格重开',             0,   'RD', ProjectStage.RND,         'FAILED',     False),
            ('小试失败返工',               10,  'RD', ProjectStage.PILOT,       'FAILED',     False),
            ('中试失败返工',               20,  'RD', ProjectStage.MID_TEST,    'FAILED',     False),

            # --- 3. 异常返工（多轮 FAILED）--- 多次返工仍未通过，给予少量基础分 ---
            ('研发多次返工仍未通过',       5,   'RD', ProjectStage.RND,         'FAILED',     True),
            ('小试多次失败后停止',         10,  'RD', ProjectStage.PILOT,       'FAILED',     True),
            ('中试多次失败后停止',         20,  'RD', ProjectStage.MID_TEST,    'FAILED',     True),

            # --- 4. 多轮成功后完成 --- 返工后达成，分值略低于首轮通过 ---
            ('研发调整后完成',             50,  'RD', ProjectStage.RND,         'DONE',       True),
            ('小试二次通过',               70,  'RD', ProjectStage.PILOT,       'DONE',       True),
            ('中试二次通过',               80,  'RD', ProjectStage.MID_TEST,    'DONE',       True),

            # --- 5. 按阶段终止（首轮 TERMINATED）--- 根据终止时的进度给予阶梯分值 ---
            ('立项阶段项目终止',           0,   'RD', ProjectStage.INIT,        'TERMINATED', False),
            ('资料收集阶段终止',           5,   'RD', ProjectStage.COLLECT,     'TERMINATED', False),
            ('可行性评估阶段终止',         10,  'RD', ProjectStage.FEASIBILITY, 'TERMINATED', False),
            ('研发阶段终止',               15,  'RD', ProjectStage.RND,         'TERMINATED', False),
            ('小试阶段终止',               25,  'RD', ProjectStage.PILOT,       'TERMINATED', False),
            ('中试阶段终止',               35,  'RD', ProjectStage.MID_TEST,    'TERMINATED', False),
            ('量产意向阶段终止',           45,  'RD', ProjectStage.MASS_PROD,   'TERMINATED', False),
            ('最终下单阶段终止',           50,  'RD', ProjectStage.ORDER,       'TERMINATED', False),

            # --- 6. 按阶段终止（多轮 TERMINATED）--- 返工中途终止，略低于首轮终止 ---
            ('返工后研发阶段终止',         10,  'RD', ProjectStage.RND,         'TERMINATED', True),
            ('返工后小试阶段终止',         15,  'RD', ProjectStage.PILOT,       'TERMINATED', True),
            ('返工后中试阶段终止',         25,  'RD', ProjectStage.MID_TEST,    'TERMINATED', True),

            # --- 7. 通用终止兜底 --- 未匹配到具体阶段时的通用终止规则 ---
            ('项目意外终止',               0,   'RD', None,                     'TERMINATED', False),
            ('返工后项目终止',             0,   'RD', None,                     'TERMINATED', True),


            # ================================================================
            #  二、销售规则 (rule_type='SALES')
            # ================================================================

            # --- 1. 前期跟进（首轮 DONE）--- 销售侧重商务推进，前期分值偏保守 ---
            ('项目立项（销售）',           5,   'SALES', ProjectStage.INIT,        'DONE',       False),
            ('收集资料（销售）',           10,  'SALES', ProjectStage.COLLECT,     'DONE',       False),
            ('可行性评估（销售）',         30,  'SALES', ProjectStage.FEASIBILITY, 'DONE',       False),
            ('客户定价完成',               50,  'SALES', ProjectStage.PRICING,     'DONE',       False),

            # --- 2. 研发阶段同步跟进（首轮 DONE）--- 研发推进期间销售的协同价值 ---
            ('研发阶段完成（销售）',       15,  'SALES', ProjectStage.RND,         'DONE',       False),
            ('小试完成（销售）',           25,  'SALES', ProjectStage.PILOT,       'DONE',       False),
            ('中试完成（销售）',           40,  'SALES', ProjectStage.MID_TEST,    'DONE',       False),

            # --- 3. 商务冲刺（首轮 DONE）--- 销售价值在后端集中爆发 ---
            ('量产意向达成（销售）',       80,  'SALES', ProjectStage.MASS_PROD,   'DONE',       False),
            ('开发周期完成（销售）',       100, 'SALES', ProjectStage.ORDER,       'DONE',       False),

            # --- 4. 按阶段终止（首轮 TERMINATED）--- 根据商务推进程度给予阶梯分值 ---
            ('立项阶段终止（销售）',       0,   'SALES', ProjectStage.INIT,        'TERMINATED', False),
            ('资料收集阶段终止（销售）',   2,   'SALES', ProjectStage.COLLECT,     'TERMINATED', False),
            ('可行性评估阶段终止（销售）', 10,  'SALES', ProjectStage.FEASIBILITY, 'TERMINATED', False),
            ('客户定价阶段终止（销售）',   20,  'SALES', ProjectStage.PRICING,     'TERMINATED', False),
            ('研发阶段终止（销售）',       5,   'SALES', ProjectStage.RND,         'TERMINATED', False),
            ('小试阶段终止（销售）',       10,  'SALES', ProjectStage.PILOT,       'TERMINATED', False),
            ('中试阶段终止（销售）',       20,  'SALES', ProjectStage.MID_TEST,    'TERMINATED', False),
            ('量产意向阶段终止（销售）',   40,  'SALES', ProjectStage.MASS_PROD,   'TERMINATED', False),
            ('最终下单阶段终止（销售）',   50,  'SALES', ProjectStage.ORDER,       'TERMINATED', False),

            # --- 5. 异常返工（首轮 FAILED）--- 销售在可迭代阶段的失败得分，反映协同损失 ---
            ('研发异常（销售）',           0,   'SALES', ProjectStage.RND,         'FAILED',     False),
            ('小试失败返工（销售）',       5,   'SALES', ProjectStage.PILOT,       'FAILED',     False),
            ('中试失败返工（销售）',       10,  'SALES', ProjectStage.MID_TEST,    'FAILED',     False),

            # --- 6. 异常返工（多轮 FAILED）--- 多次返工仍未通过，销售给予基础认可分 ---
            ('研发多次返工（销售）',       0,   'SALES', ProjectStage.RND,         'FAILED',     True),
            ('小试多次失败（销售）',       5,   'SALES', ProjectStage.PILOT,       'FAILED',     True),
            ('中试多次失败（销售）',       10,  'SALES', ProjectStage.MID_TEST,    'FAILED',     True),

            # --- 7. 多轮成功后完成 --- 返工后达成，分值略低于首轮 ---
            ('研发调整后完成（销售）',     10,  'SALES', ProjectStage.RND,         'DONE',       True),
            ('小试二次通过（销售）',       20,  'SALES', ProjectStage.PILOT,       'DONE',       True),
            ('中试二次通过（销售）',       30,  'SALES', ProjectStage.MID_TEST,    'DONE',       True),

            # --- 8. 按阶段终止（多轮 TERMINATED）--- 返工中途终止，分值低于首轮 ---
            ('返工后研发终止（销售）',     3,   'SALES', ProjectStage.RND,         'TERMINATED', True),
            ('返工后小试终止（销售）',     5,   'SALES', ProjectStage.PILOT,       'TERMINATED', True),
            ('返工后中试终止（销售）',     10,  'SALES', ProjectStage.MID_TEST,    'TERMINATED', True),

            # --- 9. 通用终止兜底 ---
            ('项目意外终止（销售）',       0,   'SALES', None,                     'TERMINATED', False),
            ('返工后项目终止（销售）',     0,   'SALES', None,                     'TERMINATED', True),
        ]

        self.stdout.write(self.style.MIGRATE_LABEL('正在初始化评分规则...'))

        created_count = 0
        updated_count = 0

        for name, score, rule_type, stage, status, is_multiple in rules_data:
            rule, created = NodeScoreRule.objects.update_or_create(
                rule_type=rule_type,
                trigger_stage=stage,
                trigger_status=status,
                is_multiple_rounds=is_multiple,
                defaults={
                    'name': name,
                    'score_value': score,
                    'description': f'系统初始化规则: {name}'
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'初始化完成！成功创建 {created_count} 条规则，更新 {updated_count} 条规则。'
        ))
        self.stdout.write(self.style.WARNING(
            '提示：规则已更新，已有节点的得分不会自动重算。如需重算全部节点，请通过管理后台逐个保存项目节点。'
        ))
