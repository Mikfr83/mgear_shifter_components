"""Collider-driven skirt component."""

from __future__ import annotations

import importlib
import math
import re
from typing import TYPE_CHECKING, Tuple, cast  # noqa: UP035

import maya.api.OpenMaya as om2
from maya import cmds
from mgear.core import attribute
from mgear.shifter import component

try:
    pm = importlib.import_module("mgear.pymaya")
except ImportError:
    pm = importlib.import_module("pymel.core")
try:
    datatypes = importlib.import_module("mgear.pymaya.datatypes")
except ImportError:
    datatypes = importlib.import_module("pymel.core.datatypes")

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typing import Union

    from ymt_shifter_utility.type_protocols import MatrixLike, PymelNode

    MatrixSource = Union[MatrixLike, "Sequence[Sequence[float]]", "Sequence[float]"]


AUTHOR = "yamahigashi"
VERSION = [0, 1, 0]
TYPE = "ymt_skirt_01"
NAME = "skirt"

LEG_PROFILE_RADIUS_NAMES = tuple(
    station + "Radius" + axis for station in ("thigh", "knee", "calf", "ankle") for axis in ("X", "Z")
)
LEG_PROFILE_POSITION_NAMES = ("thighPosition", "calfPosition")


FIXED_REFERENCE_NAMES = ("waist", "hip_L", "knee_L", "heel_L", "hip_R", "knee_R", "heel_R")
GRID_NAME_RE = re.compile(r"^skirt_(\d+)_(\d+)_loc$")
# typing.Tuple, not builtin tuple: runtime aliases must import under Maya 2022 (Python 3.7).
Vector3 = Tuple[float, float, float]  # noqa: UP006
Matrix16 = Tuple[  # noqa: UP006
    float, float, float, float, float, float, float, float, float, float, float, float, float, float, float, float
]


def _validated_leg_profile_value(name: str, raw: float | int | str | None) -> float:
    requirement = "finite and greater than zero" if name in LEG_PROFILE_RADIUS_NAMES else "finite and within [0, 1]"
    try:
        value = float(raw) if raw is not None else math.nan
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError("ymt_skirt_01 %s=%r must be %s." % (name, raw, requirement)) from exc
    valid_range = value > 0.0 if name in LEG_PROFILE_RADIUS_NAMES else 0.0 <= value <= 1.0
    if not math.isfinite(value) or not valid_range:
        raise RuntimeError("ymt_skirt_01 %s=%r must be %s." % (name, raw, requirement))
    return value


def _cell_stem(cell: tuple[int, int]) -> str:
    row, col = cell
    return "skirt_%s_%s" % (col, row)


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


def _ring_stations(d_knee: float, d_heel: float, hem_projection: float) -> tuple[float, float | None]:
    knee_station = min(d_knee, hem_projection)
    ankle_station = min(d_heel, hem_projection)
    if ankle_station - knee_station < 0.05 * hem_projection:
        return ankle_station, None
    return knee_station, ankle_station


def _ring_positions_error(raw: str, token_index: int, raw_token: str, reason: str) -> RuntimeError:
    return RuntimeError(
        "ymt_skirt_01 ringPositions %r is invalid at token %s %r: %s." % (raw, token_index, raw_token, reason)
    )


def _parse_ring_position_token(raw: str, token_index: int, raw_token: str, previous: float | None) -> float:
    if not raw_token.strip():
        raise _ring_positions_error(raw, token_index, raw_token, "the token is empty")
    try:
        value = float(raw_token)
    except ValueError as exc:
        raise _ring_positions_error(raw, token_index, raw_token, "expected a number") from exc
    if not math.isfinite(value):
        raise _ring_positions_error(raw, token_index, raw_token, "the value must be finite")
    if value <= 0.0 or value > 1.0:
        raise _ring_positions_error(raw, token_index, raw_token, "values must satisfy 0 < t <= 1")
    if token_index == 1 and value < 1.0e-3:
        raise _ring_positions_error(raw, token_index, raw_token, "the leading separation must be >= 1e-3")
    if previous is not None and value <= previous:
        raise _ring_positions_error(raw, token_index, raw_token, "values must be strictly increasing")
    if previous is not None and value - previous < 1.0e-3:
        raise _ring_positions_error(raw, token_index, raw_token, "adjacent separation must be >= 1e-3")
    return value


def _parse_normalized_ring_positions(raw: str) -> tuple[list[float], list[str]]:
    raw_tokens = raw.strip().split(",")
    if len(raw_tokens) > 32:
        raise _ring_positions_error(raw, 33, raw_tokens[32], "at most 32 stations are allowed")
    positions = []
    previous = None
    for token_index, raw_token in enumerate(raw_tokens, start=1):
        value = _parse_ring_position_token(raw, token_index, raw_token, previous)
        positions.append(value)
        previous = value
    return positions, raw_tokens


def _seams_error(raw: str, token_index: int, raw_token: str, reason: str) -> RuntimeError:
    return RuntimeError("ymt_skirt_01 seams %r is invalid at token %s %r: %s." % (raw, token_index, raw_token, reason))


def _parse_seams(raw: str, rows: int, cols: int) -> tuple[list[tuple[int, int]], list[str]]:
    if not isinstance(raw, str):
        raise _seams_error(raw, 1, raw, "expected a string")
    if not raw.strip():
        return [], []
    tokens = raw.split(",")
    if len(tokens) > 32:
        raise _seams_error(raw, 33, tokens[32], "at most 32 seams are allowed")
    seams = []
    gaps: set[int] = set()
    for index, token in enumerate(tokens, start=1):
        match = re.fullmatch(r"\s*([+-]?[0-9]+)\s*:\s*([+-]?[0-9]+)\s*", token)
        if match is None:
            raise _seams_error(raw, index, token, "expected integer:integer")
        gap, row = int(match[1]), int(match[2])
        if not 0 <= gap < cols or not 0 <= row < rows:
            raise _seams_error(raw, index, token, "require 0 <= gap < %s and 0 <= row < %s" % (cols, rows))
        if gap in gaps:
            raise _seams_error(raw, index, token, "duplicate gap")
        if (gap - 1) % cols in gaps or (gap + 1) % cols in gaps:
            raise _seams_error(raw, index, token, "adjacent gaps leave a panel with only one column")
        gaps.add(gap)
        seams.append((gap, row))
    return seams, tokens


def _column_panel_assignment(col: int, material: float, ranges: dict[int, tuple[float, float]]) -> tuple[int, float]:
    matches = []
    for panel_id, (start, end) in ranges.items():
        # The uncut panel's 0/1 boundary is periodic, so columns may lie on it.
        if panel_id == 0:
            matches.append((panel_id, material))
            continue
        unwrapped = material + math.ceil(start - material)
        for boundary in (start, end):
            distance = abs(unwrapped - boundary)
            if min(distance, abs(distance - 1.0)) <= 1.0e-6:
                raise RuntimeError("ymt_skirt_01 column %s is on panel %s boundary." % (col, panel_id))
        if start < unwrapped < end:
            matches.append((panel_id, unwrapped))
    if len(matches) != 1:
        raise RuntimeError("ymt_skirt_01 column %s must belong to exactly one panel." % col)
    return matches[0]


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


def _ring_skin_weights(
    axial_projection: float,
    stations: Sequence[float],
) -> list[float]:
    if not stations:
        raise ValueError("ring skin weights require at least one station")
    weights = [0.0] * (len(stations) + 1)
    if axial_projection <= 0.0:
        weights[0] = 1.0
        return weights
    if axial_projection >= stations[-1]:
        weights[-1] = 1.0
        return weights
    lower_station = 0.0
    for upper_index, upper_station in enumerate(stations, start=1):
        if axial_projection <= upper_station:
            ratio = (axial_projection - lower_station) / (upper_station - lower_station)
            weights[upper_index - 1] = 1.0 - ratio
            weights[upper_index] = ratio
            return weights
        lower_station = upper_station
    raise RuntimeError("ring skin weight interval resolution failed")


