import os
import time
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.apps import apps

from app_dify_sync.models import DifySyncRecord
from app_dify_sync.dify_api import create_dataset_in_dify, create_document_in_dify, update_document_in_dify, delete_document_in_dify
from app_dify_sync.utils import get_document_content

class Command(BaseCommand):
    """
    python manage.py sync_to_dify
    """
    help = '检查并创建Dify数据集，然后同步数据到Dify知识库'

    def handle(self, *args, **kwargs):
        self.api_key = settings.DIFY_SYNC_CONFIG.get('API_KEY')
        if not self.api_key or 'YOUR_DIFY_API_KEY' in self.api_key:
            raise CommandError("请在 settings.py 中配置一个有效的 DIFY_API_KEY。")

        self.stdout.write(self.style.HTTP_INFO('--- 步骤 1/2: 准备 Dify 数据集 ---'))
        
        prepared_datasets = self._prepare_datasets()
        if prepared_datasets is None:
            return

        self.stdout.write(self.style.HTTP_INFO('\n--- 步骤 2/2: 开始同步文档数据 ---'))
        
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
                    
                    self.process_record(locked_record, prepared_datasets)

                except DifySyncRecord.DoesNotExist:
                    continue
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'处理记录 {record.pk} 时发生意外错误: {e}'))
                    record.status = DifySyncRecord.SyncStatus.FAILED
                    record.error_message = str(e)
                    record.save()

        self.stdout.write(self.style.SUCCESS('\n✅ 同步完成！'))

    def _prepare_datasets(self):
        dataset_configs = settings.DIFY_SYNC_CONFIG.get('DATASETS', {})
        real_dataset_ids = {}
        all_ok = True

        for model_key, dataset_id in dataset_configs.items():
            # 关键修复：自动去除 dataset_id 前后的空格
            dataset_id = dataset_id.strip()

            try:
                app_label, model_name = model_key.split('.')
                model = apps.get_model(app_label, model_name)
                model_verbose_name = model._meta.verbose_name
            except (ValueError, LookupError):
                self.stdout.write(self.style.ERROR(f"配置错误：无效的模型 '{model_key}'。"))
                all_ok = False
                continue

            if "YOUR_" in dataset_id or not dataset_id:
                self.stdout.write(f"  -> 为模型 '{model_verbose_name}' 自动创建数据集中...")
                success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")
                if success:
                    new_id = result.get('id')
                    real_dataset_ids[model_key] = new_id
                    self.stdout.write(self.style.SUCCESS(f"     - 成功创建数据集，ID: {new_id}"))
                    self.stdout.write(self.style.WARNING(f"     - 请将此ID更新到 settings.py 的 '{model_key}' 中。"))
                else:
                    self.stdout.write(self.style.ERROR(f"     - 创建数据集失败: {result}"))
                    all_ok = False
            else:
                real_dataset_ids[model_key] = dataset_id
                self.stdout.write(f"  -> 数据集 '{model_verbose_name}' 已配置，ID: {dataset_id}")
        
        return real_dataset_ids if all_ok else None

    def process_record(self, record: DifySyncRecord, prepared_datasets: dict):
        dataset_id = record.dify_dataset_id
        if not dataset_id:
            model_key = f"{record.content_type.app_label}.{record.content_type.model}"
            dataset_id = prepared_datasets.get(model_key)
            if not dataset_id:
                record.status = DifySyncRecord.SyncStatus.FAILED
                record.error_message = f"找不到模型 {model_key} 的数据集ID"
                record.save()
                return
            record.dify_dataset_id = dataset_id.strip() # 确保回填时也去除空格
            record.save(update_fields=['dify_dataset_id'])

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
            self.process_record(record, prepared_datasets)
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
