/**
 * CAD 预览 — 量测
 */
import { THREE, S, hooks, DEFAULT_HINT, MEASURE_COLOR, MEASURE_HINT, cadGroupIsShown, escapeHtml, getModelBox, setHint, setToggleActive } from './core.js';

function measurePanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-measure-panel]');
}

function toggleMeasurePanel() {
    var panel = measurePanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showMeasurePanel();
    } else {
        hideMeasurePanel();
    }
}

function showMeasurePanel() {
    hooks.hideLightPanel();
    hooks.hideSectionPanel();
    hooks.hideExplodePanel();
    hooks.hideDisplayPanel();
    hooks.hideShotPanel();
    var panel = measurePanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    enterMeasuring();
    syncMeasureUi();
}

function hideMeasurePanel() {
    var panel = measurePanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    exitMeasuring();
}

function formatMeasure(n) {
    var abs = Math.abs(n);
    var text;
    if (abs >= 1e5 || (n !== 0 && abs < 1e-2)) {
        text = n.toExponential(2);
    } else {
        text = n.toFixed(2);
    }
    return text + ' mm';
}

function enterMeasuring() {
    if (S.placingPivot) {
        hooks.setPlacingPivot(false);
    }
    S.measuring = true;
    if (S.stageEl) {
        S.stageEl.classList.toggle('is-measuring', true);
    }
    setHint(MEASURE_HINT);
    setToggleActive('measure', true);
}

function exitMeasuring() {
    S.measuring = false;
    hideMeasurePreview();
    if (S.stageEl) {
        S.stageEl.classList.remove('is-measuring');
    }
    setHint(DEFAULT_HINT);
    setToggleActive('measure', hooks.isPanelOpen(measurePanel()) || hasMeasureGeom());
}

function ensureMeasureGroup() {
    if (!S.scene || !THREE) {
        return null;
    }
    if (!S.measureGroup) {
        S.measureGroup = new THREE.Group();
        S.measureGroup.name = '__cad_measure';
        S.measureGroup.renderOrder = 10000;
        S.scene.add(S.measureGroup);
    }
    return S.measureGroup;
}

function measureWorldPerPixel(atPoint) {
    if (!S.camera || !THREE) {
        return 0.2;
    }
    var h = (S.stageEl && S.stageEl.clientHeight) || (S.canvasEl && S.canvasEl.clientHeight) || 480;
    if (h < 1) {
        h = 480;
    }
    if (S.camera.isOrthographicCamera) {
        return Math.abs(S.camera.top - S.camera.bottom) / h;
    }
    var origin = atPoint
        ? atPoint.clone()
        : (S.controls && S.controls.target ? S.controls.target.clone() : S.camera.position.clone());
    var dist = origin.distanceTo(S.camera.position);
    var fov = (S.camera.fov || 45) * Math.PI / 180;
    return 2 * dist * Math.tan(fov / 2) / h;
}

function measureMarkerSize(atPoint) {
    var px = measureWorldPerPixel(atPoint);
    var info = getModelBox(false);
    var maxDim = info ? info.maxDim : 50;
    return Math.max(px * 14, maxDim * 0.0004, 1e-4);
}

function measureSnapRadius(atPoint) {
    var px = measureWorldPerPixel(atPoint);
    var info = getModelBox(false);
    var maxDim = info ? info.maxDim : 50;
    return Math.max(px * 12, maxDim * 0.0003, 1e-4);
}

function measureLineMaterial(color) {
    var mat = new THREE.LineBasicMaterial({
        color: color == null ? MEASURE_COLOR : color,
        depthTest: false,
        depthWrite: false,
        transparent: true,
        opacity: 1,
    });
    mat.clippingPlanes = [];
    mat.clipShadows = false;
    return mat;
}

function addMeasureLine(group, a, b, mat) {
    var line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([a, b]),
        mat
    );
    line.renderOrder = 10000;
    line.frustumCulled = false;
    line.raycast = function () {};
    group.add(line);
    return line;
}

function setMeasureMarkColor(root, color) {
    if (!root) {
        return;
    }
    root.traverse(function (obj) {
        if (obj.material && obj.material.color) {
            obj.material.color.setHex(color);
        }
    });
}

