/**
 * CAD 预览 — OCCT 解析与网格装配
 */
import { THREE, S, hooks, DEFAULT_COLOR, DEFAULT_EXPLODE_BIN_PCT, LARGE_FILE_BYTES, WORKER_TIMEOUT_MS, assets, initScene, makeSolidMaterial, setError, setStatus } from './core.js';

function cadFormat(ext) {
    ext = (ext || '').toLowerCase();
    if (ext === 'igs' || ext === 'iges') {
        return 'iges';
    }
    return 'step';
}

function disposeWorker() {
    if (S.worker) {
        try {
            S.worker.terminate();
        } catch (e) { /* ignore */ }
        S.worker = null;
    }
}

function buildMesh(geometryMesh) {
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
    hooks.snapshotSolidOrig(mesh);

    var group = new THREE.Group();
    group.name = mesh.name;
    group.add(mesh);
    group.add(buildFaceEdges(geometry, index, geometryMesh.brep_faces));
    return group;
}

function nextNodeId() {
    S.nodeIdSeq += 1;
    return 'n' + S.nodeIdSeq;
}

function registerNode(id, object, name, parentId) {
    object.userData.cadNodeId = id;
    S.nodeMap[id] = { id: id, object: object, name: name, parentId: parentId };
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
    var edges = new THREE.Group();
    edges.name = '__cad_edges';
    edges.userData.cadRole = 'edges';
    edges.visible = false;
    var planes = [];
    var material = new THREE.LineBasicMaterial({
        color: 0x3b4a5a,
        clippingPlanes: planes,
    });
    material.userData._cadClip = planes;

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
    if (!S.modelGroup || !result || !result.meshes) {
        return 0;
    }
    S.nodeIdSeq = 0;
    S.nodeMap = {};
    S.selectedNodeId = null;
    S.selectedNodeIds = [];
    S.isolateBackup = null;
    S.explodeUnits = [];
    S.explodeAmount = 0;
    S.explodeParentId = null;
    S.explodeStyle = 'radial';
    S.explodeCenterId = null;
    S.explodeEven = true;
    S.explodeBinPct = DEFAULT_EXPLODE_BIN_PCT;
    S.alignedView = null;
    hooks.showViewRoll(false);
    hooks.resetTreeFilterState();
    hooks.hideMeasurePanel();
    hooks.clearMeasure();
    hooks.resetSection();
    while (S.modelGroup.children.length) {
        S.modelGroup.remove(S.modelGroup.children[0]);
    }
    var root = result.root;
    if (!root) {
        root = {
            name: fallbackName || '模型',
            meshes: result.meshes.map(function (_, i) { return i; }),
            children: [],
        };
    }
    S.modelGroup.add(buildSceneNode(root, result, null, fallbackName || '模型'));
    hooks.cacheLeafCounts();
    return result.meshes.length;
}

function parseInWorker(buffer, ext) {
    return new Promise(function (resolve, reject) {
        var a = assets();
        if (!a.worker) {
            reject(new Error('未配置 CAD worker'));
            return;
        }
        disposeWorker();
        S.worker = new Worker(a.worker);
        var timer = setTimeout(function () {
            disposeWorker();
            reject(new Error('timeout'));
        }, WORKER_TIMEOUT_MS);
        S.worker.onmessage = function (ev) {
            clearTimeout(timer);
            resolve(ev.data);
        };
        S.worker.onerror = function (ev) {
            clearTimeout(timer);
            reject(ev.error || new Error(ev.message || 'Worker 解析失败'));
        };
        var u8 = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
        S.worker.postMessage({
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
    if (!S.renderer) {
        setStatus('正在加载 3D 引擎…');
        initScene(S.canvasEl, S.stageEl);
    }

    if (opts.size > LARGE_FILE_BYTES) {
        setStatus('文件较大（' + humanSize(opts.size) + '），正在下载，解析可能较慢…');
    } else {
        setStatus('正在下载文件…');
    }

    S.abortController = new AbortController();
    var response;
    try {
        response = await fetch(opts.url, {
            credentials: 'same-origin',
            signal: S.abortController.signal,
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

    S.currentFileName = opts.name || 'cad';
    addMeshes(result, S.currentFileName);
    hooks.renderTree();
    hooks.setDisplayMode('solid');
    hooks.setDarkCanvas(S.darkCanvas);
    if (hooks.applyMaterialGloss) {
        hooks.applyMaterialGloss();
    }
    hooks.applyLights();
    hooks.syncExplodeUi();
    if (hooks.isSectionOn()) {
        hooks.applyAllSectionCuts();
        if (S.sectionPreviewing) {
            hooks.rebuildSectionHelpers();
        }
    }
    hooks.fitToView();
    setStatus('');
}


hooks.cadFormat = cadFormat;
hooks.disposeWorker = disposeWorker;
hooks.buildMesh = buildMesh;
hooks.nextNodeId = nextNodeId;
hooks.registerNode = registerNode;
hooks.uniqueIndices = uniqueIndices;
hooks.nodeLabel = nodeLabel;
hooks.attachMeshes = attachMeshes;
hooks.buildSceneNode = buildSceneNode;
hooks.buildFaceEdges = buildFaceEdges;
hooks.addMeshes = addMeshes;
hooks.parseInWorker = parseInWorker;
hooks.humanSize = humanSize;
hooks.loadModel = loadModel;
export { cadFormat, disposeWorker, buildMesh, nextNodeId, registerNode, uniqueIndices, nodeLabel, attachMeshes, buildSceneNode, buildFaceEdges, addMeshes, parseInWorker, humanSize, loadModel };
