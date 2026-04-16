import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.db import transaction
from ..models import Customer, OEM, ProjectRepository # 移除 Salesperson
from app_project.models import Project
from app_material_api.integration.webhooks import send_data_sync_webhook

logger = logging.getLogger(__name__)

def _push_member_to_catalog(instance, role_type):
    if not instance.user or not instance.member_token:
        return
    data = {
        'token': str(instance.member_token),
        'username': instance.user.username,
        'display_name': str(instance),
        'email': instance.user.email,
        'role': role_type,
        'is_active': instance.is_active
    }
    send_data_sync_webhook('member_sync', 'member', data)

# --- 1. 自动为客户创建账号 ---
@receiver(post_save, sender=Customer)
def auto_create_customer_user(sender, instance, created, **kwargs):
    if created and not instance.user:
        try:
            with transaction.atomic():
                username = f"cust_{instance.id}"
                user = User.objects.create_user(
                    username=username,
                    email=instance.email or f"cust{instance.id}@sunwill.com.cn",
                    password=f"Sunwill@{instance.id}", 
                    is_staff=False 
                )
                instance.user = user
                instance.save(update_fields=['user'])
                group, _ = Group.objects.get_or_create(name='Member_Customer')
                user.groups.add(group)
        except Exception as e:
            logger.error(f"Failed to auto-create User for Customer {instance.id}: {e}")
    transaction.on_commit(lambda: _push_member_to_catalog(instance, 'CUSTOMER'))

# --- 2. 自动为主机厂创建账号 ---
@receiver(post_save, sender=OEM)
def auto_create_oem_user(sender, instance, created, **kwargs):
    if created and not instance.user:
        try:
            with transaction.atomic():
                username = f"oem_{instance.id}"
                user = User.objects.create_user(
                    username=username,
                    email=instance.contact_email or f"oem{instance.id}@sunwill.com.cn",
                    password=f"Oem@{instance.id}",
                    is_staff=False
                )
                instance.user = user
                instance.save(update_fields=['user'])
                group, _ = Group.objects.get_or_create(name='Member_OEM')
                user.groups.add(group)
        except Exception as e:
            logger.error(f"Failed to auto-create User for OEM {instance.id}: {e}")
    transaction.on_commit(lambda: _push_member_to_catalog(instance, 'OEM'))

# --- 3. 全量员工同步逻辑 (核心) ---
@receiver(post_save, sender=User)
def staff_member_sync(sender, instance, created, **kwargs):
    if instance.is_staff:
        data = {
            'token': f"staff_{instance.id}",
            'username': instance.username,
            'display_name': instance.get_full_name() or instance.username,
            'email': instance.email,
            'role': 'STAFF',
            'is_active': instance.is_active
        }
        transaction.on_commit(lambda: send_data_sync_webhook('member_sync', 'member', data))

# --- 4. 自动为项目创建档案 ---
@receiver(post_save, sender=Project)
def create_project_repository(sender, instance, created, **kwargs):
    if created:
        ProjectRepository.objects.get_or_create(project=instance)
