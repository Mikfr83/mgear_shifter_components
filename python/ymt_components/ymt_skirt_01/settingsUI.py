"""Qt settings UI for ymt_skirt_01."""

from mgear.core import pyqt as gqt

QtGui, QtCore, QtWidgets, wrapInstance = gqt.qt_import()


class Ui_Form(object):
    def _ring_scale_spin_box(self) -> QtWidgets.QDoubleSpinBox:
        spin_box = QtWidgets.QDoubleSpinBox(self.groupBox)
        spin_box.setDecimals(3)
        spin_box.setMinimum(0.001)
        spin_box.setMaximum(100.0)
        spin_box.setSingleStep(0.05)
        return spin_box

    def _unit_spin_box(self) -> QtWidgets.QDoubleSpinBox:
        spin_box = QtWidgets.QDoubleSpinBox(self.groupBox)
        spin_box.setDecimals(2)
        spin_box.setMinimum(0.0)
        spin_box.setMaximum(1.0)
        spin_box.setSingleStep(0.05)
        return spin_box

    def setupUi(self, Form: QtWidgets.QWidget) -> None:
        Form.setObjectName("Form")
        Form.resize(300, 470)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.groupBox = QtWidgets.QGroupBox(Form)
        self.mainLayout = QtWidgets.QVBoxLayout(self.groupBox)
        self.formLayout = QtWidgets.QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.rows_label = QtWidgets.QLabel(self.groupBox)
        self.rows_spinBox = QtWidgets.QSpinBox(self.groupBox)
        self.rows_spinBox.setMinimum(2)
        self.rows_spinBox.setMaximum(100)
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.rows_label)
        self.formLayout.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.rows_spinBox)

        self.cols_label = QtWidgets.QLabel(self.groupBox)
        self.cols_spinBox = QtWidgets.QSpinBox(self.groupBox)
        self.cols_spinBox.setMinimum(3)
        self.cols_spinBox.setMaximum(128)
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.cols_label)
        self.formLayout.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.cols_spinBox)

        self.rebuildGrid_pushButton = QtWidgets.QPushButton(self.groupBox)
        self.formLayout.setWidget(2, QtWidgets.QFormLayout.SpanningRole, self.rebuildGrid_pushButton)

        self.ctlSize_label = QtWidgets.QLabel(self.groupBox)
        self.ctlSize_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.ctlSize_doubleSpinBox.setDecimals(3)
        self.ctlSize_doubleSpinBox.setMinimum(0.001)
        self.ctlSize_doubleSpinBox.setMaximum(100.0)
        self.ctlSize_doubleSpinBox.setSingleStep(0.1)
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.ctlSize_label)
        self.formLayout.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.ctlSize_doubleSpinBox)

        self.addJoints_checkBox = QtWidgets.QCheckBox(self.groupBox)
        self.formLayout.setWidget(4, QtWidgets.QFormLayout.FieldRole, self.addJoints_checkBox)

        self.postCollision_checkBox = QtWidgets.QCheckBox(self.groupBox)
        self.formLayout.setWidget(14, QtWidgets.QFormLayout.FieldRole, self.postCollision_checkBox)

        self.wave_checkBox = QtWidgets.QCheckBox(self.groupBox)
        self.formLayout.setWidget(15, QtWidgets.QFormLayout.FieldRole, self.wave_checkBox)

        self.rebuildSpansV_label = QtWidgets.QLabel(self.groupBox)
        self.rebuildSpansV_spinBox = QtWidgets.QSpinBox(self.groupBox)
        self.rebuildSpansV_spinBox.setMinimum(1)
        self.rebuildSpansV_spinBox.setMaximum(256)
        self.formLayout.setWidget(16, QtWidgets.QFormLayout.LabelRole, self.rebuildSpansV_label)
        self.formLayout.setWidget(16, QtWidgets.QFormLayout.FieldRole, self.rebuildSpansV_spinBox)

        self.tightness_label = QtWidgets.QLabel(self.groupBox)
        self.tightness_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.tightness_doubleSpinBox.setDecimals(3)
        self.tightness_doubleSpinBox.setMinimum(0.0)
        self.tightness_doubleSpinBox.setMaximum(1.0)
        self.tightness_doubleSpinBox.setSingleStep(0.05)
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.LabelRole, self.tightness_label)
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.FieldRole, self.tightness_doubleSpinBox)

        self.falloff_label = QtWidgets.QLabel(self.groupBox)
        self.falloff_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.falloff_doubleSpinBox.setDecimals(3)
        self.falloff_doubleSpinBox.setMinimum(-1.0)
        self.falloff_doubleSpinBox.setMaximum(1.0)
        self.falloff_doubleSpinBox.setSingleStep(0.05)
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.LabelRole, self.falloff_label)
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.FieldRole, self.falloff_doubleSpinBox)

        self.smoothness_label = QtWidgets.QLabel(self.groupBox)
        self.smoothness_doubleSpinBox = self._unit_spin_box()
        self.formLayout.setWidget(7, QtWidgets.QFormLayout.LabelRole, self.smoothness_label)
        self.formLayout.setWidget(7, QtWidgets.QFormLayout.FieldRole, self.smoothness_doubleSpinBox)

        self.follow_label = QtWidgets.QLabel(self.groupBox)
        self.follow_doubleSpinBox = self._unit_spin_box()
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.LabelRole, self.follow_label)
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.FieldRole, self.follow_doubleSpinBox)

        self.ringPositions_label = QtWidgets.QLabel(self.groupBox)
        self.ringPositions_lineEdit = QtWidgets.QLineEdit(self.groupBox)
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.LabelRole, self.ringPositions_label)
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.FieldRole, self.ringPositions_lineEdit)

        self.ringScaleX_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleX_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.LabelRole, self.ringScaleX_label)
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.FieldRole, self.ringScaleX_doubleSpinBox)

        self.ringScaleY_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleY_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(11, QtWidgets.QFormLayout.LabelRole, self.ringScaleY_label)
        self.formLayout.setWidget(11, QtWidgets.QFormLayout.FieldRole, self.ringScaleY_doubleSpinBox)

        self.ringScaleZ_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleZ_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(12, QtWidgets.QFormLayout.LabelRole, self.ringScaleZ_label)
        self.formLayout.setWidget(12, QtWidgets.QFormLayout.FieldRole, self.ringScaleZ_doubleSpinBox)

        self._setup_leg_profile()
        self.mainLayout.addLayout(self.formLayout)
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)
        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def _setup_leg_profile(self) -> None:
        self.legProfile_groupBox = QtWidgets.QGroupBox(self.groupBox)
        layout = QtWidgets.QFormLayout(self.legProfile_groupBox)
        for station in ("thigh", "knee", "calf", "ankle"):
            row = QtWidgets.QHBoxLayout()
            for axis in ("X", "Z"):
                row.addWidget(QtWidgets.QLabel(axis, self.legProfile_groupBox))
                spin_box = self._ring_scale_spin_box()
                # Fitted ratios are unbounded above; a clamped widget would hide the guide value.
                spin_box.setMaximum(10000.0)
                setattr(self, station + "Radius" + axis + "_doubleSpinBox", spin_box)
                row.addWidget(spin_box)
            layout.addRow(gqt.fakeTranslate("Form", station.title(), None, -1), row)
        for station in ("thigh", "calf"):
            spin_box = self._unit_spin_box()
            spin_box.setDecimals(4)
            setattr(self, station + "Position_doubleSpinBox", spin_box)
            layout.addRow(gqt.fakeTranslate("Form", station.title() + " Position", None, -1), spin_box)
        self.profileMesh_lineEdit = QtWidgets.QLineEdit(self.legProfile_groupBox)
        layout.addRow(gqt.fakeTranslate("Form", "Body mesh", None, -1), self.profileMesh_lineEdit)
        self.useSelection_pushButton = QtWidgets.QPushButton(self.legProfile_groupBox)
        self.fitProfile_pushButton = QtWidgets.QPushButton(self.legProfile_groupBox)
        layout.addRow(self.useSelection_pushButton)
        layout.addRow(self.fitProfile_pushButton)
        self.formLayout.setWidget(13, QtWidgets.QFormLayout.SpanningRole, self.legProfile_groupBox)

    def retranslateUi(self, Form: QtWidgets.QWidget) -> None:
        Form.setWindowTitle(gqt.fakeTranslate("Form", "Form", None, -1))
        self.groupBox.setTitle(gqt.fakeTranslate("Form", "Skirt Grid", None, -1))
        self.rows_label.setText(gqt.fakeTranslate("Form", "Rows", None, -1))
        self.cols_label.setText(gqt.fakeTranslate("Form", "Columns", None, -1))
        self.rebuildGrid_pushButton.setText(gqt.fakeTranslate("Form", "Rebuild Grid Locators", None, -1))
        self.ctlSize_label.setText(gqt.fakeTranslate("Form", "Ctl Size", None, -1))
        self.addJoints_checkBox.setText(gqt.fakeTranslate("Form", "Add Joints", None, -1))
        self.postCollision_checkBox.setText(gqt.fakeTranslate("Form", "Post Collision (2nd pass)", None, -1))
        self.wave_checkBox.setText(gqt.fakeTranslate("Form", "Wave (deterministic oscillator)", None, -1))
        self.rebuildSpansV_label.setText(gqt.fakeTranslate("Form", "Surface Spans V", None, -1))
        self.tightness_label.setText(gqt.fakeTranslate("Form", "Tightness", None, -1))
        self.falloff_label.setText(gqt.fakeTranslate("Form", "Falloff", None, -1))
        self.smoothness_label.setText(gqt.fakeTranslate("Form", "Smoothness", None, -1))
        self.follow_label.setText(gqt.fakeTranslate("Form", "Follow", None, -1))
        self.ringPositions_label.setText(gqt.fakeTranslate("Form", "Ring Positions", None, -1))
        self.ringScaleX_label.setText(gqt.fakeTranslate("Form", "Ring Scale X", None, -1))
        self.ringScaleY_label.setText(gqt.fakeTranslate("Form", "Ring Scale Y", None, -1))
        self.ringScaleZ_label.setText(gqt.fakeTranslate("Form", "Ring Scale Z", None, -1))
        self.legProfile_groupBox.setTitle(gqt.fakeTranslate("Form", "Leg profile", None, -1))
        self.useSelection_pushButton.setText(gqt.fakeTranslate("Form", "Use selection", None, -1))
        self.fitProfile_pushButton.setText(gqt.fakeTranslate("Form", "Fit profile from mesh", None, -1))
