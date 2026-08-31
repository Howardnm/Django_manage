/**
 * CAD 预览 — 工具栏动作路由
 */
import { S, hooks, closeParentDropdown } from './core.js';

function onToolbarClick(ev) {
    var btn = ev.target.closest('[data-cad-action]');
    if (!btn) {
        return;
    }
    var action = btn.getAttribute('data-cad-action');
    if (action === 'solid') {
        ev.preventDefault();
        hooks.setDisplayMode('solid');
    } else if (action === 'wireframe') {
        ev.preventDefault();
        hooks.setDisplayMode(S.displayMode === 'wireframe' ? 'solid' : 'wireframe');
    } else if (action === 'xray') {
        ev.preventDefault();
        hooks.setDisplayMode(S.displayMode === 'xray' ? 'solid' : 'xray');
    } else if (action === 'dark') {
        ev.preventDefault();
        hooks.setDarkCanvas(!S.darkCanvas);
    } else if (action === 'display-panel') {
        ev.preventDefault();
        hooks.toggleDisplayPanel();
        closeParentDropdown(btn);
    } else if (action === 'display-close') {
        ev.preventDefault();
        hooks.hideDisplayPanel();
    } else if (action === 'part-color') {
        ev.preventDefault();
        hooks.applySelectedPartColor();
    } else if (action === 'part-color-reset') {
        ev.preventDefault();
        hooks.restorePartColor(S.selectedNodeId);
    } else if (action === 'part-color-reset-all') {
        ev.preventDefault();
        hooks.restorePartColor(null);
    } else if (action === 'shot-scale') {
        ev.preventDefault();
        hooks.setShotScale(Number(btn.getAttribute('data-cad-shot-scale')));
    } else if (action === 'shot-size') {
        ev.preventDefault();
        hooks.setShotSize(Number(btn.getAttribute('data-cad-shot-size')));
    } else if (action === 'fit') {
        ev.preventDefault();
        hooks.fitToView();
        closeParentDropdown(btn);
    } else if (action === 'light') {
        ev.preventDefault();
        hooks.hideTreePanel();
        hooks.toggleLightPanel();
        closeParentDropdown(btn);
    } else if (action === 'light-close') {
        ev.preventDefault();
        hooks.hideLightPanel();
    } else if (action === 'light-reset') {
        ev.preventDefault();
        hooks.resetLights();
    } else if (action === 'light-kind') {
        ev.preventDefault();
        hooks.setLightKind(btn.getAttribute('data-cad-light-kind') || 'area');
    } else if (action === 'tree') {
        ev.preventDefault();
        hooks.hideLightPanel();
        hooks.toggleTreePanel();
    } else if (action === 'tree-close') {
        ev.preventDefault();
        hooks.hideTreePanel();
    } else if (action === 'tree-filter') {
        ev.preventDefault();
        hooks.setTreeVisFilter(btn.getAttribute('data-cad-tree-filter') || 'all');
    } else if (action === 'tree-expand-all') {
        ev.preventDefault();
        hooks.expandAllTreeNodes();
    } else if (action === 'tree-collapse-all') {
        ev.preventDefault();
        hooks.collapseAllTreeNodes();
    } else if (action === 'view') {
        ev.preventDefault();
        hooks.setPresetView(btn.getAttribute('data-cad-view') || 'iso');
        closeParentDropdown(btn);
    } else if (action === 'view-roll') {
        ev.preventDefault();
        hooks.rollAlignedView(Number(btn.getAttribute('data-cad-roll')) || 90);
    } else if (action === 'ortho') {
        ev.preventDefault();
        hooks.setOrtho(!S.orthoOn);
    } else if (action === 'grid') {
        ev.preventDefault();
        hooks.setGrid(!S.gridOn);
    } else if (action === 'axes') {
        ev.preventDefault();
        hooks.setAxes(!S.axesOn);
    } else if (action === 'screenshot') {
        ev.preventDefault();
        hooks.toggleShotPanel();
    } else if (action === 'shot-close') {
        ev.preventDefault();
        hooks.hideShotPanel();
    } else if (action === 'shot-export') {
        ev.preventDefault();
        hooks.captureScreenshot();
    } else if (action === 'place-pivot') {
        ev.preventDefault();
        hooks.setPlacingPivot(!S.placingPivot);
        closeParentDropdown(btn);
    } else if (action === 'section') {
        ev.preventDefault();
        hooks.toggleSectionPanel();
        closeParentDropdown(btn);
    } else if (action === 'section-close') {
        ev.preventDefault();
        hooks.hideSectionPanel();
    } else if (action === 'section-reset') {
        ev.preventDefault();
        hooks.resetSection();
    } else if (action === 'section-add') {
        ev.preventDefault();
        hooks.onSectionAddClick();
    } else if (action === 'section-commit') {
        ev.preventDefault();
        hooks.commitSectionCut();
    } else if (action === 'section-select') {
        ev.preventDefault();
        hooks.selectSectionCut(btn.getAttribute('data-cad-cut-id'));
    } else if (action === 'section-remove') {
        ev.preventDefault();
        hooks.removeSectionCut(btn.getAttribute('data-cad-cut-id'));
    } else if (action === 'section-pivot') {
        ev.preventDefault();
        hooks.snapActiveCutToPivot();
    } else if (action === 'section-axis') {
        ev.preventDefault();
        hooks.setSectionAxis(btn.getAttribute('data-cad-axis') || 'z');
    } else if (action === 'explode') {
        ev.preventDefault();
        hooks.toggleExplodePanel();
        closeParentDropdown(btn);
    } else if (action === 'measure') {
        ev.preventDefault();
        hooks.toggleMeasurePanel();
        closeParentDropdown(btn);
    } else if (action === 'measure-close') {
        ev.preventDefault();
        hooks.hideMeasurePanel();
    } else if (action === 'measure-clear') {
        ev.preventDefault();
        hooks.clearMeasure();
    } else if (action === 'measure-remove') {
        ev.preventDefault();
        hooks.removeMeasureSegment(Number(btn.getAttribute('data-cad-measure-index')));
    } else if (action === 'explode-close') {
        ev.preventDefault();
        hooks.hideExplodePanel();
    } else if (action === 'explode-reset') {
        ev.preventDefault();
        hooks.resetExplode();
    } else if (action === 'explode-selected') {
        ev.preventDefault();
        hooks.explodeFromSelected();
    } else if (action === 'explode-default') {
        ev.preventDefault();
        hooks.explodeToDefault();
    } else if (action === 'explode-style') {
        ev.preventDefault();
        hooks.setExplodeStyle(btn.getAttribute('data-cad-explode-style') || 'radial');
    } else if (action === 'explode-center') {
        ev.preventDefault();
        hooks.explodeCenterFromSelected();
    } else if (action === 'explode-center-reset') {
        ev.preventDefault();
        S.explodeCenterId = null;
        hooks.recomputeExplodeDirs();
        hooks.syncExplodeUi();
    } else if (action === 'pivot-selected') {
        ev.preventDefault();
        hooks.pivotToSelected();
    } else if (action === 'isolate') {
        ev.preventDefault();
        hooks.isolateSelected();
    } else if (action === 'show-all') {
        ev.preventDefault();
        hooks.showAllNodes();
    }
}


hooks.onToolbarClick = onToolbarClick;
export { onToolbarClick };
