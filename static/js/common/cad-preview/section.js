/**
 * CAD 预览 — 剖切（GPU 预览 / CSG 提交）
 */
import { THREE, S, hooks, MAX_SECTION_CUTS, disposeHelperObject, eachSolid, escapeHtml, getModelBox, meshMaterials, setToggleActive } from './core.js';

function sectionPanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-section-panel]');
}

function toggleSectionPanel() {
    var panel = sectionPanel();
    if (!panel) {
        return;
    }
    if (panel.classList.contains('is-hidden')) {
        showSectionPanel();
    } else {
        hideSectionPanel();
    }
}

function showSectionPanel() {
    hooks.hideLightPanel();
    hooks.hideExplodePanel();
    hooks.hideMeasurePanel();
    hooks.hideDisplayPanel();
    hooks.hideShotPanel();
    var panel = sectionPanel();
    if (panel) {
        panel.classList.remove('is-hidden');
    }
    if (S.sectionPreviewing) {
        rebuildSectionHelpers();
    }
    syncSectionUi();
    setToggleActive('section', true);
}

function hideSectionPanel() {
    var panel = sectionPanel();
    if (panel) {
        panel.classList.add('is-hidden');
    }
    if (S.sectionPreviewing) {
        S.sectionPreviewing = false;
        hideSectionHelpers();
        applyAllSectionCuts();
    }
    setToggleActive('section', isSectionOn());
}

function isSectionOn() {
    return S.sectionCuts.length > 0;
}

function activeCut() {
    if (!S.sectionActiveId) {
        return S.sectionCuts.length ? S.sectionCuts[S.sectionCuts.length - 1] : null;
    }
    for (var i = 0; i < S.sectionCuts.length; i++) {
        if (S.sectionCuts[i].id === S.sectionActiveId) {
            return S.sectionCuts[i];
        }
    }
    return S.sectionCuts.length ? S.sectionCuts[S.sectionCuts.length - 1] : null;
}

function dirFromAzEl(azimuth, elevation) {
    var az = (Number(azimuth) || 0) * Math.PI / 180;
    var el = (Number(elevation) || 0) * Math.PI / 180;
    var cosEl = Math.cos(el);
    return new THREE.Vector3(cosEl * Math.cos(az), cosEl * Math.sin(az), Math.sin(el));
}

function axisFromDir(n) {
    if (n.distanceToSquared(new THREE.Vector3(1, 0, 0)) < 1e-4) {
        return 'x';
    }
    if (n.distanceToSquared(new THREE.Vector3(0, 1, 0)) < 1e-4) {
        return 'y';
    }
    if (n.distanceToSquared(new THREE.Vector3(0, 0, 1)) < 1e-4) {
        return 'z';
    }
    return 'free';
}

function setAzElFromAxis(obj, axis) {
    if (axis === 'x') {
        obj.azimuth = 0;
        obj.elevation = 0;
    } else if (axis === 'y') {
        obj.azimuth = 90;
        obj.elevation = 0;
    } else {
        axis = 'z';
        obj.azimuth = 0;
        obj.elevation = 90;
    }
    obj.axis = axis;
}

function projectBoxOnNormal(box, n) {
    var minDot = Infinity;
    var maxDot = -Infinity;
    var x = [box.min.x, box.max.x];
    var y = [box.min.y, box.max.y];
    var z = [box.min.z, box.max.z];
    for (var i = 0; i < 2; i++) {
        for (var j = 0; j < 2; j++) {
            for (var k = 0; k < 2; k++) {
                var d = n.x * x[i] + n.y * y[j] + n.z * z[k];
                if (d < minDot) {
                    minDot = d;
                }
                if (d > maxDot) {
                    maxDot = d;
                }
            }
        }
    }
    return { min: minDot, max: maxDot, extent: Math.max(maxDot - minDot, 1e-6) };
}

function currentCutTargetIds() {
    return hooks.currentSelectedIds ? hooks.currentSelectedIds() : (S.selectedNodeId ? [S.selectedNodeId] : []);
}

function cutNodeIds(cut) {
    var ids = [];
    var seen = {};
    function add(id) {
        if (!id || seen[id] || !S.nodeMap[id]) {
            return;
        }
        seen[id] = true;
        ids.push(id);
    }
    if (cut && cut.nodeIds && cut.nodeIds.length) {
        cut.nodeIds.forEach(add);
    } else if (cut && cut.nodeId) {
        add(cut.nodeId);
    }
    return ids;
}

function cutRoots(cut) {
    return cutNodeIds(cut).map(function (id) {
        return S.nodeMap[id].object;
    });
}

function cutRoot(cut) {
    var roots = cutRoots(cut);
    return roots.length ? roots[0] : null;
}

