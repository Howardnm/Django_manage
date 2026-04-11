import time
import signal
from django.core.management.base import BaseCommand
from ...models import WebhookTask
from ...integration.webhooks import perform_webhook_send # 更新导入路径

class Command(BaseCommand):
    help = '后台处理 Webhook 异步任务队列'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)

    def handle_exit(self, sig, frame):
        self.stdout.write(self.style.WARNING('\n正在停止 Webhook 处理器...'))
        self.running = False

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Webhook 后台处理器已启动 (集成层模式)...'))
        
        while self.running:
            tasks = WebhookTask.objects.filter(status='PENDING').order_by('created_at')[:10]
            
            if not tasks:
                time.sleep(5)
                continue

            for task in tasks:
                if not self.running:
                    break
                
                success = perform_webhook_send(task)
                
                status_msg = self.style.SUCCESS("成功") if success else self.style.ERROR(f"失败: {task.last_error}")
                self.stdout.write(f"处理任务 {task.id} [{task.event_type}]: {status_msg}")
            
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Webhook 处理器已安全退出。'))
