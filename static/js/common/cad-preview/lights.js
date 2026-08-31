/**
 * CAD 预览 — 光照
 */
import { THREE, S, hooks, DEFAULT_LIGHT_AZIMUTH, DEFAULT_LIGHT_COLOR, DEFAULT_LIGHT_DISTANCE, DEFAULT_LIGHT_ELEVATION, DEFAULT_LIGHT_GLOSS, DEFAULT_LIGHT_INTENSITY, DEFAULT_LIGHT_KIND, DEFAULT_MAT_CLEARCOAT, DEFAULT_MAT_CLEARCOAT_ROUGHNESS, DEFAULT_MAT_METALNESS, DEFAULT_MAT_ROUGHNESS, applyGlossPreset, clamp01, currentMatParams, getModelBox } from './core.js';

function lightPanel() {
    return S.pageRoot && S.pageRoot.querySelector('[data-cad-light-panel]');
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
    hooks.hideSectionPanel();
    hooks.hideExplodePanel();
    hooks.hideMeasurePanel();
    hooks.hideDisplayPanel();
    hooks.hideShotPanel();
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
    var btn = S.pageRoot && S.pageRoot.querySelector('[data-cad-action="light"]');
    if (btn) {
        btn.classList.toggle('active', !!on);
    }
    if (hooks.syncGroupToggles) {
        hooks.syncGroupToggles();
    }
}

function onLightInput(ev) {
    var input = ev.target.closest('[data-cad-light]');
    if (!input) {
        return;
    }
    var kind = input.getAttribute('data-cad-light');
    if (kind === 'azimuth') {
        S.lightAzimuth = Number(input.value);
        S.lightFollow = false;
    } else if (kind === 'elevation') {
        S.lightElevation = Number(input.value);
        S.lightFollow = false;
    } else if (kind === 'intensity') {
        S.lightIntensity = Number(input.value);
    } else if (kind === 'color') {
        S.lightColor = input.value || DEFAULT_LIGHT_COLOR;
    } else if (kind === 'follow') {
        S.lightFollow = !!input.checked;
    } else if (kind === 'distance') {
        S.lightDistance = Number(input.value);
        if (!(S.lightDistance > 0)) {
            S.lightDistance = DEFAULT_LIGHT_DISTANCE;
        }
    } else if (kind === 'gloss') {
        applyGlossPreset(input.value);
        applyMaterialGloss();
    } else if (kind === 'roughness') {
        S.matRoughness = clamp01(input.value);
        applyMaterialGloss();
    } else if (kind === 'metalness') {
        S.matMetalness = clamp01(input.value);
        applyMaterialGloss();
    } else if (kind === 'clearcoat') {
        S.matClearcoat = clamp01(input.value);
        applyMaterialGloss();
    } else if (kind === 'clearcoat-roughness') {
        S.matClearcoatRoughness = clamp01(input.value);
        applyMaterialGloss();
    }
    applyLights();
    syncLightUi();
}

function setLightKind(kind) {
    S.lightKind = kind === 'point' ? 'point' : 'area';
    applyLights();
    syncLightUi();
}

function resetLights() {
    S.lightAzimuth = DEFAULT_LIGHT_AZIMUTH;
    S.lightElevation = DEFAULT_LIGHT_ELEVATION;
    S.lightIntensity = DEFAULT_LIGHT_INTENSITY;
    S.lightColor = DEFAULT_LIGHT_COLOR;
    S.lightFollow = false;
    S.lightKind = DEFAULT_LIGHT_KIND;
    S.lightDistance = DEFAULT_LIGHT_DISTANCE;
    applyGlossPreset(DEFAULT_LIGHT_GLOSS);
    S.matRoughness = DEFAULT_MAT_ROUGHNESS;
    S.matMetalness = DEFAULT_MAT_METALNESS;
    S.matClearcoat = DEFAULT_MAT_CLEARCOAT;
    S.matClearcoatRoughness = DEFAULT_MAT_CLEARCOAT_ROUGHNESS;
    applyLights();
    applyMaterialGloss();
    syncLightUi();
}

