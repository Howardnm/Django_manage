# 请进入到本项目Python虚拟环境，然后运行此脚本进行数据库初始化。
python manage.py makemigrations
python manage.py migrate
python init_configs.py
python init_materials_data.py
python init_oem_data.py
python init_raw_materials_data.py
python manage.py createsuperuser