/**
 * CAD 预览 — 装配结构树
 */
import { S, hooks, HIGHLIGHT_EMISSIVE, TREE_AUTO_COLLAPSE_MIN, escapeHtml, getTreeChildren, objectIsShown } from './core.js';

function treePanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-panel]');
}

function toggleTreePanel() {
    var panel = treePanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showTreePanel();
    } else {
        hideTreePanel();
    }
}

function showTreePanel() {
    var panel = treePanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    setTreeButtonActive(true);
}

function hideTreePanel() {
    var panel = treePanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    setTreeButtonActive(false);
}

function setTreeButtonActive(on) {
    var btn = S.pageRoot && S.pageRoot.querySelector('[data-cad-action="tree"]');
    if (btn) {
        btn.classList.toggle('active', !!on);
    }
}

function resetTreeDom() {
    resetTreeFilterState();
    var tree = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree]');
    if (tree) {
        tree.innerHTML = '<div class="text-muted small px-1">解析完成后显示装配树</div>';
    }
}

function resetTreeFilterState() {
    S.treeQuery = '';
    S.treeVisFilter = 'all';
    if (!S.pageRoot) {
        return;
    }
    var search = S.pageRoot.querySelector('[data-cad-tree-search]');
    if (search) {
        search.value = '';
    }
    var group = S.pageRoot.querySelector('.cad-preview-tree-filters');
    if (group) {
        group.setAttribute('data-cad-tree-filter', 'all');
        var chips = group.querySelectorAll('[data-cad-action="tree-filter"]');
        for (var i = 0; i < chips.length; i++) {
            chips[i].classList.toggle('active', chips[i].getAttribute('data-cad-tree-filter') === 'all');
        }
    }
    var empty = S.pageRoot.querySelector('[data-cad-tree-empty]');
    if (empty) {
        empty.classList.add('is-hidden');
    }
    var tree = S.pageRoot.querySelector('[data-cad-tree]');
    if (tree) {
        tree.classList.remove('is-hidden');
    }
    var stats = S.pageRoot.querySelector('[data-cad-tree-stats]');
    if (stats) {
        stats.textContent = '';
    }
}

function cacheLeafCounts() {
    Object.keys(S.nodeMap).forEach(function (id) {
        S.nodeMap[id].leafCount = 0;
    });
    Object.keys(S.nodeMap).forEach(function (id) {
        var rec = S.nodeMap[id];
        if (!rec || getTreeChildren(rec.object).length) {
            return;
        }
        rec.leafCount = 1;
        var cur = rec.parentId;
        while (cur && S.nodeMap[cur]) {
            S.nodeMap[cur].leafCount += 1;
            cur = S.nodeMap[cur].parentId;
        }
    });
}

function treeLeafTotal() {
    if (!S.modelGroup) {
        return 0;
    }
    var total = 0;
    getTreeChildren(S.modelGroup).forEach(function (root) {
        var rec = S.nodeMap[root.userData && root.userData.cadNodeId];
        total += rec && rec.leafCount ? rec.leafCount : 0;
    });
    return total;
}

function hiddenLeafCount() {
    var hidden = 0;
    Object.keys(S.nodeMap).forEach(function (id) {
        var rec = S.nodeMap[id];
        if (!rec || getTreeChildren(rec.object).length) {
            return;
        }
        if (!objectIsShown(rec.object)) {
            hidden += 1;
        }
    });
    return hidden;
}

function treeFilterOn() {
    return !!(S.treeQuery && S.treeQuery.trim()) || S.treeVisFilter !== 'all';
}

function nodeMatchesFilter(rec) {
    if (!rec) {
        return false;
    }
    var query = (S.treeQuery || '').trim().toLowerCase();
    if (query && String(rec.name || '').toLowerCase().indexOf(query) === -1) {
        return false;
    }
    if (S.treeVisFilter === 'visible') {
        return !!rec.object.visible;
    }
    if (S.treeVisFilter === 'hidden') {
        return !rec.object.visible;
    }
    return true;
}

