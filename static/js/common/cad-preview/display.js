/**
 * CAD 预览 — 显示模式 / 深色画布 / 零件色
 */
import { S, hooks, DEFAULT_COLOR, XRAY_OPACITY, applyCanvasClear, eachMaterial, setToggleActive } from './core.js';

function displayPanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-display-panel]');
}

function toggleDisplayPanel() {
    var panel = displayPanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showDisplayPanel();
    } else {
        hideDisplayPanel();
    }
}

function showDisplayPanel() {
    hooks.hideLightPanel();
    hooks.hideSectionPanel();
    hooks.hideExplodePanel();
    hooks.hideMeasurePanel();
    hooks.hideShotPanel();
    var panel = displayPanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    syncDisplayUi();
    setToggleActive('display-panel', true);
}

function hideDisplayPanel() {
    var panel = displayPanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    setToggleActive('display-panel', false);
}

function setDarkCanvas(on) {
    S.darkCanvas = !!on;
    if (S.stageEl) {
        S.stageEl.classList.toggle('is-dark', S.darkCanvas);
    }
    applyCanvasClear(false);
    if (S.gridOn) {
        hooks.syncHelpers();
    }
    setToggleActive('dark', S.darkCanvas);
    syncDisplayUi();
}

function hexToCss(hex) {
    var n = hex & 0xffffff;
    var s = n.toString(16);
    while (s.length < 6) {
        s = '0' + s;
    }
    return '#' + s;
}

function parseCssColor(value) {
    var s = String(value || '').replace('#', '');
    var n = parseInt(s, 16);
    return isNaN(n) ? DEFAULT_COLOR : n;
}

function applyPartColor(nodeId, hex) {
    if (!nodeId || !S.nodeMap[nodeId]) {
        return;
    }
    hooks.eachSolidMaterial(nodeId, function (m) {
        if (!m.color) {
            return;
        }
        if (!m.userData) {
            m.userData = {};
        }
        if (m.userData._cadColorOrig == null) {
            m.userData._cadColorOrig = m.color.getHex();
        }
        m.color.setHex(hex);
        m.needsUpdate = true;
    });
}

function restorePartColor(nodeId) {
    var ids = nodeId ? [nodeId] : Object.keys(S.nodeMap);
    ids.forEach(function (id) {
        hooks.eachSolidMaterial(id, function (m) {
            if (m.color && m.userData && m.userData._cadColorOrig != null) {
                m.color.setHex(m.userData._cadColorOrig);
                m.needsUpdate = true;
            }
        });
    });
    syncDisplayUi();
}

function applySelectedPartColor() {
    if (!S.selectedNodeId) {
        return;
    }
    var input = S.pageRoot && S.pageRoot.querySelector('[data-cad-part-color]');
    applyPartColor(S.selectedNodeId, parseCssColor(input && input.value));
    syncDisplayUi();
}

function selectedPartColorHex() {
    var hex = null;
    if (!S.selectedNodeId) {
        return DEFAULT_COLOR;
    }
    hooks.eachSolidMaterial(S.selectedNodeId, function (m) {
        if (hex == null && m.color) {
            hex = m.color.getHex();
        }
    });
    return hex == null ? DEFAULT_COLOR : hex;
}

function onDisplayInput(ev) {
    if (ev.target && ev.target.hasAttribute('data-cad-dark')) {
        setDarkCanvas(!!ev.target.checked);
        return;
    }
    var input = ev.target.closest('[data-cad-shot]');
    if (!input) {
        return;
    }
    var kind = input.getAttribute('data-cad-shot');
    if (kind === 'measure') {
        S.shotIncludeMeasure = !!input.checked;
    } else if (kind === 'helpers') {
        S.shotIncludeHelpers = !!input.checked;
    } else if (kind === 'highlight') {
        S.shotIncludeHighlight = !!input.checked;
    } else if (kind === 'alpha') {
        S.shotAlpha = !!input.checked;
    }
}

