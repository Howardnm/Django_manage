"""
app_catalog 伪数据生成器

业务逻辑：
  - CatalogCategory：手动分类，镜像 MaterialType
  - MirrorScenario / MirrorCharacteristic：从主系统（种子数据）镜像
  - CatalogProduct：镜像 MaterialLibrary（is_published=True 的材料对客户可见）
  - CatalogMember：外部客户和 OEM 成员的访问授权
"""

import random
from django.db import transaction
from django.contrib.auth import get_user_model
from ._base import FakeContext, pick_one, pick, COUNT_CATALOG_PRODUCTS

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[12/13] Creating catalog data...")

    from app_catalog.models.catalog import (
        CatalogCategory, MirrorScenario, MirrorCharacteristic, CatalogProduct,
    )
    from app_catalog.models.member import CatalogMember

    # --- CatalogCategory ---
    cat_categories = []
    for mt in ctx.material_types[:8]:
        obj, _ = CatalogCategory.objects.get_or_create(
            name=mt.name, defaults={'order': mt.id, 'icon': 'package'},
        )
        cat_categories.append(obj)

    # --- MirrorScenario ---
    mirror_scenarios = []
    for s in ctx.scenarios:
        obj, _ = MirrorScenario.objects.get_or_create(
            name=s.name, defaults={'remote_id': s.id},
        )
        mirror_scenarios.append(obj)

    # --- MirrorCharacteristic ---
    mirror_chars = []
    for c in ctx.characteristics[:6]:
        obj, _ = MirrorCharacteristic.objects.get_or_create(
            name=c.name, defaults={'remote_id': c.id},
        )
        mirror_chars.append(obj)

    # --- CatalogProduct ---
    for i in range(min(COUNT_CATALOG_PRODUCTS, len(ctx.materials))):
        m = ctx.materials[i]
        obj, _ = CatalogProduct.objects.get_or_create(
            remote_material_id=m.id,
            defaults={
                'display_name': m.grade_name,
                'category': pick_one(cat_categories),
                'is_published': m.is_published,
                'is_featured': i < 4,
                'view_count': random.randint(10, 500),
                'download_count': random.randint(0, 50),
            },
        )
        if obj.scenarios.count() == 0:
            obj.scenarios.set(pick(mirror_scenarios, random.randint(1, 3)))
        if obj.characteristics.count() == 0:
            obj.characteristics.set(pick(mirror_chars, random.randint(1, 3)))

    # --- CatalogMember ---
    member_count = 0
    for cu in User.objects.filter(user_type='CUSTOMER')[:3]:
        _, created = CatalogMember.objects.get_or_create(
            remote_member_token=str(cu.member_token),
            defaults={'display_name': cu.first_name, 'role': 'CUSTOMER'},
        )
        if created:
            member_count += 1
    for ou in User.objects.filter(user_type='OEM')[:3]:
        _, created = CatalogMember.objects.get_or_create(
            remote_member_token=str(ou.member_token),
            defaults={'display_name': ou.first_name, 'role': 'OEM'},
        )
        if created:
            member_count += 1

    print(f"  catalog_categories={len(cat_categories)}, "
          f"products={min(COUNT_CATALOG_PRODUCTS, len(ctx.materials))}, "
          f"members={member_count}")
