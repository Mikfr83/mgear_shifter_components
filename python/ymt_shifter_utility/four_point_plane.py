"""Utilities for building transforms from four ordered plane points."""

from __future__ import annotations

import math
from typing import Literal, cast

import maya.cmds as cmds


Vector3 = tuple[float, float, float]
NormalAxis = Literal["+x", "+y", "+z", "-x", "-y", "-z"]

_AXES = ("+x", "+y", "+z", "-x", "-y", "-z")
_EPSILON = 0.000001


def create_four_point_plane_transform(
    normal_transform: str,
    normal_axis: NormalAxis,
    point_a: str,
    point_b: str,
    point_c: str,
    point_d: str,
    name: str | None = None,
    parent: str | None = None,
) -> str:
    """Create a transform constrained to the plane made by four ordered points.

    The four points must be ordered around the quadrilateral perimeter. For
    example: lower-left, lower-right, upper-right, upper-left.
    """
    axis = _normalize_axis_name(normal_axis)
    points = (point_a, point_b, point_c, point_d)
    _validate_transform(normal_transform, "normal_transform")
    for label, point in zip(("point_a", "point_b", "point_c", "point_d"), points):
        _validate_transform(point, label)
    if parent is not None:
        _validate_transform(parent, "parent")

    _validate_initial_plane(points)

    target = cmds.createNode("transform", name=name or "fourPointPlane_transform", parent=parent)
    nodes = _build_plane_nodes(normal_transform, axis, points, target)
    for node_name in nodes:
        _tag_node(node_name, target)

    return target


def _build_plane_nodes(
    normal_transform: str,
    normal_axis: NormalAxis,
    points: tuple[str, ...],
    target: str,
) -> list[str]:
    prefix = _short_name(target)
    nodes: list[str] = []

    point_decomposes = []
    for index, point in enumerate(points):
        decompose = _create_node("decomposeMatrix", prefix, "point%s_dm" % index, nodes)
        cmds.connectAttr(point + ".worldMatrix[0]", decompose + ".inputMatrix", force=True)
        point_decomposes.append(decompose)

    center_sum = _create_node("plusMinusAverage", prefix, "center_pma", nodes)
    cmds.setAttr(center_sum + ".operation", 1)
    for index, decompose in enumerate(point_decomposes):
        cmds.connectAttr(decompose + ".outputTranslate", center_sum + ".input3D[%s]" % index, force=True)

    center_scale = _create_node("multiplyDivide", prefix, "center_md", nodes)
    cmds.setAttr(center_scale + ".operation", 1)
    cmds.setAttr(center_scale + ".input2", 0.25, 0.25, 0.25, type="double3")
    cmds.connectAttr(center_sum + ".output3D", center_scale + ".input1", force=True)

    u_vector = _create_edge_sum(
        point_decomposes[1] + ".outputTranslate",
        point_decomposes[0] + ".outputTranslate",
        point_decomposes[2] + ".outputTranslate",
        point_decomposes[3] + ".outputTranslate",
        prefix,
        "u",
        nodes,
    )
    v_vector = _create_edge_sum(
        point_decomposes[3] + ".outputTranslate",
        point_decomposes[0] + ".outputTranslate",
        point_decomposes[2] + ".outputTranslate",
        point_decomposes[1] + ".outputTranslate",
        prefix,
        "v",
        nodes,
    )

    u_normalized = _create_normalized_vector(u_vector, prefix, "u_norm", nodes)
    plane_normal_raw = _create_cross_vector(u_normalized, v_vector, prefix, "normal_raw", nodes)
    reference_normal = _create_reference_normal(normal_transform, normal_axis, prefix, nodes)
    normal_sign = _create_normal_sign(plane_normal_raw, reference_normal, prefix, nodes)
    plane_normal = _create_scaled_vector(plane_normal_raw, normal_sign + ".outColorR", prefix, "normal", nodes)

    axis_vectors = _create_axis_vectors(plane_normal, u_normalized, normal_axis, prefix, nodes)
    plane_matrix = _create_matrix(axis_vectors, center_scale + ".output", prefix, nodes)

    local_matrix = _create_node("multMatrix", prefix, "local_mm", nodes)
    cmds.connectAttr(plane_matrix + ".output", local_matrix + ".matrixIn[0]", force=True)
    cmds.connectAttr(target + ".parentInverseMatrix[0]", local_matrix + ".matrixIn[1]", force=True)

    decompose = _create_node("decomposeMatrix", prefix, "local_dm", nodes)
    cmds.connectAttr(local_matrix + ".matrixSum", decompose + ".inputMatrix", force=True)
    cmds.connectAttr(target + ".rotateOrder", decompose + ".inputRotateOrder", force=True)
    cmds.connectAttr(decompose + ".outputTranslate", target + ".translate", force=True)
    cmds.connectAttr(decompose + ".outputRotate", target + ".rotate", force=True)

    return nodes


