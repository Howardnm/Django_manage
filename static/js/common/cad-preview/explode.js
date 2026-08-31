/**
 * CAD 预览 — 爆炸图
 */
import { THREE, S, hooks, DEFAULT_EXPLODE_BIN_PCT, getTreeChildren, setToggleActive } from './core.js';

function explodePanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-explode-panel]');
}

function toggleExplodePanel() {
    var panel = explodePanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showExplodePanel();
    } else {
        hideExplodePanel();
    }
}

function showExplodePanel() {
    hooks.hideLightPanel();
    hooks.hideSectionPanel();
    hooks.hideMeasurePanel();
    hooks.hideDisplayPanel();
    hooks.hideShotPanel();
    var panel = explodePanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    if (!S.explodeUnits.length) {
        prepareExplodeUnits();
    }
    syncExplodeUi();
    setToggleActive('explode', true);
}

function hideExplodePanel() {
    var panel = explodePanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    setToggleActive('explode', S.explodeAmount > 0);
}

function findDefaultExplodeParent() {
    var roots = S.modelGroup ? getTreeChildren(S.modelGroup) : [];
    if (!roots.length) {
        return { parent: null, units: [] };
    }
    if (roots.length >= 2) {
        return { parent: null, units: roots };
    }
    var cur = roots[0];
    while (cur) {
        var kids = getTreeChildren(cur);
        if (kids.length >= 2) {
            return { parent: cur, units: kids };
        }
        if (kids.length === 1) {
            cur = kids[0];
            continue;
        }
        return { parent: cur, units: kids };
    }
    return { parent: roots[0], units: [] };
}

function restoreExplodeHomes() {
    S.explodeUnits.forEach(function (u) {
        u.object.position.copy(u.home);
    });
    S.explodeUnits = [];
    S.explodeAmount = 0;
}

function unionBoxOf(objects) {
    var box = new THREE.Box3();
    var has = false;
    (objects || []).forEach(function (obj) {
        obj.updateWorldMatrix(true, true);
        var b = new THREE.Box3().setFromObject(obj);
        if (b.isEmpty()) {
            return;
        }
        if (!has) {
            box.copy(b);
            has = true;
        } else {
            box.union(b);
        }
    });
    return { box: box, has: has };
}

function worldCenterOf(obj) {
    obj.updateWorldMatrix(true, true);
    var b = new THREE.Box3().setFromObject(obj);
    return b.isEmpty() ? null : b.getCenter(new THREE.Vector3());
}

function explodeOriginPoint(fallback) {
    if (S.explodeCenterId && S.nodeMap[S.explodeCenterId]) {
        var center = worldCenterOf(S.nodeMap[S.explodeCenterId].object);
        if (center) {
            return center;
        }
    }
    return fallback.clone();
}

function explodeMetric(center, origin) {
    if (S.explodeStyle === 'x') {
        return center.x - origin.x;
    }
    if (S.explodeStyle === 'y') {
        return center.y - origin.y;
    }
    if (S.explodeStyle === 'z') {
        return center.z - origin.z;
    }
    return center.distanceTo(origin);
}

function computeExplodeDir(center, origin, i, n, obj) {
    var isOriginPart = !!(S.explodeCenterId && obj.userData && obj.userData.cadNodeId === S.explodeCenterId);
    if (S.explodeStyle === 'x' || S.explodeStyle === 'y' || S.explodeStyle === 'z') {
        var axis = new THREE.Vector3(
            S.explodeStyle === 'x' ? 1 : 0,
            S.explodeStyle === 'y' ? 1 : 0,
            S.explodeStyle === 'z' ? 1 : 0
        );
        var delta = explodeMetric(center, origin);
        if (isOriginPart) {
            return new THREE.Vector3(0, 0, 0);
        }
        if (Math.abs(delta) < 1e-8) {
            var s = i - (n - 1) / 2;
            if (Math.abs(s) < 1e-9) {
                s = 1;
            }
            return axis.multiplyScalar(s > 0 ? 1 : -1);
        }
        return axis.multiplyScalar(delta > 0 ? 1 : -1);
    }
    var dir = center.clone().sub(origin);
    if (dir.lengthSq() < 1e-10) {
        if (isOriginPart) {
            return new THREE.Vector3(0, 0, 0);
        }
        var ang = (i / Math.max(n, 1)) * Math.PI * 2;
        dir.set(Math.cos(ang), Math.sin(ang), 0);
    }
    return dir.normalize();
}

