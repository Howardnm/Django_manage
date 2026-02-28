#!/bin/bash

# ==============================================================================
# Django 项目一键初始化脚本
# ==============================================================================
#
# 使用方法:
# 1. 确保您已进入项目的 Python 虚拟环境。
# 2. 确保数据库连接信息和 Dify 配置在 settings.py 中已正确填写。
# 3. 在项目根目录下运行此脚本: ./Initialize.sh
#
# ==============================================================================

# 函数：打印带有颜色的信息
print_info() {
    echo -e "\n\033[1;34m--- $1 ---\033[0m"
}

print_success() {
    echo -e "\033[1;32m✅ $1\033[0m"
}

print_warning() {
    echo -e "\033[1;33m⚠️ $1\033[0m"
}

print_error() {
    echo -e "\033[1;31m❌ $1\033[0m"
}

# --- 步骤 1: 数据库迁移 ---
print_info "步骤 1/5: 正在执行数据库迁移..."
python manage.py makemigrations
python manage.py migrate

# 检查迁移是否成功
if [ $? -ne 0 ]; then
    echo -e "\033[1;31m❌ 数据库迁移失败，请检查错误信息并修复。脚本已中止。\033[0m"
    exit 1
fi
print_success "数据库迁移完成。"


# --- 步骤 2: 导入基础数据 ---
print_info "步骤 2/5: 正在导入基础数据..."
echo "  -> 正在导入供应商..."
python manage.py import_suppliers
echo "  -> 正在导入原材料类型..."
python manage.py import_raw_material_types
echo "  -> 正在导入主机厂(OEM)和应用场景..."
python manage.py import_base_data
python manage.py import_oems
echo "  -> 正在导入测试配置库..."
python manage.py import_configs
echo "  -> 正在导入原材料..."
python manage.py import_raw_materials
print_success "基础数据导入完成。"


# --- 步骤 3: Dify 知识库首次初始化 ---
print_info "步骤 3/5: 正在初始化 Dify 知识库..."
print_warning "此步骤将清空本地的 Dify 同步记录，然后为所有现有数据创建新的同步任务。"
read -p "这是一个一次性操作，您确定要继续吗？ (输入 'yes' 继续): " confirm
if [[ "$confirm" != "yes" ]]; then
    print_warning "操作已取消。跳过 Dify 初始化。"
else
    echo "  -> (1/3) 清理本地旧的同步记录..."
    python manage.py cleanup_dify_records --confirm
    
    echo "  -> (2/3) 引导创建新的同步任务..."
    python manage.py bootstrap_dify_sync_records
    
    echo "  -> (3/3) 首次执行同步..."
    python manage.py sync_to_dify
    
    print_success "Dify 知识库首次数据填充完成。"
fi


# --- 步骤 4: 收集静态文件 ---
print_info "步骤 4/5: 正在收集静态文件..."
python manage.py collectstatic --noinput

if [ $? -ne 0 ]; then
    print_warning "静态文件收集过程中出现问题，但这通常不影响开发环境的运行。"
else
    print_success "静态文件收集完成。"
fi
echo "  生产环境提示: 请确保您的 Web 服务器 (如 Nginx) 已正确配置静态文件目录映射。"
echo "  例如: location /static/ { alias /path/to/your/project/staticfiles/; }"


# --- 步骤 5: 创建超级管理员 ---
print_info "步骤 5/5: 创建超级管理员账户"
print_warning "接下来，请根据终端提示，输入您的管理员用户名、邮箱和密码。"
python manage.py createsuperuser


# --- 完成 ---
echo -e "\n\n=================================================="
print_success "🎉 项目初始化流程已全部完成！"
echo "您现在可以运行 'python manage.py runserver' 来启动开发服务器了。"
echo "=================================================="