function cutBox(cut) {
    var roots = cutRoots(cut);
    if (!roots.length || !THREE) {
        return null;
    }
    var box = new THREE.Box3();
    var has = false;
    roots.forEach(function (root) {
        root.updateWorldMatrix(true, true);
        var b = new THREE.Box3().setFromObject(root);
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
    var center = box.getCenter(new THREE.Vector3());
    return {
        box: box,
        size: size,
        center: center,
        maxDim: Math.max(size.x, size.y, size.z, 1),
    };
}

function snapCutToPivot(cut) {
    var info = cutBox(cut);
    if (!info || !THREE || !cut) {
        return;
    }
    var origin = (S.controls && S.controls.target) ? S.controls.target.clone() : info.center.clone();
    var n = dirFromAzEl(cut.azimuth, cut.elevation);
    if (cut.flip) {
        n.negate();
    }
    var proj = projectBoxOnNormal(info.box, n);
    var d = n.x * origin.x + n.y * origin.y + n.z * origin.z;
    cut.offset = Math.max(0, Math.min(100, (d - proj.min) / proj.extent * 100));
}

function snapActiveCutToPivot() {
    var cut = activeCut();
    if (!cut) {
        return;
    }
    snapCutToPivot(cut);
    uncommitCut(cut);
    applyAllSectionCuts();
    showSectionHelpers();
    syncSectionUi();
}

function planeFromBox(n, offset, box) {
    var proj = projectBoxOnNormal(box, n);
    var t = Math.max(0, Math.min(100, Number(offset) || 0)) / 100;
    var dA = proj.min + proj.extent * t;
    return {
        plane: new THREE.Plane(n.clone(), -dA),
        proj: proj,
        dA: dA,
    };
}

function cutPlanes(cut) {
    var info = cutBox(cut);
    if (!info || !THREE || !cut) {
        return [];
    }
    var n = dirFromAzEl(cut.azimuth, cut.elevation);
    if (cut.flip) {
        n.negate();
    }
    return [planeFromBox(n, cut.offset, info.box).plane];
}

function eachClipMesh(root, fn) {
    if (!root) {
        return;
    }
    root.traverse(function (obj) {
        var role = obj.userData && obj.userData.cadRole;
        if (role === 'solid' && obj.isMesh) {
            fn(obj);
        } else if (obj.isLineSegments && obj.parent && obj.parent.userData && obj.parent.userData.cadRole === 'edges') {
            fn(obj);
        }
    });
}

function objectClipPlanes(obj) {
    if (obj && obj.userData && obj.userData._cadClip && obj.userData._cadClip.length) {
        return obj.userData._cadClip;
    }
    var mats = meshMaterials(obj);
    for (var i = 0; i < mats.length; i++) {
        if (mats[i].clippingPlanes && mats[i].clippingPlanes.length) {
            return mats[i].clippingPlanes;
        }
    }
    return [];
}

function syncMeshClipWorld(mesh) {
    var mats = meshMaterials(mesh);
    if (!mats.length || !THREE) {
        return;
    }
    var clip = mesh.userData._cadClip;
    if (!clip) {
        clip = (mats[0].userData && mats[0].userData._cadClip) || [];
        mesh.userData._cadClip = clip;
    }
    mats.forEach(function (m) {
        m.clippingPlanes = clip;
        if (!m.userData) {
            m.userData = {};
        }
        m.userData._cadClip = clip;
    });
    var needed = [];
    var local = mesh.userData._cadLocalClips || {};
    mesh.updateWorldMatrix(true, false);
    Object.keys(local).forEach(function (id) {
        (local[id] || []).forEach(function (lp) {
            needed.push(lp.clone().applyMatrix4(mesh.matrixWorld));
        });
    });
    var prev = clip.length;
    var i;
    while (clip.length < needed.length) {
        clip.push(new THREE.Plane());
    }
    if (clip.length > needed.length) {
        clip.length = needed.length;
    }
    for (i = 0; i < needed.length; i++) {
        clip[i].copy(needed[i]);
    }
    if (clip.length !== prev) {
        mats.forEach(function (m) {
            m.needsUpdate = true;
        });
    }
}

function bakeCutToMeshes(cut) {
    if (!cut || !THREE || !S.modelGroup) {
        return;
    }
    var worldPlanes = cutPlanes(cut);
    var roots = cutRoots(cut);
    eachClipMesh(S.modelGroup, function (mesh) {
        if (mesh.userData._cadLocalClips) {
            delete mesh.userData._cadLocalClips[cut.id];
        }
    });
    if (worldPlanes.length) {
        roots.forEach(function (root) {
            eachClipMesh(root, function (mesh) {
                if (!cutUsesGpu(cut, mesh)) {
                    return;
                }
                mesh.updateWorldMatrix(true, false);
                var inv = mesh.matrixWorld.clone().invert();
                if (!mesh.userData._cadLocalClips) {
                    mesh.userData._cadLocalClips = {};
                }
                mesh.userData._cadLocalClips[cut.id] = worldPlanes.map(function (p) {
                    return p.clone().applyMatrix4(inv);
                });
            });
        });
    }
    cut.helperLocals = worldPlanes.map(function (p) {
        return p.clone();
    });
}

function syncAllClipWorld() {
    if (!S.modelGroup) {
        return;
    }
    eachClipMesh(S.modelGroup, syncMeshClipWorld);
}

function solidFromClipObject(obj) {
    if (obj && obj.isMesh && obj.userData && obj.userData.cadRole === 'solid') {
        return obj;
    }
    var edgesGroup = obj && obj.parent;
    if (!edgesGroup || !edgesGroup.userData || edgesGroup.userData.cadRole !== 'edges') {
        return null;
    }
    var parent = edgesGroup.parent;
    if (!parent) {
        return null;
    }
    var i;
    for (i = 0; i < parent.children.length; i++) {
        var ch = parent.children[i];
        if (ch.isMesh && ch.userData && ch.userData.cadRole === 'solid') {
            return ch;
        }
    }
    return null;
}

function cutUsesGpu(cut, mesh) {
    if (!cut) {
        return false;
    }
    var solid = solidFromClipObject(mesh) || mesh;
    var data = (solid && solid.userData) || {};
    if (data._cadGpuFallbackCuts && data._cadGpuFallbackCuts[cut.id]) {
        return true;
    }
    if (cut.gpuFallback) {
        return true;
    }
    if (S.sectionPreviewing && cut.id === S.sectionActiveId && !cut.committed) {
        return true;
    }
    if (cut.committed && !data._cadCsgDirty) {
        return true;
    }
    return false;
}

function applyAllSectionCuts() {
    S.sectionCuts.forEach(function (cut) {
        bakeCutToMeshes(cut);
    });
    if (S.modelGroup) {
        eachClipMesh(S.modelGroup, function (mesh) {
            var local = mesh.userData._cadLocalClips;
            if (local) {
                Object.keys(local).forEach(function (id) {
                    var cut = null;
                    for (var i = 0; i < S.sectionCuts.length; i++) {
                        if (S.sectionCuts[i].id === id) {
                            cut = S.sectionCuts[i];
                            break;
                        }
                    }
                    if (!cut || !cutUsesGpu(cut, mesh)) {
                        delete local[id];
                    }
                });
            }
            syncMeshClipWorld(mesh);
        });
    }
    if (!S.sectionCuts.length) {
        clearSectionHelpers();
    }
}

function makeCutFromPivot() {
    var ids = currentCutTargetIds();
    var cut = {
        id: 'c' + (++S.sectionCutSeq),
        nodeIds: ids.slice(),
        nodeId: ids.length ? ids[ids.length - 1] : null,
        axis: 'z',
        azimuth: 0,
        elevation: 90,
        offset: 50,
        flip: false,
        helperLocals: [],
        committed: false,
        gpuFallback: false,
    };
    snapCutToPivot(cut);
    return cut;
}

function beginSectionCut() {
    if (S.sectionPreviewing || S.sectionCuts.length >= MAX_SECTION_CUTS) {
        return;
    }
    if (!currentCutTargetIds().length) {
        return;
    }
    var cut = makeCutFromPivot();
    S.sectionCuts.push(cut);
    S.sectionActiveId = cut.id;
    S.sectionPreviewing = true;
    applyAllSectionCuts();
    showSectionHelpers();
    syncSectionUi();
    setToggleActive('section', true);
}

function commitSectionCut() {
    if (!S.sectionPreviewing) {
        return;
    }
    var cut = activeCut();
    if (cut) {
        cut.committed = true;
        cut.gpuFallback = false;
    }
    S.sectionPreviewing = false;
    hideSectionHelpers();
    rebuildCommittedMeshes();
    syncSectionUi();
    setToggleActive('section', isSectionOn() || hooks.isPanelOpen(sectionPanel()));
}

function onSectionAddClick() {
    beginSectionCut();
}

function selectSectionCut(id) {
    if (!id) {
        return;
    }
    var found = null;
    for (var i = 0; i < S.sectionCuts.length; i++) {
        if (S.sectionCuts[i].id === id) {
            found = S.sectionCuts[i];
            break;
        }
    }
    if (!found) {
        return;
    }
    S.sectionActiveId = id;
    if (found.committed) {
        found.committed = false;
        found.gpuFallback = false;
        rebuildCommittedMeshes();
    }
    S.sectionPreviewing = true;
    applyAllSectionCuts();
    showSectionHelpers();
    syncSectionUi();
}

function removeSectionCut(id) {
    S.sectionCuts = S.sectionCuts.filter(function (c) {
        return c.id !== id;
    });
    if (S.sectionActiveId === id) {
        S.sectionActiveId = S.sectionCuts.length ? S.sectionCuts[S.sectionCuts.length - 1].id : null;
        S.sectionPreviewing = false;
    }
    rebuildCommittedMeshes();
    applyAllSectionCuts();
    if (S.sectionPreviewing) {
        showSectionHelpers();
    } else {
        hideSectionHelpers();
    }
    syncSectionUi();
    setToggleActive('section', isSectionOn() || hooks.isPanelOpen(sectionPanel()));
}

function setSectionAxis(axis) {
    var cut = activeCut();
    if (!cut) {
        return;
    }
    setAzElFromAxis(cut, axis);
    uncommitCut(cut);
    applyAllSectionCuts();
    showSectionHelpers();
    syncSectionUi();
}

function resetSection() {
    S.sectionCuts = [];
    S.sectionActiveId = null;
    S.sectionPreviewing = false;
    restoreAllOrigMeshes();
    applyAllSectionCuts();
    clearSectionHelpers();
    syncSectionUi();
    setToggleActive('section', hooks.isPanelOpen(sectionPanel()));
}

function syncSectionUi() {
    var panel = sectionPanel();
    if (!panel) {
        return;
    }
    var cut = activeCut();
    var az = panel.querySelector('[data-cad-section="azimuth"]');
    var el = panel.querySelector('[data-cad-section="elevation"]');
    var off = panel.querySelector('[data-cad-section="offset"]');
    var azVal = panel.querySelector('[data-cad-section-az-val]');
    var elVal = panel.querySelector('[data-cad-section-el-val]');
    var offVal = panel.querySelector('[data-cad-section-off-val]');
    var flip = panel.querySelector('[data-cad-section="flip"]');
    var targets = panel.querySelector('[data-cad-section="targets"]');
    var addBtn = panel.querySelector('[data-cad-action="section-add"]');
    var commitBtn = panel.querySelector('[data-cad-action="section-commit"]');
    var listEl = panel.querySelector('[data-cad-section="list"]');
    if (az) {
        az.value = String(Math.round(cut ? cut.azimuth : 0));
    }
    if (el) {
        el.value = String(Math.round(cut ? cut.elevation : 90));
    }
    if (off) {
        off.value = String(cut ? cut.offset : 50);
    }
    if (azVal) {
        azVal.textContent = Math.round(cut ? cut.azimuth : 0) + '°';
    }
    if (elVal) {
        elVal.textContent = Math.round(cut ? cut.elevation : 90) + '°';
    }
    if (offVal) {
        offVal.textContent = Math.round(cut ? cut.offset : 50) + '%';
    }
    if (flip) {
        flip.checked = !!(cut && cut.flip);
    }
    var targetIds = cut ? cutNodeIds(cut) : currentCutTargetIds();
    if (targets) {
        if (!targetIds.length) {
            targets.textContent = '请选择要剖切的零件（Ctrl 多选）';
        } else {
            var names = targetIds.map(function (id) {
                return (S.nodeMap[id] && S.nodeMap[id].name) || id;
            });
            targets.textContent = names.length === 1
                ? ('所选：' + names[0])
                : ('所选 ' + names.length + ' 件：' + names.join('、'));
        }
    }
    if (addBtn) {
        addBtn.disabled = S.sectionPreviewing || S.sectionCuts.length >= MAX_SECTION_CUTS || !currentCutTargetIds().length;
    }
    if (commitBtn) {
        commitBtn.disabled = !S.sectionPreviewing;
    }
    var axes = panel.querySelectorAll('[data-cad-action="section-axis"]');
    var axis = cut ? cut.axis : 'z';
    for (var i = 0; i < axes.length; i++) {
        axes[i].classList.toggle('active', axes[i].getAttribute('data-cad-axis') === axis);
    }
    if (listEl) {
        if (!S.sectionCuts.length) {
            listEl.innerHTML = '';
            listEl.classList.add('is-hidden');
        } else {
            listEl.innerHTML = S.sectionCuts.map(function (c) {
                var ids = cutNodeIds(c);
                var name = '未选零件';
                if (ids.length === 1 && S.nodeMap[ids[0]]) {
                    name = S.nodeMap[ids[0]].name || ids[0];
                } else if (ids.length > 1) {
                    name = ids.length + ' 件';
                }
                var ax = c.axis === 'free' ? '斜' : String(c.axis || 'z').toUpperCase();
                var cls = 'cad-preview-measure-item' + (c.id === (cut && cut.id) ? ' is-selected' : '');
                return '<div class="' + cls + '" data-cad-action="section-select" data-cad-cut-id="' + c.id + '">' +
                    '<span>' + escapeHtml(name + ' · ' + ax + ' · ' + Math.round(c.offset) + '%') + '</span>' +
                    '<button type="button" class="btn btn-sm btn-ghost-secondary cad-preview-measure-remove"' +
                    ' data-cad-action="section-remove" data-cad-cut-id="' + c.id + '" title="删除此剖切">×</button></div>';
            }).join('');
            listEl.classList.remove('is-hidden');
        }
    }
}

function onSectionInput(ev) {
    var input = ev.target.closest('[data-cad-section]');
    if (!input) {
        return;
    }
    var kind = input.getAttribute('data-cad-section');
    if (kind === 'list') {
        return;
    }
    var cut = activeCut();
    if (!cut) {
        return;
    }
    if (kind === 'offset') {
        cut.offset = Number(input.value);
    } else if (kind === 'azimuth') {
        cut.azimuth = Number(input.value);
        cut.axis = axisFromDir(dirFromAzEl(cut.azimuth, cut.elevation));
    } else if (kind === 'elevation') {
        cut.elevation = Number(input.value);
        cut.axis = axisFromDir(dirFromAzEl(cut.azimuth, cut.elevation));
    } else if (kind === 'flip') {
        cut.flip = !!input.checked;
    } else {
        return;
    }
    uncommitCut(cut);
    S.sectionPreviewing = true;
    applyAllSectionCuts();
    showSectionHelpers();
    syncSectionUi();
}

function clearSectionHelpers() {
    S.sectionHelpers.forEach(function (h) {
        if (h.helper && h.helper.parent) {
            h.helper.parent.remove(h.helper);
        }
        disposeHelperObject(h.helper);
    });
    S.sectionHelpers = [];
}

function hideSectionHelpers() {
    S.sectionHelpers.forEach(function (h) {
        if (h.helper) {
            h.helper.visible = false;
        }
    });
}

function poseSectionHelper(h) {
    if (!h || !h.helper || !h.plane || !THREE) {
        return;
    }
    if (h.local) {
        h.plane.copy(h.local);
    }
    var info = cutBox(activeCut()) || getModelBox(false);
    var size = info ? Math.max(info.maxDim * 1.15, 1) : 50;
    var origin = info ? info.center : new THREE.Vector3();
    var pos = h.plane.projectPoint(origin, new THREE.Vector3());
    h.helper.position.copy(pos);
    if (Math.abs(h.plane.normal.y) < 0.9) {
        h.helper.up.set(0, 1, 0);
    } else {
        h.helper.up.set(0, 0, 1);
    }
    h.helper.lookAt(
        pos.x - h.plane.normal.x,
        pos.y - h.plane.normal.y,
        pos.z - h.plane.normal.z
    );
    h.helper.scale.set(size, size, 1);
    h.helper.visible = true;
}

function rebuildSectionHelpers() {
    clearSectionHelpers();
    if (!S.sectionPreviewing) {
        return;
    }
    var cut = activeCut();
    if (!cut || !S.scene || !THREE) {
        return;
    }
    var locals = cut.helperLocals || [];
    locals.forEach(function (lp) {
        var world = lp.clone();
        var geom = new THREE.PlaneGeometry(1, 1);
        var mat = new THREE.MeshBasicMaterial({
            color: 0xe67e22,
            transparent: true,
            opacity: 0.18,
            side: THREE.DoubleSide,
            depthWrite: false,
            depthTest: true,
            polygonOffset: true,
            polygonOffsetFactor: -1,
            polygonOffsetUnits: -1,
        });
        var helper = new THREE.Mesh(geom, mat);
        helper.name = 'cad-section-helper';
        helper.userData.cadRole = 'section-helper';
        helper.renderOrder = 2;
        helper.frustumCulled = false;
        helper.raycast = function () {};
        var outline = new THREE.LineLoop(
            new THREE.BufferGeometry().setAttribute(
                'position',
                new THREE.Float32BufferAttribute([
                    -0.5, -0.5, 0,
                    0.5, -0.5, 0,
                    0.5, 0.5, 0,
                    -0.5, 0.5, 0,
                ], 3)
            ),
            new THREE.LineBasicMaterial({
                color: 0xe67e22,
                depthTest: false,
                depthWrite: false,
            })
        );
        outline.renderOrder = 3;
        outline.frustumCulled = false;
        outline.raycast = function () {};
        helper.add(outline);
        S.scene.add(helper);
        var rec = { helper: helper, plane: world, local: lp };
        S.sectionHelpers.push(rec);
        poseSectionHelper(rec);
    });
}

function showSectionHelpers() {
    S.sectionPreviewing = true;
    rebuildSectionHelpers();
}

function updateSectionHelpers() {
    if (S.capturingShot || !S.sectionPreviewing || !S.sectionHelpers.length) {
        hideSectionHelpers();
        return;
    }
    S.sectionHelpers.forEach(poseSectionHelper);
}

function uncommitCut(cut) {
    if (!cut || !cut.committed) {
        return;
    }
    cut.committed = false;
    cut.gpuFallback = false;
    rebuildCommittedMeshes();
}

function solidIsUnderCut(mesh, cut) {
    var roots = cutRoots(cut);
    if (!roots.length || !mesh) {
        return false;
    }
    var cur = mesh;
    while (cur) {
        if (roots.indexOf(cur) !== -1) {
            return true;
        }
        cur = cur.parent;
    }
    return false;
}

function snapshotSolidOrig(mesh) {
    if (!mesh || !mesh.geometry || mesh.userData._cadOrig) {
        return;
    }
    var geom = mesh.geometry;
    var pos = geom.attributes.position;
    var nrm = geom.attributes.normal;
    var idx = geom.index;
    mesh.userData._cadOrig = {
        position: pos.array.slice(),
        normal: nrm ? nrm.array.slice() : null,
        index: idx ? idx.array.slice() : null,
        groups: (geom.groups || []).map(function (g) {
            return { start: g.start, count: g.count, materialIndex: g.materialIndex };
        }),
        material: mesh.material,
    };
    mesh.userData._cadCsgDirty = false;
}

function origGeometryOf(mesh) {
    var orig = mesh.userData._cadOrig;
    if (!orig) {
        snapshotSolidOrig(mesh);
        orig = mesh.userData._cadOrig;
    }
    var geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(orig.position.slice(), 3));
    if (orig.normal) {
        geom.setAttribute('normal', new THREE.Float32BufferAttribute(orig.normal.slice(), 3));
    } else {
        geom.computeVertexNormals();
    }
    if (orig.index) {
        geom.setIndex(new THREE.BufferAttribute(orig.index.slice(), 1));
    }
    (orig.groups || []).forEach(function (g) {
        geom.addGroup(g.start, g.count, g.materialIndex);
    });
    return geom;
}

function findEdgesGroup(solid) {
    var parent = solid && solid.parent;
    if (!parent) {
        return null;
    }
    for (var i = 0; i < parent.children.length; i++) {
        var ch = parent.children[i];
        if (ch.userData && ch.userData.cadRole === 'edges') {
            return ch;
        }
    }
    return null;
}

function groupsToBrepFaces(geom) {
    var groups = geom && geom.groups;
    if (!groups || !groups.length || !geom.index) {
        return null;
    }
    var faces = [];
    var i;
    for (i = 0; i < groups.length; i++) {
        var g = groups[i];
        if (!g || g.count < 3 || (g.start % 3) !== 0 || (g.count % 3) !== 0) {
            continue;
        }
        var first = g.start / 3;
        faces.push({ first: first, last: first + g.count / 3 - 1 });
    }
    return faces.length ? faces : null;
}

function geomTriRange(geometry, posCount) {
    var index = geometry.index;
    var total = index ? index.count : posCount;
    var start = geometry.drawRange ? geometry.drawRange.start : 0;
    var count = geometry.drawRange ? geometry.drawRange.count : Infinity;
    if (count == null || count === Infinity || count < 0) {
        count = total - start;
    }
    var end = Math.min(total, start + count);
    start = Math.max(0, start);
    end = end - ((end - start) % 3);
    return { index: index, start: start, end: end };
}

function geometryMaterialCount(geom) {
    var groups = geom && geom.groups;
    if (!groups || !groups.length) {
        return 1;
    }
    var max = 0;
    var i;
    for (i = 0; i < groups.length; i++) {
        var g = groups[i];
        if (!g || g.cadCap) {
            continue;
        }
        var m = g.materialIndex || 0;
        if (m > max) {
            max = m;
        }
    }
    return max + 1;
}

function assignCapMaterialSlots(geom, origMatCount) {
    var groups = geom && geom.groups;
    if (!groups || !groups.length) {
        return;
    }
    var i;
    for (i = 0; i < groups.length; i++) {
        if (groups[i] && groups[i].cadCap) {
            groups[i].materialIndex = origMatCount;
        }
    }
}

function weldGeometry(geometry) {
    var posAttr = geometry && geometry.attributes && geometry.attributes.position;
    if (!posAttr || !posAttr.count) {
        var empty = new THREE.BufferGeometry();
        empty.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
        empty.setIndex([]);
        return empty;
    }
    geometry.computeBoundingBox();
    var box = geometry.boundingBox;
    var maxDim = 1;
    if (box && !box.isEmpty()) {
        maxDim = Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z, 1);
    }
    var precision = Math.max(maxDim * 1e-5, 1e-6);
    var hashToIndex = Object.create(null);
    var newPos = [];
    var next = 0;

    function vertexIndex(i) {
        var x = posAttr.getX(i);
        var y = posAttr.getY(i);
        var z = posAttr.getZ(i);
        var key = Math.round(x / precision) + ',' + Math.round(y / precision) + ',' + Math.round(z / precision);
        var mapped = hashToIndex[key];
        if (mapped == null) {
            hashToIndex[key] = next;
            newPos.push(x, y, z);
            mapped = next;
            next += 1;
        }
        return mapped;
    }

    var range = geomTriRange(geometry, posAttr.count);
    var newIndex = [];
    var t;
    for (t = range.start; t + 2 < range.end; t += 3) {
        var a = vertexIndex(range.index ? range.index.getX(t) : t);
        var b = vertexIndex(range.index ? range.index.getX(t + 1) : t + 1);
        var c = vertexIndex(range.index ? range.index.getX(t + 2) : t + 2);
        if (a === b || b === c || c === a) {
            continue;
        }
        newIndex.push(a, b, c);
    }
    var out = new THREE.BufferGeometry();
    out.setAttribute('position', new THREE.Float32BufferAttribute(newPos, 3));
    out.setIndex(newIndex);
    return out;
}

