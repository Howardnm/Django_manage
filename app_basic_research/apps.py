from django.apps import AppConfig


class AppBasicResearchConfig(AppConfig):
    name = 'app_basic_research'
    verbose_name = '基础预研项目'

    def ready(self):
        import app_basic_research.utils.signals