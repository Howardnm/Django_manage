"""已注册到 Admin 的业务模型不应再被 Django 自动加上英文复数 s。"""

from django.contrib import admin
from django.test import SimpleTestCase


class AdminVerbosePluralTests(SimpleTestCase):
    def test_registered_app_models_do_not_get_english_plural_s(self):
        offenders = []
        for model in admin.site._registry:
            if not model._meta.app_label.startswith("app_"):
                continue
            singular = str(model._meta.verbose_name)
            plural = str(model._meta.verbose_name_plural)
            if plural == f"{singular}s":
                offenders.append(f"{model._meta.label}: {plural}")
        self.assertEqual(offenders, [])
