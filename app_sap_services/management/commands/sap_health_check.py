"""Django 管理命令: 检测 SAP 连接是否正常"""

from django.core.management.base import BaseCommand

from app_sap_services.services.connection import connection_pool


class Command(BaseCommand):
    help = '检测 SAP RFC 连接是否正常'

    def handle(self, **options):
        self.stdout.write('正在检测 SAP 连接...')
        ok = connection_pool.health_check()
        if ok:
            self.stdout.write(self.style.SUCCESS('SAP 连接正常'))
        else:
            self.stdout.write(self.style.ERROR('SAP 连接失败'))
