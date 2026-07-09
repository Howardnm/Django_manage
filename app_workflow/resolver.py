"""组织角色解析器。根据发起人的组织归属（工作组 → 部门 → 子公司）逐级查找对应角色的审批人。

导出: OrgRoleResolver。"""

import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()

# 回退链路：当前层级找不到时，按此顺序向上一级查找
ESCALATION_CHAIN = ['workgroup', 'department', 'subsidiary']


class OrgRoleResolver:
    """组织角色解析器。

    根据发起人 (initiator) 的组织归属，在 OrgRoleAssignment 表中
    查找指定角色的负责人。

    解析链路：
        1. 取发起人的工作归属: workgroup → department → subsidiary
        2. 根据 role.scope 锁定起始查找层级
        3. 在 OrgRoleAssignment 中查找该层级 + 该角色的指派
        4. 如果未找到且 role.allow_escalation=True，逐级向上回退
        5. 回退链路：工作组 → 部门 → 子公司（每个层级都会尝试）
        6. 全部未找到则返回 None

    使用示例:
        resolver = OrgRoleResolver(initiator=request.user)
        approver = resolver.resolve('group_leader')  # → User | None
    """

    def __init__(self, initiator):
        """初始化解析器。

        Args:
            initiator: 发起审批的用户实例 (User)。
        """
        self.initiator = initiator

    def resolve(self, role_code: str):
        """根据角色编码查找发起人对应的审批人。

        Args:
            role_code: 角色编码字符串，如 'group_leader'、'dept_manager'。

        Returns:
            匹配的 User 实例，未找到则返回 None。
        """
        from app_user.models import OrgRole

        role = OrgRole.objects.filter(code=role_code).first()
        if not role:
            logger.warning(
                f"OrgRoleResolver: role_code '{role_code}' not found in OrgRole table"
            )
            return None

        return self._resolve_with_escalation(role)

    def _resolve_with_escalation(self, role):
        """按 scope 起始层级查找，允许逐级向上回退。

        回退规则：
            — workgroup → department → subsidiary
            — department → subsidiary
            — subsidiary → 不再回退（已是最顶层）

        Args:
            role: OrgRole 实例。

        Returns:
            User | None
        """
        # 确定从哪个层级开始查找
        try:
            start_index = ESCALATION_CHAIN.index(role.scope)
        except ValueError:
            logger.warning(
                f"OrgRoleResolver: unknown scope '{role.scope}' for role '{role.code}'"
            )
            return None

        # 确定查找范围：允许回退时遍历后续所有层级，否则只查当前层级
        end_index = len(ESCALATION_CHAIN) if role.allow_escalation else start_index + 1

        scope_methods = {
            'workgroup': self._resolve_workgroup_role,
            'department': self._resolve_department_role,
            'subsidiary': self._resolve_subsidiary_role,
        }

        for i in range(start_index, end_index):
            scope = ESCALATION_CHAIN[i]
            is_escalated = i > start_index
            prefix = "escalated" if is_escalated else "primary"

            resolver = scope_methods[scope]
            result = resolver(role)

            if result:
                logger.info(
                    f"OrgRoleResolver: [{prefix}] resolved role '{role.code}' "
                    f"(scope={scope}, escalated={is_escalated}) "
                    f"for initiator '{self.initiator.username}' → '{result.username}'"
                )
                return result
            elif is_escalated:
                logger.info(
                    f"OrgRoleResolver: escalation: '{role.code}' not found at "
                    f"scope='{ESCALATION_CHAIN[i-1]}', trying next level '{scope}' "
                    f"for initiator '{self.initiator.username}'"
                )

        logger.info(
            f"OrgRoleResolver: no match for role '{role.code}' "
            f"(scope={role.scope}, escalation={'on' if role.allow_escalation else 'off'}) "
            f"for initiator '{self.initiator.username}'"
        )
        return None

    # ── 各层级解析方法 ──────────────────────────────────────────

    def _resolve_workgroup_role(self, role):
        """查找发起人所在工作组中 role 角色的负责人。

        遍历发起人的所有活跃工作组，返回第一个匹配的主负责人。
        """
        from app_user.models import OrgRoleAssignment

        wgs = self.initiator.work_groups.filter(is_active=True)
        for wg in wgs:
            assignment = OrgRoleAssignment.objects.filter(
                role=role, workgroup=wg, is_primary=True,
            ).select_related('user').first()
            if assignment:
                return assignment.user
        return None

    def _resolve_department_role(self, role):
        """查找发起人所在部门中 role 角色的负责人。"""
        from app_user.models import OrgRoleAssignment

        dept = self.initiator.department
        if not dept:
            return None
        assignment = OrgRoleAssignment.objects.filter(
            role=role, department=dept, is_primary=True,
        ).select_related('user').first()
        return assignment.user if assignment else None

    def _resolve_subsidiary_role(self, role):
        """查找发起人所在子公司中 role 角色的负责人。"""
        from app_user.models import OrgRoleAssignment

        sub = self.initiator.subsidiary
        if not sub:
            return None
        assignment = OrgRoleAssignment.objects.filter(
            role=role, subsidiary=sub, is_primary=True,
        ).select_related('user').first()
        return assignment.user if assignment else None
