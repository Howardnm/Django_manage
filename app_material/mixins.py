from app_user.mixins import UnifiedAccessMixin, IdentityConfig

class MaterialAccessMixin(UnifiedAccessMixin):
    """
    材料库模块权限管控。
    
    特点：
    1. 准入控制：内部全员 (INTERNAL_STAFF) 均可查看。
    2. 资源性质：材料库是公司的核心资产和共享资源，默认不设部门隔离（全员可见）。
    3. 维护权限：通常仅限技术人员 (TECH_CORE) 进行增删改操作。
    """
    
    # 默认允许内部全员准入 (研发、工艺、销售、采购、管理)
    identity_required = IdentityConfig.INTERNAL_STAFF
    
    # 材料库为共享资源，关闭部门隔离
    enforce_dept_isolation = False