function expandTreeAncestors(id) {
    var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
    var p = li && li.parentElement;
    while (p) {
        if (p.classList && p.classList.contains('cad-preview-tree-node')) {
            p.classList.remove('is-collapsed');
        }
        p = p.parentElement;
    }
}

function updateTreeStats(hitCount) {
    var stats = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-stats]');
    if (!stats) {
        return;
    }
    var text = treeLeafTotal() + ' 件 · 隐藏 ' + hiddenLeafCount();
    if (treeFilterOn() && hitCount != null) {
        text += ' · 匹配 ' + hitCount;
    }
    stats.textContent = text;
}

function applyTreeFilter() {
    if (!S.pageRoot) {
        return;
    }
    var filterOn = treeFilterOn();
    var hits = {};
    var hitCount = 0;
    Object.keys(S.nodeMap).forEach(function (id) {
        if (nodeMatchesFilter(S.nodeMap[id])) {
            hits[id] = true;
            hitCount += 1;
        }
    });
    var keep = {};
    if (filterOn) {
        Object.keys(hits).forEach(function (id) {
            var cur = id;
            while (cur) {
                keep[cur] = true;
                cur = S.nodeMap[cur] ? S.nodeMap[cur].parentId : null;
            }
        });
    }
    var nodes = S.pageRoot.querySelectorAll('[data-cad-tree-node]');
    for (var i = 0; i < nodes.length; i++) {
        var li = nodes[i];
        var id = li.getAttribute('data-cad-tree-node');
        li.classList.toggle('is-filtered-out', filterOn && !keep[id]);
    }
    if (filterOn) {
        Object.keys(hits).forEach(expandTreeAncestors);
    }
    var noMatch = filterOn && hitCount === 0;
    var empty = S.pageRoot.querySelector('[data-cad-tree-empty]');
    if (empty) {
        empty.classList.toggle('is-hidden', !noMatch);
    }
    var tree = S.pageRoot.querySelector('[data-cad-tree]');
    if (tree) {
        tree.classList.toggle('is-hidden', noMatch);
    }
    updateTreeStats(hitCount);
}

function autoCollapseLargeGroups() {
    Object.keys(S.nodeMap).forEach(function (id) {
        var rec = S.nodeMap[id];
        if (!rec || rec.parentId == null) {
            return;
        }
        if (getTreeChildren(rec.object).length < TREE_AUTO_COLLAPSE_MIN) {
            return;
        }
        var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
        if (li) {
            li.classList.add('is-collapsed');
        }
    });
}

function setTreeVisFilter(kind) {
    S.treeVisFilter = kind === 'visible' || kind === 'hidden' ? kind : 'all';
    var group = S.pageRoot && S.pageRoot.querySelector('.cad-preview-tree-filters');
    if (group) {
        group.setAttribute('data-cad-tree-filter', S.treeVisFilter);
        var chips = group.querySelectorAll('[data-cad-action="tree-filter"]');
        for (var i = 0; i < chips.length; i++) {
            chips[i].classList.toggle(
                'active',
                chips[i].getAttribute('data-cad-tree-filter') === S.treeVisFilter
            );
        }
    }
    applyTreeFilter();
}

function expandAllTreeNodes() {
    if (!S.pageRoot) {
        return;
    }
    var nodes = S.pageRoot.querySelectorAll('[data-cad-tree-node]');
    for (var i = 0; i < nodes.length; i++) {
        nodes[i].classList.remove('is-collapsed');
    }
}

function collapseAllTreeNodes() {
    Object.keys(S.nodeMap).forEach(function (id) {
        var rec = S.nodeMap[id];
        if (!rec || rec.parentId == null) {
            return;
        }
        if (!getTreeChildren(rec.object).length) {
            return;
        }
        var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
        if (li) {
            li.classList.add('is-collapsed');
        }
    });
}

function onTreeSearchInput(ev) {
    var input = ev.target && ev.target.closest && ev.target.closest('[data-cad-tree-search]');
    if (!input) {
        return;
    }
    S.treeQuery = input.value || '';
    applyTreeFilter();
}

