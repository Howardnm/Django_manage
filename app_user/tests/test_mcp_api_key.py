"""个人 MCP API Key：生成、哈希、未开通拒绝。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_user.services.mcp_api_key import (
    McpApiKeyDisabled,
    authenticate_mcp_api_key,
    generate_mcp_api_key,
    hash_mcp_api_key,
)

User = get_user_model()


class McpApiKeyServiceTests(TestCase):
    def test_generate_requires_enabled(self):
        user = User.objects.create_user(
            username="off", email="off@corp.com", password="x",
        )
        with self.assertRaises(McpApiKeyDisabled):
            generate_mcp_api_key(user)

    def test_generate_stores_hash_not_plaintext(self):
        user = User.objects.create_user(
            username="on", email="on@corp.com", password="x",
            mcp_api_key_enabled=True,
        )
        token = generate_mcp_api_key(user)
        user.refresh_from_db()
        self.assertTrue(token.startswith("mcp_"))
        self.assertNotEqual(user.mcp_api_key_hash, token)
        self.assertEqual(user.mcp_api_key_hash, hash_mcp_api_key(token))
        self.assertEqual(authenticate_mcp_api_key(token).pk, user.pk)
        self.assertIsNone(authenticate_mcp_api_key("mcp_not_the_real_key"))