function applyMaterialGloss() {
    if (!S.modelGroup) {
        return;
    }
    var p = currentMatParams();
    var seen = [];
    S.modelGroup.traverse(function (obj) {
        if (!obj.userData || obj.userData.cadRole !== 'solid') {
            return;
        }
        var mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach(function (m) {
            if (!m || seen.indexOf(m) !== -1) {
                return;
            }
            if (m.roughness == null && m.metalness == null) {
                return;
            }
            seen.push(m);
            if (m.roughness != null) {
                m.roughness = p.roughness;
            }
            if (m.metalness != null) {
                m.metalness = p.metalness;
            }
            if (m.clearcoat != null) {
                m.clearcoat = p.clearcoat;
            }
            if (m.clearcoatRoughness != null) {
                m.clearcoatRoughness = p.clearcoatRoughness;
            }
            m.needsUpdate = true;
        });
    });
}

function lightDirection() {
    var dir = new THREE.Vector3();
    if (S.lightFollow && S.camera && S.controls) {
        dir.copy(S.camera.position).sub(S.controls.target);
        if (dir.lengthSq() < 1e-8) {
            dir.set(1, 1, 1);
        }
        return dir.normalize();
    }
    var az = S.lightAzimuth * Math.PI / 180;
    var el = S.lightElevation * Math.PI / 180;
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
    var roughness = panel.querySelector('[data-cad-light="roughness"]');
    var metalness = panel.querySelector('[data-cad-light="metalness"]');
    var clearcoat = panel.querySelector('[data-cad-light="clearcoat"]');
    var coatRough = panel.querySelector('[data-cad-light="clearcoat-roughness"]');
    var azVal = panel.querySelector('[data-cad-light-az-val]');
    var elVal = panel.querySelector('[data-cad-light-el-val]');
    var inVal = panel.querySelector('[data-cad-light-in-val]');
    var colorVal = panel.querySelector('[data-cad-light-color-val]');
    var distVal = panel.querySelector('[data-cad-light-dist-val]');
    var glossVal = panel.querySelector('[data-cad-light-gloss-val]');
    var roughnessVal = panel.querySelector('[data-cad-light-roughness-val]');
    var metalnessVal = panel.querySelector('[data-cad-light-metalness-val]');
    var clearcoatVal = panel.querySelector('[data-cad-light-clearcoat-val]');
    var coatRoughVal = panel.querySelector('[data-cad-light-clearcoat-roughness-val]');
    var isPoint = S.lightKind === 'point';
    if (az) {
        az.value = String(Math.round(S.lightAzimuth));
        az.disabled = S.lightFollow;
    }
    if (el) {
        el.value = String(Math.round(S.lightElevation));
        el.disabled = S.lightFollow;
    }
    if (ins) {
        ins.value = String(S.lightIntensity);
    }
    if (color) {
        color.value = S.lightColor;
    }
    if (follow) {
        follow.checked = S.lightFollow;
    }
    if (dist) {
        dist.value = String(S.lightDistance);
        dist.disabled = !isPoint;
    }
    if (gloss) {
        gloss.value = String(S.lightGloss);
    }
    if (roughness) {
        roughness.value = String(S.matRoughness);
    }
    if (metalness) {
        metalness.value = String(S.matMetalness);
    }
    if (clearcoat) {
        clearcoat.value = String(S.matClearcoat);
    }
    if (coatRough) {
        coatRough.value = String(S.matClearcoatRoughness);
    }
    if (azVal) {
        azVal.textContent = S.lightFollow ? '跟随' : Math.round(S.lightAzimuth) + '°';
    }
    if (elVal) {
        elVal.textContent = S.lightFollow ? '跟随' : Math.round(S.lightElevation) + '°';
    }
    if (inVal) {
        inVal.textContent = Number(S.lightIntensity).toFixed(2);
    }
    if (colorVal) {
        colorVal.textContent = S.lightColor;
    }
    if (distVal) {
        distVal.textContent = Number(S.lightDistance).toFixed(1) + '×';
    }
    if (glossVal) {
        glossVal.textContent = Math.round(S.lightGloss * 100) + '%';
    }
    if (roughnessVal) {
        roughnessVal.textContent = Math.round(S.matRoughness * 100) + '%';
    }
    if (metalnessVal) {
        metalnessVal.textContent = Math.round(S.matMetalness * 100) + '%';
    }
    if (clearcoatVal) {
        clearcoatVal.textContent = Math.round(S.matClearcoat * 100) + '%';
    }
    if (coatRoughVal) {
        coatRoughVal.textContent = Math.round(S.matClearcoatRoughness * 100) + '%';
    }
    panel.querySelectorAll('[data-cad-light-kind]').forEach(function (btn) {
        btn.classList.toggle('active', btn.getAttribute('data-cad-light-kind') === S.lightKind);
    });
    panel.classList.toggle('is-follow', S.lightFollow);
    panel.classList.toggle('is-point', isPoint);
}