function makeMeasureMark(color) {
    var group = new THREE.Group();
    group.renderOrder = 10000;
    var mat = measureLineMaterial(color);
    addMeasureLine(group, new THREE.Vector3(-1, 0, 0), new THREE.Vector3(1, 0, 0), mat);
    addMeasureLine(group, new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 1, 0), mat);
    addMeasureLine(group, new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, 0, 1), mat);
    return group;
}

function addMeasureArrow(group, from, to, size, mat) {
    var dir = to.clone().sub(from);
    if (dir.lengthSq() < 1e-12) {
        return;
    }
    dir.normalize();
    var back = to.clone().addScaledVector(dir, -size);
    var up = Math.abs(dir.z) < 0.92 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0);
    var side = new THREE.Vector3().crossVectors(dir, up);
    if (side.lengthSq() < 1e-12) {
        side.set(1, 0, 0);
    }
    side.normalize().multiplyScalar(size * 0.42);
    addMeasureLine(group, to, back.clone().add(side), mat);
    addMeasureLine(group, to, back.clone().sub(side), mat);
}

function clearMeasureChildren(group) {
    if (!group) {
        return;
    }
    var seen = [];
    while (group.children.length) {
        var child = group.children[0];
        group.remove(child);
        child.traverse(function (obj) {
            if (obj.geometry && obj.geometry.dispose) {
                obj.geometry.dispose();
            }
            var mats = obj.material
                ? (Array.isArray(obj.material) ? obj.material : [obj.material])
                : [];
            mats.forEach(function (m) {
                if (m && m.dispose && seen.indexOf(m) === -1) {
                    seen.push(m);
                    m.dispose();
                }
            });
        });
    }
}

function measureWorldDistance(seg) {
    if (!seg) {
        return 0;
    }
    var a = worldMeasurePoint(seg.a);
    var b = worldMeasurePoint(seg.b);
    return (a && b) ? a.distanceTo(b) : 0;
}

function worldMeasurePoint(rec) {
    if (!rec || !rec.local) {
        return rec && rec.point ? rec.point.clone() : null;
    }
    if (rec.mesh && rec.mesh.parent) {
        rec.mesh.updateWorldMatrix(true, false);
        return rec.local.clone().applyMatrix4(rec.mesh.matrixWorld);
    }
    return rec.local.clone();
}

function measureRecAlive(rec) {
    return !!(rec && rec.local && (!rec.mesh || rec.mesh.parent));
}

function makeMeasureRec(point, mesh) {
    if (!point || !THREE) {
        return null;
    }
    if (mesh) {
        mesh.updateWorldMatrix(true, false);
        return {
            local: point.clone().applyMatrix4(mesh.matrixWorld.clone().invert()),
            mesh: mesh,
        };
    }
    return { local: point.clone(), mesh: null };
}

function pruneMeasure() {
    if (S.measurePending && !measureRecAlive(S.measurePending)) {
        S.measurePending = null;
    }
    S.measureSegments = S.measureSegments.filter(function (seg) {
        return measureRecAlive(seg.a) && measureRecAlive(seg.b);
    });
}

function worldVertex(obj, attr, index) {
    return new THREE.Vector3().fromBufferAttribute(attr, index).applyMatrix4(obj.matrixWorld);
}

function hitCandidateVertices(hit) {
    var obj = hit && hit.object;
    var geom = obj && obj.geometry;
    var attr = geom && geom.attributes && geom.attributes.position;
    if (!attr || !THREE) {
        return [];
    }
    obj.updateWorldMatrix(true, false);
    var out = [];
    if (hit.face) {
        out.push(worldVertex(obj, attr, hit.face.a));
        out.push(worldVertex(obj, attr, hit.face.b));
        out.push(worldVertex(obj, attr, hit.face.c));
        return out;
    }
    if (hit.index == null) {
        return out;
    }
    var idx = geom.index;
    var i0;
    var i1;
    if (idx) {
        i0 = idx.getX(hit.index);
        i1 = idx.getX(Math.min(hit.index + 1, idx.count - 1));
    } else {
        i0 = hit.index;
        i1 = Math.min(hit.index + 1, attr.count - 1);
    }
    out.push(worldVertex(obj, attr, i0));
    if (i1 !== i0) {
        out.push(worldVertex(obj, attr, i1));
    }
    return out;
}

