/**
 * CAD 预览 — 截图
 */
import { S, hooks, applyCanvasClear, applyOrthoFrustum, setToggleActive } from './core.js';

function shotPanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-shot-panel]');
}

function toggleShotPanel() {
    var panel = shotPanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showShotPanel();
    } else {
        hideShotPanel();
    }
}

function showShotPanel() {
    hooks.hideLightPanel();
    hooks.hideSectionPanel();
    hooks.hideExplodePanel();
    hooks.hideMeasurePanel();
    hooks.hideDisplayPanel();
    var panel = shotPanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    syncShotUi();
    setToggleActive('screenshot', true);
}

function hideShotPanel() {
    var panel = shotPanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    setToggleActive('screenshot', false);
}

function setShotScale(n) {
    n = Math.round(Number(n));
    if (!(n >= 1 && n <= 8)) {
        n = 2;
    }
    S.shotScale = n;
    syncShotUi();
}

function setShotSize(n) {
    n = Number(n) || 0;
    if (n !== 1920 && n !== 2560 && n !== 3840) {
        n = 0;
    }
    S.shotSize = n;
    syncShotUi();
}

function syncShotUi() {
    var panel = shotPanel();
    if (!panel) {
        return;
    }
    var shotMap = {
        measure: S.shotIncludeMeasure,
        helpers: S.shotIncludeHelpers,
        highlight: S.shotIncludeHighlight,
        alpha: S.shotAlpha,
    };
    Object.keys(shotMap).forEach(function (key) {
        var el = panel.querySelector('[data-cad-shot="' + key + '"]');
        if (el) {
            el.checked = shotMap[key];
        }
    });
    var scaleBtns = panel.querySelectorAll('[data-cad-action="shot-scale"]');
    var i;
    for (i = 0; i < scaleBtns.length; i++) {
        scaleBtns[i].classList.toggle(
            'active',
            Number(scaleBtns[i].getAttribute('data-cad-shot-scale')) === S.shotScale
        );
    }
    var sizeBtns = panel.querySelectorAll('[data-cad-action="shot-size"]');
    var j;
    for (j = 0; j < sizeBtns.length; j++) {
        sizeBtns[j].classList.toggle(
            'active',
            Number(sizeBtns[j].getAttribute('data-cad-shot-size')) === S.shotSize
        );
    }
}

function captureScreenshot() {
    if (!S.renderer || !S.scene || !S.camera || !S.canvasEl || S.capturingShot) {
        return;
    }
    S.capturingShot = true;
    hooks.hideMeasurePreview();
    var hidden = [];
    var els = S.stageEl ? S.stageEl.querySelectorAll(
        '[data-cad-status], [data-cad-error], [data-cad-light-panel], [data-cad-tree-panel], [data-cad-section-panel], [data-cad-explode-panel], [data-cad-measure-panel], [data-cad-display-panel], [data-cad-shot-panel], [data-cad-measure-label], [data-cad-view-roll]'
    ) : [];
    for (var i = 0; i < els.length; i++) {
        if (!els[i].classList.contains('is-hidden')) {
            els[i].classList.add('is-hidden');
            hidden.push(els[i]);
        }
    }
    var hidden3d = [];
    function hide3d(obj) {
        if (obj && obj.visible) {
            hidden3d.push(obj);
            obj.visible = false;
        }
    }
    hide3d(S.pivotHelper);
    S.sectionHelpers.forEach(function (h) {
        hide3d(h.helper);
    });
    if (!S.shotIncludeMeasure) {
        hide3d(S.measureGroup);
        hide3d(S.measurePreview);
    }
    if (!S.shotIncludeHelpers) {
        hide3d(S.gridHelper);
        hide3d(S.axesHelper);
    }
    var highlightHidden = false;
    var highlightIds = (hooks.currentSelectedIds ? hooks.currentSelectedIds() : (S.selectedNodeId ? [S.selectedNodeId] : []));
    if (!S.shotIncludeHighlight && highlightIds.length) {
        highlightIds.forEach(function (id) {
            hooks.restoreEmissive(id);
        });
        highlightHidden = true;
    }

    var liveW = (S.stageEl && S.stageEl.clientWidth) || 800;
    var liveH = (S.stageEl && S.stageEl.clientHeight) || 480;
    var liveRatio = Math.min(window.devicePixelRatio || 1, 2);
    var w = liveW;
    var h = liveH;
    if (S.shotSize > 0) {
        var longSide = Math.max(liveW, liveH) || 1;
        var k = S.shotSize / longSide;
        w = Math.max(1, Math.round(liveW * k));
        h = Math.max(1, Math.round(liveH * k));
    }
    var scale = S.shotScale;
    var maxDim = 8192;
    try {
        var gl = S.renderer.getContext();
        if (gl) {
            var cap = gl.getParameter(gl.MAX_RENDERBUFFER_SIZE);
            if (cap) {
                maxDim = Math.min(maxDim, cap);
            }
        }
    } catch (e) { /* ignore */ }
    if (Math.max(w, h) * scale > maxDim) {
        scale = maxDim / Math.max(w, h);
    }

    if (S.camera.isOrthographicCamera) {
        applyOrthoFrustum(w, h);
    } else {
        S.camera.aspect = w / Math.max(h, 1);
        S.camera.updateProjectionMatrix();
    }
    S.renderer.setPixelRatio(scale);
    S.renderer.setSize(w, h, false);
    applyCanvasClear(S.shotAlpha);
    S.renderer.render(S.scene, S.camera);

    var base = String(S.currentFileName || 'cad')
        .replace(/\.[^.]+$/, '')
        .replace(/[\\/:*?"<>|]+/g, '_')
        .trim() || 'cad';
    S.canvasEl.toBlob(function (blob) {
        hidden.forEach(function (el) {
            el.classList.remove('is-hidden');
        });
        hidden3d.forEach(function (obj) {
            obj.visible = true;
        });
        if (highlightHidden && highlightIds.length) {
            highlightIds.forEach(function (id) {
                hooks.applyEmissive(id);
            });
        }
        if (S.camera) {
            if (S.camera.isOrthographicCamera) {
                applyOrthoFrustum(liveW, liveH);
            } else {
                S.camera.aspect = liveW / Math.max(liveH, 1);
                S.camera.updateProjectionMatrix();
            }
        }
        if (S.renderer) {
            S.renderer.setPixelRatio(liveRatio);
            S.renderer.setSize(liveW, liveH, false);
            applyCanvasClear(false);
        }
        S.capturingShot = false;
        if (!blob) {
            return;
        }
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = base + '.png';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () {
            URL.revokeObjectURL(url);
        }, 1500);
    }, 'image/png');
}


hooks.shotPanel = shotPanel;
hooks.toggleShotPanel = toggleShotPanel;
hooks.showShotPanel = showShotPanel;
hooks.hideShotPanel = hideShotPanel;
hooks.setShotScale = setShotScale;
hooks.setShotSize = setShotSize;
hooks.syncShotUi = syncShotUi;
hooks.captureScreenshot = captureScreenshot;
export { shotPanel, toggleShotPanel, showShotPanel, hideShotPanel, setShotScale, setShotSize, syncShotUi, captureScreenshot };
