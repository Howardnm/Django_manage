/**
 * CAD 预览 — 共享引擎与状态。仅 attachment:viewer 加载。
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export { THREE };

export var LARGE_FILE_BYTES = 20 * 1024 * 1024;
export var WORKER_TIMEOUT_MS = 90 * 1000;
export var DEFAULT_COLOR = 0x8a9ba8;
export var DEFAULT_LIGHT_AZIMUTH = 50;
export var DEFAULT_LIGHT_ELEVATION = 46;
export var DEFAULT_LIGHT_INTENSITY = 1.0;
export var DEFAULT_LIGHT_COLOR = '#ffffff';
export var DEFAULT_LIGHT_KIND = 'area';
export var DEFAULT_LIGHT_DISTANCE = 1.5;
export var DEFAULT_LIGHT_GLOSS = 0.35;
export var DEFAULT_MAT_ROUGHNESS = 0.452;
export var DEFAULT_MAT_METALNESS = 0.106;
export var DEFAULT_MAT_CLEARCOAT = 0.295;
export var DEFAULT_MAT_CLEARCOAT_ROUGHNESS = 0.178;
export var MAX_SECTION_CUTS = 8;
export var DEFAULT_EXPLODE_BIN_PCT = 2;
export var TREE_AUTO_COLLAPSE_MIN = 12;
export var DEFAULT_HINT = '拖动旋转 · 滚轮缩放 · 右键平移 · 双击零件设为旋转中心';
export var MEASURE_HINT = '单击两点测距 · 可连续标注 · 靠近端点吸附 · Esc 退出';
export var MEASURE_COLOR = 0x206bc4;
export var XRAY_OPACITY = 0.22;
export var HIGHLIGHT_EMISSIVE = 0x1a4a7a;
export var CLEAR_COLOR_LIGHT = 0xf4f6f8;
export var CLEAR_COLOR_DARK = 0x1c2330;
export var PIVOT_HOLD_MS = 1000;

export var ALIGNED_VIEWS = {
    front: { offset: [0, 1, 0], up: [0, 0, 1] },
    back: { offset: [0, -1, 0], up: [0, 0, 1] },
    right: { offset: [1, 0, 0], up: [0, 0, 1] },
    left: { offset: [-1, 0, 0], up: [0, 0, 1] },
    top: { offset: [0, 0, 1], up: [0, 1, 0] },
    bottom: { offset: [0, 0, -1], up: [0, 1, 0] },
};

export var hooks = {};

export var S = {
    renderer: null,
    scene: null,
    camera: null,
    controls: null,
    modelGroup: null,
    ambientLight: null,
    keyLight: null,
    fillLight: null,
    pointLight: null,
    rafId: 0,
    resizeObserver: null,
    worker: null,
    abortController: null,
    displayMode: 'solid',
    canvasEl: null,
    stageEl: null,
    pageRoot: null,
    lightAzimuth: DEFAULT_LIGHT_AZIMUTH,
    lightElevation: DEFAULT_LIGHT_ELEVATION,
    lightIntensity: DEFAULT_LIGHT_INTENSITY,
    lightColor: DEFAULT_LIGHT_COLOR,
    lightFollow: false,
    lightKind: DEFAULT_LIGHT_KIND,
    lightDistance: DEFAULT_LIGHT_DISTANCE,
    lightGloss: DEFAULT_LIGHT_GLOSS,
    matRoughness: DEFAULT_MAT_ROUGHNESS,
    matMetalness: DEFAULT_MAT_METALNESS,
    matClearcoat: DEFAULT_MAT_CLEARCOAT,
    matClearcoatRoughness: DEFAULT_MAT_CLEARCOAT_ROUGHNESS,
    nodeIdSeq: 0,
    nodeMap: {},
    selectedNodeId: null,
    selectedNodeIds: [],
    isolateBackup: null,
    treeQuery: '',
    treeVisFilter: 'all',
    orthoOn: false,
    gridOn: false,
    axesOn: false,
    gridHelper: null,
    axesHelper: null,
    currentFileName: 'cad',
    pointerDownPos: null,
    orthoHalf: 50,
    pivotHelper: null,
    placingPivot: false,
    measuring: false,
    measureSegments: [],
    measurePending: null,
    measureGroup: null,
    measurePreview: null,
    darkCanvas: false,
    shotIncludeMeasure: true,
    shotIncludeHelpers: true,
    shotIncludeHighlight: true,
    shotAlpha: false,
    shotScale: 2,
    shotSize: 0,
    capturingShot: false,
    pivotInteracting: false,
    pivotHideAt: 0,
    sectionCuts: [],
    sectionActiveId: null,
    sectionCutSeq: 0,
    sectionHelpers: [],
    sectionPreviewing: false,
    csgMod: null,
    csgEvaluator: null,
    csgGen: 0,
    explodeAmount: 0,
    explodeSpan: 50,
    explodeUnits: [],
    explodeParentId: null,
    explodeStyle: 'radial',
    explodeCenterId: null,
    explodeEven: true,
    explodeBinPct: DEFAULT_EXPLODE_BIN_PCT,
    alignedView: null,
};


function assets() {
    return window.CAD_PREVIEW_ASSETS || {};
}

function $(sel, root) {
    return (root || document).querySelector(sel);
}

function setStatus(message) {
    if (!S.stageEl) {
        return;
    }
    var overlay = $('[data-cad-status]', S.stageEl);
    var text = $('[data-cad-status-text]', S.stageEl);
    var error = $('[data-cad-error]', S.stageEl);
    if (error) {
        error.classList.add('is-hidden');
    }
    if (!message) {
        if (overlay) {
            overlay.classList.add('is-hidden');
        }
        return;
    }
    if (overlay) {
        overlay.classList.remove('is-hidden');
    }
    if (text) {
        text.textContent = message;
    }
}

function setError(message) {
    if (!S.stageEl) {
        return;
    }
    var overlay = $('[data-cad-status]', S.stageEl);
    var error = $('[data-cad-error]', S.stageEl);
    var text = $('[data-cad-error-text]', S.stageEl);
    if (overlay) {
        overlay.classList.add('is-hidden');
    }
    if (error) {
        error.classList.remove('is-hidden');
    }
    if (text) {
        text.textContent = message;
    }
}

function canvasClearColor() {
    return S.darkCanvas ? CLEAR_COLOR_DARK : CLEAR_COLOR_LIGHT;
}

function applyCanvasClear(alpha) {
    if (!S.renderer) {
        return;
    }
    if (alpha) {
        S.renderer.setClearColor(0x000000, 0);
    } else {
        S.renderer.setClearColor(canvasClearColor(), 1);
    }
}

function setHint(text) {
    var hint = S.pageRoot && S.pageRoot.querySelector('[data-cad-hint]');
    if (hint) {
        hint.textContent = text || DEFAULT_HINT;
    }
}

function setToggleActive(action, on) {
    var btn = S.pageRoot && S.pageRoot.querySelector('[data-cad-action="' + action + '"]');
    if (btn) {
        btn.classList.toggle('active', !!on);
    }
    if (hooks.syncGroupToggles) {
        hooks.syncGroupToggles();
    }
}

function setGroupActive(group, on) {
    var btn = S.pageRoot && S.pageRoot.querySelector('[data-cad-group="' + group + '"]');
    if (btn) {
        btn.classList.toggle('active', !!on);
    }
}

function closeParentDropdown(el) {
    var root = el && el.closest ? el.closest('.dropdown') : null;
    var toggle = root && root.querySelector('[data-bs-toggle="dropdown"]');
    if (!toggle || !window.bootstrap || !bootstrap.Dropdown) {
        return;
    }
    var inst = bootstrap.Dropdown.getInstance(toggle);
    if (inst) {
        inst.hide();
    }
}

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function clamp01(v) {
    v = Number(v);
    if (!(v >= 0)) {
        return 0;
    }
    if (v > 1) {
        return 1;
    }
    return v;
}

function glossParams(g) {
    g = clamp01(g);
    return {
        roughness: 0.62 - g * 0.48,
        metalness: 0.05 + g * 0.16,
        clearcoat: 0.12 + g * 0.5,
        clearcoatRoughness: 0.22 - g * 0.12,
    };
}

function applyGlossPreset(g) {
    var p = glossParams(g);
    S.lightGloss = clamp01(g);
    S.matRoughness = p.roughness;
    S.matMetalness = p.metalness;
    S.matClearcoat = p.clearcoat;
    S.matClearcoatRoughness = p.clearcoatRoughness;
    return p;
}

function currentMatParams() {
    return {
        roughness: clamp01(S.matRoughness),
        metalness: clamp01(S.matMetalness),
        clearcoat: clamp01(S.matClearcoat),
        clearcoatRoughness: clamp01(S.matClearcoatRoughness),
    };
}

function disposeScene() {
    if (S.rafId) {
        cancelAnimationFrame(S.rafId);
        S.rafId = 0;
    }
    if (S.resizeObserver) {
        try {
            S.resizeObserver.disconnect();
        } catch (e) { /* ignore */ }
        S.resizeObserver = null;
    }
    if (S.controls) {
        try {
            S.controls.dispose();
        } catch (e) { /* ignore */ }
        S.controls = null;
    }
    if (S.scene) {
        if (hooks.clearSectionHelpers) {
            hooks.clearSectionHelpers();
        }
        S.scene.traverse(function (obj) {
            var role = obj.userData && obj.userData.cadRole;
            if (obj.geometry && role !== 'section-stencil') {
                obj.geometry.dispose();
            }
            if (obj.material) {
                var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
                mats.forEach(function (m) {
                    if (m && m.dispose) {
                        m.dispose();
                    }
                });
            }
        });
        S.scene = null;
    }
    S.modelGroup = null;
    S.camera = null;
    S.ambientLight = null;
    S.keyLight = null;
    S.fillLight = null;
    S.pointLight = null;
    S.gridHelper = null;
    S.axesHelper = null;
    S.pivotHelper = null;
    S.measureGroup = null;
    S.measurePreview = null;
    S.measureSegments = [];
    S.measurePending = null;
    S.measuring = false;
    S.nodeMap = {};
    S.nodeIdSeq = 0;
    S.selectedNodeId = null;
    S.selectedNodeIds = [];
    S.isolateBackup = null;
    S.treeQuery = '';
    S.treeVisFilter = 'all';
    S.pointerDownPos = null;
    S.capturingShot = false;
    S.sectionHelpers = [];
    S.sectionPreviewing = false;
    S.sectionCuts = [];
    S.sectionActiveId = null;
    S.explodeUnits = [];
    S.explodeAmount = 0;
    S.explodeSpan = 50;
    S.explodeParentId = null;
    S.explodeStyle = 'radial';
    S.explodeCenterId = null;
    S.explodeEven = true;
    S.explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
    S.alignedView = null;
    if (S.renderer) {
        try {
            S.renderer.dispose();
        } catch (e) { /* ignore */ }
        S.renderer = null;
    }
}