function rebuildSolidEdges(solid) {
    var parent = solid && solid.parent;
    if (!parent) {
        return;
    }
    var old = findEdgesGroup(solid);
    var vis = old ? old.visible : S.displayMode !== 'solid';
    if (old) {
        parent.remove(old);
        disposeHelperObject(old);
    }
    var geom = solid.geometry;
    if (!geom || !geom.attributes || !geom.attributes.position) {
        return;
    }
    var faces = groupsToBrepFaces(geom);
    var edges;
    if (faces && faces.length) {
        edges = hooks.buildFaceEdges(geom, geom.index ? geom.index.array : null, faces);
    } else {
        var welded = weldGeometry(geom);
        edges = hooks.buildFaceEdges(welded, welded.index ? welded.index.array : null, null);
        welded.dispose();
    }
    edges.visible = vis;
    parent.add(edges);
}

function replaceSolidGeometry(mesh, geometry, flattenMat) {
    var old = mesh.geometry;
    mesh.geometry = geometry;
    if (old && old !== geometry && old.dispose) {
        old.dispose();
    }
    if (flattenMat && Array.isArray(mesh.material) && mesh.material.length) {
        mesh.material = mesh.material[0];
    }
    mesh.userData._cadCsgDirty = true;
    rebuildSolidEdges(mesh);
}

