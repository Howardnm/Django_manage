import time
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from app_dify_sync.models import DifySyncRecord
from app_dify_sync.dify_api import create_document_in_dify, update_document_in_dify, delete_document_in_dify
from app_dify_sync.utils import get_document_content

class Command(BaseCommand):
    help = '同步数据到 Dify 知识库。假定所有数据集ID已在settings.py中正确配置。'

    def handle(self, *args, **kwargs):
        self.api_key = settings.DIFY_SYNC_CONFIG.get('API_KEY')
        if not self.api_key or 'YOUR_DIFY_API_KEY' in self.api_key:
            raise CommandError("请在 settings.py 中配置一个有效的 DIFY_API_KEY。")

        self.stdout.write(self.style.HTTP_INFO('--- 开始同步文档数据到 Dify ---'))
        
        records_to_process = DifySyncRecord.objects.filter(
            status__in=[
                DifySyncRecord.SyncStatus.PENDING,
                DifySyncRecord.SyncStatus.OUTDATED,
                DifySyncRecord.SyncStatus.DELETED,
                DifySyncRecord.SyncStatus.FAILED,
            ]
        ).select_related('content_type')

        if not records_to_process.exists():
            self.stdout.write(self.style.SUCCESS('没有需要同步的文档。'))
            return

        self.stdout.write(f'发现 {records_to_process.count()} 条记录需要处理...')

        for record in records_to_process:
            with transaction.atomic():
                try:
                    locked_record = DifySyncRecord.objects.select_for_update().get(pk=record.pk)
                    
                    if locked_record.status not in [DifySyncRecord.SyncStatus.PENDING, DifySyncRecord.SyncStatus.OUTDATED, DifySyncRecord.SyncStatus.DELETED, DifySyncRecord.SyncStatus.FAILED]:
                        continue

                    locked_record.status = DifySyncRecord.SyncStatus.SYNCING
                    locked_record.save(update_fields=['status'])
                    
                    self.process_record(locked_record)

                except DifySyncRecord.DoesNotExist:
                    continue
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理记录 {record.pk} 时发生意外错误: {e}'))
                    record.status = DifySyncRecord.SyncStatus.FAILED
                    record.error_message = str(e)
                    record.save()

        self.stdout.write(self.style.SUCCESS('\n✅ 同步完成！'))

    def process_record(self, record: DifySyncRecord):
        self.stdout.write(f'\n  -> 正在处理: {record.content_object} (状态: {record.status})')

        dataset_id = record.dify_dataset_id.strip() if record.dify_dataset_id else None
        
        if not dataset_id or "YOUR_" in dataset_id:
            self.stdout.write(self.style.ERROR(f'     - 错误：记录 {record.pk} 的数据集ID无效或未配置，无法同步。'))
            record.status = DifySyncRecord.SyncStatus.FAILED
            record.error_message = "数据集ID无效或未在引导步骤中正确设置。"
            record.save()
            return

        if record.status == DifySyncRecord.SyncStatus.DELETED:
            if not record.dify_document_id:
                record.delete()
                return
            success, message = delete_document_in_dify(self.api_key, dataset_id, record.dify_document_id)
            if success: record.delete()
            else:
                record.status = DifySyncRecord.SyncStatus.FAILED
                record.error_message = f"删除失败: {message}"
                record.save()
            return

        source_object = record.content_object
        if not source_object:
            record.status = DifySyncRecord.SyncStatus.DELETED
            record.save()
            self.process_record(record)
            return

        name, text = get_document_content(source_object)
        new_hash = record.calculate_hash(text)

        if not record.dify_document_id:
            success, result = create_document_in_dify(self.api_key, dataset_id, name, text, record.object_id)
            if success:
                record.dify_document_id = result
                record.status = DifySyncRecord.SyncStatus.COMPLETED
                record.source_hash = new_hash
                record.last_sync_at = timezone.now()
                record.last_success_at = timezone.now()
                record.error_message = None
                record.save()
            else:
                record.status = DifySyncRecord.SyncStatus.FAILED
                record.error_message = f"创建失败: {result}"
                record.last_sync_at = timezone.now()
                record.save()
        else:
            if record.source_hash == new_hash and record.status != DifySyncRecord.SyncStatus.FAILED:
                record.status = DifySyncRecord.SyncStatus.COMPLETED
                record.save(update_fields=['status'])
                return
            success, message = update_document_in_dify(self.api_key, dataset_id, record.dify_document_id, name, text)
            if success:
                record.status = DifySyncRecord.SyncStatus.COMPLETED
                record.source_hash = new_hash
                record.last_sync_at = timezone.now()
                record.last_success_at = timezone.now()
                record.error_message = None
                record.save()
            else:
                record.status = DifySyncRecord.SyncStatus.FAILED
                record.error_message = f"更新失败: {message}"
                record.last_sync_at = timezone.now()
                record.save()
