from django.core.management.base import BaseCommand
from django.db import transaction
from app_dify_sync.models import DifySyncRecord

class Command(BaseCommand):
    """
        python manage.py cleanup_dify_records --confirm
    """
    help = '【一次性工具】清空所有 Dify 同步记录，用于修复数据污染问题。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='必须添加此参数以确认执行删除操作。',
        )

    def handle(self, *args, **kwargs):
        if not kwargs['confirm']:
            self.stdout.write(self.style.ERROR('这是一个危险操作，会清空所有同步记录。'))
            self.stdout.write(self.style.WARNING('请添加 --confirm 参数以确认执行。例如：python manage.py cleanup_dify_records --confirm'))
            return

        self.stdout.write(self.style.HTTP_INFO('--- 开始清空 Dify 同步记录表 ---'))
        
        with transaction.atomic():
            count, _ = DifySyncRecord.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f'\n✅ 清理完成！共删除了 {count} 条记录。'))
        self.stdout.write('现在，您可以重新运行 "bootstrap_dify_sync_records" 来生成干净的同步任务。')
