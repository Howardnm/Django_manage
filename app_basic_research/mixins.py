from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class BasicResearchAccessMixin(UnifiedAccessMixin):
    """
    预研项目模块权限管控。
    
    1. 负责人识别：manager。
    2. 准入控制：仅限技术研发人员 (RND_ONLY)，包含研发工程师和管理员。
    3. 部门隔离：启用，跨部门不可见。
    """
    
    # 明确负责人字段
    user_link_fields = ['manager']
    
    # 使用对象化分组：锁定为纯研发核心 (通常工艺工程师和销售不参与预研)
    identity_required = IdentityConfig.RND_ONLY
    
    # 启用严格的部门隔离
    enforce_dept_isolation = True
