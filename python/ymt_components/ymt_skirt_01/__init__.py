"""Collider-driven skirt component."""

from __future__ import annotations

import importlib
import math
import re
from typing import TYPE_CHECKING, Tuple, cast  # noqa: UP035

cmds = importlib.import_module("maya.cmds")
om2 = importlib.import_module("maya.api.OpenMaya")

try:
    pm = importlib.import_module("mgear.pymaya")
except ImportError:
    pm = importlib.import_module("pymel.core")
try:
    datatypes = importlib.import_module("mgear.pymaya.datatypes")
except ImportError:
    datatypes = importlib.import_module("pymel.core.datatypes")

attribute = importlib.import_module("mgear.core.attribute")
component = importlib.import_module("mgear.shifter.component")

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing import Union

    from ymt_shifter_utility.type_protocols import MatrixLike, PymelNode

    MatrixSource = Union[MatrixLike, "Sequence[Sequence[float]]", "Sequence[float]"]


AUTHOR = "yamahigashi"
VERSION = [1, 1, 0]
TYPE = "ymt_skirt_01"
NAME = "skirt"

FIXED_REFERENCE_NAMES = ("waist", "hip_L", "knee_L", "heel_L", "hip_R", "knee_R", "heel_R")
GRID_NAME_RE = re.compile(r"^skirt_(\d+)_(\d+)_loc$")
# typing.Tuple, not builtin tuple: runtime aliases must import under Maya 2022 (Python 3.7).
Vector3 = Tuple[float, float, float]  # noqa: UP006
Matrix16 = Tuple[float, ...]  # noqa: UP006