function resizeRenderer() {
    if (!S.renderer || !S.camera || !S.stageEl || S.capturingShot) {
        return;
    }
    var w = S.stageEl.clientWidth || 800;
    var h = S.stageEl.clientHeight || 480;
    if (S.camera.isOrthographicCamera) {
        applyOrthoFrustum(w, h);
    } else {
        S.camera.aspect = w / Math.max(h, 1);
        S.camera.updateProjectionMatrix();
    }
    S.renderer.setSize(w, h, false);
}

function animate() {
    S.rafId = requestAnimationFrame(animate);
    if (S.controls) {
        S.controls.update();
    }
    if (hooks.onFrame) {
        hooks.onFrame();
    }
    if (S.renderer && S.scene && S.camera && !S.capturingShot) {
        S.renderer.render(S.scene, S.camera);
    }
}

function initScene(canvas, container) {
    var w = container.clientWidth || 800;
    var h = container.clientHeight || 480;

    S.renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: true,
        preserveDrawingBuffer: true,
        stencil: false,
    });
    S.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    S.renderer.setSize(w, h, false);
    S.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    S.renderer.toneMappingExposure = 1.12;
    applyCanvasClear(false);
    S.renderer.localClippingEnabled = true;

    S.scene = new THREE.Scene();
    S.camera = new THREE.PerspectiveCamera(45, w / Math.max(h, 1), 0.1, 100000);
    S.camera.up.set(0, 0, 1);
    S.camera.position.set(120, 90, 80);

    S.ambientLight = new THREE.HemisphereLight(0xffffff, 0x6e7a86, 0.95);
    S.scene.add(S.ambientLight);
    S.keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    S.scene.add(S.keyLight);
    S.fillLight = new THREE.DirectionalLight(0xffffff, 0.9);
    S.scene.add(S.fillLight);
    S.pointLight = new THREE.PointLight(0xffffff, 2.8, 0, 2);
    S.pointLight.visible = false;
    S.scene.add(S.pointLight);
    if (hooks.applyLights) {
        hooks.applyLights();
    }

    bindControls(S.camera, canvas);

    S.modelGroup = new THREE.Group();
    S.scene.add(S.modelGroup);

    S.resizeObserver = new ResizeObserver(function () {
        resizeRenderer();
    });
    S.resizeObserver.observe(container);
    animate();
}

