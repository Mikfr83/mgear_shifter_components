"""Guide for ymt_skirt_01."""

from __future__ import annotations

import importlib
import math
import re
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, ClassVar, cast

if TYPE_CHECKING:
    from ymt_shifter_utility.type_protocols import Point3Like, PymelNode, VectorLike

try:
    pm = importlib.import_module("mgear.pymaya")
except ImportError:
    pm = importlib.import_module("pymel.core")
try:
    datatypes = importlib.import_module("mgear.pymaya.datatypes")
except ImportError:
    datatypes = importlib.import_module("pymel.core.datatypes")

import maya.api.OpenMaya as om2
from maya import cmds
from maya.app.general.mayaMixin import MayaQDockWidget, MayaQWidgetDockableMixin
from mgear.core import curve, pyqt, transform
from mgear.shifter.component import guide
from mgear.vendor.Qt import QtCore, QtWidgets

from . import LEG_PROFILE_POSITION_NAMES, LEG_PROFILE_RADIUS_NAMES, _validated_leg_profile_value
from . import settingsUI as sui


AUTHOR = "yamahigashi"
URL = "yamahigashi.dev"
EMAIL = "yamahigashi@gmail.com"
VERSION = [0, 1, 0]
TYPE = "ymt_skirt_01"
NAME = "skirt"
DESCRIPTION = "Collider-driven FK skirt grid."

GRID_NAME_RE = re.compile(r"^skirt_(\d+)_(\d+)_loc$")
FIXED_REFERENCE_NAMES = ("waist", "hip_L", "knee_L", "heel_L", "hip_R", "knee_R", "heel_R")


def _grid_locator_name(col: int, row: int) -> str:
    return "skirt_%s_%s_loc" % (col, row)


def _grid_sort_key(local_name: str) -> tuple[int, int, str]:
    match = GRID_NAME_RE.fullmatch(local_name)
    if match is None:
        return (0, 0, local_name)
    return (int(match.group(1)), int(match.group(2)), local_name)


def _leg_section_frame(
    leg_axis: VectorLike, front_axis: VectorLike, scale_length: float, epsilon: float, label: str
) -> tuple[VectorLike, VectorLike]:
    length = float(leg_axis.length())
    if not math.isfinite(length) or length <= epsilon:
        raise RuntimeError("ymt_skirt_01 has a degenerate %s leg axis." % label)
    normal = leg_axis / length
    projected_front = front_axis - (normal * (front_axis * normal))
    if projected_front.length() * scale_length <= epsilon:
        raise RuntimeError("ymt_skirt_01 root front is parallel to the %s leg axis." % label)
    x_axis = projected_front.normal()
    return x_axis, (leg_axis ^ x_axis).normal()


def _profile_mesh_shapes(value: str) -> list[str]:
    """Resolve profileMesh to every non-intermediate mesh shape it names or contains.

    A transform resolves to all mesh shapes below it, so a body split into parts
    can be fitted by naming the group.
    """
    error = (
        "ymt_skirt_01 profileMesh=%r must name an existing, unambiguous mesh shape,"
        " or a transform with mesh shapes below it." % value
    )
    if not value or not cmds.objExists(value):
        raise RuntimeError(error)
    matches = cmds.ls(value, long=True) or []
    if len(matches) != 1:
        raise RuntimeError(error)
    node = matches[0]
    if cmds.nodeType(node) == "mesh":
        if cmds.getAttr(node + ".intermediateObject"):
            raise RuntimeError(error)
        return [node]
    if cmds.nodeType(node) == "transform":
        shapes = cmds.listRelatives(node, allDescendents=True, noIntermediate=True, fullPath=True, type="mesh") or []
        if shapes:
            return sorted(set(shapes))
    raise RuntimeError(error)


def _profile_mesh_shape(value: str) -> str:
    return _profile_mesh_shapes(value)[0]


def _segment_distance_squared(point: VectorLike, start: VectorLike, end: VectorLike) -> float:
    axis = end - start
    t = max(0.0, min(1.0, ((point - start) * axis) / (axis * axis)))
    delta = point - (start + axis * t)
    return delta * delta


@dataclass(frozen=True)
class _ProfileSection:
    radius_x: float
    radius_z: float
    t: float
    fallback: bool = False


def _required_profile_section(section: _ProfileSection | None, station: str, side: str) -> _ProfileSection:
    if section is None:
        raise RuntimeError("ymt_skirt_01 cannot fit %s_%s: fewer than 8 kept hits." % (station, side))
    return section