function applyLights() {
    if (!S.keyLight || !S.fillLight || !S.ambientLight) {
        return;
    }
    var dir = lightDirection();
    var isPoint = S.lightKind === 'point';
    S.keyLight.visible = !isPoint;
    S.fillLight.visible = !isPoint;
    if (S.pointLight) {
        S.pointLight.visible = isPoint;
    }
    S.keyLight.color.set(S.lightColor);
    S.fillLight.color.copy(S.keyLight.color).multiplyScalar(0.72);
    if (S.ambientLight.isHemisphereLight) {
        S.ambientLight.color.copy(S.keyLight.color);
        S.ambientLight.groundColor.copy(S.keyLight.color).multiplyScalar(0.38);
        S.ambientLight.intensity = 0.55 + S.lightIntensity * 0.42;
    } else {
        S.ambientLight.color.copy(S.keyLight.color).multiplyScalar(0.7);
        S.ambientLight.intensity = 0.28 + S.lightIntensity * 0.22;
    }
    if (isPoint && S.pointLight) {
        var info = getModelBox(false);
        var maxDim = info ? info.maxDim : 80;
        var dist = Math.max(maxDim * S.lightDistance, 1);
        if (info) {
            S.pointLight.position.copy(info.center).addScaledVector(dir, dist);
        } else {
            S.pointLight.position.copy(dir).multiplyScalar(dist);
        }
        S.pointLight.color.set(S.lightColor);
        // r185 物理点光按距离平方衰减。强度乘 dist²，模型中心亮度跟区域主光同级。
        S.pointLight.intensity = S.lightIntensity * 2.8 * dist * dist;
        S.pointLight.distance = 0;
        S.pointLight.decay = 2;
        return;
    }
    S.keyLight.position.copy(dir);
    S.keyLight.intensity = S.lightIntensity * 2.8;
    S.fillLight.position.set(-dir.x * 0.55, -dir.y * 0.55, Math.max(dir.z * 0.3, 0.15));
    S.fillLight.intensity = Math.max(S.lightIntensity * 0.95, 0.28);
}


hooks.lightPanel = lightPanel;
hooks.toggleLightPanel = toggleLightPanel;
hooks.showLightPanel = showLightPanel;
hooks.hideLightPanel = hideLightPanel;
hooks.setLightButtonActive = setLightButtonActive;
hooks.onLightInput = onLightInput;
hooks.setLightKind = setLightKind;
hooks.resetLights = resetLights;
hooks.applyMaterialGloss = applyMaterialGloss;
hooks.lightDirection = lightDirection;
hooks.syncLightUi = syncLightUi;
hooks.applyLights = applyLights;
export { lightPanel, toggleLightPanel, showLightPanel, hideLightPanel, setLightButtonActive, onLightInput, setLightKind, resetLights, applyMaterialGloss, lightDirection, syncLightUi, applyLights };
