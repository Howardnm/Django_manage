"""get_mcp_health：注册期可观测状态 + 调用人权限自检。

夹具复用 test_tool_access 的 McpToolFixtureMixin —— 权限自检要的正是那套
角色 / 等级 / 权限码组合（alice 全过、dave 卡 L1、noperm 卡 L3）。
"""
from django.test import TestCase

from app_mcp_server.core import registry
from app_mcp_server.core.server import mcp
from app_mcp_server.tests.test_tool_access import McpToolFixtureMixin, empty_ctx, fake_ctx
from app_mcp_server.tools.health import _MODULES, get_mcp_health
from app_user.models import ModuleAccessConfig
from app_user.services.identity_service import IdentityService


def _by_module(data):
    return {entry["module"]: entry for entry in data["module_access"]}


class McpHealthTests(McpToolFixtureMixin, TestCase):
    def test_reports_caller_and_registry(self):
        data = get_mcp_health(fake_ctx(self.alice, "get_mcp_health"))

        self.assertIs(data["ok"], True)
        self.assertEqual(data["caller"]["username"], "alice")
        self.assertEqual(data["caller"]["role"], "研发工程师")
        self.assertEqual(data["caller"]["level"], 1)
        self.assertEqual(data["caller"]["department"], "研发一部")

        tools = data["tools"]
        self.assertGreaterEqual(tools["registered"], 7)
        # 每个工具都套了 @safe_tool 且发布出了 output_schema
        self.assertEqual(tools["unguarded"], [])
        self.assertEqual(tools["load_failures"], [])
        self.assertEqual(tools["duplicate_names"], [])

    def test_requires_identity(self):
        result = get_mcp_health(empty_ctx())
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_code"], "NO_IDENTITY")

    def test_every_module_allowed_for_full_access_user(self):
        data = get_mcp_health(fake_ctx(self.alice, "get_mcp_health"))
        access = _by_module(data)
        self.assertEqual(set(access), {"project", "formula", "material"})
        for module, entry in access.items():
            with self.subTest(module=module):
                self.assertIs(entry["allowed"], True)
                self.assertIsNone(entry["reason"])
                # 准入过了不等于看得到全部数据，这一点必须说清
                self.assertIn("部门", entry["note"])

    def test_l1_role_denied_is_attributed(self):
        data = get_mcp_health(fake_ctx(self.dave, "get_mcp_health"))
        entry = _by_module(data)["project"]
        self.assertIs(entry["allowed"], False)
        self.assertIn("L1", entry["reason"])
        self.assertNotIn("note", entry)

    def test_l3_permission_denied_is_attributed(self):
        data = get_mcp_health(fake_ctx(self.noperm, "get_mcp_health"))
        entry = _by_module(data)["project"]
        self.assertIs(entry["allowed"], False)
        self.assertIn("L3", entry["reason"])
        self.assertIn("app_project.view_project", entry["reason"])

    def test_l2_level_denied_is_attributed(self):
        cfg = ModuleAccessConfig.objects.get(module_code="project")
        cfg.min_level = 5
        cfg.save(update_fields=["min_level"])
        IdentityService.invalidate_cache()

        entry = _by_module(get_mcp_health(fake_ctx(self.alice, "get_mcp_health")))["project"]
        self.assertIs(entry["allowed"], False)
        self.assertIn("L2", entry["reason"])

    def test_module_table_matches_tool_permissions(self):
        """模块表从工具模块导入，防止权限码在两处各写一份而漂移。"""
        from app_mcp_server.tools import formulas, materials, projects

        expected = {
            "project": (projects.ProjectAccessMixin, projects._PERM),
            "formula": (formulas.FormulaAccessMixin, formulas._PERM),
            "material": (materials.MaterialAccessMixin, materials._MATERIAL_PERM),
        }
        self.assertEqual(
            {code: (mixin, perm) for code, mixin, perm in _MODULES}, expected,
        )

    def test_duplicate_registration_is_reported(self):
        registry.reset()
        try:
            def search_projects(ctx):  # noqa: ARG001 - 故意重名
                """撞名"""

            mcp.add_tool(search_projects, annotations=None)
            self.assertIn("search_projects", registry.duplicate_names())

            data = get_mcp_health(fake_ctx(self.alice, "get_mcp_health"))
            self.assertIn("search_projects", data["tools"]["duplicate_names"])
        finally:
            registry.reset()

    def test_unguarded_tool_is_reported(self):
        """漏套 @safe_tool（或注解读不出 schema）的工具必须被点名。"""
        def naked_tool(ctx) -> dict:  # noqa: ARG001
            """没有 @safe_tool、也没有 structured output"""
            return {}

        mcp.add_tool(naked_tool, annotations=None)
        try:
            data = get_mcp_health(fake_ctx(self.alice, "get_mcp_health"))
            self.assertIn("naked_tool", data["tools"]["unguarded"])
            self.assertEqual(
                data["tools"]["guarded"] + len(data["tools"]["unguarded"]),
                data["tools"]["registered"],
            )
        finally:
            mcp._tool_manager.remove_tool("naked_tool")

    def test_load_failure_is_reported(self):
        registry.record_module("app_xxx.mcp_tools", False, "ImportError: boom")
        try:
            data = get_mcp_health(fake_ctx(self.alice, "get_mcp_health"))
            self.assertEqual(
                data["tools"]["load_failures"],
                [{"module": "app_xxx.mcp_tools", "error": "ImportError: boom"}],
            )
        finally:
            registry.reset()