function onTreeSearchKeydown(ev) {
    if (ev.key !== 'Escape') {
        return;
    }
    var input = ev.target && ev.target.closest && ev.target.closest('[data-cad-tree-search]');
    if (!input || !input.value) {
        return;
    }
    ev.preventDefault();
    input.value = '';
    S.treeQuery = '';
    applyTreeFilter();
}

function renderTree() {
    var tree = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree]');
    if (!tree) {
        return;
    }
    var roots = S.modelGroup ? getTreeChildren(S.modelGroup) : [];
    if (!roots.length) {
        tree.classList.remove('is-hidden');
        tree.innerHTML = '<div class="text-muted small px-1">无可显示的结构</div>';
        var empty = S.pageRoot.querySelector('[data-cad-tree-empty]');
        if (empty) {
            empty.classList.add('is-hidden');
        }
        updateTreeStats(0);
        return;
    }
    tree.innerHTML = '<ul class="cad-preview-tree-list">' + roots.map(renderTreeNode).join('') + '</ul>';
    autoCollapseLargeGroups();
    applyTreeFilter();
}

function renderTreeNode(object) {
    var id = object.userData.cadNodeId;
    var rec = S.nodeMap[id];
    var kids = getTreeChildren(object);
    var isLeaf = kids.length === 0;
    var hidden = !object.visible;
    var selected = isNodeSelected(id);
    var cls = 'cad-preview-tree-node';
    if (hidden) {
        cls += ' is-hidden-node';
    }
    if (selected) {
        cls += ' is-selected';
    }
    var toggleCls = 'cad-preview-tree-toggle' + (isLeaf ? ' is-leaf' : '');
    var eyeIcon = hidden ? 'ti ti-eye-off' : 'ti ti-eye';
    var name = rec ? rec.name : id;
    var countHtml = '';
    if (!isLeaf && rec && rec.leafCount) {
        countHtml = '<span class="cad-preview-tree-count" data-cad-tree-count>(' + rec.leafCount + ')</span>';
    }
    var childrenHtml = kids.length ? '<ul>' + kids.map(renderTreeNode).join('') + '</ul>' : '';
    return '<li class="' + cls + '" data-cad-tree-node="' + id + '">' +
        '<div class="cad-preview-tree-row">' +
        '<button type="button" class="' + toggleCls + '" data-cad-tree-toggle="' + id + '" aria-label="展开">' +
        '<i class="ti ti-chevron-down"></i></button>' +
        '<button type="button" class="cad-preview-tree-vis" data-cad-tree-vis="' + id + '" aria-label="显隐">' +
        '<i class="' + eyeIcon + '"></i></button>' +
        '<span class="cad-preview-tree-label" data-cad-tree-select="' + id + '" title="' + escapeHtml(name) + '">' +
        escapeHtml(name) + '</span>' + countHtml + '</div>' + childrenHtml + '</li>';
}

function onTreeClick(ev) {
    var toggle = ev.target.closest('[data-cad-tree-toggle]');
    if (toggle) {
        ev.preventDefault();
        if (!toggle.classList.contains('is-leaf')) {
            var foldLi = toggle.closest('[data-cad-tree-node]');
            if (foldLi) {
                foldLi.classList.toggle('is-collapsed');
            }
        }
        return;
    }
    var vis = ev.target.closest('[data-cad-tree-vis]');
    if (vis) {
        ev.preventDefault();
        toggleNodeVisible(vis.getAttribute('data-cad-tree-vis'));
        return;
    }
    var sel = ev.target.closest('[data-cad-tree-select]');
    if (sel) {
        ev.preventDefault();
        selectNode(sel.getAttribute('data-cad-tree-select'), {
            toggle: !!(ev.ctrlKey || ev.metaKey),
        });
    }
}

function toggleNodeVisible(id) {
    var rec = S.nodeMap[id];
    if (!rec) {
        return;
    }
    rec.object.visible = !rec.object.visible;
    syncTreeNodeUi(id);
    applyTreeFilter();
    hooks.syncMeasureUi();
}