function restoreOrigGeometry(mesh) {
    if (!mesh || !mesh.userData._cadOrig) {
        if (mesh && mesh.userData) {
            mesh.userData._cadGpuFallbackCuts = {};
        }
        return;
    }
    if (mesh.userData._cadCsgDirty) {
        replaceSolidGeometry(mesh, origGeometryOf(mesh), false);
        if (mesh.userData._cadOrig.material) {
            mesh.material = mesh.userData._cadOrig.material;
        }
        mesh.userData._cadCsgDirty = false;
    }
    mesh.userData._cadGpuFallbackCuts = {};
}

function restoreAllOrigMeshes() {
    eachSolid(restoreOrigGeometry);
}

function configureCsgEvaluator() {
    if (!S.csgEvaluator) {
        return;
    }
    S.csgEvaluator.useGroups = true;
    S.csgEvaluator.consolidateGroups = false;
    S.csgEvaluator.removeUnusedMaterials = false;
    S.csgEvaluator.attributes = ['position', 'normal'];
}

function ensureCsg() {
    if (S.csgMod && S.csgEvaluator) {
        configureCsgEvaluator();
        return Promise.resolve(S.csgMod);
    }
    return import('three-bvh-csg').then(function (mod) {
        S.csgMod = mod;
        S.csgEvaluator = new mod.Evaluator();
        configureCsgEvaluator();
        return S.csgMod;
    });
}