function syncDisplayUi() {
    var panel = displayPanel();
    if (!panel) {
        return;
    }
    var darkEl = panel.querySelector('[data-cad-dark]');
    if (darkEl) {
        darkEl.checked = S.darkCanvas;
    }
    var nameEl = panel.querySelector('[data-cad-part-name]');
    var rec = S.selectedNodeId && S.nodeMap[S.selectedNodeId];
    if (nameEl) {
        nameEl.textContent = rec ? (rec.name || S.selectedNodeId) : '（无选中）';
    }
    var colorEl = panel.querySelector('[data-cad-part-color]');
    if (colorEl && rec) {
        colorEl.value = hexToCss(selectedPartColorHex());
    }
    var applyBtn = panel.querySelector('[data-cad-action="part-color"]');
    var resetBtn = panel.querySelector('[data-cad-action="part-color-reset"]');
    if (applyBtn) {
        applyBtn.disabled = !rec;
    }
    if (resetBtn) {
        resetBtn.disabled = !rec;
    }
}

function applyXrayMaterial(m, on) {
    if (!m.userData) {
        m.userData = {};
    }
    if (on) {
        if (m.userData._cadXrayOrig == null) {
            m.userData._cadXrayOrig = {
                transparent: m.transparent,
                opacity: m.opacity,
                depthWrite: m.depthWrite,
            };
        }
        m.transparent = true;
        m.opacity = XRAY_OPACITY;
        m.depthWrite = false;
        m.needsUpdate = true;
    } else if (m.userData._cadXrayOrig) {
        m.transparent = m.userData._cadXrayOrig.transparent;
        m.opacity = m.userData._cadXrayOrig.opacity;
        m.depthWrite = m.userData._cadXrayOrig.depthWrite;
        m.userData._cadXrayOrig = null;
        m.needsUpdate = true;
    }
}

function setDisplayMode(mode) {
    if (mode !== 'wireframe' && mode !== 'xray') {
        mode = 'solid';
    }
    S.displayMode = mode;
    if (S.modelGroup) {
        S.modelGroup.traverse(function (obj) {
            var role = obj.userData && obj.userData.cadRole;
            if (role === 'solid') {
                obj.visible = S.displayMode !== 'wireframe';
                eachMaterial(obj, function (m) {
                    applyXrayMaterial(m, S.displayMode === 'xray');
                });
            } else if (role === 'edges') {
                obj.visible = S.displayMode !== 'solid';
            }
        });
    }
    setToggleActive('solid', S.displayMode === 'solid');
    setToggleActive('wireframe', S.displayMode === 'wireframe');
    setToggleActive('xray', S.displayMode === 'xray');
}


hooks.displayPanel = displayPanel;
hooks.toggleDisplayPanel = toggleDisplayPanel;
hooks.showDisplayPanel = showDisplayPanel;
hooks.hideDisplayPanel = hideDisplayPanel;
hooks.setDarkCanvas = setDarkCanvas;
hooks.hexToCss = hexToCss;
hooks.parseCssColor = parseCssColor;
hooks.applyPartColor = applyPartColor;
hooks.restorePartColor = restorePartColor;
hooks.applySelectedPartColor = applySelectedPartColor;
hooks.selectedPartColorHex = selectedPartColorHex;
hooks.onDisplayInput = onDisplayInput;
hooks.syncDisplayUi = syncDisplayUi;
hooks.applyXrayMaterial = applyXrayMaterial;
hooks.setDisplayMode = setDisplayMode;
export { displayPanel, toggleDisplayPanel, showDisplayPanel, hideDisplayPanel, setDarkCanvas, hexToCss, parseCssColor, applyPartColor, restorePartColor, applySelectedPartColor, selectedPartColorHex, onDisplayInput, syncDisplayUi, applyXrayMaterial, setDisplayMode };
