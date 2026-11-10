"""创建一把目录 API 服务端密钥，明文只打印一次。

用法:
    python manage.py create_service_api_key "CRM 官网"
    python manage.py create_service_api_key "CRM 预发" --expires 2027-01-01T00:00:00
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from app_user.services.service_api_key import create_service_api_key


class Command(BaseCommand):
    help = "创建服务端 API 密钥（明文只输出一次；省略 --expires 则永不过期）"

    def add_arguments(self, parser):
        parser.add_argument("name", help="钥匙名称，例如 CRM 官网")
        parser.add_argument("--expires", help="到期时间，ISO 格式。省略则永不过期")

    def handle(self, *args, **options):
        expires = None
        raw = options.get("expires")
        if raw:
            expires = parse_datetime(raw)
            if expires is None:
                raise CommandError("无法解析 --expires，请用 ISO 时间，如 2027-01-01T00:00:00")
            if timezone.is_naive(expires):
                expires = timezone.make_aware(expires)
        key, token = create_service_api_key(options["name"], expires_at=expires)
        self.stdout.write(self.style.SUCCESS(f"已创建 {key.name}（{key.key_prefix}）"))
        self.stdout.write("明文只显示这一次，请立即交给 CRM，不要写入日志：")
        self.stdout.write(token)
