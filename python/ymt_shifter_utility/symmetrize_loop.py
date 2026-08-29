"""Symmetrize ordered transform nodes along a closed outline."""

from __future__ import annotations

from collections.abc import Sequence

import maya.cmds as cmds


Point = tuple[float, float, float]
Axis = str | Sequence[float]
Center = str | Sequence[float]

_EPSILON = 1.0e-10
_NAMED_AXES = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


def _as_point(value: Sequence[float], label: str) -> Point:
    if len(value) != 3:
        raise ValueError("{} must contain exactly three values.".format(label))
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError("{} must contain three numeric values.".format(label)) from exc


def _normalize_axis(axis: Axis) -> Point:
    if isinstance(axis, str):
        axis_name = axis.lower().strip()
        direction = _NAMED_AXES.get(axis_name)
        if direction is None:
            raise ValueError("axis must be 'x', 'y', 'z', or a three-value vector.")
    else:
        direction = _as_point(axis, "axis")

    length_squared = sum(component * component for component in direction)
    if length_squared <= _EPSILON:
        raise ValueError("axis must not be a zero-length vector.")
    inverse_length = length_squared**-0.5
    return tuple(component * inverse_length for component in direction)  # type: ignore[return-value]


def _resolve_center(center: Center) -> Point:
    if isinstance(center, str):
        matches = cmds.ls(center, long=True) or []
        if len(matches) != 1 or not cmds.objectType(matches[0], isAType="transform"):
            raise ValueError("center must identify exactly one transform: {!r}".format(center))
        return _as_point(cmds.xform(matches[0], query=True, worldSpace=True, translation=True), "center")
    return _as_point(center, "center")


def _resolve_nodes(nodes: Sequence[str] | None) -> list[str]:
    if nodes is None:
        requested = cmds.ls(orderedSelection=True, long=True) or []
    else:
        requested = list(nodes)
    if len(requested) < 3:
        raise ValueError("At least three ordered transform nodes are required.")

    resolved = []
    for node in requested:
        matches = cmds.ls(node, long=True) or []
        if len(matches) != 1:
            raise ValueError("Node must resolve uniquely: {!r}".format(node))
        node_name = matches[0]
        if not cmds.objectType(node_name, isAType="transform"):
            raise TypeError("Node is not a transform: {!r}".format(node_name))
        if node_name in resolved:
            raise ValueError("Node is selected more than once: {!r}".format(node_name))
        resolved.append(node_name)
    return resolved


def _dot(left: Point, right: Point) -> float:
    return sum(a * b for a, b in zip(left, right))


def _reflect(point: Point, normal: Point, center: Point) -> Point:
    distance = _dot(tuple(point[i] - center[i] for i in range(3)), normal)  # type: ignore[arg-type]
    return tuple(point[i] - (2.0 * distance * normal[i]) for i in range(3))  # type: ignore[return-value]


def _project_to_plane(point: Point, normal: Point, center: Point) -> Point:
    distance = _dot(tuple(point[i] - center[i] for i in range(3)), normal)  # type: ignore[arg-type]
    return tuple(point[i] - (distance * normal[i]) for i in range(3))  # type: ignore[return-value]


def _average(left: Point, right: Point) -> Point:
    return tuple((left[i] + right[i]) * 0.5 for i in range(3))  # type: ignore[return-value]


def _symmetrize_pair(left: Point, right: Point, normal: Point, center: Point) -> tuple[Point, Point]:
    left_position = _average(left, _reflect(right, normal, center))
    return left_position, _reflect(left_position, normal, center)


def symmetrize_loop(
    nodes: Sequence[str] | None = None,
    axis: Axis = "x",
    center: Center = (0.0, 0.0, 0.0),
) -> list[str]:
    """Symmetrize ordered transforms across a plane.

    The plane passes through ``center`` and ``axis`` is its normal. Only world
    positions are changed; rotations and scales are preserved.

    The node order must follow the closed outline. With an odd node count, the
    first and last nodes represent the duplicated seam and are placed at the
    same position. With an even node count, the first node represents the seam
    by itself. The node opposite the seam is also projected onto the plane.

    Args:
        nodes: Ordered transform names. The ordered Maya selection is used when
            omitted.
        axis: Plane normal as ``"x"``, ``"y"``, ``"z"``, or a vector.
        center: A point on the plane, or the name of a transform whose world
            position supplies that point.

    Returns:
        Resolved long names in their input order.
    """

    resolved_nodes = _resolve_nodes(nodes)
    normal = _normalize_axis(axis)
    plane_center = _resolve_center(center)
    positions = [
        _as_point(cmds.xform(node, query=True, worldSpace=True, translation=True), node)
        for node in resolved_nodes
    ]
    result_positions = list(positions)
    node_count = len(resolved_nodes)

    if node_count % 2:
        seam_position = _project_to_plane(_average(positions[0], positions[-1]), normal, plane_center)
        result_positions[0] = seam_position
        result_positions[-1] = seam_position
        opposite_index = node_count // 2
        result_positions[opposite_index] = _project_to_plane(
            positions[opposite_index],
            normal,
            plane_center,
        )
        pair_indices = ((index, node_count - 1 - index) for index in range(1, opposite_index))
    else:
        result_positions[0] = _project_to_plane(positions[0], normal, plane_center)
        opposite_index = node_count // 2
        result_positions[opposite_index] = _project_to_plane(
            positions[opposite_index],
            normal,
            plane_center,
        )
        pair_indices = ((index, node_count - index) for index in range(1, opposite_index))

    for left_index, right_index in pair_indices:
        left_position, right_position = _symmetrize_pair(
            positions[left_index],
            positions[right_index],
            normal,
            plane_center,
        )
        result_positions[left_index] = left_position
        result_positions[right_index] = right_position

    cmds.undoInfo(openChunk=True, chunkName="symmetrizeLoop")
    try:
        for node, position in zip(resolved_nodes, result_positions):
            cmds.xform(node, worldSpace=True, translation=position)
    finally:
        cmds.undoInfo(closeChunk=True)

    return resolved_nodes
