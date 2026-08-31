/**
 * CAD 预览入口 — mount / dispose / boot
 * 仅 attachment:viewer 加载。副作用 import 注册各功能 hooks。
 */
import { S, DEFAULT_EXPLODE_BIN_PCT, DEFAULT_HINT, disposeScene, setError, setGroupActive, setHint, setStatus, setToggleActive } from './core.js';
import './ui.js';
import './lights.js';
import './display.js';
import './views.js';
import './pivot.js';
import './load.js';
import './tree.js';
import './section.js';
import './explode.js';
import './measure.js';
import './screenshot.js';
import './picking.js';
import './toolbar.js';
import { hooks } from './core.js';

function onFrame() {
    if (S.lightFollow && hooks.applyLights) {
        hooks.applyLights();
    }
    if (hooks.syncPivotHelper) {
        hooks.syncPivotHelper();
    }
    if (hooks.syncAllClipWorld) {
        hooks.syncAllClipWorld();
    }
    if (hooks.updateSectionHelpers) {
        hooks.updateSectionHelpers();
    }
    if (hooks.updateMeasureLabel) {
        hooks.updateMeasureLabel();
    }
}

hooks.onFrame = onFrame;

function dispose() {
    if (S.abortController) {
        S.abortController.abort();
        S.abortController = null;
    }
    if (hooks.disposeWorker) {
        hooks.disposeWorker();
    }
    disposeScene();
    S.displayMode = 'solid';
    S.orthoOn = false;
    S.gridOn = false;
    S.axesOn = false;
    S.placingPivot = false;
    S.pivotInteracting = false;
    S.pivotHideAt = 0;
    if (hooks.hideLightPanel) {
        hooks.hideLightPanel();
    }
    if (hooks.hideSectionPanel) {
        hooks.hideSectionPanel();
    }
    if (hooks.hideExplodePanel) {
        hooks.hideExplodePanel();
    }
    if (hooks.hideMeasurePanel) {
        hooks.hideMeasurePanel();
    }
    if (hooks.hideDisplayPanel) {
        hooks.hideDisplayPanel();
    }
    if (hooks.hideShotPanel) {
        hooks.hideShotPanel();
    }
    if (hooks.hideTreePanel) {
        hooks.hideTreePanel();
    }
    if (hooks.resetTreeDom) {
        hooks.resetTreeDom();
    }
    if (hooks.clearMeasure) {
        hooks.clearMeasure();
    }
    setHint(DEFAULT_HINT);
    S.sectionCuts = [];
    S.sectionActiveId = null;
    S.sectionCutSeq = 0;
    S.sectionPreviewing = false;
    S.explodeAmount = 0;
    S.explodeStyle = 'radial';
    S.explodeCenterId = null;
    S.explodeEven = true;
    S.explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
    S.alignedView = null;
    if (hooks.showViewRoll) {
        hooks.showViewRoll(false);
    }
    if (S.stageEl) {
        S.stageEl.classList.remove('is-placing-pivot');
        S.stageEl.classList.remove('is-measuring');
    }
    setToggleActive('measure', false);
    setToggleActive('ortho', false);
    setToggleActive('grid', false);
    setToggleActive('axes', false);
    setToggleActive('solid', true);
    setToggleActive('wireframe', false);
    setToggleActive('xray', false);
    setToggleActive('place-pivot', false);
    setToggleActive('section', false);
    setToggleActive('explode', false);
    setGroupActive('display', false);
    setGroupActive('view', false);
    setGroupActive('assist', false);
    setGroupActive('tools', false);
}

async function mount(container, opts) {
    dispose();
    S.stageEl = container;
    S.pageRoot = container.closest('.cad-preview-page') || container;
    S.canvasEl = container.querySelector('canvas') || document.createElement('canvas');
    if (!S.canvasEl.parentNode) {
        S.canvasEl.className = 'cad-preview-canvas';
        container.appendChild(S.canvasEl);
    }
    if (!S.pageRoot.__cadToolbarBound) {
        S.pageRoot.addEventListener('click', hooks.onToolbarClick);
        S.pageRoot.addEventListener('click', hooks.onTreeClick);
        S.pageRoot.addEventListener('input', hooks.onLightInput);
        S.pageRoot.addEventListener('change', hooks.onLightInput);
        S.pageRoot.addEventListener('input', hooks.onSectionInput);
        S.pageRoot.addEventListener('change', hooks.onSectionInput);
        S.pageRoot.addEventListener('input', hooks.onExplodeInput);
        S.pageRoot.addEventListener('change', hooks.onExplodeInput);
        S.pageRoot.addEventListener('input', hooks.onDisplayInput);
        S.pageRoot.addEventListener('change', hooks.onDisplayInput);
        S.pageRoot.addEventListener('input', hooks.onTreeSearchInput);
        S.pageRoot.addEventListener('change', hooks.onTreeSearchInput);
        S.pageRoot.addEventListener('keydown', hooks.onTreeSearchKeydown);
        document.addEventListener('keydown', hooks.onPivotKeydown);
        S.pageRoot.__cadToolbarBound = true;
    }
    if (S.canvasEl && !S.canvasEl.__cadPickBound) {
        S.canvasEl.addEventListener('pointerdown', hooks.onCanvasPointerDown);
        S.canvasEl.addEventListener('pointerup', hooks.onCanvasPointerUp);
        S.canvasEl.addEventListener('pointermove', hooks.onCanvasPointerMove);
        S.canvasEl.addEventListener('pointerleave', hooks.hideMeasurePreview);
        S.canvasEl.addEventListener('dblclick', hooks.onCanvasDblClick);
        S.canvasEl.__cadPickBound = true;
    }
    setStatus('正在加载 3D 引擎…');
    try {
        await hooks.loadModel(opts);
    } catch (err) {
        setError(err.message || '预览失败');
    }
}

function boot() {
    var stage = document.getElementById('cad-preview-page-stage');
    if (!stage) {
        return;
    }
    mount(stage, {
        url: stage.getAttribute('data-cad-url'),
        name: stage.getAttribute('data-cad-name') || '3D 预览',
        ext: stage.getAttribute('data-cad-ext') || '',
        size: Number(stage.getAttribute('data-cad-size') || 0),
    });
}

window.CadPreview = {
    mount: mount,
    dispose: dispose,
};

window.addEventListener('pagehide', function () {
    dispose();
});

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}

export { dispose, mount, boot };
