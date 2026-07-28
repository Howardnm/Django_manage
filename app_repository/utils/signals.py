import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db import transaction
from ..models import ProjectRepository
from app_project.models import Project
from app_material_api.services.webhook_service import WebhookService

User = get_user_model()
logger = logging.getLogger(__name__)

# ==========================================
# 1. 统一身份同步 (电子手册会员数据源)
# ==========================================
@receiver(post_save, sender=User)
def sync_member_to_catalog(sender, instance, created, **kwargs):
    """
    当用户信息、角色或公司归属发生变化时，同步精简画像到电子手册。
    """
    # 确定角色类型
    role = 'CUSTOMER'
    if instance.is_superuser or instance.is_staff or (instance.user_type and instance.user_type.is_internal):
        role = 'STAFF'
    elif instance.associated_oem:
        role = 'OEM'
    elif instance.associated_customer:
        role = 'CUSTOMER'
    else:
        # 如果既不是员工也没有公司归属，暂不同步（防止同步孤立账号）
        return

    # 构建 4D 精简画像
    sync_data = {
        'token': str(instance.member_token),
        'display_name': instance.get_full_name() or instance.username,
        'role': role,
        'is_active': instance.is_active,
        # 扩展权限因子 (供子系统 Session 使用)
        'user_type': instance.user_type,
        'user_level': instance.user_level,
        'dept_code': instance.department.code if instance.department else "NONE"
    }

    # 使用重构后的低代码 WebhookService 执行异步同步
    transaction.on_commit(lambda: WebhookService.notify_member_sync(sync_data))


# ==========================================
# 2. 项目档案自动化
# ==========================================
@receiver(post_save, sender=Project)
def auto_create_project_repository(sender, instance, created, **kwargs):
    """
    立项即开档案。
    """
    if created:
        ProjectRepository.objects.get_or_create(project=instance)
