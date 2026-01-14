from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    department = models.CharField("所属部门", max_length=50, blank=True)
    phone = models.CharField("手机号码", max_length=20, blank=True)
    # 可以加头像 avatar = models.ImageField(...)

    def __str__(self):
        return f"{self.user.username} 的资料"

    class Meta:
        verbose_name = "用户信息"

# 信号量：创建 User 时自动创建 UserProfile，不用手动管
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()