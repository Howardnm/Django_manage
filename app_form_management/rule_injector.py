"""
规则注入器：遍历 form-create 规则数组，为所有 type='upload' 的规则注入
上传配置（action、headers、data、onSuccess、beforeRemove）。

处理嵌套容器内的规则：group、subForm、table、tabs、collapse、row、
col、card、tabPane、collapseItem、tableForm、tableFormColumn。
"""
import copy
from typing import Any, Dict, List, Optional


def inject_upload_config(
    rules: List[Dict[str, Any]],
    submission_id: Optional[int],
    csrf_token: str,
    is_editable: bool = True,
) -> List[Dict[str, Any]]:
    """
    深拷贝规则列表，递归查找所有上传规则并注入配置。

    Args:
        rules: FormTemplate.form_config 的 JSON 数组。
        submission_id: FormSubmission 的主键（上传 API 的上下文）。
        csrf_token: Django CSRF token，用于 XHR 认证。
        is_editable: False 时上传字段设 disabled=True 且不注入 beforeRemove。

    Returns:
        注入上传配置后的新规则列表（不影响原数据）。
    """
    rules = copy.deepcopy(rules)
    _inject_recursive(rules, submission_id, csrf_token, is_editable)
    return rules


def _inject_recursive(
    rules: List[Dict[str, Any]],
    submission_id: Optional[int],
    csrf_token: str,
    is_editable: bool,
) -> None:
    """递归遍历规则树，为每个上传规则注入配置。"""
    for rule in rules:
        if not isinstance(rule, dict):
            continue

        if rule.get('type') == 'upload':
            _configure_upload_rule(rule, submission_id, csrf_token, is_editable)

        # 递归进入普通子规则
        children = rule.get('children')
        if isinstance(children, list):
            _inject_recursive(children, submission_id, csrf_token, is_editable)

        # 递归进入布局容器（group、subForm、table 等的子规则存在 control 中）
        control = rule.get('control')
        if isinstance(control, list):
            _inject_recursive(control, submission_id, csrf_token, is_editable)


def _configure_upload_rule(
    rule: Dict[str, Any],
    submission_id: Optional[int],
    csrf_token: str,
    is_editable: bool,
) -> None:
    """替换单个上传规则中的上传相关 props。"""
    field_name = rule.get('field', '')
    props = rule.setdefault('props', {})

    # 基础配置（无论是否可编辑都注入）
    props['action'] = '/forms/api/upload/'
    props['withCredentials'] = True
    # 是否选取后立即上传：尊重设计器配置（默认 true）。
    # 设为 false 时，文件不会立即上传，需在提交前由前端 flushPendingUploads() 统一上传。
    props.setdefault('autoUpload', True)
    props['headers'] = {
        'X-CSRFToken': csrf_token,
        'X-Requested-With': 'XMLHttpRequest',
    }
    props['data'] = {
        'submission_id': str(submission_id) if submission_id else '',
        'field_name': field_name,
        'csrfmiddlewaretoken': csrf_token,
    }

    # onChange: 记录该字段当前的文件列表（含未上传的原始文件），
    # 供提交时 flushPendingUploads() 检测并上传"选择了但未上传"的文件。
    # Element Plus on-change 回调签名 (uploadFile, uploadFiles)，
    # $inject.args[1] 为完整文件列表。
    props['onChange'] = (
        '$FNX:var files = $inject.args[1];\n'
        'window.__fcPendingUploads__ = window.__fcPendingUploads__ || {};\n'
        f'window.__fcPendingUploads__["{field_name}"] = files;'
    )

    # onSuccess: 从服务端响应提取 url 和 name 存入文件对象
    # $FNX: form-create 将函数体包装为 function($inject){...}
    # $inject.args[0] = XHR 响应体, $inject.args[1] = ElUpload 文件对象
    # 必须设置 file.value: update() 中 v.value || v.url，
    # ElUpload 原生对象无 value 属性会退回 url 字符串，导致文件名丢失。
    props['onSuccess'] = (
        '$FNX:var res = $inject.args[0];\n'
        'var file = $inject.args[1];\n'
        'file.url = res.data.url;\n'
        'if (res.data.name) file.name = res.data.name;\n'
        'file.value = {url: file.url, name: file.name};'
    )

    # onError: 权限拒绝等错误时显示服务端返回的具体原因
    # $inject.args[0] = XHR 响应体（JSON 对象或错误信息）
    props['onError'] = (
        '$FNX:var res = $inject.args[0];\n'
        'var msg = (res && res.message) || "文件上传失败，请检查权限或文件格式";\n'
        'ElementPlus.ElMessage.error(msg);'
    )

    if is_editable:
        props['beforeRemove'] = _build_before_remove(csrf_token)
    else:
        props.setdefault('disabled', True)