function assignExplodeRanks(origin, maxDim) {
    var binPct = Math.max(0.2, Math.min(20, S.explodeBinPct));
    var delta = Math.max(maxDim * (binPct / 100), 1e-10);
    var coincideEps = Math.max(maxDim * 1e-6, 1e-10);
    S.explodeUnits.forEach(function (u, i) {
        var center = worldCenterOf(u.object) || origin.clone();
        var metric = explodeMetric(center, origin);
        var id = u.object.userData && u.object.userData.cadNodeId;
        var isOriginPart = !!(S.explodeCenterId && id === S.explodeCenterId);
        var rank;
        if (S.explodeStyle === 'x' || S.explodeStyle === 'y' || S.explodeStyle === 'z') {
            rank = Math.round(metric / delta);
        } else {
            rank = Math.floor(Math.abs(metric) / delta);
        }
        if (!isOriginPart && Math.abs(metric) < coincideEps) {
            rank = rank === 0 ? 1 : rank;
            if (u.dir.lengthSq() < 1e-12) {
                var ang = (i / Math.max(S.explodeUnits.length, 1)) * Math.PI * 2;
                u.dir.set(Math.cos(ang), Math.sin(ang), 0);
            }
        }
        u.rank = rank;
        if (rank === 0) {
            u.dir.set(0, 0, 0);
        } else {
            u.dir.normalize().multiplyScalar(Math.abs(rank));
        }
    });
}

function assignExplodeDirs() {
    if (!THREE || S.explodeUnits.length < 2) {
        return;
    }
    var objects = S.explodeUnits.map(function (u) { return u.object; });
    var union = unionBoxOf(objects);
    var fallback = union.has ? union.box.getCenter(new THREE.Vector3()) : new THREE.Vector3();
    var size = union.has ? union.box.getSize(new THREE.Vector3()) : new THREE.Vector3(1, 1, 1);
    var origin = explodeOriginPoint(fallback);
    var maxDim = Math.max(size.x, size.y, size.z, 1);
    S.explodeSpan = maxDim * (S.explodeEven ? 0.12 : 0.55);
    S.explodeUnits.forEach(function (u, i) {
        var center = worldCenterOf(u.object) || origin.clone();
        u.dir = computeExplodeDir(center, origin, i, S.explodeUnits.length, u.object);
        u.rank = 1;
    });
    if (S.explodeEven) {
        assignExplodeRanks(origin, maxDim);
    }
}

function recomputeExplodeDirs() {
    if (S.explodeUnits.length < 2) {
        syncExplodeUi();
        return;
    }
    S.explodeUnits.forEach(function (u) {
        u.object.position.copy(u.home);
    });
    assignExplodeDirs();
    applyExplode();
    syncExplodeUi();
    setToggleActive('explode', S.explodeAmount > 0 || hooks.isPanelOpen(explodePanel()));
}

function setExplodeStyle(style) {
    if (style !== 'x' && style !== 'y' && style !== 'z') {
        style = 'radial';
    }
    S.explodeStyle = style;
    if (!S.explodeUnits.length) {
        prepareExplodeUnits();
    } else {
        recomputeExplodeDirs();
    }
    syncExplodeUi();
}

function explodeCenterFromSelected() {
    if (!S.selectedNodeId || !S.nodeMap[S.selectedNodeId]) {
        syncExplodeUi();
        return;
    }
    S.explodeCenterId = S.selectedNodeId;
    if (!S.explodeUnits.length) {
        prepareExplodeUnits();
    } else {
        recomputeExplodeDirs();
    }
    showExplodePanel();
    syncExplodeUi();
}