function snapMeasureHit(hit) {
    var point = hit && hit.point ? hit.point.clone() : null;
    if (!point) {
        return { point: null, snapped: false, mesh: null };
    }
    var mesh = resolveMeasureMesh(hit.object);
    var radius = measureSnapRadius(point);
    var vertBest = null;
    var vertDist = radius;
    hitCandidateVertices(hit).forEach(function (v) {
        var d = v.distanceTo(point);
        if (d < vertDist) {
            vertDist = d;
            vertBest = v;
        }
    });
    if (vertBest) {
        return { point: vertBest, snapped: true, mesh: mesh };
    }
    return { point: point, snapped: false, mesh: mesh };
}

function resolveMeasureMesh(obj) {
    var cur = obj;
    while (cur) {
        var role = cur.userData && cur.userData.cadRole;
        if (role === 'solid' && cur.isMesh) {
            return cur;
        }
        if (role === 'edges' || cur.isLineSegments) {
            var host = role === 'edges' ? cur.parent : (cur.parent && cur.parent.parent);
            var found = findSolidInGroup(host || cur.parent);
            if (found) {
                return found;
            }
        }
        cur = cur.parent;
    }
    return obj || null;
}

function findSolidInGroup(group) {
    if (!group) {
        return null;
    }
    var found = null;
    (group.children || []).forEach(function (ch) {
        if (found) {
            return;
        }
        if (ch.isMesh && ch.userData && ch.userData.cadRole === 'solid') {
            found = ch;
        }
    });
    return found;
}

function hideMeasurePreview() {
    if (S.measurePreview) {
        S.measurePreview.visible = false;
    }
}

function showMeasurePreview(point, snapped) {
    if (!point || !THREE || !S.scene) {
        hideMeasurePreview();
        return;
    }
    if (!S.measurePreview) {
        S.measurePreview = makeMeasureMark(MEASURE_COLOR);
        S.measurePreview.name = '__cad_measure_preview';
        S.measurePreview.renderOrder = 10000;
        S.scene.add(S.measurePreview);
    }
    S.measurePreview.position.copy(point);
    S.measurePreview.userData.cadSnapped = !!snapped;
    S.measurePreview.scale.setScalar(measureMarkerSize(point) * (snapped ? 1 : 0.7));
    setMeasureMarkColor(S.measurePreview, snapped ? 0xe67e22 : MEASURE_COLOR);
    S.measurePreview.visible = true;
}

function rebuildMeasureGeom() {
    var group = ensureMeasureGroup();
    if (!group || !THREE) {
        return;
    }
    pruneMeasure();
    clearMeasureChildren(group);
    var size = measureMarkerSize();
    var mat = measureLineMaterial();
    function addMark(p) {
        var mark = makeMeasureMark(MEASURE_COLOR);
        mark.position.copy(p);
        mark.scale.setScalar(size);
        mark.userData.cadMeasureMark = true;
        group.add(mark);
    }
    function addSegment(a, b) {
        addMark(a);
        addMark(b);
        addMeasureLine(group, a, b, mat);
        var arrow = Math.min(size * 1.35, a.distanceTo(b) * 0.22);
        if (arrow > 1e-4) {
            addMeasureArrow(group, a, b, arrow, mat);
            addMeasureArrow(group, b, a, arrow, mat);
        }
    }
    S.measureSegments.forEach(function (seg) {
        var a = worldMeasurePoint(seg.a);
        var b = worldMeasurePoint(seg.b);
        if (a && b) {
            addSegment(a, b);
        }
    });
    if (S.measurePending) {
        var pendingPt = worldMeasurePoint(S.measurePending);
        if (pendingPt) {
            addMark(pendingPt);
        }
    }
    updateMeasureLabel();
}

function hasMeasureGeom() {
    return S.measureSegments.length > 0 || !!S.measurePending;
}

function clearMeasure() {
    S.measureSegments = [];
    S.measurePending = null;
    hideMeasurePreview();
    rebuildMeasureGeom();
    syncMeasureUi();
    if (!S.measuring) {
        setToggleActive('measure', hooks.isPanelOpen(measurePanel()));
    }
}

function removeMeasureSegment(index) {
    if (!Number.isInteger(index) || index < 0 || index >= S.measureSegments.length) {
        return;
    }
    S.measureSegments.splice(index, 1);
    rebuildMeasureGeom();
    syncMeasureUi();
    if (!S.measuring && !hasMeasureGeom()) {
        setToggleActive('measure', hooks.isPanelOpen(measurePanel()));
    }
}