def _build_before_remove(csrf_token: str) -> str:
    """构建 beforeRemove 钩子的 $FNX 函数字符串。

    CSRF token 在服务端渲染时注入，每次页面加载获取最新的 token。

    beforeRemove 接收 (uploadFile, uploadFiles)，通过 $inject.args 传入。
    必须返回 Promise：resolve(true) 移除文件，resolve(false) 保留文件。

    延迟上传（autoUpload=false）时，文件可能尚未上传到后端：
    此时文件对象有 raw 但无服务器下载 URL/token，直接本地移除即可，
    无需（也无法）调用后端删除端点，否则 token 为空会阻止删除。
    """
    return (
        # file = $inject.args[0], files = $inject.args[1]
        '$FNX:var file = $inject.args[0];\n'
        # 尚未上传的待上传文件：有 raw 且无服务器下载 URL → 直接本地移除
        'var isPending = !!(file && file.raw) && !(file.url'
        ' && file.url.indexOf("/attachment/download/") > -1);\n'
        'if (isPending) return true;\n'
        'var parts = (file.url || "").split("/").filter(function(p)'
        ' { return p !== ""; });\n'
        'var token = parts.length > 0 ? parts[parts.length - 1] : "";\n'
        'if (!token) return false;\n'
        f'return fetch("/forms/api/upload/delete/", {{\n'
        f'  method: "POST",\n'
        f'  headers: {{\n'
        f'    "Content-Type": "application/json",\n'
        f'    "X-CSRFToken": "{csrf_token}",\n'
        f'    "Accept": "application/json",\n'
        f'    "X-Requested-With": "XMLHttpRequest"\n'
        f'  }},\n'
        f'  body: JSON.stringify({{token: token}})\n'
        f'}}).then(function(r) {{\n'
        f'  if (!r.ok) {{ return r.json().then(function(data)'
        f' {{ throw new Error(data.message || "删除失败，HTTP " + r.status); }}); }}\n'
        f'  return r.json();\n'
        f'}}).then(function(data) {{\n'
        f'  if (data.status === "success") return true;\n'
        f'  throw new Error(data.message || "删除失败");\n'
        f'}}).catch(function(e) {{\n'
        f'  ElementPlus.ElMessage.error(e.message || "删除失败");\n'
        f'  return false;\n'
        f'}});'
    )


def _collect_upload_field_names(
    rules: List[Dict[str, Any]],
) -> set:
    """递归收集所有 type='upload' 规则的字段名。"""
    fields = set()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if rule.get('type') == 'upload' and rule.get('field'):
            fields.add(rule['field'])
        for key in ('children', 'control'):
            children = rule.get(key)
            if isinstance(children, list):
                fields.update(_collect_upload_field_names(children))
    return fields


def enrich_upload_form_data(
    form_data: Dict[str, Any],
    rules: List[Dict[str, Any]],
    submission_obj,
) -> Dict[str, Any]:
    """
    将上传字段的值从纯 URL 字符串转为 {url, name} 对象，
    使 form-create 的 parseFile() 能正确保留文件名。

    不调用此函数时，getFileName(url) 提取 URL 末尾段作为文件名，
    对于 /attachment/download/<uuid>/ 会得到空字符串。
    """
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from app_attachment.models import Attachment

    upload_fields = _collect_upload_field_names(rules)
    if not upload_fields:
        return form_data

    # 从 Attachment 记录构建 url → display_name 映射
    ct = ContentType.objects.get_for_model(type(submission_obj))
    attachments = Attachment.objects.filter(
        content_type=ct,
        object_id=submission_obj.pk,
        is_deleted=False,
    )

    url_name_map = {}
    for att in attachments:
        url = reverse('attachment:download', kwargs={'token': str(att.download_token)})
        url_name_map[url] = att.display_name or att.filename

    # 将字符串 URL 转为 {url, name} 对象
    result = dict(form_data)
    for field_name in upload_fields:
        value = result.get(field_name)
        if not value:
            continue

        if isinstance(value, list):
            result[field_name] = [
                _normalize_upload_value(v, url_name_map) for v in value
            ]
        else:
            result[field_name] = _normalize_upload_value(value, url_name_map)

    return result


def _normalize_upload_value(value, url_name_map):
    """将单个上传字段值转换为 {url, name} 格式。

    确保每个值都有 'url' 和有意义的 'name'：
    - 字符串 URL → {url, name} 对象（name 从 Attachment 查找）
    - 对象但 name 缺失/为空 → 从 Attachment 查找补全 name
    - 对象且 name 有效 → 原样透传
    """
    if isinstance(value, dict) and 'url' in value:
        # name 为空时尝试从 Attachment 查找补全
        if not value.get('name'):
            looked_up = url_name_map.get(value['url'], '')
            if looked_up:
                value = dict(value)
                value['name'] = looked_up
        return value
    if isinstance(value, str):
        name = url_name_map.get(value, '')
        return {'url': value, 'name': name}
    return value