function setExplodeUnits(units, parent) {
    restoreExplodeHomes();
    S.explodeParentId = parent && parent.userData ? parent.userData.cadNodeId : null;
    if (!THREE || !units || units.length < 2) {
        S.explodeUnits = [];
        syncExplodeUi();
        setToggleActive('explode', hooks.isPanelOpen(explodePanel()));
        return;
    }
    units.forEach(function (obj) {
        S.explodeUnits.push({
            object: obj,
            home: obj.position.clone(),
            dir: new THREE.Vector3(1, 0, 0),
        });
    });
    assignExplodeDirs();
    applyExplode();
    syncExplodeUi();
    setToggleActive('explode', S.explodeAmount > 0 || hooks.isPanelOpen(explodePanel()));
}

function prepareExplodeUnits() {
    var found = findDefaultExplodeParent();
    setExplodeUnits(found.units, found.parent);
}

function explodeToDefault() {
    prepareExplodeUnits();
}

function explodeFromSelected() {
    if (!S.selectedNodeId || !S.nodeMap[S.selectedNodeId]) {
        syncExplodeUi();
        return;
    }
    var rec = S.nodeMap[S.selectedNodeId];
    var kids = getTreeChildren(rec.object);
    setExplodeUnits(kids, rec.object);
    showExplodePanel();
}

function applyExplode() {
    var t = Math.max(0, Math.min(300, S.explodeAmount)) / 100;
    S.explodeUnits.forEach(function (u) {
        u.object.position.copy(u.home).addScaledVector(u.dir, t * S.explodeSpan);
    });
    hooks.syncAllClipWorld();
    hooks.rebuildMeasureGeom();
    hooks.syncMeasureUi();
}

function resetExplode() {
    S.explodeAmount = 0;
    applyExplode();
    syncExplodeUi();
    setToggleActive('explode', hooks.isPanelOpen(explodePanel()));
}

function explodeLevelLabel() {
    if (!S.explodeParentId) {
        return '当前：整棵树（最粗）';
    }
    var rec = S.nodeMap[S.explodeParentId];
    var name = rec ? rec.name : S.explodeParentId;
    return '当前：' + name + ' 的子级（' + S.explodeUnits.length + '）';
}

function explodeCenterLabel() {
    if (S.explodeCenterId && S.nodeMap[S.explodeCenterId]) {
        return '中心：' + S.nodeMap[S.explodeCenterId].name;
    }
    return '中心：包围盒';
}

function syncExplodeUi() {
    var panel = explodePanel();
    if (!panel) {
        return;
    }
    if (S.explodeCenterId && !S.nodeMap[S.explodeCenterId]) {
        S.explodeCenterId = null;
    }
    var can = S.explodeUnits.length >= 2;
    panel.classList.toggle('is-explode-locked', !can);
    var hint = panel.querySelector('[data-cad-explode-hint]');
    if (hint) {
        if (!can && S.selectedNodeId && S.explodeParentId === S.selectedNodeId) {
            hint.textContent = '所选节点没有可分开的子级';
        } else if (!can) {
            hint.textContent = '单实体无法爆炸';
        }
        hint.classList.toggle('is-hidden', can);
    }
    var level = panel.querySelector('[data-cad-explode-level]');
    if (level) {
        level.textContent = explodeLevelLabel();
    }
    var center = panel.querySelector('[data-cad-explode-center]');
    if (center) {
        center.textContent = explodeCenterLabel();
    }
    panel.querySelectorAll('[data-cad-action="explode-style"]').forEach(function (btn) {
        var style = btn.getAttribute('data-cad-explode-style') || 'radial';
        btn.classList.toggle('active', style === S.explodeStyle);
    });
    panel.classList.toggle('is-even-off', !S.explodeEven);
    var even = panel.querySelector('[data-cad-explode="even"]');
    if (even) {
        even.checked = S.explodeEven;
        even.disabled = !can;
    }
    var bin = panel.querySelector('[data-cad-explode="bin"]');
    if (bin) {
        bin.value = String(S.explodeBinPct);
        bin.disabled = !can || !S.explodeEven;
    }
    var binVal = panel.querySelector('[data-cad-explode-bin-val]');
    if (binVal) {
        binVal.textContent = Number(S.explodeBinPct).toFixed(
            Math.abs(S.explodeBinPct % 1) < 1e-6 ? 0 : 1
        ) + '%';
    }
    var input = panel.querySelector('[data-cad-explode="amount"]');
    if (input) {
        input.value = String(S.explodeAmount);
        input.disabled = !can;
    }
    var val = panel.querySelector('[data-cad-explode-val]');
    if (val) {
        val.textContent = Math.round(S.explodeAmount) + '%';
    }
}