function localCutterBrush(localPlane, geom) {
    geom.computeBoundingBox();
    var box = geom.boundingBox;
    var size = box.getSize(new THREE.Vector3());
    var maxDim = Math.max(size.x, size.y, size.z, 1);
    var span = maxDim * 4;
    var depth = maxDim * 4;
    var cutterGeom = new THREE.BoxGeometry(span, span, depth);
    var brush = new S.csgMod.Brush(cutterGeom);
    var n = localPlane.normal.clone();
    if (n.lengthSq() < 1e-12) {
        n.set(0, 0, 1);
    } else {
        n.normalize();
    }
    var origin = box.getCenter(new THREE.Vector3());
    var onPlane = localPlane.projectPoint(origin, new THREE.Vector3());
    brush.position.copy(onPlane).addScaledVector(n, -depth / 2);
    brush.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
    brush.matrixWorldNeedsUpdate = true;
    brush.updateMatrixWorld(true);
    return brush;
}

function applyPlanesToGeometry(geom, worldPlanes, meshMatrixWorld) {
    var preserveGroups = !!(geom.groups && geom.groups.length);
    var origMatCount = preserveGroups ? geometryMaterialCount(geom) : 0;
    if (preserveGroups && origMatCount) {
        assignCapMaterialSlots(geom, origMatCount);
    }
    var inv = meshMatrixWorld.clone().invert();
    var brushA = new S.csgMod.Brush(geom);
    brushA.matrixWorldNeedsUpdate = true;
    brushA.updateMatrixWorld(true);
    var i;
    for (i = 0; i < worldPlanes.length; i++) {
        var localPlane = worldPlanes[i].clone().applyMatrix4(inv);
        var cutter = localCutterBrush(localPlane, brushA.geometry);
        var target = new S.csgMod.Brush();
        var ok = false;
        var lastErr = null;
        try {
            S.csgEvaluator.evaluate(brushA, cutter, S.csgMod.SUBTRACTION, target);
            if (target.geometry && target.geometry.attributes && target.geometry.attributes.position && target.geometry.attributes.position.count) {
                ok = true;
            }
        } catch (err) {
            lastErr = err;
        }
        if (cutter.geometry && cutter.geometry.dispose) {
            cutter.geometry.dispose();
        }
        if (!ok) {
            throw lastErr || new Error('CSG 切削失败');
        }
        brushA = target;
        brushA.matrixWorldNeedsUpdate = true;
        brushA.updateMatrixWorld(true);
    }
    return compactGeometry(brushA.geometry, origMatCount, preserveGroups);
}

