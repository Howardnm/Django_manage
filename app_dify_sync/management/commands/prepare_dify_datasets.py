from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.apps import apps

from app_dify_sync.dify_api import create_dataset_in_dify

class Command(BaseCommand):
    help = '【一次性工具】检查Dify配置，并为需要的数据集自动创建知识库。'

    def handle(self, *args, **kwargs):
        self.api_key = settings.DIFY_SYNC_CONFIG.get('API_KEY')
        if not self.api_key or 'YOUR_DIFY_API_KEY' in self.api_key:
            raise CommandError("请在 settings.py 中配置一个有效的 DIFY_API_KEY。")

        self.stdout.write(self.style.HTTP_INFO('--- 开始准备 Dify 数据集 ---'))
        
        dataset_configs = settings.DIFY_SYNC_CONFIG.get('DATASETS', {})
        if not dataset_configs:
            raise CommandError("在 settings.py 中没有找到 DIFY_SYNC_CONFIG['DATASETS'] 配置。")

        all_ok = True
        found_placeholder = False

        for model_key, dataset_id in dataset_configs.items():
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
                found_placeholder = True
                self.stdout.write(f"\n  -> 为模型 '{model_verbose_name}' 自动创建数据集中...")
                
                success, result = create_dataset_in_dify(self.api_key, name=f"Django - {model_verbose_name}")
                
                if success:
                    new_id = result.get('id')
                    self.stdout.write(self.style.SUCCESS(f"     - 成功创建数据集，ID: {new_id}"))
                    self.stdout.write(self.style.WARNING(f"     - 请将此ID更新到 settings.py 的 '{model_key}' 中。"))
                else:
                    self.stdout.write(self.style.ERROR(f"     - 创建数据集失败: {result}"))
                    all_ok = False
            else:
                self.stdout.write(f"  -> 数据集 '{model_verbose_name}' 已配置。")
        
        if not all_ok:
            self.stdout.write(self.style.ERROR("\n数据集准备过程中出现错误，请检查。"))
        elif not found_placeholder:
            self.stdout.write(self.style.SUCCESS("\n所有数据集均已配置，无需创建。"))
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ 数据集创建完成！请务必将新生成的ID更新到您的 settings.py 文件中。"))
