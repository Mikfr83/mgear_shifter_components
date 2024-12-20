"""mGear shifter components"""
# pylint: disable=import-error,W0201,C0111,C0112
import re
import six
import sys
import math
import traceback

import maya.cmds as cmds
import maya.api.OpenMaya as om

import pymel.core as pm
from pymel.core import datatypes

from mgear import rigbits
from mgear.rigbits import ghost
from mgear.shifter import component

from mgear.core import (
    transform,
    applyop,
    # vector,
    node,
    primitive,
)

from mgear.core.transform import (
    getTransform,
    setMatrixPosition,
    setMatrixRotation,
    setMatrixScale,
)

from mgear.core.primitive import (
    addTransform,
)
import ymt_shifter_utility as ymt_util
import ymt_shifter_utility.curve as curve


if sys.version_info > (3, 0):
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from typing import (
            Optional,  # noqa: F401
            Dict,  # noqa: F401
            List,  # noqa: F401
            Tuple,  # noqa: F401
            Pattern,  # noqa: F401
            Callable,  # noqa: F401
            Any,  # noqa: F401
            Text,  # noqa: F401
            Generator,  # noqa: F401
            Union  # noqa: F401
        )

from logging import (  # noqa:F401 pylint: disable=unused-import, wrong-import-order
    StreamHandler,
    getLogger,
    WARN,  # noqa: F401
    DEBUG,
    INFO
)

handler = StreamHandler()
handler.setLevel(DEBUG)
logger = getLogger(__name__)
logger.setLevel(INFO)
logger.setLevel(DEBUG)
logger.addHandler(handler)
logger.propagate = False


