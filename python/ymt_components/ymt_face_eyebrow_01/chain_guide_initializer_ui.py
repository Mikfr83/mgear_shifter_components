import mgear.core.pyqt as gqt
from mgear.vendor.Qt import QtCore, QtWidgets

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(200, 133)
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.sections_label = QtWidgets.QLabel(Dialog)
        self.sections_label.setObjectName("sections_label")
        self.horizontalLayout.addWidget(self.sections_label)
        self.sections_spinBox = QtWidgets.QSpinBox(Dialog)
        self.sections_spinBox.setMinimum(4)
        self.sections_spinBox.setMaximum(999)
        self.sections_spinBox.setProperty("value", 4)
        self.sections_spinBox.setObjectName("sections_spinBox")
        self.horizontalLayout.addWidget(self.sections_spinBox)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.direction_label = QtWidgets.QLabel(Dialog)
        self.direction_label.setObjectName("direction_label")
        self.horizontalLayout_2.addWidget(self.direction_label)
        self.direction_comboBox = QtWidgets.QComboBox(Dialog)
        self.direction_comboBox.setObjectName("direction_comboBox")
        self.direction_comboBox.addItem("")
        self.direction_comboBox.addItem("")
        self.direction_comboBox.addItem("")
        self.direction_comboBox.addItem("")
        self.direction_comboBox.addItem("")
        self.direction_comboBox.addItem("")
        self.horizontalLayout_2.addWidget(self.direction_comboBox)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.spacing_label = QtWidgets.QLabel(Dialog)
        self.spacing_label.setObjectName("spacing_label")
        self.horizontalLayout_3.addWidget(self.spacing_label)
        self.spacing_doubleSpinBox = QtWidgets.QDoubleSpinBox(Dialog)
        self.spacing_doubleSpinBox.setDecimals(4)
        self.spacing_doubleSpinBox.setMaximum(999.99)
        self.spacing_doubleSpinBox.setProperty("value", 0.6)
        self.spacing_doubleSpinBox.setObjectName("spacing_doubleSpinBox")
        self.horizontalLayout_3.addWidget(self.spacing_doubleSpinBox)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.verticalLayout_2.addLayout(self.verticalLayout)
        self.buttonBox = QtWidgets.QDialogButtonBox(Dialog)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.Cancel|QtWidgets.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout_2.addWidget(self.buttonBox)
        spacerItem = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding)
        self.verticalLayout_2.addItem(spacerItem)

        self.retranslateUi(Dialog)
        self.buttonBox.accepted.connect(Dialog.accept)
        self.buttonBox.rejected.connect(Dialog.reject)

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(gqt.fakeTranslate("Dialog", "Dialog", None, -1))
        self.sections_label.setText(gqt.fakeTranslate("Dialog", "Sections Number", None, -1))
        self.direction_label.setText(gqt.fakeTranslate("Dialog", "Direction", None, -1))
        self.direction_comboBox.setItemText(0, gqt.fakeTranslate("Dialog", "X", None, -1))
        self.direction_comboBox.setItemText(1, gqt.fakeTranslate("Dialog", "Y", None, -1))
        self.direction_comboBox.setItemText(2, gqt.fakeTranslate("Dialog", "Z", None, -1))
        self.direction_comboBox.setItemText(3, gqt.fakeTranslate("Dialog", "-X", None, -1))
        self.direction_comboBox.setItemText(4, gqt.fakeTranslate("Dialog", "-Y", None, -1))
        self.direction_comboBox.setItemText(5, gqt.fakeTranslate("Dialog", "-Z", None, -1))
        self.direction_comboBox.setCurrentIndex(0)
        self.spacing_label.setText(gqt.fakeTranslate("Dialog", "Spacing", None, -1))

