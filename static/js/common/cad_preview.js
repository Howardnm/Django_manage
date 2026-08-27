/**
 * CAD 3D 预览页 — STP / STEP / IGES
 *
 * 仅挂在 attachment:viewer。列表页是普通 <a target="_blank">，不加载本脚本。
 */
(function () {
    'use strict';

    if (window.__CAD_PREVIEW_JS_LOADED) {
        return;
    }
    window.__CAD_PREVIEW_JS_LOADED = true;

    var LARGE_FILE_BYTES = 20 * 1024 * 1024;
    var WORKER_TIMEOUT_MS = 90 * 1000;
    var DEFAULT_COLOR = 0x8a9ba8;
    var DEFAULT_LIGHT_AZIMUTH = 50;
    var DEFAULT_LIGHT_ELEVATION = 46;
    var DEFAULT_LIGHT_INTENSITY = 0.75;
    var DEFAULT_LIGHT_COLOR = '#ffffff';
    var DEFAULT_EXPLODE_BIN_PCT = 2;

    var libsPromise = null;
    var renderer = null;
    var scene = null;
    var camera = null;
    var controls = null;
    var modelGroup = null;
    var ambientLight = null;
    var keyLight = null;
    var fillLight = null;
    var rafId = 0;
    var resizeObserver = null;
    var worker = null;
    var abortController = null;
    var displayMode = 'solid';
    var XRAY_OPACITY = 0.22;
    var canvasEl = null;
    var stageEl = null;
    var pageRoot = null;
    var lightAzimuth = DEFAULT_LIGHT_AZIMUTH;
    var lightElevation = DEFAULT_LIGHT_ELEVATION;
    var lightIntensity = DEFAULT_LIGHT_INTENSITY;
    var lightColor = DEFAULT_LIGHT_COLOR;
    var lightFollow = false;
    var nodeIdSeq = 0;
    var nodeMap = {};
    var selectedNodeId = null;
    var isolateBackup = null;
    var orthoOn = false;
    var gridOn = false;
    var axesOn = false;
    var gridHelper = null;
    var axesHelper = null;
    var currentFileName = 'cad';
    var HIGHLIGHT_EMISSIVE = 0x1a4a7a;
    var pointerDownPos = null;
    var orthoHalf = 50;
    var pivotHelper = null;
    var placingPivot = false;
    var pivotInteracting = false;
    var pivotHideAt = 0;
    var PIVOT_HOLD_MS = 1000;
    var CLIP_PLANES = [];
    var clipPlane = null;
    var clipHelper = null;
    var sectionOn = false;
    var sectionAxis = 'z';
    var sectionOffset = 50;
    var sectionFlip = false;
    var explodeAmount = 0;
    var explodeSpan = 50;
    var explodeUnits = [];
    var explodeParentId = null;
    var explodeStyle = 'radial';
    var explodeCenterId = null;
    var explodeEven = true;
    var explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
    var alignedView = null;
    var ALIGNED_VIEWS = {
        front: { offset: [0, 1, 0], up: [0, 0, 1] },
        back: { offset: [0, -1, 0], up: [0, 0, 1] },
        right: { offset: [1, 0, 0], up: [0, 0, 1] },
        left: { offset: [-1, 0, 0], up: [0, 0, 1] },
        top: { offset: [0, 0, 1], up: [0, 1, 0] },
        bottom: { offset: [0, 0, -1], up: [0, 1, 0] },
    };

    function assets() {
        return window.CAD_PREVIEW_ASSETS || {};
    }

    function $(sel, root) {
        return (root || document).querySelector(sel);
    }

    function loadScript(src) {
        return new Promise(function (resolve, reject) {
            if (!src) {
                reject(new Error('缺少脚本路径'));
                return;
            }
            var existing = document.querySelector('script[data-cad-src="' + src + '"]');
            if (existing) {
                if (existing.getAttribute('data-cad-loaded') === '1') {
                    resolve();
                    return;
                }
                existing.addEventListener('load', function () { resolve(); });
                existing.addEventListener('error', function () { reject(new Error('脚本加载失败')); });
                return;
            }
            var s = document.createElement('script');
            s.src = src;
            s.setAttribute('data-cad-src', src);
            s.onload = function () {
                s.setAttribute('data-cad-loaded', '1');
                resolve();
            };
            s.onerror = function () {
                reject(new Error('脚本加载失败: ' + src));
            };
            document.head.appendChild(s);
        });
    }

    function ensureLibs() {
        if (libsPromise) {
            return libsPromise;
        }
        var a = assets();
        libsPromise = loadScript(a.three)
            .then(function () { return loadScript(a.orbit); })
            .catch(function (err) {
                libsPromise = null;
                throw err;
            });
        return libsPromise;
    }

    function onToolbarClick(ev) {
        var btn = ev.target.closest('[data-cad-action]');
        if (!btn) {
            return;
        }
        var action = btn.getAttribute('data-cad-action');
        if (action === 'solid') {
            ev.preventDefault();
            setDisplayMode('solid');
        } else if (action === 'wireframe') {
            ev.preventDefault();
            setDisplayMode(displayMode === 'wireframe' ? 'solid' : 'wireframe');
        } else if (action === 'xray') {
            ev.preventDefault();
            setDisplayMode(displayMode === 'xray' ? 'solid' : 'xray');
        } else if (action === 'fit') {
            ev.preventDefault();
            fitToView();
            closeParentDropdown(btn);
        } else if (action === 'light') {
            ev.preventDefault();
            hideTreePanel();
            toggleLightPanel();
            closeParentDropdown(btn);
        } else if (action === 'light-close') {
            ev.preventDefault();
            hideLightPanel();
        } else if (action === 'light-reset') {
            ev.preventDefault();
            resetLights();
        } else if (action === 'tree') {
            ev.preventDefault();
            hideLightPanel();
            toggleTreePanel();
        } else if (action === 'tree-close') {
            ev.preventDefault();
            hideTreePanel();
        } else if (action === 'view') {
            ev.preventDefault();
            setPresetView(btn.getAttribute('data-cad-view') || 'iso');
            closeParentDropdown(btn);
        } else if (action === 'view-roll') {
            ev.preventDefault();
            rollAlignedView(Number(btn.getAttribute('data-cad-roll')) || 90);
        } else if (action === 'ortho') {
            ev.preventDefault();
            setOrtho(!orthoOn);
        } else if (action === 'grid') {
            ev.preventDefault();
            setGrid(!gridOn);
        } else if (action === 'axes') {
            ev.preventDefault();
            setAxes(!axesOn);
        } else if (action === 'screenshot') {
            ev.preventDefault();
            captureScreenshot();
        } else if (action === 'place-pivot') {
            ev.preventDefault();
            setPlacingPivot(!placingPivot);
            closeParentDropdown(btn);
        } else if (action === 'section') {
            ev.preventDefault();
            toggleSectionPanel();
            closeParentDropdown(btn);
        } else if (action === 'section-close') {
            ev.preventDefault();
            hideSectionPanel();
        } else if (action === 'section-reset') {
            ev.preventDefault();
            resetSection();
        } else if (action === 'section-axis') {
            ev.preventDefault();
            setSectionAxis(btn.getAttribute('data-cad-axis') || 'z');
        } else if (action === 'explode') {
            ev.preventDefault();
            toggleExplodePanel();
            closeParentDropdown(btn);
        } else if (action === 'explode-close') {
            ev.preventDefault();
            hideExplodePanel();
        } else if (action === 'explode-reset') {
            ev.preventDefault();
            resetExplode();
        } else if (action === 'explode-selected') {
            ev.preventDefault();
            explodeFromSelected();
        } else if (action === 'explode-default') {
            ev.preventDefault();
            explodeToDefault();
        } else if (action === 'explode-style') {
            ev.preventDefault();
            setExplodeStyle(btn.getAttribute('data-cad-explode-style') || 'radial');
        } else if (action === 'explode-center') {
            ev.preventDefault();
            explodeCenterFromSelected();
        } else if (action === 'explode-center-reset') {
            ev.preventDefault();
            explodeCenterId = null;
            recomputeExplodeDirs();
            syncExplodeUi();
        } else if (action === 'pivot-selected') {
            ev.preventDefault();
            pivotToSelected();
        } else if (action === 'isolate') {
            ev.preventDefault();
            isolateSelected();
        } else if (action === 'show-all') {
            ev.preventDefault();
            showAllNodes();
        }
    }

    function setStatus(message) {
        if (!stageEl) {
            return;
        }
        var overlay = $('[data-cad-status]', stageEl);
        var text = $('[data-cad-status-text]', stageEl);
        var error = $('[data-cad-error]', stageEl);
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
        if (!stageEl) {
            return;
        }
        var overlay = $('[data-cad-status]', stageEl);
        var error = $('[data-cad-error]', stageEl);
        var text = $('[data-cad-error-text]', stageEl);
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

    function lightPanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-light-panel]');
    }

    function toggleLightPanel() {
        var panel = lightPanel();
        if (!panel) {
            return;
        }
        if (panel.classList.contains('is-hidden')) {
            showLightPanel();
        } else {
            hideLightPanel();
        }
    }

    function showLightPanel() {
        hideSectionPanel();
        hideExplodePanel();
        var panel = lightPanel();
        if (panel) {
            panel.classList.remove('is-hidden');
        }
        syncLightUi();
        setLightButtonActive(true);
    }

    function hideLightPanel() {
        var panel = lightPanel();
        if (panel) {
            panel.classList.add('is-hidden');
        }
        setLightButtonActive(false);
    }

    function setLightButtonActive(on) {
        var btn = pageRoot && pageRoot.querySelector('[data-cad-action="light"]');
        if (btn) {
            btn.classList.toggle('active', !!on);
        }
        syncGroupToggles();
    }

    function treePanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-tree-panel]');
    }

    function toggleTreePanel() {
        var panel = treePanel();
        if (!panel) {
            return;
        }
        if (panel.classList.contains('is-hidden')) {
            showTreePanel();
        } else {
            hideTreePanel();
        }
    }

    function showTreePanel() {
        var panel = treePanel();
        if (panel) {
            panel.classList.remove('is-hidden');
        }
        setTreeButtonActive(true);
    }

    function hideTreePanel() {
        var panel = treePanel();
        if (panel) {
            panel.classList.add('is-hidden');
        }
        setTreeButtonActive(false);
    }

    function setTreeButtonActive(on) {
        var btn = pageRoot && pageRoot.querySelector('[data-cad-action="tree"]');
        if (btn) {
            btn.classList.toggle('active', !!on);
        }
    }

    function sectionPanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-section-panel]');
    }

    function explodePanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-explode-panel]');
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
        hideLightPanel();
        hideExplodePanel();
        var panel = sectionPanel();
        if (panel) {
            panel.classList.remove('is-hidden');
        }
        if (!sectionOn) {
            setSectionEnabled(true);
        }
        syncSectionUi();
        setToggleActive('section', true);
    }

    function hideSectionPanel() {
        var panel = sectionPanel();
        if (panel) {
            panel.classList.add('is-hidden');
        }
        setToggleActive('section', sectionOn);
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
        hideLightPanel();
        hideSectionPanel();
        var panel = explodePanel();
        if (panel) {
            panel.classList.remove('is-hidden');
        }
        if (!explodeUnits.length) {
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
        setToggleActive('explode', explodeAmount > 0);
    }

    function setToggleActive(action, on) {
        var btn = pageRoot && pageRoot.querySelector('[data-cad-action="' + action + '"]');
        if (btn) {
            btn.classList.toggle('active', !!on);
        }
        syncGroupToggles();
    }

    function setGroupActive(group, on) {
        var btn = pageRoot && pageRoot.querySelector('[data-cad-group="' + group + '"]');
        if (btn) {
            btn.classList.toggle('active', !!on);
        }
    }

    function isPanelOpen(panel) {
        return !!(panel && !panel.classList.contains('is-hidden'));
    }

    function syncGroupToggles() {
        setGroupActive('display', displayMode !== 'solid');
        setGroupActive('view', orthoOn);
        setGroupActive(
            'assist',
            gridOn || axesOn || placingPivot || sectionOn || explodeAmount > 0
                || isPanelOpen(lightPanel())
                || isPanelOpen(sectionPanel())
                || isPanelOpen(explodePanel())
        );
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

    function onLightInput(ev) {
        var input = ev.target.closest('[data-cad-light]');
        if (!input) {
            return;
        }
        var kind = input.getAttribute('data-cad-light');
        if (kind === 'azimuth') {
            lightAzimuth = Number(input.value);
            lightFollow = false;
        } else if (kind === 'elevation') {
            lightElevation = Number(input.value);
            lightFollow = false;
        } else if (kind === 'intensity') {
            lightIntensity = Number(input.value);
        } else if (kind === 'color') {
            lightColor = input.value || DEFAULT_LIGHT_COLOR;
        } else if (kind === 'follow') {
            lightFollow = !!input.checked;
        }
        applyLights();
        syncLightUi();
    }

    function resetLights() {
        lightAzimuth = DEFAULT_LIGHT_AZIMUTH;
        lightElevation = DEFAULT_LIGHT_ELEVATION;
        lightIntensity = DEFAULT_LIGHT_INTENSITY;
        lightColor = DEFAULT_LIGHT_COLOR;
        lightFollow = false;
        applyLights();
        syncLightUi();
    }

    function syncLightUi() {
        var panel = lightPanel();
        if (!panel) {
            return;
        }
        var az = panel.querySelector('[data-cad-light="azimuth"]');
        var el = panel.querySelector('[data-cad-light="elevation"]');
        var ins = panel.querySelector('[data-cad-light="intensity"]');
        var color = panel.querySelector('[data-cad-light="color"]');
        var follow = panel.querySelector('[data-cad-light="follow"]');
        var azVal = panel.querySelector('[data-cad-light-az-val]');
        var elVal = panel.querySelector('[data-cad-light-el-val]');
        var inVal = panel.querySelector('[data-cad-light-in-val]');
        var colorVal = panel.querySelector('[data-cad-light-color-val]');
        if (az) {
            az.value = String(Math.round(lightAzimuth));
            az.disabled = lightFollow;
        }
        if (el) {
            el.value = String(Math.round(lightElevation));
            el.disabled = lightFollow;
        }
        if (ins) {
            ins.value = String(lightIntensity);
        }
        if (color) {
            color.value = lightColor;
        }
        if (follow) {
            follow.checked = lightFollow;
        }
        if (azVal) {
            azVal.textContent = lightFollow ? '跟随' : Math.round(lightAzimuth) + '°';
        }
        if (elVal) {
            elVal.textContent = lightFollow ? '跟随' : Math.round(lightElevation) + '°';
        }
        if (inVal) {
            inVal.textContent = Number(lightIntensity).toFixed(2);
        }
        if (colorVal) {
            colorVal.textContent = lightColor;
        }
        panel.classList.toggle('is-follow', lightFollow);
    }

    function applyLights() {
        if (!keyLight || !fillLight || !ambientLight) {
            return;
        }
        var dir;
        if (lightFollow && camera && controls) {
            dir = camera.position.clone().sub(controls.target);
            if (dir.lengthSq() < 1e-8) {
                dir.set(1, 1, 1);
            }
            dir.normalize();
        } else {
            var az = lightAzimuth * Math.PI / 180;
            var el = lightElevation * Math.PI / 180;
            var cosEl = Math.cos(el);
            dir = {
                x: cosEl * Math.cos(az),
                y: cosEl * Math.sin(az),
                z: Math.sin(el),
            };
        }
        keyLight.position.set(dir.x, dir.y, dir.z);
        keyLight.intensity = lightIntensity;
        fillLight.position.set(-dir.x * 0.55, -dir.y * 0.55, Math.max(dir.z * 0.3, 0.15));
        fillLight.intensity = Math.max(lightIntensity * 0.32, 0.12);
        ambientLight.intensity = 0.38 + lightIntensity * 0.22;
        keyLight.color.set(lightColor);
        fillLight.color.copy(keyLight.color).multiplyScalar(0.55);
        ambientLight.color.copy(keyLight.color).multiplyScalar(0.7);
    }

    function cadFormat(ext) {
        ext = (ext || '').toLowerCase();
        if (ext === 'igs' || ext === 'iges') {
            return 'iges';
        }
        return 'step';
    }

    function disposeWorker() {
        if (worker) {
            try {
                worker.terminate();
            } catch (e) { /* ignore */ }
            worker = null;
        }
    }

    function disposeScene() {
        if (rafId) {
            cancelAnimationFrame(rafId);
            rafId = 0;
        }
        if (resizeObserver) {
            try {
                resizeObserver.disconnect();
            } catch (e) { /* ignore */ }
            resizeObserver = null;
        }
        if (controls) {
            try {
                controls.dispose();
            } catch (e) { /* ignore */ }
            controls = null;
        }
        if (scene) {
            scene.traverse(function (obj) {
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
            scene = null;
        }
        modelGroup = null;
        camera = null;
        ambientLight = null;
        keyLight = null;
        fillLight = null;
        gridHelper = null;
        axesHelper = null;
        pivotHelper = null;
        nodeMap = {};
        nodeIdSeq = 0;
        selectedNodeId = null;
        isolateBackup = null;
        pointerDownPos = null;
        clipHelper = null;
        explodeUnits = [];
        explodeAmount = 0;
        explodeSpan = 50;
        explodeParentId = null;
        explodeStyle = 'radial';
        explodeCenterId = null;
        explodeEven = true;
        explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
        alignedView = null;
        if (renderer) {
            try {
                renderer.dispose();
            } catch (e) { /* ignore */ }
            renderer = null;
        }
    }

    function dispose() {
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
        disposeWorker();
        disposeScene();
        displayMode = 'solid';
        orthoOn = false;
        gridOn = false;
        axesOn = false;
        placingPivot = false;
        pivotInteracting = false;
        pivotHideAt = 0;
        hideLightPanel();
        hideSectionPanel();
        hideExplodePanel();
        hideTreePanel();
        resetTreeDom();
        sectionOn = false;
        sectionAxis = 'z';
        sectionOffset = 50;
        sectionFlip = false;
        explodeAmount = 0;
        explodeStyle = 'radial';
        explodeCenterId = null;
        explodeEven = true;
        explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
        alignedView = null;
        showViewRoll(false);
        CLIP_PLANES.length = 0;
        if (stageEl) {
            stageEl.classList.remove('is-placing-pivot');
        }
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
    }

    function resetTreeDom() {
        var tree = pageRoot && pageRoot.querySelector('[data-cad-tree]');
        if (tree) {
            tree.innerHTML = '<div class="text-muted small px-1">解析完成后显示装配树</div>';
        }
    }

    function resizeRenderer() {
        if (!renderer || !camera || !stageEl) {
            return;
        }
        var w = stageEl.clientWidth || 800;
        var h = stageEl.clientHeight || 480;
        if (camera.isOrthographicCamera) {
            applyOrthoFrustum(w, h);
        } else {
            camera.aspect = w / Math.max(h, 1);
            camera.updateProjectionMatrix();
        }
        renderer.setSize(w, h, false);
    }

    function animate() {
        rafId = requestAnimationFrame(animate);
        if (controls) {
            controls.update();
        }
        if (lightFollow) {
            applyLights();
        }
        syncPivotHelper();
        if (renderer && scene && camera) {
            renderer.render(scene, camera);
        }
    }

    function initScene(canvas, container) {
        var THREE = window.THREE;
        var w = container.clientWidth || 800;
        var h = container.clientHeight || 480;

        renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, preserveDrawingBuffer: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(w, h, false);
        renderer.setClearColor(0xf4f6f8);
        renderer.localClippingEnabled = true;
        ensureClipPlane();

        scene = new THREE.Scene();
        camera = new THREE.PerspectiveCamera(45, w / Math.max(h, 1), 0.1, 100000);
        camera.up.set(0, 0, 1);
        camera.position.set(120, 90, 80);

        ambientLight = new THREE.AmbientLight(0xffffff, 0.55);
        scene.add(ambientLight);
        keyLight = new THREE.DirectionalLight(0xffffff, 0.75);
        scene.add(keyLight);
        fillLight = new THREE.DirectionalLight(0xffffff, 0.25);
        scene.add(fillLight);
        applyLights();

        bindControls(camera, canvas);

        modelGroup = new THREE.Group();
        scene.add(modelGroup);

        resizeObserver = new ResizeObserver(function () {
            resizeRenderer();
        });
        resizeObserver.observe(container);
        animate();
    }

    function makeSolidMaterial(color) {
        var THREE = window.THREE;
        return new THREE.MeshPhongMaterial({
            color: color,
            specular: 0x111111,
            shininess: 8,
            side: THREE.DoubleSide,
            clippingPlanes: CLIP_PLANES,
        });
    }

    function ensureClipPlane() {
        if (!window.THREE || clipPlane) {
            return;
        }
        clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
    }

    function sectionNormal() {
        var THREE = window.THREE;
        var n;
        if (sectionAxis === 'x') {
            n = new THREE.Vector3(1, 0, 0);
        } else if (sectionAxis === 'y') {
            n = new THREE.Vector3(0, 1, 0);
        } else {
            n = new THREE.Vector3(0, 0, 1);
        }
        if (sectionFlip) {
            n.negate();
        }
        return n;
    }

    function setSectionEnabled(on) {
        sectionOn = !!on;
        ensureClipPlane();
        CLIP_PLANES.length = 0;
        if (sectionOn && clipPlane) {
            CLIP_PLANES.push(clipPlane);
            applySectionPlane();
        } else if (clipHelper) {
            clipHelper.visible = false;
        }
        setToggleActive('section', sectionOn || isPanelOpen(sectionPanel()));
    }

    function setSectionAxis(axis) {
        if (axis !== 'x' && axis !== 'y') {
            axis = 'z';
        }
        sectionAxis = axis;
        if (sectionOn) {
            applySectionPlane();
        }
        syncSectionUi();
    }

    function resetSection() {
        sectionAxis = 'z';
        sectionOffset = 50;
        sectionFlip = false;
        setSectionEnabled(false);
        syncSectionUi();
    }

    function applySectionPlane() {
        if (!clipPlane || !window.THREE) {
            return;
        }
        var info = getModelBox(true) || getModelBox(false);
        if (!info) {
            return;
        }
        var axis = sectionAxis === 'x' || sectionAxis === 'y' ? sectionAxis : 'z';
        var min = info.box.min[axis];
        var max = info.box.max[axis];
        var t = Math.max(0, Math.min(100, sectionOffset)) / 100;
        var point = info.center.clone();
        point[axis] = min + (max - min) * t;
        clipPlane.setFromNormalAndCoplanarPoint(sectionNormal(), point);
        updateClipHelper(info);
    }

    function updateClipHelper(info) {
        if (!sectionOn || !scene || !clipPlane || !window.THREE) {
            if (clipHelper) {
                clipHelper.visible = false;
            }
            return;
        }
        var THREE = window.THREE;
        var size = Math.max(info.maxDim * 1.15, 1);
        if (!clipHelper) {
            clipHelper = new THREE.PlaneHelper(clipPlane, size, 0xe67e22);
            clipHelper.name = 'cad-section-helper';
            scene.add(clipHelper);
        } else {
            clipHelper.size = size;
        }
        clipHelper.visible = true;
    }

    function syncSectionUi() {
        var panel = sectionPanel();
        if (!panel) {
            return;
        }
        var off = panel.querySelector('[data-cad-section="offset"]');
        if (off) {
            off.value = String(sectionOffset);
        }
        var offVal = panel.querySelector('[data-cad-section-off-val]');
        if (offVal) {
            offVal.textContent = Math.round(sectionOffset) + '%';
        }
        var flip = panel.querySelector('[data-cad-section="flip"]');
        if (flip) {
            flip.checked = !!sectionFlip;
        }
        var axes = panel.querySelectorAll('[data-cad-action="section-axis"]');
        for (var i = 0; i < axes.length; i++) {
            axes[i].classList.toggle('active', axes[i].getAttribute('data-cad-axis') === sectionAxis);
        }
    }

    function onSectionInput(ev) {
        var input = ev.target.closest('[data-cad-section]');
        if (!input) {
            return;
        }
        var kind = input.getAttribute('data-cad-section');
        if (kind === 'offset') {
            sectionOffset = Number(input.value);
        } else if (kind === 'flip') {
            sectionFlip = !!input.checked;
        } else {
            return;
        }
        if (!sectionOn) {
            setSectionEnabled(true);
        } else {
            applySectionPlane();
        }
        syncSectionUi();
    }

    function findDefaultExplodeParent() {
        var roots = modelGroup ? getTreeChildren(modelGroup) : [];
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
        explodeUnits.forEach(function (u) {
            u.object.position.copy(u.home);
        });
        explodeUnits = [];
        explodeAmount = 0;
    }

    function unionBoxOf(objects) {
        var THREE = window.THREE;
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
        var THREE = window.THREE;
        obj.updateWorldMatrix(true, true);
        var b = new THREE.Box3().setFromObject(obj);
        return b.isEmpty() ? null : b.getCenter(new THREE.Vector3());
    }

    function explodeOriginPoint(fallback) {
        if (explodeCenterId && nodeMap[explodeCenterId]) {
            var center = worldCenterOf(nodeMap[explodeCenterId].object);
            if (center) {
                return center;
            }
        }
        return fallback.clone();
    }

    function explodeMetric(center, origin) {
        if (explodeStyle === 'x') {
            return center.x - origin.x;
        }
        if (explodeStyle === 'y') {
            return center.y - origin.y;
        }
        if (explodeStyle === 'z') {
            return center.z - origin.z;
        }
        return center.distanceTo(origin);
    }

    function computeExplodeDir(center, origin, i, n, obj) {
        var THREE = window.THREE;
        var isOriginPart = !!(explodeCenterId && obj.userData && obj.userData.cadNodeId === explodeCenterId);
        if (explodeStyle === 'x' || explodeStyle === 'y' || explodeStyle === 'z') {
            var axis = new THREE.Vector3(
                explodeStyle === 'x' ? 1 : 0,
                explodeStyle === 'y' ? 1 : 0,
                explodeStyle === 'z' ? 1 : 0
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
        var binPct = Math.max(0.2, Math.min(20, explodeBinPct));
        var delta = Math.max(maxDim * (binPct / 100), 1e-10);
        var coincideEps = Math.max(maxDim * 1e-6, 1e-10);
        explodeUnits.forEach(function (u, i) {
            var center = worldCenterOf(u.object) || origin.clone();
            var metric = explodeMetric(center, origin);
            var id = u.object.userData && u.object.userData.cadNodeId;
            var isOriginPart = !!(explodeCenterId && id === explodeCenterId);
            var rank;
            if (explodeStyle === 'x' || explodeStyle === 'y' || explodeStyle === 'z') {
                rank = Math.round(metric / delta);
            } else {
                rank = Math.floor(Math.abs(metric) / delta);
            }
            if (!isOriginPart && Math.abs(metric) < coincideEps) {
                rank = rank === 0 ? 1 : rank;
                if (u.dir.lengthSq() < 1e-12) {
                    var ang = (i / Math.max(explodeUnits.length, 1)) * Math.PI * 2;
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
        if (!window.THREE || explodeUnits.length < 2) {
            return;
        }
        var THREE = window.THREE;
        var objects = explodeUnits.map(function (u) { return u.object; });
        var union = unionBoxOf(objects);
        var fallback = union.has ? union.box.getCenter(new THREE.Vector3()) : new THREE.Vector3();
        var size = union.has ? union.box.getSize(new THREE.Vector3()) : new THREE.Vector3(1, 1, 1);
        var origin = explodeOriginPoint(fallback);
        var maxDim = Math.max(size.x, size.y, size.z, 1);
        explodeSpan = maxDim * (explodeEven ? 0.12 : 0.55);
        explodeUnits.forEach(function (u, i) {
            var center = worldCenterOf(u.object) || origin.clone();
            u.dir = computeExplodeDir(center, origin, i, explodeUnits.length, u.object);
            u.rank = 1;
        });
        if (explodeEven) {
            assignExplodeRanks(origin, maxDim);
        }
    }

    function recomputeExplodeDirs() {
        if (explodeUnits.length < 2) {
            syncExplodeUi();
            return;
        }
        explodeUnits.forEach(function (u) {
            u.object.position.copy(u.home);
        });
        assignExplodeDirs();
        applyExplode();
        syncExplodeUi();
        setToggleActive('explode', explodeAmount > 0 || isPanelOpen(explodePanel()));
    }

    function setExplodeStyle(style) {
        if (style !== 'x' && style !== 'y' && style !== 'z') {
            style = 'radial';
        }
        explodeStyle = style;
        if (!explodeUnits.length) {
            prepareExplodeUnits();
        } else {
            recomputeExplodeDirs();
        }
        syncExplodeUi();
    }

    function explodeCenterFromSelected() {
        if (!selectedNodeId || !nodeMap[selectedNodeId]) {
            syncExplodeUi();
            return;
        }
        explodeCenterId = selectedNodeId;
        if (!explodeUnits.length) {
            prepareExplodeUnits();
        } else {
            recomputeExplodeDirs();
        }
        showExplodePanel();
        syncExplodeUi();
    }

    function setExplodeUnits(units, parent) {
        restoreExplodeHomes();
        explodeParentId = parent && parent.userData ? parent.userData.cadNodeId : null;
        if (!window.THREE || !units || units.length < 2) {
            explodeUnits = [];
            syncExplodeUi();
            setToggleActive('explode', isPanelOpen(explodePanel()));
            return;
        }
        units.forEach(function (obj) {
            explodeUnits.push({
                object: obj,
                home: obj.position.clone(),
                dir: new window.THREE.Vector3(1, 0, 0),
            });
        });
        assignExplodeDirs();
        applyExplode();
        syncExplodeUi();
        setToggleActive('explode', explodeAmount > 0 || isPanelOpen(explodePanel()));
    }

    function prepareExplodeUnits() {
        var found = findDefaultExplodeParent();
        setExplodeUnits(found.units, found.parent);
    }

    function explodeToDefault() {
        prepareExplodeUnits();
    }

    function explodeFromSelected() {
        if (!selectedNodeId || !nodeMap[selectedNodeId]) {
            syncExplodeUi();
            return;
        }
        var rec = nodeMap[selectedNodeId];
        var kids = getTreeChildren(rec.object);
        setExplodeUnits(kids, rec.object);
        showExplodePanel();
    }

    function applyExplode() {
        var t = Math.max(0, Math.min(300, explodeAmount)) / 100;
        explodeUnits.forEach(function (u) {
            u.object.position.copy(u.home).addScaledVector(u.dir, t * explodeSpan);
        });
        if (sectionOn) {
            applySectionPlane();
        }
    }

    function resetExplode() {
        explodeAmount = 0;
        applyExplode();
        syncExplodeUi();
        setToggleActive('explode', isPanelOpen(explodePanel()));
    }

    function explodeLevelLabel() {
        if (!explodeParentId) {
            return '当前：整棵树（最粗）';
        }
        var rec = nodeMap[explodeParentId];
        var name = rec ? rec.name : explodeParentId;
        return '当前：' + name + ' 的子级（' + explodeUnits.length + '）';
    }

    function explodeCenterLabel() {
        if (explodeCenterId && nodeMap[explodeCenterId]) {
            return '中心：' + nodeMap[explodeCenterId].name;
        }
        return '中心：包围盒';
    }

    function syncExplodeUi() {
        var panel = explodePanel();
        if (!panel) {
            return;
        }
        if (explodeCenterId && !nodeMap[explodeCenterId]) {
            explodeCenterId = null;
        }
        var can = explodeUnits.length >= 2;
        panel.classList.toggle('is-explode-locked', !can);
        var hint = panel.querySelector('[data-cad-explode-hint]');
        if (hint) {
            if (!can && selectedNodeId && explodeParentId === selectedNodeId) {
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
            btn.classList.toggle('active', style === explodeStyle);
        });
        panel.classList.toggle('is-even-off', !explodeEven);
        var even = panel.querySelector('[data-cad-explode="even"]');
        if (even) {
            even.checked = explodeEven;
            even.disabled = !can;
        }
        var bin = panel.querySelector('[data-cad-explode="bin"]');
        if (bin) {
            bin.value = String(explodeBinPct);
            bin.disabled = !can || !explodeEven;
        }
        var binVal = panel.querySelector('[data-cad-explode-bin-val]');
        if (binVal) {
            binVal.textContent = Number(explodeBinPct).toFixed(
                Math.abs(explodeBinPct % 1) < 1e-6 ? 0 : 1
            ) + '%';
        }
        var input = panel.querySelector('[data-cad-explode="amount"]');
        if (input) {
            input.value = String(explodeAmount);
            input.disabled = !can;
        }
        var val = panel.querySelector('[data-cad-explode-val]');
        if (val) {
            val.textContent = Math.round(explodeAmount) + '%';
        }
    }

    function onExplodeInput(ev) {
        var input = ev.target.closest('[data-cad-explode]');
        if (!input) {
            return;
        }
        var kind = input.getAttribute('data-cad-explode');
        if (kind === 'amount') {
            explodeAmount = Number(input.value);
            if (!explodeUnits.length) {
                prepareExplodeUnits();
            }
            applyExplode();
            syncExplodeUi();
            setToggleActive('explode', explodeAmount > 0 || isPanelOpen(explodePanel()));
            return;
        }
        if (kind === 'even') {
            explodeEven = !!input.checked;
            if (!explodeUnits.length) {
                prepareExplodeUnits();
            } else {
                recomputeExplodeDirs();
            }
            return;
        }
        if (kind === 'bin') {
            explodeBinPct = Math.max(0.2, Math.min(20, Number(input.value) || DEFAULT_EXPLODE_BIN_PCT));
            if (!explodeUnits.length) {
                prepareExplodeUnits();
            } else {
                recomputeExplodeDirs();
            }
        }
    }

    function buildMesh(geometryMesh) {
        var THREE = window.THREE;
        var geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
            'position',
            new THREE.Float32BufferAttribute(geometryMesh.attributes.position.array, 3)
        );
        if (geometryMesh.attributes.normal) {
            geometry.setAttribute(
                'normal',
                new THREE.Float32BufferAttribute(geometryMesh.attributes.normal.array, 3)
            );
        }
        var index = Uint32Array.from(geometryMesh.index.array);
        geometry.setIndex(new THREE.BufferAttribute(index, 1));

        var color = geometryMesh.color
            ? new THREE.Color(geometryMesh.color[0], geometryMesh.color[1], geometryMesh.color[2])
            : new THREE.Color(DEFAULT_COLOR);
        var defaultMaterial = makeSolidMaterial(color);
        var materials = [defaultMaterial];

        if (geometryMesh.brep_faces && geometryMesh.brep_faces.length > 0) {
            for (var i = 0; i < geometryMesh.brep_faces.length; i++) {
                var faceColor = geometryMesh.brep_faces[i];
                var c = faceColor.color
                    ? new THREE.Color(faceColor.color[0], faceColor.color[1], faceColor.color[2])
                    : color;
                materials.push(makeSolidMaterial(c));
            }
            var triangleCount = geometryMesh.index.array.length / 3;
            var triangleIndex = 0;
            var faceColorGroupIndex = 0;
            while (triangleIndex < triangleCount) {
                var firstIndex = triangleIndex;
                var lastIndex;
                var materialIndex;
                if (faceColorGroupIndex >= geometryMesh.brep_faces.length) {
                    lastIndex = triangleCount;
                    materialIndex = 0;
                } else if (triangleIndex < geometryMesh.brep_faces[faceColorGroupIndex].first) {
                    lastIndex = geometryMesh.brep_faces[faceColorGroupIndex].first;
                    materialIndex = 0;
                } else {
                    lastIndex = geometryMesh.brep_faces[faceColorGroupIndex].last + 1;
                    materialIndex = faceColorGroupIndex + 1;
                    faceColorGroupIndex++;
                }
                geometry.addGroup(firstIndex * 3, (lastIndex - firstIndex) * 3, materialIndex);
                triangleIndex = lastIndex;
            }
        }

        var mesh = new THREE.Mesh(geometry, materials.length > 1 ? materials : materials[0]);
        mesh.name = geometryMesh.name || '';
        mesh.userData.cadRole = 'solid';

        var group = new THREE.Group();
        group.name = mesh.name;
        group.add(mesh);
        group.add(buildFaceEdges(geometry, index, geometryMesh.brep_faces));
        return group;
    }

    function nextNodeId() {
        nodeIdSeq += 1;
        return 'n' + nodeIdSeq;
    }

    function registerNode(id, object, name, parentId) {
        object.userData.cadNodeId = id;
        nodeMap[id] = { id: id, object: object, name: name, parentId: parentId };
    }

    function uniqueIndices(list) {
        var seen = {};
        var out = [];
        (list || []).forEach(function (idx) {
            if (seen[idx]) {
                return;
            }
            seen[idx] = true;
            out.push(idx);
        });
        return out;
    }

    function nodeLabel(node, fallback) {
        var name = node && node.name ? String(node.name).trim() : '';
        return name || fallback;
    }

    function attachMeshes(group, node, result, parentId, asLeaves) {
        uniqueIndices(node && node.meshes).forEach(function (idx, i) {
            var meshData = result.meshes[idx];
            if (!meshData) {
                return;
            }
            var meshGroup = buildMesh(meshData);
            if (asLeaves) {
                var meshId = nextNodeId();
                var meshName = (meshData.name && String(meshData.name).trim()) || ('零件 ' + (i + 1));
                meshGroup.name = meshName;
                registerNode(meshId, meshGroup, meshName, parentId);
            } else {
                meshGroup.userData.cadNodeId = parentId;
            }
            group.add(meshGroup);
        });
    }

    function buildSceneNode(node, result, parentId, fallbackName) {
        var group = new THREE.Group();
        var id = nextNodeId();
        var name = nodeLabel(node, fallbackName);
        var children = (node && node.children) || [];
        var meshCount = uniqueIndices(node && node.meshes).length;
        group.name = name;
        registerNode(id, group, name, parentId);
        attachMeshes(group, node, result, id, children.length > 0 || meshCount > 1);
        for (var i = 0; i < children.length; i++) {
            group.add(buildSceneNode(children[i], result, id, '组 ' + (i + 1)));
        }
        return group;
    }

    function buildFaceEdges(geometry, indexArray, brepFaces) {
        var THREE = window.THREE;
        var edges = new THREE.Group();
        edges.name = '__cad_edges';
        edges.userData.cadRole = 'edges';
        edges.visible = false;
        var material = new THREE.LineBasicMaterial({
            color: 0x3b4a5a,
            clippingPlanes: CLIP_PLANES,
        });

        if (brepFaces && brepFaces.length) {
            for (var i = 0; i < brepFaces.length; i++) {
                var face = brepFaces[i];
                var first = face.first;
                var last = face.last + 1;
                if (!(last > first)) {
                    continue;
                }
                var inner = new THREE.BufferGeometry();
                inner.setAttribute('position', geometry.attributes.position);
                inner.setIndex(new THREE.BufferAttribute(indexArray.slice(first * 3, last * 3), 1));
                // EdgesGeometry 会拷贝边界顶点；inner 与实体网格共享 position，不能 dispose。
                edges.add(new THREE.LineSegments(new THREE.EdgesGeometry(inner, 180), material));
            }
        } else {
            edges.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), material));
        }
        return edges;
    }

    function addMeshes(result, fallbackName) {
        if (!modelGroup || !result || !result.meshes) {
            return 0;
        }
        nodeIdSeq = 0;
        nodeMap = {};
        selectedNodeId = null;
        isolateBackup = null;
        explodeUnits = [];
        explodeAmount = 0;
        explodeParentId = null;
        explodeStyle = 'radial';
        explodeCenterId = null;
        explodeEven = true;
        explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
        alignedView = null;
        showViewRoll(false);
        while (modelGroup.children.length) {
            modelGroup.remove(modelGroup.children[0]);
        }
        var root = result.root;
        if (!root) {
            root = {
                name: fallbackName || '模型',
                meshes: result.meshes.map(function (_, i) { return i; }),
                children: [],
            };
        }
        modelGroup.add(buildSceneNode(root, result, null, fallbackName || '模型'));
        return result.meshes.length;
    }

    function eachMaterial(obj, fn) {
        var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach(function (m) {
            if (m) {
                fn(m);
            }
        });
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
        displayMode = mode;
        if (modelGroup) {
            modelGroup.traverse(function (obj) {
                var role = obj.userData && obj.userData.cadRole;
                if (role === 'solid') {
                    obj.visible = displayMode !== 'wireframe';
                    eachMaterial(obj, function (m) {
                        applyXrayMaterial(m, displayMode === 'xray');
                    });
                } else if (role === 'edges') {
                    obj.visible = displayMode !== 'solid';
                }
            });
        }
        setToggleActive('solid', displayMode === 'solid');
        setToggleActive('wireframe', displayMode === 'wireframe');
        setToggleActive('xray', displayMode === 'xray');
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
        if (!modelGroup || !window.THREE) {
            return null;
        }
        var THREE = window.THREE;
        var box = new THREE.Box3();
        var has = false;
        modelGroup.updateWorldMatrix(true, true);
        modelGroup.traverse(function (obj) {
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
            box.setFromObject(modelGroup);
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
        if (!camera) {
            return;
        }
        camera.near = Math.max(maxDim / 1000, 0.01);
        camera.far = maxDim * 100;
        camera.zoom = 1;
    }

    function applyOrthoFrustum(w, h) {
        if (!camera || !camera.isOrthographicCamera) {
            return;
        }
        var aspect = (w || 800) / Math.max(h || 480, 1);
        var half = orthoHalf || 50;
        camera.left = -half * aspect;
        camera.right = half * aspect;
        camera.top = half;
        camera.bottom = -half;
        camera.updateProjectionMatrix();
    }

    function normalizeViewKind(kind) {
        if (kind === 'side') {
            return 'right';
        }
        return kind || 'iso';
    }

    function viewRollEl() {
        return stageEl && stageEl.querySelector('[data-cad-view-roll]');
    }

    function showViewRoll(on) {
        var el = viewRollEl();
        if (el) {
            el.classList.toggle('is-hidden', !on);
        }
    }

    function clearAlignedView() {
        alignedView = null;
        showViewRoll(false);
    }

    function bindControls(cam, canvas) {
        var THREE = window.THREE;
        var target = controls ? controls.target.clone() : new THREE.Vector3();
        if (controls) {
            try {
                controls.dispose();
            } catch (e) { /* ignore */ }
        }
        controls = new THREE.OrbitControls(cam, canvas || canvasEl);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.screenSpacePanning = true;
        controls.target.copy(target);
        controls.addEventListener('start', onOrbitStart);
        controls.addEventListener('end', onOrbitEnd);
        return controls;
    }

    function onOrbitStart() {
        pivotInteracting = true;
        pivotHideAt = 0;
        showPivotHelper(true);
        clearAlignedView();
    }

    function onOrbitEnd() {
        pivotInteracting = false;
        pivotHideAt = Date.now() + PIVOT_HOLD_MS;
    }

    function nodeCenter(id) {
        var rec = nodeMap[id];
        if (!rec || !window.THREE) {
            return null;
        }
        rec.object.updateWorldMatrix(true, true);
        var box = new THREE.Box3().setFromObject(rec.object);
        if (box.isEmpty()) {
            return null;
        }
        return box.getCenter(new THREE.Vector3());
    }

    function setOrbitTarget(point, keepDistance) {
        if (!controls || !camera || !point) {
            return;
        }
        if (keepDistance) {
            var offset = camera.position.clone().sub(controls.target);
            controls.target.copy(point);
            camera.position.copy(point).add(offset);
        } else {
            controls.target.copy(point);
        }
        camera.lookAt(controls.target);
        controls.update();
        ensurePivotHelper();
        if (pivotHelper) {
            pivotHelper.position.copy(point);
            pivotHelper.quaternion.identity();
        }
        showPivotHelper(true);
        pivotHideAt = Date.now() + PIVOT_HOLD_MS * 1.6;
    }

    function ensurePivotHelper() {
        if (pivotHelper || !scene || !window.THREE) {
            return;
        }
        var THREE = window.THREE;
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
        group.add(ring);
        group.visible = false;
        scene.add(group);
        pivotHelper = group;
        syncPivotHelper();
    }

    function showPivotHelper(on) {
        ensurePivotHelper();
        if (pivotHelper) {
            pivotHelper.visible = !!on;
        }
    }

    function syncPivotHelper() {
        if (!pivotHelper || !controls) {
            return;
        }
        pivotHelper.position.copy(controls.target);
        var info = getModelBox(false);
        var size = info ? Math.max(info.maxDim * 0.035, 0.6) : 8;
        pivotHelper.scale.set(size, size, size);
        if (pivotInteracting || placingPivot) {
            pivotHelper.visible = true;
            return;
        }
        if (pivotHideAt && Date.now() < pivotHideAt) {
            pivotHelper.visible = true;
            return;
        }
        pivotHelper.visible = false;
    }

    function setPlacingPivot(on) {
        placingPivot = !!on;
        if (stageEl) {
            stageEl.classList.toggle('is-placing-pivot', placingPivot);
        }
        setToggleActive('place-pivot', placingPivot);
        if (placingPivot) {
            showPivotHelper(true);
        }
    }

    function onPivotKeydown(ev) {
        if (ev.key === 'Escape' && placingPivot) {
            setPlacingPivot(false);
        }
    }

    function pivotToSelected() {
        if (!selectedNodeId) {
            return;
        }
        var center = nodeCenter(selectedNodeId);
        if (center) {
            setOrbitTarget(center, true);
            setPlacingPivot(false);
        }
    }

    function applyViewTransform(kind, info) {
        var center = info.center;
        var dist = getFitDistance(info.maxDim);
        applyCameraClip(info.maxDim);
        kind = normalizeViewKind(kind);
        var preset = ALIGNED_VIEWS[kind];
        if (preset) {
            camera.up.fromArray(preset.up);
            camera.position.set(
                center.x + preset.offset[0] * dist,
                center.y + preset.offset[1] * dist,
                center.z + preset.offset[2] * dist
            );
            alignedView = kind;
            showViewRoll(true);
        } else {
            camera.up.set(0, 0, 1);
            camera.position.set(center.x + dist, center.y + dist * 0.8, center.z + dist * 0.55);
            clearAlignedView();
        }
        if (camera.isOrthographicCamera) {
            orthoHalf = info.maxDim * 0.9;
            applyOrthoFrustum(stageEl && stageEl.clientWidth, stageEl && stageEl.clientHeight);
        } else {
            camera.updateProjectionMatrix();
        }
        bindControls(camera, canvasEl);
        controls.target.copy(center);
        camera.lookAt(center);
        controls.update();
    }

    function rollAlignedView(deg) {
        if (!alignedView || !camera || !controls || !window.THREE) {
            return;
        }
        var THREE = window.THREE;
        var target = controls.target.clone();
        var viewDir = target.clone().sub(camera.position);
        if (viewDir.lengthSq() < 1e-12) {
            return;
        }
        viewDir.normalize();
        // 画面顺时针 = 相机绕视线逆时针（屏幕坐标 y 向下）。
        var angle = -THREE.MathUtils.degToRad(deg);
        camera.up.applyQuaternion(new THREE.Quaternion().setFromAxisAngle(viewDir, angle));
        camera.lookAt(target);
        bindControls(camera, canvasEl);
        controls.target.copy(target);
        controls.update();
        showViewRoll(true);
    }

    function fitToView() {
        setPresetView('iso');
    }

    function setPresetView(kind) {
        if (!modelGroup || !camera || !controls || !window.THREE) {
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
        if (!window.THREE || !camera || !controls || !stageEl) {
            return;
        }
        var THREE = window.THREE;
        var w = stageEl.clientWidth || 800;
        var h = stageEl.clientHeight || 480;
        var pos = camera.position.clone();
        var target = controls.target.clone();
        var up = camera.up.clone();
        var info = getModelBox(true) || getModelBox(false);
        var maxDim = info ? info.maxDim : 100;
        orthoOn = !!on;
        if (orthoOn) {
            orthoHalf = maxDim * 0.9;
            camera = new THREE.OrthographicCamera(-1, 1, 1, -1, Math.max(maxDim / 1000, 0.01), maxDim * 100);
            applyOrthoFrustum(w, h);
        } else {
            camera = new THREE.PerspectiveCamera(45, w / Math.max(h, 1), Math.max(maxDim / 1000, 0.01), maxDim * 100);
            camera.updateProjectionMatrix();
        }
        camera.up.copy(up);
        camera.position.copy(pos);
        camera.lookAt(target);
        bindControls(camera, canvasEl);
        controls.target.copy(target);
        controls.update();
        setToggleActive('ortho', orthoOn);
    }

    function disposeHelper(helper) {
        if (!helper) {
            return;
        }
        if (scene) {
            scene.remove(helper);
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

    function syncHelpers(info) {
        info = info || getModelBox(false);
        if (!info || !scene || !window.THREE) {
            return;
        }
        if (gridOn) {
            rebuildGrid(info);
        }
        if (axesOn) {
            rebuildAxes(info);
        }
    }

    function rebuildGrid(info) {
        var THREE = window.THREE;
        disposeHelper(gridHelper);
        var size = Math.max(info.maxDim * 2.2, 1);
        var divisions = 20;
        gridHelper = new THREE.GridHelper(size, divisions, 0xb0b8c4, 0xd8dde5);
        gridHelper.rotation.x = Math.PI / 2;
        gridHelper.position.set(info.center.x, info.center.y, info.box.min.z);
        scene.add(gridHelper);
    }

    function rebuildAxes(info) {
        var THREE = window.THREE;
        disposeHelper(axesHelper);
        axesHelper = new THREE.AxesHelper(info.maxDim * 0.28);
        axesHelper.position.copy(info.box.min);
        scene.add(axesHelper);
    }

    function setGrid(on) {
        gridOn = !!on;
        if (gridOn) {
            syncHelpers();
        } else {
            disposeHelper(gridHelper);
            gridHelper = null;
        }
        setToggleActive('grid', gridOn);
    }

    function setAxes(on) {
        axesOn = !!on;
        if (axesOn) {
            syncHelpers();
        } else {
            disposeHelper(axesHelper);
            axesHelper = null;
        }
        setToggleActive('axes', axesOn);
    }

    function captureScreenshot() {
        if (!renderer || !scene || !camera || !canvasEl) {
            return;
        }
        var hidden = [];
        var els = stageEl ? stageEl.querySelectorAll(
            '[data-cad-status], [data-cad-error], [data-cad-light-panel], [data-cad-tree-panel], [data-cad-section-panel], [data-cad-explode-panel], [data-cad-view-roll]'
        ) : [];
        for (var i = 0; i < els.length; i++) {
            if (!els[i].classList.contains('is-hidden')) {
                els[i].classList.add('is-hidden');
                hidden.push(els[i]);
            }
        }
        var pivotWasVisible = pivotHelper && pivotHelper.visible;
        if (pivotHelper) {
            pivotHelper.visible = false;
        }
        var clipWasVisible = clipHelper && clipHelper.visible;
        if (clipHelper) {
            clipHelper.visible = false;
        }
        renderer.render(scene, camera);
        var base = String(currentFileName || 'cad')
            .replace(/\.[^.]+$/, '')
            .replace(/[\\/:*?"<>|]+/g, '_')
            .trim() || 'cad';
        canvasEl.toBlob(function (blob) {
            hidden.forEach(function (el) {
                el.classList.remove('is-hidden');
            });
            if (pivotHelper) {
                pivotHelper.visible = !!pivotWasVisible;
            }
            if (clipHelper) {
                clipHelper.visible = !!clipWasVisible;
            }
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

    function getTreeChildren(object) {
        var out = [];
        (object.children || []).forEach(function (child) {
            var id = child.userData && child.userData.cadNodeId;
            if (id && nodeMap[id] && nodeMap[id].object === child) {
                out.push(child);
            }
        });
        return out;
    }

    function renderTree() {
        var tree = pageRoot && pageRoot.querySelector('[data-cad-tree]');
        if (!tree) {
            return;
        }
        var roots = modelGroup ? getTreeChildren(modelGroup) : [];
        if (!roots.length) {
            tree.innerHTML = '<div class="text-muted small px-1">无可显示的结构</div>';
            return;
        }
        tree.innerHTML = '<ul class="cad-preview-tree-list">' + roots.map(renderTreeNode).join('') + '</ul>';
    }

    function renderTreeNode(object) {
        var id = object.userData.cadNodeId;
        var rec = nodeMap[id];
        var kids = getTreeChildren(object);
        var isLeaf = kids.length === 0;
        var hidden = !object.visible;
        var selected = id === selectedNodeId;
        var cls = 'cad-preview-tree-node';
        if (hidden) {
            cls += ' is-hidden-node';
        }
        if (selected) {
            cls += ' is-selected';
        }
        var toggleCls = 'cad-preview-tree-toggle' + (isLeaf ? ' is-leaf' : '');
        var eyeIcon = hidden ? 'ti ti-eye-off' : 'ti ti-eye';
        var name = rec ? rec.name : id;
        var childrenHtml = kids.length ? '<ul>' + kids.map(renderTreeNode).join('') + '</ul>' : '';
        return '<li class="' + cls + '" data-cad-tree-node="' + id + '">' +
            '<div class="cad-preview-tree-row">' +
            '<button type="button" class="' + toggleCls + '" data-cad-tree-toggle="' + id + '" aria-label="展开">' +
            '<i class="ti ti-chevron-down"></i></button>' +
            '<button type="button" class="cad-preview-tree-vis" data-cad-tree-vis="' + id + '" aria-label="显隐">' +
            '<i class="' + eyeIcon + '"></i></button>' +
            '<span class="cad-preview-tree-label" data-cad-tree-select="' + id + '" title="' + escapeHtml(name) + '">' +
            escapeHtml(name) + '</span></div>' + childrenHtml + '</li>';
    }

    function onTreeClick(ev) {
        var toggle = ev.target.closest('[data-cad-tree-toggle]');
        if (toggle) {
            ev.preventDefault();
            if (!toggle.classList.contains('is-leaf')) {
                var foldLi = toggle.closest('[data-cad-tree-node]');
                if (foldLi) {
                    foldLi.classList.toggle('is-collapsed');
                }
            }
            return;
        }
        var vis = ev.target.closest('[data-cad-tree-vis]');
        if (vis) {
            ev.preventDefault();
            toggleNodeVisible(vis.getAttribute('data-cad-tree-vis'));
            return;
        }
        var sel = ev.target.closest('[data-cad-tree-select]');
        if (sel) {
            ev.preventDefault();
            selectNode(sel.getAttribute('data-cad-tree-select'));
        }
    }

    function toggleNodeVisible(id) {
        var rec = nodeMap[id];
        if (!rec) {
            return;
        }
        rec.object.visible = !rec.object.visible;
        syncTreeNodeUi(id);
    }

    function syncTreeNodeUi(id) {
        var rec = nodeMap[id];
        var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
        if (!rec || !li) {
            return;
        }
        li.classList.toggle('is-hidden-node', !rec.object.visible);
        var row = li.querySelector('.cad-preview-tree-row');
        var icon = row && row.querySelector('.cad-preview-tree-vis i');
        if (icon) {
            icon.className = rec.object.visible ? 'ti ti-eye' : 'ti ti-eye-off';
        }
    }

    function refreshTreeVisibility() {
        Object.keys(nodeMap).forEach(syncTreeNodeUi);
    }

    function eachSolidMaterial(nodeId, fn) {
        var rec = nodeMap[nodeId];
        if (!rec) {
            return;
        }
        rec.object.traverse(function (obj) {
            if (!obj.userData || obj.userData.cadRole !== 'solid') {
                return;
            }
            var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            mats.forEach(function (m) {
                if (m && m.emissive) {
                    fn(m);
                }
            });
        });
    }

    function restoreEmissive(nodeId) {
        eachSolidMaterial(nodeId, function (m) {
            if (m.userData && m.userData._cadEmissiveOrig != null) {
                m.emissive.setHex(m.userData._cadEmissiveOrig);
            }
        });
    }

    function applyEmissive(nodeId) {
        eachSolidMaterial(nodeId, function (m) {
            if (!m.userData) {
                m.userData = {};
            }
            if (m.userData._cadEmissiveOrig == null) {
                m.userData._cadEmissiveOrig = m.emissive.getHex();
            }
            m.emissive.setHex(HIGHLIGHT_EMISSIVE);
        });
    }

    function selectNode(id) {
        if (selectedNodeId && selectedNodeId !== id) {
            restoreEmissive(selectedNodeId);
            var prev = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + selectedNodeId + '"]');
            if (prev) {
                prev.classList.remove('is-selected');
            }
        }
        selectedNodeId = id || null;
        if (!selectedNodeId || !nodeMap[selectedNodeId]) {
            selectedNodeId = null;
            return;
        }
        applyEmissive(selectedNodeId);
        var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + selectedNodeId + '"]');
        if (!li) {
            return;
        }
        li.classList.add('is-selected');
        var p = li.parentElement;
        while (p) {
            if (p.classList && p.classList.contains('cad-preview-tree-node')) {
                p.classList.remove('is-collapsed');
            }
            p = p.parentElement;
        }
        if (typeof li.scrollIntoView === 'function') {
            li.scrollIntoView({ block: 'nearest' });
        }
    }

    function isOnSelectedPath(id) {
        if (!selectedNodeId) {
            return false;
        }
        if (id === selectedNodeId) {
            return true;
        }
        var cur = selectedNodeId;
        while (cur) {
            if (cur === id) {
                return true;
            }
            cur = nodeMap[cur] ? nodeMap[cur].parentId : null;
        }
        cur = id;
        while (cur) {
            if (cur === selectedNodeId) {
                return true;
            }
            cur = nodeMap[cur] ? nodeMap[cur].parentId : null;
        }
        return false;
    }

    function isolateSelected() {
        if (!selectedNodeId || !nodeMap[selectedNodeId]) {
            return;
        }
        if (!isolateBackup) {
            isolateBackup = {};
            Object.keys(nodeMap).forEach(function (id) {
                isolateBackup[id] = nodeMap[id].object.visible;
            });
        }
        Object.keys(nodeMap).forEach(function (id) {
            nodeMap[id].object.visible = isOnSelectedPath(id);
        });
        refreshTreeVisibility();
    }

    function showAllNodes() {
        isolateBackup = null;
        Object.keys(nodeMap).forEach(function (id) {
            nodeMap[id].object.visible = true;
        });
        refreshTreeVisibility();
    }

    function findCadNode(obj) {
        var cur = obj;
        while (cur) {
            var id = cur.userData && cur.userData.cadNodeId;
            if (id && nodeMap[id] && nodeMap[id].object === cur) {
                return id;
            }
            cur = cur.parent;
        }
        return null;
    }

    function onCanvasPointerDown(ev) {
        if (ev.button !== 0) {
            pointerDownPos = null;
            return;
        }
        pointerDownPos = { x: ev.clientX, y: ev.clientY };
    }

    function onCanvasPointerUp(ev) {
        if (!pointerDownPos || ev.button !== 0) {
            pointerDownPos = null;
            return;
        }
        var dx = ev.clientX - pointerDownPos.x;
        var dy = ev.clientY - pointerDownPos.y;
        pointerDownPos = null;
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
            selectNode(id);
            var center = nodeCenter(id);
            if (center) {
                setOrbitTarget(center, true);
            }
        }
    }

    function collectPickTargets() {
        var targets = [];
        if (!modelGroup) {
            return targets;
        }
        modelGroup.traverse(function (obj) {
            var role = obj.userData && obj.userData.cadRole;
            if (displayMode === 'wireframe') {
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
        if (!renderer || !camera || !modelGroup || !canvasEl || !window.THREE) {
            return null;
        }
        var THREE = window.THREE;
        var rect = canvasEl.getBoundingClientRect();
        if (!rect.width || !rect.height) {
            return null;
        }
        var x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
        var y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
        var raycaster = new THREE.Raycaster();
        var info = getModelBox(false);
        raycaster.params.Line = { threshold: info ? Math.max(info.maxDim * 0.008, 0.4) : 1 };
        raycaster.setFromCamera(new THREE.Vector2(x, y), camera);
        var hits = raycaster.intersectObjects(collectPickTargets(), false);
        return hits.length ? hits[0] : null;
    }

    function pickCanvas(ev) {
        var hit = raycastModel(ev);
        if (placingPivot) {
            if (hit) {
                setOrbitTarget(hit.point.clone(), true);
            }
            setPlacingPivot(false);
            if (hit) {
                var id = findCadNode(hit.object);
                if (id) {
                    selectNode(id);
                }
            }
            return;
        }
        if (!hit) {
            selectNode(null);
            return;
        }
        var nodeId = findCadNode(hit.object);
        if (nodeId) {
            selectNode(nodeId);
        }
    }

    function parseInWorker(buffer, ext) {
        return new Promise(function (resolve, reject) {
            var a = assets();
            if (!a.worker) {
                reject(new Error('未配置 CAD worker'));
                return;
            }
            disposeWorker();
            worker = new Worker(a.worker);
            var timer = setTimeout(function () {
                disposeWorker();
                reject(new Error('timeout'));
            }, WORKER_TIMEOUT_MS);
            worker.onmessage = function (ev) {
                clearTimeout(timer);
                resolve(ev.data);
            };
            worker.onerror = function (ev) {
                clearTimeout(timer);
                reject(ev.error || new Error(ev.message || 'Worker 解析失败'));
            };
            var u8 = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
            worker.postMessage({
                format: cadFormat(ext),
                buffer: u8,
                params: null,
            });
        });
    }

    function humanSize(bytes) {
        if (!bytes) {
            return '';
        }
        if (bytes < 1024) {
            return bytes + ' B';
        }
        if (bytes < 1024 * 1024) {
            return (bytes / 1024).toFixed(1) + ' KB';
        }
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    async function loadModel(opts) {
        setStatus('正在加载 3D 引擎…');
        await ensureLibs();
        if (!window.THREE || !window.THREE.OrbitControls) {
            throw new Error('3D 引擎加载失败');
        }

        if (!renderer) {
            initScene(canvasEl, stageEl);
        }

        if (opts.size > LARGE_FILE_BYTES) {
            setStatus('文件较大（' + humanSize(opts.size) + '），正在下载，解析可能较慢…');
        } else {
            setStatus('正在下载文件…');
        }

        abortController = new AbortController();
        var response;
        try {
            response = await fetch(opts.url, {
                credentials: 'same-origin',
                signal: abortController.signal,
            });
        } catch (err) {
            if (err && err.name === 'AbortError') {
                return;
            }
            throw new Error('文件下载失败，请稍后重试');
        }

        if (response.status === 403) {
            setError('无权预览该文件');
            return;
        }
        if (!response.ok) {
            setError('文件下载失败，请稍后重试');
            return;
        }

        var buffer = await response.arrayBuffer();
        if (!buffer || buffer.byteLength === 0) {
            setError('文件为空，无法预览');
            return;
        }

        setStatus('正在解析模型，大文件可能需要较长时间…');
        var result;
        try {
            result = await parseInWorker(buffer, opts.ext);
        } catch (err) {
            if (String(err && err.message) === 'timeout') {
                setError('解析超时。模型过大或过于复杂，请下载后使用 CAD 软件打开');
                return;
            }
            setError('模型过大或过于复杂，浏览器无法预览。请下载后使用 CAD 软件打开');
            return;
        }

        if (!result || result.success === false || !result.meshes || !result.meshes.length) {
            setError('无法解析该 CAD 文件。请确认是 STEP/IGES，或下载后用专业软件打开');
            return;
        }

        currentFileName = opts.name || 'cad';
        addMeshes(result, currentFileName);
        renderTree();
        setDisplayMode('solid');
        syncExplodeUi();
        if (sectionOn) {
            applySectionPlane();
        }
        fitToView();
        setStatus('');
    }

    async function mount(container, opts) {
        dispose();
        stageEl = container;
        pageRoot = container.closest('.cad-preview-page') || container;
        canvasEl = container.querySelector('canvas') || document.createElement('canvas');
        if (!canvasEl.parentNode) {
            canvasEl.className = 'cad-preview-canvas';
            container.appendChild(canvasEl);
        }
        if (!pageRoot.__cadToolbarBound) {
            pageRoot.addEventListener('click', onToolbarClick);
            pageRoot.addEventListener('click', onTreeClick);
            pageRoot.addEventListener('input', onLightInput);
            pageRoot.addEventListener('change', onLightInput);
            pageRoot.addEventListener('input', onSectionInput);
            pageRoot.addEventListener('change', onSectionInput);
            pageRoot.addEventListener('input', onExplodeInput);
            pageRoot.addEventListener('change', onExplodeInput);
            document.addEventListener('keydown', onPivotKeydown);
            pageRoot.__cadToolbarBound = true;
        }
        if (canvasEl && !canvasEl.__cadPickBound) {
            canvasEl.addEventListener('pointerdown', onCanvasPointerDown);
            canvasEl.addEventListener('pointerup', onCanvasPointerUp);
            canvasEl.addEventListener('dblclick', onCanvasDblClick);
            canvasEl.__cadPickBound = true;
        }
        setStatus('正在加载 3D 引擎…');
        try {
            await loadModel(opts);
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
})();