def _interior_profile_station(
    sections: list[_ProfileSection | None], start: _ProfileSection, end: _ProfileSection, segment: str
) -> _ProfileSection:
    valid = [section for section in sections[1:-1] if section is not None]
    if not valid:
        pm.displayWarning("ymt_skirt_01 profile segment %s used the midpoint fallback." % segment)
        return _ProfileSection((start.radius_x + end.radius_x) * 0.5, (start.radius_z + end.radius_z) * 0.5, 0.5, True)
    maximum = max(valid, key=lambda section: section.radius_x + section.radius_z)
    score = maximum.radius_x + maximum.radius_z
    tied = [
        section for section in valid if score == 0.0 or (score - (section.radius_x + section.radius_z)) / score < 1.0e-6
    ]
    return _ProfileSection(maximum.radius_x, maximum.radius_z, sum(section.t for section in tied) / len(tied))


def _profile_stations(
    sections_a: list[_ProfileSection | None], sections_b: list[_ProfileSection | None], side: str
) -> dict[str, _ProfileSection]:
    hip = _required_profile_section(sections_a[0], "Hip", side)
    knee_a = _required_profile_section(sections_a[-1], "Knee (A)", side)
    knee_b = _required_profile_section(sections_b[0], "Knee (B)", side)
    knee = _ProfileSection(max(knee_a.radius_x, knee_b.radius_x), max(knee_a.radius_z, knee_b.radius_z), 1.0)
    heel = _required_profile_section(sections_b[-1], "Heel", side)
    stations = {
        "hip": hip,
        "thigh": _interior_profile_station(sections_a, hip, knee, "A_%s (hip-to-knee)" % side),
        "knee": knee,
        "calf": _interior_profile_station(sections_b, knee, heel, "B_%s (knee-to-heel)" % side),
        "ankle": heel,
    }
    return {
        name: _ProfileSection(max(0.001, section.radius_x), max(0.001, section.radius_z), section.t, section.fallback)
        for name, section in stations.items()
    }


def _average_profile_values(profiles: dict[str, dict[str, _ProfileSection]], hip_separation: float) -> dict[str, float]:
    averages = {}
    for station in ("hip", "thigh", "knee", "calf", "ankle"):
        sides = [profiles[side][station] for side in ("L", "R")]
        measured = [section for section in sides if not section.fallback] or sides
        averages[station] = _ProfileSection(
            sum(section.radius_x for section in measured) / len(measured),
            sum(section.radius_z for section in measured) / len(measured),
            sum(section.t for section in measured) / len(measured),
        )
    hip = averages["hip"]
    values = {"ringScaleX": hip.radius_x / (hip_separation * 0.5), "ringScaleZ": hip.radius_z / (hip_separation * 0.5)}
    for station in ("thigh", "knee", "calf", "ankle"):
        values[station + "RadiusX"] = averages[station].radius_x / hip.radius_x
        values[station + "RadiusZ"] = averages[station].radius_z / hip.radius_z
    for station in ("thigh", "calf"):
        values[station + "Position"] = averages[station].t
    return values


class _LegProfileSampler:
    def __init__(self, mesh_name: str, hip_separation: float) -> None:
        self.meshes = []
        for shape in _profile_mesh_shapes(mesh_name):
            selection = om2.MSelectionList()
            selection.add(shape)
            mesh = om2.MFnMesh(selection.getDagPath(0))
            self.meshes.append((mesh, mesh.autoUniformGridParams()))
        self.max_param = 4.0 * hip_separation

    def _ray_hit(self, center: VectorLike, direction: VectorLike) -> VectorLike | None:
        source = om2.MFloatPoint(center.x, center.y, center.z)
        ray = om2.MFloatVector(direction.x, direction.y, direction.z)
        nearest = None
        nearest_param = self.max_param
        for mesh, accelerator in self.meshes:
            result = cast(
                "tuple[Point3Like, float, int, int, float, float] | None",
                mesh.closestIntersection(source, ray, om2.MSpace.kWorld, nearest_param, False, accelParams=accelerator),
            )
            if result is None:
                continue
            point, param = result[0], float(result[1])
            if nearest is None or param < nearest_param:
                nearest = datatypes.Vector(point.x, point.y, point.z)
                nearest_param = param
        return nearest

    def _section(
        self,
        t: float,
        segment: tuple[VectorLike, VectorLike],
        other_segment: tuple[VectorLike, VectorLike],
        axes: tuple[VectorLike, VectorLike],
        directions: list[VectorLike],
    ) -> _ProfileSection | None:
        start, end = segment
        center = start + (end - start) * t
        radius_x = radius_z = 0.0
        kept = 0
        for direction in directions:
            hit = self._ray_hit(center, direction)
            if hit is None:
                continue
            if _segment_distance_squared(hit, start, end) >= _segment_distance_squared(hit, *other_segment):
                continue
            delta = hit - center
            radius_x = max(radius_x, abs(delta * axes[0]))
            radius_z = max(radius_z, abs(delta * axes[1]))
            kept += 1
        return _ProfileSection(radius_x, radius_z, t) if kept >= 8 else None

    def sample_segment(
        self,
        segment: tuple[VectorLike, VectorLike],
        other_segment: tuple[VectorLike, VectorLike],
        axes: tuple[VectorLike, VectorLike],
    ) -> list[_ProfileSection | None]:
        directions = [
            (axes[0] * math.cos(2.0 * math.pi * k / 32) + axes[1] * math.sin(2.0 * math.pi * k / 32)).normal()
            for k in range(32)
        ]
        return [self._section(i / 16.0, segment, other_segment, axes, directions) for i in range(17)]


