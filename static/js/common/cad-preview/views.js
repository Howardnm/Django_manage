/**
 * CAD 预览 — 六面视图 / 正交 / 网格轴线
 */
import { THREE, S, hooks, ALIGNED_VIEWS, applyCameraClip, applyOrthoFrustum, bindControls, disposeHelper, getFitDistance, getModelBox, setToggleActive } from './core.js';

function normalizeViewKind(kind) {
    if (kind === 'side') {
        return 'right';
    }
    return kind || 'iso';
}

function viewRollEl() {
    return S.stageEl && S.stageEl.querySelector('[data-cad-view-roll]');
}

function showViewRoll(on) {
    var el = viewRollEl();
    if (el) {
        el.classList.toggle('is-hidden', !on);
    }
}

function clearAlignedView() {
    S.alignedView = null;
    showViewRoll(false);
}

function applyViewTransform(kind, info) {
    var center = info.center;
    var dist = getFitDistance(info.maxDim);
    applyCameraClip(info.maxDim);
    kind = normalizeViewKind(kind);
    var preset = ALIGNED_VIEWS[kind];
    if (preset) {
        S.camera.up.fromArray(preset.up);
        S.camera.position.set(
            center.x + preset.offset[0] * dist,
            center.y + preset.offset[1] * dist,
            center.z + preset.offset[2] * dist
        );
        S.alignedView = kind;
        showViewRoll(true);
    } else {
        S.camera.up.set(0, 0, 1);
        S.camera.position.set(center.x + dist, center.y + dist * 0.8, center.z + dist * 0.55);
        clearAlignedView();
    }
    if (S.camera.isOrthographicCamera) {
        S.orthoHalf = info.maxDim * 0.9;
        applyOrthoFrustum(S.stageEl && S.stageEl.clientWidth, S.stageEl && S.stageEl.clientHeight);
    } else {
        S.camera.updateProjectionMatrix();
    }
    bindControls(S.camera, S.canvasEl);
    S.controls.target.copy(center);
    S.camera.lookAt(center);
    S.controls.update();
}

function rollAlignedView(deg) {
    if (!S.alignedView || !S.camera || !S.controls || !THREE) {
        return;
    }
    var target = S.controls.target.clone();
    var viewDir = target.clone().sub(S.camera.position);
    if (viewDir.lengthSq() < 1e-12) {
        return;
    }
    viewDir.normalize();
    // 画面顺时针 = 相机绕视线逆时针（屏幕坐标 y 向下）。
    var angle = -THREE.MathUtils.degToRad(deg);
    S.camera.up.applyQuaternion(new THREE.Quaternion().setFromAxisAngle(viewDir, angle));
    S.camera.lookAt(target);
    bindControls(S.camera, S.canvasEl);
    S.controls.target.copy(target);
    S.controls.update();
    showViewRoll(true);
}

function fitToView() {
    setPresetView('iso');
}

function setPresetView(kind) {
    if (!S.modelGroup || !S.camera || !S.controls || !THREE) {
        return;
    }
    var info = getModelBox(true) || getModelBox(false);
    if (!info) {
        return;
    }
    applyViewTransform(kind || 'iso', info);
    syncHelpers(info);
}

function setOrtho(on) {
    if (!THREE || !S.camera || !S.controls || !S.stageEl) {
        return;
    }
    var w = S.stageEl.clientWidth || 800;
    var h = S.stageEl.clientHeight || 480;
    var pos = S.camera.position.clone();
    var target = S.controls.target.clone();
    var up = S.camera.up.clone();
    var info = getModelBox(true) || getModelBox(false);
    var maxDim = info ? info.maxDim : 100;
    S.orthoOn = !!on;
    if (S.orthoOn) {
        S.orthoHalf = maxDim * 0.9;
        S.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, Math.max(maxDim / 1000, 0.01), maxDim * 100);
        applyOrthoFrustum(w, h);
    } else {
        S.camera = new THREE.PerspectiveCamera(45, w / Math.max(h, 1), Math.max(maxDim / 1000, 0.01), maxDim * 100);
        S.camera.updateProjectionMatrix();
    }
    S.camera.up.copy(up);
    S.camera.position.copy(pos);
    S.camera.lookAt(target);
    bindControls(S.camera, S.canvasEl);
    S.controls.target.copy(target);
    S.controls.update();
    setToggleActive('ortho', S.orthoOn);
}

function syncHelpers(info) {
    info = info || getModelBox(false);
    if (!info || !S.scene || !THREE) {
        return;
    }
    if (S.gridOn) {
        rebuildGrid(info);
    }
    if (S.axesOn) {
        rebuildAxes(info);
    }
}

function rebuildGrid(info) {
    disposeHelper(S.gridHelper);
    var size = Math.max(info.maxDim * 2.2, 1);
    var divisions = 20;
    S.gridHelper = new THREE.GridHelper(
        size,
        divisions,
        S.darkCanvas ? 0x5b6778 : 0xb0b8c4,
        S.darkCanvas ? 0x2f3948 : 0xd8dde5
    );
    S.gridHelper.rotation.x = Math.PI / 2;
    S.gridHelper.position.set(info.center.x, info.center.y, info.box.min.z);
    S.scene.add(S.gridHelper);
}

function rebuildAxes(info) {
    disposeHelper(S.axesHelper);
    S.axesHelper = new THREE.AxesHelper(info.maxDim * 0.28);
    S.axesHelper.position.copy(info.box.min);
    S.scene.add(S.axesHelper);
}

function setGrid(on) {
    S.gridOn = !!on;
    if (S.gridOn) {
        syncHelpers();
    } else {
        disposeHelper(S.gridHelper);
        S.gridHelper = null;
    }
    setToggleActive('grid', S.gridOn);
}

function setAxes(on) {
    S.axesOn = !!on;
    if (S.axesOn) {
        syncHelpers();
    } else {
        disposeHelper(S.axesHelper);
        S.axesHelper = null;
    }
    setToggleActive('axes', S.axesOn);
}


hooks.normalizeViewKind = normalizeViewKind;
hooks.viewRollEl = viewRollEl;
hooks.showViewRoll = showViewRoll;
hooks.clearAlignedView = clearAlignedView;
hooks.applyViewTransform = applyViewTransform;
hooks.rollAlignedView = rollAlignedView;
hooks.fitToView = fitToView;
hooks.setPresetView = setPresetView;
hooks.setOrtho = setOrtho;
hooks.syncHelpers = syncHelpers;
hooks.rebuildGrid = rebuildGrid;
hooks.rebuildAxes = rebuildAxes;
hooks.setGrid = setGrid;
hooks.setAxes = setAxes;
export { normalizeViewKind, viewRollEl, showViewRoll, clearAlignedView, applyViewTransform, rollAlignedView, fitToView, setPresetView, setOrtho, syncHelpers, rebuildGrid, rebuildAxes, setGrid, setAxes };