function makeSolidMaterial(color) {
    var p = currentMatParams();
    var planes = [];
    var mat = new THREE.MeshPhysicalMaterial({
        color: color,
        roughness: p.roughness,
        metalness: p.metalness,
        clearcoat: p.clearcoat,
        clearcoatRoughness: p.clearcoatRoughness,
        side: THREE.DoubleSide,
        clippingPlanes: planes,
    });
    mat.userData._cadClip = planes;
    return mat;
}

function meshMaterials(mesh) {
    if (!mesh || !mesh.material) {
        return [];
    }
    return Array.isArray(mesh.material) ? mesh.material.filter(Boolean) : [mesh.material];
}

function disposeHelperObject(obj) {
    if (!obj) {
        return;
    }
    while (obj.children && obj.children.length) {
        var child = obj.children[0];
        obj.remove(child);
        disposeHelperObject(child);
    }
    if (obj.geometry && obj.geometry.dispose) {
        obj.geometry.dispose();
    }
    if (obj.material) {
        var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach(function (m) {
            if (m && m.dispose) {
                m.dispose();
            }
        });
    }
}

function eachSolid(fn) {
    if (!S.modelGroup) {
        return;
    }
    S.modelGroup.traverse(function (obj) {
        if (obj.isMesh && obj.userData && obj.userData.cadRole === 'solid') {
            fn(obj);
        }
    });
}