class Guide(guide.ComponentGuide):
    """Component guide class."""

    compType = TYPE
    compName = NAME
    description = DESCRIPTION

    author = AUTHOR
    url = URL
    email = EMAIL
    version = VERSION

    connectors: ClassVar[list[str]] = ["standard"]

    def postInit(self) -> None:
        self.save_transform = ["root", *FIXED_REFERENCE_NAMES]

    def addObjects(self) -> None:
        self.root = self.addRoot()
        self.waist = self.addLoc("waist", self.root, transform.getOffsetPosition(self.root, [0.0, 0.0, 0.0]))
        self.hip_L = self.addLoc("hip_L", self.root, transform.getOffsetPosition(self.root, [1.0, -1.5, 0.0]))
        self.knee_L = self.addLoc("knee_L", self.root, transform.getOffsetPosition(self.root, [0.9, -5.0, 0.0]))
        self.heel_L = self.addLoc("heel_L", self.root, transform.getOffsetPosition(self.root, [0.8, -9.0, 0.0]))
        self.hip_R = self.addLoc("hip_R", self.root, transform.getOffsetPosition(self.root, [-1.0, -1.5, 0.0]))
        self.knee_R = self.addLoc("knee_R", self.root, transform.getOffsetPosition(self.root, [-0.9, -5.0, 0.0]))
        self.heel_R = self.addLoc("heel_R", self.root, transform.getOffsetPosition(self.root, [-0.8, -9.0, 0.0]))
        self.grid_locs = self._add_grid_locators_from_template()

        self.left_leg_dispcrv = self.addDispCurve("leftLegCrv", [self.waist, self.hip_L, self.knee_L, self.heel_L])
        self.right_leg_dispcrv = self.addDispCurve("rightLegCrv", [self.waist, self.hip_R, self.knee_R, self.heel_R])
        self.row_dispcrvs = self._add_row_display_curves()

    def addParameters(self) -> None:
        self.pRows = self.addParam("rows", "long", 5, 2, None)
        self.pCols = self.addParam("cols", "long", 8, 3, None)
        self.pCtlSize = self.addParam("ctlSize", "double", 1.0, 0.001, None)
        self.pAddJoints = self.addParam("addJoints", "bool", True)
        self.pPostCollision = self.addParam("postCollision", "bool", True)
        self.pWave = self.addParam("wave", "bool", False)
        self.pRebuildSpansV = self.addParam("rebuildSpansV", "long", 4, 1, 256)
        self.pTightness = self.addParam("tightness", "double", 0.6, 0.0, 1.0)
        self.pFalloff = self.addParam("falloff", "double", -1.0, -1.0, 1.0)
        self.pSmoothness = self.addParam("smoothness", "double", 0.1, 0.0, 1.0)
        self.pFollow = self.addParam("follow", "double", 0.2, 0.0, 1.0)
        self.pRingPositions = self.addParam("ringPositions", "string", "auto")
        self.pRingScaleX = self.addParam("ringScaleX", "double", 1.0, 0.001, None)
        self.pRingScaleY = self.addParam("ringScaleY", "double", 1.0, 0.001, None)
        self.pRingScaleZ = self.addParam("ringScaleZ", "double", 1.0, 0.001, None)
        for name in LEG_PROFILE_RADIUS_NAMES:
            self.addParam(name, "double", 1.0, 0.001, None)
        for name in LEG_PROFILE_POSITION_NAMES:
            self.addParam(name, "double", 0.5, 0.0, 1.0)
        self.pProfileMesh = self.addParam("profileMesh", "string", "")
        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam("parentJointIndex", "long", -1, None, None)

    def setFromHierarchy(self, root: PymelNode) -> None:
        super(Guide, self).setFromHierarchy(root)
        self._collect_grid_guides()

    def _add_grid_locators_from_template(self) -> list[PymelNode]:
        locators = []
        locators_by_name: dict[str, PymelNode] = {}
        for local_name in self._serialized_grid_locator_names():
            col, row, _name = _grid_sort_key(local_name)
            if row == 0:
                parent = self.root
            else:
                parent_name = _grid_locator_name(col, row - 1)
                if parent_name not in locators_by_name:
                    raise RuntimeError(
                        "ymt_skirt_01 guide template has %s without its parent %s." % (local_name, parent_name)
                    )
                parent = locators_by_name[parent_name]
            position = transform.getPositionFromMatrix(self.tra[local_name])
            locator = self.addLoc(local_name, parent, position)
            locators_by_name[local_name] = locator
            locators.append(locator)
        return locators

    def _serialized_grid_locator_names(self) -> list[str]:
        names = [local_name for local_name in self.tra if GRID_NAME_RE.fullmatch(local_name)]
        return sorted(names, key=_grid_sort_key)

    def _add_row_display_curves(self) -> list[PymelNode]:
        rows: dict[int, list[tuple[int, PymelNode]]] = {}
        for locator in self.grid_locs:
            local_name = locator.name().split("|")[-1][len(self.fullName) + 1 :]
            match = GRID_NAME_RE.fullmatch(local_name)
            if match is None:
                continue
            rows.setdefault(int(match.group(2)), []).append((int(match.group(1)), locator))
        curves = []
        for row, indexed_locators in sorted(rows.items()):
            locators = [locator for _col, locator in sorted(indexed_locators)]
            if len(locators) >= 3:
                curves.append(self.addDispCurve("skirtRow%sCrv" % row, [*locators, locators[0]]))
        return curves

    def _collect_grid_guides(self) -> None:
        prefix = self.fullName + "_"
        children = pm.listRelatives(self.model, ad=True, typ="transform") or []
        grid_nodes = []
        name_counts: dict[str, int] = {}
        self.grid_locator_parents: dict[str, str] = {}
        for node in children:
            node_name = node.name().split("|")[-1]
            if not node_name.startswith(prefix):
                continue
            local_name = node_name[len(prefix) :]
            if not (local_name.startswith("skirt_") and local_name.endswith("_loc")):
                continue
            name_counts[local_name] = name_counts.get(local_name, 0) + 1
            parent_name = node.getParent().name().split("|")[-1]
            if parent_name.startswith(prefix):
                parent_name = parent_name[len(prefix) :]
            self.grid_locator_parents[local_name] = parent_name
            if local_name in self.tra:
                continue
            grid_nodes.append((local_name, node))
        self.grid_locator_name_counts = name_counts
        for local_name, node in sorted(grid_nodes, key=lambda item: _grid_sort_key(item[0])):
            matrix = node.getMatrix(worldSpace=True)
            position = node.getTranslation(space="world")
            self.tra[local_name] = matrix
            self.atra.append(matrix)
            self.pos[local_name] = position
            self.apos.append(position)


