from app_user.mixins import UnifiedAccessMixin
from app_user.models import User

class FormulaAccessMixin(UnifiedAccessMixin):
    """
    实验配方模块权限管控。
    
    特点：
    1. 负责人识别：仅识别 creator 字段。
    2. 严格准入：仅限研发核心。
    3. 强部门隔离：不支持协同穿透，确保配方安全。
    """
    
    # 明确配方负责人的字段名为 creator
    user_link_fields = ['creator']
    
    # 默认准入角色
    identity_required = [User.UserType.ENGINEER, User.UserType.ADMIN]
    
    # 启用严格的部门隔离逻辑
    enforce_dept_isolation = True