function addMeasurePoint(point, mesh) {
    var rec = makeMeasureRec(point, mesh);
    if (!rec) {
        return;
    }
    if (!S.measurePending) {
        S.measurePending = rec;
    } else {
        S.measureSegments.push({ a: S.measurePending, b: rec });
        S.measurePending = null;
    }
    rebuildMeasureGeom();
    syncMeasureUi();
    setToggleActive('measure', true);
}

function selectedNodeBox() {
    if (!S.selectedNodeId || !S.nodeMap[S.selectedNodeId] || !THREE) {
        return null;
    }
    var rec = S.nodeMap[S.selectedNodeId];
    rec.object.updateWorldMatrix(true, true);
    var box = new THREE.Box3();
    var has = false;
    rec.object.traverse(function (obj) {
        if (!obj.isMesh || !obj.userData || obj.userData.cadRole !== 'solid') {
            return;
        }
        if (!cadGroupIsShown(obj)) {
            return;
        }
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
    if (!has) {
        return null;
    }
    var size = box.getSize(new THREE.Vector3());
    return {
        name: rec.name || S.selectedNodeId,
        size: size,
        diagonal: size.length(),
    };
}

function syncMeasureUi() {
    if (!S.pageRoot) {
        return;
    }
    var distEl = S.pageRoot.querySelector('[data-cad-measure="distance"]');
    var n = S.measureSegments.length;
    if (distEl) {
        if (S.measurePending) {
            distEl.textContent = n ? ('点第二点（已 ' + n + ' 条）') : '点第二点';
        } else if (!n) {
            distEl.textContent = S.measuring ? '点第一点' : '—';
        } else if (n === 1) {
            distEl.textContent = formatMeasure(measureWorldDistance(S.measureSegments[0]));
        } else {
            distEl.textContent = formatMeasure(measureWorldDistance(S.measureSegments[n - 1])) + '（共 ' + n + ' 条）';
        }
    }
    var listEl = S.pageRoot.querySelector('[data-cad-measure="list"]');
    if (listEl) {
        if (!n) {
            listEl.innerHTML = '';
            listEl.classList.add('is-hidden');
        } else {
            listEl.innerHTML = S.measureSegments.map(function (seg, i) {
                return '<div class="cad-preview-measure-item">' +
                    '<span>' + (i + 1) + '. ' + escapeHtml(formatMeasure(measureWorldDistance(seg))) + '</span>' +
                    '<button type="button" class="btn btn-sm btn-ghost-secondary cad-preview-measure-remove"' +
                    ' data-cad-action="measure-remove" data-cad-measure-index="' + i + '" title="删除此标注">×</button>' +
                    '</div>';
            }).join('');
            listEl.classList.remove('is-hidden');
        }
    }
    var box = selectedNodeBox();
    var nameEl = S.pageRoot.querySelector('[data-cad-measure="name"]');
    var sizeEl = S.pageRoot.querySelector('[data-cad-measure="size"]');
    if (nameEl) {
        nameEl.textContent = box ? box.name : '（无）';
    }
    if (sizeEl) {
        if (box) {
            sizeEl.textContent = 'X ' + formatMeasure(box.size.x) +
                '  Y ' + formatMeasure(box.size.y) +
                '  Z ' + formatMeasure(box.size.z) +
                '\n对角 ' + formatMeasure(box.diagonal);
        } else {
            sizeEl.textContent = S.measuring
                ? '在结构树或退出量测后点选零件'
                : '点选零件查看包围盒';
        }
    }
    updateMeasureLabel();
}

function updateMeasureLabel() {
    if (!S.pageRoot || !S.camera || !S.canvasEl || !THREE) {
        return;
    }
    var labels = S.pageRoot.querySelectorAll('[data-cad-measure-label]');
    if (!labels.length) {
        return;
    }
    var parent = labels[0].parentNode;
    var n = S.measureSegments.length;
    while (labels.length < n) {
        parent.appendChild(labels[0].cloneNode(true));
        labels = S.pageRoot.querySelectorAll('[data-cad-measure-label]');
    }
    var rect = S.canvasEl.getBoundingClientRect();
    var i;
    for (i = 0; i < labels.length; i++) {
        var el = labels[i];
        if (i >= n) {
            el.classList.add('is-hidden');
            continue;
        }
        var a = worldMeasurePoint(S.measureSegments[i].a);
        var b = worldMeasurePoint(S.measureSegments[i].b);
        if (!a || !b) {
            el.classList.add('is-hidden');
            continue;
        }
        var mid = a.clone().add(b).multiplyScalar(0.5);
        var ndc = mid.project(S.camera);
        var x = (ndc.x * 0.5 + 0.5) * rect.width;
        var y = (-ndc.y * 0.5 + 0.5) * rect.height;
        if (ndc.z > 1 || ndc.z < -1 || x < 0 || y < 0 || x > rect.width || y > rect.height) {
            el.classList.add('is-hidden');
            continue;
        }
        el.textContent = formatMeasure(a.distanceTo(b));
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        el.classList.remove('is-hidden');
    }
    syncMeasureMarkScale();
}

function syncMeasureMarkScale() {
    if (S.measurePreview && S.measurePreview.visible) {
        var previewPt = S.measurePreview.position;
        var snapped = !!(S.measurePreview.userData && S.measurePreview.userData.cadSnapped);
        S.measurePreview.scale.setScalar(measureMarkerSize(previewPt) * (snapped ? 1 : 0.7));
    }
    if (!S.measureGroup) {
        return;
    }
    S.measureGroup.traverse(function (obj) {
        if (obj.userData && obj.userData.cadMeasureMark) {
            obj.scale.setScalar(measureMarkerSize(obj.position));
        }
    });
}


hooks.measurePanel = measurePanel;
hooks.toggleMeasurePanel = toggleMeasurePanel;
hooks.showMeasurePanel = showMeasurePanel;
hooks.hideMeasurePanel = hideMeasurePanel;
hooks.formatMeasure = formatMeasure;
hooks.enterMeasuring = enterMeasuring;
hooks.exitMeasuring = exitMeasuring;
hooks.ensureMeasureGroup = ensureMeasureGroup;
hooks.measureWorldPerPixel = measureWorldPerPixel;
hooks.measureMarkerSize = measureMarkerSize;
hooks.measureSnapRadius = measureSnapRadius;
hooks.measureLineMaterial = measureLineMaterial;
hooks.addMeasureLine = addMeasureLine;
hooks.setMeasureMarkColor = setMeasureMarkColor;
hooks.makeMeasureMark = makeMeasureMark;
hooks.addMeasureArrow = addMeasureArrow;
hooks.clearMeasureChildren = clearMeasureChildren;
hooks.measureWorldDistance = measureWorldDistance;
hooks.worldMeasurePoint = worldMeasurePoint;
hooks.measureRecAlive = measureRecAlive;
hooks.makeMeasureRec = makeMeasureRec;
hooks.pruneMeasure = pruneMeasure;
hooks.worldVertex = worldVertex;
hooks.hitCandidateVertices = hitCandidateVertices;
hooks.snapMeasureHit = snapMeasureHit;
hooks.resolveMeasureMesh = resolveMeasureMesh;
hooks.findSolidInGroup = findSolidInGroup;
hooks.hideMeasurePreview = hideMeasurePreview;
hooks.showMeasurePreview = showMeasurePreview;
hooks.rebuildMeasureGeom = rebuildMeasureGeom;
hooks.hasMeasureGeom = hasMeasureGeom;
hooks.clearMeasure = clearMeasure;
hooks.removeMeasureSegment = removeMeasureSegment;
hooks.addMeasurePoint = addMeasurePoint;
hooks.selectedNodeBox = selectedNodeBox;
hooks.syncMeasureUi = syncMeasureUi;
hooks.updateMeasureLabel = updateMeasureLabel;
hooks.syncMeasureMarkScale = syncMeasureMarkScale;
export { measurePanel, toggleMeasurePanel, showMeasurePanel, hideMeasurePanel, formatMeasure, enterMeasuring, exitMeasuring, ensureMeasureGroup, measureWorldPerPixel, measureMarkerSize, measureSnapRadius, measureLineMaterial, addMeasureLine, setMeasureMarkColor, makeMeasureMark, addMeasureArrow, clearMeasureChildren, measureWorldDistance, worldMeasurePoint, measureRecAlive, makeMeasureRec, pruneMeasure, worldVertex, hitCandidateVertices, snapMeasureHit, resolveMeasureMesh, findSolidInGroup, hideMeasurePreview, showMeasurePreview, rebuildMeasureGeom, hasMeasureGeom, clearMeasure, removeMeasureSegment, addMeasurePoint, selectedNodeBox, syncMeasureUi, updateMeasureLabel, syncMeasureMarkScale };
