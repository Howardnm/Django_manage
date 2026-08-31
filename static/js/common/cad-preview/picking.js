/**
 * CAD 预览 — 画布拾取
 */
import { THREE, S, hooks, findCadNode, getModelBox, nodeCenter, objectIsShown } from './core.js';

function onCanvasPointerMove(ev) {
    if (!S.measuring || S.placingPivot) {
        hooks.hideMeasurePreview();
        return;
    }
    var hit = raycastModel(ev);
    if (!hit) {
        hooks.hideMeasurePreview();
        return;
    }
    var snap = hooks.snapMeasureHit(hit);
    hooks.showMeasurePreview(snap.point, snap.snapped);
}

function onCanvasPointerDown(ev) {
    if (ev.button !== 0) {
        S.pointerDownPos = null;
        return;
    }
    S.pointerDownPos = { x: ev.clientX, y: ev.clientY };
}

function onCanvasPointerUp(ev) {
    if (!S.pointerDownPos || ev.button !== 0) {
        S.pointerDownPos = null;
        return;
    }
    var dx = ev.clientX - S.pointerDownPos.x;
    var dy = ev.clientY - S.pointerDownPos.y;
    S.pointerDownPos = null;
    if (dx * dx + dy * dy > 16) {
        return;
    }
    pickCanvas(ev);
}

function onCanvasDblClick(ev) {
    if (ev.button != null && ev.button !== 0) {
        return;
    }
    ev.preventDefault();
    var hit = raycastModel(ev);
    if (!hit) {
        return;
    }
    var id = findCadNode(hit.object);
    if (id) {
        hooks.selectNode(id);
        var center = nodeCenter(id);
        if (center) {
            hooks.setOrbitTarget(center, true);
        }
    }
}

function collectPickTargets() {
    var targets = [];
    if (!S.modelGroup) {
        return targets;
    }
    S.modelGroup.traverse(function (obj) {
        var role = obj.userData && obj.userData.cadRole;
        if (S.displayMode === 'wireframe') {
            if (obj.isLineSegments && objectIsShown(obj)) {
                targets.push(obj);
            }
        } else if (role === 'solid' && objectIsShown(obj)) {
            targets.push(obj);
        }
    });
    return targets;
}

function raycastModel(ev) {
    if (!S.renderer || !S.camera || !S.modelGroup || !S.canvasEl || !THREE) {
        return null;
    }
    var rect = S.canvasEl.getBoundingClientRect();
    if (!rect.width || !rect.height) {
        return null;
    }
    var x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    var y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    var raycaster = new THREE.Raycaster();
    var info = getModelBox(false);
    var lineThresh = hooks.measureSnapRadius ? hooks.measureSnapRadius() : 0.02;
    if (info) {
        lineThresh = Math.max(lineThresh, info.maxDim * 0.0015);
    }
    raycaster.params.Line = { threshold: Math.max(lineThresh, 0.02) };
    raycaster.setFromCamera(new THREE.Vector2(x, y), S.camera);
    var hits = raycaster.intersectObjects(collectPickTargets(), false);
    if (!(hooks.isSectionOn && hooks.isSectionOn())) {
        return hits.length ? hits[0] : null;
    }
    for (var i = 0; i < hits.length; i++) {
        var hitObj = hits[i].object;
        var pt = hits[i].point;
        var planes = hooks.objectClipPlanes ? hooks.objectClipPlanes(hitObj) : [];
        var keep = true;
        for (var p = 0; p < planes.length; p++) {
            if (planes[p].distanceToPoint(pt) < -1e-6) {
                keep = false;
                break;
            }
        }
        if (keep) {
            return hits[i];
        }
    }
    return null;
}

function pickCanvas(ev) {
    var hit = raycastModel(ev);
    if (S.placingPivot) {
        if (hit) {
            hooks.setOrbitTarget(hit.point.clone(), true);
        }
        hooks.setPlacingPivot(false);
        if (hit) {
            var id = findCadNode(hit.object);
            if (id) {
                hooks.selectNode(id);
            }
        }
        return;
    }
    if (S.measuring) {
        if (hit) {
            var snap = hooks.snapMeasureHit(hit);
            hooks.addMeasurePoint(snap.point, snap.mesh || hit.object);
            hooks.hideMeasurePreview();
        } else if (S.measurePending) {
            S.measurePending = null;
            hooks.rebuildMeasureGeom();
            hooks.syncMeasureUi();
        }
        return;
    }
    if (!hit) {
        if (!(ev.ctrlKey || ev.metaKey)) {
            hooks.selectNode(null);
        }
        return;
    }
    var nodeId = findCadNode(hit.object);
    if (nodeId) {
        hooks.selectNode(nodeId, { toggle: !!(ev.ctrlKey || ev.metaKey) });
    }
}


hooks.onCanvasPointerMove = onCanvasPointerMove;
hooks.onCanvasPointerDown = onCanvasPointerDown;
hooks.onCanvasPointerUp = onCanvasPointerUp;
hooks.onCanvasDblClick = onCanvasDblClick;
hooks.collectPickTargets = collectPickTargets;
hooks.raycastModel = raycastModel;
hooks.pickCanvas = pickCanvas;
export { onCanvasPointerMove, onCanvasPointerDown, onCanvasPointerUp, onCanvasDblClick, collectPickTargets, raycastModel, pickCanvas };