function compactGeometry(geometry, origMatCount, preserveGroups) {
    var posAttr = geometry && geometry.attributes && geometry.attributes.position;
    if (!posAttr || !posAttr.count) {
        var empty = new THREE.BufferGeometry();
        empty.setAttribute('position', new THREE.Float32BufferAttribute([], 3));
        empty.setIndex([]);
        return empty;
    }
    var nrmAttr = geometry.attributes.normal;
    var range = geomTriRange(geometry, posAttr.count);
    var newPos = [];
    var newNrm = [];
    var next = 0;
    var newIndex = [];
    var newGroups = [];
    var weldPrecision = 1e-6;
    if (preserveGroups) {
        geometry.computeBoundingBox();
        var box = geometry.boundingBox;
        if (box && !box.isEmpty()) {
            var maxDim = Math.max(box.max.x - box.min.x, box.max.y - box.min.y, box.max.z - box.min.z, 1);
            weldPrecision = Math.max(maxDim * 1e-5, 1e-6);
        }
    }
    var map = Object.create(null);
    function pushVertex(i) {
        newPos.push(posAttr.getX(i), posAttr.getY(i), posAttr.getZ(i));
        if (nrmAttr) {
            newNrm.push(nrmAttr.getX(i), nrmAttr.getY(i), nrmAttr.getZ(i));
        }
        var mapped = next;
        next += 1;
        return mapped;
    }
    function mapByOrig(i) {
        var mapped = map[i];
        if (mapped == null) {
            mapped = pushVertex(i);
            map[i] = mapped;
        }
        return mapped;
    }
    function makeGroupWelder() {
        var hashToIndex = Object.create(null);
        return function mapByPos(i) {
            var key = Math.round(posAttr.getX(i) / weldPrecision) + ',' +
                Math.round(posAttr.getY(i) / weldPrecision) + ',' +
                Math.round(posAttr.getZ(i) / weldPrecision);
            var mapped = hashToIndex[key];
            if (mapped == null) {
                mapped = pushVertex(i);
                hashToIndex[key] = mapped;
            }
            return mapped;
        };
    }
    function appendTri(t, mapFn) {
        var a = range.index ? range.index.getX(t) : t;
        var b = range.index ? range.index.getX(t + 1) : t + 1;
        var c = range.index ? range.index.getX(t + 2) : t + 2;
        a = mapFn(a);
        b = mapFn(b);
        c = mapFn(c);
        if (a === b || b === c || c === a) {
            return;
        }
        newIndex.push(a, b, c);
    }
    function groupWindow(g) {
        var gStart = Math.max(g.start, range.start);
        var gEnd = Math.min(g.start + g.count, range.end);
        gStart = gStart + ((3 - (gStart % 3)) % 3);
        gEnd = gEnd - ((gEnd - gStart) % 3);
        return { start: gStart, end: gEnd };
    }
    function isCapGroup(g) {
        return !!(g.cadCap || (origMatCount && (g.materialIndex || 0) >= origMatCount));
    }
    var groups = preserveGroups ? (geometry.groups || []) : [];
    var t;
    if (groups.length) {
        var gi;
        var g;
        var win;
        var added;
        for (gi = 0; gi < groups.length; gi++) {
            g = groups[gi];
            if (!g || g.count < 3 || isCapGroup(g)) {
                continue;
            }
            win = groupWindow(g);
            var groupIndexStart = newIndex.length;
            var weld = makeGroupWelder();
            for (t = win.start; t + 2 < win.end; t += 3) {
                appendTri(t, weld);
            }
            added = newIndex.length - groupIndexStart;
            if (added < 3) {
                continue;
            }
            newGroups.push({
                start: groupIndexStart,
                count: added,
                materialIndex: g.materialIndex || 0,
            });
        }
        var capStart = newIndex.length;
        var capWeld = makeGroupWelder();
        for (gi = 0; gi < groups.length; gi++) {
            g = groups[gi];
            if (!g || g.count < 3 || !isCapGroup(g)) {
                continue;
            }
            win = groupWindow(g);
            for (t = win.start; t + 2 < win.end; t += 3) {
                appendTri(t, capWeld);
            }
        }
        added = newIndex.length - capStart;
        if (added >= 3) {
            newGroups.push({ start: capStart, count: added, materialIndex: 0, cadCap: true });
        }
    } else {
        for (t = range.start; t + 2 < range.end; t += 3) {
            appendTri(t, mapByOrig);
        }
    }
    var out = new THREE.BufferGeometry();
    out.setAttribute('position', new THREE.Float32BufferAttribute(newPos, 3));
    if (newNrm.length) {
        out.setAttribute('normal', new THREE.Float32BufferAttribute(newNrm, 3));
    } else {
        out.computeVertexNormals();
    }
    out.setIndex(newIndex);
    for (t = 0; t < newGroups.length; t++) {
        var ng = newGroups[t];
        out.addGroup(ng.start, ng.count, ng.materialIndex);
        if (ng.cadCap) {
            out.groups[out.groups.length - 1].cadCap = true;
        }
    }
    return out;
}


