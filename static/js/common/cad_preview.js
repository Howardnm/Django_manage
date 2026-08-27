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
    var DEFAULT_LIGHT_KIND = 'area';
    var DEFAULT_LIGHT_DISTANCE = 1.5;
    var DEFAULT_LIGHT_GLOSS = 0.35;
    var DEFAULT_EXPLODE_BIN_PCT = 2;
    var TREE_AUTO_COLLAPSE_MIN = 12;
    var DEFAULT_HINT = '拖动旋转 · 滚轮缩放 · 右键平移 · 双击零件设为旋转中心';
    var MEASURE_HINT = '单击两点测距 · 可连续标注 · 靠近端点吸附 · Esc 退出';
    var MEASURE_COLOR = 0x206bc4;

    var libsPromise = null;
    var renderer = null;
    var scene = null;
    var camera = null;
    var controls = null;
    var modelGroup = null;
    var ambientLight = null;
    var keyLight = null;
    var fillLight = null;
    var pointLight = null;
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
    var lightKind = DEFAULT_LIGHT_KIND;
    var lightDistance = DEFAULT_LIGHT_DISTANCE;
    var lightGloss = DEFAULT_LIGHT_GLOSS;
    var nodeIdSeq = 0;
    var nodeMap = {};
    var selectedNodeId = null;
    var isolateBackup = null;
    var treeQuery = '';
    var treeVisFilter = 'all';
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
    var measuring = false;
    var measureSegments = [];
    var measurePending = null;
    var measureGroup = null;
    var measurePreview = null;
    var darkCanvas = false;
    var shotIncludeMeasure = true;
    var shotIncludeHelpers = true;
    var shotIncludeHighlight = true;
    var shotAlpha = false;
    var shotScale = 2;
    var shotSize = 0;
    var capturingShot = false;
    var CLEAR_COLOR_LIGHT = 0xf4f6f8;
    var CLEAR_COLOR_DARK = 0x1c2330;
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
        } else if (action === 'dark') {
            ev.preventDefault();
            setDarkCanvas(!darkCanvas);
        } else if (action === 'display-panel') {
            ev.preventDefault();
            toggleDisplayPanel();
            closeParentDropdown(btn);
        } else if (action === 'display-close') {
            ev.preventDefault();
            hideDisplayPanel();
        } else if (action === 'part-color') {
            ev.preventDefault();
            applySelectedPartColor();
        } else if (action === 'part-color-reset') {
            ev.preventDefault();
            restorePartColor(selectedNodeId);
        } else if (action === 'part-color-reset-all') {
            ev.preventDefault();
            restorePartColor(null);
        } else if (action === 'shot-scale') {
            ev.preventDefault();
            setShotScale(Number(btn.getAttribute('data-cad-shot-scale')));
        } else if (action === 'shot-size') {
            ev.preventDefault();
            setShotSize(Number(btn.getAttribute('data-cad-shot-size')));
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
        } else if (action === 'light-kind') {
            ev.preventDefault();
            setLightKind(btn.getAttribute('data-cad-light-kind') || 'area');
        } else if (action === 'tree') {
            ev.preventDefault();
            hideLightPanel();
            toggleTreePanel();
        } else if (action === 'tree-close') {
            ev.preventDefault();
            hideTreePanel();
        } else if (action === 'tree-filter') {
            ev.preventDefault();
            setTreeVisFilter(btn.getAttribute('data-cad-tree-filter') || 'all');
        } else if (action === 'tree-expand-all') {
            ev.preventDefault();
            expandAllTreeNodes();
        } else if (action === 'tree-collapse-all') {
            ev.preventDefault();
            collapseAllTreeNodes();
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
            toggleShotPanel();
        } else if (action === 'shot-close') {
            ev.preventDefault();
            hideShotPanel();
        } else if (action === 'shot-export') {
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
        } else if (action === 'measure') {
            ev.preventDefault();
            toggleMeasurePanel();
            closeParentDropdown(btn);
        } else if (action === 'measure-close') {
            ev.preventDefault();
            hideMeasurePanel();
        } else if (action === 'measure-clear') {
            ev.preventDefault();
            clearMeasure();
        } else if (action === 'measure-remove') {
            ev.preventDefault();
            removeMeasureSegment(Number(btn.getAttribute('data-cad-measure-index')));
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
        hideMeasurePanel();
        hideDisplayPanel();
        hideShotPanel();
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
        hideMeasurePanel();
        hideDisplayPanel();
        hideShotPanel();
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
        hideMeasurePanel();
        hideDisplayPanel();
        hideShotPanel();
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

    function measurePanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-measure-panel]');
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
        hideLightPanel();
        hideSectionPanel();
        hideExplodePanel();
        hideDisplayPanel();
        hideShotPanel();
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

    function displayPanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-display-panel]');
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
        hideLightPanel();
        hideSectionPanel();
        hideExplodePanel();
        hideMeasurePanel();
        hideShotPanel();
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

    function shotPanel() {
        return pageRoot && pageRoot.querySelector('[data-cad-shot-panel]');
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
        hideLightPanel();
        hideSectionPanel();
        hideExplodePanel();
        hideMeasurePanel();
        hideDisplayPanel();
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

    function canvasClearColor() {
        return darkCanvas ? CLEAR_COLOR_DARK : CLEAR_COLOR_LIGHT;
    }

    function applyCanvasClear(alpha) {
        if (!renderer) {
            return;
        }
        if (alpha) {
            renderer.setClearColor(0x000000, 0);
        } else {
            renderer.setClearColor(canvasClearColor(), 1);
        }
    }

    function setDarkCanvas(on) {
        darkCanvas = !!on;
        if (stageEl) {
            stageEl.classList.toggle('is-dark', darkCanvas);
        }
        applyCanvasClear(false);
        if (gridOn) {
            syncHelpers();
        }
        setToggleActive('dark', darkCanvas);
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
        if (!nodeId || !nodeMap[nodeId]) {
            return;
        }
        eachSolidMaterial(nodeId, function (m) {
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
        var ids = nodeId ? [nodeId] : Object.keys(nodeMap);
        ids.forEach(function (id) {
            eachSolidMaterial(id, function (m) {
                if (m.color && m.userData && m.userData._cadColorOrig != null) {
                    m.color.setHex(m.userData._cadColorOrig);
                    m.needsUpdate = true;
                }
            });
        });
        syncDisplayUi();
    }

    function applySelectedPartColor() {
        if (!selectedNodeId) {
            return;
        }
        var input = pageRoot && pageRoot.querySelector('[data-cad-part-color]');
        applyPartColor(selectedNodeId, parseCssColor(input && input.value));
        syncDisplayUi();
    }

    function selectedPartColorHex() {
        var hex = null;
        if (!selectedNodeId) {
            return DEFAULT_COLOR;
        }
        eachSolidMaterial(selectedNodeId, function (m) {
            if (hex == null && m.color) {
                hex = m.color.getHex();
            }
        });
        return hex == null ? DEFAULT_COLOR : hex;
    }

    function setShotScale(n) {
        n = Math.round(Number(n));
        if (!(n >= 1 && n <= 8)) {
            n = 2;
        }
        shotScale = n;
        syncShotUi();
    }

    function setShotSize(n) {
        n = Number(n) || 0;
        if (n !== 1920 && n !== 2560 && n !== 3840) {
            n = 0;
        }
        shotSize = n;
        syncShotUi();
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
            shotIncludeMeasure = !!input.checked;
        } else if (kind === 'helpers') {
            shotIncludeHelpers = !!input.checked;
        } else if (kind === 'highlight') {
            shotIncludeHighlight = !!input.checked;
        } else if (kind === 'alpha') {
            shotAlpha = !!input.checked;
        }
    }

    function syncDisplayUi() {
        var panel = displayPanel();
        if (!panel) {
            return;
        }
        var darkEl = panel.querySelector('[data-cad-dark]');
        if (darkEl) {
            darkEl.checked = darkCanvas;
        }
        var nameEl = panel.querySelector('[data-cad-part-name]');
        var rec = selectedNodeId && nodeMap[selectedNodeId];
        if (nameEl) {
            nameEl.textContent = rec ? (rec.name || selectedNodeId) : '（无选中）';
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

    function syncShotUi() {
        var panel = shotPanel();
        if (!panel) {
            return;
        }
        var shotMap = {
            measure: shotIncludeMeasure,
            helpers: shotIncludeHelpers,
            highlight: shotIncludeHighlight,
            alpha: shotAlpha,
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
                Number(scaleBtns[i].getAttribute('data-cad-shot-scale')) === shotScale
            );
        }
        var sizeBtns = panel.querySelectorAll('[data-cad-action="shot-size"]');
        var j;
        for (j = 0; j < sizeBtns.length; j++) {
            sizeBtns[j].classList.toggle(
                'active',
                Number(sizeBtns[j].getAttribute('data-cad-shot-size')) === shotSize
            );
        }
    }

    function setHint(text) {
        var hint = pageRoot && pageRoot.querySelector('[data-cad-hint]');
        if (hint) {
            hint.textContent = text || DEFAULT_HINT;
        }
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
        if (placingPivot) {
            setPlacingPivot(false);
        }
        measuring = true;
        if (stageEl) {
            stageEl.classList.toggle('is-measuring', true);
        }
        setHint(MEASURE_HINT);
        setToggleActive('measure', true);
    }

    function exitMeasuring() {
        measuring = false;
        hideMeasurePreview();
        if (stageEl) {
            stageEl.classList.remove('is-measuring');
        }
        setHint(DEFAULT_HINT);
        setToggleActive('measure', isPanelOpen(measurePanel()) || hasMeasureGeom());
    }

    function ensureMeasureGroup() {
        if (!scene || !window.THREE) {
            return null;
        }
        if (!measureGroup) {
            measureGroup = new window.THREE.Group();
            measureGroup.name = '__cad_measure';
            scene.add(measureGroup);
        }
        return measureGroup;
    }

    function measureMarkerSize() {
        var info = getModelBox(false);
        var maxDim = info ? info.maxDim : 50;
        return Math.max(maxDim * 0.012, 0.25);
    }

    function measureSnapRadius() {
        var info = getModelBox(false);
        var maxDim = info ? info.maxDim : 50;
        var dist = 80;
        if (camera && controls) {
            dist = camera.position.distanceTo(controls.target);
        }
        return Math.max(maxDim * 0.01, dist * 0.012, 0.2);
    }

    function measureLineMaterial(color) {
        return new window.THREE.LineBasicMaterial({
            color: color == null ? MEASURE_COLOR : color,
            depthTest: false,
            depthWrite: false,
        });
    }

    function addMeasureLine(group, a, b, mat) {
        var line = new window.THREE.Line(
            new window.THREE.BufferGeometry().setFromPoints([a, b]),
            mat
        );
        line.renderOrder = 10;
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
        var THREE = window.THREE;
        var group = new THREE.Group();
        var mat = measureLineMaterial(color);
        addMeasureLine(group, new THREE.Vector3(-1, 0, 0), new THREE.Vector3(1, 0, 0), mat);
        addMeasureLine(group, new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 1, 0), mat);
        addMeasureLine(group, new THREE.Vector3(0, 0, -1), new THREE.Vector3(0, 0, 1), mat);
        return group;
    }

    function addMeasureArrow(group, from, to, size, mat) {
        var THREE = window.THREE;
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

    function worldVertex(obj, attr, index) {
        return new window.THREE.Vector3().fromBufferAttribute(attr, index).applyMatrix4(obj.matrixWorld);
    }

    function hitCandidateVertices(hit) {
        var obj = hit && hit.object;
        var geom = obj && obj.geometry;
        var attr = geom && geom.attributes && geom.attributes.position;
        if (!attr || !window.THREE) {
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
            return { point: null, snapped: false };
        }
        var best = point;
        var bestDist = measureSnapRadius();
        var snapped = false;
        hitCandidateVertices(hit).forEach(function (v) {
            var d = v.distanceTo(point);
            if (d < bestDist) {
                bestDist = d;
                best = v;
                snapped = true;
            }
        });
        return { point: best, snapped: snapped };
    }

    function hideMeasurePreview() {
        if (measurePreview) {
            measurePreview.visible = false;
        }
    }

    function showMeasurePreview(point, snapped) {
        var THREE = window.THREE;
        if (!point || !THREE || !scene) {
            hideMeasurePreview();
            return;
        }
        if (!measurePreview) {
            measurePreview = makeMeasureMark(MEASURE_COLOR);
            measurePreview.name = '__cad_measure_preview';
            scene.add(measurePreview);
        }
        measurePreview.position.copy(point);
        measurePreview.scale.setScalar(measureMarkerSize() * (snapped ? 1 : 0.7));
        setMeasureMarkColor(measurePreview, snapped ? 0xe67e22 : MEASURE_COLOR);
        measurePreview.visible = true;
    }

    function rebuildMeasureGeom() {
        var THREE = window.THREE;
        var group = ensureMeasureGroup();
        if (!group || !THREE) {
            return;
        }
        clearMeasureChildren(group);
        var size = measureMarkerSize();
        var mat = measureLineMaterial();
        function addMark(p) {
            var mark = makeMeasureMark(MEASURE_COLOR);
            mark.position.copy(p);
            mark.scale.setScalar(size);
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
        measureSegments.forEach(function (seg) {
            addSegment(seg.a, seg.b);
        });
        if (measurePending) {
            addMark(measurePending);
        }
        updateMeasureLabel();
    }

    function hasMeasureGeom() {
        return measureSegments.length > 0 || !!measurePending;
    }

    function clearMeasure() {
        measureSegments = [];
        measurePending = null;
        hideMeasurePreview();
        rebuildMeasureGeom();
        syncMeasureUi();
        if (!measuring) {
            setToggleActive('measure', isPanelOpen(measurePanel()));
        }
    }

    function removeMeasureSegment(index) {
        if (!Number.isInteger(index) || index < 0 || index >= measureSegments.length) {
            return;
        }
        measureSegments.splice(index, 1);
        rebuildMeasureGeom();
        syncMeasureUi();
        if (!measuring && !hasMeasureGeom()) {
            setToggleActive('measure', isPanelOpen(measurePanel()));
        }
    }

    function addMeasurePoint(point) {
        if (!point || !window.THREE) {
            return;
        }
        var p = point.clone();
        if (!measurePending) {
            measurePending = p;
        } else {
            measureSegments.push({ a: measurePending, b: p });
            measurePending = null;
        }
        rebuildMeasureGeom();
        syncMeasureUi();
        setToggleActive('measure', true);
    }

    function selectedNodeBox() {
        if (!selectedNodeId || !nodeMap[selectedNodeId] || !window.THREE) {
            return null;
        }
        var rec = nodeMap[selectedNodeId];
        rec.object.updateWorldMatrix(true, true);
        var THREE = window.THREE;
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
            name: rec.name || selectedNodeId,
            size: size,
            diagonal: size.length(),
        };
    }

    function syncMeasureUi() {
        if (!pageRoot) {
            return;
        }
        var distEl = pageRoot.querySelector('[data-cad-measure="distance"]');
        var n = measureSegments.length;
        if (distEl) {
            if (measurePending) {
                distEl.textContent = n ? ('点第二点（已 ' + n + ' 条）') : '点第二点';
            } else if (!n) {
                distEl.textContent = measuring ? '点第一点' : '—';
            } else if (n === 1) {
                distEl.textContent = formatMeasure(measureSegments[0].a.distanceTo(measureSegments[0].b));
            } else {
                var last = measureSegments[n - 1];
                distEl.textContent = formatMeasure(last.a.distanceTo(last.b)) + '（共 ' + n + ' 条）';
            }
        }
        var listEl = pageRoot.querySelector('[data-cad-measure="list"]');
        if (listEl) {
            if (!n) {
                listEl.innerHTML = '';
                listEl.classList.add('is-hidden');
            } else {
                listEl.innerHTML = measureSegments.map(function (seg, i) {
                    return '<div class="cad-preview-measure-item">' +
                        '<span>' + (i + 1) + '. ' + escapeHtml(formatMeasure(seg.a.distanceTo(seg.b))) + '</span>' +
                        '<button type="button" class="btn btn-sm btn-ghost-secondary cad-preview-measure-remove"' +
                        ' data-cad-action="measure-remove" data-cad-measure-index="' + i + '" title="删除此标注">×</button>' +
                        '</div>';
                }).join('');
                listEl.classList.remove('is-hidden');
            }
        }
        var box = selectedNodeBox();
        var nameEl = pageRoot.querySelector('[data-cad-measure="name"]');
        var sizeEl = pageRoot.querySelector('[data-cad-measure="size"]');
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
                sizeEl.textContent = measuring
                    ? '在结构树或退出量测后点选零件'
                    : '点选零件查看包围盒';
            }
        }
        updateMeasureLabel();
    }

    function updateMeasureLabel() {
        if (!pageRoot || !camera || !canvasEl || !window.THREE) {
            return;
        }
        var labels = pageRoot.querySelectorAll('[data-cad-measure-label]');
        if (!labels.length) {
            return;
        }
        var parent = labels[0].parentNode;
        var n = measureSegments.length;
        while (labels.length < n) {
            parent.appendChild(labels[0].cloneNode(true));
            labels = pageRoot.querySelectorAll('[data-cad-measure-label]');
        }
        var rect = canvasEl.getBoundingClientRect();
        var i;
        for (i = 0; i < labels.length; i++) {
            var el = labels[i];
            if (i >= n) {
                el.classList.add('is-hidden');
                continue;
            }
            var a = measureSegments[i].a;
            var b = measureSegments[i].b;
            var mid = a.clone().add(b).multiplyScalar(0.5);
            var ndc = mid.project(camera);
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
        setGroupActive(
            'display',
            displayMode !== 'solid' || darkCanvas
                || isPanelOpen(displayPanel())
                || isPanelOpen(lightPanel())
        );
        setGroupActive('view', orthoOn);
        setGroupActive('assist', gridOn || axesOn || placingPivot);
        setGroupActive(
            'tools',
            measuring || sectionOn || explodeAmount > 0
                || isPanelOpen(sectionPanel())
                || isPanelOpen(explodePanel())
                || isPanelOpen(measurePanel())
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
        } else if (kind === 'distance') {
            lightDistance = Number(input.value);
            if (!(lightDistance > 0)) {
                lightDistance = DEFAULT_LIGHT_DISTANCE;
            }
        } else if (kind === 'gloss') {
            lightGloss = Number(input.value);
            if (!(lightGloss >= 0)) {
                lightGloss = 0;
            }
            if (lightGloss > 1) {
                lightGloss = 1;
            }
            applyMaterialGloss();
        }
        applyLights();
        syncLightUi();
    }

    function setLightKind(kind) {
        lightKind = kind === 'point' ? 'point' : 'area';
        applyLights();
        syncLightUi();
    }

    function resetLights() {
        lightAzimuth = DEFAULT_LIGHT_AZIMUTH;
        lightElevation = DEFAULT_LIGHT_ELEVATION;
        lightIntensity = DEFAULT_LIGHT_INTENSITY;
        lightColor = DEFAULT_LIGHT_COLOR;
        lightFollow = false;
        lightKind = DEFAULT_LIGHT_KIND;
        lightDistance = DEFAULT_LIGHT_DISTANCE;
        lightGloss = DEFAULT_LIGHT_GLOSS;
        applyLights();
        applyMaterialGloss();
        syncLightUi();
    }

    function glossParams(g) {
        g = Math.max(0, Math.min(1, Number(g) || 0));
        var spec = Math.round(g * 210);
        return {
            hex: (spec << 16) | (spec << 8) | spec,
            shininess: 1 + g * 30 + g * g * 70,
        };
    }

    function applyMaterialGloss() {
        if (!modelGroup) {
            return;
        }
        var p = glossParams(lightGloss);
        var seen = [];
        modelGroup.traverse(function (obj) {
            if (!obj.userData || obj.userData.cadRole !== 'solid') {
                return;
            }
            var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            mats.forEach(function (m) {
                if (!m || !m.specular || seen.indexOf(m) !== -1) {
                    return;
                }
                seen.push(m);
                m.specular.setHex(p.hex);
                m.shininess = p.shininess;
                m.needsUpdate = true;
            });
        });
    }

    function lightDirection() {
        var THREE = window.THREE;
        var dir = new THREE.Vector3();
        if (lightFollow && camera && controls) {
            dir.copy(camera.position).sub(controls.target);
            if (dir.lengthSq() < 1e-8) {
                dir.set(1, 1, 1);
            }
            return dir.normalize();
        }
        var az = lightAzimuth * Math.PI / 180;
        var el = lightElevation * Math.PI / 180;
        var cosEl = Math.cos(el);
        return dir.set(cosEl * Math.cos(az), cosEl * Math.sin(az), Math.sin(el));
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
        var dist = panel.querySelector('[data-cad-light="distance"]');
        var gloss = panel.querySelector('[data-cad-light="gloss"]');
        var azVal = panel.querySelector('[data-cad-light-az-val]');
        var elVal = panel.querySelector('[data-cad-light-el-val]');
        var inVal = panel.querySelector('[data-cad-light-in-val]');
        var colorVal = panel.querySelector('[data-cad-light-color-val]');
        var distVal = panel.querySelector('[data-cad-light-dist-val]');
        var glossVal = panel.querySelector('[data-cad-light-gloss-val]');
        var isPoint = lightKind === 'point';
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
        if (dist) {
            dist.value = String(lightDistance);
            dist.disabled = !isPoint;
        }
        if (gloss) {
            gloss.value = String(lightGloss);
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
        if (distVal) {
            distVal.textContent = Number(lightDistance).toFixed(1) + '×';
        }
        if (glossVal) {
            glossVal.textContent = Math.round(lightGloss * 100) + '%';
        }
        panel.querySelectorAll('[data-cad-light-kind]').forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-cad-light-kind') === lightKind);
        });
        panel.classList.toggle('is-follow', lightFollow);
        panel.classList.toggle('is-point', isPoint);
    }

    function applyLights() {
        if (!keyLight || !fillLight || !ambientLight) {
            return;
        }
        var dir = lightDirection();
        var isPoint = lightKind === 'point';
        keyLight.visible = !isPoint;
        fillLight.visible = !isPoint;
        if (pointLight) {
            pointLight.visible = isPoint;
        }
        keyLight.color.set(lightColor);
        fillLight.color.copy(keyLight.color).multiplyScalar(0.55);
        ambientLight.color.copy(keyLight.color).multiplyScalar(0.7);
        ambientLight.intensity = 0.38 + lightIntensity * 0.22;
        if (isPoint && pointLight) {
            var info = getModelBox(false);
            var maxDim = info ? info.maxDim : 80;
            var dist = Math.max(maxDim * lightDistance, 1);
            if (info) {
                pointLight.position.copy(info.center).addScaledVector(dir, dist);
            } else {
                pointLight.position.copy(dir).multiplyScalar(dist);
            }
            pointLight.color.set(lightColor);
            pointLight.intensity = lightIntensity * 2.8;
            pointLight.distance = dist + maxDim * 1.8;
            pointLight.decay = 2;
            return;
        }
        keyLight.position.copy(dir);
        keyLight.intensity = lightIntensity;
        fillLight.position.set(-dir.x * 0.55, -dir.y * 0.55, Math.max(dir.z * 0.3, 0.15));
        fillLight.intensity = Math.max(lightIntensity * 0.32, 0.12);
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
        pointLight = null;
        gridHelper = null;
        axesHelper = null;
        pivotHelper = null;
        measureGroup = null;
        measurePreview = null;
        measureSegments = [];
        measurePending = null;
        measuring = false;
        nodeMap = {};
        nodeIdSeq = 0;
        selectedNodeId = null;
        isolateBackup = null;
        treeQuery = '';
        treeVisFilter = 'all';
        pointerDownPos = null;
        capturingShot = false;
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
        hideMeasurePanel();
        hideDisplayPanel();
        hideShotPanel();
        hideTreePanel();
        resetTreeDom();
        clearMeasure();
        setHint(DEFAULT_HINT);
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
            stageEl.classList.remove('is-measuring');
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
    }

    function resetTreeDom() {
        resetTreeFilterState();
        var tree = pageRoot && pageRoot.querySelector('[data-cad-tree]');
        if (tree) {
            tree.innerHTML = '<div class="text-muted small px-1">解析完成后显示装配树</div>';
        }
    }

    function resizeRenderer() {
        if (!renderer || !camera || !stageEl || capturingShot) {
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
        updateMeasureLabel();
        if (renderer && scene && camera && !capturingShot) {
            renderer.render(scene, camera);
        }
    }

    function initScene(canvas, container) {
        var THREE = window.THREE;
        var w = container.clientWidth || 800;
        var h = container.clientHeight || 480;

        renderer = new THREE.WebGLRenderer({
            canvas: canvas,
            antialias: true,
            alpha: true,
            preserveDrawingBuffer: true,
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(w, h, false);
        applyCanvasClear(false);
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
        pointLight = new THREE.PointLight(0xffffff, 0.75, 0, 2);
        pointLight.visible = false;
        scene.add(pointLight);
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
        var p = glossParams(lightGloss);
        return new THREE.MeshPhongMaterial({
            color: color,
            specular: p.hex,
            shininess: p.shininess,
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
        syncMeasureUi();
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
        resetTreeFilterState();
        hideMeasurePanel();
        clearMeasure();
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
        cacheLeafCounts();
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
            if (measuring) {
                hideMeasurePanel();
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
        if (placingPivot) {
            setPlacingPivot(false);
            return;
        }
        if (measuring) {
            hideMeasurePanel();
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
        gridHelper = new THREE.GridHelper(
            size,
            divisions,
            darkCanvas ? 0x5b6778 : 0xb0b8c4,
            darkCanvas ? 0x2f3948 : 0xd8dde5
        );
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
        if (!renderer || !scene || !camera || !canvasEl || capturingShot) {
            return;
        }
        capturingShot = true;
        hideMeasurePreview();
        var hidden = [];
        var els = stageEl ? stageEl.querySelectorAll(
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
        hide3d(pivotHelper);
        hide3d(clipHelper);
        if (!shotIncludeMeasure) {
            hide3d(measureGroup);
            hide3d(measurePreview);
        }
        if (!shotIncludeHelpers) {
            hide3d(gridHelper);
            hide3d(axesHelper);
        }
        var highlightHidden = false;
        if (!shotIncludeHighlight && selectedNodeId) {
            restoreEmissive(selectedNodeId);
            highlightHidden = true;
        }

        var liveW = (stageEl && stageEl.clientWidth) || 800;
        var liveH = (stageEl && stageEl.clientHeight) || 480;
        var liveRatio = Math.min(window.devicePixelRatio || 1, 2);
        var w = liveW;
        var h = liveH;
        if (shotSize > 0) {
            var longSide = Math.max(liveW, liveH) || 1;
            var k = shotSize / longSide;
            w = Math.max(1, Math.round(liveW * k));
            h = Math.max(1, Math.round(liveH * k));
        }
        var scale = shotScale;
        var maxDim = 8192;
        try {
            var gl = renderer.getContext();
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

        if (camera.isOrthographicCamera) {
            applyOrthoFrustum(w, h);
        } else {
            camera.aspect = w / Math.max(h, 1);
            camera.updateProjectionMatrix();
        }
        renderer.setPixelRatio(scale);
        renderer.setSize(w, h, false);
        applyCanvasClear(shotAlpha);
        renderer.render(scene, camera);

        var base = String(currentFileName || 'cad')
            .replace(/\.[^.]+$/, '')
            .replace(/[\\/:*?"<>|]+/g, '_')
            .trim() || 'cad';
        canvasEl.toBlob(function (blob) {
            hidden.forEach(function (el) {
                el.classList.remove('is-hidden');
            });
            hidden3d.forEach(function (obj) {
                obj.visible = true;
            });
            if (highlightHidden && selectedNodeId) {
                applyEmissive(selectedNodeId);
            }
            if (camera) {
                if (camera.isOrthographicCamera) {
                    applyOrthoFrustum(liveW, liveH);
                } else {
                    camera.aspect = liveW / Math.max(liveH, 1);
                    camera.updateProjectionMatrix();
                }
            }
            if (renderer) {
                renderer.setPixelRatio(liveRatio);
                renderer.setSize(liveW, liveH, false);
                applyCanvasClear(false);
            }
            capturingShot = false;
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

    function resetTreeFilterState() {
        treeQuery = '';
        treeVisFilter = 'all';
        if (!pageRoot) {
            return;
        }
        var search = pageRoot.querySelector('[data-cad-tree-search]');
        if (search) {
            search.value = '';
        }
        var group = pageRoot.querySelector('.cad-preview-tree-filters');
        if (group) {
            group.setAttribute('data-cad-tree-filter', 'all');
            var chips = group.querySelectorAll('[data-cad-action="tree-filter"]');
            for (var i = 0; i < chips.length; i++) {
                chips[i].classList.toggle('active', chips[i].getAttribute('data-cad-tree-filter') === 'all');
            }
        }
        var empty = pageRoot.querySelector('[data-cad-tree-empty]');
        if (empty) {
            empty.classList.add('is-hidden');
        }
        var tree = pageRoot.querySelector('[data-cad-tree]');
        if (tree) {
            tree.classList.remove('is-hidden');
        }
        var stats = pageRoot.querySelector('[data-cad-tree-stats]');
        if (stats) {
            stats.textContent = '';
        }
    }

    function cacheLeafCounts() {
        Object.keys(nodeMap).forEach(function (id) {
            nodeMap[id].leafCount = 0;
        });
        Object.keys(nodeMap).forEach(function (id) {
            var rec = nodeMap[id];
            if (!rec || getTreeChildren(rec.object).length) {
                return;
            }
            rec.leafCount = 1;
            var cur = rec.parentId;
            while (cur && nodeMap[cur]) {
                nodeMap[cur].leafCount += 1;
                cur = nodeMap[cur].parentId;
            }
        });
    }

    function treeLeafTotal() {
        if (!modelGroup) {
            return 0;
        }
        var total = 0;
        getTreeChildren(modelGroup).forEach(function (root) {
            var rec = nodeMap[root.userData && root.userData.cadNodeId];
            total += rec && rec.leafCount ? rec.leafCount : 0;
        });
        return total;
    }

    function objectIsShown(object) {
        var cur = object;
        while (cur) {
            if (cur.visible === false) {
                return false;
            }
            cur = cur.parent;
        }
        return true;
    }

    function hiddenLeafCount() {
        var hidden = 0;
        Object.keys(nodeMap).forEach(function (id) {
            var rec = nodeMap[id];
            if (!rec || getTreeChildren(rec.object).length) {
                return;
            }
            if (!objectIsShown(rec.object)) {
                hidden += 1;
            }
        });
        return hidden;
    }

    function treeFilterOn() {
        return !!(treeQuery && treeQuery.trim()) || treeVisFilter !== 'all';
    }

    function nodeMatchesFilter(rec) {
        if (!rec) {
            return false;
        }
        var query = (treeQuery || '').trim().toLowerCase();
        if (query && String(rec.name || '').toLowerCase().indexOf(query) === -1) {
            return false;
        }
        if (treeVisFilter === 'visible') {
            return !!rec.object.visible;
        }
        if (treeVisFilter === 'hidden') {
            return !rec.object.visible;
        }
        return true;
    }

    function expandTreeAncestors(id) {
        var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
        var p = li && li.parentElement;
        while (p) {
            if (p.classList && p.classList.contains('cad-preview-tree-node')) {
                p.classList.remove('is-collapsed');
            }
            p = p.parentElement;
        }
    }

    function updateTreeStats(hitCount) {
        var stats = pageRoot && pageRoot.querySelector('[data-cad-tree-stats]');
        if (!stats) {
            return;
        }
        var text = treeLeafTotal() + ' 件 · 隐藏 ' + hiddenLeafCount();
        if (treeFilterOn() && hitCount != null) {
            text += ' · 匹配 ' + hitCount;
        }
        stats.textContent = text;
    }

    function applyTreeFilter() {
        if (!pageRoot) {
            return;
        }
        var filterOn = treeFilterOn();
        var hits = {};
        var hitCount = 0;
        Object.keys(nodeMap).forEach(function (id) {
            if (nodeMatchesFilter(nodeMap[id])) {
                hits[id] = true;
                hitCount += 1;
            }
        });
        var keep = {};
        if (filterOn) {
            Object.keys(hits).forEach(function (id) {
                var cur = id;
                while (cur) {
                    keep[cur] = true;
                    cur = nodeMap[cur] ? nodeMap[cur].parentId : null;
                }
            });
        }
        var nodes = pageRoot.querySelectorAll('[data-cad-tree-node]');
        for (var i = 0; i < nodes.length; i++) {
            var li = nodes[i];
            var id = li.getAttribute('data-cad-tree-node');
            li.classList.toggle('is-filtered-out', filterOn && !keep[id]);
        }
        if (filterOn) {
            Object.keys(hits).forEach(expandTreeAncestors);
        }
        var noMatch = filterOn && hitCount === 0;
        var empty = pageRoot.querySelector('[data-cad-tree-empty]');
        if (empty) {
            empty.classList.toggle('is-hidden', !noMatch);
        }
        var tree = pageRoot.querySelector('[data-cad-tree]');
        if (tree) {
            tree.classList.toggle('is-hidden', noMatch);
        }
        updateTreeStats(hitCount);
    }

    function autoCollapseLargeGroups() {
        Object.keys(nodeMap).forEach(function (id) {
            var rec = nodeMap[id];
            if (!rec || rec.parentId == null) {
                return;
            }
            if (getTreeChildren(rec.object).length < TREE_AUTO_COLLAPSE_MIN) {
                return;
            }
            var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
            if (li) {
                li.classList.add('is-collapsed');
            }
        });
    }

    function setTreeVisFilter(kind) {
        treeVisFilter = kind === 'visible' || kind === 'hidden' ? kind : 'all';
        var group = pageRoot && pageRoot.querySelector('.cad-preview-tree-filters');
        if (group) {
            group.setAttribute('data-cad-tree-filter', treeVisFilter);
            var chips = group.querySelectorAll('[data-cad-action="tree-filter"]');
            for (var i = 0; i < chips.length; i++) {
                chips[i].classList.toggle(
                    'active',
                    chips[i].getAttribute('data-cad-tree-filter') === treeVisFilter
                );
            }
        }
        applyTreeFilter();
    }

    function expandAllTreeNodes() {
        if (!pageRoot) {
            return;
        }
        var nodes = pageRoot.querySelectorAll('[data-cad-tree-node]');
        for (var i = 0; i < nodes.length; i++) {
            nodes[i].classList.remove('is-collapsed');
        }
    }

    function collapseAllTreeNodes() {
        Object.keys(nodeMap).forEach(function (id) {
            var rec = nodeMap[id];
            if (!rec || rec.parentId == null) {
                return;
            }
            if (!getTreeChildren(rec.object).length) {
                return;
            }
            var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + id + '"]');
            if (li) {
                li.classList.add('is-collapsed');
            }
        });
    }

    function onTreeSearchInput(ev) {
        var input = ev.target && ev.target.closest && ev.target.closest('[data-cad-tree-search]');
        if (!input) {
            return;
        }
        treeQuery = input.value || '';
        applyTreeFilter();
    }

    function onTreeSearchKeydown(ev) {
        if (ev.key !== 'Escape') {
            return;
        }
        var input = ev.target && ev.target.closest && ev.target.closest('[data-cad-tree-search]');
        if (!input || !input.value) {
            return;
        }
        ev.preventDefault();
        input.value = '';
        treeQuery = '';
        applyTreeFilter();
    }

    function renderTree() {
        var tree = pageRoot && pageRoot.querySelector('[data-cad-tree]');
        if (!tree) {
            return;
        }
        var roots = modelGroup ? getTreeChildren(modelGroup) : [];
        if (!roots.length) {
            tree.classList.remove('is-hidden');
            tree.innerHTML = '<div class="text-muted small px-1">无可显示的结构</div>';
            var empty = pageRoot.querySelector('[data-cad-tree-empty]');
            if (empty) {
                empty.classList.add('is-hidden');
            }
            updateTreeStats(0);
            return;
        }
        tree.innerHTML = '<ul class="cad-preview-tree-list">' + roots.map(renderTreeNode).join('') + '</ul>';
        autoCollapseLargeGroups();
        applyTreeFilter();
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
        var countHtml = '';
        if (!isLeaf && rec && rec.leafCount) {
            countHtml = '<span class="cad-preview-tree-count" data-cad-tree-count>(' + rec.leafCount + ')</span>';
        }
        var childrenHtml = kids.length ? '<ul>' + kids.map(renderTreeNode).join('') + '</ul>' : '';
        return '<li class="' + cls + '" data-cad-tree-node="' + id + '">' +
            '<div class="cad-preview-tree-row">' +
            '<button type="button" class="' + toggleCls + '" data-cad-tree-toggle="' + id + '" aria-label="展开">' +
            '<i class="ti ti-chevron-down"></i></button>' +
            '<button type="button" class="cad-preview-tree-vis" data-cad-tree-vis="' + id + '" aria-label="显隐">' +
            '<i class="' + eyeIcon + '"></i></button>' +
            '<span class="cad-preview-tree-label" data-cad-tree-select="' + id + '" title="' + escapeHtml(name) + '">' +
            escapeHtml(name) + '</span>' + countHtml + '</div>' + childrenHtml + '</li>';
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
        applyTreeFilter();
        syncMeasureUi();
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
            syncDisplayUi();
            syncMeasureUi();
            return;
        }
        applyEmissive(selectedNodeId);
        syncDisplayUi();
        var li = pageRoot && pageRoot.querySelector('[data-cad-tree-node="' + selectedNodeId + '"]');
        if (li) {
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
        syncMeasureUi();
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
        applyTreeFilter();
        syncMeasureUi();
    }

    function showAllNodes() {
        isolateBackup = null;
        Object.keys(nodeMap).forEach(function (id) {
            nodeMap[id].object.visible = true;
        });
        refreshTreeVisibility();
        applyTreeFilter();
        syncMeasureUi();
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

    function onCanvasPointerMove(ev) {
        if (!measuring || placingPivot) {
            hideMeasurePreview();
            return;
        }
        var hit = raycastModel(ev);
        if (!hit) {
            hideMeasurePreview();
            return;
        }
        var snap = snapMeasureHit(hit);
        showMeasurePreview(snap.point, snap.snapped);
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
        if (measuring) {
            if (hit) {
                addMeasurePoint(snapMeasureHit(hit).point);
                hideMeasurePreview();
            } else if (measurePending) {
                measurePending = null;
                rebuildMeasureGeom();
                syncMeasureUi();
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
        setDarkCanvas(darkCanvas);
        applyLights();
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
            pageRoot.addEventListener('input', onDisplayInput);
            pageRoot.addEventListener('change', onDisplayInput);
            pageRoot.addEventListener('input', onTreeSearchInput);
            pageRoot.addEventListener('change', onTreeSearchInput);
            pageRoot.addEventListener('keydown', onTreeSearchKeydown);
            document.addEventListener('keydown', onPivotKeydown);
            pageRoot.__cadToolbarBound = true;
        }
        if (canvasEl && !canvasEl.__cadPickBound) {
            canvasEl.addEventListener('pointerdown', onCanvasPointerDown);
            canvasEl.addEventListener('pointerup', onCanvasPointerUp);
            canvasEl.addEventListener('pointermove', onCanvasPointerMove);
            canvasEl.addEventListener('pointerleave', hideMeasurePreview);
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