def _create_edge_sum(
    positive_a: str,
    negative_a: str,
    positive_b: str,
    negative_b: str,
    prefix: str,
    name: str,
    nodes: list[str],
) -> str:
    edge_a = _create_node("plusMinusAverage", prefix, name + "A_pma", nodes)
    cmds.setAttr(edge_a + ".operation", 2)
    cmds.connectAttr(positive_a, edge_a + ".input3D[0]", force=True)
    cmds.connectAttr(negative_a, edge_a + ".input3D[1]", force=True)

    edge_b = _create_node("plusMinusAverage", prefix, name + "B_pma", nodes)
    cmds.setAttr(edge_b + ".operation", 2)
    cmds.connectAttr(positive_b, edge_b + ".input3D[0]", force=True)
    cmds.connectAttr(negative_b, edge_b + ".input3D[1]", force=True)

    result = _create_node("plusMinusAverage", prefix, name + "_pma", nodes)
    cmds.setAttr(result + ".operation", 1)
    cmds.connectAttr(edge_a + ".output3D", result + ".input3D[0]", force=True)
    cmds.connectAttr(edge_b + ".output3D", result + ".input3D[1]", force=True)
    return result + ".output3D"


def _create_normalized_vector(vector_attr: str, prefix: str, name: str, nodes: list[str]) -> str:
    vector = _create_node("vectorProduct", prefix, name + "_vp", nodes)
    cmds.setAttr(vector + ".operation", 0)
    cmds.setAttr(vector + ".normalizeOutput", True)
    cmds.connectAttr(vector_attr, vector + ".input1", force=True)
    return vector + ".output"


def _create_cross_vector(input1: str, input2: str, prefix: str, name: str, nodes: list[str]) -> str:
    vector = _create_node("vectorProduct", prefix, name + "_vp", nodes)
    cmds.setAttr(vector + ".operation", 2)
    cmds.setAttr(vector + ".normalizeOutput", True)
    cmds.connectAttr(input1, vector + ".input1", force=True)
    cmds.connectAttr(input2, vector + ".input2", force=True)
    return vector + ".output"


def _create_reference_normal(normal_transform: str, normal_axis: NormalAxis, prefix: str, nodes: list[str]) -> str:
    vector = _create_node("vectorProduct", prefix, "referenceNormal_vp", nodes)
    cmds.setAttr(vector + ".operation", 3)
    cmds.setAttr(vector + ".normalizeOutput", True)
    cmds.setAttr(vector + ".input1", *_axis_vector(normal_axis), type="double3")
    cmds.connectAttr(normal_transform + ".worldMatrix[0]", vector + ".matrix", force=True)
    return vector + ".output"


def _create_normal_sign(plane_normal: str, reference_normal: str, prefix: str, nodes: list[str]) -> str:
    dot = _create_node("vectorProduct", prefix, "normalDot_vp", nodes)
    cmds.setAttr(dot + ".operation", 1)
    cmds.connectAttr(plane_normal, dot + ".input1", force=True)
    cmds.connectAttr(reference_normal, dot + ".input2", force=True)

    condition = _create_node("condition", prefix, "normalSign_cnd", nodes)
    cmds.setAttr(condition + ".operation", 2)
    cmds.setAttr(condition + ".secondTerm", 0.0)
    cmds.setAttr(condition + ".colorIfTrue", -1.0, -1.0, -1.0, type="double3")
    cmds.setAttr(condition + ".colorIfFalse", 1.0, 1.0, 1.0, type="double3")
    cmds.connectAttr(dot + ".outputX", condition + ".firstTerm", force=True)
    return condition


def _create_scaled_vector(vector_attr: str, scalar_attr: str, prefix: str, name: str, nodes: list[str]) -> str:
    multiply = _create_node("multiplyDivide", prefix, name + "_md", nodes)
    cmds.setAttr(multiply + ".operation", 1)
    cmds.connectAttr(vector_attr, multiply + ".input1", force=True)
    for axis in ("X", "Y", "Z"):
        cmds.connectAttr(scalar_attr, multiply + ".input2" + axis, force=True)
    return multiply + ".output"


