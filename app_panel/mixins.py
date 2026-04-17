from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class PanelAccessMixin(UnifiedAccessMixin):
    """
    工作台看板模块权限管控。
    
    特点：
    1. 准入控制：内部全员 (INTERNAL_STAFF) 均可查看个人看板和统计数据。
    2. 资源性质：看板是综合性的统计展示，不设部门隔离，以便进行跨部门数据汇总。
    """
    
    # 默认允许内部全员准入 (研发、工艺、销售、采购、管理)
    identity_required = IdentityConfig.INTERNAL_STAFF
    
    # 看板通常涉及跨部门统计，关闭部门隔离以显示全局概况（如系统总材料数）
    # 如果后续需要“部门看板”，可在具体视图中手动开启
    enforce_dept_isolation = False
