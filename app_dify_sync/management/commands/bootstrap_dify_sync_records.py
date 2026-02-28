from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.apps import apps
from django.db import transaction

from app_dify_sync.models import DifySyncRecord
from app_dify_sync.utils import get_document_content

class Command(BaseCommand):
    """
    python manage.py bootstrap_dify_sync_records
    """
    help = '为所有已存在的、需要同步的数据创建初始同步记录。'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.HTTP_INFO('--- 开始初始化 Dify 同步记录 ---'))
        
        synced_models_config = settings.DIFY_SYNC_CONFIG.get('DATASETS', {})
        if not synced_models_config:
            raise CommandError("在 settings.py 中没有找到 DIFY_SYNC_CONFIG['DATASETS'] 配置。")

        total_created = 0

        for model_key, dataset_id in synced_models_config.items():
            # 关键修复：在这里也添加 strip()，防止写入被污染的数据
            dataset_id = dataset_id.strip()

            try:
                app_label, model_name = model_key.split('.')
                model = apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                self.stdout.write(self.style.ERROR(f"配置错误：跳过无效的模型 '{model_key}'。"))
                continue

            self.stdout.write(f"\n  -> 正在处理模型: {model._meta.verbose_name}...")
            
            created_in_loop = 0
            with transaction.atomic():
                for instance in model.objects.all().iterator():
                    record, created = DifySyncRecord.objects.get_or_create(
                        content_type=ContentType.objects.get_for_model(instance),
                        object_id=instance.pk,
                        defaults={
                            'dify_dataset_id': dataset_id,
                            'status': DifySyncRecord.SyncStatus.PENDING
                        }
                    )
                    
                    if created:
                        _, text = get_document_content(instance)
                        record.source_hash = record.calculate_hash(text)
                        record.save(update_fields=['source_hash'])
                        created_in_loop += 1
            
            if created_in_loop > 0:
                self.stdout.write(self.style.SUCCESS(f"     - 为 {created_in_loop} 条新记录创建了同步任务。"))
                total_created += created_in_loop
            else:
                self.stdout.write(self.style.HTTP_INFO('     - 所有记录均已存在同步任务。'))

        self.stdout.write(self.style.SUCCESS(f'\n✅ 初始化完成！共创建了 {total_created} 条新的同步任务。'))
        self.stdout.write('现在，您可以运行 "python manage.py sync_to_dify" 来开始同步这些数据了。')