function syncTreeNodeUi(id) {
    var rec = S.nodeMap[id];
    var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
    if (!rec || !li) {
        return;
    }
    li.classList.toggle('is-hidden-node', !rec.object.visible);
    var row = li.querySelector('.cad-preview-tree-row');
    var icon = row && row.querySelector('.cad-preview-tree-vis i');
    if (icon) {
        icon.className = rec.object.visible ? 'ti ti-eye' : 'ti ti-eye-off';
    }
}

function refreshTreeVisibility() {
    Object.keys(S.nodeMap).forEach(syncTreeNodeUi);
}

function eachSolidMaterial(nodeId, fn) {
    var rec = S.nodeMap[nodeId];
    if (!rec) {
        return;
    }
    rec.object.traverse(function (obj) {
        if (!obj.userData || obj.userData.cadRole !== 'solid') {
            return;
        }
        var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach(function (m) {
            if (m && m.emissive) {
                fn(m);
            }
        });
    });
}

function restoreEmissive(nodeId) {
    eachSolidMaterial(nodeId, function (m) {
        if (m.userData && m.userData._cadEmissiveOrig != null) {
            m.emissive.setHex(m.userData._cadEmissiveOrig);
        }
    });
}

function applyEmissive(nodeId) {
    eachSolidMaterial(nodeId, function (m) {
        if (!m.userData) {
            m.userData = {};
        }
        if (m.userData._cadEmissiveOrig == null) {
            m.userData._cadEmissiveOrig = m.emissive.getHex();
        }
        m.emissive.setHex(HIGHLIGHT_EMISSIVE);
    });
}

function currentSelectedIds() {
    var ids = [];
    var seen = {};
    function add(id) {
        if (!id || seen[id] || !S.nodeMap[id]) {
            return;
        }
        seen[id] = true;
        ids.push(id);
    }
    (S.selectedNodeIds || []).forEach(add);
    add(S.selectedNodeId);
    return ids;
}

function isNodeSelected(id) {
    return currentSelectedIds().indexOf(id) !== -1;
}

function markTreeSelected(id, on) {
    var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
    if (li) {
        li.classList.toggle('is-selected', !!on);
    }
}

function revealTreeNode(id) {
    var li = S.pageRoot && S.pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
    if (!li) {
        return;
    }
    var p = li.parentElement;
    while (p) {
        if (p.classList && p.classList.contains('cad-preview-tree-node')) {
            p.classList.remove('is-collapsed');
        }
        p = p.parentElement;
    }
    if (typeof li.scrollIntoView === 'function') {
        li.scrollIntoView({ block: 'nearest' });
    }
}

function setSelection(ids) {
    var prev = currentSelectedIds();
    var next = [];
    var seen = {};
    (ids || []).forEach(function (id) {
        if (!id || seen[id] || !S.nodeMap[id]) {
            return;
        }
        seen[id] = true;
        next.push(id);
    });
    prev.forEach(function (id) {
        if (seen[id]) {
            return;
        }
        restoreEmissive(id);
        markTreeSelected(id, false);
    });
    S.selectedNodeIds = next;
    S.selectedNodeId = next.length ? next[next.length - 1] : null;
    next.forEach(function (id) {
        applyEmissive(id);
        markTreeSelected(id, true);
    });
    if (S.selectedNodeId) {
        revealTreeNode(S.selectedNodeId);
    }
    hooks.syncDisplayUi();
    hooks.syncMeasureUi();
    hooks.syncSectionUi();
}

function selectNode(id, opts) {
    opts = opts || {};
    if (!id) {
        setSelection([]);
        return;
    }
    if (!S.nodeMap[id]) {
        return;
    }
    if (opts.toggle) {
        var ids = currentSelectedIds().slice();
        var at = ids.indexOf(id);
        if (at >= 0) {
            ids.splice(at, 1);
        } else {
            ids.push(id);
        }
        setSelection(ids);
        return;
    }
    setSelection([id]);
}

function isOnSelectedPath(id) {
    var selected = currentSelectedIds();
    if (!selected.length) {
        return false;
    }
    var i;
    for (i = 0; i < selected.length; i++) {
        if (id === selected[i]) {
            return true;
        }
        var cur = selected[i];
        while (cur) {
            if (cur === id) {
                return true;
            }
            cur = S.nodeMap[cur] ? S.nodeMap[cur].parentId : null;
        }
        cur = id;
        while (cur) {
            if (cur === selected[i]) {
                return true;
            }
            cur = S.nodeMap[cur] ? S.nodeMap[cur].parentId : null;
        }
    }
    return false;
}

