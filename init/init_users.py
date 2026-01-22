import os
import django
import sys

# 初始化 Django 环境
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
django.setup()

from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from app_project.models import Project
from app_repository.models import MaterialLibrary, ProjectRepository
from app_process.models import ProcessProfile
from app_formula.models import LabFormula

def run():
    print("🚀 开始初始化用户、组和权限...")

    # 1. 创建用户组
    groups = {
        '项目经理': '项目经理，拥有项目管理和查看所有资料的权限',
        '研发工程师': '研发工程师，负责配方、工艺和材料库',
        '销售人员': '销售人员，查看项目进度和客户信息',
        '管理层': '管理层，查看所有数据报表',
    }

    created_groups = {}
    for name, desc in groups.items():
        group, created = Group.objects.get_or_create(name=name)
        created_groups[name] = group
        if created:
            print(f"   + [新增组] {name}")
        else:
            print(f"   . [已存在] {name}")

    # 2. 分配权限给组 (示例)
    # 获取 ContentType
    ct_project = ContentType.objects.get_for_model(Project)
    ct_material = ContentType.objects.get_for_model(MaterialLibrary)
    ct_formula = ContentType.objects.get_for_model(LabFormula)
    ct_process = ContentType.objects.get_for_model(ProcessProfile)

    # 定义权限列表
    perms = {
        '项目经理': [
            'add_project', 'change_project', 'view_project',
            'view_materiallibrary', 'view_projectrepository',
        ],
        '研发工程师': [
            'add_labformula', 'change_labformula', 'view_labformula',
            'add_processprofile', 'change_processprofile', 'view_processprofile',
            'add_materiallibrary', 'change_materiallibrary', 'view_materiallibrary',
            'view_project', # 研发通常只能看项目
        ],
        '销售人员': [
            'view_project', 'view_materiallibrary',
        ],
        '管理层': [
            # 管理层通常拥有所有查看权限，这里简化处理
            'view_project', 'view_labformula', 'view_processprofile', 'view_materiallibrary'
        ]
    }

    print("\n🔹 正在分配权限...")
    for group_name, perm_codes in perms.items():
        group = created_groups[group_name]
        for codename in perm_codes:
            try:
                # 尝试从所有 app 中查找权限 (简化逻辑，实际可能需要指定 app_label)
                # 这里我们假设 codename 是唯一的或者我们只关心主要 app 的
                perm = Permission.objects.filter(codename=codename).first()
                if perm:
                    group.permissions.add(perm)
                    # print(f"     -> {group_name} + {codename}")
            except Exception as e:
                print(f"     ! 权限 {codename} 添加失败: {e}")

    # 3. 创建初始用户
    users = [
        # (用户名, 邮箱, 密码, 组名, 真实姓名)
        ('admin_pm', 'pm@example.com', '123456', '项目经理', '张经理'),
        ('user_rd', 'rd@example.com', '123456', '研发工程师', '李工'),
        ('user_sales', 'sales@example.com', '123456', '销售人员', '王销售'),
        ('user_boss', 'boss@example.com', '123456', '管理层', '赵总'),
    ]

    print("\n🔹 正在初始化用户...")
    
    # 3.1 创建超级管理员
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@example.com', '123456')
        print(f"   + [新增超级管理员] admin")
    else:
        print(f"   . [已存在] admin")

    # 3.2 创建普通用户
    for username, email, password, group_name, first_name in users:
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(username=username, email=email, password=password)
            user.first_name = first_name
            user.save()
            
            # 添加到组
            if group_name in created_groups:
                created_groups[group_name].user_set.add(user)
            
            print(f"   + [新增用户] {username} ({first_name}) -> {group_name}")
        else:
            print(f"   . [已存在] {username}")

    print("\n✅ 用户初始化完成！")

if __name__ == '__main__':
    run()