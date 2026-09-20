"""MCP 工具：tool claim + L1~L5 过滤。"""
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from mcp.server.mcpserver.exceptions import ToolError

from app_formula.models import LabFormula
from app_material.models import MaterialLibrary, MaterialType
from app_mcp_server.tools.formulas import get_formula_detail, search_formulas
from app_mcp_server.tools.materials import get_material_and_formulas, search_material_library
from app_mcp_server.tools.projects import get_project_details, search_projects
from app_project.models import Project, ProjectMember, ProjectSalesMember
from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()


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


class McpToolAccessTests(TestCase):
    def setUp(self):
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

    def _user(self, username, email, role, dept):
        user = User.objects.create_user(
            username=username, email=email, password="x", department=dept,
        )
        user.user_type = role
        user.save()
        return user

    def test_tool_claim_mismatch(self):
        ctx = fake_ctx(self.alice, "search_formulas")
        with self.assertRaises(ToolError) as cm:
            search_projects(ctx)
        self.assertIn("无权调用该工具", str(cm.exception))

    def test_api_key_skips_tool_claim(self):
        ctx = fake_ctx(self.alice, None)
        ctx.request_context.request.state.mcp_jwt = {"auth": "api_key"}
        results = search_projects(ctx)
        self.assertIsInstance(results, list)

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
        with self.assertRaises(ToolError) as cm:
            search_projects(empty_ctx())
        self.assertIn("此通道未启用身份认证", str(cm.exception))

    def test_l1_role_denied(self):
        ctx = fake_ctx(self.dave, "search_projects")
        with self.assertRaises(ToolError) as cm:
            search_projects(ctx)
        self.assertIn("无权访问", str(cm.exception))

    def test_l3_perm_denied(self):
        ctx = fake_ctx(self.noperm, "search_projects")
        with self.assertRaises(ToolError) as cm:
            search_projects(ctx)
        self.assertIn("无权访问", str(cm.exception))

    def test_l4_hides_other_dept_projects(self):
        results = search_projects(fake_ctx(self.alice, "search_projects"))
        names = {item["name"] for item in results}
        self.assertIn("Alice项目", names)
        self.assertNotIn("Bob项目", names)
        self.assertIn("协同项目", names)
        self.assertIn("销售项目", names)

    def test_project_member_penetration(self):
        results = search_projects(fake_ctx(self.alice, "search_projects"), keyword="协同")
        self.assertEqual([item["name"] for item in results], ["协同项目"])

    def test_project_sales_member_penetration(self):
        results = search_projects(fake_ctx(self.alice, "search_projects"), keyword="销售")
        self.assertEqual([item["name"] for item in results], ["销售项目"])

    def test_detail_does_not_leak_existence(self):
        with self.assertRaises(ToolError) as cm:
            get_project_details(
                fake_ctx(self.alice, "get_project_details"), project_id=self.p_bob.id,
            )
        self.assertEqual(str(cm.exception), "未找到或无权访问")

        with self.assertRaises(ToolError) as cm:
            get_project_details(
                fake_ctx(self.alice, "get_project_details"), project_id=999999,
            )
        self.assertEqual(str(cm.exception), "未找到或无权访问")

    def test_member_can_get_project_details(self):
        data = get_project_details(
            fake_ctx(self.alice, "get_project_details"), project_id=self.p_member.id,
        )
        self.assertEqual(data["name"], "协同项目")

    def test_superuser_sees_all(self):
        results = search_projects(fake_ctx(self.admin, "search_projects"))
        names = {item["name"] for item in results}
        self.assertGreaterEqual(len(names), 4)
        self.assertIn("Alice项目", names)
        self.assertIn("Bob项目", names)

    def test_formula_l4(self):
        results = search_formulas(fake_ctx(self.alice, "search_formulas"))
        codes = {item["code"] for item in results}
        self.assertIn("FA-001", codes)
        self.assertNotIn("FB-001", codes)

    def test_formula_detail_denied_same_message(self):
        with self.assertRaises(ToolError) as cm:
            get_formula_detail(fake_ctx(self.alice, "get_formula_detail"), code="FB-001")
        self.assertEqual(str(cm.exception), "未找到或无权访问")

        data = get_formula_detail(fake_ctx(self.bob, "get_formula_detail"), code="FB-001")
        self.assertEqual(data["version"], 2)
        data_v1 = get_formula_detail(
            fake_ctx(self.bob, "get_formula_detail"), code="FB-001", version=1,
        )
        self.assertEqual(data_v1["version"], 1)

    def test_material_l4(self):
        results = search_material_library(fake_ctx(self.alice, "search_material_library"))
        grades = {item["grade_name"] for item in results}
        self.assertIn("PA66-A", grades)
        self.assertNotIn("PA66-B", grades)

    def test_material_and_formulas_dual_gate(self):
        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-A",
        )
        self.assertEqual(data["grade_name"], "PA66-A")
        self.assertEqual(len(data["associated_formulas_history"]), 1)

        with self.assertRaises(ToolError):
            get_material_and_formulas(
                fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-B",
            )

    def test_material_visible_formulas_hidden(self):
        material_open = ModuleAccessConfig.objects.get(module_code="material")
        material_open.enforce_dept_isolation = False
        material_open.save(update_fields=["enforce_dept_isolation"])
        IdentityService.invalidate_cache()

        data = get_material_and_formulas(
            fake_ctx(self.alice, "get_material_and_formulas"), grade_name="PA66-B",
        )
        self.assertEqual(data["grade_name"], "PA66-B")
        self.assertEqual(data["associated_formulas_history"], [])

    def test_missing_project_id_and_name(self):
        with self.assertRaises(ToolError) as cm:
            get_project_details(fake_ctx(self.alice, "get_project_details"))
        self.assertIn("project_id", str(cm.exception))