class Component(component.Main):
    """Shifter component class."""

    def addObjects(self) -> None:
        self.WIP = self.options["mode"]
        self._ensure_ydd_colliders_plugin()
        self.rows, self.cols = self._validated_dimensions()
        self.guide_size = self._validated_guide_size()
        self.evaluation_root_initial_matrix = self._matrix_attr(self._node_name(self.root) + ".worldMatrix[0]")
        self.reference_matrices = self._validated_reference_matrices()
        self.grid_matrices = self._validated_grid_matrices()
        self._convert_guide_to_evaluation_space()
        self.reference_positions = {
            name: self._matrix_position(matrix) for name, matrix in self.reference_matrices.items()
        }
        self.grid_positions = {cell: self._matrix_position(matrix) for cell, matrix in self.grid_matrices.items()}
        self._fit_cone()
        self.ctl_size = self.guide_size * self._validated_positive_setting("ctlSize") * 0.1
        self.add_joints = self._validated_bool_setting("addJoints")
        self.column_fk = self._validated_bool_setting("columnFk")
        self.column_fk_group: str | None = None
        self.column_fk_anchors: dict[int, str] = {}
        self.column_fk_ctls: dict[int, PymelNode] = {}
        self.column_fk_frames: dict[int, Matrix16] = {}
        self.post_collision = self._validated_bool_setting("postCollision")
        self.wave = self._validated_bool_setting("wave")
        self._validate_animator_settings()
        self.leg_profile = self._validated_leg_profile()
        self._validate_seam_settings()
        nodes_before = set(cmds.ls(long=True) or [])

        self.refs_group = self._create_refs_group()
        self.skirt_collider_refs = self._create_internal_references()
        self.collider_node = self._create_collider_node()
        self._connect_collider_references()
        self._configure_collider()
        try:
            self._calibrate_material_u()
            if self.column_fk:
                self._sample_column_fk_frames()
            self._configure_seams()
            self._configure_panel_hems()
            if self.column_fk:
                self._create_column_fk_controls()
        except Exception as exc:
            created = set(cmds.ls(long=True) or []) - nodes_before
            for node in sorted(created, key=lambda name: name.count("|"), reverse=True):
                if cmds.objExists(node):
                    cmds.delete(node)
            raise RuntimeError("ymt_skirt_01 panel construction failed: %s" % exc) from exc
        surfaces = self._create_rebuilt_surface()
        self.collider_surface = {panel_id: pair[0] for panel_id, pair in surfaces.items()}
        self.collider_surface_shape = {panel_id: pair[1] for panel_id, pair in surfaces.items()}
        # Rings sample the rebuilt (pre-ring-skin) surface, so they must build after it.
        self._create_ring_controllers()
        self.surface_u_values = self._surface_u_parameters()
        self.surface_v_values = self._surface_v_parameters()
        self.npos: dict[tuple[int, int], PymelNode] = {}
        self.fk_ctls: list[PymelNode] = []
        self.fk_ctls_by_cell: dict[tuple[int, int], PymelNode] = {}
        self._create_surface_drivers_and_controls()
        self._assert_ring_control_identity()
        self.wave_deformer: dict[int, str] = {}
        self.post_collide_deformer: dict[int, str] = {}
        self.post_collide_rest: dict[int, str] = {}
        self._skin_rebuilt_surface()
        # cmds.deformer appends to the chain: wave MUST be created before the
        # corrective pass so the order is skin -> wave -> collide (ADR-0004).
        if self.wave:
            self._create_wave_deformer()
            if not self.post_collision:
                cmds.warning(
                    "ymt_skirt_01: wave is enabled without postCollision;"
                    " inward wave tucks can penetrate the legs uncorrected."
                )
        if self.post_collision:
            self._create_post_collision_deformer()
        self._assert_surface_deformer_order()
        if not self.settings.get("ui_host"):
            self.uihost = self.fk_ctls[0]
        self._objects_built = True

    def addOperators(self) -> None:
        return

    def addAttributes(self) -> None:
        # Shifter keeps stepping after a failed step; stop here with the real cause
        # instead of an AttributeError on a node addObjects never created.
        if not getattr(self, "_objects_built", False):
            raise RuntimeError("ymt_skirt_01 addObjects did not complete; fix the error reported above.")
        self.tightness_att = self.addAnimParam(
            "tightness", "Tightness (Long Only)", "double", float(self.settings["tightness"]), 0.0, 1.0
        )
        self.falloff_att = self.addAnimParam("falloff", "Falloff", "double", float(self.settings["falloff"]), -1.0, 1.0)
        self.smoothness_att = self.addAnimParam(
            "smoothness", "Smoothness", "double", float(self.settings["smoothness"]), 0.0, 1.0
        )
        self.follow_att = self.addAnimParam("follow", "Follow", "double", float(self.settings["follow"]), 0.0, 1.0)
        cmds.connectAttr(str(self.tightness_att), self.collider_node + ".tightness", force=True)
        cmds.connectAttr(str(self.falloff_att), self.collider_node + ".falloff", force=True)
        cmds.connectAttr(str(self.smoothness_att), self.collider_node + ".smoothness", force=True)
        cmds.connectAttr(str(self.follow_att), self.collider_node + ".follow", force=True)
        if self.post_collision:
            self.post_falloff_att = self.addAnimParam("postFalloff", "Post Falloff", "double", 0.8, 0.0, 1.0)
            for deformer in self.post_collide_deformer.values():
                cmds.connectAttr(str(self.post_falloff_att), deformer + ".falloff", force=True)
        if self.wave:
            # Host channels are grouped by prefix: sway* = continuous layers
            # (periodic wave + noise), send* = the one-shot wave send.
            self.wave_amplitude_att = self.addAnimParam("waveAmplitude", "Wave Amplitude", "double", 1.0, 0.0, 3.0)
            self.sway_amount_att = self.addAnimParam("swayAmount", "Sway Amount", "double", 0.0, 0.0, 2.0)
            self.sway_vertical_att = self.addAnimParam("swayVertical", "Sway Vertical", "double", 1.0, 0.0, 2.0)
            self.sway_around_att = self.addAnimParam("swayAround", "Sway Around", "double", 0.0, 0.0, 2.0)
            self.sway_directional_att = self.addAnimParam(
                "swayDirectional", "Sway Directional", "double", 1.0, 0.0, 1.0
            )
            self.sway_dir_x_att = self.addAnimParam("swayDirX", "Sway Dir X", "double", -1.0)
            self.sway_dir_z_att = self.addAnimParam("swayDirZ", "Sway Dir Z", "double", 0.0)
            self.sway_spread_att = self.addAnimParam("swaySpread", "Sway Spread", "double", 0.0, 0.0, 0.5)
            self.sway_phase_att = self.addAnimParam("swayPhase", "Sway Phase", "double", 0.0)
            self.sway_spin_att = self.addAnimParam("swaySpin", "Sway Spin", "double", 0.0)
            self.sway_noise_att = self.addAnimParam("swayNoise", "Sway Noise", "double", 0.0, 0.0, 2.0)
            self.sway_noise_phase_att = self.addAnimParam("swayNoisePhase", "Sway Noise Phase", "double", 0.0)
            self.send_amount_att = self.addAnimParam("sendAmount", "Send Amount", "double", 0.0, 0.0, 2.0)
            self.send_dir_x_att = self.addAnimParam("sendDirX", "Send Dir X", "double", -0.5)
            self.send_dir_z_att = self.addAnimParam("sendDirZ", "Send Dir Z", "double", 0.0)
            # Max 2.0: a crest fully clears the hem at impulsePosition >= 1 + impulseWidth (width max 1.0).
            self.send_pos_att = self.addAnimParam("sendPos", "Send Pos", "double", 0.0, 0.0, 2.0)
            connections = (
                (self.wave_amplitude_att, "amplitude"),
                (self.sway_amount_att, "idleAmplitude"),
                (self.sway_vertical_att, "idleAmplitudeV"),
                (self.sway_around_att, "idleAmplitudeU"),
                (self.sway_directional_att, "idleDirectionality"),
                (self.sway_dir_x_att, "idleDirectionX"),
                (self.sway_dir_z_att, "idleDirectionZ"),
                (self.sway_spread_att, "phaseSpread"),
                (self.sway_phase_att, "wavePhaseV"),
                (self.sway_spin_att, "wavePhaseU"),
                (self.sway_noise_att, "noiseAmplitude"),
                (self.sway_noise_phase_att, "noisePhase"),
                (self.send_amount_att, "impulseAmount"),
                (self.send_dir_x_att, "impulseX"),
                (self.send_dir_z_att, "impulseZ"),
                (self.send_pos_att, "impulsePosition"),
            )
            for attr, deformer_attribute in connections:
                for deformer in self.wave_deformer.values():
                    cmds.connectAttr(str(attr), deformer + "." + deformer_attribute, force=True)
            soft_ranges = (
                (self.sway_dir_x_att, -1.0, 1.0),
                (self.sway_dir_z_att, -1.0, 1.0),
                (self.sway_phase_att, -5.0, 5.0),
                (self.sway_spin_att, -5.0, 5.0),
                (self.sway_noise_phase_att, -5.0, 5.0),
                (self.send_dir_x_att, -2.0, 2.0),
                (self.send_dir_z_att, -2.0, 2.0),
            )
            for attr, soft_min, soft_max in soft_ranges:
                cmds.addAttr(
                    str(attr),
                    edit=True,
                    hasSoftMinValue=True,
                    softMinValue=soft_min,
                    hasSoftMaxValue=True,
                    softMaxValue=soft_max,
                )

    def setRelation(self) -> None:
        self.relatives["root"] = self.fk_ctls[0]
        self.controlRelatives["root"] = self.fk_ctls[0]
        self.aliasRelatives["root"] = "skirtRoot"
        for index, ctl in enumerate(self.ring_ctls):
            relative_name = "ring%s" % index
            self.relatives[relative_name] = ctl
            self.controlRelatives[relative_name] = ctl
            self.aliasRelatives[relative_name] = relative_name
        for cell, ctl in self.fk_ctls_by_cell.items():
            stem = _cell_stem(cell)
            local_name = stem + "_loc"
            self.relatives[local_name] = ctl
            self.controlRelatives[local_name] = ctl
            self.aliasRelatives[local_name] = stem[len("skirt_") :]

    def addConnection(self) -> None:
        self.connections["standard"] = self.connect_standard

    def connect_standard(self) -> None:
        self.parent.addChild(self.root)

    def get_skirt_collider_refs(self) -> dict[str, PymelNode]:
        return dict(self.skirt_collider_refs)

    def _ensure_ydd_colliders_plugin(self) -> None:
        try:
            loaded = cmds.pluginInfo("yddColliders", query=True, loaded=True)
        except RuntimeError:
            loaded = False
        if not loaded:
            try:
                cmds.loadPlugin("yddColliders")
            except RuntimeError as exc:
                maya_version = cmds.about(version=True)
                raise RuntimeError("ymt_skirt_01 requires the yddColliders plugin for Maya %s." % maya_version) from exc
        maya_version = cmds.about(version=True)
        try:
            node_types = cmds.pluginInfo("yddColliders", query=True, dependNode=True) or []
        except RuntimeError as exc:
            raise RuntimeError(
                "ymt_skirt_01 yddColliders plugin for Maya %s does not report registered dependency nodes."
                % maya_version
            ) from exc
        requirements = {
            "yddSkirtBellCollider": (
                "outputPatches",
                "seams",
                "panelHems",
                "columnOffsetMatrix",
                "columnMaterialU",
                "followRange",
                "referenceMaterialHeight",
                "outputReferenceHeight",
            ),
            "yddSkirtSurfaceFit": ("protectedVParameters",),
            "yddSkirtWaveDeformer": ("heightNormalization", "referenceHeight"),
        }
        for node_type, attributes in requirements.items():
            if node_type not in node_types:
                raise RuntimeError("ymt_skirt_01 yddColliders does not register %s." % node_type)
            missing = [name for name in attributes if not cmds.attributeQuery(name, type=node_type, exists=True)]
            if missing:
                raise RuntimeError("ymt_skirt_01 %s is missing attributes %s." % (node_type, ", ".join(missing)))

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

    @property
    def evaluation_to_world_plug(self) -> str:
        # Shifter reparents the root after addObjects; resolve its current DAG path.
        return self._node_name(self.root) + ".worldMatrix[0]"

    def _convert_guide_to_evaluation_space(self) -> None:
        """Convert serialized world-space guide data into component-local data."""
        values = self.evaluation_root_initial_matrix
        root_matrix = om2.MMatrix(values)
        axes = (
            (values[0], values[1], values[2]),
            (values[4], values[5], values[6]),
            (values[8], values[9], values[10]),
        )
        lengths = tuple(_length(axis) for axis in axes)
        minimum, maximum = min(lengths), max(lengths)
        determinant = float(root_matrix.det4x4())
        if minimum < 1.0e-8 or not math.isfinite(determinant) or determinant <= 0.0:
            raise RuntimeError("ymt_skirt_01 built component root must have a nondegenerate positive uniform scale.")
        if maximum / minimum > 1.0 + 1.0e-6 or any(
            abs(_dot(axes[first], axes[second])) > 1.0e-6 * lengths[first] * lengths[second]
            for first, second in ((0, 1), (0, 2), (1, 2))
        ):
            raise RuntimeError("ymt_skirt_01 built component root does not support nonuniform scale or shear.")
        inverse_root = root_matrix.inverse()

        def to_evaluation(matrix: Matrix16) -> Matrix16:
            return self._openmaya_matrix_values(om2.MMatrix(matrix) * inverse_root)

        self.reference_matrices = {name: to_evaluation(matrix) for name, matrix in self.reference_matrices.items()}
        self.grid_matrices = {cell: to_evaluation(matrix) for cell, matrix in self.grid_matrices.items()}
        self.guide_root_matrix = to_evaluation(self.guide_root_matrix)
        self.evaluation_root_initial_scale = sum(lengths) / 3.0
        self.guide_size /= self.evaluation_root_initial_scale
        self.evaluation_ref_matrices: dict[str, str] = {}

    def _validated_grid_matrices(self) -> dict[tuple[int, int], Matrix16]:
        expected_names = {_cell_stem((row, col)) + "_loc" for col in range(self.cols) for row in range(self.rows)}
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

        parents = getattr(self.guide, "grid_locator_parents", {})
        if parents:
            for col in range(self.cols):
                for row in range(self.rows):
                    name = _cell_stem((row, col)) + "_loc"
                    expected_parent = "root" if row == 0 else _cell_stem((row - 1, col)) + "_loc"
                    actual_parent = parents.get(name)
                    if actual_parent != expected_parent:
                        raise RuntimeError(
                            "ymt_skirt_01 grid locator %s must be parented under %s; found %s."
                            % (name, expected_parent, actual_parent)
                        )

        matrices: dict[tuple[int, int], Matrix16] = {}
        for name in sorted(expected_names, key=self._grid_name_sort_key):
            match = GRID_NAME_RE.fullmatch(name)
            if match is None or name not in self.guide.tra:
                raise RuntimeError("ymt_skirt_01 could not collect grid transform: %s." % name)
            cell = (int(match.group(2)), int(match.group(1)))
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
        return cast("Matrix16", flat)

    def _matrix_position(self, matrix: Matrix16) -> Vector3:
        return (matrix[12], matrix[13], matrix[14])

    def _fit_cone(self) -> None:
        epsilon = 0.001 * self.guide_size
        self._fit_bell_frame(epsilon)
        self._fit_grid_profile(epsilon)
        self._seat_bell_origin_on_top_row()
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
        self.hem_column_projections = [
            _dot(_subtract(self.grid_positions[(self.rows - 1, col)], waist), self.axis) for col in range(self.cols)
        ]
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

    def _seat_bell_origin_on_top_row(self) -> None:
        # The collider surface starts at the bell origin (V = 0) and cannot represent
        # rows above it. A waistband placed above the waist joint is a valid guide, so
        # seat the origin on the top row instead of mapping it outside the V range,
        # which pointOnSurfaceInfo answers with an all-zero (singular) frame.
        top_projection = self.row_axial_projections[0]
        if top_projection >= 0.0:
            return
        waist = _add(self.reference_positions["waist"], _multiply(self.axis, top_projection))
        self.reference_positions["waist"] = waist
        self.bell_matrix = _matrix_from_axes(self.bell_x_axis, self.axis, self.bell_z_axis, waist)
        self.row_axial_projections = [projection - top_projection for projection in self.row_axial_projections]
        self.hem_column_projections = [projection - top_projection for projection in self.hem_column_projections]
        cmds.warning(
            "ymt_skirt_01: the top row lies %.3f units above the waist reference along the"
            " waist-to-heel axis; the bell origin is seated on the top row." % -top_projection
        )

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

        hem_projection = max(self.hem_column_projections)
        self.skirt_type = 1 if hem_projection > self.d_knee else 0
        if self.skirt_type == 0:
            span_start, span_end = self.d_hip, self.d_knee
        else:
            span_start, span_end = self.d_knee, self.d_heel
        raw_height = (hem_projection - span_start) / (span_end - span_start)
        if not math.isfinite(raw_height):
            raise RuntimeError("ymt_skirt_01 fitted height is not finite: %s." % raw_height)
        # The node clamps height to [0, 1] (0.01 floor here so the surface keeps a
        # usable length). Mirror the clamp and derive the length of the surface the
        # node will actually emit; every row and ring maps against that length, so
        # a hem above the hips or below the heels still builds.
        self.height = min(1.0, max(0.01, raw_height))
        self.surface_length = span_start + ((span_end - span_start) * self.height)
        if abs(self.height - raw_height) > 1.0e-9:
            cmds.warning(
                "ymt_skirt_01: hem row projection %.3f is outside the collider %s range [%.3f, %.3f];"
                " height clamped to %.2f and rows past the surface end share its hem frame."
                % (
                    hem_projection,
                    "hip-to-knee" if self.skirt_type == 0 else "knee-to-heel",
                    span_start,
                    span_end,
                    self.height,
                )
            )
        return hip_distance

    def _surface_fraction(self, projection: float) -> float:
        # Normalized station along the collider surface: 0 = bell origin, 1 = the
        # surface hem. Values past either end clamp so they stay on the surface.
        return min(1.0, max(0.0, projection / self.surface_length))

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
                        "ymt_skirt_01 row %s has coincident locators %s_loc and %s_loc."
                        % (row, _cell_stem((row, first)), _cell_stem((row, second)))
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

    def _validated_leg_profile(self) -> dict[str, float]:
        values = {}
        for name in LEG_PROFILE_RADIUS_NAMES + LEG_PROFILE_POSITION_NAMES:
            if name not in self.settings:
                raise RuntimeError("ymt_skirt_01 %s=<missing> is required." % name)
            values[name] = _validated_leg_profile_value(name, self.settings[name])
        return values

    def _validate_animator_settings(self) -> None:
        self._validated_range_setting("tightness", 0.0, 1.0)
        self._validated_range_setting("falloff", -1.0, 1.0)
        self._validated_range_setting("smoothness", 0.0, 1.0)
        self._validated_range_setting("follow", 0.0, 1.0)

    def _validated_ring_stations(self) -> list[float]:
        if "ringPositions" not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the ringPositions setting.")
        raw_value = self.settings["ringPositions"]
        if not isinstance(raw_value, str):
            raise RuntimeError(
                "ymt_skirt_01 ringPositions must be a string; raw=%r, token 1=%r." % (raw_value, raw_value)
            )
        raw = raw_value
        normalized = raw.strip()
        hem_projection = max(self.hem_column_projections)
        if normalized == "auto":
            knee_station, ankle_station = _ring_stations(self.d_knee, self.d_heel, hem_projection)
            self.ring_position_tokens = ["auto"]
            if ankle_station is not None:
                self.ring_position_tokens.append("auto")
                return [knee_station, ankle_station]
            return [knee_station]
        normalized_positions, self.ring_position_tokens = _parse_normalized_ring_positions(raw)
        return [value * hem_projection for value in normalized_positions]

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
        self._lock_identity_group(group_name)
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
        absolute_matrices: dict[str, Matrix16] = {}
        parents = {
            "waist": None,
            "hip_L": "waist",
            "knee_L": "hip_L",
            "heel_L": "knee_L",
            "hip_R": "waist",
            "knee_R": "hip_R",
            "heel_R": "knee_R",
        }
        for name in FIXED_REFERENCE_NAMES:
            parent_name = parents[name]
            parent = self.refs_group if parent_name is None else refs[parent_name]
            node = cmds.createNode(
                "transform",
                name=self.getName(rig_names[name]),
                parent=self._node_name(parent),
            )
            parent_matrix = self._identity_matrix() if parent_name is None else absolute_matrices[parent_name]
            local_matrix = om2.MMatrix(matrices[name]) * om2.MMatrix(parent_matrix).inverse()
            cmds.xform(node, objectSpace=True, matrix=self._openmaya_matrix_values(local_matrix))
            for channel in ("tx", "ty", "tz", "rx", "ry", "rz"):
                cmds.setAttr(node + "." + channel, lock=False, keyable=False, channelBox=False)
            refs[name] = pm.PyNode(node)
            absolute_matrices[name] = matrices[name]

        aggregate_plugs: dict[str, str] = {}
        for name in FIXED_REFERENCE_NAMES:
            matrix_node = cmds.createNode("multMatrix", name=self.getName(rig_names[name] + "_eval_mm"))
            cmds.connectAttr(self._node_name(refs[name]) + ".matrix", matrix_node + ".matrixIn[0]", force=True)
            cmds.connectAttr(
                self._node_name(refs[name]) + ".offsetParentMatrix",
                matrix_node + ".matrixIn[1]",
                force=True,
            )
            parent_name = parents[name]
            if parent_name is not None:
                cmds.connectAttr(aggregate_plugs[parent_name], matrix_node + ".matrixIn[2]", force=True)
            aggregate_plugs[name] = matrix_node + ".matrixSum"
        self.evaluation_ref_matrices = aggregate_plugs
        return refs

    def _create_ring_controllers(self) -> None:
        self.ring_stations = self._validated_ring_stations()
        group_name = cmds.createNode(
            "transform",
            name=self.getName("ringCtls"),
            parent=self._node_name(self.root),
        )
        self._lock_identity_group(group_name)
        cmds.setAttr(group_name + ".visibility", True)
        self.ring_ctls_group = pm.PyNode(group_name)
        self.ring_ctls: list[PymelNode] = []
        self.ring_constraint_nodes: list[tuple[PymelNode, str]] = []
        self.ring_anchor_names: list[str] = []

        for index, station in enumerate(self.ring_stations):
            self._create_ring_controller("ring%s" % index, station)
        self._create_ring_influence_joints()

    def _create_ring_controller(
        self,
        stem: str,
        station: float,
    ) -> PymelNode:
        position = _add(self.reference_positions["waist"], _multiply(self.axis, station))
        frame_values = _matrix_from_axes(self.bell_x_axis, self.axis, self.bell_z_axis, position)
        anchor_name = cmds.createNode(
            "transform",
            name=self.getName(stem + "_anchor"),
            parent=self._node_name(self.ring_ctls_group),
        )
        cmds.xform(anchor_name, objectSpace=True, matrix=frame_values)
        self._connect_anchor_surface_follow(stem, anchor_name, station)

        # The control frame must be the anchor's evaluated frame so its local matrix is
        # exactly identity even where the fitted cone center deviates from the axis.
        frame = datatypes.Matrix(self._matrix_attr(anchor_name + ".worldMatrix[0]"))
        radius = _station_radius(station, self.row_axial_projections, self.row_mean_radii) * 1.1
        control_parent = pm.PyNode(anchor_name)
        ctl = self.addCtl(
            control_parent,
            stem + "_ctl",
            frame,
            self.color_ik,
            "circle",
            w=radius * 2.0,
            tp=self.parentCtlTag,
            wip=self.WIP,
        )
        attribute.setKeyableAttributes(ctl, ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"])
        ctl_name = self._node_name(ctl)
        cmds.setAttr(
            ctl_name + ".offsetParentMatrix",
            *self._identity_matrix(),
            type="matrix",
        )

        self.ring_ctls.append(ctl)
        self.ring_constraint_nodes.append((ctl, anchor_name))
        self.ring_anchor_names.append(anchor_name)
        return ctl

    def _connect_anchor_surface_follow(self, stem: str, anchor_name: str, station: float) -> None:
        # Rebuild output is in evaluation space, before ring skin. Sampling the final
        # shape would cycle: ring edit -> skin -> anchor -> bindPreMatrix.
        v_value = self._surface_fraction(station)
        u_values = self._ring_u_parameters(stem, v_value)
        average = cmds.createNode("plusMinusAverage", name=self.getName(stem + "_center_avg"))
        cmds.setAttr(average + ".operation", 3)
        sample_positions = []
        for index, (panel_id, u_value) in enumerate(u_values):
            posi = cmds.createNode("pointOnSurfaceInfo", name=self.getName("%s_center%s_posi" % (stem, index)))
            cmds.connectAttr(
                self.surface_fit_node[panel_id] + ".outputSurface",
                posi + ".inputSurface",
                force=True,
            )
            cmds.setAttr(posi + ".parameterU", u_value)
            cmds.setAttr(posi + ".parameterV", v_value)
            cmds.connectAttr(posi + ".position", "%s.input3D[%s]" % (average, index), force=True)
            sample_positions.append(posi + ".position")

        # Level frame from the two sampled diameters: Y = normalize(d2 x d1) is the
        # band plane normal, X = normalize(d1) (orthogonal to Y by construction),
        # Z = X x Y. The cross order is fixed at build so rest Y points hem-ward.
        diameter_front = self._create_vector_difference(stem + "_d1", sample_positions[0], sample_positions[4])
        diameter_side = self._create_vector_difference(stem + "_d2", sample_positions[2], sample_positions[6])
        rest_front = self._plug_vector(diameter_front)
        rest_side = self._plug_vector(diameter_side)
        rest_normal = _cross(rest_side, rest_front)
        if _length(rest_normal) < 1.0e-8:
            raise RuntimeError("ymt_skirt_01 %s level frame is degenerate at rest." % stem)
        if _dot(rest_normal, self.axis) >= 0.0:
            cross_inputs = (diameter_side, diameter_front)
        else:
            cross_inputs = (diameter_front, diameter_side)
        y_axis = cmds.createNode("vectorProduct", name=self.getName(stem + "_yAxis_vp"))
        cmds.setAttr(y_axis + ".operation", 2)
        cmds.setAttr(y_axis + ".normalizeOutput", True)
        cmds.connectAttr(cross_inputs[0], y_axis + ".input1", force=True)
        cmds.connectAttr(cross_inputs[1], y_axis + ".input2", force=True)
        x_axis = cmds.createNode("vectorProduct", name=self.getName(stem + "_xAxis_vp"))
        cmds.setAttr(x_axis + ".operation", 0)
        cmds.setAttr(x_axis + ".normalizeOutput", True)
        cmds.connectAttr(diameter_front, x_axis + ".input1", force=True)
        z_axis = cmds.createNode("vectorProduct", name=self.getName(stem + "_zAxis_vp"))
        cmds.setAttr(z_axis + ".operation", 2)
        cmds.setAttr(z_axis + ".normalizeOutput", True)
        cmds.connectAttr(x_axis + ".output", z_axis + ".input1", force=True)
        cmds.connectAttr(y_axis + ".output", z_axis + ".input2", force=True)

        frame = cmds.createNode("fourByFourMatrix", name=self.getName(stem + "_level_fbfm"))
        for row, source in ((0, x_axis + ".output"), (1, y_axis + ".output"), (2, z_axis + ".output")):
            for column, channel in enumerate("XYZ"):
                cmds.connectAttr("%s%s" % (source, channel), "%s.in%s%s" % (frame, row, column), force=True)
        for column, channel in enumerate("xyz"):
            cmds.connectAttr("%s.output3D%s" % (average, channel), "%s.in3%s" % (frame, column), force=True)

        decompose = cmds.createNode("decomposeMatrix", name=self.getName(stem + "_center_dm"))
        cmds.connectAttr(frame + ".output", decompose + ".inputMatrix", force=True)
        cmds.connectAttr(decompose + ".outputTranslate", anchor_name + ".translate", force=True)
        cmds.connectAttr(decompose + ".outputRotate", anchor_name + ".rotate", force=True)
        self._connect_anchor_scale(stem, anchor_name, sample_positions)

    def _ring_u_parameters(self, stem: str, v_value: float) -> list[tuple[int, float]]:
        sampler = cmds.createNode("pointOnSurfaceInfo", name=self.getName(stem + "_calibration_posi"))
        sampled: list[tuple[int, float, float]] = []
        try:
            for panel_id in self.panel_ids:
                cmds.connectAttr(
                    self.surface_fit_node[panel_id] + ".outputSurface", sampler + ".inputSurface", force=True
                )
                for index in range(256):
                    u_value = index / 256.0
                    angle = self._surface_angle(self._surface_point(sampler, u_value, v_value))
                    sampled.append((panel_id, u_value, angle))
        finally:
            if cmds.objExists(sampler):
                cmds.delete(sampler)
        selected = []
        for target_index in range(8):
            target = target_index * math.pi / 4.0
            panel_id, u_value, _angle = min(sampled, key=lambda sample: abs(self._wrap_angle(sample[2] - target)))
            selected.append((panel_id, u_value))
        if len(set(selected)) != 8:
            raise RuntimeError(
                "ymt_skirt_01 %s ring calibration did not select eight distinct panel/U values: %s."
                % (stem, ", ".join("panel %s u %.6f" % pair for pair in selected))
            )
        return selected

    def _connect_anchor_scale(self, stem: str, anchor_name: str, sample_positions: Sequence[str]) -> None:
        front_distance = cmds.createNode("distanceBetween", name=self.getName(stem + "_lenFront_db"))
        cmds.connectAttr(sample_positions[0], front_distance + ".point1", force=True)
        cmds.connectAttr(sample_positions[4], front_distance + ".point2", force=True)
        side_distance = cmds.createNode("distanceBetween", name=self.getName(stem + "_lenSide_db"))
        cmds.connectAttr(sample_positions[2], side_distance + ".point1", force=True)
        cmds.connectAttr(sample_positions[6], side_distance + ".point2", force=True)

        rest_front = float(cmds.getAttr(front_distance + ".distance"))
        rest_side = float(cmds.getAttr(side_distance + ".distance"))
        threshold = 1.0e-5 * self.guide_size
        if not math.isfinite(rest_front) or rest_front < threshold:
            raise RuntimeError("ymt_skirt_01 %s front ring diameter is shorter than 1e-5 times guide size." % stem)
        if not math.isfinite(rest_side) or rest_side < threshold:
            raise RuntimeError("ymt_skirt_01 %s side ring diameter is shorter than 1e-5 times guide size." % stem)

        ratio = cmds.createNode("multiplyDivide", name=self.getName(stem + "_ratio_md"))
        cmds.setAttr(ratio + ".operation", 2)
        cmds.connectAttr(front_distance + ".distance", ratio + ".input1X", force=True)
        cmds.connectAttr(side_distance + ".distance", ratio + ".input1Z", force=True)
        cmds.setAttr(ratio + ".input2X", rest_front)
        cmds.setAttr(ratio + ".input2Z", rest_side)
        scale_max = cmds.createNode("condition", name=self.getName(stem + "_scaleMax_cnd"))
        cmds.setAttr(scale_max + ".operation", 2)
        cmds.connectAttr(ratio + ".outputX", scale_max + ".firstTerm", force=True)
        cmds.connectAttr(ratio + ".outputZ", scale_max + ".secondTerm", force=True)
        cmds.connectAttr(ratio + ".outputX", scale_max + ".colorIfTrueR", force=True)
        cmds.connectAttr(ratio + ".outputZ", scale_max + ".colorIfFalseR", force=True)
        for axis in "XYZ":
            cmds.connectAttr(scale_max + ".outColorR", anchor_name + ".scale" + axis, force=True)

    def _create_vector_difference(self, name: str, first_plug: str, second_plug: str) -> str:
        node = cmds.createNode("plusMinusAverage", name=self.getName(name + "_pma"))
        cmds.setAttr(node + ".operation", 2)
        cmds.connectAttr(first_plug, node + ".input3D[0]", force=True)
        cmds.connectAttr(second_plug, node + ".input3D[1]", force=True)
        return node + ".output3D"

    def _plug_vector(self, plug: str) -> Vector3:
        values = cmds.getAttr(plug)
        if not isinstance(values, (list, tuple)) or len(values) != 1 or len(values[0]) != 3:
            raise RuntimeError("ymt_skirt_01 could not read vector plug %s." % plug)
        vector = (float(values[0][0]), float(values[0][1]), float(values[0][2]))
        if not all(math.isfinite(value) for value in vector):
            raise RuntimeError("ymt_skirt_01 vector plug %s is non-finite." % plug)
        return vector

    def _set_identity_transform(self, node: str) -> None:
        cmds.setAttr(node + ".translate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".rotate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".scale", 1.0, 1.0, 1.0, type="double3")
        cmds.setAttr(node + ".shear", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".rotatePivot", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".rotatePivotTranslate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".scalePivot", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".scalePivotTranslate", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(node + ".rotateAxis", 0.0, 0.0, 0.0, type="double3")

    def _lock_identity_group(self, node: str) -> None:
        # These fixed parents define the evaluation space; their display remains editable.
        for attribute_name in ("matrix", "offsetParentMatrix"):
            values = self._matrix_attr(node + "." + attribute_name)
            if any(abs(value - expected) > 1.0e-12 for value, expected in zip(values, self._identity_matrix())):
                raise RuntimeError("ymt_skirt_01 requires an identity internal group: %s." % node)
        for attribute_name in (
            "translate",
            "rotate",
            "scale",
            "shear",
            "offsetParentMatrix",
            "inheritsTransform",
            "rotatePivot",
            "rotatePivotTranslate",
            "scalePivot",
            "scalePivotTranslate",
            "rotateAxis",
        ):
            cmds.setAttr(node + "." + attribute_name, lock=True, keyable=False, channelBox=False)

    def _create_ring_influence_joints(self) -> None:
        waist_anchor = cmds.createNode(
            "transform",
            name=self.getName("ringWaist_anchor"),
            parent=self._node_name(self.ring_ctls_group),
        )
        cmds.xform(waist_anchor, objectSpace=True, matrix=self.bell_matrix)
        waist_frame = cmds.createNode("decomposeMatrix", name=self.getName("ringWaist_eval_dm"))
        cmds.connectAttr(self.evaluation_ref_matrices["waist"], waist_frame + ".inputMatrix", force=True)
        cmds.connectAttr(waist_frame + ".outputTranslate", waist_anchor + ".translate", force=True)
        cmds.connectAttr(waist_frame + ".outputRotate", waist_anchor + ".rotate", force=True)
        waist_joint = cmds.createNode("joint", name=self.getName("ringWaist_jnt"), parent=waist_anchor)
        self._set_identity_transform(waist_joint)
        cmds.setAttr(waist_joint + ".jointOrient", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(waist_joint + ".segmentScaleCompensate", False)
        cmds.setAttr(waist_joint + ".drawStyle", 2)
        cmds.setAttr(waist_joint + ".visibility", False)
        self.ring_skin_joints = [waist_joint]
        self.ring_skin_anchors = [waist_anchor]
        for index, (ctl, anchor_name) in enumerate(zip(self.ring_ctls, self.ring_anchor_names)):
            stem = "ring%s" % index
            joint = cmds.createNode("joint", name=self.getName(stem + "_jnt"), parent=self._node_name(ctl))
            self._set_identity_transform(joint)
            cmds.setAttr(joint + ".jointOrient", 0.0, 0.0, 0.0, type="double3")
            cmds.setAttr(joint + ".segmentScaleCompensate", False)
            cmds.setAttr(joint + ".drawStyle", 2)
            cmds.setAttr(joint + ".visibility", False)
            self.ring_skin_joints.append(joint)
            self.ring_skin_anchors.append(anchor_name)

        # Each hidden influence owns its evaluation-space matrix. Keeping the joint
        # as the skin input source preserves Maya's influence and weight APIs.
        self.ring_skin_bind_pre_plugs: list[str] = []
        for index, (joint, anchor) in enumerate(zip(self.ring_skin_joints, self.ring_skin_anchors)):
            cmds.setAttr(joint + ".inheritsTransform", False)
            anchor_matrix = cmds.createNode("multMatrix", name=self.getName("ringSkin%s_anchor_mm" % index))
            cmds.connectAttr(anchor + ".matrix", anchor_matrix + ".matrixIn[0]", force=True)
            cmds.connectAttr(anchor + ".offsetParentMatrix", anchor_matrix + ".matrixIn[1]", force=True)
            influence_matrix = anchor_matrix + ".matrixSum"
            if index > 0:
                control = self._node_name(self.ring_ctls[index - 1])
                matrix_node = cmds.createNode("multMatrix", name=self.getName("ringSkin%s_mm" % index))
                cmds.connectAttr(control + ".matrix", matrix_node + ".matrixIn[0]", force=True)
                cmds.connectAttr(control + ".offsetParentMatrix", matrix_node + ".matrixIn[1]", force=True)
                cmds.connectAttr(influence_matrix, matrix_node + ".matrixIn[2]", force=True)
                influence_matrix = matrix_node + ".matrixSum"
            cmds.connectAttr(influence_matrix, joint + ".offsetParentMatrix", force=True)
            inverse_anchor = cmds.createNode("inverseMatrix", name=self.getName("ringSkin%s_bindPre_inv" % index))
            cmds.connectAttr(anchor_matrix + ".matrixSum", inverse_anchor + ".inputMatrix", force=True)
            self.ring_skin_bind_pre_plugs.append(inverse_anchor + ".outputMatrix")

    def _assert_ring_control_identity(self) -> None:
        identity = self._identity_matrix()
        for ctl, anchor_name in self.ring_constraint_nodes:
            cmds.getAttr(anchor_name + ".matrix")
            ctl_name = self._node_name(ctl)
            local_matrix = self._matrix_attr(ctl_name + ".matrix")
            if any(abs(value - expected) > 1.0e-6 for value, expected in zip(local_matrix, identity)):
                raise RuntimeError("ymt_skirt_01 ring control local matrix is not identity: %s." % ctl_name)
            offset_parent_matrix = self._matrix_attr(ctl_name + ".offsetParentMatrix")
            if any(abs(value - expected) > 1.0e-6 for value, expected in zip(offset_parent_matrix, identity)):
                raise RuntimeError("ymt_skirt_01 ring control offsetParentMatrix is not identity: %s." % ctl_name)
            for attribute_name in (
                "rotatePivot",
                "rotatePivotTranslate",
                "scalePivot",
                "scalePivotTranslate",
                "shear",
                "rotateAxis",
            ):
                values = cmds.getAttr(ctl_name + "." + attribute_name)
                vector = values[0] if isinstance(values, (list, tuple)) and len(values) == 1 else values
                if len(vector) != 3 or any(abs(float(value)) > 1.0e-6 for value in vector):
                    raise RuntimeError("ymt_skirt_01 ring control %s is not identity: %s." % (attribute_name, ctl_name))

    def _create_collider_node(self) -> str:
        node = cmds.createNode("yddSkirtBellCollider", name=self.getName("yddSkirtBellCollider"))
        missing_attributes = [
            name
            for name in ("smoothness", "follow", *LEG_PROFILE_RADIUS_NAMES, *LEG_PROFILE_POSITION_NAMES)
            if not cmds.attributeQuery(name, node=node, exists=True)
        ]
        if missing_attributes:
            maya_version = cmds.about(version=True)
            # The locator is still an unparented world-level transform here; later
            # validators fail inside the component hierarchy, this one must clean up.
            stale_parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            cmds.delete(stale_parents[0] if stale_parents else node)
            raise RuntimeError(
                "ymt_skirt_01 yddColliders plugin for Maya %s is missing yddSkirtBellCollider attributes %s;"
                " rebuild the yddColliders plugin." % (maya_version, ", ".join(missing_attributes))
            )
        parents = cmds.listRelatives(node, parent=True, type="transform", fullPath=True) or []
        if len(parents) != 1:
            raise RuntimeError("ymt_skirt_01 could not resolve the yddSkirtBellCollider transform.")
        collider_transform = cmds.rename(parents[0], self.getName("yddSkirtBellColliderTransform"))
        cmds.parent(collider_transform, self._node_name(self.root))
        # The plugin output is component-local; this hidden locator follows the root once
        # so any diagnostic drawing remains at the component's displayed world position.
        cmds.setAttr(collider_transform + ".inheritsTransform", True)
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
                self.evaluation_ref_matrices[name],
                self.collider_node + "." + collider_attribute,
                force=True,
            )

    def _configure_collider(self) -> None:
        cmds.setAttr(self.collider_node + ".skirtType", self.skirt_type)
        cmds.setAttr(self.collider_node + ".height", self.height)
        cmds.setAttr(self.collider_node + ".leftRingAxis", 0)
        cmds.setAttr(self.collider_node + ".rightRingAxis", 0)
        cmds.setAttr(self.collider_node + ".bellAxis", 1)
        cmds.setAttr(self.collider_node + ".tightness", float(self.settings["tightness"]))
        cmds.setAttr(self.collider_node + ".falloff", float(self.settings["falloff"]))
        cmds.setAttr(self.collider_node + ".smoothness", float(self.settings["smoothness"]))
        cmds.setAttr(self.collider_node + ".follow", float(self.settings["follow"]))
        cmds.setAttr(self.collider_node + ".followRange", self.follow_range)
        cmds.setAttr(self.collider_node + ".referenceMaterialHeight", self.surface_length)
        for name, value in self.leg_profile.items():
            cmds.setAttr(self.collider_node + "." + name, value)
        self._configure_evaluation_scale()
        self._rewrite_bell_scale_ramp()

    def _configure_evaluation_scale(self) -> None:
        cmds.setAttr(self.collider_node + ".bellScale0", self.hem_radius)
        cmds.setAttr(self.collider_node + ".bellScale2", self.hem_radius)
        cmds.setAttr(self.collider_node + ".ringScale0", self.ring_radius_x)
        cmds.setAttr(self.collider_node + ".ringScale2", self.ring_radius_z)
        cmds.setAttr(self.collider_node + ".bellScale1", 1.0)
        cmds.setAttr(self.collider_node + ".ringScale1", self.ring_height_scale)

    def _rewrite_bell_scale_ramp(self) -> None:
        ramp = self.collider_node + ".bellScaleRamp"
        indices = cmds.getAttr(ramp, multiIndices=True) or []
        for index in sorted(indices, reverse=True):
            cmds.removeMultiInstance("%s[%s]" % (ramp, index), b=True)
        # Rows past the surface end collapse onto one ramp key; the later row wins so
        # the surface hem carries the true hem radius.
        keys: list[tuple[float, float]] = []
        for projection, radius in zip(self.row_axial_projections, self.row_mean_radii):
            position = self._surface_fraction(projection)
            value = radius / self.hem_radius
            if keys and abs(keys[-1][0] - position) < 1.0e-6:
                keys[-1] = (position, value)
            else:
                keys.append((position, value))
        for index, (position, value) in enumerate(keys):
            element = "%s[%s]" % (ramp, index)
            cmds.setAttr(element + ".bellScaleRamp_Position", position)
            cmds.setAttr(element + ".bellScaleRamp_FloatValue", value)
            cmds.setAttr(element + ".bellScaleRamp_Interp", 1)

    def _validate_seam_settings(self) -> None:
        if "seams" not in self.settings:
            raise RuntimeError("ymt_skirt_01 requires the seams setting.")
        self.seams, self.seam_tokens = _parse_seams(self.settings["seams"], self.rows, self.cols)
        self.follow_range = self._validated_range_setting("followRange", 0.0, math.inf)
        self.seam_heights = []
        for index, (_gap, row) in enumerate(self.seams):
            height = 0.0 if row == 0 else max(self._surface_fraction(self.row_axial_projections[row - 1]), 1.0e-6)
            reason = ""
            if height >= 1.0 - 1.0e-9:
                reason = "the start row is at the surface end"
            elif row > 0 and self._surface_fraction(self.row_axial_projections[row]) <= height + 1.0e-9:
                reason = "the start row has the same height as the preceding row"
            if reason:
                raise _seams_error(self.settings["seams"], index + 1, self.seam_tokens[index], reason)
            self.seam_heights.append(height)
        self.rebuild_spans_v = self._integer_setting("rebuildSpansV")
        if not 1 <= self.rebuild_spans_v <= 256:
            raise RuntimeError("ymt_skirt_01 rebuildSpansV must be an integer within 1..256.")

    def _force_patch_evaluation(self, panel_ids: Sequence[int]) -> None:
        messages: list[str] = []

        def capture(message: str, message_type: int, _client_data: None) -> None:
            if message_type == om2.MCommandMessage.kError:
                messages.append(message)

        callback = om2.MCommandMessage.addCommandOutputCallback(capture)
        failure = None
        try:
            cmds.dgdirty(self.collider_node)
            for panel_id in panel_ids:
                plug_name = "%s.outputPatches[%s].surface" % (self.collider_node, panel_id)
                selection = om2.MSelectionList()
                selection.add(plug_name)
                data = selection.getPlug(0).asMObject()
                if data.isNull():
                    raise RuntimeError("ymt_skirt_01 %s returned null surface data." % plug_name)
        except Exception as exc:
            failure = exc
        finally:
            om2.MMessage.removeCallback(callback)
        node_name = self.collider_node.split("|")[-1]
        errors = [message for message in messages if message.split("|")[-1].startswith(node_name + ": ")]
        if errors:
            raise RuntimeError("ymt_skirt_01 " + "\n".join(errors)) from failure
        if failure is not None:
            raise RuntimeError("ymt_skirt_01 patch evaluation failed: %s" % failure) from failure

    def _calibrate_material_u(self) -> None:
        self._force_patch_evaluation([0])
        surface = cmds.createNode("transform", name=self.getName("materialCalibration"))
        sampler = ""
        try:
            shape = cmds.createNode("nurbsSurface", name=self.getName("materialCalibrationShape"), parent=surface)
            cmds.connectAttr(self.collider_node + ".outputPatches[0].surface", shape + ".create", force=True)
            sampler = cmds.createNode("pointOnSurfaceInfo", name=self.getName("materialCalibration_posi"))
            cmds.connectAttr(shape + ".local", sampler + ".inputSurface", force=True)
            count = max(256, self.cols * 64)
            angles = [self._surface_angle(self._surface_point(sampler, k / float(count), 0.5)) for k in range(count)]
            column_angles = [self._column_mean_angle(col) for col in range(self.cols)]
            self.material_u = {
                col: self._calibrated_material_parameter(sampler, angles, angle)
                for col, angle in enumerate(column_angles)
            }
            self.seam_material_u = []
            for gap, _row in self.seams:
                first, second = column_angles[gap], column_angles[(gap + 1) % self.cols]
                sine, cosine = math.sin(first) + math.sin(second), math.cos(first) + math.cos(second)
                if abs(sine) < 1.0e-9 and abs(cosine) < 1.0e-9:
                    raise RuntimeError("ymt_skirt_01 gap %s has a degenerate angle." % gap)
                value = self._calibrated_material_parameter(sampler, angles, math.atan2(sine, cosine))
                self._validate_seam_material_parameter(gap, value)
                self.seam_material_u.append(value)
        finally:
            if sampler and cmds.objExists(sampler):
                cmds.delete(sampler)
                if cmds.objExists(surface):
                    cmds.delete(surface)

    def _sample_column_fk_frames(self) -> None:
        surface_transform = cmds.createNode("transform", name=self.getName("columnFkCalibration"))
        sampler = ""
        node_state = int(cmds.getAttr(self.collider_node + ".nodeState"))
        try:
            shape = cmds.createNode(
                "nurbsSurface", name=self.getName("columnFkCalibrationShape"), parent=surface_transform
            )
            cmds.connectAttr(self.collider_node + ".outputPatches[0].surface", shape + ".create", force=True)
            sampler = cmds.createNode("pointOnSurfaceInfo", name=self.getName("columnFkCalibration_posi"))
            cmds.connectAttr(shape + ".local", sampler + ".inputSurface", force=True)
            cmds.setAttr(sampler + ".turnOnPercentage", False)
            self.column_fk_frames: dict[int, Matrix16] = {}
            cmds.setAttr(self.collider_node + ".nodeState", 1)
            self._force_patch_evaluation([0])
            axis = self.axis
            bell_position = self._matrix_position(self.bell_matrix)
            threshold = 1.0e-4 * self.guide_size
            for col in range(self.cols):
                origin = self._surface_point(sampler, self.material_u[col], 0.0)
                tangent = self._plug_vector(sampler + ".tangentU")
                tangent_projected = _subtract(tangent, _multiply(axis, _dot(tangent, axis)))
                radial = _subtract(_subtract(origin, bell_position), _multiply(axis, _dot(_subtract(origin, bell_position), axis)))
                tangent_length = _length(tangent_projected)
                if tangent_length < threshold:
                    raise RuntimeError("ymt_skirt_01 column %s has a degenerate tangentU." % col)
                tangent_axis = _normalize(tangent_projected, "column %s tangentU" % col, threshold)
                radial_projected = _subtract(radial, _multiply(tangent_axis, _dot(radial, tangent_axis)))
                if _length(radial_projected) < threshold:
                    raise RuntimeError("ymt_skirt_01 column %s has a degenerate radial frame." % col)
                radial_axis = _normalize(radial_projected, "column %s radial frame" % col, threshold)
                frame = _matrix_from_axes(tangent_axis, radial_axis, axis, origin)
                self.column_fk_frames[col] = self._finite_matrix(frame, "column %s rest frame" % col)
        finally:
            try:
                cmds.setAttr(self.collider_node + ".nodeState", node_state)
                self._force_patch_evaluation([0])
            finally:
                try:
                    if sampler and cmds.objExists(sampler):
                        cmds.delete(sampler)
                finally:
                    if cmds.objExists(surface_transform):
                        cmds.delete(surface_transform)

    def _create_column_fk_controls(self) -> None:
        ordered_materials = sorted((self.material_u[col], col) for col in range(self.cols))
        for index, (material, col) in enumerate(ordered_materials):
            next_material, next_col = ordered_materials[(index + 1) % len(ordered_materials)]
            spacing = next_material - material if index + 1 < len(ordered_materials) else next_material + 1.0 - material
            if spacing <= 1.0e-9:
                raise RuntimeError(
                    "ymt_skirt_01 columns %s and %s have material U spacing %s; expected more than 1e-9."
                    % (col, next_col, spacing)
                )
        self.column_fk_group = cmds.createNode(
            "transform", name=self.getName("skirtColFk_grp"), parent=self._node_name(self.root)
        )
        decompose = cmds.createNode("decomposeMatrix", name=self.getName("skirtColFk_dcm"))
        cmds.connectAttr(
            self.evaluation_ref_matrices["waist"], decompose + ".inputMatrix", force=True
        )
        cmds.connectAttr(decompose + ".outputTranslate", self.column_fk_group + ".translate", force=True)
        cmds.connectAttr(decompose + ".outputRotate", self.column_fk_group + ".rotate", force=True)
        for channel in ("sx", "sy", "sz", "shearXY", "shearXZ", "shearYZ", "visibility"):
            cmds.setAttr(self.column_fk_group + "." + channel, lock=True, keyable=False, channelBox=False)

        waist_matrix = om2.MMatrix(self._matrix_attr(self.evaluation_ref_matrices["waist"]))
        self.column_fk_anchors: dict[int, str] = {}
        self.column_fk_ctls: dict[int, PymelNode] = {}
        radius = _station_radius(0.0, self.row_axial_projections, self.row_mean_radii) * 1.1
        for col in range(self.cols):
            anchor = cmds.createNode(
                "transform",
                name=self.getName("skirtCol%s_fk_anchor" % col),
                parent=self.column_fk_group,
            )
            anchor_matrix = om2.MMatrix(self.column_fk_frames[col]) * waist_matrix.inverse()
            cmds.xform(anchor, objectSpace=True, matrix=self._openmaya_matrix_values(anchor_matrix))
            cmds.setAttr(anchor + ".offsetParentMatrix", *self._identity_matrix(), type="matrix")
            frame = datatypes.Matrix(self._matrix_attr(anchor + ".worldMatrix[0]"))
            ctl = self.addCtl(
                pm.PyNode(anchor),
                "skirtCol%s_fk" % col,
                frame,
                self.color_fk,
                "circle",
                w=radius * 2.0,
                tp=self.parentCtlTag,
                wip=self.WIP,
            )
            ctl_name = self._node_name(ctl)
            self._set_identity_transform(ctl_name)
            cmds.setAttr(ctl_name + ".offsetParentMatrix", *self._identity_matrix(), type="matrix")
            attribute.setKeyableAttributes(ctl, ["tx", "ty", "tz", "rx", "ry", "rz"])
            for channel in ("sx", "sy", "sz"):
                cmds.setAttr(ctl_name + "." + channel, lock=False, keyable=False, channelBox=False)
                cmds.setAttr(ctl_name + "." + channel, 1.0)
                cmds.setAttr(ctl_name + "." + channel, lock=True, keyable=False, channelBox=False)
            identity = self._identity_matrix()
            self._require_cell_matrix(ctl_name + ".matrix", identity, 0.0)
            self._require_cell_matrix(ctl_name + ".offsetParentMatrix", identity, 0.0)
            self.column_fk_anchors[col] = anchor
            self.column_fk_ctls[col] = ctl

        materials = [self.material_u[col] for col in range(self.cols)]
        cmds.setAttr(self.collider_node + ".columnMaterialU", materials, type="doubleArray")
        for col in range(self.cols):
            cmds.connectAttr(
                self._node_name(self.column_fk_ctls[col]) + ".matrix",
                "%s.columnOffsetMatrix[%s]" % (self.collider_node, col),
                force=True,
            )
        self._force_patch_evaluation(self.panel_ids)

    def _calibrated_material_parameter(self, sampler: str, angles: Sequence[float], target: float) -> float:
        count = len(angles)
        nearest = min(range(count), key=lambda k: abs(self._wrap_angle(angles[k] - target)))
        lower, upper = (nearest - 1) / float(count), (nearest + 1) / float(count)

        def difference(u_value: float) -> float:
            return self._wrap_angle(self._surface_angle(self._surface_point(sampler, u_value % 1.0, 0.5)) - target)

        lower_value, upper_value = difference(lower), difference(upper)
        if lower_value * upper_value > 0.0:
            return nearest / float(count)
        for _iteration in range(40):
            middle = (lower + upper) * 0.5
            middle_value = difference(middle)
            if lower_value * middle_value <= 0.0:
                upper = middle
            else:
                lower, lower_value = middle, middle_value
        return ((lower + upper) * 0.5) % 1.0

    def _validate_seam_material_parameter(self, gap: int, value: float) -> None:
        for previous in self.seam_material_u:
            delta = abs(value - previous)
            if min(delta, 1.0 - delta) <= 1.0e-9:
                raise RuntimeError("ymt_skirt_01 gap %s duplicates another seam material U." % gap)
        for col, column_u in self.material_u.items():
            delta = abs(value - column_u)
            if min(delta, 1.0 - delta) <= 1.0e-6:
                raise RuntimeError("ymt_skirt_01 seam at gap %s overlaps column %s." % (gap, col))

    def _read_panels(self) -> dict[int, tuple[float, float, list[float]]]:
        self._force_patch_evaluation(self.panel_ids)
        indices = cmds.getAttr(self.collider_node + ".outputPatches", multiIndices=True) or []
        if set(indices) != set(self.panel_ids):
            raise RuntimeError("ymt_skirt_01 outputPatches indices %s differ from %s." % (indices, self.panel_ids))
        panels = {}
        shared_breaks = None
        for panel_id in self.panel_ids:
            plug = "%s.outputPatches[%s]" % (self.collider_node, panel_id)
            start = float(cmds.getAttr(plug + ".materialUStart"))
            end = float(cmds.getAttr(plug + ".materialUEnd"))
            breaks = list(cmds.getAttr(plug + ".vBreaks") or [])
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                raise RuntimeError("ymt_skirt_01 panel %s has an invalid material range." % panel_id)
            if any(not math.isfinite(value) for value in breaks):
                raise RuntimeError("ymt_skirt_01 panel %s has invalid vBreaks." % panel_id)
            if shared_breaks is not None and breaks != shared_breaks:
                raise RuntimeError("ymt_skirt_01 panels have different vBreaks.")
            shared_breaks = breaks
            panels[panel_id] = (start, end, breaks)
        return panels

    def _configure_seams(self) -> None:
        for index, (material, height) in enumerate(zip(self.seam_material_u, self.seam_heights)):
            plug = "%s.seams[%s]" % (self.collider_node, index)
            cmds.setAttr(plug + ".enabled", True)
            cmds.setAttr(plug + ".materialU", material)
            cmds.setAttr(plug + ".startHeight", height)
        self.panel_ids = list(range(1, len(self.seams) + 1)) if self.seams else [0]
        self.panels = self._read_panels()
        if self._validate_seam_breaks(rewrite=True):
            self.panels = self._read_panels()
            self._validate_seam_breaks(rewrite=False)
        breaks = self.panels[self.panel_ids[0]][2]
        self.beta = max(breaks) if breaks else 0.0
        required = len(breaks) + 1
        if self.rebuild_spans_v < required:
            raise RuntimeError("ymt_skirt_01 rebuildSpansV=%s requires at least %s." % (self.rebuild_spans_v, required))
        self.panel_ranges = {panel_id: (panel[0], panel[1]) for panel_id, panel in self.panels.items()}

    def _validate_seam_breaks(self, rewrite: bool) -> bool:
        breaks = self.panels[self.panel_ids[0]][2]
        changed = False
        for index, height in enumerate(self.seam_heights):
            if height == 0.0:
                continue
            matching = [value for value in breaks if abs(value - height) <= 1.0e-9]
            if not matching:
                raise RuntimeError("ymt_skirt_01 seam %s startHeight %s is missing from vBreaks." % (index, height))
            value = min(matching, key=lambda candidate: abs(candidate - height))
            if value < height:
                if not rewrite:
                    raise RuntimeError(
                        "ymt_skirt_01 seam %s vBreak remains below startHeight after correction." % index
                    )
                corrected = value + 1.5e-9
                cmds.setAttr("%s.seams[%s].startHeight" % (self.collider_node, index), corrected)
                self.seam_heights[index] = corrected
                changed = True
        return changed

    def _assign_panel_columns(self) -> None:
        self.panel_columns: dict[int, list[int]] = {panel_id: [] for panel_id in self.panel_ids}
        self.column_material: dict[int, float] = {}
        for col, material in self.material_u.items():
            panel_id, unwrapped = _column_panel_assignment(col, material, self.panel_ranges)
            self.panel_columns[panel_id].append(col)
            self.column_material[col] = unwrapped
        self.column_panel = {}
        self.k_col = {}
        for panel_id, columns in self.panel_columns.items():
            if not columns:
                raise RuntimeError("ymt_skirt_01 panel %s has no columns." % panel_id)
            columns.sort(key=lambda col: self.column_material[col])
            for index, col in enumerate(columns):
                self.column_panel[col] = panel_id
                self.k_col[col] = index
        if set(self.column_material) != set(range(self.cols)):
            raise RuntimeError("ymt_skirt_01 panel assignment does not cover every column.")

    def _panel_hem_samples(self, panel_id: int) -> tuple[list[float], list[float]]:
        start, end = self.panel_ranges[panel_id]
        samples = []
        for col in self.panel_columns[panel_id]:
            projection = self.hem_column_projections[col]
            name = _cell_stem((self.rows - 1, col)) + "_loc"
            if projection <= 0.0:
                raise RuntimeError("ymt_skirt_01 %s hem projection must be greater than zero." % name)
            height = min(1.0, projection / self.surface_length)
            if height <= self.beta + 1.0e-9:
                raise RuntimeError("ymt_skirt_01 %s hem is above the protected row; beta=%s." % (name, self.beta))
            samples.append(((self.column_material[col] - start) / (end - start), height))
        first, last = samples[0][1], samples[-1][1]
        if panel_id == 0:
            ratio = (1.0 - samples[-1][0]) / (samples[0][0] + 1.0 - samples[-1][0])
            first = last = (1.0 - ratio) * last + ratio * first
        interior = []
        for u_value, height in samples:
            if abs(u_value) <= 1.0e-12:
                first = height
            elif abs(u_value - 1.0) <= 1.0e-12:
                last = height
            else:
                interior.append((u_value, height))
        samples = [(0.0, first), *interior, (1.0, last)]
        return [sample[0] for sample in samples], [sample[1] for sample in samples]

    def _configure_panel_hems(self) -> None:
        self._assign_panel_columns()
        samples = {panel_id: self._panel_hem_samples(panel_id) for panel_id in self.panel_ids}
        write_hems = any(height != 1.0 for _u_values, heights in samples.values() for height in heights)
        if write_hems:
            for panel_id, (u_values, heights) in samples.items():
                plug = "%s.panelHems[%s]" % (self.collider_node, panel_id)
                cmds.setAttr(plug + ".uSamples", list(u_values), type="doubleArray")
                cmds.setAttr(plug + ".heightSamples", list(heights), type="doubleArray")
        self._force_patch_evaluation(self.panel_ids)
        if write_hems:
            for panel_id, (_u_values, heights) in samples.items():
                plug = "%s.outputPatches[%s].hemHeightSamples" % (self.collider_node, panel_id)
                if list(cmds.getAttr(plug) or []) != heights:
                    raise RuntimeError("ymt_skirt_01 panel %s hemHeightSamples differ from panelHems." % panel_id)

    def _create_rebuilt_surface(self) -> dict[int, tuple[PymelNode, str]]:
        surfaces = {}
        self.surface_fit_node: dict[int, str] = {}
        for panel_id in self.panel_ids:
            stem = "colliderSurface_p%s" % panel_id
            surface = cmds.createNode("transform", name=self.getName(stem), parent=self._node_name(self.root))
            cmds.setAttr(surface + ".inheritsTransform", True)
            self._set_identity_transform(surface)
            cmds.setAttr(surface + ".visibility", False)
            shape = cmds.createNode("nurbsSurface", name=self.getName(stem + "Shape"), parent=surface)
            fit = cmds.createNode("yddSkirtSurfaceFit", name=self.getName(stem + "_fit"))
            cmds.setAttr(fit + ".spansV", self.rebuild_spans_v)
            patch = "%s.outputPatches[%s]" % (self.collider_node, panel_id)
            cmds.connectAttr(patch + ".surface", fit + ".inputSurface", force=True)
            cmds.connectAttr(patch + ".vBreaks", fit + ".protectedVParameters", force=True)
            cmds.connectAttr(fit + ".outputSurface", shape + ".create", force=True)
            self.surface_fit_node[panel_id] = fit
            surfaces[panel_id] = (pm.PyNode(surface), shape)
        return surfaces

    def _surface_u_parameters(self) -> dict[int, float]:
        parameters = {}
        for panel_id in self.panel_ids:
            shape = self.collider_surface_shape[panel_id]
            minimum = float(cmds.getAttr(shape + ".minValueU"))
            maximum = float(cmds.getAttr(shape + ".maxValueU"))
            if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
                raise RuntimeError("ymt_skirt_01 panel %s has an invalid U range." % panel_id)
            sample_count = max(256, self.cols * 64)
            sampler = cmds.createNode("pointOnSurfaceInfo", name=self.getName("surfaceCalibration_p%s_posi" % panel_id))
            try:
                cmds.connectAttr(shape + ".local", sampler + ".inputSurface", force=True)
                sampled = []
                for index in range(sample_count + 1):
                    u_value = minimum + index / float(sample_count) * (maximum - minimum)
                    sampled.append((u_value, self._surface_angle(self._surface_point(sampler, u_value, 0.5))))
                for col in self.panel_columns[panel_id]:
                    target = self._column_mean_angle(col)
                    parameters[col] = min(sampled, key=lambda sample: abs(self._wrap_angle(sample[1] - target)))[0]
            finally:
                if cmds.objExists(sampler):
                    cmds.delete(sampler)
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

    def _surface_point(self, sampler: str, u_value: float, v_value: float) -> Vector3:
        cmds.setAttr(sampler + ".parameterU", u_value)
        cmds.setAttr(sampler + ".parameterV", v_value)
        values = cmds.getAttr(sampler + ".position")
        if not isinstance(values, (list, tuple)) or len(values) != 1 or len(values[0]) != 3:
            raise RuntimeError("ymt_skirt_01 could not sample the rebuilt collider surface.")
        point = (float(values[0][0]), float(values[0][1]), float(values[0][2]))
        if not all(math.isfinite(value) for value in point):
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface returned a non-finite sample.")
        return point

    def _surface_v_parameters(self) -> list[float]:
        shape = self.collider_surface_shape[self.panel_ids[0]]
        minimum = float(cmds.getAttr(shape + ".minValueV"))
        maximum = float(cmds.getAttr(shape + ".maxValueV"))
        if not math.isfinite(minimum) or not math.isfinite(maximum) or maximum <= minimum:
            raise RuntimeError("ymt_skirt_01 rebuilt surface has an invalid V range.")
        values = [
            minimum + (self._surface_fraction(projection) * (maximum - minimum))
            for projection in self.row_axial_projections
        ]
        tolerance = 1.0e-9 * max(1.0, abs(maximum - minimum))
        for row, value in enumerate(values):
            if value < minimum - tolerance or value > maximum + tolerance:
                raise RuntimeError(
                    "ymt_skirt_01 row %s maps to V=%s outside the rebuilt surface range [%s, %s]."
                    % (row, value, minimum, maximum)
                )
        return values

    def _ring_weights_for_cv(self, cv: str, influence_count: int) -> list[float]:
        values = cmds.pointPosition(cv, local=True)
        position = (float(values[0]), float(values[1]), float(values[2]))
        if not all(math.isfinite(value) for value in position):
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface has a non-finite CV position.")
        axial_projection = _dot(_subtract(position, self.reference_positions["waist"]), self.axis)
        if not math.isfinite(axial_projection):
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface has a non-finite CV projection.")
        weights = _ring_skin_weights(axial_projection, self.ring_stations)
        if not all(math.isfinite(weight) for weight in weights):
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface produced non-finite ring weights.")
        if len(weights) != influence_count:
            raise RuntimeError("ymt_skirt_01 ring weight count does not match skin influences.")
        if abs(sum(weights) - 1.0) > 1.0e-6:
            raise RuntimeError("ymt_skirt_01 rebuilt collider surface ring weights do not sum to one.")
        return weights

    def _validate_live_ring_weights(self, maximum_ring_weights: Sequence[float]) -> None:
        for ring_index, maximum_weight in enumerate(maximum_ring_weights):
            if maximum_weight <= 1.0e-6:
                raise RuntimeError(
                    "ymt_skirt_01 ring %s is dead for ringPositions token %r at rebuildSpansV=%s;"
                    " raise rebuildSpansV or widen/move stations so a CV row falls inside"
                    " (t_{i-1}, t_{i+1})." % (ring_index, self.ring_position_tokens[ring_index], self.rebuild_spans_v)
                )

    def _skin_rebuilt_surface(self) -> None:
        self.ring_skin_cluster: dict[int, str] = {}
        influences = list(self.ring_skin_joints)
        maximum_ring_weights = [0.0] * len(self.ring_stations)
        for panel_id in self.panel_ids:
            cvs = cmds.ls(self.collider_surface_shape[panel_id] + ".cv[*][*]", flatten=True) or []
            if not cvs:
                raise RuntimeError("ymt_skirt_01 rebuilt collider surface has no CVs.")
            weighted_cvs = []
            for cv in cvs:
                weights = self._ring_weights_for_cv(cv, len(influences))
                for ring_index, weight in enumerate(weights[1:]):
                    maximum_ring_weights[ring_index] = max(maximum_ring_weights[ring_index], weight)
                weighted_cvs.append((cv, weights))
            skin_cluster = cmds.skinCluster(
                *influences,
                self.collider_surface_shape[panel_id],
                toSelectedBones=True,
                normalizeWeights=1,
                skinMethod=0,
                name=self.getName("ringSkin_p%s_skc" % panel_id),
            )[0]
            # Retain Maya's DG output cache when only downstream Wave inputs change.
            # Upstream geometry, weights and influence edits still invalidate the skin.
            cmds.setAttr(skin_cluster + ".caching", True)
            for cv, weights in weighted_cvs:
                cmds.skinPercent(
                    skin_cluster,
                    cv,
                    # The cmds stub types the multi-use transformValue flag as a single pair.
                    transformValue=list(zip(influences, weights)),  # ty: ignore[invalid-argument-type]
                )
            for joint, bind_pre in zip(influences, self.ring_skin_bind_pre_plugs):
                plugs = cmds.listConnections(joint + ".worldMatrix[0]", type="skinCluster", plugs=True) or []
                matrix_plugs = [plug for plug in plugs if plug.startswith(skin_cluster + ".matrix[")]
                if len(matrix_plugs) != 1:
                    raise RuntimeError("ymt_skirt_01 could not resolve the skin matrix index for %s." % joint)
                index = matrix_plugs[0].split("[")[1].split("]")[0]
                cmds.connectAttr(joint + ".offsetParentMatrix", matrix_plugs[0], force=True)
                cmds.connectAttr(bind_pre, "%s.bindPreMatrix[%s]" % (skin_cluster, index), force=True)
            cmds.setAttr(skin_cluster + ".geomMatrix", *self._identity_matrix(), type="matrix")
            self.ring_skin_cluster[panel_id] = skin_cluster
        self._validate_live_ring_weights(maximum_ring_weights)

    def _create_post_collision_deformer(self) -> None:
        maya_version = cmds.about(version=True)
        node_types = cmds.pluginInfo("yddColliders", query=True, dependNode=True) or []
        if "yddSkirtCollideDeformer" not in node_types:
            raise RuntimeError(
                "ymt_skirt_01 postCollision requires a yddColliders plugin registering yddSkirtCollideDeformer"
                " for Maya %s; rebuild the plugin or disable the postCollision guide setting." % maya_version
            )
        for panel_id in self.panel_ids:
            # The post-collide deformer decides each point's contact side from the rest
            # shape, so a static copy of the surface at build pose is kept as its input.
            rest_copy = cmds.duplicate(
                self._node_name(self.collider_surface[panel_id]),
                name=self.getName("postCollide_p%s_rest" % panel_id),
                returnRootsOnly=True,
            )[0]
            cmds.parent(rest_copy, self._node_name(self.root))
            rest_shapes = cmds.listRelatives(rest_copy, shapes=True, noIntermediate=True, fullPath=True) or []
            if not rest_shapes:
                raise RuntimeError("ymt_skirt_01 postCollide_p%s_rest has no surface shape." % panel_id)
            rest_shape = rest_shapes[0]
            cmds.setAttr(rest_shape + ".intermediateObject", True)
            cmds.setAttr(rest_copy + ".visibility", False)
            self.post_collide_rest[panel_id] = rest_copy
            result = cmds.deformer(
                self.collider_surface_shape[panel_id],
                type="yddSkirtCollideDeformer",
                name=self.getName("postCollide_p%s_def" % panel_id),
            )
            if not result:
                raise RuntimeError("ymt_skirt_01 could not create the yddSkirtCollideDeformer.")
            deformer = result[0]
            rest_attributes = {
                "waist": "restBellMatrix",
                "hip_L": "restLeftHipMatrix",
                "knee_L": "restLeftKneeMatrix",
                "heel_L": "restLeftHeelMatrix",
                "hip_R": "restRightHipMatrix",
                "knee_R": "restRightKneeMatrix",
                "heel_R": "restRightHeelMatrix",
            }
            missing_rest = [
                name
                for name in ["restGeometry", *rest_attributes.values()]
                if not cmds.attributeQuery(name, node=deformer, exists=True)
            ]
            if missing_rest:
                raise RuntimeError(
                    "ymt_skirt_01 yddColliders plugin for Maya %s is missing yddSkirtCollideDeformer attributes %s;"
                    " rebuild the yddColliders plugin." % (maya_version, ", ".join(missing_rest))
                )
            cmds.connectAttr(rest_shape + ".local", deformer + ".restGeometry", force=True)
            for name, deformer_attribute in rest_attributes.items():
                values = cmds.getAttr(self.evaluation_ref_matrices[name])
                cmds.setAttr(deformer + "." + deformer_attribute, *values, type="matrix")
            attributes = {
                "waist": "bellMatrix",
                "hip_L": "leftHipMatrix",
                "knee_L": "leftKneeMatrix",
                "heel_L": "leftHeelMatrix",
                "hip_R": "rightHipMatrix",
                "knee_R": "rightKneeMatrix",
                "heel_R": "rightHeelMatrix",
            }
            for name, deformer_attribute in attributes.items():
                cmds.connectAttr(
                    self.evaluation_ref_matrices[name],
                    deformer + "." + deformer_attribute,
                    force=True,
                )
            cmds.setAttr(deformer + ".skirtType", self.skirt_type)
            cmds.setAttr(deformer + ".leftRingAxis", 0)
            cmds.setAttr(deformer + ".rightRingAxis", 0)
            cmds.setAttr(deformer + ".ringScale0", self.ring_radius_x)
            cmds.setAttr(deformer + ".ringScale1", self.ring_height_scale)
            cmds.setAttr(deformer + ".ringScale2", self.ring_radius_z)
            missing_attributes = [
                name for name in self.leg_profile if not cmds.attributeQuery(name, node=deformer, exists=True)
            ]
            if missing_attributes:
                raise RuntimeError(
                    "ymt_skirt_01 yddColliders plugin for Maya %s is missing yddSkirtCollideDeformer attributes %s;"
                    " rebuild the yddColliders plugin." % (maya_version, ", ".join(missing_attributes))
                )
            for name, value in self.leg_profile.items():
                cmds.setAttr(deformer + "." + name, value)
            self.post_collide_deformer[panel_id] = deformer

    def _create_wave_deformer(self) -> None:
        maya_version = cmds.about(version=True)
        node_types = cmds.pluginInfo("yddColliders", query=True, dependNode=True) or []
        if "yddSkirtWaveDeformer" not in node_types:
            raise RuntimeError(
                "ymt_skirt_01 wave requires a yddColliders plugin registering yddSkirtWaveDeformer"
                " for Maya %s; rebuild the plugin or disable the wave guide setting." % maya_version
            )
        for panel_id in self.panel_ids:
            result = cmds.deformer(
                self.collider_surface_shape[panel_id],
                type="yddSkirtWaveDeformer",
                name=self.getName("wave_p%s_def" % panel_id),
            )
            if not result:
                raise RuntimeError("ymt_skirt_01 could not create the yddSkirtWaveDeformer.")
            deformer = result[0]
            required_attributes = (
                "idleAmplitudeV",
                "idleAmplitudeU",
                "idleDirectionality",
                "idleDirectionX",
                "idleDirectionZ",
                "idleDirectionSpace",
                "phaseSpread",
                "impulseAmount",
                "evaluationToWorldRotation",
            )
            missing = [
                name for name in required_attributes if not cmds.attributeQuery(name, node=deformer, exists=True)
            ]
            if missing:
                raise RuntimeError(
                    "ymt_skirt_01 wave requires yddSkirtWaveDeformer attributes %s for Maya %s; rebuild the yddColliders plugin."
                    % (", ".join(missing), maya_version)
                )
            cmds.connectAttr(
                self.evaluation_ref_matrices["waist"],
                deformer + ".bellMatrix",
                force=True,
            )
            rotation_pick = cmds.createNode("pickMatrix", name=self.getName("wave_p%s_evalRotation_pick" % panel_id))
            cmds.connectAttr(self.evaluation_to_world_plug, rotation_pick + ".inputMatrix", force=True)
            cmds.setAttr(rotation_pick + ".useTranslate", False)
            cmds.setAttr(rotation_pick + ".useScale", False)
            cmds.setAttr(rotation_pick + ".useShear", False)
            cmds.connectAttr(rotation_pick + ".outputMatrix", deformer + ".evaluationToWorldRotation", force=True)
            cmds.setAttr(deformer + ".heightNormalization", 1)
            cmds.connectAttr(self.collider_node + ".outputReferenceHeight", deformer + ".referenceHeight", force=True)
            self.wave_deformer[panel_id] = deformer

    def _assert_surface_deformer_order(self) -> None:
        for panel_id in self.panel_ids:
            # listHistory returns the deformation chain downstream-first.
            history = cmds.listHistory(self.collider_surface_shape[panel_id], pruneDagObjects=True) or []
            expected = [self.ring_skin_cluster[panel_id]]
            if self.wave:
                expected.insert(0, self.wave_deformer[panel_id])
            if self.post_collision:
                expected.insert(0, self.post_collide_deformer[panel_id])
            indices = []
            for node in expected:
                if node not in history:
                    raise RuntimeError("ymt_skirt_01: %s is missing from the surface deformation history." % node)
                indices.append(history.index(node))
            if indices != sorted(indices):
                actual = [node for node in history if node in expected]
                raise RuntimeError(
                    "ymt_skirt_01: surface deformer order must be ringSkin -> wave -> postCollide;"
                    " listHistory (downstream first) returned %s." % " <- ".join(actual)
                )

    def _create_surface_drivers_and_controls(self) -> None:
        self._validate_cell_frame_geometry(self.grid_positions, "rest")
        self.cell_winding_sign = self._cell_winding_sign()
        self.cell_position_matrices: dict[tuple[int, int], str] = {}
        self.cell_position_nodes: dict[tuple[int, int], str] = {}
        self.cell_aim_nodes: dict[tuple[int, int], str] = {}
        self.cell_parents: dict[tuple[int, int], PymelNode] = {}
        self.cell_rest_matrices: dict[tuple[int, int], Matrix16] = {}
        self.cell_rest_distances: dict[tuple[int, int], float] = {}
        self._create_cell_pins()
        group_name = cmds.createNode(
            "transform",
            name=self.getName("skirtCtls_grp"),
            parent=self._node_name(self.root),
        )
        self._lock_identity_group(group_name)
        self.skirt_ctls_group = pm.PyNode(group_name)
        self.skirt_col_groups: list[PymelNode] = []
        for col in range(self.cols):
            col_group_name = cmds.createNode(
                "transform",
                name=self.getName("skirtCol%s_grp" % col),
                parent=self._node_name(self.skirt_ctls_group),
            )
            self._lock_identity_group(col_group_name)
            col_group = pm.PyNode(col_group_name)
            self.skirt_col_groups.append(col_group)
            for row in range(self.rows):
                cell = (row, col)
                coordinate = "%s.coordinate[%s]" % (
                    self.cell_pin_node[self.column_panel[col]],
                    self.k_col[col] * self.rows + row,
                )
                cmds.setAttr(coordinate + ".coordinateU", self.surface_u_values[col])
                cmds.setAttr(coordinate + ".coordinateV", self.surface_v_values[row])
                self._create_cell_driver(cell, col_group)
        distant_cells = [
            "%s=%g" % (_cell_stem(cell), distance)
            for cell, distance in self.cell_rest_distances.items()
            if distance > 0.1 * self.guide_size
        ]
        if distant_cells:
            cmds.warning(
                "ymt_skirt_01: locator-to-uvPin distances exceed 0.1 * guide_size; "
                "uvPin rotation contributes to cell positions in proportion to these distances: "
                + ", ".join(distant_cells)
            )
        positions = {
            cell: self._plug_vector(node + ".outputTranslate") for cell, node in self.cell_position_nodes.items()
        }
        self._validate_sampled_cell_positions(positions)
        for cell in positions:
            self._create_cell_aim(cell)
        evaluation_to_world = om2.MMatrix(self._matrix_attr(self.evaluation_to_world_plug))
        for cell in positions:
            npo = self._create_cell_npo(cell, evaluation_to_world)
            npo_matrix = datatypes.Matrix(cmds.xform(self._node_name(npo), query=True, worldSpace=True, matrix=True))
            ctl_length = self._cell_ctl_length(cell)
            ctl = self.addCtl(
                npo,
                _cell_stem(cell) + "_ctl",
                npo_matrix,
                self.color_fk,
                "cube",
                w=self.ctl_size,
                h=self.ctl_size * 0.1,
                d=ctl_length,
                po=datatypes.Vector(0.0, 0.0, ctl_length * 0.5),
                tp=self.parentCtlTag,
                wip=self.WIP,
            )
            ctl_name = self._node_name(ctl)
            cmds.setAttr(ctl_name + ".offsetParentMatrix", *self._identity_matrix(), type="matrix")
            self._require_cell_matrix(ctl_name + ".matrix", self._identity_matrix(), 1.0e-6)
            self._require_cell_matrix(ctl_name + ".offsetParentMatrix", self._identity_matrix(), 1.0e-6)
            attribute.setKeyableAttributes(ctl, ["tx", "ty", "tz", "rx", "ry", "rz"])
            self.npos[cell] = npo
            self.fk_ctls.append(ctl)
            self.fk_ctls_by_cell[cell] = ctl
        if self.add_joints:
            for col in range(self.cols):
                for row in range(self.rows):
                    cell = (row, col)
                    ctl = self.fk_ctls_by_cell[cell]
                    stem = _cell_stem(cell)
                    joint_name = stem[len("skirt_") :]
                    if row == 0:
                        self.jnt_pos.append([ctl, joint_name, "parent_relative_jnt"])
                    else:
                        self.jnt_pos.append([ctl, joint_name])
                    self.jointRelatives[stem + "_loc"] = col * self.rows + row
            self.jointRelatives["root"] = 0

    def _create_cell_pins(self) -> None:
        self.cell_pin_node: dict[int, str] = {}
        for panel_id in self.panel_ids:
            pin = cmds.createNode("uvPin", name=self.getName("skirtCells_p%s_uvPin" % panel_id))
            cmds.connectAttr(self.collider_surface_shape[panel_id] + ".local", pin + ".deformedGeometry", force=True)
            cmds.setAttr(pin + ".relativeSpaceMode", 1)
            cmds.setAttr(pin + ".normalizedIsoParms", False)
            cmds.setAttr(pin + ".normalAxis", 1)
            cmds.setAttr(pin + ".tangentAxis", 0)
            self.cell_pin_node[panel_id] = pin

    def _validate_sampled_cell_positions(self, positions: dict[tuple[int, int], Vector3]) -> None:
        try:
            self._validate_cell_frame_geometry(positions, "sampled")
        except RuntimeError:
            cmds.delete(
                [
                    *self.cell_pin_node.values(),
                    *self.cell_position_matrices.values(),
                    *self.cell_position_nodes.values(),
                ]
            )
            raise

    def _cell_ctl_length(self, cell: tuple[int, int]) -> float:
        # Local Z follows the next-row chord; the hem row reuses the previous span.
        row, col = cell
        if row + 1 < self.rows:
            return _distance(self.grid_positions[(row, col)], self.grid_positions[(row + 1, col)])
        return _distance(self.grid_positions[(row - 1, col)], self.grid_positions[(row, col)])

    def _cell_chord(self, positions: dict[tuple[int, int], Vector3], cell: tuple[int, int]) -> Vector3:
        row, col = cell
        if row + 1 < self.rows:
            return _subtract(positions[(row + 1, col)], positions[cell])
        return _subtract(positions[cell], positions[(row - 1, col)])

    def _cell_neighbours(self, row: int, col: int) -> tuple[int | None, int | None]:
        next_col: int | None = (col + 1) % self.cols
        prev_col: int | None = (col - 1) % self.cols
        for gap, start_row in self.seams:
            if row >= start_row:
                if gap == col:
                    next_col = None
                if gap == (col - 1) % self.cols:
                    prev_col = None
        if next_col is None and prev_col is None:
            raise RuntimeError("ymt_skirt_01 cell %s has no circumferential neighbours." % _cell_stem((row, col)))
        return next_col, prev_col

    def _cell_tangent(self, positions: dict[tuple[int, int], Vector3], cell: tuple[int, int]) -> Vector3:
        row, col = cell
        next_col, prev_col = self._cell_neighbours(row, col)
        return _subtract(
            positions[(row, next_col if next_col is not None else col)],
            positions[(row, prev_col if prev_col is not None else col)],
        )

    def _validate_cell_frame_geometry(self, positions: dict[tuple[int, int], Vector3], label: str) -> None:
        eps_len = 1.0e-4 * self.guide_size
        eps_dir = 1.0e-3
        for col in range(self.cols):
            for row in range(self.rows - 1):
                cell = (row, col)
                next_cell = (row + 1, col)
                if _distance(positions[cell], positions[next_cell]) < eps_len:
                    raise RuntimeError(
                        "ymt_skirt_01 %s chord between %s and %s is shorter than %g."
                        % (label, _cell_stem(cell), _cell_stem(next_cell), eps_len)
                    )
        for col in range(self.cols):
            for row in range(self.rows):
                cell = (row, col)
                stem = _cell_stem(cell)
                z_axis = _normalize(self._cell_chord(positions, cell), label + " chord " + stem, eps_len)
                tangent = _normalize(self._cell_tangent(positions, cell), label + " tangent " + stem, eps_len)
                projected = _subtract(tangent, _multiply(z_axis, _dot(tangent, z_axis)))
                if _length(projected) < eps_dir:
                    raise RuntimeError(
                        "ymt_skirt_01 %s cell %s has a projected tangent direction shorter than %g."
                        % (label, stem, eps_dir)
                    )

    def _cell_winding_sign(self) -> int:
        eps_len = 1.0e-4 * self.guide_size
        reference_sign = 0
        for col in range(self.cols):
            for row in range(self.rows):
                cell = (row, col)
                stem = _cell_stem(cell)
                offset = _subtract(self.grid_positions[cell], self.reference_positions["waist"])
                radial = _subtract(offset, _multiply(self.axis, _dot(offset, self.axis)))
                radial_length = _length(radial)
                if radial_length < eps_len:
                    raise RuntimeError("ymt_skirt_01 cell %s has a radial length below %g." % (stem, eps_len))
                z_axis = _normalize(self._cell_chord(self.grid_positions, cell), stem + " chord", eps_len)
                x_axis = self._projected_tangent(self.grid_positions, cell, z_axis, 1)
                q = _dot(_cross(z_axis, x_axis), radial)
                if abs(q) <= 1.0e-6 * radial_length:
                    raise RuntimeError("ymt_skirt_01 cell %s has indeterminate winding." % stem)
                sign = 1 if q > 0.0 else -1
                if cell == (0, 0):
                    reference_sign = sign
                elif sign != reference_sign:
                    raise RuntimeError(
                        "ymt_skirt_01 winding mismatch: %s sign %+d, %s sign %+d."
                        % (_cell_stem((0, 0)), reference_sign, stem, sign)
                    )
        return reference_sign

    def _rest_chain_cell_matrix(self, cell: tuple[int, int]) -> Matrix16:
        eps_len = 1.0e-4 * self.guide_size
        stem = _cell_stem(cell)
        z_axis = _normalize(self._cell_chord(self.grid_positions, cell), stem + " chord", eps_len)
        x_axis = self._projected_tangent(self.grid_positions, cell, z_axis, self.cell_winding_sign)
        return _matrix_from_axes(x_axis, _cross(z_axis, x_axis), z_axis, self.grid_positions[cell])

    def _projected_tangent(
        self,
        positions: dict[tuple[int, int], Vector3],
        cell: tuple[int, int],
        z_axis: Vector3,
        sign: int,
    ) -> Vector3:
        stem = _cell_stem(cell)
        tangent = _normalize(self._cell_tangent(positions, cell), stem + " tangent", 1.0e-4 * self.guide_size)
        tangent = _multiply(tangent, float(sign))
        projected = _subtract(tangent, _multiply(z_axis, _dot(tangent, z_axis)))
        return _normalize(projected, stem + " projected tangent", 1.0e-3)

    def _create_cell_driver(self, cell: tuple[int, int], parent: PymelNode) -> None:
        row, col = cell
        stem = _cell_stem(cell)
        rest_values = self._rest_chain_cell_matrix(cell)
        pin_output = "%s.outputMatrix[%s]" % (
            self.cell_pin_node[self.column_panel[col]],
            self.k_col[col] * self.rows + row,
        )
        frame_values = self._matrix_attr(pin_output)
        axes = tuple((frame_values[i], frame_values[i + 1], frame_values[i + 2]) for i in (0, 4, 8))
        frame_matrix = om2.MMatrix(frame_values)
        if (
            any(abs(_length(axis) - 1.0) > 1.0e-6 for axis in axes)
            or any(abs(_dot(axes[i], axes[j])) > 1.0e-6 for i, j in ((0, 1), (0, 2), (1, 2)))
            or float(frame_matrix.det4x4()) <= 0.0
        ):
            raise RuntimeError("ymt_skirt_01 cell %s requires a right-handed orthonormal uvPin frame." % stem)
        offset_values = self._openmaya_matrix_values(om2.MMatrix(rest_values) * frame_matrix.inverse())
        matrix_node = cmds.createNode("multMatrix", name=self.getName(stem + "_pos_mm"))
        cmds.setAttr(matrix_node + ".matrixIn[0]", *offset_values, type="matrix")
        cmds.connectAttr(pin_output, matrix_node + ".matrixIn[1]", force=True)
        self._require_cell_matrix(matrix_node + ".matrixIn[0]", offset_values, 1.0e-9)
        position_node = cmds.createNode("decomposeMatrix", name=self.getName(stem + "_pos_dm"))
        cmds.connectAttr(matrix_node + ".matrixSum", position_node + ".inputMatrix", force=True)
        self.cell_position_matrices[cell] = matrix_node
        self.cell_position_nodes[cell] = position_node
        self.cell_parents[cell] = parent
        self.cell_rest_matrices[cell] = rest_values
        self.cell_rest_distances[cell] = _distance(self.grid_positions[cell], self._matrix_position(frame_values))

    def _create_cell_aim(self, cell: tuple[int, int]) -> None:
        row, col = cell
        stem = _cell_stem(cell)
        tangent_node = cmds.createNode("plusMinusAverage", name=self.getName(stem + "_tan_pma"))
        cmds.setAttr(tangent_node + ".operation", 2)
        next_col, prev_col = self._cell_neighbours(row, col)
        neighbours = (next_col if next_col is not None else col, prev_col if prev_col is not None else col)
        if self.cell_winding_sign < 0:
            neighbours = neighbours[::-1]
        for index, neighbour_col in enumerate(neighbours):
            cmds.connectAttr(
                self.cell_position_nodes[(row, neighbour_col)] + ".outputTranslate",
                "%s.input3D[%s]" % (tangent_node, index),
                force=True,
            )
        aim_node = cmds.createNode("aimMatrix", name=self.getName(stem + "_aim"))
        cmds.connectAttr(self.cell_position_matrices[cell] + ".matrixSum", aim_node + ".inputMatrix", force=True)
        target_row = row + 1 if row + 1 < self.rows else row - 1
        primary_axis = 1.0 if row + 1 < self.rows else -1.0
        cmds.setAttr(aim_node + ".primaryInputAxis", 0.0, 0.0, primary_axis, type="double3")
        cmds.connectAttr(
            self.cell_position_matrices[(target_row, col)] + ".matrixSum",
            aim_node + ".primaryTargetMatrix",
            force=True,
        )
        cmds.setAttr(aim_node + ".primaryTargetVector", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(aim_node + ".secondaryInputAxis", 1.0, 0.0, 0.0, type="double3")
        cmds.connectAttr(tangent_node + ".output3D", aim_node + ".secondaryTargetVector", force=True)
        self._configure_cell_aim_modes(aim_node, stem)
        self._verify_cell_aim_defaults(aim_node, stem)
        self.cell_aim_nodes[cell] = aim_node

    def _configure_cell_aim_modes(self, aim_node: str, stem: str) -> None:
        for attr, label in (("primaryMode", "Aim"), ("secondaryMode", "Align")):
            definitions = cast("list[str]", cmds.attributeQuery(attr, node=aim_node, listEnum=True))
            value = self._enum_value(definitions[0] if definitions else "", label)
            if value is None:
                raise RuntimeError("ymt_skirt_01 cell %s requires %s label %s." % (stem, attr, label))
            cmds.setAttr(aim_node + "." + attr, value)
            if cmds.getAttr(aim_node + "." + attr) != value:
                raise RuntimeError("ymt_skirt_01 cell %s failed to set %s to %s." % (stem, attr, label))

    def _verify_cell_aim_defaults(self, aim_node: str, stem: str) -> None:
        for attr in ("secondaryTargetMatrix", "preSpaceMatrix", "postSpaceMatrix"):
            if not cmds.attributeQuery(attr, node=aim_node, exists=True):
                continue
            if cmds.listConnections(aim_node + "." + attr, source=True, destination=False):
                raise RuntimeError("ymt_skirt_01 cell %s must leave aim %s unconnected." % (stem, attr))
            self._require_cell_matrix(aim_node + "." + attr, self._identity_matrix(), 1.0e-9)
        for attr, expected in (("enable", 1.0), ("envelope", 1.0)):
            if float(cmds.getAttr(aim_node + "." + attr)) != expected:
                raise RuntimeError("ymt_skirt_01 cell %s requires aim %s=%g." % (stem, attr, expected))

    def _enum_value(self, definition: str, label: str) -> int | None:
        # listEnum yields "name" tokens with implicit consecutive values, or "name=value" tokens.
        value = -1
        for token in definition.split(":"):
            name, separator, explicit = token.partition("=")
            value = int(explicit) if separator else value + 1
            if name == label:
                return value
        return None

    def _create_cell_npo(self, cell: tuple[int, int], evaluation_to_world: om2.MMatrix) -> PymelNode:
        stem = _cell_stem(cell)
        npo_name = cmds.createNode(
            "transform", name=self.getName(stem + "_npo"), parent=self._node_name(self.cell_parents[cell])
        )
        cmds.xform(npo_name, objectSpace=True, matrix=self._identity_matrix())
        self._require_cell_matrix(npo_name + ".matrix", self._identity_matrix(), 1.0e-6)
        aim_output = self.cell_aim_nodes[cell] + ".outputMatrix"
        cmds.connectAttr(aim_output, npo_name + ".offsetParentMatrix", force=True)
        if not cmds.isConnected(aim_output, npo_name + ".offsetParentMatrix"):
            raise RuntimeError("ymt_skirt_01 cell %s lost its aimMatrix connection." % stem)
        rest_values = self.cell_rest_matrices[cell]
        tolerance = 1.0e-6 * max(1.0, self.guide_size)
        self._require_cell_matrix(aim_output, rest_values, tolerance)
        expected_world = self._openmaya_matrix_values(om2.MMatrix(rest_values) * evaluation_to_world)
        self._require_cell_matrix(npo_name + ".worldMatrix[0]", expected_world, tolerance)
        return cast("PymelNode", pm.PyNode(npo_name))

    def _require_cell_matrix(self, plug: str, expected: Matrix16, tolerance: float) -> None:
        actual = self._matrix_attr(plug)
        if any(abs(value - target) > tolerance for value, target in zip(actual, expected)):
            raise RuntimeError("ymt_skirt_01 cell matrix %s differs from the expected transform." % plug)

    def _matrix_attr(self, plug: str) -> Matrix16:
        values = cmds.getAttr(plug)
        if isinstance(values, (list, tuple)) and len(values) == 1 and isinstance(values[0], (list, tuple)):
            values = values[0]
        flat = tuple(float(values[index]) for index in range(16))
        if not all(math.isfinite(value) for value in flat):
            raise RuntimeError("ymt_skirt_01 matrix plug returned non-finite values: %s." % plug)
        return cast("Matrix16", flat)

    def _identity_matrix(self) -> Matrix16:
        return _matrix_from_axes(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
        )

    def _openmaya_matrix_values(self, matrix: om2.MMatrix) -> Matrix16:
        return cast("Matrix16", tuple(float(matrix[index]) for index in range(16)))

    def _node_name(self, node: PymelNode | str) -> str:
        name = getattr(node, "name", None)
        return str(name()) if callable(name) else str(node)
