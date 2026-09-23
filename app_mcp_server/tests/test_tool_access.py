"""MCP 工具：tool claim + L1~L5 过滤 + 结构化失败信封 + 空值约定。"""
import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, TransactionTestCase

from app_formula.models import FormulaTestResult, LabFormula
from app_material.models import (
    MaterialDataPoint,
    MaterialLibrary,
    MaterialType,
    MetricCategory,
    TestConfig,
)
from app_mcp_server.core.server import mcp
from app_mcp_server.tools.formulas import get_formula_detail, search_formulas
from app_mcp_server.tools.health import get_mcp_health
from app_mcp_server.tools.materials import get_material_and_formulas, search_material_library
from app_mcp_server.tools.projects import get_project_details, search_projects
from app_project.models import Project, ProjectMember, ProjectSalesMember
from app_repository.models import ProjectRepository
from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()

ALL_TOOLS = (
    search_projects, get_project_details,
    search_formulas, get_formula_detail,
    search_material_library, get_material_and_formulas,
    get_mcp_health,
)


def fake_ctx(user, tool):
    state = SimpleNamespace(mcp_user_id=user.pk if user else None, mcp_jwt={"tool": tool})
    request = SimpleNamespace(state=state)
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


def empty_ctx():
    return SimpleNamespace(request_context=SimpleNamespace(request=None))


def _grant(user, app_label, *codenames):
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label=app_label,
    )
    user.user_permissions.add(*perms)


