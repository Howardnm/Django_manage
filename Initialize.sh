# 请进入到本项目Python虚拟环境，然后运行此脚本进行数据库初始化。
# 1. 构建初始化数据表
python manage.py makemigrations
python manage.py migrate

# 2. 收集静态文件
python manage.py collectstatic
# nginx设置文件夹映射
# location /static/ {
#     alias /www/wwwroot/django_manage/staticfiles/;  # 静态文件绝对路径
#     expires 30d;  # 缓存静态文件
# }

# 3. 导入初始化数据
python ./init/init_configs.py
python ./init/init_materials_data.py
python ./init/init_oem_data.py
python ./init/init_raw_materials_data.py

# 4. 创建超级管理员（请根据终端指示，填入对应的信息）
python manage.py createsuperuser