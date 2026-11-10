"""服务端 API 密钥：永不过期、过期拒绝、停用拒绝。明文不入库。"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from app_user.services.service_api_key import (
    authenticate_service_api_key,
    create_service_api_key,
    hash_service_api_key,
)


class ServiceApiKeyTests(TestCase):
    def test_blank_expiry_never_expires_and_stores_hash(self):
        key, token = create_service_api_key("CRM 官网")
        key.refresh_from_db()
        self.assertTrue(token.startswith("cat_"))
        self.assertIsNone(key.expires_at)
        self.assertNotEqual(key.key_hash, token)
        self.assertEqual(key.key_hash, hash_service_api_key(token))
        self.assertEqual(authenticate_service_api_key(token).pk, key.pk)
        key.refresh_from_db()
        self.assertIsNotNone(key.last_used_at)

    def test_second_use_within_an_hour_does_not_rewrite_last_used(self):
        key, token = create_service_api_key("CRM 官网")
        authenticate_service_api_key(token)
        key.refresh_from_db()
        stamped = key.last_used_at
        authenticate_service_api_key(token)
        key.refresh_from_db()
        self.assertEqual(key.last_used_at, stamped)

    def test_expired_and_inactive_keys_are_rejected(self):
        expired, expired_token = create_service_api_key(
            "过期", expires_at=timezone.now() - timedelta(minutes=1),
        )
        inactive, inactive_token = create_service_api_key("停用")
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        self.assertIsNone(authenticate_service_api_key(expired_token))
        self.assertIsNone(authenticate_service_api_key(inactive_token))
        self.assertIsNone(authenticate_service_api_key("cat_not_the_real_key"))
        expired.refresh_from_db()
        inactive.refresh_from_db()
        self.assertIsNone(expired.last_used_at)
        self.assertIsNone(inactive.last_used_at)
