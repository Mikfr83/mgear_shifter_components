"""Qt settings UI for ymt_skirt_01."""

import importlib


gqt = importlib.import_module("mgear.core.pyqt")
QtGui, QtCore, QtWidgets, wrapInstance = gqt.qt_import()


class Ui_Form(object):
    def _ring_scale_spin_box(self) -> QtWidgets.QDoubleSpinBox:
        spin_box = QtWidgets.QDoubleSpinBox(self.groupBox)
        spin_box.setDecimals(3)
        spin_box.setMinimum(0.001)
        spin_box.setMaximum(100.0)
        spin_box.setSingleStep(0.05)
        return spin_box

    def setupUi(self, Form: QtWidgets.QWidget) -> None:
        Form.setObjectName("Form")
        Form.resize(300, 380)
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
        self.formLayout.setWidget(11, QtWidgets.QFormLayout.FieldRole, self.postCollision_checkBox)

        self.collision_label = QtWidgets.QLabel(self.groupBox)
        self.collision_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.collision_doubleSpinBox.setDecimals(3)
        self.collision_doubleSpinBox.setMinimum(0.0)
        self.collision_doubleSpinBox.setMaximum(1.0)
        self.collision_doubleSpinBox.setSingleStep(0.05)
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.LabelRole, self.collision_label)
        self.formLayout.setWidget(5, QtWidgets.QFormLayout.FieldRole, self.collision_doubleSpinBox)

        self.tightness_label = QtWidgets.QLabel(self.groupBox)
        self.tightness_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.tightness_doubleSpinBox.setDecimals(3)
        self.tightness_doubleSpinBox.setMinimum(0.0)
        self.tightness_doubleSpinBox.setMaximum(1.0)
        self.tightness_doubleSpinBox.setSingleStep(0.05)
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.LabelRole, self.tightness_label)
        self.formLayout.setWidget(6, QtWidgets.QFormLayout.FieldRole, self.tightness_doubleSpinBox)

        self.falloff_label = QtWidgets.QLabel(self.groupBox)
        self.falloff_doubleSpinBox = QtWidgets.QDoubleSpinBox(self.groupBox)
        self.falloff_doubleSpinBox.setDecimals(3)
        self.falloff_doubleSpinBox.setMinimum(-1.0)
        self.falloff_doubleSpinBox.setMaximum(1.0)
        self.falloff_doubleSpinBox.setSingleStep(0.05)
        self.formLayout.setWidget(7, QtWidgets.QFormLayout.LabelRole, self.falloff_label)
        self.formLayout.setWidget(7, QtWidgets.QFormLayout.FieldRole, self.falloff_doubleSpinBox)

        self.ringScaleX_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleX_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.LabelRole, self.ringScaleX_label)
        self.formLayout.setWidget(8, QtWidgets.QFormLayout.FieldRole, self.ringScaleX_doubleSpinBox)

        self.ringScaleY_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleY_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.LabelRole, self.ringScaleY_label)
        self.formLayout.setWidget(9, QtWidgets.QFormLayout.FieldRole, self.ringScaleY_doubleSpinBox)

        self.ringScaleZ_label = QtWidgets.QLabel(self.groupBox)
        self.ringScaleZ_doubleSpinBox = self._ring_scale_spin_box()
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.LabelRole, self.ringScaleZ_label)
        self.formLayout.setWidget(10, QtWidgets.QFormLayout.FieldRole, self.ringScaleZ_doubleSpinBox)

        self.mainLayout.addLayout(self.formLayout)
        self.gridLayout.addWidget(self.groupBox, 0, 0, 1, 1)
        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form: QtWidgets.QWidget) -> None:
        Form.setWindowTitle(gqt.fakeTranslate("Form", "Form", None, -1))
        self.groupBox.setTitle(gqt.fakeTranslate("Form", "Skirt Grid", None, -1))
        self.rows_label.setText(gqt.fakeTranslate("Form", "Rows", None, -1))
        self.cols_label.setText(gqt.fakeTranslate("Form", "Columns", None, -1))
        self.rebuildGrid_pushButton.setText(gqt.fakeTranslate("Form", "Rebuild Grid Locators", None, -1))
        self.ctlSize_label.setText(gqt.fakeTranslate("Form", "Ctl Size", None, -1))
        self.addJoints_checkBox.setText(gqt.fakeTranslate("Form", "Add Joints", None, -1))
        self.postCollision_checkBox.setText(gqt.fakeTranslate("Form", "Post Collision (2nd pass)", None, -1))
        self.collision_label.setText(gqt.fakeTranslate("Form", "Collision", None, -1))
        self.tightness_label.setText(gqt.fakeTranslate("Form", "Tightness", None, -1))
        self.falloff_label.setText(gqt.fakeTranslate("Form", "Falloff", None, -1))
        self.ringScaleX_label.setText(gqt.fakeTranslate("Form", "Ring Scale X", None, -1))
        self.ringScaleY_label.setText(gqt.fakeTranslate("Form", "Ring Scale Y", None, -1))
        self.ringScaleZ_label.setText(gqt.fakeTranslate("Form", "Ring Scale Z", None, -1))
