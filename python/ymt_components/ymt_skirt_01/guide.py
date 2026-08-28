"""Guide for ymt_skirt_01."""

from __future__ import annotations

import importlib
import math
import re
from functools import partial
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from ymt_shifter_utility.type_protocols import PymelNode, VectorLike

try:
    pm = importlib.import_module("mgear.pymaya")
except ImportError:
    pm = importlib.import_module("pymel.core")
try:
    datatypes = importlib.import_module("mgear.pymaya.datatypes")
except ImportError:
    datatypes = importlib.import_module("pymel.core.datatypes")

from . import settingsUI as sui

maya_mixin = importlib.import_module("maya.app.general.mayaMixin")
MayaQDockWidget = maya_mixin.MayaQDockWidget
MayaQWidgetDockableMixin = maya_mixin.MayaQWidgetDockableMixin
curve = importlib.import_module("mgear.core.curve")
pyqt = importlib.import_module("mgear.core.pyqt")
transform = importlib.import_module("mgear.core.transform")
guide = importlib.import_module("mgear.shifter.component.guide")
qt = importlib.import_module("mgear.vendor.Qt")
QtCore = qt.QtCore
QtWidgets = qt.QtWidgets


AUTHOR = "yamahigashi"
URL = "yamahigashi.dev"
EMAIL = "yamahigashi@gmail.com"
VERSION = [1, 3, 1]
TYPE = "ymt_skirt_01"
NAME = "skirt"
DESCRIPTION = "Collider-driven FK skirt grid."

GRID_NAME_RE = re.compile(r"^skirt_(\d+)_(\d+)_loc$")
FIXED_REFERENCE_NAMES = ("waist", "hip_L", "knee_L", "heel_L", "hip_R", "knee_R", "heel_R")


def _grid_name(row: int, col: int) -> str:
    return "skirt_%s_%s_loc" % (row, col)


