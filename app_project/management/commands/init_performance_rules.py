from django.core.management.base import BaseCommand
from app_project.models import NodeScoreRule, ProjectStage

class Command(BaseCommand):
    help = '初始化项目绩效评分规则'

    def handle(self, *args, **options):
        # 定义初始规则数据
        # (名称, 分值, 触发阶段, 触发状态, 是否多轮)
        rules_data = [
            # 1. 正常流程完成规则
            ('项目立项完成', 10, ProjectStage.INIT, 'DONE', False),
            ('资料收集完成', 20, ProjectStage.COLLECT, 'DONE', False),
            ('可行性评估通过', 40, ProjectStage.FEASIBILITY, 'DONE', False),
            ('研发阶段成功', 60, ProjectStage.RND, 'DONE', False),
            ('客户小试合格', 80, ProjectStage.PILOT, 'DONE', False),
            ('客户中试合格', 90, ProjectStage.MID_TEST, 'DONE', False),
            ('量产意向达成', 95, ProjectStage.MASS_PROD, 'DONE', False),
            ('项目最终下单/量产', 100, ProjectStage.ORDER, 'DONE', False),

            # 2. 异常与返工规则 (分值较低或为0)
            ('研发不合格重开', 0, ProjectStage.RND, 'FAILED', False),
            ('小试失败返工', 10, ProjectStage.PILOT, 'FAILED', False),
            ('中试失败返工', 20, ProjectStage.MID_TEST, 'FAILED', False),
            
            # 3. 多轮次(返工后)完成规则 (通常比首轮得分略低，以示区别)
            ('研发调整后完成', 50, ProjectStage.RND, 'DONE', True),
            ('小试二次通过', 70, ProjectStage.PILOT, 'DONE', True),
            ('中试二次通过', 80, ProjectStage.MID_TEST, 'DONE', True),

            # 4. 终止规则 (通用)
            ('项目意外终止', 0, None, 'TERMINATED', False),
            ('返工后项目终止', 0, None, 'TERMINATED', True),
        ]

        self.stdout.write(self.style.MIGRATE_LABEL('正在初始化评分规则...'))
        
        created_count = 0
        updated_count = 0

        for name, score, stage, status, is_multiple in rules_data:
            # 使用 update_or_create 确保可重复运行
            rule, created = NodeScoreRule.objects.update_or_create(
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
        self.stdout.write(self.style.WARNING('提示：规则已更新，项目得分将自动开始根据新规则计算。'))
