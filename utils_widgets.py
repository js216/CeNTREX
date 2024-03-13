from PySide6 import QtCore, QtWidgets

from config import (
    IndicatorButtonParam,
    IndicatorLineEditParam,
    IndicatorParam,
    QCheckBoxParam,
    QComboBoxParam,
    QLineEditParam,
    QPushButtonParam,
)
from device import Device
from protocols import ControlGUIProtocol


def update_qcombobox(cbx: QtWidgets.QComboBox, options: list[str], value: str):
    # update the QComboBox with new runs
    cbx.clear()
    for option in options:
        cbx.addItem(option)

    # select the last run by default
    cbx.setCurrentText(value)


def create_checkbox_widget(
    param: QCheckBoxParam, control_name: str, device: Device
) -> QtWidgets.QCheckBox:
    control = QtWidgets.QCheckBox(param.label)
    control.setCheckState(QtCore.Qt.CheckState(param.value))
    if param.tristate:
        control.setTristate(True)
    if param.tooltip is not None:
        control.setToolTip(param.tooltip)

    control.stateChanged[int].connect(
        lambda state,
        dev=device,
        control_name=control_name: dev.config.change_param_subsection(
            param=control_name,
            section="control_params",
            value=state,
        )
    )

    return control


def create_pushbutton_widget(
    param: QPushButtonParam,
    control_name: str,
    device: Device,
    control_gui: ControlGUIProtocol,
) -> QtWidgets.QPushButton:
    control = QtWidgets.QPushButton(param.label)
    if param.tooltip is not None:
        control.setToolTip(param.tooltip)

    if param.argument is not None:
        control.clicked[bool].connect(
            lambda state,
            device=device,
            command=param.command,
            argument=device.config.control_params[
                param.argument
            ]: control_gui.queue_command(device, f"{command}({argument['value']})")
        )
    else:
        control.clicked[bool].connect(
            lambda state,
            device=device,
            command=param.command: control_gui.queue_command(device, f"{command}()")
        )
    return control


def create_qlineedit_widget(
    param: QLineEditParam,
    control_name: str,
    device: Device,
    control_gui: ControlGUIProtocol,
) -> QtWidgets.QLineEdit:
    control = QtWidgets.QLineEdit()
    control.setText(str(param.value))

    def text_changed_command(
        text: str, device: Device = device, control_name: str = control_name
    ) -> None:
        device.config.change_param_subsection(
            param=control_name, section="control_params", value=text
        )

    control.textChanged[str].connect(text_changed_command)

    if param.tooltip is not None:
        control.setToolTip(param.tooltip)

    if param.command is not None:

        def pressed_command(device: Device = device, command: str = param.command):
            control_gui.queue_command(device, f"{command}({control.text()})")

        control.returnPressed.connect(pressed_command)
    return control


def create_qcombobox_widget(
    param: QComboBoxParam,
    control_name: str,
    device: Device,
    control_gui: ControlGUIProtocol,
) -> QtWidgets.QComboBox:
    control = QtWidgets.QComboBox()
    update_qcombobox(
        control,
        options=list(set(param.options) | set(param.value)),
        value=str(param.value),
    )

    if param.tooltips is not None:
        control.setToolTip(param.tooltip)

    def value_changed(
        value: int, device: Device = device, control_name: str = control_name
    ) -> None:
        device.config.change_param_subsection(
            param=control_name, section="control_params", value=control.itemText(value)
        )

    control.activated[int].connect(value_changed)

    if param.command is not None:

        def value_changed_command(
            value: int,
            device=device,
            control_name: str = control_name,
            command: str = param.command,
        ) -> None:
            control_gui.queue_command(device, f"{command}({control.currentText()})")

        control.activated[int].connect(value_changed_command)

    return control


def create_indicator_widget(
    param: IndicatorParam,
) -> QtWidgets.QLabel:
    indicator = QtWidgets.QLabel(
        param.label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter
    )
    indicator.setProperty("state", param.states[-1])
    if param.tooltip is not None:
        indicator.setToolTip(param.tooltip)
    return indicator


def create_indicator_qlineedit_widget(
    param: IndicatorLineEditParam,
    control_name: str,
    device: Device,
    control_gui: ControlGUIProtocol,
) -> QtWidgets.QLineEdit:
    control = create_qlineedit_widget(param, control_name, device, control_gui)

    # disable auto-updating when the text is being edited
    device.config.change_param(
        GUI_element=control_name, key="currently_editing", val=False
    )

    def text_changed_command(
        text: str, device: Device = device, control_name: str = control_name
    ) -> None:
        device.config.change_param_subsection(
            param="currently_editing", section="control_GUI_elements", value=True
        )

    control.textEdited[str].connect(text_changed_command)

    def return_pressed_command(
        device: Device = device, control_name: str = control_name
    ) -> None:
        device.config.change_param_subsection(
            param="currently_editing", section="control_GUI_elements", value=False
        )

    control.returnPressed.connect(return_pressed_command)

    return control


def create_indicator_button_widget(
    param: IndicatorButtonParam,
    control_name: str,
    device: Device,
    control_gui: ControlGUIProtocol,
) -> QtWidgets.QCheckBox:
    control = QtWidgets.QPushButton(param.label)
    control.setCheckable(True)
    control.setChecked(param.checked[-1])
    control.setProperty("state", param.states[-1])

    if param.tooltip is not None:
        control.setToolTip(param.tooltip)

    if param.argument is not None:

        def button_clicked(
            state,
            device: Device = device,
            command_list: list[str] = param.action_commands,
            argument: str = device.config.control_params[param.argument].value,
        ):
            control_gui.queue_command(device, f"{command_list[int(state)]}({argument})")

        control.clicked[bool].connect(button_clicked)
    else:

        def button_clicked(
            state,
            device: Device = device,
            command_list: list[str] = param.action_commands,
        ):
            control_gui.queue_command(device, f"{command_list[int(state)]}()")

        control.clicked[bool].connect(button_clicked)
    return control
