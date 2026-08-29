# -*- coding: utf-8 -*-
import maya.cmds as cmds
import importlib
try:
    pm = importlib.import_module("mgear.pymaya")
except ImportError:
    pm = importlib.import_module("pymel.core")

from mgear import rigbits
import mgear.shifter.custom_step as cstp


class CustomShifterStep(cstp.customShifterMainStep):

    # No annotations here: mgear 4.x runStep inspects __init__ with
    # inspect.getargspec, which raises ValueError on annotated functions.
    def __init__(self):
        self.name = "Sknning Surface"

    def run(self, stepDict: dict[str, object]) -> None:
        self.deformers = [
            "headBend_C0_0_jnt",
            "headBend_C1_0_jnt",
            "eye_L0_base_jnt",
            "eye_R0_base_jnt",
            "headBend_C2_0_jnt",
            "headBend_C3_0_jnt",
            "mouth_C0_jaw_jnt",
            "forehead_C0_0_jnt",
            # "zygoma_L0_0_jnt",
            # "zygoma_R0_0_jnt",
        ]
        self.surfaces = self.find_surfaces()
        self.skinning()

    def find_surfaces(self) -> list[str]:
        # surfaces = []

        return cmds.ls("surface_C0_surface")

    def skinning(self) -> None:
        cmds.select(self.deformers)
        skin = self.skin = cmds.skinCluster(
            self.deformers,
            self.surfaces,
            toSelectedBones=True,
            # skinMethod=1,
            bindMethod=1,
            smoothWeights=0.5,
        )[0]

        cmds.setAttr("{}.relativeSpaceMode".format(skin), 1)  # local skinning

        # cmds.deformer(type="deltaMush")
