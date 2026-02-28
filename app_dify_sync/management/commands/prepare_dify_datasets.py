from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.apps import apps

from app_dify_sync.dify_api import get_dataset_in_dify, create_dataset_in_dify

class Command(BaseCommand):
    help = '【智能环境准备工具】检查Dify数据集ID，如果不存在则自动创建。'

    def handle(self, *args, **kwargs):
        self.api_key = settings.DIFY_SYNC_CONFIG.get('API_KEY')
        if not self.api_key or 'YOUR_DIFY_API_KEY' in self.api_key:
            raise CommandError("请在 settings.py 中配置一个有效的 DIFY_API_KEY。")

        self.stdout.write(self.style.HTTP_INFO('--- 开始准备 Dify 数据集 (检查或创建) ---'))
        
        dataset_configs = settings.DIFY_SYNC_CONFIG.get('DATASETS', {})
        if not dataset_configs:
            raise CommandError("在 settings.py 中没有找到 DIFY_SYNC_CONFIG['DATASETS'] 配置。")

        all_ok = True
        needs_update = False

        for model_key, dataset_id in dataset_configs.items():
            dataset_id = dataset_id.strip()

            try:
                app_label, model_name = model_key.split('.')
                model = apps.get_model(app_label, model_name)
                model_verbose_name = model._meta.verbose_name
            except (ValueError, LookupError):
                self.stdout.write(self.style.ERROR(f"配置错误：跳过无效的模型 '{model_key}'。"))
                all_ok = False
                continue

            # 1. 检查 ID 是否为占位符或无效
            is_placeholder = "YOUR_" in dataset_id or not dataset_id
            
            if is_placeholder:
                # 如果是占位符，直接进入创建流程
                self.stdout.write(f"\n  -> 配置项 '{model_verbose_name}' 未配置ID，将自动创建...")
                success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")
            else:
                # 如果不是占位符，先验证其存在性
                self.stdout.write(f"\n  -> 正在验证 '{model_verbose_name}' 的数据集 (ID: {dataset_id})...")
                success, result = get_dataset_in_dify(self.api_key, dataset_id)
                if success:
                    dify_name = result.get('name', '未知名称')
                    self.stdout.write(self.style.SUCCESS(f"     - 验证成功！Dify 知识库名称: '{dify_name}'"))
                    continue # 验证成功，处理下一个
                else:
                    # 验证失败，进入创建流程
                    self.stdout.write(self.style.WARNING(f"     - 验证失败: ID '{dataset_id}' 在 Dify 平台不存在。将为您创建一个新的。"))
                    success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")

            # 统一处理创建结果
            if success:
                needs_update = True
                new_id = result.get('id')
                self.stdout.write(self.style.SUCCESS(f"     - 成功创建新知识库，新ID: {new_id}"))
                self.stdout.write(self.style.WARNING(f"     - 🔴 重要：请将此新ID更新到 settings.py 的 '{model_key}' 中。"))
            else:
                self.stdout.write(self.style.ERROR(f"     - 创建新知识库失败: {result}"))
                all_ok = False
        
        if not all_ok:
            self.stdout.write(self.style.ERROR("\n❌ 数据集准备过程中出现错误，请检查。"))
            exit(1)
        elif needs_update:
            self.stdout.write(self.style.WARNING("\n⚠️ 部分数据集是新创建的，请务必根据上面的提示更新您的 settings.py 文件，然后再执行后续操作！"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ 所有数据集配置均已验证通过！环境准备就绪。"))
