"""
清理 upload_files/ 里没有 Attachment 记录的文件。

只走附件目录。oem/logos/、customer/logos/ 虽然用同一个默认 storage，
但是并列目录，这里不会列出也不会删除。
"""
import logging
import os
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

UPLOAD_ROOT = 'upload_files'
# 先写盘再 INSERT。这段时间内无记录的文件可能还在提交，只展示不删。
ORPHAN_GRACE = timedelta(minutes=10)


def _storage():
    from .models import Attachment
    return Attachment._meta.get_field('file').storage


def _normalize(name):
    return (name or '').replace('\\', '/').lstrip('/')


def _is_inside_upload_root(name):
    parts = [part for part in name.split('/') if part not in ('', '.')]
    return len(parts) >= 2 and parts[0] == UPLOAD_ROOT and '..' not in parts


def _referenced_names():
    """含软删除。那些行还占着文件，等真删除时才由 post_delete 清掉。"""
    from .models import Attachment
    return {
        _normalize(name)
        for name in Attachment.objects.values_list('file', flat=True)
        if name
    }


def _walk(storage, prefix):
    try:
        directories, files = storage.listdir(prefix)
    except OSError:
        return
    for filename in files:
        yield f'{prefix}/{filename}'
    for directory in directories:
        if directory in ('', '.', '..'):
            continue
        yield from _walk(storage, f'{prefix}/{directory}')


def _aware(moment):
    if timezone.is_naive(moment):
        return timezone.make_aware(moment, timezone.get_current_timezone())
    return moment


def scan_orphan_files(now=None):
    """
    返回 (deletable, recent)。

    deletable：可删的孤儿。recent：未满宽限，只展示。
    每项是 name / size / modified。
    """
    storage = _storage()
    now = now or timezone.now()
    referenced = _referenced_names()
    deletable = []
    recent = []
    for name in _walk(storage, UPLOAD_ROOT):
        name = _normalize(name)
        if not _is_inside_upload_root(name) or name in referenced:
            continue
        try:
            modified = _aware(storage.get_modified_time(name))
            size = storage.size(name)
        except OSError:
            logger.warning('读取孤儿文件信息失败: %s', name, exc_info=True)
            continue
        item = {'name': name, 'size': size, 'modified': modified}
        if now - modified < ORPHAN_GRACE:
            recent.append(item)
        else:
            deletable.append(item)
    deletable.sort(key=lambda item: item['name'])
    recent.sort(key=lambda item: item['name'])
    return deletable, recent


def _remove_empty_dirs(storage):
    """删掉 upload_files 里面的空目录，保留 upload_files 本身。"""
    try:
        root = storage.path(UPLOAD_ROOT)
    except Exception:
        logger.warning('无法定位附件目录', exc_info=True)
        return 0
    if not os.path.isdir(root):
        return 0
    removed = 0
    root_abs = os.path.abspath(root)
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        if os.path.abspath(dirpath) == root_abs:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
                removed += 1
        except OSError:
            logger.warning('删除空目录失败: %s', dirpath, exc_info=True)
    return removed


def delete_orphan_files():
    """重新扫描，只删除超过宽限的孤儿。不使用调用方传入的路径。"""
    storage = _storage()
    deletable, recent = scan_orphan_files()
    deleted = 0
    failed = 0
    for item in deletable:
        name = item['name']
        if not _is_inside_upload_root(name):
            continue
        try:
            storage.delete(name)
        except Exception:
            logger.warning('删除孤儿文件失败: %s', name, exc_info=True)
            failed += 1
            continue
        deleted += 1
    return {
        'deleted': deleted,
        'failed': failed,
        'skipped_recent': len(recent),
        'removed_dirs': _remove_empty_dirs(storage),
    }
