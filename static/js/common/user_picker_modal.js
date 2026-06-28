/**
 * 人员选择器模态框 — includes/user_picker_modal.html
 *
 * 用法：
 *   1. 在页面中 include 'includes/user_picker_modal.html' with picker_id='myPicker'
 *      或由 JS 动态创建 overlay DOM（见 _ensureOverlay）
 *   2. 加载本 JS 文件（base.html 全局加载）
 *   3. 调用 openUserPicker('myPicker', callback, options)
 *
 * options:
 *   { multi: false, title: '选择人员' }
 *
 * 回调参数（单选）： { id, label }           ← 向后兼容
 * 回调参数（多选）： { users: [{id, label}, ...] }
 */

(function () {
    'use strict';

    // ── 实例状态存储（key = pickerId） ──
    var instances = {};

    function getInstance(id) {
        return instances[id] || null;
    }

    function htmlEscape(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ── 渲染树 ──
    function renderNode(node, depth, pickerId) {
        if (node.type === 'user') {
            var inst = getInstance(pickerId);
            var selectedIds = inst ? inst.selectedIds || [] : [];
            var isSelected = selectedIds.indexOf(String(node.id)) !== -1;

            return '<div class="tree-leaf' + (isSelected ? ' selected' : '') +
                '" data-id="' + node.id + '" data-label="' + htmlEscape(node.label) + '">'
                + htmlEscape(node.label) + '</div>';
        }
        var iconMap = { department: '&#127970;', reviewgroup: '&#128101;' };
        var icon = iconMap[node.type] || '&#128100;';
        var collapsed = node.collapsed !== false;

        return '<div class="tree-node">'
            + '<div class="tree-node-header">'
            + '<span class="tree-node-arrow' + (collapsed ? '' : ' expanded') + '">&#9654;</span>'
            + '<span class="tree-node-icon">' + icon + '</span>'
            + '<span class="tree-node-label">' + htmlEscape(node.label) + '</span>'
            + '</div>'
            + '<div class="tree-node-children' + (collapsed ? '' : ' open') + '">'
            + (node.children || []).map(function (c) { return renderNode(c, depth + 1, pickerId); }).join('')
            + '</div></div>';
    }

    function renderTree(id) {
        var inst = getInstance(id);
        if (!inst) return;

        var treeEl = document.getElementById('pickerTree_' + id);
        if (!treeEl) return;
        if (!inst.treeData || inst.treeData.length === 0) {
            treeEl.innerHTML = '<div class="user-picker-empty">无匹配人员</div>';
            return;
        }
        var html = '';
        inst.treeData.forEach(function (node) {
            html += renderNode(node, 0, id);
        });
        treeEl.innerHTML = html;
    }

    // ── 更新选中状态显示的 Footer 文本 ──
    function updateSelectedText(id) {
        var inst = getInstance(id);
        if (!inst) return;
        var el = document.getElementById('pickerSelected_' + id);
        if (!el) return;

        var count = (inst.selectedUsers || []).length;
        if (count === 0) {
            el.textContent = '';
        } else if (inst.multi) {
            el.textContent = '已选 ' + count + ' 人';
        } else {
            el.textContent = '已选: ' + inst.selectedUsers[0].label;
        }
    }

    // ── 加载树数据 ──
    async function loadTree(id, query) {
        var inst = getInstance(id);
        if (!inst) return;

        var treeEl = document.getElementById('pickerTree_' + id);
        if (!treeEl) return;
        treeEl.innerHTML = '<div class="user-picker-empty">加载中...</div>';
        try {
            var overlay = document.getElementById('pickerOverlay_' + id);
            var baseUrl = (overlay && overlay.dataset.apiUrl) ||
                (window.USER_PICKER_API_URL || '/common/api/user-tree/');
            var url = baseUrl + '?q=' + encodeURIComponent(query);
            var resp = await fetch(url);
            var data = await resp.json();
            inst.treeData = data.nodes || [];
            renderTree(id);
        } catch (e) {
            treeEl.innerHTML = '<div class="user-picker-empty">加载失败，请重试</div>';
        }
    }

    // ── 绑定事件到指定实例的 DOM ──
    function bindEvents(id) {
        var overlay = document.getElementById('pickerOverlay_' + id);
        if (!overlay) return;

        // 关闭按钮
        var closeBtn = overlay.querySelector('.user-picker-close');
        if (closeBtn && !closeBtn.dataset.bound) {
            closeBtn.dataset.bound = '1';
            closeBtn.addEventListener('click', function () {
                closeUserPicker(id);
            });
        }

        // 取消按钮
        var cancelBtn = overlay.querySelector('.user-picker-cancel-btn');
        if (cancelBtn && !cancelBtn.dataset.bound) {
            cancelBtn.dataset.bound = '1';
            cancelBtn.addEventListener('click', function () {
                closeUserPicker(id);
            });
        }

        // 确认按钮
        var confirmBtn = document.getElementById('pickerConfirm_' + id);
        if (confirmBtn && !confirmBtn.dataset.bound) {
            confirmBtn.dataset.bound = '1';
            confirmBtn.addEventListener('click', function () {
                confirmUserPicker(id);
            });
        }

        // 搜索输入
        var searchInput = document.getElementById('pickerSearch_' + id);
        if (searchInput && !searchInput.dataset.bound) {
            searchInput.dataset.bound = '1';
            searchInput.addEventListener('input', function () {
                filterUserTree(id);
            });
        }

        // 事件委托：树节点折叠/展开 & 用户叶子选择
        var treeEl = document.getElementById('pickerTree_' + id);
        if (treeEl && !treeEl.dataset.bound) {
            treeEl.dataset.bound = '1';
            treeEl.addEventListener('click', function (e) {
                // 树节点折叠/展开
                var header = e.target.closest('.tree-node-header');
                if (header) {
                    var arrow = header.querySelector('.tree-node-arrow');
                    var children = header.nextElementSibling;
                    if (children) {
                        var isOpen = children.classList.contains('open');
                        if (isOpen) {
                            children.classList.remove('open');
                            if (arrow) arrow.classList.remove('expanded');
                        } else {
                            children.classList.add('open');
                            if (arrow) arrow.classList.add('expanded');
                        }
                    }
                    return;
                }

                // 用户叶子选择
                var leaf = e.target.closest('.tree-leaf');
                if (leaf) {
                    var inst = getInstance(id);
                    if (!inst) return;

                    var userId = leaf.getAttribute('data-id');
                    var userLabel = leaf.getAttribute('data-label');

                    if (inst.multi) {
                        // ── 多选模式：toggle ──
                        var idx = inst.selectedIds.indexOf(userId);
                        if (idx !== -1) {
                            // 取消选择
                            inst.selectedIds.splice(idx, 1);
                            inst.selectedUsers = inst.selectedUsers.filter(function (u) { return u.id !== userId; });
                            leaf.classList.remove('selected');
                        } else {
                            // 添加选择
                            inst.selectedIds.push(userId);
                            inst.selectedUsers.push({ id: userId, label: userLabel });
                            leaf.classList.add('selected');
                        }
                    } else {
                        // ── 单选模式：替换 ──
                        treeEl.querySelectorAll('.tree-leaf').forEach(function (el) {
                            el.classList.remove('selected');
                        });
                        leaf.classList.add('selected');
                        inst.selectedIds = [userId];
                        inst.selectedUsers = [{ id: userId, label: userLabel }];
                    }

                    updateSelectedText(id);

                    var confirmBtn2 = document.getElementById('pickerConfirm_' + id);
                    if (confirmBtn2) {
                        confirmBtn2.disabled = inst.selectedUsers.length === 0;
                    }
                }
            });
        }
    }

    // ── 初始化实例 ──
    function initInstance(id, options) {
        options = options || {};
        if (instances[id]) {
            // 已存在实例时更新 multi 选项
            instances[id].multi = !!options.multi;
            return;
        }
        instances[id] = {
            selectedUsers: [],
            selectedIds: [],
            callback: null,
            treeData: [],
            multi: !!options.multi
        };
        bindEvents(id);
    }

    // ── 动态创建 overlay DOM ──
    function ensureOverlay(id, options) {
        options = options || {};
        var existing = document.getElementById('pickerOverlay_' + id);
        if (existing) return;

        var title = options.title || '选择人员';
        var apiUrl = options.apiUrl || window.USER_PICKER_API_URL || '/common/api/user-tree/';
        var html = '<div class="user-picker-overlay" id="pickerOverlay_' + id + '" data-api-url="' + apiUrl + '">'
            + '<div class="user-picker-dialog">'
            + '<div class="user-picker-header">'
            + '<span>' + htmlEscape(title) + '</span>'
            + '<span class="user-picker-close">&times;</span>'
            + '</div>'
            + '<div class="user-picker-body">'
            + '<input type="text" class="user-picker-search" id="pickerSearch_' + id + '" placeholder="搜索姓名或用户名...">'
            + '<div class="user-picker-tree" id="pickerTree_' + id + '">'
            + '<div class="user-picker-empty">加载中...</div>'
            + '</div>'
            + '</div>'
            + '<div class="user-picker-footer">'
            + '<span id="pickerSelected_' + id + '" class="user-picker-selected-text"></span>'
            + '<button class="user-picker-cancel-btn" type="button">取消</button>'
            + '<button id="pickerConfirm_' + id + '" class="user-picker-confirm-btn" type="button" disabled>确认</button>'
            + '</div>'
            + '</div>'
            + '</div>';

        var wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        document.body.appendChild(wrapper.firstElementChild);
    }

    // 导出供 search_picker_modal.js 等外部调用
    window.ensureUserPickerOverlay = ensureOverlay;

    function removeOverlay(id) {
        var overlay = document.getElementById('pickerOverlay_' + id);
        if (overlay && overlay.dataset.dynamic === '1') {
            overlay.remove();
        }
    }

    // ── Public API ──

    /**
     * 打开人员选择器
     * @param {string}   id       picker 唯一标识
     * @param {function} cb       选中后的回调
     * @param {object}   options  { multi: false, title: '选择人员', dynamic: false }
     *
     * 单选回调参数： { id, label }              ← 向后兼容
     * 多选回调参数： { users: [{id, label}, ...] }
     */
    window.openUserPicker = function (id, cb, options) {
        options = options || {};

        // 动态创建 overlay（如果不存在）
        if (options.dynamic) {
            ensureOverlay(id, options);
            var overlay = document.getElementById('pickerOverlay_' + id);
            if (overlay) overlay.dataset.dynamic = '1';
        }

        initInstance(id, options);
        var inst = getInstance(id);
        if (!inst) return;

        inst.callback = cb;
        inst.selectedUsers = [];
        inst.selectedIds = [];
        inst.multi = !!options.multi;
        inst.treeData = [];

        // 更新标题
        if (options.title) {
            var headerSpan = document.querySelector('#pickerOverlay_' + id + ' .user-picker-header span:first-child');
            if (headerSpan) headerSpan.textContent = options.title;
        }

        overlay = document.getElementById('pickerOverlay_' + id);
        if (overlay) overlay.classList.add('show');

        var searchInput = document.getElementById('pickerSearch_' + id);
        if (searchInput) searchInput.value = '';

        var confirmBtn = document.getElementById('pickerConfirm_' + id);
        if (confirmBtn) confirmBtn.disabled = true;

        updateSelectedText(id);

        loadTree(id, '');
    };

    window.closeUserPicker = function (id) {
        var overlay = document.getElementById('pickerOverlay_' + id);
        if (overlay) overlay.classList.remove('show');
    };

    window.confirmUserPicker = function (id) {
        var inst = getInstance(id);
        if (!inst || inst.selectedUsers.length === 0) return;
        if (inst.callback) {
            if (inst.multi) {
                inst.callback({ users: inst.selectedUsers.slice() });
            } else {
                // 向后兼容：单选返回 { id, label }
                var u = inst.selectedUsers[0];
                inst.callback({ id: u.id, label: u.label });
            }
        }
        closeUserPicker(id);
    };

    window.filterUserTree = function (id) {
        var searchInput = document.getElementById('pickerSearch_' + id);
        var q = searchInput ? searchInput.value.trim() : '';
        loadTree(id, q);
    };

    // ── 页面加载时自动初始化页面上已存在的 picker ──
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.user-picker-overlay').forEach(function (overlay) {
            var id = overlay.id.replace('pickerOverlay_', '');
            if (id) initInstance(id);
        });
    });

})();