class McpToolFixtureMixin:
    """共用夹具。TestCase 与 TransactionTestCase 两种基类都要用。"""

    def setUp(self):
        super().setUp()
        self.engineer = UserRole.objects.create(code="ENGINEER", name="研发工程师")
        self.sales = UserRole.objects.create(code="SALES", name="业务员")
        rnd_group = RoleGroup.objects.create(code="RND", name="研发组")
        rnd_group.roles.add(self.engineer)

        self.dept_a = Department.objects.create(name="研发一部")
        self.dept_b = Department.objects.create(name="研发二部")

        project_cfg = ModuleAccessConfig.objects.create(
            module_code="project", module_name="项目管理中心",
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        project_cfg.role_groups.add(rnd_group)

        formula_cfg = ModuleAccessConfig.objects.create(
            module_code="formula", module_name="实验配方库",
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        formula_cfg.role_groups.add(rnd_group)

        material_cfg = ModuleAccessConfig.objects.create(
            module_code="material", module_name="材料成品库",
            enforce_dept_isolation=True, enforce_group_isolation=False,
        )
        material_cfg.role_groups.add(rnd_group)
        IdentityService.invalidate_cache()

        self.alice = self._user("alice", "alice@corp.com", self.engineer, self.dept_a)
        self.bob = self._user("bob", "bob@corp.com", self.engineer, self.dept_b)
        self.carol = self._user("carol", "carol@corp.com", self.engineer, self.dept_b)
        self.dave = self._user("dave", "dave@corp.com", self.sales, self.dept_a)
        self.noperm = self._user("noperm", "noperm@corp.com", self.engineer, self.dept_a)
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@corp.com", password="x",
        )

        _grant(self.alice, "app_project", "view_project")
        _grant(self.alice, "app_formula", "view_labformula")
        _grant(self.alice, "app_material", "view_materiallibrary")
        _grant(self.bob, "app_project", "view_project")
        _grant(self.bob, "app_formula", "view_labformula")
        _grant(self.bob, "app_material", "view_materiallibrary")
        _grant(self.carol, "app_project", "view_project")
        _grant(self.dave, "app_project", "view_project")

        self.mt = MaterialType.objects.create(name="PA66")
        self.mat_alice = MaterialLibrary.objects.create(
            grade_name="PA66-A", sap_material_code="SAP-A",
            category=self.mt, creator=self.alice,
        )
        self.mat_bob = MaterialLibrary.objects.create(
            grade_name="PA66-B", sap_material_code="SAP-B",
            category=self.mt, creator=self.bob,
        )

        self.p_alice = Project.objects.create(
            code="PA", name="Alice项目", manager=self.alice, material=self.mat_alice,
        )
        self.p_bob = Project.objects.create(
            code="PB", name="Bob项目", manager=self.bob, material=self.mat_bob,
        )
        self.p_member = Project.objects.create(
            code="PM", name="协同项目", manager=self.bob, material=self.mat_bob,
        )
        ProjectMember.objects.create(project=self.p_member, user=self.alice)
        self.p_sales = Project.objects.create(
            code="PS", name="销售项目", manager=self.bob, material=self.mat_bob,
        )
        ProjectSalesMember.objects.create(project=self.p_sales, user=self.alice)

        self.f_alice = LabFormula.objects.create(
            code="FA-001", name="Alice配方", material_type=self.mt,
            project=self.p_alice, creator=self.alice,
        )
        self.f_bob = LabFormula.objects.create(
            code="FB-001", name="Bob配方", material_type=self.mt,
            project=self.p_bob, creator=self.bob, version=1,
        )
        LabFormula.objects.create(
            code="FB-001", name="Bob配方v2", material_type=self.mt,
            project=self.p_bob, creator=self.bob, version=2,
        )

        # —— 空值约定用的夹具 ——
        # 有业务档案但没附件：associated_files 应是 []（"确实没有"）
        self.p_repo_no_files = Project.objects.create(
            code="PR", name="有档案无附件", manager=self.alice,
        )
        # 无业务档案：associated_files / business_info 应是 null（"无从判断"）。
        # 注意 app_repository 有 post_save(Project) 信号「立项即开档案」，
        # 所以每个新项目都会自动带一个空档案——要构造这个状态必须显式删掉它。
        self.p_norepo = Project.objects.create(
            code="PN", name="无档案项目", manager=self.alice,
        )
        ProjectRepository.objects.filter(project=self.p_norepo).delete()

        # 物性链：一项有值，一项完全没有值
        self.metric_cat = MetricCategory.objects.create(name="力学", order=1)
        self.tc_valued = self._test_config("拉伸强度", "ISO 527", "NUMBER", "MPa", 1)
        self.tc_blank = self._test_config("阻燃测试", "UL94", "TEXT", "", 2)
        MaterialDataPoint.objects.create(
            material=self.mat_alice, test_config=self.tc_valued, value=Decimal("75.5"),
        )
        MaterialDataPoint.objects.create(material=self.mat_alice, test_config=self.tc_blank)

        # 配方里一条完全没有测量值的测试结果
        FormulaTestResult.objects.create(
            formula=self.f_alice, test_config=self.tc_blank, unique_key="mcp-test-blank",
        )

    def _test_config(self, name, standard, data_type, unit, order):
        return TestConfig.objects.create(
            category=self.metric_cat, name=name, standard=standard,
            data_type=data_type, unit=unit, order=order,
        )

    def _user(self, username, email, role, dept):
        user = User.objects.create_user(
            username=username, email=email, password="x", department=dept,
        )
        user.user_type = role
        user.save()
        return user

    def assertFailure(self, result, error_code):
        """失败信封的形状：ok=False + 错误码 + message/hint 都非空。"""
        self.assertIsInstance(result, dict)
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_code"], error_code)
        self.assertTrue(result["message"], result)
        self.assertTrue(result["hint"], result)
        self.assertNotIn("data", result)

class McpToolAccessTests(McpToolFixtureMixin, TestCase):
    # ---------- 准入：调用人自己的状态，如实告知 ----------

    def test_tool_claim_mismatch(self):
        ctx = fake_ctx(self.alice, "search_formulas")
        self.assertFailure(search_projects(ctx), "TOOL_NOT_ALLOWED")

    def test_api_key_skips_tool_claim(self):
        ctx = fake_ctx(self.alice, None)
        ctx.request_context.request.state.mcp_jwt = {"auth": "api_key"}
        result = search_projects(ctx)
        self.assertIs(result["ok"], True)
        self.assertIsInstance(result["data"], list)

    def test_tool_call_logs_arguments(self):
        ctx = fake_ctx(self.alice, "search_projects")
        ctx.request_context.params = {
            "name": "search_projects",
            "arguments": {"keyword": "比亚迪", "is_terminated": False},
        }
        with self.assertLogs("app_mcp_server.access", level="INFO") as cm:
            search_projects(ctx, keyword="比亚迪", is_terminated=False)
        self.assertTrue(
            any(
                'args={"is_terminated": false, "keyword": "比亚迪"}' in line
                for line in cm.output
            ),
            cm.output,
        )

    def test_stdio_no_state(self):
        self.assertFailure(search_projects(empty_ctx()), "NO_IDENTITY")

    def test_l1_role_denied(self):
        ctx = fake_ctx(self.dave, "search_projects")
        self.assertFailure(search_projects(ctx), "NO_MODULE_ACCESS")

    def test_l3_perm_denied(self):
        ctx = fake_ctx(self.noperm, "search_projects")
        self.assertFailure(search_projects(ctx), "NO_MODULE_ACCESS")

    # ---------- L4/L5 数据隔离 ----------

    def test_l4_hides_other_dept_projects(self):
        result = search_projects(fake_ctx(self.alice, "search_projects"))
        names = {item["name"] for item in result["data"]}
        self.assertIn("Alice项目", names)
        self.assertNotIn("Bob项目", names)
        self.assertIn("协同项目", names)
        self.assertIn("销售项目", names)

    def test_project_member_penetration(self):
        result = search_projects(fake_ctx(self.alice, "search_projects"), keyword="协同")
        self.assertEqual([item["name"] for item in result["data"]], ["协同项目"])

    def test_project_sales_member_penetration(self):
        result = search_projects(fake_ctx(self.alice, "search_projects"), keyword="销售")
        self.assertEqual([item["name"] for item in result["data"]], ["销售项目"])

    def test_superuser_sees_all(self):
        result = search_projects(fake_ctx(self.admin, "search_projects"))
        names = {item["name"] for item in result["data"]}
        self.assertGreaterEqual(len(names), 4)
        self.assertIn("Alice项目", names)
        self.assertIn("Bob项目", names)

    def test_formula_l4(self):
        result = search_formulas(fake_ctx(self.alice, "search_formulas"))
        codes = {item["code"] for item in result["data"]}
        self.assertIn("FA-001", codes)
        self.assertNotIn("FB-001", codes)

    def test_material_l4(self):
        result = search_material_library(fake_ctx(self.alice, "search_material_library"))
        grades = {item["grade_name"] for item in result["data"]}
        self.assertIn("PA66-A", grades)
        self.assertNotIn("PA66-B", grades)

    # ---------- 记录层面：区分「无权」与「不存在」 ----------

    def test_detail_distinguishes_no_permission_from_not_found(self):
        """存在但不可见 → NO_PERMISSION（并劝其别再试探）；确实不存在 → NOT_FOUND。"""
        hidden = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_bob.id,
        )
        self.assertFailure(hidden, "NO_PERMISSION")

        absent = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=999999,
        )
        self.assertFailure(absent, "NOT_FOUND")

    def test_formula_detail_no_permission_and_not_found(self):
        self.assertFailure(
            get_formula_detail(fake_ctx(self.alice, "get_formula_detail"), code="FB-001"),
            "NO_PERMISSION",
        )
        # 编号不存在
        self.assertFailure(
            get_formula_detail(fake_ctx(self.bob, "get_formula_detail"), code="NOPE-999"),
            "NOT_FOUND",
        )
        # 编号存在但版本不存在
        self.assertFailure(
            get_formula_detail(
                fake_ctx(self.bob, "get_formula_detail"), code="FB-001", version=99,
            ),
            "NOT_FOUND",
        )

    def test_member_can_get_project_details(self):
        data = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_member.id,
        )
        self.assertEqual(data["name"], "协同项目")
        self.assertNotIn("error_code", data)

    def test_formula_detail_versions(self):
        data = get_formula_detail(fake_ctx(self.bob, "get_formula_detail"), code="FB-001")
        self.assertEqual(data["version"], 2)
        data_v1 = get_formula_detail(
            fake_ctx(self.bob, "get_formula_detail"), code="FB-001", version=1,
        )
        self.assertEqual(data_v1["version"], 1)

    def test_missing_project_id_and_name(self):
        result = get_project_details(fake_ctx(self.alice, "get_project_details"))
        self.assertFailure(result, "INVALID_ARGUMENT")

    def test_material_and_formulas_dual_gate(self):
        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-A",
        )
        self.assertEqual(data["grade_name"], "PA66-A")
        self.assertEqual(len(data["associated_formulas_history"]), 1)
        self.assertNotIn("associated_formulas_note", data)

        # 牌号本身不可见 → 整体失败，且是 NO_PERMISSION 而非 NOT_FOUND
        self.assertFailure(
            get_material_and_formulas(
                fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-B",
            ),
            "NO_PERMISSION",
        )

    def test_material_visible_formulas_hidden(self):
        """材料可见但配方被 L4 隔离：保留材料数据，并明说列表为空是权限所致。"""
        material_open = ModuleAccessConfig.objects.get(module_code="material")
        material_open.enforce_dept_isolation = False
        material_open.save(update_fields=["enforce_dept_isolation"])
        IdentityService.invalidate_cache()

        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-B",
        )
        self.assertEqual(data["grade_name"], "PA66-B")
        self.assertEqual(data["associated_formulas_history"], [])
        self.assertTrue(data["associated_formulas_note"])

    def test_material_returned_when_only_formula_module_denied(self):
        """只有配方模块准入没过才降级；材料数据照常返回并给出说明。"""
        formula_cfg = ModuleAccessConfig.objects.get(module_code="formula")
        formula_cfg.role_groups.clear()
        IdentityService.invalidate_cache()

        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-A",
        )
        self.assertEqual(data["grade_name"], "PA66-A")
        self.assertEqual(data["associated_formulas_history"], [])
        self.assertTrue(data["associated_formulas_note"])

    # ---------- 零命中：成功但明确为空 ----------

    def test_empty_search_is_explicit_not_empty_value(self):
        cases = (
            (search_projects, fake_ctx(self.alice, "search_projects"), {"keyword": "绝无此项目"}),
            (search_formulas, fake_ctx(self.alice, "search_formulas"), {"keyword": "绝无此配方"}),
            (
                search_material_library,
                fake_ctx(self.alice, "search_material_library"),
                {"keyword": "绝无此牌号"},
            ),
        )
        for fn, ctx, kwargs in cases:
            with self.subTest(tool=fn.__name__):
                result = fn(ctx, **kwargs)
                self.assertIs(result["ok"], True)
                self.assertEqual(result["data"], [])
                self.assertEqual(result["total"], 0)
                self.assertTrue(result["hint"], "零命中必须说明是检索到 0 条")
                self.assertNotIn("error_code", result)

    def test_success_total_matches_data(self):
        result = search_projects(fake_ctx(self.alice, "search_projects"))
        self.assertEqual(result["total"], len(result["data"]))
        self.assertNotIn("hint", result)

    # ---------- 兜底 ----------

    def test_unexpected_error_becomes_internal_envelope(self):
        with patch(
            "app_mcp_server.tools.projects.serialize_project",
            side_effect=RuntimeError("boom"),
        ):
            result = search_projects(fake_ctx(self.alice, "search_projects"))
        self.assertFailure(result, "INTERNAL")

    def test_every_tool_is_wrapped_by_safe_tool(self):
        for fn in ALL_TOOLS:
            with self.subTest(tool=fn.__name__):
                self.assertTrue(
                    hasattr(fn, "__wrapped__"),
                    f"{fn.__name__} 漏了 @safe_tool，异常会逃到协议层",
                )

    def test_every_tool_description_documents_the_envelope(self):
        """description 是每个客户端都会展示的部分，必须告诉 agent 怎么读失败。"""
        for fn in ALL_TOOLS:
            with self.subTest(tool=fn.__name__):
                self.assertIn("error_code", fn.__doc__)

    # ---------- 结果上限 ----------

    def test_no_limit_returns_everything(self):
        result = search_projects(fake_ctx(self.alice, "search_projects"))
        self.assertGreater(len(result["data"]), 1)
        self.assertEqual(result["total"], len(result["data"]))
        self.assertEqual(result["returned"], len(result["data"]))
        self.assertIs(result["has_more"], False)
        self.assertNotIn("hint", result)

    def test_limit_truncates_and_reports_real_total(self):
        full = search_projects(fake_ctx(self.alice, "search_projects"))
        result = search_projects(fake_ctx(self.alice, "search_projects"), limit=1)

        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["returned"], 1)
        self.assertEqual(result["total"], len(full["data"]))  # 真实匹配总数
        self.assertIs(result["has_more"], True)
        self.assertTrue(result["hint"], "被截断时必须告诉 agent 还能怎么办")

    def test_limit_covers_all_search_tools(self):
        for fn, ctx, kwargs in (
            (search_projects, fake_ctx(self.alice, "search_projects"), {}),
            (search_formulas, fake_ctx(self.alice, "search_formulas"), {}),
            (search_material_library, fake_ctx(self.alice, "search_material_library"), {}),
        ):
            with self.subTest(tool=fn.__name__):
                result = fn(ctx, limit=1, **kwargs)
                self.assertIs(result["ok"], True)
                self.assertEqual(result["returned"], 1)

    def test_limit_below_one_is_invalid(self):
        for bad in (0, -5):
            with self.subTest(limit=bad):
                self.assertFailure(
                    search_projects(fake_ctx(self.alice, "search_projects"), limit=bad),
                    "INVALID_ARGUMENT",
                )

    # ---------- 空值约定 ----------

    def test_material_absent_attributes_are_null(self):
        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-A",
        )
        # 以前是 "Unknown" / "N/A"
        self.assertIsNone(data["manufacturer"])
        self.assertIsNone(data["flammability"])

        summary = data["properties_summary"]
        self.assertEqual(summary["拉伸强度 (ISO 527)"], "75.5 MPa")
        # 以前会写成字符串 "None"，agent 当真实测量值读
        self.assertIsNone(summary["阻燃测试 (UL94)"])

        blank_item = next(
            item for group in data["grouped_properties"]
            for item in group["items"] if item["name"] == "阻燃测试"
        )
        self.assertIsNone(blank_item["value"])
        self.assertIsNone(blank_item["unit"], "空 unit 以前是空串")

    def test_formula_test_result_without_value_is_null(self):
        data = get_formula_detail(fake_ctx(self.alice, "get_formula_detail"), code="FA-001")
        blank = next(r for r in data["test_results"] if r["item"] == "阻燃测试")
        self.assertIsNone(blank["value"])  # 以前是 "N/A"
        self.assertIsNone(blank["unit"])

    def test_project_without_repository_keeps_fields_as_null(self):
        data = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_norepo.id,
        )
        # 以前 business_info 整个字段被 pop 掉
        self.assertIn("business_info", data)
        self.assertIsNone(data["business_info"])
        # 无档案 = 无从判断，与"有档案没附件"（[]）区分
        self.assertIsNone(data["associated_files"])
        self.assertNotIn("warnings", data)

    def test_project_with_repository_and_no_files_is_empty_list(self):
        data = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_repo_no_files.id,
        )
        self.assertEqual(data["associated_files"], [])
        self.assertIsNotNone(data["business_info"])
        self.assertNotIn("warnings", data)

    def test_repository_target_cost_null_when_unset(self):
        """没设目标成本是 None，不是 0（0 是"目标成本为零"这个真实语义）。"""
        data = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_repo_no_files.id,
        )
        self.assertIsNone(data["business_info"]["target_cost"])
        self.assertIsNone(data["business_info"]["customer"])
        self.assertIsNone(data["business_info"]["target_material"])

    # ---------- 附件读取失败不再静默 ----------

    def test_material_attachment_failure_is_null_with_warning(self):
        with patch(
            "app_mcp_server.serializers.material.attachments_for",
            side_effect=RuntimeError("boom"),
        ):
            data = get_material_and_formulas(
                fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-A",
            )
        self.assertIsNone(data["files"])
        self.assertTrue(data["warnings"])

    def test_project_attachment_failure_is_null_with_warning(self):
        with patch(
            "app_mcp_server.serializers.project.attachments_for",
            side_effect=RuntimeError("boom"),
        ):
            data = get_project_details(
                fake_ctx(self.alice, "get_project_details"),
                project_id=self.p_repo_no_files.id,
            )
        self.assertIsNone(data["associated_files"])
        self.assertTrue(data["warnings"])

    # ---------- 配方被隐藏时给出计数而不是只有一句话 ----------

    def test_hidden_formulas_carry_structured_counts(self):
        material_open = ModuleAccessConfig.objects.get(module_code="material")
        material_open.enforce_dept_isolation = False
        material_open.save(update_fields=["enforce_dept_isolation"])
        IdentityService.invalidate_cache()

        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-B",
        )
        self.assertEqual(data["associated_formulas_total"], 2)  # FB-001 v1 + v2
        self.assertEqual(data["associated_formulas_hidden"], 2)
        self.assertEqual(data["associated_formulas_history"], [])
        self.assertTrue(data["associated_formulas_note"])


