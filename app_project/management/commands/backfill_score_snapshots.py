from django.core.management.base import BaseCommand

from app_project.models import Project
from app_project.utils.signals import record_project_score_snapshots


class Command(BaseCommand):
    help = '为所有项目回填成员成绩快照基线（仅当前在册成员）'

    def handle(self, *args, **options):
        total_created = 0
        project_count = 0

        for project in Project.objects.all().iterator():
            project_count += 1
            try:
                total_created += record_project_score_snapshots(project)
            except Exception:
                self.stderr.write(f"项目 {project.pk} 回填失败：")

        self.stdout.write(self.style.SUCCESS(
            f'回填完成！共处理 {project_count} 个项目，写入 {total_created} 条快照。'
        ))