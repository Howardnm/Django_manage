from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.apps import apps
import pprint

from app_dify_sync.dify_api import get_dataset_in_dify, create_dataset_in_dify

class Command(BaseCommand):
    help = '【智能环境准备工具】检查Dify数据集ID，如果不存在则自动创建，并生成可复制的配置。'

    def handle(self, *args, **kwargs):
        self.api_key = settings.DIFY_SYNC_CONFIG.get('API_KEY')
        if not self.api_key or 'YOUR_DIFY_API_KEY' in self.api_key:
            raise CommandError("请在 settings.py 中配置一个有效的 DIFY_API_KEY。")

        self.stdout.write(self.style.HTTP_INFO('--- 开始准备 Dify 数据集 (检查或创建) ---'))
        
        dataset_configs = settings.DIFY_SYNC_CONFIG.get('DATASETS', {})
        if not dataset_configs:
            raise CommandError("在 settings.py 中没有找到 DIFY_SYNC_CONFIG['DATASETS'] 配置。")

        final_dataset_ids = {}
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

            is_placeholder = "YOUR_" in dataset_id or not dataset_id
            
            if is_placeholder:
                self.stdout.write(f"\n  -> 配置项 '{model_verbose_name}' 未配置ID，将自动创建...")
                success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")
            else:
                self.stdout.write(f"\n  -> 正在验证 '{model_verbose_name}' 的数据集 (ID: {dataset_id})...")
                success, result = get_dataset_in_dify(self.api_key, dataset_id)
                if success:
                    dify_name = result.get('name', '未知名称')
                    self.stdout.write(self.style.SUCCESS(f"     - 验证成功！Dify 知识库名称: '{dify_name}'"))
                    final_dataset_ids[model_key] = dataset_id
                    continue
                else:
                    self.stdout.write(self.style.WARNING(f"     - 验证失败: ID '{dataset_id}' 在 Dify 平台不存在。将为您创建一个新的。"))
                    success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")

            if success:
                needs_update = True
                new_id = result.get('id')
                final_dataset_ids[model_key] = new_id
                self.stdout.write(self.style.SUCCESS(f"     - 成功创建新知识库，新ID: {new_id}"))
            else:
                self.stdout.write(self.style.ERROR(f"     - 创建新知识库失败: {result}"))
                all_ok = False
        
        if not all_ok:
            self.stdout.write(self.style.ERROR("\n❌ 数据集准备过程中出现错误，请检查。"))
            exit(1)
        
        if needs_update:
            self.stdout.write(self.style.SUCCESS("\n" + "="*50))
            self.stdout.write(self.style.WARNING("⚠️  请注意：已为您创建了新的数据集。"))
            self.stdout.write("请将以下整个 'DATASETS' 字典代码块，完整地复制并覆盖到您的 settings.py 文件中：")
            
            # 使用 pprint 格式化输出，保证美观和正确性
            pretty_datasets = pprint.pformat(final_dataset_ids, indent=4)
            
            # 打印带引导的代码块
            self.stdout.write("\n'DATASETS': " + pretty_datasets + "\n")
            self.stdout.write("="*50 + "\n")
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ 所有数据集配置均已验证通过！环境准备就绪。"))
