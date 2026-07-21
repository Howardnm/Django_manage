from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class FormulaAccessMixin(UnifiedAccessMixin):
    """
    实验配方模块权限管控。

    特点：
    1. 负责人识别：仅识别 creator 字段。
    2. 严格准入：仅限研发核心 (RND_ONLY)。
    3. 强部门隔离：不支持协同穿透，确保配方安全。
    """

    # 明确配方负责人的字段名为 creator
    user_link_fields = ['creator']

    # L1: 仅研发工程师 + 管理员
    identity_required = IdentityConfig.RND_ONLY

    # L4: 启用严格的部门隔离逻辑
    enforce_dept_isolation = True

    # L5: 启用工作组隔离逻辑（同部门不同工作组之间数据不可见）
    enforce_group_isolation = True