class McpWireShapeTests(McpToolFixtureMixin, TransactionTestCase):
    """走真实 mcp.call_tool 的形状断言。

    必须用 TransactionTestCase：同步工具在 anyio 工作线程里跑，用的是另一条 DB 连接，
    看不到 TestCase 未提交的事务数据。
    """

    def test_argument_validation_is_an_envelope_not_a_tool_error(self):
        """参数类型传错也要是结构化信封（SDK 默认会压成 is_error=true 的纯文本）。"""
        result = asyncio.run(mcp.call_tool("get_project_details", {"project_id": "abc"}))
        self.assertIs(result.is_error, False)
        envelope = result.structured_content["result"]
        self.assertIs(envelope["ok"], False)
        self.assertEqual(envelope["error_code"], "INVALID_ARGUMENT")
        self.assertIn("project_id", envelope["message"])

    def test_success_and_failure_wire_shape(self):
        """成功与失败都是 {"result": ...}，is_error 恒为 False。

        这是 agent 实际收到的东西；锁住它，避免 SDK 升级或注解改动悄悄改形状。
        """
        ok = asyncio.run(mcp.call_tool(
            "get_project_details", {"project_id": self.p_alice.id},
            fake_ctx(self.alice, "get_project_details"),
        ))
        self.assertIs(ok.is_error, False)
        self.assertEqual(ok.structured_content["result"]["name"], "Alice项目")
        self.assertNotIn("error_code", ok.structured_content["result"])

        denied = asyncio.run(mcp.call_tool(
            "get_project_details", {"project_id": self.p_bob.id},
            fake_ctx(self.alice, "get_project_details"),
        ))
        self.assertIs(denied.is_error, False)
        self.assertIs(denied.structured_content["result"]["ok"], False)
        self.assertEqual(
            denied.structured_content["result"]["error_code"], "NO_PERMISSION",
        )

    def test_empty_search_wire_shape(self):
        result = asyncio.run(mcp.call_tool(
            "search_projects", {"keyword": "绝无此项目"},
            fake_ctx(self.alice, "search_projects"),
        ))
        self.assertIs(result.is_error, False)
        payload = result.structured_content["result"]
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["total"], 0)
        self.assertTrue(payload["hint"])