function isolateSelected() {
    if (!currentSelectedIds().length) {
        return;
    }
    if (!S.isolateBackup) {
        S.isolateBackup = {};
        Object.keys(S.nodeMap).forEach(function (id) {
            S.isolateBackup[id] = S.nodeMap[id].object.visible;
        });
    }
    Object.keys(S.nodeMap).forEach(function (id) {
        S.nodeMap[id].object.visible = isOnSelectedPath(id);
    });
    refreshTreeVisibility();
    applyTreeFilter();
    hooks.syncMeasureUi();
}

function showAllNodes() {
    S.isolateBackup = null;
    Object.keys(S.nodeMap).forEach(function (id) {
        S.nodeMap[id].object.visible = true;
    });
    refreshTreeVisibility();
    applyTreeFilter();
    hooks.syncMeasureUi();
}


hooks.treePanel = treePanel;
hooks.toggleTreePanel = toggleTreePanel;
hooks.showTreePanel = showTreePanel;
hooks.hideTreePanel = hideTreePanel;
hooks.setTreeButtonActive = setTreeButtonActive;
hooks.resetTreeDom = resetTreeDom;
hooks.resetTreeFilterState = resetTreeFilterState;
hooks.cacheLeafCounts = cacheLeafCounts;
hooks.treeLeafTotal = treeLeafTotal;
hooks.hiddenLeafCount = hiddenLeafCount;
hooks.treeFilterOn = treeFilterOn;
hooks.nodeMatchesFilter = nodeMatchesFilter;
hooks.expandTreeAncestors = expandTreeAncestors;
hooks.updateTreeStats = updateTreeStats;
hooks.applyTreeFilter = applyTreeFilter;
hooks.autoCollapseLargeGroups = autoCollapseLargeGroups;
hooks.setTreeVisFilter = setTreeVisFilter;
hooks.expandAllTreeNodes = expandAllTreeNodes;
hooks.collapseAllTreeNodes = collapseAllTreeNodes;
hooks.onTreeSearchInput = onTreeSearchInput;
hooks.onTreeSearchKeydown = onTreeSearchKeydown;
hooks.renderTree = renderTree;
hooks.renderTreeNode = renderTreeNode;
hooks.onTreeClick = onTreeClick;
hooks.toggleNodeVisible = toggleNodeVisible;
hooks.syncTreeNodeUi = syncTreeNodeUi;
hooks.refreshTreeVisibility = refreshTreeVisibility;
hooks.eachSolidMaterial = eachSolidMaterial;
hooks.restoreEmissive = restoreEmissive;
hooks.applyEmissive = applyEmissive;
hooks.currentSelectedIds = currentSelectedIds;
hooks.isNodeSelected = isNodeSelected;
hooks.setSelection = setSelection;
hooks.selectNode = selectNode;
hooks.isOnSelectedPath = isOnSelectedPath;
hooks.isolateSelected = isolateSelected;
hooks.showAllNodes = showAllNodes;
export { treePanel, toggleTreePanel, showTreePanel, hideTreePanel, setTreeButtonActive, resetTreeDom, resetTreeFilterState, cacheLeafCounts, treeLeafTotal, hiddenLeafCount, treeFilterOn, nodeMatchesFilter, expandTreeAncestors, updateTreeStats, applyTreeFilter, autoCollapseLargeGroups, setTreeVisFilter, expandAllTreeNodes, collapseAllTreeNodes, onTreeSearchInput, onTreeSearchKeydown, renderTree, renderTreeNode, onTreeClick, toggleNodeVisible, syncTreeNodeUi, refreshTreeVisibility, eachSolidMaterial, restoreEmissive, applyEmissive, currentSelectedIds, isNodeSelected, setSelection, selectNode, isOnSelectedPath, isolateSelected, showAllNodes };
