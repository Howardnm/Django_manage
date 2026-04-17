from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class ProcessAccessMixin(UnifiedAccessMixin):
    """
    工艺模块权限管控。
    
    1. 负责人识别：仅识别 creator。
    2. 准入控制：仅限技术核心 (TECH_CORE)，包含研发工程师、工艺工程师、管理员。
    3. 部门隔离：启用，具体的方案包为部门私有。
    """
    
    # 明确负责人字段
    user_link_fields = ['creator']
    
    # 允许技术核心全员准入
    identity_required = IdentityConfig.TECH_CORE
    
    enforce_dept_isolation = True
