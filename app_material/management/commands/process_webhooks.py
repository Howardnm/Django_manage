import time
import logging
from django.core.management.base import BaseCommand
from ...models.sync import WebhookTask
from ...integration.webhooks import perform_webhook_send

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '后台异步处理 Webhook 发送任务队列'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 Webhook 处理器已启动，正在监听任务...'))
        
        while True:
            # 1. 获取所有待处理或需要重试的任务
            # 这里的逻辑：状态为 PENDING 且重试次数未达上限
            tasks = WebhookTask.objects.filter(status='PENDING').order_by('created_at')[:10]
            
            if not tasks:
                # 如果没任务，休眠 3 秒再查，避免过度消耗 CPU
                time.sleep(3)
                continue

            for task in tasks:
                self.stdout.write(f"  - 正在处理任务 {task.id}: {task.event_type}...")
                
                # 执行发送
                success = perform_webhook_send(task)
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] 任务 {task.id} 发送成功"))
                else:
                    self.stdout.write(self.style.ERROR(f"    [FAIL] 任务 {task.id} 发送失败，已记录错误。"))

            # 批处理完后稍微休息下
            time.sleep(1)
