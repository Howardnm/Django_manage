"""初始化 RBAC 缓存表。

DatabaseCache 的 rbac_cache 缓存表不会随 migrate 自动创建（缓存表不是 model，
Django 的 makemigrations/migrate 均不感知），需通过 createcachetable 手动建表。
本命令封装建表流程，供部署脚本 entrypoint 调用：

    python manage.py init_rbac_cache

幂等：表已存在时 createcachetable 会自动跳过。
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='仅预览，不创建表')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # 前置检查：rbac 缓存未配置时跳过（避免误报）
        from django.conf import settings
        if 'rbac' not in settings.CACHES:
            self.stdout.write(self.style.WARNING(
                "CACHES 中未配置 'rbac' 缓存，跳过建表。"
            ))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'dry-run 模式：跳过 rbac_cache 建表。'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            '创建 rbac_cache 缓存表（幂等）...'))
        call_command('createcachetable', 'rbac_cache',
                     verbosity=options['verbosity'])
        self.stdout.write(self.style.SUCCESS('rbac_cache 缓存表就绪。'))