def _add(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _subtract(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _multiply(value: Vector3, scalar: float) -> Vector3:
    return (value[0] * scalar, value[1] * scalar, value[2] * scalar)


def _dot(a: Vector3, b: Vector3) -> float:
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    )


def _length(value: Vector3) -> float:
    return math.sqrt(_dot(value, value))


def _normalize(value: Vector3, label: str, threshold: float) -> Vector3:
    magnitude = _length(value)
    if magnitude < threshold:
        raise RuntimeError("ymt_skirt_01 requires a non-degenerate %s." % label)
    return _multiply(value, 1.0 / magnitude)


def _distance(a: Vector3, b: Vector3) -> float:
    return _length(_subtract(a, b))


def _matrix_from_axes(x_axis: Vector3, y_axis: Vector3, z_axis: Vector3, position: Vector3) -> Matrix16:
    return (
        x_axis[0],
        x_axis[1],
        x_axis[2],
        0.0,
        y_axis[0],
        y_axis[1],
        y_axis[2],
        0.0,
        z_axis[0],
        z_axis[1],
        z_axis[2],
        0.0,
        position[0],
        position[1],
        position[2],
        1.0,
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _ring_stations(d_knee: float, d_heel: float, hem_projection: float) -> tuple[float, float | None]:
    knee_station = min(d_knee, hem_projection)
    ankle_station = min(d_heel, hem_projection)
    if ankle_station - knee_station < 0.05 * hem_projection:
        return ankle_station, None
    return knee_station, ankle_station


def _station_radius(station: float, projections: Sequence[float], radii: Sequence[float]) -> float:
    if station <= projections[0]:
        return radii[0]
    for index in range(1, len(projections)):
        upper_projection = projections[index]
        if station <= upper_projection:
            lower_projection = projections[index - 1]
            ratio = (station - lower_projection) / (upper_projection - lower_projection)
            return radii[index - 1] + (ratio * (radii[index] - radii[index - 1]))
    return radii[-1]


def _ring_weights(
    axial_projection: float,
    first_projection: float,
    knee_station: float,
    ankle_station: float | None,
) -> tuple[float, float]:
    if knee_station <= first_projection:
        rise = 1.0
    else:
        rise = _clamp(
            (axial_projection - first_projection) / (knee_station - first_projection),
            0.0,
            1.0,
        )
    if ankle_station is None:
        return rise, 0.0
    if axial_projection <= knee_station:
        ankle_weight = 0.0
    elif axial_projection >= ankle_station:
        ankle_weight = 1.0
    else:
        ankle_weight = (axial_projection - knee_station) / (ankle_station - knee_station)
    return rise * (1.0 - ankle_weight), ankle_weight


def _blend_node_weights(knee_weight: float, ankle_weight: float) -> tuple[float, float]:
    node_ankle_weight = ankle_weight
    node_knee_weight = 0.0 if ankle_weight == 1.0 else knee_weight / (1.0 - ankle_weight)
    return node_knee_weight, node_ankle_weight


class Component(component.Main):
    """Shifter component class."""

    def addObjects(self) -> None:
        self._ensure_colliders_plugin()
        self.rows, self.cols = self._validated_dimensions()
        self.guide_size = self._validated_guide_size()
        self.reference_matrices = self._validated_reference_matrices()
        self.grid_matrices = self._validated_grid_matrices()
        self.reference_positions = {
            name: self._matrix_position(matrix) for name, matrix in self.reference_matrices.items()
        }
        self.grid_positions = {cell: self._matrix_position(matrix) for cell, matrix in self.grid_matrices.items()}
        self._fit_cone()
        self.ctl_size = self.guide_size * self._validated_positive_setting("ctlSize") * 0.1
        self.add_joints = self._validated_bool_setting("addJoints")
        self._validate_animator_settings()

        self.refs_group = self._create_refs_group()
        self.skirt_collider_refs = self._create_internal_references()
        self._create_ring_controllers()
        self.collider_node = self._create_collider_node()
        self._connect_collider_references()
        self._configure_collider()
        self.collider_surface, self.collider_surface_shape = self._create_rebuilt_surface()
        self.surface_u_values = self._surface_u_parameters()
        self.surface_v_values = self._surface_v_parameters()
        self.npos: dict[tuple[int, int], PymelNode] = {}
        self.ring_offsets: dict[tuple[int, int], PymelNode] = {}
        self.fk_ctls: list[PymelNode] = []
        self.fk_ctls_by_cell: dict[tuple[int, int], PymelNode] = {}
        self._create_surface_drivers_and_controls()
        self._assert_ring_control_identity()
        if not self.settings.get("ui_host"):
            self.uihost = self.fk_ctls[0]

    def addOperators(self) -> None:
        return

    def addAttributes(self) -> None:
        self.collision_att = self.addAnimParam(
            "collision", "Collision", "double", float(self.settings["collision"]), 0.0, 1.0
        )
        self.tightness_att = self.addAnimParam(
            "tightness", "Tightness (Long Only)", "double", float(self.settings["tightness"]), 0.0, 1.0
        )
        self.falloff_att = self.addAnimParam("falloff", "Falloff", "double", float(self.settings["falloff"]), -1.0, 1.0)
        cmds.connectAttr(str(self.collision_att), self.collider_node + ".collision", force=True)
        cmds.connectAttr(str(self.tightness_att), self.collider_node + ".tightness", force=True)
        cmds.connectAttr(str(self.falloff_att), self.collider_node + ".falloff", force=True)

    def setRelation(self) -> None:
        self.relatives["root"] = self.fk_ctls[0]
        self.controlRelatives["root"] = self.fk_ctls[0]
        self.aliasRelatives["root"] = "skirtRoot"
        self.relatives["ringKnee"] = self.ring_knee_ctl
        self.controlRelatives["ringKnee"] = self.ring_knee_ctl
        self.aliasRelatives["ringKnee"] = "ringKnee"
        if self.ring_ankle_ctl is not None:
            self.relatives["ringAnkle"] = self.ring_ankle_ctl
            self.controlRelatives["ringAnkle"] = self.ring_ankle_ctl
            self.aliasRelatives["ringAnkle"] = "ringAnkle"
        for (row, col), ctl in self.fk_ctls_by_cell.items():
            local_name = "skirt_%s_%s_loc" % (row, col)
            self.relatives[local_name] = ctl
            self.controlRelatives[local_name] = ctl
            self.aliasRelatives[local_name] = "%s_%s" % (row, col)

    def addConnection(self) -> None:
        self.connections["standard"] = self.connect_standard

    def connect_standard(self) -> None:
        self.parent.addChild(self.root)

    def get_skirt_collider_refs(self) -> dict[str, PymelNode]:
        return dict(self.skirt_collider_refs)

    def _ensure_colliders_plugin(self) -> None:
        try:
            loaded = cmds.pluginInfo("colliders", query=True, loaded=True)
        except RuntimeError:
            loaded = False
        if loaded:
            return
        try:
            cmds.loadPlugin("colliders")
        except RuntimeError as exc:
            maya_version = cmds.about(version=True)
            raise RuntimeError("ymt_skirt_01 requires the colliders plugin for Maya %s." % maya_version) from exc

    def _validated_dimensions(self) -> tuple[int, int]:
        rows = self._integer_setting("rows")
        cols = self._integer_setting("cols")
        if rows < 2 or cols < 3:
            raise RuntimeError("ymt_skirt_01 requires rows >= 2 and cols >= 3; got rows=%s, cols=%s." % (rows, cols))
        return rows, cols

    def _integer_setting(self, name: str) -> int:
        if name not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the %s setting." % name)
        value = self.settings[name]
        if isinstance(value, bool):
            raise RuntimeError("ymt_skirt_01 %s must be an integer." % name)
        try:
            result = int(value)
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ymt_skirt_01 %s must be an integer." % name) from exc
        if not math.isfinite(numeric_value) or numeric_value != result:
            raise RuntimeError("ymt_skirt_01 %s must be an integer." % name)
        return result

    def _validated_guide_size(self) -> float:
        try:
            value = float(self.size)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ymt_skirt_01 requires a finite positive guide size.") from exc
        if not math.isfinite(value) or value <= 0.0:
            raise RuntimeError("ymt_skirt_01 requires a finite positive guide size.")
        return value

    def _validated_reference_matrices(self) -> dict[str, Matrix16]:
        matrices: dict[str, Matrix16] = {}
        for name in FIXED_REFERENCE_NAMES:
            if name not in self.guide.tra:
                raise RuntimeError("ymt_skirt_01 is missing fixed reference transform: %s." % name)
            matrices[name] = self._finite_matrix(self.guide.tra[name], "fixed reference %s" % name)
        if "root" not in self.guide.tra:
            raise RuntimeError("ymt_skirt_01 is missing the guide root transform.")
        self.guide_root_matrix = self._finite_matrix(self.guide.tra["root"], "guide root")
        return matrices

    def _validated_grid_matrices(self) -> dict[tuple[int, int], Matrix16]:
        expected_names = {"skirt_%s_%s_loc" % (row, col) for row in range(self.rows) for col in range(self.cols)}
        serialized_names = {name for name in self.guide.tra if name.startswith("skirt_") and name.endswith("_loc")}
        name_counts = dict(getattr(self.guide, "grid_locator_name_counts", {}))
        for name in serialized_names:
            name_counts[name] = max(1, int(name_counts.get(name, 0)))
        found_names = serialized_names.union(name_counts)
        missing = sorted(expected_names.difference(found_names))
        extra = sorted(found_names.difference(expected_names))
        duplicates = sorted(name for name, count in name_counts.items() if int(count) > 1)
        if missing or extra or duplicates:
            raise RuntimeError(
                "ymt_skirt_01 grid locator names do not match rows/cols; missing=%s, extra=%s, duplicate=%s."
                % (missing, extra, duplicates)
            )

        matrices: dict[tuple[int, int], Matrix16] = {}
        for name in sorted(expected_names, key=self._grid_name_sort_key):
            match = GRID_NAME_RE.fullmatch(name)
            if match is None or name not in self.guide.tra:
                raise RuntimeError("ymt_skirt_01 could not collect grid transform: %s." % name)
            cell = (int(match.group(1)), int(match.group(2)))
            matrices[cell] = self._finite_matrix(self.guide.tra[name], "grid locator %s" % name)
        return matrices

    def _grid_name_sort_key(self, name: str) -> tuple[int, int]:
        match = GRID_NAME_RE.fullmatch(name)
        if match is None:
            return (-1, -1)
        return (int(match.group(1)), int(match.group(2)))

    def _finite_matrix(self, matrix: MatrixSource, label: str) -> Matrix16:
        try:
            values = self._matrix_values(matrix)
        except (IndexError, TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("ymt_skirt_01 has a malformed %s transform." % label) from exc
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError("ymt_skirt_01 has a non-finite %s transform." % label)
        return values

    def _matrix_values(self, matrix: MatrixSource) -> Matrix16:
        matrix_get = getattr(matrix, "get", None)
        raw = cast(
            "Sequence[float] | Sequence[Sequence[float]]",
            matrix_get() if callable(matrix_get) else matrix,
        )
        if isinstance(raw[0], (int, float)):
            flat_values = cast("Sequence[float]", raw)
            flat = tuple(float(flat_values[index]) for index in range(16))
        else:
            nested_values = cast("Sequence[Sequence[float]]", raw)
            flat = tuple(float(nested_values[row][column]) for row in range(4) for column in range(4))
        if len(flat) != 16:
            raise RuntimeError("ymt_skirt_01 expected a 4x4 transform matrix.")
        return flat

    def _matrix_position(self, matrix: Matrix16) -> Vector3:
        return (matrix[12], matrix[13], matrix[14])

    def _fit_cone(self) -> None:
        epsilon = 0.001 * self.guide_size
        self._fit_bell_frame(epsilon)
        self._fit_grid_profile(epsilon)
        hip_distance = self._fit_chain_height(epsilon)
        self.hem_radius = self.row_mean_radii[-1]
        self.ring_radius_x = hip_distance * 0.5 * self._validated_positive_setting("ringScaleX")
        self.ring_radius_z = hip_distance * 0.5 * self._validated_positive_setting("ringScaleZ")
        self.ring_height_scale = self._validated_positive_setting("ringScaleY")
        self._fit_aim_frames()

    def _fit_bell_frame(self, epsilon: float) -> None:
        waist = self.reference_positions["waist"]
        heel_mid = _multiply(_add(self.reference_positions["heel_L"], self.reference_positions["heel_R"]), 0.5)
        axis_vector = _subtract(heel_mid, waist)
        axis_length = _length(axis_vector)
        if axis_length < epsilon:
            raise RuntimeError("ymt_skirt_01 waist-to-heel axis is shorter than 1e-3 times guide size.")
        self.axis = _multiply(axis_vector, 1.0 / axis_length)

        raw_front = (self.guide_root_matrix[8], self.guide_root_matrix[9], self.guide_root_matrix[10])
        front = _normalize(raw_front, "guide root front axis", 1.0e-8)
        projected_front = _subtract(front, _multiply(self.axis, _dot(front, self.axis)))
        if _length(projected_front) < 0.001:
            raise RuntimeError("ymt_skirt_01 guide root front is parallel to the cone axis within 1e-3.")
        self.bell_x_axis = _normalize(projected_front, "projected guide root front", 1.0e-8)
        self.bell_z_axis = _normalize(_cross(self.bell_x_axis, self.axis), "bell frame Z axis", 1.0e-8)
        self.bell_matrix = _matrix_from_axes(self.bell_x_axis, self.axis, self.bell_z_axis, waist)

    def _fit_grid_profile(self, epsilon: float) -> None:
        waist = self.reference_positions["waist"]
        self.row_axial_projections = []
        self.row_mean_radii = []
        previous_projection = None
        for row in range(self.rows):
            positions = [self.grid_positions[(row, col)] for col in range(self.cols)]
            centroid = _multiply(self._sum_vectors(positions), 1.0 / self.cols)
            projection = _dot(_subtract(centroid, waist), self.axis)
            if previous_projection is not None and projection <= previous_projection:
                raise RuntimeError(
                    "ymt_skirt_01 row centroid axial projections must be strictly increasing; row %s is not." % row
                )
            previous_projection = projection
            radii = [self._axis_radius(position, waist) for position in positions]
            mean_radius = sum(radii) / self.cols
            if mean_radius < epsilon:
                raise RuntimeError("ymt_skirt_01 row %s mean radius is shorter than 1e-3 times guide size." % row)
            self._validate_distinct_row_positions(row, positions, epsilon)
            self.row_axial_projections.append(projection)
            self.row_mean_radii.append(mean_radius)

    def _fit_chain_height(self, epsilon: float) -> float:
        waist = self.reference_positions["waist"]
        hip_left = self.reference_positions["hip_L"]
        hip_right = self.reference_positions["hip_R"]
        hip_distance = _distance(hip_left, hip_right)
        if hip_distance < epsilon:
            raise RuntimeError("ymt_skirt_01 hip-to-hip distance is shorter than 1e-3 times guide size.")

        thigh_length = 0.5 * (
            _distance(hip_left, self.reference_positions["knee_L"])
            + _distance(hip_right, self.reference_positions["knee_R"])
        )
        calf_length = 0.5 * (
            _distance(self.reference_positions["knee_L"], self.reference_positions["heel_L"])
            + _distance(self.reference_positions["knee_R"], self.reference_positions["heel_R"])
        )
        hip_mid = _multiply(_add(hip_left, hip_right), 0.5)
        self.d_hip = _distance(hip_mid, waist)
        self.d_knee = self.d_hip + thigh_length
        self.d_heel = self.d_knee + calf_length
        if self.d_knee - self.d_hip < 1.0e-5:
            raise RuntimeError("ymt_skirt_01 thigh interpolation denominator is shorter than 1e-5.")
        if self.d_heel - self.d_knee < 1.0e-5:
            raise RuntimeError("ymt_skirt_01 calf interpolation denominator is shorter than 1e-5.")

        hem_projection = self.row_axial_projections[-1]
        self.skirt_type = 1 if hem_projection > self.d_knee else 0
        if self.skirt_type == 0:
            self.height = (hem_projection - self.d_hip) / (self.d_knee - self.d_hip)
        else:
            self.height = (hem_projection - self.d_knee) / (self.d_heel - self.d_knee)
        if not math.isfinite(self.height) or self.height < 0.01 or self.height > 1.0:
            raise RuntimeError("ymt_skirt_01 fitted height is outside [0.01, 1.0]: %s." % self.height)
        return hip_distance

    def _fit_aim_frames(self) -> None:
        hip_left = self.reference_positions["hip_L"]
        hip_right = self.reference_positions["hip_R"]
        self.aim_matrices = {
            "hip_L": self._aim_matrix(hip_left, self.reference_positions["knee_L"], "hip_L"),
            "knee_L": self._aim_matrix(
                self.reference_positions["knee_L"], self.reference_positions["heel_L"], "knee_L"
            ),
            "hip_R": self._aim_matrix(hip_right, self.reference_positions["knee_R"], "hip_R"),
            "knee_R": self._aim_matrix(
                self.reference_positions["knee_R"], self.reference_positions["heel_R"], "knee_R"
            ),
        }
        self.aim_matrices["heel_L"] = self._matrix_with_position(
            self.aim_matrices["knee_L"], self.reference_positions["heel_L"]
        )
        self.aim_matrices["heel_R"] = self._matrix_with_position(
            self.aim_matrices["knee_R"], self.reference_positions["heel_R"]
        )

    def _sum_vectors(self, values: Sequence[Vector3]) -> Vector3:
        result = (0.0, 0.0, 0.0)
        for value in values:
            result = _add(result, value)
        return result

    def _axis_radius(self, position: Vector3, axis_origin: Vector3) -> float:
        offset = _subtract(position, axis_origin)
        perpendicular = _subtract(offset, _multiply(self.axis, _dot(offset, self.axis)))
        return _length(perpendicular)

    def _validate_distinct_row_positions(self, row: int, positions: Sequence[Vector3], epsilon: float) -> None:
        for first in range(len(positions)):
            for second in range(first + 1, len(positions)):
                if _distance(positions[first], positions[second]) < epsilon:
                    raise RuntimeError(
                        "ymt_skirt_01 row %s has coincident locators skirt_%s_%s_loc and skirt_%s_%s_loc."
                        % (row, row, first, row, second)
                    )

    def _aim_matrix(self, position: Vector3, target: Vector3, name: str) -> Matrix16:
        aim = _normalize(_subtract(target, position), "%s aim direction" % name, 1.0e-5)
        projected_up = _subtract(self.bell_x_axis, _multiply(aim, _dot(self.bell_x_axis, aim)))
        if _length(projected_up) < 0.001:
            raise RuntimeError("ymt_skirt_01 %s aim up-vector is parallel to its aim direction within 1e-3." % name)
        up = _normalize(projected_up, "%s projected aim up-vector" % name, 1.0e-8)
        side = _normalize(_cross(aim, up), "%s aim frame Z axis" % name, 1.0e-8)
        return _matrix_from_axes(aim, up, side, position)

    def _matrix_with_position(self, matrix: Matrix16, position: Vector3) -> Matrix16:
        return _matrix_from_axes(
            (matrix[0], matrix[1], matrix[2]),
            (matrix[4], matrix[5], matrix[6]),
            (matrix[8], matrix[9], matrix[10]),
            position,
        )

    def _validated_positive_setting(self, name: str) -> float:
        if name not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the %s setting." % name)
        try:
            value = float(self.settings[name])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ymt_skirt_01 %s must be finite and positive." % name) from exc
        if not math.isfinite(value) or value <= 0.0:
            raise RuntimeError("ymt_skirt_01 %s must be finite and positive." % name)
        return value

    def _validate_animator_settings(self) -> None:
        self._validated_range_setting("collision", 0.0, 1.0)
        self._validated_range_setting("tightness", 0.0, 1.0)
        self._validated_range_setting("falloff", -1.0, 1.0)

    def _validated_bool_setting(self, name: str) -> bool:
        if name not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the %s setting." % name)
        value = self.settings[name]
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise RuntimeError("ymt_skirt_01 %s must be a boolean." % name)

    def _validated_range_setting(self, name: str, minimum: float, maximum: float) -> float:
        if name not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the %s setting." % name)
        try:
            value = float(self.settings[name])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ymt_skirt_01 %s must be within [%s, %s]." % (name, minimum, maximum)) from exc
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise RuntimeError("ymt_skirt_01 %s must be within [%s, %s]." % (name, minimum, maximum))
        return value

    def _create_refs_group(self) -> PymelNode:
        group_name = cmds.createNode("transform", name=self.getName("colliderRefs"), parent=self._node_name(self.root))
        cmds.setAttr(group_name + ".visibility", False)
        return pm.PyNode(group_name)

    def _create_internal_references(self) -> dict[str, PymelNode]:
        matrices = {
            "waist": self.bell_matrix,
            "hip_L": self.aim_matrices["hip_L"],
            "knee_L": self.aim_matrices["knee_L"],
            "heel_L": self.aim_matrices["heel_L"],
            "hip_R": self.aim_matrices["hip_R"],
            "knee_R": self.aim_matrices["knee_R"],
            "heel_R": self.aim_matrices["heel_R"],
        }
        rig_names = {
            "waist": "waistRef",
            "hip_L": "hipRef_L",
            "knee_L": "kneeRef_L",
            "heel_L": "heelRef_L",
            "hip_R": "hipRef_R",
            "knee_R": "kneeRef_R",
            "heel_R": "heelRef_R",
        }
        refs: dict[str, PymelNode] = {}
        for name in FIXED_REFERENCE_NAMES:
            node = cmds.createNode(
                "transform",
                name=self.getName(rig_names[name]),
                parent=self._node_name(self.refs_group),
            )
            cmds.xform(node, worldSpace=True, matrix=matrices[name])
            for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
                cmds.setAttr(node + "." + channel, lock=False, keyable=False, channelBox=False)
            refs[name] = pm.PyNode(node)
        return refs

    def _create_ring_controllers(self) -> None:
        hem_projection = self.row_axial_projections[-1]
        self.knee_station, self.ankle_station = _ring_stations(self.d_knee, self.d_heel, hem_projection)
        first_projection = self.row_axial_projections[0]
        self.ring_row_weights = [
            _ring_weights(projection, first_projection, self.knee_station, self.ankle_station)
            for projection in self.row_axial_projections
        ]
        group_name = cmds.createNode(
            "transform",
            name=self.getName("ringCtls"),
            parent=self._node_name(self.root),
        )
        cmds.setAttr(group_name + ".visibility", True)
        self.ring_ctls_group = pm.PyNode(group_name)
        self.ring_ctls: list[PymelNode] = []
        self.ring_constraint_nodes: list[tuple[PymelNode, str]] = []
        self.ring_delta_nodes: dict[str, str] = {}

        self.ring_knee_ctl = self._create_ring_controller("ringKnee", self.knee_station)
        self.ring_ankle_ctl: PymelNode | None = None
        if self.ankle_station is not None:
            self.ring_ankle_ctl = self._create_ring_controller("ringAnkle", self.ankle_station)

    def _create_ring_controller(self, stem: str, station: float) -> PymelNode:
        position = _add(self.reference_positions["waist"], _multiply(self.axis, station))
        frame_values = _matrix_from_axes(self.bell_x_axis, self.axis, self.bell_z_axis, position)
        frame = datatypes.Matrix(frame_values)
        npo_name = cmds.createNode(
            "transform",
            name=self.getName(stem + "_npo"),
            parent=self._node_name(self.ring_ctls_group),
        )
        cmds.xform(npo_name, worldSpace=True, matrix=frame_values)
        constraints = cmds.parentConstraint(
            self._node_name(self.skirt_collider_refs["waist"]),
            npo_name,
            maintainOffset=True,
            name=self.getName(stem + "_parentConstraint"),
        )
        if not constraints:
            raise RuntimeError("ymt_skirt_01 could not constrain %s to waistRef." % self.getName(stem + "_npo"))

        radius = _station_radius(station, self.row_axial_projections, self.row_mean_radii) * 1.1
        npo = pm.PyNode(npo_name)
        ctl = self.addCtl(
            npo,
            stem + "_ctl",
            frame,
            self.color_ik,
            "circle",
            w=radius * 2.0,
            tp=self.parentCtlTag,
        )
        attribute.setKeyableAttributes(ctl, ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"])
        ctl_name = self._node_name(ctl)
        cmds.setAttr(
            ctl_name + ".offsetParentMatrix",
            *self._identity_matrix(),
            type="matrix",
        )

        delta = cmds.createNode("multMatrix", name=self.getName(stem + "_delta_mm"))
        cmds.connectAttr(npo_name + ".worldInverseMatrix[0]", delta + ".matrixIn[0]", force=True)
        cmds.connectAttr(ctl_name + ".matrix", delta + ".matrixIn[1]", force=True)
        cmds.connectAttr(npo_name + ".worldMatrix[0]", delta + ".matrixIn[2]", force=True)
        self.ring_ctls.append(ctl)
        self.ring_constraint_nodes.append((ctl, str(constraints[0])))
        self.ring_delta_nodes[stem] = delta
        return ctl

    def _assert_ring_control_identity(self) -> None:
        identity = self._identity_matrix()
        for ctl, constraint in self.ring_constraint_nodes:
            cmds.getAttr(constraint + ".constraintTranslate")
            ctl_name = self._node_name(ctl)
            local_matrix = self._matrix_attr(ctl_name + ".matrix")
            if any(abs(value - expected) > 1.0e-6 for value, expected in zip(local_matrix, identity)):
                raise RuntimeError("ymt_skirt_01 ring control local matrix is not identity: %s." % ctl_name)

    def _create_collider_node(self) -> str:
        node = cmds.createNode("skirtBellCollider", name=self.getName("skirtBellCollider"))
        parents = cmds.listRelatives(node, parent=True, type="transform", fullPath=True) or []
        if len(parents) != 1:
            raise RuntimeError("ymt_skirt_01 could not resolve the skirtBellCollider transform.")
        collider_transform = cmds.rename(parents[0], self.getName("skirtBellColliderTransform"))
        cmds.parent(collider_transform, self._node_name(self.root))
        # The node draws in world space; inheriting the root transform double-transforms it.
        cmds.setAttr(collider_transform + ".inheritsTransform", False)
        cmds.setAttr(collider_transform + ".translate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(collider_transform + ".rotate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(collider_transform + ".scale", 1.0, 1.0, 1.0, type="double3")
        cmds.setAttr(collider_transform + ".visibility", False)
        self.collider_transform = pm.PyNode(collider_transform)
        return node

    def _connect_collider_references(self) -> None:
        attributes = {
            "waist": "bellMatrix",
            "hip_L": "leftHipMatrix",
            "knee_L": "leftKneeMatrix",
            "heel_L": "leftHeelMatrix",
            "hip_R": "rightHipMatrix",
            "knee_R": "rightKneeMatrix",
            "heel_R": "rightHeelMatrix",
        }
        for name, collider_attribute in attributes.items():
            cmds.connectAttr(
                self._node_name(self.skirt_collider_refs[name]) + ".worldMatrix[0]",
                self.collider_node + "." + collider_attribute,
                force=True,
            )

    def _configure_collider(self) -> None:
        cmds.setAttr(self.collider_node + ".skirtType", self.skirt_type)
        cmds.setAttr(self.collider_node + ".height", self.height)
        cmds.setAttr(self.collider_node + ".leftRingAxis", 0)
        cmds.setAttr(self.collider_node + ".rightRingAxis", 0)
        cmds.setAttr(self.collider_node + ".bellAxis", 1)
        cmds.setAttr(self.collider_node + ".collision", float(self.settings["collision"]))
        cmds.setAttr(self.collider_node + ".tightness", float(self.settings["tightness"]))
        cmds.setAttr(self.collider_node + ".falloff", float(self.settings["falloff"]))
        self._configure_global_scale()
        self._rewrite_bell_scale_ramp()

    def _configure_global_scale(self) -> None:
        root_matrix = self._matrix_attr(self._node_name(self.root) + ".worldMatrix[0]")
        scale_x = _length((root_matrix[0], root_matrix[1], root_matrix[2]))
        scale_z = _length((root_matrix[8], root_matrix[9], root_matrix[10]))
        if scale_x < 1.0e-8 or scale_z < 1.0e-8:
            raise RuntimeError("ymt_skirt_01 component root world scale is degenerate.")

        scale_decompose = cmds.createNode("decomposeMatrix", name=self.getName("rootScale_dm"))
        cmds.connectAttr(self._node_name(self.root) + ".worldMatrix[0]", scale_decompose + ".inputMatrix", force=True)
        bell_multiply = self._create_scale_multiply(
            "bellScale",
            self.hem_radius / scale_x,
            self.hem_radius / scale_z,
            scale_decompose,
        )
        ring_multiply = self._create_scale_multiply(
            "ringScale",
            self.ring_radius_x / scale_x,
            self.ring_radius_z / scale_z,
            scale_decompose,
        )
        # k3Double children are auto-named with 0/1/2 suffixes, not X/Y/Z.
        cmds.connectAttr(bell_multiply + ".outputX", self.collider_node + ".bellScale0", force=True)
        cmds.connectAttr(bell_multiply + ".outputZ", self.collider_node + ".bellScale2", force=True)
        cmds.connectAttr(ring_multiply + ".outputX", self.collider_node + ".ringScale0", force=True)
        cmds.connectAttr(ring_multiply + ".outputZ", self.collider_node + ".ringScale2", force=True)
        cmds.setAttr(self.collider_node + ".bellScale1", 1.0)
        cmds.setAttr(self.collider_node + ".ringScale1", self.ring_height_scale)
        self.root_scale_decompose = scale_decompose

    def _create_scale_multiply(
        self,
        name: str,
        fitted_x: float,
        fitted_z: float,
        scale_decompose: str,
    ) -> str:
        multiply = cmds.createNode("multiplyDivide", name=self.getName(name + "_md"))
        cmds.setAttr(multiply + ".operation", 1)
        cmds.setAttr(multiply + ".input1X", fitted_x)
        cmds.setAttr(multiply + ".input1Z", fitted_z)
        cmds.connectAttr(scale_decompose + ".outputScaleX", multiply + ".input2X", force=True)
        cmds.connectAttr(scale_decompose + ".outputScaleZ", multiply + ".input2Z", force=True)
        return multiply

    def _rewrite_bell_scale_ramp(self) -> None:
        ramp = self.collider_node + ".bellScaleRamp"
        indices = cmds.getAttr(ramp, multiIndices=True) or []
        for index in sorted(indices, reverse=True):
            cmds.removeMultiInstance("%s[%s]" % (ramp, index), b=True)
        hem_projection = self.row_axial_projections[-1]
        for row, (projection, radius) in enumerate(zip(self.row_axial_projections, self.row_mean_radii)):
            element = "%s[%s]" % (ramp, row)
            cmds.setAttr(element + ".bellScaleRamp_Position", projection / hem_projection)
            cmds.setAttr(element + ".bellScaleRamp_FloatValue", radius / self.hem_radius)
            cmds.setAttr(element + ".bellScaleRamp_Interp", 1)

    def _create_rebuilt_surface(self) -> tuple[PymelNode, str]:
        surface = cmds.createNode(
            "transform",
            name=self.getName("colliderSurface"),
            parent=self._node_name(self.root),
        )
        cmds.setAttr(surface + ".inheritsTransform", False)
        cmds.setAttr(surface + ".translate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(surface + ".rotate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(surface + ".scale", 1.0, 1.0, 1.0, type="double3")
        cmds.setAttr(surface + ".visibility", False)
        shape = cmds.createNode("nurbsSurface", name=self.getName("colliderSurfaceShape"), parent=surface)
        rebuild = cmds.createNode("rebuildSurface", name=self.getName("colliderSurface_rebuild"))
        cmds.setAttr(rebuild + ".direction", 1)
        cmds.setAttr(rebuild + ".spansU", 1)
        cmds.setAttr(rebuild + ".spansV", 4)
        cmds.setAttr(rebuild + ".degreeU", 3)
        cmds.setAttr(rebuild + ".degreeV", 3)
        cmds.setAttr(rebuild + ".keepRange", 0)
        cmds.connectAttr(self.collider_node + ".outputSurface", rebuild + ".inputSurface", force=True)
        cmds.connectAttr(rebuild + ".outputSurface", shape + ".create", force=True)
        self.surface_rebuild_node = rebuild
        return pm.PyNode(surface), shape

    def _surface_u_parameters(self) -> list[float]:
        minimum = float(cmds.getAttr(self.collider_surface_shape + ".minValueU"))
        maximum = float(cmds.getAttr(self.collider_surface_shape + ".maxValueU"))
        if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
            raise RuntimeError("ymt_skirt_01 rebuilt surface has an invalid U range.")
        minimum_v = float(cmds.getAttr(self.collider_surface_shape + ".minValueV"))
        maximum_v = float(cmds.getAttr(self.collider_surface_shape + ".maxValueV"))
        sample_v = (minimum_v + maximum_v) * 0.5
        # The node's knot origin is not guaranteed to align with the bell front axis, so
        # calibrate each column U against the sampled surface angle instead of assuming it.
        sample_count = max(256, self.cols * 64)
        sampled = []
        for index in range(sample_count):
            u_value = minimum + ((index / float(sample_count)) * (maximum - minimum))
            sampled.append((u_value, self._surface_angle(self._surface_point(u_value, sample_v))))
        parameters = []
        for col in range(self.cols):
            target = self._column_mean_angle(col)
            best_u = sampled[0][0]
            best_difference = None
            for u_value, angle in sampled:
                difference = abs(self._wrap_angle(angle - target))
                if best_difference is None or difference < best_difference:
                    best_u = u_value
                    best_difference = difference
            parameters.append(best_u)
        return parameters

    def _surface_angle(self, position: Vector3) -> float:
        # Angle around the cone axis, measured from the bell front axis, positive clockwise
        # when viewed from the waist looking toward the hem.
        waist = self.reference_positions["waist"]
        offset = _subtract(position, waist)
        radial = _subtract(offset, _multiply(self.axis, _dot(offset, self.axis)))
        side = _cross(self.axis, self.bell_x_axis)
        return math.atan2(_dot(radial, side), _dot(radial, self.bell_x_axis))

    def _column_mean_angle(self, col: int) -> float:
        sine_sum = 0.0
        cosine_sum = 0.0
        for row in range(self.rows):
            angle = self._surface_angle(self.grid_positions[(row, col)])
            sine_sum += math.sin(angle)
            cosine_sum += math.cos(angle)
        if abs(sine_sum) < 1.0e-9 and abs(cosine_sum) < 1.0e-9:
            raise RuntimeError("ymt_skirt_01 column %s has no defined mean angle around the cone axis." % col)
        return math.atan2(sine_sum, cosine_sum)

    def _wrap_angle(self, angle: float) -> float:
        return math.atan2(math.sin(angle), math.cos(angle))

    def _surface_point(self, u_value: float, v_value: float) -> Vector3:
        values = cmds.pointOnSurface(
            self.collider_surface_shape,
            parameterU=u_value,
            parameterV=v_value,
            position=True,
        )
        if values is None or len(values) != 3:
            raise RuntimeError("ymt_skirt_01 could not sample the rebuilt collider surface.")
        point = (float(values[0]), float(values[1]), float(values[2]))
        if not all(math.isfinite(value) for value in point):
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface returned a non-finite sample.")
        return point

    def _surface_v_parameters(self) -> list[float]:
        minimum = float(cmds.getAttr(self.collider_surface_shape + ".minValueV"))
        maximum = float(cmds.getAttr(self.collider_surface_shape + ".maxValueV"))
        if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
            raise RuntimeError("ymt_skirt_01 rebuilt surface has an invalid V range.")
        hem_projection = self.row_axial_projections[-1]
        return [
            minimum + ((projection / hem_projection) * (maximum - minimum)) for projection in self.row_axial_projections
        ]

    def _create_surface_drivers_and_controls(self) -> None:
        for row in range(self.rows):
            for col in range(self.cols):
                cell = (row, col)
                npo = self._create_cell_driver(cell, self.grid_positions[cell])
                npo_matrix = datatypes.Matrix(
                    cmds.xform(self._node_name(npo), query=True, worldSpace=True, matrix=True)
                )
                ring_offset = self._create_ring_offset(cell, npo, self.ring_row_weights[row])
                ctl_length = self._cell_ctl_length(cell)
                ctl = self.addCtl(
                    ring_offset,
                    "skirt_%s_%s_ctl" % cell,
                    npo_matrix,
                    self.color_fk,
                    "cube",
                    w=self.ctl_size,
                    h=self.ctl_size * 0.1,
                    d=ctl_length,
                    po=datatypes.Vector(0.0, 0.0, ctl_length * 0.5),
                    tp=self.parentCtlTag,
                )
                attribute.setKeyableAttributes(ctl, ["tx", "ty", "tz", "rx", "ry", "rz"])
                self.npos[cell] = npo
                self.ring_offsets[cell] = ring_offset
                self.fk_ctls.append(ctl)
                self.fk_ctls_by_cell[cell] = ctl
                if self.add_joints:
                    self.jnt_pos.append([ctl, "%s_%s" % cell, "parent_relative_jnt"])

    def _cell_ctl_length(self, cell: tuple[int, int]) -> float:
        # npo local Z is tangentV, pointing toward the next row; the hem row reuses the previous span.
        row, col = cell
        if row + 1 < self.rows:
            return _distance(self.grid_positions[(row, col)], self.grid_positions[(row + 1, col)])
        return _distance(self.grid_positions[(row - 1, col)], self.grid_positions[(row, col)])

    def _create_ring_offset(
        self,
        cell: tuple[int, int],
        npo: PymelNode,
        weights: tuple[float, float],
    ) -> PymelNode:
        stem = "skirt_%s_%s" % cell
        npo_name = self._node_name(npo)
        offset_name = cmds.createNode(
            "transform",
            name=self.getName(stem + "_ringOffset"),
            parent=npo_name,
        )
        cmds.setAttr(offset_name + ".inheritsTransform", True)
        cmds.setAttr(offset_name + ".translate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(offset_name + ".rotate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(offset_name + ".scale", 1.0, 1.0, 1.0, type="double3")
        cmds.setAttr(offset_name + ".shear", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(offset_name + ".rotatePivot", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(offset_name + ".scalePivot", 0.0, 0.0, 0.0, type="double3")

        delta_plug = self._cell_ring_delta_plug(cell, weights)
        opm_multiply = cmds.createNode("multMatrix", name=self.getName(stem + "_ringOpm_mm"))
        # ADR-0002 row-vector order: npoWorld * deltaCell * npoWorldInverse.
        cmds.connectAttr(npo_name + ".worldMatrix[0]", opm_multiply + ".matrixIn[0]", force=True)
        if delta_plug is None:
            cmds.setAttr(opm_multiply + ".matrixIn[1]", *self._identity_matrix(), type="matrix")
        else:
            cmds.connectAttr(delta_plug, opm_multiply + ".matrixIn[1]", force=True)
        cmds.connectAttr(npo_name + ".worldInverseMatrix[0]", opm_multiply + ".matrixIn[2]", force=True)
        cmds.connectAttr(opm_multiply + ".matrixSum", offset_name + ".offsetParentMatrix", force=True)
        return pm.PyNode(offset_name)

    def _cell_ring_delta_plug(self, cell: tuple[int, int], weights: tuple[float, float]) -> str | None:
        knee_weight, ankle_weight = weights
        knee_delta = self.ring_delta_nodes["ringKnee"] + ".matrixSum"
        ankle_delta = None
        if self.ankle_station is not None:
            ankle_delta = self.ring_delta_nodes["ringAnkle"] + ".matrixSum"

        if weights == (0.0, 0.0):
            return None
        if weights == (1.0, 0.0):
            return knee_delta
        if weights == (0.0, 1.0):
            if ankle_delta is None:
                raise RuntimeError("ymt_skirt_01 cannot apply ankle-only ring weights without ringAnkle_ctl.")
            return ankle_delta

        stem = "skirt_%s_%s" % cell
        blend = cmds.createNode("blendMatrix", name=self.getName(stem + "_ringBlend_bm"))
        cmds.setAttr(blend + ".envelope", 1.0)
        cmds.setAttr(blend + ".inputMatrix", *self._identity_matrix(), type="matrix")
        node_knee_weight, node_ankle_weight = _blend_node_weights(knee_weight, ankle_weight)
        cmds.connectAttr(knee_delta, blend + ".target[0].targetMatrix", force=True)
        cmds.setAttr(blend + ".target[0].weight", node_knee_weight)
        if ankle_delta is not None:
            cmds.connectAttr(ankle_delta, blend + ".target[1].targetMatrix", force=True)
            cmds.setAttr(blend + ".target[1].weight", node_ankle_weight)
        return blend + ".outputMatrix"

    def _rest_cell_matrix(self, driver_values: Matrix16, locator_position: Vector3) -> Matrix16:
        # Radial rest frame: Y = outward surface normal, Z = tangentV toward the hem,
        # X = Y cross Z (circumference tangent). Signs are corrected against the cone
        # geometry because the node's surface winding is not part of the contract.
        y_axis = _normalize((driver_values[0], driver_values[1], driver_values[2]), "surface normal", 1.0e-8)
        driver_position: Vector3 = (driver_values[12], driver_values[13], driver_values[14])
        offset = _subtract(driver_position, self.reference_positions["waist"])
        radial = _subtract(offset, _multiply(self.axis, _dot(offset, self.axis)))
        if _dot(y_axis, radial) < 0.0:
            y_axis = _multiply(y_axis, -1.0)
        z_raw: Vector3 = (driver_values[8], driver_values[9], driver_values[10])
        z_axis = _subtract(z_raw, _multiply(y_axis, _dot(z_raw, y_axis)))
        z_axis = _normalize(z_axis, "surface tangentV", 1.0e-8)
        if _dot(z_axis, self.axis) < 0.0:
            z_axis = _multiply(z_axis, -1.0)
        x_axis = _cross(y_axis, z_axis)
        return _matrix_from_axes(x_axis, y_axis, z_axis, locator_position)

    def _create_cell_driver(self, cell: tuple[int, int], locator_position: Vector3) -> PymelNode:
        row, col = cell
        stem = "skirt_%s_%s" % cell
        posi = cmds.createNode("pointOnSurfaceInfo", name=self.getName(stem + "_posi"))
        cmds.connectAttr(self.collider_surface_shape + ".worldSpace[0]", posi + ".inputSurface", force=True)
        cmds.setAttr(posi + ".parameterU", self.surface_u_values[col])
        cmds.setAttr(posi + ".parameterV", self.surface_v_values[row])

        matrix_node = cmds.createNode("fourByFourMatrix", name=self.getName(stem + "_fbfm"))
        self._connect_surface_frame(posi, matrix_node)
        driver_matrix = om2.MMatrix(self._matrix_attr(matrix_node + ".output"))
        rest_values = self._rest_cell_matrix(self._matrix_attr(matrix_node + ".output"), locator_position)
        rest_matrix = om2.MMatrix(rest_values)
        # Row-vector convention: matrixSum = offset * driver * parentInverse, so offset = M0 * D0^-1,
        # where M0 carries the orthonormalized surface frame at the authored position.
        offset_matrix = rest_matrix * driver_matrix.inverse()

        npo_name = cmds.createNode("transform", name=self.getName(stem + "_npo"), parent=self._node_name(self.root))
        cmds.xform(npo_name, worldSpace=True, matrix=rest_values)
        multiply = cmds.createNode("multMatrix", name=self.getName(stem + "_mm"))
        cmds.setAttr(multiply + ".matrixIn[0]", *self._openmaya_matrix_values(offset_matrix), type="matrix")
        cmds.connectAttr(matrix_node + ".output", multiply + ".matrixIn[1]", force=True)
        cmds.connectAttr(npo_name + ".parentInverseMatrix[0]", multiply + ".matrixIn[2]", force=True)
        decompose = cmds.createNode("decomposeMatrix", name=self.getName(stem + "_dm"))
        cmds.connectAttr(multiply + ".matrixSum", decompose + ".inputMatrix", force=True)
        cmds.connectAttr(decompose + ".outputTranslate", npo_name + ".translate", force=True)
        cmds.connectAttr(decompose + ".outputRotate", npo_name + ".rotate", force=True)
        return pm.PyNode(npo_name)

    def _connect_surface_frame(self, posi: str, matrix_node: str) -> None:
        vector_rows = (
            ("normal", 0),
            ("tangentU", 1),
            ("tangentV", 2),
            ("position", 3),
        )
        for source, row in vector_rows:
            for column, axis in enumerate("XYZ"):
                source_axis = axis if source in ("normal", "position") else axis.lower()
                cmds.connectAttr(
                    "%s.%s%s" % (posi, source, source_axis),
                    "%s.in%s%s" % (matrix_node, row, column),
                    force=True,
                )

    def _matrix_attr(self, plug: str) -> Matrix16:
        values = cmds.getAttr(plug)
        if isinstance(values, (list, tuple)) and len(values) == 1 and isinstance(values[0], (list, tuple)):
            values = values[0]
        flat = tuple(float(values[index]) for index in range(16))
        if not all(math.isfinite(value) for value in flat):
            raise RuntimeError("ymt_skirt_01 matrix plug returned non-finite values: %s." % plug)
        return flat

    def _identity_matrix(self) -> Matrix16:
        return _matrix_from_axes(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
        )

    def _openmaya_matrix_values(self, matrix: om2.MMatrix) -> Matrix16:
        return tuple(float(matrix[index]) for index in range(16))

    def _node_name(self, node: PymelNode | str) -> str:
        name = getattr(node, "name", None)
        return str(name()) if callable(name) else str(node)
