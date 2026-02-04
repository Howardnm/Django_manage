import os
import re
import uuid

from django.utils import timezone


def upload_file_path(instance, filename):
    """
    文件路径生成器
    格式: upload_files/{模型名}/{ID}/{日期}/{短UUID}_{保留语义的原名}.ext
    特点: 保留了中文、括号、点号等常用符号，仅替换空格和危险字符
    """
    # 1. 拆分文件名和后缀
    base_name, ext = os.path.splitext(filename)

    # 2. 清洗文件名
    # 白名单策略：保留 [字母 数字 汉字 下划线] [横杠 -] [括号 ()] [方括号 []] [点 .] [加号 +] [等号 =]
    # 正则逻辑：[^...] 表示匹配“不在白名单里”的字符，全部替换为下划线
    clean_name = re.sub(r'[^\w\u4e00-\u9fa5\-\(\)\.]', '_', base_name)

    # 3. 美化处理
    # 将连续的下划线合并为一个 (例如 "Project   Name" -> "Project_Name")
    clean_name = re.sub(r'_+', '_', clean_name)
    # 去除两端的下划线和点 (防止 Windows 文件名报错)
    clean_name = clean_name.strip('_.')

    # 截取长度 (防止文件名过长)
    clean_name = clean_name[:60]

    # 4. 生成短 UUID (6位)
    short_uuid = uuid.uuid4().hex[:6]

    # 5. 组合最终文件名: "a1b2c3_测试项目(V1.0).pdf"
    new_filename = f"{clean_name}_{short_uuid}{ext}"

    # 6. 获取基本信息
    date_path = timezone.now().strftime("%Y-%m-%d")
    model_name = instance._meta.model_name

    # 7. 核心逻辑：只获取 ID 作为文件夹名
    folder_id = "common"

    # 情况 A: 项目文件 -> Project ID
    if hasattr(instance, 'repository') and instance.repository:
        folder_id = str(instance.repository.project.id)
    
    # 情况 B: 预研项目文件 -> ResearchProject ID
    elif hasattr(instance, 'project') and instance.project:
        folder_id = str(instance.project.id)

    # 情况 C: 材料库 -> Material ID
    elif hasattr(instance, 'grade_name'):
        folder_id = str(instance.id) if instance.id else 'temp_new'

    # 情况 D: 材料附件 -> Material ID
    elif hasattr(instance, 'material'):
        folder_id = str(instance.material.id)

    # 情况 E: 主机厂标准文件 -> OEM ID
    elif hasattr(instance, 'oem'):
        folder_id = str(instance.oem.id)

    # 情况 F: 实验配方测试结果 -> LabFormula ID
    elif hasattr(instance, 'formula'):
        folder_id = str(instance.formula.id)

    # 情况 G: 螺杆组合 -> ScrewCombination ID
    elif hasattr(instance, 'combination_code'):
        folder_id = str(instance.id) if instance.id else 'temp_new'
        
    # 情况 H: 原材料 -> RawMaterial ID
    elif hasattr(instance, 'model_name') and hasattr(instance, 'warehouse_code'):
        folder_id = str(instance.id) if instance.id else 'temp_new'

    # 8. 拼接完整路径
    return os.path.join('upload_files', model_name, folder_id, date_path, new_filename)