function rebuildCommittedMeshes() {
    var gen = ++S.csgGen;
    var committed = S.sectionCuts.filter(function (c) {
        return c.committed;
    });
    restoreAllOrigMeshes();
    applyAllSectionCuts();
    if (!committed.length) {
        return Promise.resolve();
    }
    return ensureCsg().then(function () {
        if (gen !== S.csgGen) {
            return;
        }
        eachSolid(function (mesh) {
            if (gen !== S.csgGen) {
                return;
            }
            var cutsForMesh = committed.filter(function (cut) {
                return solidIsUnderCut(mesh, cut);
            });
            if (!cutsForMesh.length) {
                restoreOrigGeometry(mesh);
                return;
            }
            snapshotSolidOrig(mesh);
            var geom = origGeometryOf(mesh);
            mesh.updateWorldMatrix(true, false);
            try {
                var i;
                for (i = 0; i < cutsForMesh.length; i++) {
                    geom = applyPlanesToGeometry(
                        geom,
                        cutPlanes(cutsForMesh[i]),
                        mesh.matrixWorld
                    );
                }
                replaceSolidGeometry(mesh, geom, false);
                mesh.userData._cadGpuFallbackCuts = {};
            } catch (err) {
                restoreOrigGeometry(mesh);
                var failed = {};
                cutsForMesh.forEach(function (cut) {
                    failed[cut.id] = true;
                });
                mesh.userData._cadGpuFallbackCuts = failed;
            }
        });
        if (gen === S.csgGen) {
            applyAllSectionCuts();
            if (hooks.setDisplayMode) {
                hooks.setDisplayMode(S.displayMode);
            }
        }
    }).catch(function () {
        if (gen !== S.csgGen) {
            return;
        }
        committed.forEach(function (cut) {
            cut.gpuFallback = true;
        });
        restoreAllOrigMeshes();
        applyAllSectionCuts();
    });
}


