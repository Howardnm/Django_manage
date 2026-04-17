from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class RawMaterialAccessMixin(UnifiedAccessMixin):
    """
    原材料模块权限管控。
    
    1. 准入控制：技术核心 (TECH_CORE) + 供应链 (SUPPLY_CHAIN)。
    2. 资源性质：由于原材料库是全公司共用的基础资源，不设部门隔离（全员可见）。
    3. 维护权限：通过 Django 原生 perms 控制，采购专员通常拥有 change 权限。
    """
    
    # 允许技术核心（研发、工艺）和采购专员准入
    # 结合 IdentityConfig 中的逻辑分组，实现低代码扩展
    identity_required = IdentityConfig.TECH_CORE + [IdentityConfig.R_PURCHASING]
    
    # 原材料库通常是全公司共享的，关闭部门隔离
    enforce_dept_isolation = False
