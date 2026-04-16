import time
import logging
from django.core.management.base import BaseCommand
from app_material.models.sync import WebhookTask # 跨模块引用主系统任务表
from app_material_api.integration.webhooks import perform_webhook_send

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '后台异步处理 Webhook 发送任务队列 (归属于集成服务层)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🚀 [API Integration] Webhook 处理器已启动...'))
        
        while True:
            # 查找待处理任务
            tasks = WebhookTask.objects.filter(status='PENDING').order_by('created_at')[:10]
            
            if not tasks:
                time.sleep(3)
                continue

            for task in tasks:
                self.stdout.write(f"  - 处理集成任务 {task.id}: {task.event_type}...")
                
                # 执行新模块中的发送逻辑
                success = perform_webhook_send(task)
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f"    [OK] 任务 {task.id} 同步成功"))
                else:
                    self.stdout.write(self.style.ERROR(f"    [FAIL] 任务 {task.id} 同步失败"))

            time.sleep(1)