hooks.sectionPanel = sectionPanel;
hooks.toggleSectionPanel = toggleSectionPanel;
hooks.showSectionPanel = showSectionPanel;
hooks.hideSectionPanel = hideSectionPanel;
hooks.isSectionOn = isSectionOn;
hooks.activeCut = activeCut;
hooks.dirFromAzEl = dirFromAzEl;
hooks.axisFromDir = axisFromDir;
hooks.setAzElFromAxis = setAzElFromAxis;
hooks.projectBoxOnNormal = projectBoxOnNormal;
hooks.cutRoot = cutRoot;
hooks.cutBox = cutBox;
hooks.snapCutToPivot = snapCutToPivot;
hooks.snapActiveCutToPivot = snapActiveCutToPivot;
hooks.planeFromBox = planeFromBox;
hooks.cutPlanes = cutPlanes;
hooks.eachClipMesh = eachClipMesh;
hooks.objectClipPlanes = objectClipPlanes;
hooks.syncMeshClipWorld = syncMeshClipWorld;
hooks.bakeCutToMeshes = bakeCutToMeshes;
hooks.syncAllClipWorld = syncAllClipWorld;
hooks.cutUsesGpu = cutUsesGpu;
hooks.applyAllSectionCuts = applyAllSectionCuts;
hooks.currentCutTargetIds = currentCutTargetIds;
hooks.cutNodeIds = cutNodeIds;
hooks.cutRoots = cutRoots;
hooks.makeCutFromPivot = makeCutFromPivot;
hooks.beginSectionCut = beginSectionCut;
hooks.commitSectionCut = commitSectionCut;
hooks.onSectionAddClick = onSectionAddClick;
hooks.selectSectionCut = selectSectionCut;
hooks.removeSectionCut = removeSectionCut;
hooks.setSectionAxis = setSectionAxis;
hooks.resetSection = resetSection;
hooks.syncSectionUi = syncSectionUi;
hooks.onSectionInput = onSectionInput;
hooks.clearSectionHelpers = clearSectionHelpers;
hooks.hideSectionHelpers = hideSectionHelpers;
hooks.poseSectionHelper = poseSectionHelper;
hooks.rebuildSectionHelpers = rebuildSectionHelpers;
hooks.showSectionHelpers = showSectionHelpers;
hooks.updateSectionHelpers = updateSectionHelpers;
hooks.uncommitCut = uncommitCut;
hooks.solidIsUnderCut = solidIsUnderCut;
hooks.snapshotSolidOrig = snapshotSolidOrig;
hooks.origGeometryOf = origGeometryOf;
hooks.findEdgesGroup = findEdgesGroup;
hooks.rebuildSolidEdges = rebuildSolidEdges;
hooks.replaceSolidGeometry = replaceSolidGeometry;
hooks.restoreOrigGeometry = restoreOrigGeometry;
hooks.restoreAllOrigMeshes = restoreAllOrigMeshes;
hooks.ensureCsg = ensureCsg;
hooks.localCutterBrush = localCutterBrush;
hooks.applyPlanesToGeometry = applyPlanesToGeometry;
hooks.rebuildCommittedMeshes = rebuildCommittedMeshes;
export { sectionPanel, toggleSectionPanel, showSectionPanel, hideSectionPanel, isSectionOn, activeCut, dirFromAzEl, axisFromDir, setAzElFromAxis, projectBoxOnNormal, currentCutTargetIds, cutNodeIds, cutRoots, cutRoot, cutBox, snapCutToPivot, snapActiveCutToPivot, planeFromBox, cutPlanes, eachClipMesh, objectClipPlanes, syncMeshClipWorld, bakeCutToMeshes, syncAllClipWorld, cutUsesGpu, applyAllSectionCuts, makeCutFromPivot, beginSectionCut, commitSectionCut, onSectionAddClick, selectSectionCut, removeSectionCut, setSectionAxis, resetSection, syncSectionUi, onSectionInput, clearSectionHelpers, hideSectionHelpers, poseSectionHelper, rebuildSectionHelpers, showSectionHelpers, updateSectionHelpers, uncommitCut, solidIsUnderCut, snapshotSolidOrig, origGeometryOf, findEdgesGroup, rebuildSolidEdges, replaceSolidGeometry, restoreOrigGeometry, restoreAllOrigMeshes, ensureCsg, localCutterBrush, applyPlanesToGeometry, rebuildCommittedMeshes };
