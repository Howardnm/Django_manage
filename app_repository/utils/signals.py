# apps/app_repository/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from app_project.models import Project
from app_repository.models import ProjectRepository

@receiver(post_save, sender=Project)
def create_project_repository(sender, instance, created, **kwargs):
    """
    当 Project 创建时，自动创建一个对应的空 ProjectRepository 档案
    用法：在本app的apps.py，导入：
        class AppRepositoryConfig(AppConfig):
        default_auto_field = 'django.db.models.BigAutoField'
        name = 'app_repository' # 确保这里的路径和你 settings.py 里的一致

        def ready(self):
            # 导入信号，使其生效
            import app_repository.utils.signals
    """
    if created:
        ProjectRepository.objects.create(project=instance)