"""
伪数据生成器 — 入口脚本

为 Django 项目生成有业务关联的伪数据，用于开发和测试。
依赖 Initialize.sh 通过 management commands 预置的基础数据。

用法: python init/generate_fake_data.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')
import django
django.setup()

if __name__ == '__main__':
    from init.fake import run_all
    run_all()
