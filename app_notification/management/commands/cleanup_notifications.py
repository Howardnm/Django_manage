import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from app_notification.models import Notification

class Command(BaseCommand):
    """
    您可以随时在终端中运行以下命令来手动清理旧的通知：
    python manage.py cleanup_notifications
    0 3 * * * /path/to/your/project/venv/bin/python /path/to/your/project/manage.py cleanup_notifications
    """
    help = '清理旧的通知消息'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.HTTP_INFO('--- 开始清理旧通知 ---'))

        # 1. 计算截止时间点
        now = timezone.now()
        read_cutoff_date = now - datetime.timedelta(days=3)
        unread_cutoff_date = now - datetime.timedelta(days=30)

        self.stdout.write(f"已读消息的保留期限: 3 天 (截止日期: {read_cutoff_date.strftime('%Y-%m-%d')})")
        self.stdout.write(f"未读消息的保留期限: 30 天 (截止日期: {unread_cutoff_date.strftime('%Y-%m-%d')})")

        # 2. 查询并删除已读的旧通知
        read_to_delete = Notification.objects.filter(
            unread=False,
            timestamp__lt=read_cutoff_date
        )
        read_count, _ = read_to_delete.delete()

        if read_count > 0:
            self.stdout.write(self.style.SUCCESS(f'  [✓] 成功删除 {read_count} 条已读的旧通知。'))
        else:
            self.stdout.write('  [-] 没有需要清理的已读通知。')

        # 3. 查询并删除未读的旧通知
        unread_to_delete = Notification.objects.filter(
            unread=True,
            timestamp__lt=unread_cutoff_date
        )
        unread_count, _ = unread_to_delete.delete()

        if unread_count > 0:
            self.stdout.write(self.style.SUCCESS(f'  [✓] 成功删除 {unread_count} 条未读的旧通知。'))
        else:
            self.stdout.write('  [-] 没有需要清理的未读通知。')
            
        self.stdout.write(self.style.SUCCESS('\n✅ 清理完成！'))
