"""Controller helpers for ymt_feather_ribbon_01."""

from typing import Optional

import maya.cmds as cmds
from maya.api import OpenMaya as om2  # noqa: F401

from ymt_shifter_utility import control_util


def _component_prefix(component_root: str) -> str:
    if not cmds.objExists(component_root):
        raise RuntimeError("ymt_feather_ribbon_01 component root does not exist: %s" % component_root)
    if not component_root.endswith("root"):
        raise RuntimeError("ymt_feather_ribbon_01 component root must end with root: %s" % component_root)
    return component_root[: -len("root")]


def _is_rotate_locked_or_connected(node_name: str) -> bool:
    for attr_name in ("rotate", "rotateX", "rotateY", "rotateZ"):
        plug = node_name + "." + attr_name
        if cmds.getAttr(plug, lock=True):
            return True
        if cmds.listConnections(plug, source=True, destination=False, plugs=True):
            return True
    return False


def _get_fold_npo(pair_blend: str) -> Optional[str]:
    fold_npos = cmds.listConnections(
        pair_blend + ".outRotate",
        source=False,
        destination=True,
        type="transform",
    ) or []
    if not fold_npos:
        cmds.warning("ymt_feather_ribbon_01 fold pairBlend has no fold_npo destination: %s" % pair_blend)
        return None
    return fold_npos[0]


def _get_detail_control(fold_npo: str) -> Optional[str]:
    if not fold_npo.endswith("_fold_npo"):
        cmds.warning("ymt_feather_ribbon_01 unexpected fold_npo name: %s" % fold_npo)
        return None

    ctl = fold_npo[: -len("_fold_npo")] + "_ctl"
    if not cmds.objExists(ctl):
        cmds.warning("ymt_feather_ribbon_01 skipping missing detail control: %s" % ctl)
        return None
    return ctl


def capture_fold_pose(component_root: str) -> list[str]:
    """Adopt the current col-0 detail control rotations into the fold targets.

    Returns the list of captured control names. Does NOT touch the fold attribute.
    """

    captured_controls: list[str] = []
    cmds.undoInfo(openChunk=True)
    try:
        prefix = _component_prefix(component_root)
        pair_blends = cmds.ls(prefix + "*_fold_pb", type="pairBlend") or []
        if not pair_blends:
            raise RuntimeError("ymt_feather_ribbon_01 fold is not built on this component: %s" % component_root)

        for pair_blend in sorted(pair_blends):
            fold_npo = _get_fold_npo(pair_blend)
            if fold_npo is None:
                continue

            ctl = _get_detail_control(fold_npo)
            if ctl is None:
                continue

            if _is_rotate_locked_or_connected(ctl):
                cmds.warning(
                    "ymt_feather_ribbon_01 skipping fold capture for locked or connected rotate plugs: %s" % ctl
                )
                continue

            rotate = control_util.compose_local_rotations_xyz_degrees(ctl, fold_npo)
            cmds.setAttr(pair_blend + ".inRotate2", rotate[0], rotate[1], rotate[2])
            cmds.setAttr(ctl + ".rotate", 0.0, 0.0, 0.0)
            captured_controls.append(ctl)
    finally:
        cmds.undoInfo(closeChunk=True)

    return captured_controls