class settingsTab(QtWidgets.QDialog, sui.Ui_Form):
    """The component settings UI."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super(settingsTab, self).__init__(parent)
        self.setupUi(self)


class componentSettings(MayaQWidgetDockableMixin, guide.componentMainSettings):
    """Create the component settings window."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        self.toolName = TYPE
        pyqt.deleteInstances(self, MayaQDockWidget)
        super(self.__class__, self).__init__(parent=parent)
        self.settingsTab = settingsTab()

        self.setup_componentSettingWindow()
        self.create_componentControls()
        self._ensure_leg_profile_parameters()
        self.populate_componentControls()
        self.create_componentLayout()
        self.create_componentConnections()

    def setup_componentSettingWindow(self) -> None:
        self.mayaMainWindow = pyqt.maya_main_window()
        self.setObjectName(self.toolName)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(TYPE)
        self.resize(320, 520)

    def create_componentControls(self) -> None:
        return

    def populate_componentControls(self) -> None:
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")
        self.settingsTab.rows_spinBox.setValue(self.root.attr("rows").get())
        self.settingsTab.cols_spinBox.setValue(self.root.attr("cols").get())
        self.settingsTab.ctlSize_doubleSpinBox.setValue(self.root.attr("ctlSize").get())
        self.populateCheck(self.settingsTab.addJoints_checkBox, "addJoints")
        self.populateCheck(self.settingsTab.postCollision_checkBox, "postCollision")
        self.populateCheck(self.settingsTab.wave_checkBox, "wave")
        self.settingsTab.rebuildSpansV_spinBox.setValue(self.root.attr("rebuildSpansV").get())
        self.settingsTab.tightness_doubleSpinBox.setValue(self.root.attr("tightness").get())
        self.settingsTab.falloff_doubleSpinBox.setValue(self.root.attr("falloff").get())
        self.settingsTab.smoothness_doubleSpinBox.setValue(self.root.attr("smoothness").get())
        self.settingsTab.follow_doubleSpinBox.setValue(self.root.attr("follow").get())
        self.settingsTab.ringPositions_lineEdit.setText(self.root.attr("ringPositions").get())
        self.settingsTab.ringScaleX_doubleSpinBox.setValue(self.root.attr("ringScaleX").get())
        self.settingsTab.ringScaleY_doubleSpinBox.setValue(self.root.attr("ringScaleY").get())
        self.settingsTab.ringScaleZ_doubleSpinBox.setValue(self.root.attr("ringScaleZ").get())

        self._refresh_profile_controls()
        self.settingsTab.profileMesh_lineEdit.setText(self.root.attr("profileMesh").get())

        self.c_box = self.mainSettingsTab.connector_comboBox
        for connector in Guide.connectors:
            self.c_box.addItem(connector)
        self.connector_items = [self.c_box.itemText(index) for index in range(self.c_box.count())]
        current_connector = self.root.attr("connector").get()
        if current_connector not in self.connector_items:
            self.c_box.addItem(current_connector)
            self.connector_items.append(current_connector)
            pm.displayWarning("The current connector: %s is not valid for this component." % current_connector)
        self.c_box.setCurrentIndex(self.connector_items.index(current_connector))

    def create_componentLayout(self) -> None:
        self.settings_layout = QtWidgets.QVBoxLayout()
        self.settings_layout.addWidget(self.tabs)
        self.settings_layout.addWidget(self.close_button)
        self.setLayout(self.settings_layout)

    def create_componentConnections(self) -> None:
        self.settingsTab.rows_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.rows_spinBox, "rows")
        )
        self.settingsTab.cols_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.cols_spinBox, "cols")
        )
        self.settingsTab.rebuildGrid_pushButton.clicked.connect(self.rebuild_grid_locators)
        self.settingsTab.ctlSize_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.ctlSize_doubleSpinBox, "ctlSize")
        )
        self.settingsTab.addJoints_checkBox.stateChanged.connect(
            partial(self.updateCheck, self.settingsTab.addJoints_checkBox, "addJoints")
        )
        self.settingsTab.postCollision_checkBox.stateChanged.connect(
            partial(self.updateCheck, self.settingsTab.postCollision_checkBox, "postCollision")
        )
        self.settingsTab.wave_checkBox.stateChanged.connect(
            partial(self.updateCheck, self.settingsTab.wave_checkBox, "wave")
        )
        self.settingsTab.rebuildSpansV_spinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.rebuildSpansV_spinBox, "rebuildSpansV")
        )
        self.settingsTab.tightness_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.tightness_doubleSpinBox, "tightness")
        )
        self.settingsTab.falloff_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.falloff_doubleSpinBox, "falloff")
        )
        self.settingsTab.smoothness_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.smoothness_doubleSpinBox, "smoothness")
        )
        self.settingsTab.follow_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.follow_doubleSpinBox, "follow")
        )
        self.settingsTab.ringPositions_lineEdit.editingFinished.connect(self._update_ring_positions)
        self.settingsTab.ringScaleX_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleX_doubleSpinBox, "ringScaleX")
        )
        self.settingsTab.ringScaleY_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleY_doubleSpinBox, "ringScaleY")
        )
        self.settingsTab.ringScaleZ_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleZ_doubleSpinBox, "ringScaleZ")
        )
        for name in LEG_PROFILE_RADIUS_NAMES + LEG_PROFILE_POSITION_NAMES:
            spin_box = getattr(self.settingsTab, name + "_doubleSpinBox")
            spin_box.valueChanged.connect(partial(self._update_ring_scale, spin_box, name))
        self.settingsTab.profileMesh_lineEdit.editingFinished.connect(self._update_profile_mesh)
        self.settingsTab.useSelection_pushButton.clicked.connect(self.use_profile_mesh_selection)
        self.settingsTab.fitProfile_pushButton.clicked.connect(self.fit_profile_from_mesh)
        self.mainSettingsTab.connector_comboBox.currentIndexChanged.connect(
            partial(self.updateConnector, self.mainSettingsTab.connector_comboBox, self.connector_items)
        )

    def dockCloseEventTriggered(self) -> None:
        self._delete_ring_preview()
        pyqt.deleteInstances(self, MayaQDockWidget)

    def _ensure_leg_profile_parameters(self) -> list[str]:
        """Add the leg profile parameters to a guide root created before they existed.

        Guides keep their attribute set until updated, so a root built by an older
        component version lacks these parameters; they are created with the
        definition defaults so the dialog and the build see the current values.
        """
        definitions = Guide().paramDefs
        added = []
        for name in (*LEG_PROFILE_RADIUS_NAMES, *LEG_PROFILE_POSITION_NAMES, "profileMesh"):
            if pm.attributeQuery(name, node=self.root, exists=True):
                continue
            definitions[name].create(self.root)
            added.append(name)
        if added:
            pm.displayInfo("ymt_skirt_01 added missing guide parameters with defaults: %s" % ", ".join(added))
        return added

    def _update_ring_scale(self, spin_box: QtWidgets.QDoubleSpinBox, attr_name: str, *_args: float) -> None:
        self.updateSpinBox(spin_box, attr_name)
        self.update_ring_preview()

    def _update_ring_positions(self) -> None:
        self.root.attr("ringPositions").set(self.settingsTab.ringPositions_lineEdit.text())

    def _update_profile_mesh(self) -> None:
        self.root.attr("profileMesh").set(self.settingsTab.profileMesh_lineEdit.text())

    def use_profile_mesh_selection(self) -> None:
        for selected in cmds.ls(selection=True, long=True, objectsOnly=True) or []:
            try:
                _profile_mesh_shapes(selected)
            except RuntimeError:
                continue
            value = selected
            if cmds.nodeType(selected) == "mesh":
                parents = cmds.listRelatives(selected, parent=True, fullPath=True) or []
                value = parents[0] if parents else selected
            self.root.attr("profileMesh").set(value)
            self.settingsTab.profileMesh_lineEdit.setText(value)
            return
        raise RuntimeError("ymt_skirt_01 Use selection requires a selected mesh, or a group containing meshes.")

    def _refresh_profile_controls(self) -> None:
        tab = getattr(self, "settingsTab", None)
        if tab is None:
            return
        for name in ("ringScaleX", "ringScaleZ", *LEG_PROFILE_RADIUS_NAMES, *LEG_PROFILE_POSITION_NAMES):
            spin_box = getattr(tab, name + "_doubleSpinBox")
            blocked = spin_box.blockSignals(True)
            try:
                spin_box.setValue(float(self.root.attr(name).get()))
            finally:
                spin_box.blockSignals(blocked)

    def _ring_preview_context(self) -> tuple[dict[str, VectorLike], VectorLike, float, float, float]:
        positions = {name: componentSettings._guide_position(self, name) for name in FIXED_REFERENCE_NAMES}
        heel_midpoint = (positions["heel_L"] + positions["heel_R"]) * 0.5
        axis_length = float((heel_midpoint - positions["waist"]).length())
        epsilon = 1.0e-3 * axis_length
        if not math.isfinite(axis_length) or axis_length <= epsilon:
            raise RuntimeError("ymt_skirt_01 requires a non-degenerate waist-to-heel axis for the ring preview.")
        front = componentSettings._root_front(self)
        front_length = float(front.length())
        if not math.isfinite(front_length) or front_length <= 0.0:
            raise RuntimeError("ymt_skirt_01 requires a non-degenerate guide root front for the ring preview.")
        hip_radius = float((positions["hip_L"] - positions["hip_R"]).length()) * 0.5
        if not math.isfinite(hip_radius) or hip_radius <= epsilon:
            raise RuntimeError("ymt_skirt_01 requires separated hip references for the ring preview.")
        return positions, front / front_length, axis_length, epsilon, hip_radius

    def fit_profile_from_mesh(self) -> None:
        mesh_name = str(self.root.attr("profileMesh").get())
        _profile_mesh_shapes(mesh_name)
        positions, front, axis_length, epsilon, hip_radius = componentSettings._ring_preview_context(self)
        segments = {
            side: (
                (positions["hip_" + side], positions["knee_" + side]),
                (positions["knee_" + side], positions["heel_" + side]),
            )
            for side in ("L", "R")
        }
        frames = {
            side: [
                _leg_section_frame(end - start, front, axis_length, epsilon, "%s_%s" % (label, side))
                for label, (start, end) in zip(("A", "B"), segments[side])
            ]
            for side in ("L", "R")
        }
        sampler = _LegProfileSampler(mesh_name, hip_radius * 2.0)
        profiles = {}
        for side, other in (("L", "R"), ("R", "L")):
            sections = [
                sampler.sample_segment(segments[side][index], segments[other][index], frames[side][index])
                for index in range(2)
            ]
            profiles[side] = _profile_stations(sections[0], sections[1], side)
        values = _average_profile_values(profiles, hip_radius * 2.0)
        for name, value in values.items():
            self.root.attr(name).set(value)
        componentSettings._refresh_profile_controls(self)
        componentSettings.update_ring_preview(self)
        for side, stations in profiles.items():
            for station, section in stations.items():
                pm.displayInfo(
                    "ymt_skirt_01 profile %s_%s: X=%.9g Z=%.9g position=%.9g fallback=%s"
                    % (station, side, section.radius_x, section.radius_z, section.t, section.fallback)
                )

    def update_ring_preview(self) -> None:
        """Redraw guide-side ellipse curves visualizing the leg collision ring size."""
        try:
            positions, front, axis_length, epsilon, hip_radius = componentSettings._ring_preview_context(self)
            profile = {
                name: _validated_leg_profile_value(name, self.root.attr(name).get())
                for name in LEG_PROFILE_RADIUS_NAMES + LEG_PROFILE_POSITION_NAMES
            }
        except RuntimeError as exc:
            pm.displayWarning(str(exc))
            return
        radius_x = float(self.root.attr("ringScaleX").get()) * hip_radius
        radius_z = float(self.root.attr("ringScaleZ").get()) * hip_radius
        componentSettings._delete_ring_preview(self)
        for side in ("L", "R"):
            hip = positions["hip_%s" % side]
            knee = positions["knee_%s" % side]
            heel = positions["heel_%s" % side]
            stations = (
                ("Hip", hip, knee - hip, 1.0, 1.0),
                (
                    "Thigh",
                    hip + (knee - hip) * profile["thighPosition"],
                    knee - hip,
                    profile["thighRadiusX"],
                    profile["thighRadiusZ"],
                ),
                ("Knee", knee, heel - knee, profile["kneeRadiusX"], profile["kneeRadiusZ"]),
                (
                    "Calf",
                    knee + (heel - knee) * profile["calfPosition"],
                    heel - knee,
                    profile["calfRadiusX"],
                    profile["calfRadiusZ"],
                ),
                ("Heel", heel, heel - knee, profile["ankleRadiusX"], profile["ankleRadiusZ"]),
            )
            for label, center, leg_axis, multiplier_x, multiplier_z in stations:
                try:
                    componentSettings._create_ring_preview_circle(
                        self,
                        side,
                        label,
                        center,
                        leg_axis,
                        front,
                        axis_length,
                        epsilon,
                        radius_x * multiplier_x,
                        radius_z * multiplier_z,
                    )
                except RuntimeError as exc:
                    pm.displayWarning(str(exc))

    def _create_ring_preview_circle(
        self,
        side: str,
        label: str,
        center: VectorLike,
        leg_axis: VectorLike,
        front_axis: VectorLike,
        scale_length: float,
        epsilon: float,
        radius_x: float,
        radius_z: float,
    ) -> None:
        u_axis, v_axis = _leg_section_frame(leg_axis, front_axis, scale_length, epsilon, "%s_%s" % (label, side))
        points = []
        segments = 24
        for index in range(segments + 1):
            angle = (2.0 * math.pi * index) / segments
            points.append(center + (u_axis * (radius_x * math.cos(angle))) + (v_axis * (radius_z * math.sin(angle))))
        prefix = self.root.name().replace("_root", "")
        node = curve.addCurve(
            self.root,
            "%s_ringPreview%s_%s_Crv" % (prefix, label, side),
            points,
            close=False,
            degree=1,
        )
        node.attr("template").set(True)

    def _delete_ring_preview(self) -> None:
        prefix = self.root.name().replace("_root", "")
        stale = []
        for node in pm.listRelatives(self.root, ad=True, typ="transform") or []:
            node_name = node.name().split("|")[-1]
            if node_name.startswith(prefix + "_ringPreview"):
                stale.append(node)
        if stale:
            pm.delete(stale)

    def rebuild_grid_locators(self) -> None:
        rows = self.settingsTab.rows_spinBox.value()
        cols = self.settingsTab.cols_spinBox.value()
        try:
            waist = self._guide_position("waist")
            heel_left = self._guide_position("heel_L")
            heel_right = self._guide_position("heel_R")
            hip_left = self._guide_position("hip_L")
            hip_right = self._guide_position("hip_R")
            axis_vector = ((heel_left + heel_right) * 0.5) - waist
            axis_length = axis_vector.length()
            epsilon = 1.0e-3 * axis_length
            axis = self._normalized(axis_vector, "waist-to-heel axis", epsilon)
            front = self._root_front()
            front_length = front.length()
            if not math.isfinite(float(front_length)) or front_length <= 0.0:
                raise RuntimeError("ymt_skirt_01 has degenerate guide root front.")
            front = front / front_length
            projected_front = front - (axis * (front * axis))
            projected_front = self._normalized(
                projected_front * axis_length,
                "projected root front",
                epsilon,
            )
            hip_radius = (hip_left - hip_right).length() * 0.5
            if hip_radius <= epsilon:
                raise RuntimeError("ymt_skirt_01 requires separated hip references to rebuild the grid.")
        except RuntimeError as exc:
            pm.displayWarning(str(exc))
            return

        side = axis ^ projected_front
        try:
            self._delete_existing_grid()
            created_by_row: dict[int, list[PymelNode]] = {}
            for col in range(cols):
                parent = self.root
                angle = (2.0 * math.pi * col) / float(cols)
                radial = (projected_front * math.cos(angle)) + (side * math.sin(angle))
                for row in range(rows):
                    row_ratio = row / float(rows - 1)
                    axial_fraction = 0.15 + (0.75 * row_ratio)
                    radius = hip_radius * (1.0 + (0.6 * row_ratio))
                    center = waist + (axis * axis_length * axial_fraction)
                    locator = self._create_grid_locator(
                        _grid_locator_name(col, row), parent, center + (radial * radius)
                    )
                    created_by_row.setdefault(row, []).append(locator)
                    parent = locator
            self._create_row_display_curves(created_by_row)
        except RuntimeError as exc:
            pm.displayWarning(str(exc))
            return
        created = [locator for row in range(rows) for locator in created_by_row[row]]
        pm.select(created)
        pm.displayInfo("Rebuilt %s ymt_skirt_01 grid locators." % len(created))

    def _guide_position(self, local_name: str) -> VectorLike:
        prefix = self.root.name().replace("_root", "")
        node_name = "%s_%s" % (prefix, local_name)
        if not pm.objExists(node_name):
            raise RuntimeError("ymt_skirt_01 guide is missing %s." % local_name)
        values = pm.xform(pm.PyNode(node_name), q=True, ws=True, t=True)
        if len(values) != 3 or not all(math.isfinite(float(value)) for value in values):
            raise RuntimeError("ymt_skirt_01 guide reference is non-finite: %s." % local_name)
        return datatypes.Vector(values)

    def _root_front(self) -> VectorLike:
        matrix = pm.xform(self.root, q=True, ws=True, matrix=True)
        values = [float(matrix[index]) for index in (8, 9, 10)]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError("ymt_skirt_01 guide root front is non-finite.")
        return datatypes.Vector(values)

    def _normalized(self, value: VectorLike, label: str, threshold: float) -> VectorLike:
        if value.length() <= threshold:
            raise RuntimeError("ymt_skirt_01 has degenerate %s." % label)
        return value.normal()

    def _delete_existing_grid(self) -> None:
        prefix = self.root.name().replace("_root", "")
        top = self.root.getParent(generations=-1)
        grid_nodes = []
        row_curves = []
        for node in pm.listRelatives(top, ad=True, typ="transform") or []:
            node_name = node.name().split("|")[-1]
            if not node_name.startswith(prefix + "_"):
                continue
            local_name = node_name[len(prefix) + 1 :]
            if local_name.startswith("skirt_") and local_name.endswith("_loc"):
                grid_nodes.append(node)
            elif local_name.startswith("skirtRow") and local_name.endswith("Crv"):
                row_curves.append(node)
        if row_curves:
            pm.delete(row_curves)
        if grid_nodes:
            pm.delete(grid_nodes)

    def _create_grid_locator(self, local_name: str, parent: PymelNode, position: VectorLike) -> PymelNode:
        prefix = self.root.name().replace("_root", "")
        created = pm.spaceLocator(name="%s_%s" % (prefix, local_name))
        node = created[0] if isinstance(created, (list, tuple)) else created
        node = pm.PyNode(node)
        node.setTranslation(position, space="world")
        pm.parent(node, parent, absolute=True)
        return node

    def _create_row_display_curves(self, locators_by_row: dict[int, list[PymelNode]]) -> None:
        prefix = self.root.name().replace("_root", "")
        for row, locators in sorted(locators_by_row.items()):
            curve.addCnsCurve(
                self.root,
                "%s_skirtRow%sCrv" % (prefix, row),
                [*locators, locators[0]],
                degree=1,
            )