def _create_axis_vectors(
    normal: str,
    tangent: str,
    normal_axis: NormalAxis,
    prefix: str,
    nodes: list[str],
) -> tuple[str, str, str]:
    sign = -1.0 if normal_axis.startswith("-") else 1.0
    axis_name = normal_axis[-1]
    axis_normal = normal if sign > 0 else _create_scaled_constant_vector(normal, -1.0, prefix, axis_name + "Neg", nodes)

    if axis_name == "x":
        x_axis = axis_normal
        z_axis = _create_cross_vector(x_axis, tangent, prefix, "zAxis", nodes)
        y_axis = _create_cross_vector(z_axis, x_axis, prefix, "yAxis", nodes)
    elif axis_name == "y":
        y_axis = axis_normal
        z_axis = _create_cross_vector(tangent, y_axis, prefix, "zAxis", nodes)
        x_axis = _create_cross_vector(y_axis, z_axis, prefix, "xAxis", nodes)
    else:
        z_axis = axis_normal
        y_axis = _create_cross_vector(z_axis, tangent, prefix, "yAxis", nodes)
        x_axis = _create_cross_vector(y_axis, z_axis, prefix, "xAxis", nodes)

    return x_axis, y_axis, z_axis


def _create_scaled_constant_vector(
    vector_attr: str,
    scale: float,
    prefix: str,
    name: str,
    nodes: list[str],
) -> str:
    multiply = _create_node("multiplyDivide", prefix, name + "_md", nodes)
    cmds.setAttr(multiply + ".operation", 1)
    cmds.connectAttr(vector_attr, multiply + ".input1", force=True)
    cmds.setAttr(multiply + ".input2", scale, scale, scale, type="double3")
    return multiply + ".output"


def _create_matrix(axis_vectors: tuple[str, str, str], center: str, prefix: str, nodes: list[str]) -> str:
    matrix = _create_node("fourByFourMatrix", prefix, "world_fbfm", nodes)
    for row, axis_attr in enumerate(axis_vectors):
        for column, component in enumerate(("X", "Y", "Z")):
            cmds.connectAttr(axis_attr + component, matrix + ".in%s%s" % (row, column), force=True)
        cmds.setAttr(matrix + ".in%s3" % row, 0.0)

    for component_index, component in enumerate(("X", "Y", "Z")):
        cmds.connectAttr(center + component, matrix + ".in3%s" % component_index, force=True)
    cmds.setAttr(matrix + ".in33", 1.0)
    return matrix


def _validate_transform(node: str, label: str) -> None:
    if not node or not cmds.objExists(node):
        raise RuntimeError("%s does not exist: %s" % (label, node))
    if cmds.nodeType(node) != "transform":
        raise TypeError("%s must be a transform: %s" % (label, node))


def _validate_initial_plane(points: tuple[str, ...]) -> None:
    positions = tuple(_world_position(point) for point in points)
    u_vector = _add(_subtract(positions[1], positions[0]), _subtract(positions[2], positions[3]))
    v_vector = _add(_subtract(positions[3], positions[0]), _subtract(positions[2], positions[1]))
    if _length(u_vector) <= _EPSILON:
        raise ValueError("Four-point plane horizontal direction is zero length.")
    if _length(v_vector) <= _EPSILON:
        raise ValueError("Four-point plane vertical direction is zero length.")
    if _length(_cross(u_vector, v_vector)) <= _EPSILON:
        raise ValueError("Four-point plane points cannot form a stable plane.")


def _world_position(node: str) -> Vector3:
    position = cmds.xform(node, query=True, worldSpace=True, translation=True)
    return float(position[0]), float(position[1]), float(position[2])


def _normalize_axis_name(axis: str) -> NormalAxis:
    axis = axis.lower().strip()
    if len(axis) == 1 and axis in ("x", "y", "z"):
        axis = "+" + axis
    if axis not in _AXES:
        raise ValueError("normal_axis must be one of %s, got: %s" % (", ".join(_AXES), axis))
    return cast("NormalAxis", axis)


def _axis_vector(axis: NormalAxis) -> Vector3:
    sign = -1.0 if axis.startswith("-") else 1.0
    axis_name = axis[-1]
    if axis_name == "x":
        return sign, 0.0, 0.0
    if axis_name == "y":
        return 0.0, sign, 0.0
    return 0.0, 0.0, sign


def _add(a: Vector3, b: Vector3) -> Vector3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def _subtract(a: Vector3, b: Vector3) -> Vector3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(vector: Vector3) -> float:
    return math.sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2])


def _create_node(node_type: str, prefix: str, suffix: str, nodes: list[str]) -> str:
    node = cmds.createNode(node_type, name=prefix + "_" + suffix)
    nodes.append(node)
    return node


def _tag_node(node: str, target: str) -> None:
    if not cmds.attributeQuery("fourPointPlaneTarget", node=node, exists=True):
        cmds.addAttr(node, longName="fourPointPlaneTarget", attributeType="message")
    cmds.connectAttr(target + ".message", node + ".fourPointPlaneTarget", force=True)


def _short_name(node: str) -> str:
    return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