function eachMaterial(obj, fn) {
    var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    mats.forEach(function (m) {
        if (m) {
            fn(m);
        }
    });
}

function objectIsShown(obj) {
    var cur = obj;
    while (cur) {
        if (cur.visible === false) {
            return false;
        }
        cur = cur.parent;
    }
    return true;
}

function cadGroupIsShown(obj) {
    var cur = obj;
    while (cur) {
        var role = cur.userData && cur.userData.cadRole;
        if (role !== 'solid' && role !== 'edges' && cur.visible === false) {
            return false;
        }
        cur = cur.parent;
    }
    return true;
}

function getModelBox(visibleOnly) {
    if (!S.modelGroup || !THREE) {
        return null;
    }
    var box = new THREE.Box3();
    var has = false;
    S.modelGroup.updateWorldMatrix(true, true);
    S.modelGroup.traverse(function (obj) {
        if (!obj.isMesh || !obj.userData || obj.userData.cadRole !== 'solid') {
            return;
        }
        if (visibleOnly && !cadGroupIsShown(obj)) {
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
        box.setFromObject(S.modelGroup);
        if (box.isEmpty()) {
            return null;
        }
    }
    var size = box.getSize(new THREE.Vector3());
    var center = box.getCenter(new THREE.Vector3());
    var maxDim = Math.max(size.x, size.y, size.z, 1);
    return { box: box, size: size, center: center, maxDim: maxDim };
}

function getFitDistance(maxDim) {
    var fov = 45 * Math.PI / 180;
    return (maxDim / 2) / Math.tan(fov / 2) * 1.6;
}

function applyCameraClip(maxDim) {
    if (!S.camera) {
        return;
    }
    S.camera.near = Math.max(maxDim / 1000, 0.01);
    S.camera.far = maxDim * 100;
    S.camera.zoom = 1;
}

function applyOrthoFrustum(w, h) {
    if (!S.camera || !S.camera.isOrthographicCamera) {
        return;
    }
    var aspect = (w || 800) / Math.max(h || 480, 1);
    var half = S.orthoHalf || 50;
    S.camera.left = -half * aspect;
    S.camera.right = half * aspect;
    S.camera.top = half;
    S.camera.bottom = -half;
    S.camera.updateProjectionMatrix();
}

function bindControls(cam, canvas) {
    var target = S.controls ? S.controls.target.clone() : new THREE.Vector3();
    if (S.controls) {
        try {
            S.controls.dispose();
        } catch (e) { /* ignore */ }
    }
    S.controls = new OrbitControls(cam, canvas || S.canvasEl);
    S.controls.enableDamping = true;
    S.controls.dampingFactor = 0.08;
    S.controls.screenSpacePanning = true;
    S.controls.target.copy(target);
    S.controls.addEventListener('start', onOrbitStart);
    S.controls.addEventListener('end', onOrbitEnd);
    return S.controls;
}

function onOrbitStart() {
    S.pivotInteracting = true;
    S.pivotHideAt = 0;
    if (hooks.showPivotHelper) {
        hooks.showPivotHelper(true);
    }
    if (hooks.clearAlignedView) {
        hooks.clearAlignedView();
    }
}

function onOrbitEnd() {
    S.pivotInteracting = false;
    S.pivotHideAt = Date.now() + PIVOT_HOLD_MS;
}

function nodeCenter(id) {
    var rec = S.nodeMap[id];
    if (!rec || !THREE) {
        return null;
    }
    rec.object.updateWorldMatrix(true, true);
    var box = new THREE.Box3().setFromObject(rec.object);
    if (box.isEmpty()) {
        return null;
    }
    return box.getCenter(new THREE.Vector3());
}

function disposeHelper(helper) {
    if (!helper) {
        return;
    }
    if (S.scene) {
        S.scene.remove(helper);
    }
    helper.traverse(function (obj) {
        if (obj.geometry) {
            obj.geometry.dispose();
        }
        if (obj.material) {
            var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            mats.forEach(function (m) {
                if (m && m.dispose) {
                    m.dispose();
                }
            });
        }
    });
}

function getTreeChildren(object) {
    var out = [];
    (object.children || []).forEach(function (child) {
        var id = child.userData && child.userData.cadNodeId;
        if (id && S.nodeMap[id] && S.nodeMap[id].object === child) {
            out.push(child);
        }
    });
    return out;
}

function findCadNode(obj) {
    var cur = obj;
    while (cur) {
        var id = cur.userData && cur.userData.cadNodeId;
        if (id && S.nodeMap[id] && S.nodeMap[id].object === cur) {
            return id;
        }
        cur = cur.parent;
    }
    return null;
}


export { assets, setStatus, setError, canvasClearColor, applyCanvasClear, setHint, setToggleActive, setGroupActive, closeParentDropdown, escapeHtml, clamp01, glossParams, applyGlossPreset, currentMatParams, disposeScene, resizeRenderer, animate, initScene, makeSolidMaterial, meshMaterials, disposeHelperObject, eachSolid, eachMaterial, objectIsShown, cadGroupIsShown, getModelBox, getFitDistance, applyCameraClip, applyOrthoFrustum, bindControls, onOrbitStart, onOrbitEnd, nodeCenter, disposeHelper, getTreeChildren, findCadNode };
