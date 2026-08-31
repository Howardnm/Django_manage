/**
 * CAD 预览 — 工具栏分组与面板开关状态
 */
import { S, hooks, setGroupActive } from './core.js';

function isPanelOpen(panel) {
    return !!(panel && !panel.classList.contains('is-hidden'));
}

function syncGroupToggles() {
    setGroupActive(
        'display',
        S.displayMode !== 'solid' || S.darkCanvas
            || isPanelOpen(hooks.displayPanel())
            || isPanelOpen(hooks.lightPanel())
    );
    setGroupActive('view', S.orthoOn);
    setGroupActive('assist', S.gridOn || S.axesOn || S.placingPivot);
    setGroupActive(
        'tools',
        S.measuring || hooks.isSectionOn() || S.explodeAmount > 0
            || isPanelOpen(hooks.sectionPanel())
            || isPanelOpen(hooks.explodePanel())
            || isPanelOpen(hooks.measurePanel())
    );
}


hooks.isPanelOpen = isPanelOpen;
hooks.syncGroupToggles = syncGroupToggles;
export { isPanelOpen, syncGroupToggles };
