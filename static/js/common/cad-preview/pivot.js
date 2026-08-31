/**
 * CAD 预览 — 旋转中心
 */
import { THREE, S, hooks, PIVOT_HOLD_MS, getModelBox, nodeCenter, setToggleActive } from './core.js';

function setOrbitTarget(point, keepDistance) {
    if (!S.controls || !S.camera || !point) {
        return;
    }
    if (keepDistance) {
        var offset = S.camera.position.clone().sub(S.controls.target);
        S.controls.target.copy(point);
        S.camera.position.copy(point).add(offset);
    } else {
        S.controls.target.copy(point);
    }
    S.camera.lookAt(S.controls.target);
    S.controls.update();
    ensurePivotHelper();
    if (S.pivotHelper) {
        S.pivotHelper.position.copy(point);
        S.pivotHelper.quaternion.identity();
    }
    showPivotHelper(true);
    S.pivotHideAt = Date.now() + PIVOT_HOLD_MS * 1.6;
}

function ensurePivotHelper() {
    if (S.pivotHelper || !S.scene || !THREE) {
        return;
    }
    var group = new THREE.Group();
    group.name = 'cad-pivot';
    var mat = new THREE.LineBasicMaterial({
        color: 0xe67e22,
        depthTest: false,
        transparent: true,
        opacity: 0.95,
    });
    var axes = [
        [0, 1, 0, 0, -1, 0],
        [1, 0, 0, -1, 0, 0],
        [0, 0, 1, 0, 0, -1],
    ];
    axes.forEach(function (coords) {
        var geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(coords, 3));
        var line = new THREE.Line(geo, mat);
        line.renderOrder = 999;
        group.add(line);
    });
    var ringGeo = new THREE.RingGeometry(0.28, 0.42, 24);
    var ringMat = new THREE.MeshBasicMaterial({
        color: 0xe67e22,
        side: THREE.DoubleSide,
        depthTest: false,
        transparent: true,
        opacity: 0.9,
    });
    var ring = new THREE.Mesh(ringGeo, ringMat);
    ring.renderOrder = 999;
    ring.userData.cadRole = 'pivot-ring';
    ring.raycast = function () {};
    group.add(ring);
    group.userData.pivotRing = ring;
    group.visible = false;
    S.scene.add(group);
    S.pivotHelper = group;
    syncPivotHelper();
}

function showPivotHelper(on) {
    ensurePivotHelper();
    if (S.pivotHelper) {
        S.pivotHelper.visible = !!on;
    }
}

function pivotHelperSize() {
    var origin = S.controls && S.controls.target ? S.controls.target : null;
    var px = hooks.measureWorldPerPixel(origin);
    var info = getModelBox(false);
    var maxDim = info ? info.maxDim : 50;
    return Math.max(px * 20, maxDim * 0.0004, 1e-4);
}

function pivotRingNormal() {
    if (S.alignedView === 'top' || S.alignedView === 'bottom') {
        return new THREE.Vector3(0, 1, 0);
    }
    return new THREE.Vector3(0, 0, 1);
}

function posePivotRing(ring) {
    if (!ring || !THREE) {
        return;
    }
    ring.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 0, 1),
        pivotRingNormal()
    );
}

function syncPivotHelper() {
    if (!S.pivotHelper || !S.controls) {
        return;
    }
    S.pivotHelper.position.copy(S.controls.target);
    var size = pivotHelperSize();
    S.pivotHelper.scale.set(size, size, size);
    posePivotRing(S.pivotHelper.userData.pivotRing);
    if (S.pivotInteracting || S.placingPivot) {
        S.pivotHelper.visible = true;
        return;
    }
    if (S.pivotHideAt && Date.now() < S.pivotHideAt) {
        S.pivotHelper.visible = true;
        return;
    }
    S.pivotHelper.visible = false;
}

function setPlacingPivot(on) {
    S.placingPivot = !!on;
    if (S.stageEl) {
        S.stageEl.classList.toggle('is-placing-pivot', S.placingPivot);
    }
    setToggleActive('place-pivot', S.placingPivot);
    if (S.placingPivot) {
        if (S.measuring) {
            hooks.hideMeasurePanel();
        }
        showPivotHelper(true);
    }
}

function onPivotKeydown(ev) {
    if (ev.key !== 'Escape') {
        return;
    }
    if (ev.target && ev.target.closest && ev.target.closest('[data-cad-tree-search]')) {
        return;
    }
    if (S.placingPivot) {
        setPlacingPivot(false);
        return;
    }
    if (S.measuring) {
        hooks.hideMeasurePanel();
    }
}

function pivotToSelected() {
    if (!S.selectedNodeId) {
        return;
    }
    var center = nodeCenter(S.selectedNodeId);
    if (center) {
        setOrbitTarget(center, true);
        setPlacingPivot(false);
    }
}


hooks.setOrbitTarget = setOrbitTarget;
hooks.ensurePivotHelper = ensurePivotHelper;
hooks.showPivotHelper = showPivotHelper;
hooks.pivotHelperSize = pivotHelperSize;
hooks.pivotRingNormal = pivotRingNormal;
hooks.posePivotRing = posePivotRing;
hooks.syncPivotHelper = syncPivotHelper;
hooks.setPlacingPivot = setPlacingPivot;
hooks.onPivotKeydown = onPivotKeydown;
hooks.pivotToSelected = pivotToSelected;
export { setOrbitTarget, ensurePivotHelper, showPivotHelper, pivotHelperSize, pivotRingNormal, posePivotRing, syncPivotHelper, setPlacingPivot, onPivotKeydown, pivotToSelected };
