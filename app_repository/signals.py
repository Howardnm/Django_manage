import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.db import transaction
from .models import Customer, OEM, Salesperson

logger = logging.getLogger(__name__)

# --- 1. 自动为客户创建账号 ---
@receiver(post_save, sender=Customer)
def auto_create_customer_user(sender, instance, created, **kwargs):
    """当创建客户记录时，自动创建一个对应的外部 User 账号"""
    if created and not instance.user:
        try:
            with transaction.atomic():
                # 生成唯一的用户名 (customer_ID)
                username = f"cust_{instance.id}_{instance.short_name or 'user'}"
                
                # 创建 User 对象
                user = User.objects.create_user(
                    username=username,
                    email=instance.email,
                    password=f"Sunwill@{instance.id}", # 默认密码
                    is_staff=False # 外部会员非员工
                )
                
                # 关联到 Customer 模型
                instance.user = user
                instance.save(update_fields=['user'])
                
                # 加入到客户权限组
                group, _ = Group.objects.get_or_create(name='Member_Customer')
                user.groups.add(group)
                
                logger.info(f"Auto-created User {username} for Customer {instance.company_name}")
                
                # TODO: 此处应触发 Webhook 推送到 app_catalog
        except Exception as e:
            logger.error(f"Failed to auto-create User for Customer {instance.id}: {e}")

# --- 2. 自动为主机厂创建账号 ---
@receiver(post_save, sender=OEM)
def auto_create_oem_user(sender, instance, created, **kwargs):
    """当创建 OEM 记录时，自动创建一个对应的外部 User 账号"""
    if created and not instance.user:
        try:
            with transaction.atomic():
                username = f"oem_{instance.id}_{instance.short_name or 'user'}"
                user = User.objects.create_user(
                    username=username,
                    email=instance.contact_email,
                    password=f"Oem@{instance.id}",
                    is_staff=False
                )
                instance.user = user
                instance.save(update_fields=['user'])
                
                group, _ = Group.objects.get_or_create(name='Member_OEM')
                user.groups.add(group)
                
                logger.info(f"Auto-created User {username} for OEM {instance.name}")
        except Exception as e:
            logger.error(f"Failed to auto-create User for OEM {instance.id}: {e}")

# --- 3. 业务员同步逻辑 (仅绑定现有) ---
@receiver(post_save, sender=Salesperson)
def salesperson_account_sync(sender, instance, **kwargs):
    """业务员变动时，确保其 user 是 is_staff"""
    if instance.user and not instance.user.is_staff:
        instance.user.is_staff = True
        instance.user.save(update_fields=['is_staff'])