##########################################################
# COMPONENT
##########################################################
class Component(component.Main):
    """Shifter component Class"""

    # =====================================================
    # OBJECTS
    # =====================================================
    def addObjects(self):
        """Add all the objects needed to create the component."""

        self.normal = self.guide.blades["blade"].z * -1.
        self.binormal = self.guide.blades["blade"].x

        self.WIP = self.options["mode"]

        if self.negate and self.settings["overrideNegate"]:
            self.negate = False
            self.n_factor = 1

        if self.settings["overrideNegate"]:
            self.mirror_conf = [0, 0, 1,
                                1, 1, 0,
                                0, 0, 0]
        else:
            self.mirror_conf = [0, 0, 0,
                                0, 0, 0,
                                0, 0, 0]

        self.connect_surface_slider = self.settings["isSlidingSurface"]
        self.surfRef = self.settings["surfaceReference"]
        self.mouthCenterRef = self.settings["mouthCenterReference"]
        self.mouthLeftRef = self.settings["mouthLeftReference"]
        self.mouthRightRef = self.settings["mouthRightReference"]
        # -------------------------------------------------------

        self.num_locs = self.getNumberOfLocators("_loc")

        self.upPos = self.guide.apos[-3]
        self.lowPos = self.guide.apos[-2]
        self.frontPos = self.guide.apos[-1]
        self.rootPos = self.guide.apos[0]

        self.locsPos = self.guide.apos[2:self.num_locs + 2]

        self.offset = (self.frontPos - self.rootPos) * 0.3
        if self.negate:
            pass
            # self.offset[2] = self.offset[2] * -1.0

        # -------------------------------------------------------
        self.ctlName = "ctl"
        self.detailControllersGroupName = "controllers_detail"  # TODO: extract to settings
        self.primaryControllersGroupName = "controllers_primary"  # TODO: extract to settings

        self.thickness = 0.07
        self.FRONT_OFFSET = 0.2
        self.NB_CVS = 2 * 4 + 4  # means 4 spans with 2 controllers each + 4 controllers for the corners
        if self.num_locs % 2 == 0:
            # even
            self.NB_ROPE = self.num_locs * 2 + 1
        else:
            self.NB_ROPE = self.num_locs * 2

        # odd / event
        if self.num_locs % 2 == 0:
            self.bottom_index = int(self.num_locs / 2)
        else:
            self.bottom_index = int((self.num_locs -1) / 2)

        # treat most left side as corner index
        peek_x = 0.0
        self.left_index = 0
        for i in range(0, self.bottom_index):
            if self.locsPos[i][0] > peek_x:
                peek_x = self.locsPos[i][0]
                self.left_index = i

        peek_x = 0.0
        self.right_index = 0
        for i in range(self.bottom_index, self.num_locs):
            if self.locsPos[i][0] < peek_x:
                peek_x = self.locsPos[i][0]
                self.right_index = i

        # --------------------------------------------------------
        self.crv = None
        self.crv_ctl = None

        self.previusTag = self.parentCtlTag

        self.addContainers()
        self.addCurve()
        self.addControlJoints()
        self.addControllers()
        self.addConstraints()

    def addContainers(self):

        t = getTransform(self.root)

        self.crv_root = addTransform(self.root, self.getName("crvs"), t)
        self.ctl_root = addTransform(self.root, self.getName("ctls"), t)
        self.rope_root = addTransform(self.root, self.getName("rope"), t)

    def getNumberOfLocators(self, query):
        # type: (Text) -> int
        """ _uplocs."""
        num = 0
        for k, v in self.guide.tra.items():
            if query in k:
                index = int(re.search(r"^(\d+)", k).group(1))
                num = max(num, index + 1)

        return num

    def addDummyPlane(self):
        # type: () -> om.MFnMesh

        positions = []
        positions.extend(self.locsPos)

        return draw_eye_guide_mesh_plane(positions, self.root)

    def addCurve(self):

        self.addCurves(self.crv_root)
        self.addCurveBaseControllers(self.crv_root)

        if not self.surfRef:
            self.sliding_surface = pm.duplicate(self.guide.getObjects(self.guide.root)["sliding_surface"])[0]
            pm.parent(self.sliding_surface.name(), self.root)
            self.sliding_surface.visibility.set(False)
            pm.makeIdentity(self.sliding_surface, apply=True, t=1,  r=1, s=1, n=0, pn=1)

    def getCurveCVs(self, crv, space="world"):
        # type: (...) -> List[om.MPoint]

        cvs = crv.getCVs(space=space)
        degree = cmds.getAttr("{}.degree".format(crv))

        # TODO: extract to settings later
        # if self.settings["close"]:
        cvs = cvs[:len(cvs) - degree]  # closed curve goes not get cvs properly

        return cvs

    def addCurves(self, crv_root):

        t = getTransform(self.root)
        plane = self.addDummyPlane()
        planeNode = pm.PyNode(plane.fullPathName())

        # -------------------------------------------------------------------
        edgeList = ["{}.e[{}]".format(plane.fullPathName(), 0)]
        for i in range(1, self.num_locs + 1):
            edgeList.append("{}.e[{}]".format(plane.fullPathName(), i * 2 + 1))
        edgeList = [pm.PyNode(x) for x in edgeList]
        crv = curve.createCurveFromOrderedEdges(
            edgeList,
            planeNode.verts[1],
            self.getName("crv"),
            parent=crv_root,
            m=t,
            close=True
        )
        crv.attr("visibility").set(False)
        cvs = self.getCurveCVs(crv)
        center_pos = sum(cvs) / len(cvs)  # type: ignore
        for i, cv in enumerate(cvs):
            offset = (cv - center_pos).normal() * self.thickness
            new_pos = [cv[0] + offset[0], cv[1] + offset[1], cv[2] + offset[2]]
            crv.setCV(i, new_pos, space="world")
        self.crv = crv
        cmds.delete(cmds.listRelatives(plane.fullPathName(), parent=True))

    def addCurveBaseControllers(self, crv_root):

        def curveFromCurve(crv, name, nbPoints, tobe_offset):
            t = getTransform(self.root)

            new_crv = curve.createCurveFromCurve(
                crv,
                self.getName(name),
                nbPoints=nbPoints,
                parent=crv_root,
                m=t,
                close=True
            )
            new_crv.attr("visibility").set(False)

            return new_crv

        # -------------------------------------------------------------------
        self.crv_ctl  = curveFromCurve(self.crv, "ctl_crv",  12,  False)
        self.rope     = curveFromCurve(self.crv, "rope_crv", self.NB_ROPE, False)

    def addControlJoints(self):
        self.tweakControllers = self._addDetailControls(self.crv, self.rope_root, self.rope)

    def _addDetailControls(self, crv, rope_root, rope):

        local_cvs = self.getCurveCVs(crv, "object")
        controls = []
        t = getTransform(self.root)

        icon_shape = "sphere"
        color = 4
        wd = .3
        po = self.offset * 0.3

        cvsObject = self.getCurveCVs(crv, "object")
        cvsWorld = self.getCurveCVs(crv, "world")
        cvPairs = list(zip(cvsObject, cvsWorld))
        cvs = cvPairs[0:-1]

        for i, (cvo, cvw) in enumerate(cvs):

            mirror = i > self.num_locs / 2
            lower = i > self.left_index and i < self.right_index

            if i == 0: 
                oSide = "C"
                _index = 0

            elif i == self.bottom_index: 
                oSide = "C"
                _index = 1

            elif not mirror:
                oSide = "L"
                if i <= self.left_index:
                    _index = i - 1
                else:
                    _index = (self.bottom_index - i + self.left_index - 1)

            else:
                tmp = self.num_locs - self.right_index
                oSide = "R"
                if i < self.right_index:
                    _index = (i - self.bottom_index + tmp - 2)
                else:
                    _index = (tmp - i + self.right_index - 2)

            with ymt_util.overrideNamingAttributeTemporary(self, side=oSide):
                cns = addTransform(rope_root, self.getName("rope_{}_cns".format(_index)))
                applyPathCnsLocal(cns, self.crv_ctl, rope, cvo)

                m = getTransform(cns)
                x = datatypes.Vector(m[0][0], m[0][1], m[0][2])
                y = datatypes.Vector(m[1][0], m[1][1], m[1][2])
                z = datatypes.Vector(m[2][0], m[2][1], m[2][2])
                rot = [x, y, z]
                xform = setMatrixPosition(t, self.locsPos[i])
                xform = setMatrixRotation(xform, rot)
                offset = datatypes.EulerRotation((90.0, 0, 0), unit="degrees")
                xform = offset.asMatrix() * xform
     
                if mirror:
                    if lower:
                        xform = setMatrixScale(xform, scl=[1, -1, -1])
                    else:
                        xform = setMatrixScale(xform, scl=[-1, 1, 1])
     
                else:
                    if lower:
                        xform = setMatrixScale(xform, scl=[-1, -1, -1])
                    else:
                        xform = setMatrixScale(xform, scl=[1, 1, 1])
     
                # if i == self.left_index:
                #     prev = getTransform(controls[i-1]).rotate
                #     xform = setMatrixRotation(xform, prev)
                if i == self.right_index + 1:
                    rightCtl = controls[self.right_index]
                    rightNpo = rightCtl.getParent()
                    pos = cmds.xform(rightNpo.fullPath(), q=True, ws=True, translation=True)
                    pm.xform(rightNpo, ws=True, matrix=xform)
                    pm.xform(rightNpo, ws=True, translation=pos)
     
                npo_name = self.getName("rope_{}_jnt_npo".format(_index))
                npo = addTransform(cns, npo_name, xform)
     
                t = getTransform(npo)
                ctl = self.addCtl(
                    npo,
                    "%s_crvdetail" % _index,
                    t,
                    color,
                    icon_shape,
                    w=wd,
                    d=wd,
                    ro=datatypes.Vector(1.57079633, 0, 0),
                    po=po
                )
     
                controls.append(ctl)
     
                # getting joint parent
                # jnt = rigbits.addJnt(npo, noReplace=True, parent=self.j_parent)
                self.jnt_pos.append([ctl, "{}".format(i)])
                self.addToSubGroup(ctl, self.detailControllersGroupName)

        return controls

    def addToSubGroup(self, obj, group_name):

        if self.settings["ctlGrp"]:
            ctlGrp = self.settings["ctlGrp"]
        else:
            ctlGrp = "controllers"

        self.addToGroup(obj, group_name, parentGrp=ctlGrp)

    def addControllers(self):

        paramsMain = ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "ro"]
        paramsSub = ["tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "ro"]
        paramsSub = ["tx", "ty", "tz"]

        ctlOptions = [
            # name,      side, icon,   color, width, keyable
            ["upper",    "C", "square", 4,  .05, paramsMain],  # 0
            ["upInner",  "L", "circle", 14, .03, paramsSub],         # 1
            ["upOuter",  "L", "circle", 14, .03, paramsSub],         # 2
            ["corner",   "L", "square", 4,  .05, paramsMain],  # 3
            ["lowOuter", "L", "circle", 14, .03, paramsSub],         # 4
            ["lowInner", "L", "circle", 14, .03, paramsSub],         # 5
            ["lower",    "C", "square", 4,  .05, paramsMain],  # 6
            ["lowInner", "R", "circle", 14, .03, paramsSub],         # 7
            ["lowOuter", "R", "circle", 14, .03, paramsSub],         # 8
            ["corner",   "R", "square", 4,  .05, paramsMain],  # 9
            ["upOuter",  "R", "circle", 14, .03, paramsSub],         # 10
            ["upInner",  "R", "circle", 14, .03, paramsSub],         # 11
        ]

        self.upNpos, self.upCtls = self._addControls(self.crv_ctl, ctlOptions)

        self.lips_C_upper_ctl  = self.upCtls[0]
        self.lips_C_lower_ctl  = self.upCtls[6]

        self.lips_L_Corner_npo = self.upNpos[3]
        self.lips_R_Corner_npo = self.upNpos[9]

        # Connecting control crvs with controls
        curve.gear_curvecns_op_local_skip_rotate(self.crv_ctl, self.upCtls)

        # adding wires
        w1 = pm.wire(self.crv, w=self.crv_ctl, dropoffDistance=[0, self.size * 10])[0]
        w2 = pm.wire(self.rope, w=self.crv_ctl, dropoffDistance=[0, self.size * 10])[0]

        cmds.setAttr(w1.name() + ".rotation", 0.0)
        cmds.setAttr(w2.name() + ".rotation", 0.0)

    def addConstraints(self):

        def applyMultiCns(ctls, src1Index, src2Index, dstIndex, p1, p2):

            src1 = ctls[src1Index]
            src2 = ctls[src2Index]
            dst = ctls[dstIndex]

            src1Path = src1.fullPath()
            src2Path = src2.fullPath()
            dstPath = ctls[dstIndex].getParent().fullPath()

            r2, r1 = calcDistRatio(src1, src2, dst)

            cns_node = cmds.parentConstraint(src1Path, src2Path, dstPath, mo=True, skipRotate=("x", "y", "z"))[0]  # type: str
            attr1 = cns_node + "." + src1.name().split("|")[-1] + "W0"
            attr2 = cns_node + "." + src2.name().split("|")[-1] + "W1"

            cmds.setAttr(attr1, (r1 * 0.4) + (p1 * 0.6))
            cmds.setAttr(attr2, (r2 * 0.4) + (p2 * 0.6))

        def calcDistRatio(a, b, c):
            pa = a.getTranslation(space="world")
            pb = b.getTranslation(space="world")
            pc = c.getTranslation(space="world")

            d1 = abs((pa- pc).length())
            d2 = abs((pb- pc).length())

            r1 = d1 / (d1 + d2)
            r2 = 1.0 - abs(r1)

            return r1, r2

        # if 8 locs, : up is 0, left is 2, bottom is 4, right is 6
        applyMultiCns(self.upCtls, 0, 3, 1,  0.70, 0.10)
        applyMultiCns(self.upCtls, 0, 3, 2,  0.70, 0.15)

        applyMultiCns(self.upCtls, 3, 6, 4,  0.20, 0.80)
        applyMultiCns(self.upCtls, 3, 6, 5,  0.20, 0.80)

        applyMultiCns(self.upCtls, 6, 9, 7,  0.80, 0.20)
        applyMultiCns(self.upCtls, 6, 9, 8,  0.80, 0.20)

        applyMultiCns(self.upCtls, 9, 0, 10, 0.10, 0.70)
        applyMultiCns(self.upCtls, 9, 0, 11, 0.15, 0.70)

        self._constrainCtlRotToCurve(self.upCtls, self.crv)

    def _addControls(self, crv_ctl, option):

        cvs = self.getCurveCVs(crv_ctl)

        center_pos = sum(cvs) / len(cvs)  # type: ignore
        total_dist = sum([(x - center_pos).length() for x in cvs])
        average_dist = total_dist / len(cvs)

        distSize = average_dist * 5.0

        npos = []
        ctls = []

        for i, cv in enumerate(cvs):

            mirror = i > (len(cvs) / 2)
            lower = i > 3 and i < 9

            oName  = option[i][0]
            oSide  = option[i][1]
            o_icon = option[i][2]
            color  = option[i][3]
            wd     = option[i][4]
            oPar   = option[i][5]

            scl = [1, 1, 1]
            if mirror:
                scl[0] = -1
            if lower:
                scl[1] = -1

            t = transform.getTransformFromPos(cv)
            t = transform.setMatrixScale(t, scl)

            with ymt_util.overrideNamingAttributeTemporary(self, side=oSide):
                npo = addTransform(self.ctl_root, self.getName("%s_npo" % oName), t)
                npos.append(npo)

                ctl = self.addCtl(
                    npo,
                    oName,
                    t,
                    color,
                    o_icon,
                    w=wd * distSize,
                    d=wd * distSize,
                    ro=datatypes.Vector(1.57079633, 0, 0),
                    po=datatypes.Vector(0, 0, .07 * distSize),
                )

                ctls.append(ctl)
                ymt_util.setKeyableAttributesDontLockVisibility(ctl, oPar)
                self.addToSubGroup(ctl, self.primaryControllersGroupName)

        return npos, ctls

    def _constrainCtlRotToCurve(self, ctls, crv): 

        # for i, cv in enumerate(cvs):
        for i in (1, 2, 4, 5, 7, 8, 10, 11):
            crvShape = crv.getShape().fullPath()

            ctl = ctls[i]
            dm_node = ymt_util.getDecomposeMatrixOfAtoB(ctl, crv, skip_last=True)

            point = cmds.createNode("nearestPointOnCurve")
            cmds.connectAttr(dm_node + ".outputTranslate", point + ".inPosition")
            cmds.connectAttr(crvShape + ".local", point + ".inputCurve")

            uvalue = cmds.getAttr(point + ".parameter")
            cmds.delete(point)
            # cmds.delete(dm_node.fullPath())

            motPath = cmds.createNode("motionPath")
            cmds.setAttr(motPath + ".uValue", uvalue)
            cmds.setAttr(motPath + ".frontAxis", 0)
            cmds.setAttr(motPath + ".upAxis", 1)
            cmds.setAttr(motPath + ".worldUpType", 3)  # vector
            cmds.setAttr(motPath + ".worldUpVector", 0, 1, 0)
            cmds.connectAttr(crvShape + ".local", motPath + ".geometryPath")

            mirror = i > 6
            lower = 3 < i and i < 9
            outpath = motPath + ".rotateZ"

            if lower:
                cmds.setAttr(motPath + ".inverseFront", 1)

                if not mirror:
                    mul = cmds.createNode("multDoubleLinear")
                    cmds.connectAttr(motPath + ".rotateZ", mul + ".input1")
                    cmds.setAttr(mul + ".input2", -1)
                    outpath = mul + ".output"

            else:
                cmds.setAttr(motPath + ".inverseFront", 0)

                if mirror:
                    mul = cmds.createNode("multDoubleLinear")
                    cmds.connectAttr(motPath + ".rotateZ", mul + ".input1")
                    cmds.setAttr(mul + ".input2", -1)
                    outpath = mul + ".output"

            # Inserting an orient constraint node in between because
            # dagPose command cannot be applied when connected dilectly to the output
            cmds.setAttr("{}.rotateZ".format(ctl), lock=False)
            oriCns = cmds.createNode("orientConstraint")
            cmds.parent(oriCns, ctl.fullPath(), relative=True)
            cmds.connectAttr(outpath, oriCns + ".target[0].targetRotateZ")
            cmds.connectAttr(oriCns + ".constraintRotateZ", ctl + ".rotateZ")
            cmds.setAttr("{}.rotateZ".format(ctl), lock=True)

    # =====================================================
    # ATTRIBUTES
    # =====================================================
    def addAttributes(self):
        """Create the anim and setupr rig attributes for the component"""

        pass
        # if not self.settings["ui_host"]:
        #     self.uihost = self.over_ctl

    # =====================================================
    # OPERATORS
    # =====================================================
    def addOperators(self):
        """Create operators and set the relations for the component rig

        Apply operators, constraints, expressions to the hierarchy.
        In order to keep the code clean and easier to debug,
        we shouldn't create any new object in this method.

        """
        pass

    # =====================================================
    # CONNECTOR
    # =====================================================
    def addConnection(self):
        self.connections["mouth_01"] = self.connect_mouth
        self.connections["lip_01"] = self.connect_mouth
        self.connections["standard"] = self.connect_mouth

    def connect_mouth(self):

        if self.parent is None:
            return

        if self.surfRef:
            ref = self.rig.findComponent(self.surfRef)
            self.sliding_surface = ref.sliding_surface

        self.parent.addChild(self.root)

        try:
            self.connect_ghosts()
        except:
            traceback.print_exc()
            raise

    def connect_standard(self):
        self.parent.addChild(self.root)
        if self.surfRef:
            ref = self.rig.findComponent(self.surfRef)
            self.sliding_surface = ref.sliding_surface

    def connect_ghosts(self):

        lipup_ref = self.parent_comp.lipup_ctl
        liplow_ref = self.parent_comp.liplow_ctl

        slide_c_ref = self.rig.findRelative(self.mouthCenterRef)
        corner_l_ref = self.rig.findRelative(self.mouthLeftRef)
        corner_r_ref = self.rig.findRelative(self.mouthRightRef)

        slide_c_comp = self.rig.findComponent(self.mouthCenterRef)
        corner_l_comp = self.rig.findComponent(self.mouthLeftRef)
        corner_r_comp = self.rig.findComponent(self.mouthRightRef)

        if slide_c_comp.root.parent(0) != self.parent:
            self.parent.addChild(slide_c_comp.root)

        if corner_l_comp.root.parent(0) != self.parent:
            self.parent.addChild(corner_l_comp.root)

        if corner_r_comp.root.parent(0) != self.parent:
            self.parent.addChild(corner_r_comp.root)

        # create interpose lvl for the ctl
        intTra = rigbits.createInterpolateTransform([lipup_ref, liplow_ref], blend=0.38)
        pm.rename(intTra, intTra.name() + "_int")

        drivers = self.connect_slide_ghost(
            intTra,
            slide_c_ref,
            corner_l_ref,
            corner_r_ref
        )
        self.connect_mouth_ghost(lipup_ref, liplow_ref)

        pm.parent(corner_l_comp.ik_cns, self.mouthSlide_ctl)
        pm.parent(corner_r_comp.ik_cns, self.mouthSlide_ctl)

        pm.parent(drivers[0], slide_c_comp.ik_cns)
        pm.parent(drivers[1], corner_l_comp.ik_cns)
        pm.parent(drivers[2], corner_r_comp.ik_cns)

        # remove elements from controllers group
        for comp in [slide_c_comp, corner_l_comp, corner_r_comp]:
            for k, v in comp.groups.items():
                if "componentsRoots" in k:
                    continue

                comp.groups[k] = []

    def _createGhostCtl(self, ghost_ctl, parent):

        ctl = ghost.createGhostCtl(ghost_ctl, parent=parent, connect=True)
        # rigbits.connectLocalTransform([ctl, ghost_ctl])
        ctl.attr("isCtl") // ghost_ctl.attr("isCtl")
        ctl.attr("isCtl").set(True)
        ghost_ctl.attr("isCtl").set(False)

        shape = ghost_ctl.getShape()
        if shape:
            _visi_off_lock(shape)

        shape = ctl.getShape()
        if shape:
            ctl.getShape().visibility.set(True)

        if self.settings["ctlGrp"]:
            ctlGrp = self.settings["ctlGrp"]
            self.addToGroup(ctl, ctlGrp, "controllers")

        else:
            ctlGrp = "controllers"
            self.addToGroup(ctl, ctlGrp)

        if ctlGrp not in self.groups.keys():
            self.groups[ctlGrp] = []

        self._removeFromCtrlGroup(ghost_ctl)
        self.addToSubGroup(ctl, self.primaryControllersGroupName)

        return ctl

    def _removeFromCtrlGroup(self, obj):

        if self.settings["ctlGrp"]:
            ctlGrp = self.settings["ctlGrp"]

        else:
            ctlGrp = "controllers"

        if ctlGrp not in self.groups.keys():
            return

        for grp_name, grp in self.groups.items():
            try:  # noqa: FURB107
                grp.remove(obj)
            except ValueError:
                pass

    def connect_slide_ghost(self, intTra, slide_c_ref, corner_l_ref, corner_r_ref):

        # create ghost controls
        self.mouthSlide_ctl = self._createGhostCtl(slide_c_ref, intTra)
        self.cornerL_ctl = self._createGhostCtl(corner_l_ref, slide_c_ref)
        self.cornerR_ctl = self._createGhostCtl(corner_r_ref, slide_c_ref)
        self.jnt_pos.insert(0, [self.mouthSlide_ctl, "slide_c"])

        # slide system
        drivers = ghostSliderForMouth(
            [slide_c_ref, corner_l_ref, corner_r_ref],
            intTra,
            self.sliding_surface,
            self.sliding_surface.getParent()
        )

        # connect scale
        pm.connectAttr(self.mouthSlide_ctl.scale, slide_c_ref.scale)
        pm.connectAttr(self.cornerL_ctl.scale, corner_l_ref.scale)
        pm.connectAttr(self.cornerR_ctl.scale, corner_r_ref.scale)

        # connect pucker
        cmds.setAttr("{}.tz".format(slide_c_ref.name()), l=False)
        pm.connectAttr(self.mouthSlide_ctl.tz, slide_c_ref.tz)

        pm.parentConstraint(corner_l_ref, self.lips_L_Corner_npo, mo=True)
        pm.parentConstraint(corner_r_ref, self.lips_R_Corner_npo, mo=True)

        ymt_util.setKeyableAttributesDontLockVisibility(slide_c_ref, [])
        ymt_util.setKeyableAttributesDontLockVisibility(corner_l_ref, [])
        ymt_util.setKeyableAttributesDontLockVisibility(corner_r_ref, [])

        return drivers

    def connect_mouth_ghost(self, lipup_ref, liplow_ref):

        # center main controls
        self.lips_C_upper_ctl, up_ghost_ctl = createGhostWithParentConstraint(self.lips_C_upper_ctl, lipup_ref)
        self.lips_C_lower_ctl, lo_ghost_ctl = createGhostWithParentConstraint(self.lips_C_lower_ctl, liplow_ref)

        self._removeFromCtrlGroup(up_ghost_ctl)
        self._removeFromCtrlGroup(lo_ghost_ctl)
        self.addToSubGroup(self.lips_C_upper_ctl, self.primaryControllersGroupName)
        self.addToSubGroup(self.lips_C_lower_ctl, self.primaryControllersGroupName)

        # add slider offset
        s = self.mouthSlide_ctl.name()
        up_npo = rigbits.addNPO(self.lips_C_upper_ctl)[0].name()
        low_npo = rigbits.addNPO(self.lips_C_lower_ctl)[0].name()

        pm.connectAttr(s + ".translate", up_npo + ".translate", force=True)
        pm.connectAttr(s + ".scale", up_npo + ".scale", force=True)
        pm.connectAttr(s + ".rotate", up_npo + ".rotate", force=True)

        r = pm.createNode("multiplyDivide")
        pm.setAttr(r + ".input2Y", -1)
        pm.connectAttr(s + ".translateY", r + ".input1Y", force=True)
        pm.connectAttr(r + ".outputY",    low_npo + ".translateY", force=True)
        pm.connectAttr(s + ".translateX", low_npo + ".translateX", force=True)
        pm.connectAttr(s + ".translateZ", low_npo + ".translateZ", force=True)
        pm.connectAttr(s + ".scale", low_npo + ".scale", force=True)
        for axis in ("X", "Y", "Z"):
            inv = cmds.createNode("multiplyDivide")
            cmds.setAttr(inv + ".input2" + axis, -1)
            cmds.connectAttr(
                s + ".rotate" + axis,
                inv + ".input1" + axis
            )
            cmds.connectAttr(
                inv + ".output" + axis,
                low_npo + ".rotate" + axis
            )

        return

    def connect_averageParentCns(self, parents, target):
        """
        Connection definition using average parent constraint.
        """

        if len(parents) == 1:
            pm.parent(parents[0], target)

        else:
            parents.append(target)
            cns_node = pm.parentConstraint(*parents, maintainOffset=True)
            cns_attr = pm.parentConstraint(
                cns_node, query=True, weightAliasList=True)

            for i, attr in enumerate(cns_attr):
                pm.setAttr(attr, 1.0)

    def setRelation(self):
        """Set the relation beetween object from guide to rig"""

        self.relatives["root"] = self.root
        for i, ctl in enumerate(self.tweakControllers):

            self.relatives["%s_loc" % i] = ctl
            self.controlRelatives["%s_loc" % i] = ctl


def draw_eye_guide_mesh_plane(points, t):
    # type: (Tuple[float, float, float], datatypes.MMatrix) -> om.MFnMesh

    mesh = om.MFnMesh()

    points = [x - t.getTranslation(space="world") for x in points]
    # points = [x - t.getTranslation(space="world") for x in points]

    mean_x = sum(p[0] for p in points) / len(points)
    mean_y = sum(p[1] for p in points) / len(points)
    mean_z = sum(p[2] for p in points) / len(points)
    mean = (mean_x, mean_y, mean_z)

    # Simple unitCube coordinates
    vertices = [om.MPoint(mean), ]
    polygonCounts = []
    polygonConnects = []

    for i, p in enumerate(points):
        vertices.append(om.MPoint(p))    # 0

        if 1 < i:
            polygonCounts.append(3)
            polygonConnects.append(i)
            polygonConnects.append(i - 1)
            polygonConnects.append(0)

        if len(points) == (i + 1):
            polygonCounts.append(3)
            polygonConnects.append(i + 1)
            polygonConnects.append(i)
            polygonConnects.append(0)

            polygonCounts.append(3)
            polygonConnects.append(1)
            polygonConnects.append(i + 1)
            polygonConnects.append(0)

    mesh_obj = mesh.create(vertices, polygonCounts, polygonConnects)
    mesh_trans = om.MFnTransform(mesh_obj)
    n = pm.PyNode(mesh_trans.name())
    v = t.getTranslation(space="world")
    n.setTranslation(v, om.MSpace.kWorld)

    return mesh


def ghostSliderForMouth(ghostControls, intTra, surface, sliderParent):
    """Modify the ghost control behaviour to slide on top of a surface

    Args:
        ghostControls (dagNode): The ghost control
        surface (Surface): The NURBS surface
        sliderParent (dagNode): The parent for the slider.
    """
    if not isinstance(ghostControls, list):
        ghostControls = [ghostControls]


    def conn(ctl, driver, ghost):

        for attr in ["translate", "scale", "rotate"]:
            pm.connectAttr("{}.{}".format(ctl, attr), "{}.{}".format(driver, attr))
            pm.disconnectAttr("{}.{}".format(ctl, attr), "{}.{}".format(ghost, attr))

    def connCenter(ctl, driver, ghost):
        dm_node = ymt_util.getDecomposeMatrixOfAtoB(ctl, driver, skip_last=True)

        for attr in ["translate", "scale"]:
            pm.connectAttr("{}.output{}".format(dm_node, attr.capitalize()), "{}.{}".format(driver, attr))
            pm.disconnectAttr("{}.{}".format(ctl, attr), "{}.{}".format(ghost, attr))

    surfaceShape = surface.getShape()
    sliders = []
    drivers = []

    for i, ctlGhost in enumerate(ghostControls):
        ctl = pm.listConnections(ctlGhost, t="transform")[-1]
        t = ctl.getMatrix(worldSpace=True)

        gDriver = primitive.addTransform(surface.getParent(), "{}_slideDriver".format(ctl.name()), t)
        drivers.append(gDriver)

        if 0 == i:
            connCenter(ctl, gDriver, ctlGhost)

        else:
            conn(ctl, gDriver, ctlGhost)

        oParent = ctlGhost.getParent()
        npoName = "_".join(ctlGhost.name().split("_")[:-1]) + "_npo"
        oTra = pm.PyNode(pm.createNode("transform", n=npoName, p=oParent, ss=True))
        oTra.setTransformation(ctlGhost.getMatrix())
        pm.parent(ctlGhost, oTra)

        slider = primitive.addTransform(sliderParent, ctl.name() + "_slideDriven", t)
        sliders.append(slider)

        # connexion
        if 0 == i:
            dm_node = node.createDecomposeMatrixNode(gDriver.attr("matrix"))

        else:
            dm_node = ymt_util.getDecomposeMatrixOfAtoB(ctl, slider, skip_last=True)

        cps_node = pm.createNode("closestPointOnSurface")
        dm_node.attr("outputTranslate") >> cps_node.attr("inPosition")
        surfaceShape.attr("local") >> cps_node.attr("inputSurface")
        cps_node.attr("position") >> slider.attr("translate")

        pm.normalConstraint(surfaceShape,
                            slider,
                            aimVector=[0, 0, 1],
                            upVector=[0, 1, 0],
                            worldUpType="objectrotation",
                            worldUpVector=[0, 1, 0],
                            worldUpObject=gDriver)

        pm.parent(ctlGhost.getParent(), slider)
        ymt_util.setKeyableAttributesDontLockVisibility(slider, [])
        # for shape in ctlGhost.getShapes():
        #     pm.delete(shape)

    for slider in sliders[1:]:
        _visi_off_lock(slider)

    return drivers


def createGhostWithParentConstraint(ctl, parent=None, connect=True):
    """Create a duplicated Ghost control

    Create a duplicate of the control and rename the original with _ghost.
    Later connect the local transforms and the Channels.
    This is useful to connect local rig controls with the final rig control.

    Args:
        ctl (dagNode): Original Control to duplicate
        parent (dagNode): Parent for the new created control

    Returns:
       pyNode: The new created control

    """
    if isinstance(ctl, (six.string_types, six.text_type)):
        ctl = pm.PyNode(ctl)

    if parent:
        if isinstance(parent, (six.string_types, six.text_type)):
            parent = pm.PyNode(parent)

    grps = ctl.listConnections(t="objectSet")
    for grp in grps:
        grp.remove(ctl)
    oName = ctl.name()
    pm.rename(ctl, oName + "_ghost")
    newCtl = pm.duplicate(ctl, po=True)[0]
    pm.rename(newCtl, oName)
    source2 = pm.duplicate(ctl)[0]
    for shape in source2.getShapes():
        pm.parent(shape, newCtl, r=True, s=True)
        pm.rename(shape, newCtl.name() + "Shape")
        pm.parent(shape, newCtl, r=True, s=True)
    pm.delete(source2)
    if parent:
        pm.parent(newCtl, parent)
        oTra = pm.createNode("transform",
                             n=newCtl.name() + "_npo",
                             p=parent, ss=True)
        oTra.setMatrix(ctl.getParent().getMatrix(worldSpace=True),
                       worldSpace=True)
        pm.parent(newCtl, oTra)
    if connect:
        pm.parentConstraint(newCtl, ctl, mo=True)
        # rigbits.connectLocalTransform([newCtl, ctl])
        rigbits.connectUserDefinedChannels(newCtl, ctl)
    for grp in grps:
        grp.add(newCtl)

    # add control tag
    node.add_controller_tag(newCtl, parent)
    for shape in ctl.getShapes():
        pm.delete(shape)

    return newCtl, ctl


def applyPathCnsLocal(target, ctl_curve, rope, cv):

    def _searchNearestEditPoint(curve, cv):

        candidate = math.inf
        index = 0
        numberOfSpans = cmds.getAttr(curve + ".spans")

        for i in range(numberOfSpans):
            point = cmds.getAttr(curve + ".editPoints["+str(i)+"]")[0]
            dist = math.sqrt((point[0] - cv[0])**2 + (point[1] - cv[1])**2 + (point[2] - cv[2])**2)
            if dist < candidate:
                candidate = dist
                index = i

        return index

    nearestIndex = _searchNearestEditPoint(rope, cv)

    nearestPointOnCurve = cmds.createNode("nearestPointOnCurve")
    cmds.connectAttr(rope+ ".editPoints["+str(nearestIndex)+"]", nearestPointOnCurve + ".inPosition")
    cmds.connectAttr(rope + ".local", nearestPointOnCurve + ".inputCurve")

    motionPath = cmds.createNode("motionPath")
    cmds.connectAttr(nearestPointOnCurve + ".parameter", motionPath + ".uValue")
    cmds.connectAttr(rope + ".local", motionPath + ".geometryPath")

    cmds.setAttr(motionPath + ".fractionMode", 0)
    cmds.setAttr(motionPath + ".frontAxis", 0)

    comp_node = cmds.createNode("composeMatrix")
    cmds.connectAttr(motionPath + ".rotate", comp_node + ".inputRotate")
    cmds.connectAttr(motionPath + ".rotateOrder", comp_node + ".inputRotateOrder")
    cmds.connectAttr(nearestPointOnCurve + ".position", comp_node + ".inputTranslate")

    cmds.connectAttr(nearestPointOnCurve + ".position", target.fullPath() + ".translate")
    cmds.connectAttr(motionPath + ".rotate", target.fullPath() + ".rotate")


def _visi_off_lock(node):
    """Short cuts."""
    if not node:
        raise Exception("node is null")

    cmds.setAttr("{}.visibility".format(node.name()), l=False)
    node.visibility.set(False)
    try:
        ymt_util.setKeyableAttributesDontLockVisibility(node, [])
    except:
        pass