def _grid_sort_key(local_name: str) -> tuple[int, int, str]:
    match = GRID_NAME_RE.fullmatch(local_name)
    if match is None:
        return (0, 0, local_name)
    return (int(match.group(1)), int(match.group(2)), local_name)


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
        self.pCollision = self.addParam("collision", "double", 0.2, 0.0, 1.0)
        self.pTightness = self.addParam("tightness", "double", 0.5, 0.0, 1.0)
        self.pFalloff = self.addParam("falloff", "double", -1.0, -1.0, 1.0)
        self.pRingScaleX = self.addParam("ringScaleX", "double", 1.0, 0.001, None)
        self.pRingScaleY = self.addParam("ringScaleY", "double", 1.0, 0.001, None)
        self.pRingScaleZ = self.addParam("ringScaleZ", "double", 1.0, 0.001, None)
        self.pUseIndex = self.addParam("useIndex", "bool", False)
        self.pParentJointIndex = self.addParam("parentJointIndex", "long", -1, None, None)

    def setFromHierarchy(self, root: PymelNode) -> None:
        super(Guide, self).setFromHierarchy(root)
        self._collect_grid_guides()

    def _add_grid_locators_from_template(self) -> list[PymelNode]:
        locators = []
        for local_name in self._serialized_grid_locator_names():
            position = transform.getPositionFromMatrix(self.tra[local_name])
            locators.append(self.addLoc(local_name, self.root, position))
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
            rows.setdefault(int(match.group(1)), []).append((int(match.group(2)), locator))
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
        for node in children:
            node_name = node.name().split("|")[-1]
            if not node_name.startswith(prefix):
                continue
            local_name = node_name[len(prefix) :]
            if not (local_name.startswith("skirt_") and local_name.endswith("_loc")):
                continue
            name_counts[local_name] = name_counts.get(local_name, 0) + 1
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
        self.populate_componentControls()
        self.create_componentLayout()
        self.create_componentConnections()

    def setup_componentSettingWindow(self) -> None:
        self.mayaMainWindow = pyqt.maya_main_window()
        self.setObjectName(self.toolName)
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle(TYPE)
        self.resize(320, 430)

    def create_componentControls(self) -> None:
        return

    def populate_componentControls(self) -> None:
        self.tabs.insertTab(1, self.settingsTab, "Component Settings")
        self.settingsTab.rows_spinBox.setValue(self.root.attr("rows").get())
        self.settingsTab.cols_spinBox.setValue(self.root.attr("cols").get())
        self.settingsTab.ctlSize_doubleSpinBox.setValue(self.root.attr("ctlSize").get())
        self.populateCheck(self.settingsTab.addJoints_checkBox, "addJoints")
        self.settingsTab.collision_doubleSpinBox.setValue(self.root.attr("collision").get())
        self.settingsTab.tightness_doubleSpinBox.setValue(self.root.attr("tightness").get())
        self.settingsTab.falloff_doubleSpinBox.setValue(self.root.attr("falloff").get())
        self.settingsTab.ringScaleX_doubleSpinBox.setValue(self.root.attr("ringScaleX").get())
        self.settingsTab.ringScaleY_doubleSpinBox.setValue(self.root.attr("ringScaleY").get())
        self.settingsTab.ringScaleZ_doubleSpinBox.setValue(self.root.attr("ringScaleZ").get())

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
        self.settingsTab.collision_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.collision_doubleSpinBox, "collision")
        )
        self.settingsTab.tightness_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.tightness_doubleSpinBox, "tightness")
        )
        self.settingsTab.falloff_doubleSpinBox.valueChanged.connect(
            partial(self.updateSpinBox, self.settingsTab.falloff_doubleSpinBox, "falloff")
        )
        self.settingsTab.ringScaleX_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleX_doubleSpinBox, "ringScaleX")
        )
        self.settingsTab.ringScaleY_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleY_doubleSpinBox, "ringScaleY")
        )
        self.settingsTab.ringScaleZ_doubleSpinBox.valueChanged.connect(
            partial(self._update_ring_scale, self.settingsTab.ringScaleZ_doubleSpinBox, "ringScaleZ")
        )
        self.mainSettingsTab.connector_comboBox.currentIndexChanged.connect(
            partial(self.updateConnector, self.mainSettingsTab.connector_comboBox, self.connector_items)
        )

    def dockCloseEventTriggered(self) -> None:
        self._delete_ring_preview()
        pyqt.deleteInstances(self, MayaQDockWidget)

    def _update_ring_scale(self, spin_box: QtWidgets.QDoubleSpinBox, attr_name: str, *_args: float) -> None:
        self.updateSpinBox(spin_box, attr_name)
        self.update_ring_preview()

    def update_ring_preview(self) -> None:
        """Redraw guide-side ellipse curves visualizing the leg collision ring size."""
        try:
            positions = {name: self._guide_position(name) for name in FIXED_REFERENCE_NAMES}
            waist = positions["waist"]
            heel_midpoint = (positions["heel_L"] + positions["heel_R"]) * 0.5
            axis_length = (heel_midpoint - waist).length()
            epsilon = 1.0e-3 * axis_length
            if not math.isfinite(float(axis_length)) or axis_length <= epsilon:
                raise RuntimeError("ymt_skirt_01 requires a non-degenerate waist-to-heel axis for the ring preview.")
            front = self._root_front()
            front_length = front.length()
            if not math.isfinite(float(front_length)) or front_length <= 0.0:
                raise RuntimeError("ymt_skirt_01 requires a non-degenerate guide root front for the ring preview.")
            front = front / front_length
            hip_radius = (positions["hip_L"] - positions["hip_R"]).length() * 0.5
            if hip_radius <= epsilon:
                raise RuntimeError("ymt_skirt_01 requires separated hip references for the ring preview.")
        except RuntimeError as exc:
            pm.displayWarning(str(exc))
            return
        radius_x = float(self.root.attr("ringScaleX").get()) * hip_radius
        radius_z = float(self.root.attr("ringScaleZ").get()) * hip_radius
        self._delete_ring_preview()
        for side in ("L", "R"):
            hip = positions["hip_%s" % side]
            knee = positions["knee_%s" % side]
            heel = positions["heel_%s" % side]
            stations = (("Hip", hip, knee - hip), ("Knee", knee, heel - knee), ("Heel", heel, heel - knee))
            for label, center, leg_axis in stations:
                try:
                    self._create_ring_preview_circle(
                        side,
                        label,
                        center,
                        leg_axis,
                        front,
                        axis_length,
                        epsilon,
                        radius_x,
                        radius_z,
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
        if leg_axis.length() <= epsilon:
            raise RuntimeError("ymt_skirt_01 ring preview skipped a degenerate %s_%s leg axis." % (label, side))
        normal = leg_axis.normal()
        projected_front = front_axis - (normal * (front_axis * normal))
        if projected_front.length() * scale_length <= epsilon:
            raise RuntimeError(
                "ymt_skirt_01 ring preview skipped %s_%s because the root front is parallel to the leg axis."
                % (label, side)
            )
        u_axis = projected_front.normal()
        v_axis = (leg_axis ^ u_axis).normal()
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
            for row in range(rows):
                row_ratio = row / float(rows - 1)
                axial_fraction = 0.15 + (0.75 * row_ratio)
                radius = hip_radius * (1.0 + (0.6 * row_ratio))
                center = waist + (axis * axis_length * axial_fraction)
                for col in range(cols):
                    angle = (2.0 * math.pi * col) / float(cols)
                    radial = (projected_front * math.cos(angle)) + (side * math.sin(angle))
                    locator = self._create_grid_locator(_grid_name(row, col), center + (radial * radius))
                    created_by_row.setdefault(row, []).append(locator)
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

    def _create_grid_locator(self, local_name: str, position: VectorLike) -> PymelNode:
        prefix = self.root.name().replace("_root", "")
        created = pm.spaceLocator(name="%s_%s" % (prefix, local_name))
        node = created[0] if isinstance(created, (list, tuple)) else created
        node = pm.PyNode(node)
        node.setTranslation(position, space="world")
        pm.parent(node, self.root)
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
