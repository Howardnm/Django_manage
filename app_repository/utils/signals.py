import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from ..models import ProjectRepository
from app_project.models import Project

logger = logging.getLogger(__name__)


# ==========================================
# 1. 项目档案自动化
# ==========================================
@receiver(post_save, sender=Project)
def auto_create_project_repository(sender, instance, created, **kwargs):
    """
    立项即开档案。
    """
    if created:
        ProjectRepository.objects.get_or_create(project=instance)