function onExplodeInput(ev) {
    var input = ev.target.closest('[data-cad-explode]');
    if (!input) {
        return;
    }
    var kind = input.getAttribute('data-cad-explode');
    if (kind === 'amount') {
        S.explodeAmount = Number(input.value);
        if (!S.explodeUnits.length) {
            prepareExplodeUnits();
        }
        applyExplode();
        syncExplodeUi();
        setToggleActive('explode', S.explodeAmount > 0 || hooks.isPanelOpen(explodePanel()));
        return;
    }
    if (kind === 'even') {
        S.explodeEven = !!input.checked;
        if (!S.explodeUnits.length) {
            prepareExplodeUnits();
        } else {
            recomputeExplodeDirs();
        }
        return;
    }
    if (kind === 'bin') {
        S.explodeBinPct = Math.max(0.2, Math.min(20, Number(input.value) || DEFAULT_EXPLODE_BIN_PCT));
        if (!S.explodeUnits.length) {
            prepareExplodeUnits();
        } else {
            recomputeExplodeDirs();
        }
    }
}


hooks.explodePanel = explodePanel;
hooks.toggleExplodePanel = toggleExplodePanel;
hooks.showExplodePanel = showExplodePanel;
hooks.hideExplodePanel = hideExplodePanel;
hooks.findDefaultExplodeParent = findDefaultExplodeParent;
hooks.restoreExplodeHomes = restoreExplodeHomes;
hooks.unionBoxOf = unionBoxOf;
hooks.worldCenterOf = worldCenterOf;
hooks.explodeOriginPoint = explodeOriginPoint;
hooks.explodeMetric = explodeMetric;
hooks.computeExplodeDir = computeExplodeDir;
hooks.assignExplodeRanks = assignExplodeRanks;
hooks.assignExplodeDirs = assignExplodeDirs;
hooks.recomputeExplodeDirs = recomputeExplodeDirs;
hooks.setExplodeStyle = setExplodeStyle;
hooks.explodeCenterFromSelected = explodeCenterFromSelected;
hooks.setExplodeUnits = setExplodeUnits;
hooks.prepareExplodeUnits = prepareExplodeUnits;
hooks.explodeToDefault = explodeToDefault;
hooks.explodeFromSelected = explodeFromSelected;
hooks.applyExplode = applyExplode;
hooks.resetExplode = resetExplode;
hooks.explodeLevelLabel = explodeLevelLabel;
hooks.explodeCenterLabel = explodeCenterLabel;
hooks.syncExplodeUi = syncExplodeUi;
hooks.onExplodeInput = onExplodeInput;
export { explodePanel, toggleExplodePanel, showExplodePanel, hideExplodePanel, findDefaultExplodeParent, restoreExplodeHomes, unionBoxOf, worldCenterOf, explodeOriginPoint, explodeMetric, computeExplodeDir, assignExplodeRanks, assignExplodeDirs, recomputeExplodeDirs, setExplodeStyle, explodeCenterFromSelected, setExplodeUnits, prepareExplodeUnits, explodeToDefault, explodeFromSelected, applyExplode, resetExplode, explodeLevelLabel, explodeCenterLabel, syncExplodeUi, onExplodeInput };
