/**
 * CAD 预览 — 光照
 */
import { THREE, S, hooks, DEFAULT_LIGHT_AZIMUTH, DEFAULT_LIGHT_COLOR, DEFAULT_LIGHT_DISTANCE, DEFAULT_LIGHT_ELEVATION, DEFAULT_LIGHT_GLOSS, DEFAULT_LIGHT_INTENSITY, DEFAULT_LIGHT_KIND, getModelBox, glossParams } from './core.js';

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
        S.lightGloss = Number(input.value);
        if (!(S.lightGloss >= 0)) {
            S.lightGloss = 0;
        }
        if (S.lightGloss > 1) {
            S.lightGloss = 1;
        }
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
    S.lightGloss = DEFAULT_LIGHT_GLOSS;
    applyLights();
    applyMaterialGloss();
    syncLightUi();
}

function applyMaterialGloss() {
    if (!S.modelGroup) {
        return;
    }
    var p = glossParams(S.lightGloss);
    var seen = [];
    S.modelGroup.traverse(function (obj) {
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
    var azVal = panel.querySelector('[data-cad-light-az-val]');
    var elVal = panel.querySelector('[data-cad-light-el-val]');
    var inVal = panel.querySelector('[data-cad-light-in-val]');
    var colorVal = panel.querySelector('[data-cad-light-color-val]');
    var distVal = panel.querySelector('[data-cad-light-dist-val]');
    var glossVal = panel.querySelector('[data-cad-light-gloss-val]');
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
    S.fillLight.color.copy(S.keyLight.color).multiplyScalar(0.55);
    S.ambientLight.color.copy(S.keyLight.color).multiplyScalar(0.7);
    S.ambientLight.intensity = 0.28 + S.lightIntensity * 0.22;
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
        S.pointLight.intensity = S.lightIntensity * 2.5;
        S.pointLight.distance = dist + maxDim * 1.8;
        S.pointLight.decay = 2;
        return;
    }
    S.keyLight.position.copy(dir);
    S.keyLight.intensity = S.lightIntensity;
    S.fillLight.position.set(-dir.x * 0.55, -dir.y * 0.55, Math.max(dir.z * 0.3, 0.15));
    S.fillLight.intensity = Math.max(S.lightIntensity * 0.32, 0.12);
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
