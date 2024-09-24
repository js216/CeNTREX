from __future__ import annotations

import asyncio
import configparser
import datetime as dt
import glob
import logging
import os
import re
import socket
import time
import traceback
from pathlib import Path

import PyQt5
import PyQt5.QtWidgets as qt
import pythoncom
import pyvisa
import wmi
from PyQt5 import QtGui

from config import DeviceConfig, ProgramConfig
from device import Device, restart_device
from device_utils import get_device_methods
from hdf_writer import HDF_writer
from monitoring import Monitoring
from networking import Networking
from plots import PlotsGUI
from sequencer import SequencerGUI
from utils import split
from utils_gui import LabelFrame, ScrollableLabelFrame, error_box, update_QComboBox


class AttrEditor(qt.QDialog):
    def __init__(self, parent: CentrexGUI, dev=None):
        super().__init__()
        self.dev = dev
        self.parent = parent

        # layout for GUI elements
        self.frame = qt.QGridLayout()
        self.setLayout(self.frame)

        # draw the table
        if self.dev:
            num_rows = len(self.dev.config["attributes"])
        else:
            num_rows = len(self.parent.config["run_attributes"])
        self.qtw = qt.QTableWidget(num_rows, 2)
        self.qtw.setAlternatingRowColors(True)
        self.frame.addWidget(self.qtw, 0, 0, 1, 2)

        # put the attributes into the table
        if self.dev:
            attrs = self.dev.config["attributes"].items()
        else:
            attrs = self.parent.config["run_attributes"].items()
        for row, (key, val) in enumerate(attrs):
            self.qtw.setItem(row, 0, qt.QTableWidgetItem(key))
            self.qtw.setItem(row, 1, qt.QTableWidgetItem(val))

        # button to read attrs from file
        pb = qt.QPushButton("Read config file")
        pb.clicked[bool].connect(self.reload_attrs_from_file)
        self.frame.addWidget(pb, 1, 0)

        # button to write attrs to file
        pb = qt.QPushButton("Write config file")
        pb.clicked[bool].connect(self.write_attrs_to_file)
        self.frame.addWidget(pb, 1, 1)

        # buttons to add/remove rows
        pb = qt.QPushButton("Add one row")
        pb.clicked[bool].connect(self.add_row)
        self.frame.addWidget(pb, 2, 0)

        pb = qt.QPushButton("Delete last row")
        pb.clicked[bool].connect(self.delete_last_row)
        self.frame.addWidget(pb, 2, 1)

        # buttons to accept or reject the edits
        pb = qt.QPushButton("Accept")
        pb.clicked[bool].connect(lambda state: self.check_attributes())
        self.accepted.connect(self.change_attrs)
        self.frame.addWidget(pb, 3, 0)

        pb = qt.QPushButton("Reject")
        pb.clicked[bool].connect(lambda state: self.reject())
        self.frame.addWidget(pb, 3, 1)

    def reload_attrs_from_file(self, state):
        # reload attributes
        params = configparser.ConfigParser()
        if self.dev:
            params.read(self.dev.config.fname)
            new_attrs = params["attributes"]
        else:
            params.read(self.parent.config.fname)
            new_attrs = params["run_attributes"]

        # rewrite the table contents
        self.qtw.clear()
        self.qtw.setRowCount(len(new_attrs))
        for row, (key, val) in enumerate(new_attrs.items()):
            self.qtw.setItem(row, 0, qt.QTableWidgetItem(key))
            self.qtw.setItem(row, 1, qt.QTableWidgetItem(val))

    def write_attrs_to_file(self, state):
        # do a sanity check of attributes and change corresponding config dicts
        self.check_attributes()

        # when changing device attributes/settings
        if self.dev:
            self.dev.config.write_to_file()

        # when changing program attributes/settings
        if not self.dev:
            self.parent.config.write_to_file()

    def add_row(self, arg):
        self.qtw.insertRow(self.qtw.rowCount())

    def delete_last_row(self, arg):
        self.qtw.removeRow(self.qtw.rowCount() - 1)

    def check_attributes(self):
        for row in range(self.qtw.rowCount()):
            if not self.qtw.item(row, 0):
                logging.warning("Attr warning: key not given.")
                error_box("Attr warning", "Key not given.")
                return
            if not self.qtw.item(row, 1):
                logging.warning("Attr warning: value not given.")
                error_box("Attr warning", "Value not given.")
                return
        self.accept()

    def change_attrs(self):
        if self.dev:  # if changing device attributes
            # write the new attributes to the config dict
            self.dev.config["attributes"] = {}
            for row in range(self.qtw.rowCount()):
                key = self.qtw.item(row, 0).text()
                val = self.qtw.item(row, 1).text()
                self.dev.config["attributes"][key] = val

            # update the column names and units
            self.parent.ControlGUI.update_col_names_and_units()

        else:  # if changing run attributes
            self.parent.config["run_attributes"] = {}
            for row in range(self.qtw.rowCount()):
                key = self.qtw.item(row, 0).text()
                val = self.qtw.item(row, 1).text()
                self.parent.config["run_attributes"][key] = val


class RestartDevicePopup(qt.QDialog):
    def __init__(self, parent: CentrexGUI):
        super().__init__()
        self.setWindowTitle("Restart Device")
        self.parent = parent

        dev_names = list(self.parent.devices.keys())

        self.device_restart = qt.QComboBox()
        self.device_restart.addItems(dev_names)

        btn = qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel

        self.button_box = qt.QDialogButtonBox(btn)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout = qt.QFormLayout()
        self.layout.addRow("restart", self.device_restart)
        self.layout.addRow(self.button_box)

        self.setLayout(self.layout)

        if not self.parent.config["control_active"]:
            self.not_running_popup()

    def accept(self):
        dev_name = self.device_restart.currentText()
        dev = self.parent.devices.get(dev_name)
        dev = restart_device(dev, self.parent.config["time_offset"])

        self.parent.devices[dev_name] = dev
        self.close()

    def not_running_popup(self):
        err_msg = qt.QMessageBox()
        err_msg.setWindowTitle("Error")
        err_msg.setIcon(qt.QMessageBox.Critical)
        err_msg.setText("CeNTREX DAQ is not running. Cannot restart devices.")
        err_msg.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        err_msg.exec()


class MandatoryParametersPopup(qt.QDialog):
    def __init__(self, parent: CentrexGUI):
        super().__init__()
        self.parent = parent

        self.setWindowTitle("Measurement Parameters")

        self.mandatory_parameters = [
            "measurement type",
            "rc transition",
            "det transition",
            "rc power",
            "det power",
        ]

        self.measurement_type = qt.QComboBox()
        self.measurement_type.addItems(["transition finding", "general"])

        self.rc_transition = qt.QLineEdit()
        self.det_transition = qt.QLineEdit()

        self.rc_power = qt.QLineEdit()
        self.rc_power.setValidator(
            QtGui.QDoubleValidator(
                bottom=0, notation=QtGui.QDoubleValidator.Notation.StandardNotation
            )
        )

        self.det_power = qt.QLineEdit()
        self.det_power.setValidator(
            QtGui.QDoubleValidator(
                bottom=0, notation=QtGui.QDoubleValidator.Notation.StandardNotation
            )
        )

        btn = qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel

        self.button_box = qt.QDialogButtonBox(btn)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout = qt.QFormLayout()
        self.layout.addRow("measurement type", self.measurement_type)
        self.layout.addRow("RC transition", self.rc_transition)
        self.layout.addRow("DET transition", self.det_transition)
        self.layout.addRow("RC power [mW]", self.rc_power)
        self.layout.addRow("DET power [mW]", self.det_power)
        self.layout.addRow(self.button_box)

        self.setLayout(self.layout)

    def empty_parameter_popup(self, attr):
        err_msg = qt.QMessageBox()
        err_msg.setIcon(qt.QMessageBox.Critical)
        err_msg.setText(f"Mandatory parameter {attr} is empty")
        err_msg.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
        err_msg.exec()

    def accept(self):
        run_attributes = self.parent.config["run_attributes"]
        for attr in self.mandatory_parameters:
            atr = getattr(self, attr.replace(" ", "_"))
            if isinstance(atr, qt.QComboBox):
                if len(atr.currentText()) == 0:
                    self.empty_parameter_popup(attr)
                    raise ValueError(f"Mandatory parameter {attr} is empty")
                run_attributes[attr] = atr.currentText()

            elif isinstance(atr, qt.QLineEdit):
                if len(atr.text()) == 0:
                    self.empty_parameter_popup(attr)
                    raise ValueError(f"Mandatory parameter {attr} is empty")

                # if isinstance(atr.validator(), QtGui.QDoubleValidator):
                #     run_attributes[attr] = float(atr.text())
                run_attributes[attr] = atr.text()

        self.close()


class ControlGUI(qt.QWidget):
    def __init__(self, parent: CentrexGUI, mandatory_parameters: bool = False):
        super().__init__()
        self.parent = parent
        self.make_devices()
        self.place_GUI_elements()
        self.place_device_controls()
        self.refresh_COM_ports(button_pressed=True)

        self.mandatory_parameters = mandatory_parameters

    def update_style(self, ind):
        ind.style().unpolish(ind)
        ind.style().polish(ind)

    def make_devices(self):
        self.parent.devices = {}

        # check the config specifies a directory with device configuration files
        if not os.path.isdir(self.parent.config["files"]["config_dir"]):
            logging.error("Directory with device configuration files not specified.")
            return

        # iterate over all device config files
        for fname in glob.glob(self.parent.config["files"]["config_dir"] + "/*.ini"):
            # read device configuration
            try:
                dev_config = DeviceConfig(fname)
            except (IndexError, ValueError, TypeError, KeyError) as err:
                logging.error(
                    "Cannot read device config file " + fname + ": " + str(err)
                )
                logging.error(traceback.format_exc())
                return

            # for meta devices, include a reference to the parent
            if dev_config["meta_device"]:
                dev_config["parent"] = self.parent

            # make a Device object
            if dev_config["name"] in self.parent.devices:
                logging.warning(
                    "Warning in make_devices(): duplicate device name: "
                    + dev_config["name"]
                )
            self.parent.devices[dev_config["name"]] = Device(dev_config)

    def place_GUI_elements(self):
        # main frame for all ControlGUI elements
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        # the status label
        self.status_label = qt.QLabel(
            "Ready to start", alignment=PyQt5.QtCore.Qt.AlignRight
        )
        self.status_label.setFont(QtGui.QFont("Helvetica", 16))
        self.main_frame.addWidget(self.status_label)

        # a frame for controls and files, side-by-side
        self.top_frame = qt.QHBoxLayout()
        self.main_frame.addLayout(self.top_frame)

        ########################################
        # control and status
        ########################################

        box, control_frame = LabelFrame("Controls")
        self.top_frame.addWidget(box)

        # control start/stop buttons
        self.start_pb = qt.QPushButton("\u26ab Start control")
        self.start_pb.setToolTip("Start control for all enabled devices (Ctrl+S).")
        self.start_pb.clicked[bool].connect(self.start_control)
        control_frame.addWidget(self.start_pb, 0, 0)

        pb = qt.QPushButton("\u2b1b Stop control")
        pb.setToolTip("Stop control for all enabled devices (Ctrl+Q).")
        pb.clicked[bool].connect(self.stop_control)
        control_frame.addWidget(pb, 0, 1)

        # buttons to show/hide monitoring info
        self.monitoring_pb = qt.QPushButton("Show monitoring")
        self.monitoring_pb.setToolTip("Show MonitoringGUI (Ctrl+M).")
        self.monitoring_pb.clicked[bool].connect(self.toggle_monitoring)
        control_frame.addWidget(self.monitoring_pb, 1, 0)

        # buttons to show/hide plots
        self.plots_pb = qt.QPushButton("Show plots")
        self.plots_pb.setToolTip("Show/hide PlotsGUI (Ctrl+P).")
        self.plots_pb.clicked[bool].connect(self.toggle_plots)
        self.plots_pb.setToolTip("Show PlotsGUI (Ctrl+P).")
        control_frame.addWidget(self.plots_pb, 1, 1)

        # for horizontal/vertical program orientation
        self.orientation_pb = qt.QPushButton("Horizontal mode")
        self.orientation_pb.setToolTip(
            "Put controls and plots/monitoring on top of each other (Ctrl+V)."
        )
        self.orientation_pb.clicked[bool].connect(self.parent.toggle_orientation)
        control_frame.addWidget(self.orientation_pb, 2, 0)

        # button to refresh the list of COM ports
        pb = qt.QPushButton("Refresh COM ports")
        pb.setToolTip("Click this to populate all the COM port dropdown menus.")
        pb.clicked[bool].connect(self.refresh_COM_ports)
        control_frame.addWidget(pb, 2, 1)

        # button to disable all devices

        pb = qt.QPushButton("Enable all")
        pb.clicked[bool].connect(self.enable_all_devices)
        control_frame.addWidget(pb, 4, 0, 1, 1)

        pb = qt.QPushButton("Disable all")
        pb.clicked[bool].connect(self.disable_all_devices)
        control_frame.addWidget(pb, 4, 1, 1, 1)

        pb = qt.QPushButton("Restart Device")
        pb.clicked[bool].connect(self.restart_device)
        control_frame.addWidget(pb, 5, 0, 1, 1)

        ########################################
        # files
        ########################################

        box, files_frame = LabelFrame("")
        self.top_frame.addWidget(box)

        # config dir
        files_frame.addWidget(qt.QLabel("Config dir:"), 0, 0)

        self.config_dir_qle = qt.QLineEdit()
        self.config_dir_qle.setToolTip(
            "Directory with .ini files with device configurations."
        )
        self.config_dir_qle.setText(self.parent.config["files"]["config_dir"])
        self.config_dir_qle.textChanged[str].connect(
            lambda val: self.parent.config.change("files", "config_dir", val)
        )
        files_frame.addWidget(self.config_dir_qle, 0, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(self.set_config_dir)
        files_frame.addWidget(pb, 0, 2)

        # HDF file
        files_frame.addWidget(qt.QLabel("HDF file:"), 1, 0)

        self.hdf_fname_qle = qt.QLineEdit()
        self.hdf_fname_qle.setToolTip("HDF file for storing all acquired data.")
        self.hdf_fname_qle.setText(self.parent.config["files"]["hdf_fname"])
        self.hdf_fname_qle.textChanged[str].connect(
            lambda val: self.parent.config.change("files", "hdf_fname", val)
        )
        files_frame.addWidget(self.hdf_fname_qle, 1, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(
            lambda val, qle=self.hdf_fname_qle: self.open_file(
                "files", "hdf_fname", self.hdf_fname_qle
            )
        )
        files_frame.addWidget(pb, 1, 2)

        # HDF writer loop delay
        files_frame.addWidget(qt.QLabel("HDF writer loop delay:"), 3, 0)

        qle = qt.QLineEdit()
        qle.setToolTip(
            "The loop delay determines how frequently acquired data is written to the"
            " HDF file."
        )
        qle.setText(self.parent.config["general"]["hdf_loop_delay"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("general", "hdf_loop_delay", val)
        )
        files_frame.addWidget(qle, 3, 1)

        # run name
        files_frame.addWidget(qt.QLabel("Run name:"), 4, 0)

        qle = qt.QLineEdit()
        qle.setToolTip(
            "The name given to the HDF group containing all data for this run."
        )
        qle.setText(self.parent.config["general"]["run_name"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("general", "run_name", val)
        )
        files_frame.addWidget(qle, 4, 1)

        # for giving the HDF file new names
        pb = qt.QPushButton("Rename HDF")
        pb.setToolTip("Give the HDF file a new name based on current time.")
        pb.clicked[bool].connect(self.rename_HDF)
        files_frame.addWidget(pb, 3, 2)

        # button to edit run attributes
        pb = qt.QPushButton("Attrs...")
        pb.setToolTip(
            "Display or edit device attributes that are written with the data to the"
            " HDF file."
        )
        pb.clicked[bool].connect(self.edit_run_attrs)
        files_frame.addWidget(pb, 4, 2)

        # the control to send a custom command to a specified device
        files_frame.addWidget(qt.QLabel("Cmd:"), 5, 0)

        cmd_frame = qt.QHBoxLayout()
        files_frame.addLayout(cmd_frame, 5, 1)

        self.custom_func_cbx = qt.QComboBox()
        self.custom_func_cbx.setToolTip(
            "Enter a command corresponding to a function in the selected device driver."
        )
        cmd_frame.addWidget(self.custom_func_cbx)

        self.custom_params_qle = qt.QLineEdit()
        self.custom_params_qle.setToolTip("Enter parameters for the selected function")
        cmd_frame.addWidget(self.custom_params_qle)

        self.custom_dev_cbx = qt.QComboBox()
        dev_list = [dev_name for dev_name in self.parent.devices]
        update_QComboBox(
            cbx=self.custom_dev_cbx,
            options=list(
                set(dev_list) | set([self.parent.config["general"]["custom_device"]])
            ),
            value=self.parent.config["general"]["custom_device"],
        )
        update_QComboBox(
            cbx=self.custom_func_cbx,
            options=get_device_methods(dev_list[0], self.parent.devices),
            value=get_device_methods(dev_list[0], self.parent.devices)[0],
        )

        self.custom_dev_cbx.currentTextChanged[str].connect(
            lambda text: update_QComboBox(
                self.custom_func_cbx,
                options=get_device_methods(
                    self.custom_dev_cbx.currentText(), self.parent.devices
                ),
                value=get_device_methods(
                    self.custom_dev_cbx.currentText(), self.parent.devices
                )[0],
            )
        )
        self.custom_dev_cbx.activated[str].connect(
            lambda val: self.parent.config.change("general", "custom_device", val)
        )
        cmd_frame.addWidget(self.custom_dev_cbx)

        pb = qt.QPushButton("Send")
        pb.clicked[bool].connect(self.queue_custom_command)
        files_frame.addWidget(pb, 5, 2)

        ########################################
        # sequencer
        ########################################

        # frame for the sequencer
        self.seq_box, self.seq_frame = LabelFrame("Sequencer")
        self.main_frame.addWidget(self.seq_box)
        if not self.parent.config["sequencer_visible"]:
            self.seq_box.hide()

        # make and place the sequencer
        self.seq = SequencerGUI(self.parent)
        self.seq_frame.addWidget(self.seq)

        # label
        files_frame.addWidget(qt.QLabel("Sequencer file:"), 6, 0)

        # box for some of the buttons and stuff
        b_frame = qt.QHBoxLayout()
        files_frame.addLayout(b_frame, 6, 1, 1, 2)

        # filename
        self.fname_qle = qt.QLineEdit()
        self.fname_qle.setToolTip("Filename for storing a sequence.")
        self.fname_qle.setText(self.parent.config["files"]["sequence_fname"])
        self.fname_qle.textChanged[str].connect(
            lambda val: self.parent.config.change("files", "sequence_fname", val)
        )
        b_frame.addWidget(self.fname_qle)

        # open button
        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(
            lambda val, qle=self.fname_qle: self.open_file(
                "files", "sequence_fname", self.fname_qle
            )
        )
        b_frame.addWidget(pb)

        # load button
        pb = qt.QPushButton("Load")
        pb.clicked[bool].connect(self.seq.load_from_file)
        b_frame.addWidget(pb)

        # save button
        pb = qt.QPushButton("Save")
        pb.clicked[bool].connect(self.seq.save_to_file)
        b_frame.addWidget(pb)

        # buttons to show/hide the sequencer
        self.hs_pb = qt.QPushButton("Show sequencer")
        self.hs_pb.clicked[bool].connect(self.toggle_sequencer)
        b_frame.addWidget(self.hs_pb)

        ########################################
        # devices
        ########################################

        # frame for device-specific controls
        box, self.devices_frame = ScrollableLabelFrame("Devices", type="flexgrid")
        self.main_frame.addWidget(box)

        ########################################
        # Monitoring controls
        ########################################

        # general monitoring controls
        box, gen_f = LabelFrame("Monitoring", maxWidth=200, fixed=True)
        self.top_frame.addWidget(box)

        # HDF writer status
        gen_f.addWidget(qt.QLabel("Last written to HDF:"), 1, 0)
        self.HDF_status = qt.QLabel("0")
        gen_f.addWidget(self.HDF_status, 1, 1, 1, 2)

        # disk space usage
        gen_f.addWidget(qt.QLabel("Disk usage:"), 2, 0)
        self.free_qpb = qt.QProgressBar()
        gen_f.addWidget(self.free_qpb, 2, 1, 1, 2)
        self.check_free_disk_space()

        gen_f.addWidget(qt.QLabel("Loop delay [s]:"), 0, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["monitoring_dt"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("general", "monitoring_dt", val)
        )
        gen_f.addWidget(qle, 0, 1, 1, 2)

        # InfluxDB controls

        qch = qt.QCheckBox("InfluxDB")
        qch.setToolTip("InfluxDB enabled")
        qch.setTristate(False)
        qch.setChecked(
            True
            if self.parent.config["influxdb"]["enabled"] in ["1", "True"]
            else False
        )
        qch.stateChanged[int].connect(
            lambda val: self.parent.config.change("influxdb", "enabled", val)
        )
        gen_f.addWidget(qch, 5, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("Host IP")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["influxdb"]["host"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("influxdb", "host", val)
        )
        gen_f.addWidget(qle, 5, 1)

        qle = qt.QLineEdit()
        qle.setToolTip("Port")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["influxdb"]["port"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("influxdb", "port", val)
        )
        gen_f.addWidget(qle, 5, 2)

        # Networking controls
        qch = qt.QCheckBox("Networking")
        qch.setToolTip("Networking enabled")
        qch.setTristate(False)
        qch.setChecked(
            True
            if self.parent.config["networking"]["enabled"] in ["1", "True"]
            else False
        )
        qch.stateChanged[int].connect(
            lambda val: self.parent.config.change("networking", "enabled", val)
        )
        gen_f.addWidget(qch, 6, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("Read port")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["networking"]["port_readout"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("networking", "port_readout", val)
        )
        gen_f.addWidget(qle, 6, 1)

        qle = qt.QLineEdit()
        qle.setToolTip("Control port")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["networking"]["port_control"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("networking", "port_control", val)
        )
        gen_f.addWidget(qle, 6, 2)

        qle = qt.QLineEdit()
        qle.setToolTip("Name")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["networking"]["name"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("networking", "name", val)
        )
        gen_f.addWidget(qle, 7, 1)

        qle = qt.QLineEdit()
        qle.setToolTip("# Workers")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["networking"]["workers"])
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("networking", "workers", val)
        )
        gen_f.addWidget(qle, 7, 2)

        qla = qt.QLabel()
        qla.setToolTip("IP address")
        qla.setText(socket.gethostbyname(socket.gethostname()))
        gen_f.addWidget(qla, 8, 1, 1, 2)

        # for displaying warnings
        self.warnings_label = qt.QLabel("(no warnings)")
        self.warnings_label.setWordWrap(True)
        gen_f.addWidget(self.warnings_label, 9, 0, 1, 3)

    def enable_all_devices(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            try:
                dev.config["control_GUI_elements"]["enabled"]["QCheckBox"].setChecked(
                    True
                )
            except KeyError as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())

    def disable_all_devices(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            try:
                dev.config["control_GUI_elements"]["enabled"]["QCheckBox"].setChecked(
                    False
                )
            except KeyError as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())

    def restart_device(self):
        restart = RestartDevicePopup(self.parent)
        if self.parent.config["control_active"]:
            restart.exec()

    def update_col_names_and_units(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            # column names
            dev.col_names_list = split(dev.config["attributes"]["column_names"])
            dev.column_names = "\n".join(dev.col_names_list)
            dev.config["monitoring_GUI_elements"]["col_names"].setText(dev.column_names)

            # units
            units = split(dev.config["attributes"]["units"])
            dev.units = "\n".join(units)
            dev.config["monitoring_GUI_elements"]["units"].setText(dev.units)

    def update_warnings(self, warnings: str):
        self.warnings_label.setText(warnings)

    def check_free_disk_space(self):
        pythoncom.CoInitialize()
        c = wmi.WMI()
        for d in c.Win32_LogicalDisk():
            if d.Caption == self.parent.config["files"]["hdf_fname"][0:2]:
                size_MB = float(d.Size) / 1024 / 1024
                free_MB = float(d.FreeSpace) / 1024 / 1024
                self.free_qpb.setMinimum(0)
                self.free_qpb.setMaximum(int(size_MB))
                self.free_qpb.setValue(int(size_MB - free_MB))
                self.parent.app.processEvents()

    def toggle_control(self, val="", show_only=False):
        if not self.parent.config["control_visible"]:
            self.parent.config["control_visible"] = True
            self.show()
            self.parent.PlotsGUI.ctrls_box.show()
            self.parent.PlotsGUI.toggle_all_plot_controls()
        elif not show_only:
            self.parent.config["control_visible"] = False
            self.hide()
            self.parent.PlotsGUI.ctrls_box.hide()
            self.parent.PlotsGUI.toggle_all_plot_controls()

    def toggle_sequencer(self, val=""):
        if not self.parent.config["sequencer_visible"]:
            self.seq_box.show()
            self.parent.config["sequencer_visible"] = True
            self.hs_pb.setText("Hide sequencer")
        else:
            self.seq_box.hide()
            self.parent.config["sequencer_visible"] = False
            self.hs_pb.setText("Show sequencer")

    def toggle_monitoring(self, val=""):
        if not self.parent.config["monitoring_visible"]:
            self.parent.config["monitoring_visible"] = True
            for dev_name, dev in self.parent.devices.items():
                dev.config["monitoring_GUI_elements"]["df_box"].show()
            self.monitoring_pb.setText("Hide monitoring")
            self.monitoring_pb.setToolTip("Hide MonitoringGUI (Ctrl+M).")
        else:
            self.parent.config["monitoring_visible"] = False
            for dev_name, dev in self.parent.devices.items():
                dev.config["monitoring_GUI_elements"]["df_box"].hide()
            self.monitoring_pb.setText("Show monitoring")
            self.monitoring_pb.setToolTip("Show MonitoringGUI (Ctrl+M).")

    def toggle_plots(self, val=""):
        if not self.parent.config["plots_visible"]:
            self.parent.config["plots_visible"] = True
            self.parent.PlotsGUI.show()
            self.plots_pb.setText("Hide plots")
            self.plots_pb.setToolTip("Hide PlotsGUI (Ctrl+P).")
        else:
            self.parent.config["plots_visible"] = False
            self.parent.PlotsGUI.hide()
            self.plots_pb.setText("Show plots")
            self.plots_pb.setToolTip("Show PlotsGUI (Ctrl+P).")

    def edit_run_attrs(self, dev):
        # open the AttrEditor dialog window
        w = AttrEditor(self.parent)
        w.setWindowTitle("Run attributes")
        w.exec_()

    def place_device_controls(self):
        for dev_name, dev in self.parent.devices.items():
            # frame for device controls and monitoring
            label = dev.config["label"] + " [" + dev.config["name"] + "]"
            box, dcf = LabelFrame(label, type="vbox")
            self.devices_frame.addWidget(box, dev.config["row"], dev.config["column"])

            # layout for controls
            df_box, df = qt.QWidget(), qt.QGridLayout()
            df_box.setLayout(df)
            dcf.addWidget(df_box)
            df.setColumnStretch(1, 1)
            df.setColumnStretch(20, 0)

            # the button to reload attributes
            pb = qt.QPushButton("Attrs...")
            pb.setToolTip(
                "Display or edit device attributes that are written with the data to"
                " the HDF file."
            )
            pb.clicked[bool].connect(lambda val, dev=dev: self.edit_attrs(dev))
            df.addWidget(pb, 0, 1)

            # for changing plots_queue maxlen
            qle = qt.QLineEdit()
            qle.setToolTip("Change plots_queue maxlen.")
            qle.setText(str(dev.config["plots_queue_maxlen"]))
            qle.textChanged[str].connect(
                lambda maxlen, dev=dev: dev.change_plots_queue_maxlen(maxlen)
            )
            df.addWidget(qle, 1, 1)

            # device-specific controls
            dev.config["control_GUI_elements"] = {}
            for c_name, param in dev.config["control_params"].items():
                # the dict for control GUI elements
                dev.config["control_GUI_elements"][c_name] = {}
                c = dev.config["control_GUI_elements"][c_name]

                # place QCheckBoxes
                if param.get("type") == "QCheckBox":
                    # the QCheckBox
                    c["QCheckBox"] = qt.QCheckBox(param["label"])
                    c["QCheckBox"].setCheckState(param["value"])
                    if param["tristate"]:
                        c["QCheckBox"].setTristate(True)
                    else:
                        c["QCheckBox"].setTristate(False)
                    df.addWidget(c["QCheckBox"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QCheckBox"].setToolTip(param["tooltip"])

                    # commands for the QCheckBox
                    c["QCheckBox"].stateChanged[int].connect(
                        lambda state,
                        dev=dev,
                        ctrl=c_name,
                        nonTriState=not param["tristate"]: dev.config.change_param(
                            ctrl, state, sect="control_params", nonTriState=nonTriState
                        )
                    )

                # place QPushButtons
                elif param.get("type") == "QPushButton":
                    # the QPushButton
                    c["QPushButton"] = qt.QPushButton(param["label"])
                    df.addWidget(c["QPushButton"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QPushButton"].setToolTip(param["tooltip"])

                    # commands for the QPushButton
                    if param.get("argument"):
                        c["QPushButton"].clicked[bool].connect(
                            lambda state,
                            dev=dev,
                            cmd=param["cmd"],
                            arg=dev.config["control_params"][
                                param["argument"]
                            ]: self.queue_command(dev, cmd + "(" + arg["value"] + ")")
                        )
                    else:
                        c["QPushButton"].clicked[bool].connect(
                            lambda state, dev=dev, cmd=param["cmd"]: self.queue_command(
                                dev, cmd + "()"
                            )
                        )

                # place QLineEdits
                elif param.get("type") == "QLineEdit":
                    # the label
                    df.addWidget(
                        qt.QLabel(param["label"]),
                        param["row"],
                        param["col"] - 1,
                        alignment=PyQt5.QtCore.Qt.AlignRight,
                    )

                    # the QLineEdit
                    c["QLineEdit"] = qt.QLineEdit()
                    c["QLineEdit"].setText(param["value"])
                    c["QLineEdit"].textChanged[str].connect(
                        lambda text, dev=dev, ctrl=c_name: dev.config.change_param(
                            ctrl, text, sect="control_params"
                        )
                    )
                    df.addWidget(c["QLineEdit"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QLineEdit"].setToolTip(param["tooltip"])

                    # commands for the QLineEdit
                    if param.get("enter_cmd"):
                        if param.get("enter_cmd") != "None":
                            c["QLineEdit"].returnPressed.connect(
                                lambda dev=dev,
                                cmd=param["enter_cmd"],
                                qle=c["QLineEdit"]: self.queue_command(
                                    dev, cmd + "(" + qle.text() + ")"
                                )
                            )

                # place QComboBoxes
                elif param.get("type") == "QComboBox":
                    # the label
                    df.addWidget(
                        qt.QLabel(param["label"]),
                        param["row"],
                        param["col"] - 1,
                        alignment=PyQt5.QtCore.Qt.AlignRight,
                    )

                    # the QComboBox
                    c["QComboBox"] = qt.QComboBox()
                    update_QComboBox(
                        cbx=c["QComboBox"],
                        options=list(set(param["options"]) | set([param["value"]])),
                        value="divide by?",
                    )
                    c["QComboBox"].setCurrentText(param["value"])
                    df.addWidget(c["QComboBox"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QComboBox"].setToolTip(param["tooltip"])

                    # commands for the QComboBox
                    c["QComboBox"].activated[str].connect(
                        lambda text, dev=dev, config=c_name: dev.config.change_param(
                            config, text, sect="control_params"
                        )
                    )
                    if param.get("command"):
                        c["QComboBox"].activated[str].connect(
                            lambda text,
                            dev=dev,
                            cmd=param["command"],
                            qcb=c["QComboBox"]: self.queue_command(
                                dev, cmd + "('" + qcb.currentText() + "')"
                            )
                        )

                # place ControlsRows
                elif param.get("type") == "ControlsRow":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(param["label"], type="hbox")
                    df.addWidget(box, param["row"], param["col"])

                    # the individual controls that compose a ControlsRow
                    for ctrl in param["ctrl_names"]:
                        if param["ctrl_types"][ctrl] == "QLineEdit":
                            qle = qt.QLineEdit()
                            qle.setText(param["value"][ctrl])
                            qle.setToolTip(param["ctrl_labels"][ctrl])
                            # stop black formatter from changing the block below
                            # fmt: off
                            qle.textChanged[str].connect(
                                lambda val, dev=dev, config=c_name, sub_ctrl=ctrl:
                                    dev.config.change_param(
                                        config,
                                        val,
                                        sect="control_params",
                                        sub_ctrl=sub_ctrl,
                                    )
                            )
                            # fmt: on
                            ctrl_frame.addWidget(qle)

                        elif param["ctrl_types"][ctrl] == "QComboBox":
                            cbx = qt.QComboBox()
                            cbx.setToolTip(param["ctrl_labels"][ctrl])
                            # stop black formatter from changing the block below
                            # fmt: off
                            cbx.activated[str].connect(
                                lambda val, dev=dev, config=c_name, sub_ctrl=ctrl:
                                    dev.config.change_param(
                                        config,
                                        val,
                                        sect="control_params",
                                        sub_ctrl=sub_ctrl,
                                    )
                            )
                            # fmt: on
                            update_QComboBox(
                                cbx=cbx,
                                options=param["ctrl_options"][ctrl],
                                value=param["value"][ctrl],
                            )
                            ctrl_frame.addWidget(cbx)

                        else:
                            logging.warning(
                                "ControlsRow error: sub-control type not supported: "
                                + param["ctrl_types"][ctrl]
                            )

                # place ControlsTables
                elif param.get("type") == "ControlsTable":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(param["label"], type="grid")
                    if param.get("rowspan") and param.get("colspan"):
                        df.addWidget(
                            box,
                            param["row"],
                            param["col"],
                            param["rowspan"],
                            param["colspan"],
                        )
                    else:
                        df.addWidget(box, param["row"], param["col"])

                    for i, row in enumerate(param["row_ids"]):
                        for j, col in enumerate(param["col_names"]):
                            if param["col_types"][col] == "QLabel":
                                ql = qt.QLabel()
                                ql.setToolTip(param["col_labels"][col])
                                ql.setText(param["value"][col][i])
                                ctrl_frame.addWidget(ql, i, j)

                            elif param["col_types"][col] == "QLineEdit":
                                qle = qt.QLineEdit()
                                qle.setToolTip(param["col_labels"][col])
                                qle.setText(param["value"][col][i])
                                # stop black formatter from changing the block below
                                # fmt: off
                                qle.textChanged[str].connect(
                                    lambda val, dev=dev, config=c_name, sub_ctrl=col,
                                    row=row:
                                        dev.config.change_param(
                                            config,
                                            val,
                                            sect="control_params",
                                            sub_ctrl=sub_ctrl,
                                            row=row,
                                        )
                                )
                                # fmt: on
                                ctrl_frame.addWidget(qle, i, j)

                            elif param["col_types"][col] == "QCheckBox":
                                qch = qt.QCheckBox()
                                qch.setToolTip(param["col_labels"][col])
                                qch.setCheckState(int(param["value"][col][i]))
                                qch.setTristate(False)
                                # stop black formatter from changing the block below
                                # fmt: off
                                qch.stateChanged[int].connect(
                                    lambda val, dev=dev, config=c_name, sub_ctrl=col,
                                    row=row:
                                        dev.config.change_param(
                                            config,
                                            "1" if val != 0 else "0",
                                            sect="control_params",
                                            sub_ctrl=sub_ctrl,
                                            row=row,
                                        )
                                )
                                # fmt: on
                                ctrl_frame.addWidget(qch, i, j)

                            elif param["col_types"][col] == "QComboBox":
                                cbx = qt.QComboBox()
                                cbx.setToolTip(param["col_labels"][col])
                                # stop black formatter from changing the block below
                                # fmt: off
                                cbx.activated[str].connect(
                                    lambda val, dev=dev, config=c_name, sub_ctrl=col,
                                    row=row:
                                        dev.config.change_param(
                                            config,
                                            val,
                                            sect="control_params",
                                            sub_ctrl=sub_ctrl,
                                            row=row,
                                        )
                                )
                                # fmt: on
                                update_QComboBox(
                                    cbx=cbx,
                                    options=param["col_options"][col],
                                    value=param["value"][col][i],
                                )
                                ctrl_frame.addWidget(cbx, i, j)

                            else:
                                logging.warning(
                                    "ControlsRow error: sub-control type not"
                                    " supported: " + c["col_types"][col]
                                )

                # place indicators
                elif param.get("type") == "indicator":
                    # the indicator label
                    c["QLabel"] = qt.QLabel(
                        param["label"], alignment=PyQt5.QtCore.Qt.AlignCenter
                    )
                    c["QLabel"].setProperty("state", param["states"][-1])
                    ind = c["QLabel"]
                    self.update_style(ind)
                    if param.get("rowspan") and param.get("colspan"):
                        df.addWidget(
                            c["QLabel"],
                            param["row"],
                            param["col"],
                            param["rowspan"],
                            param["colspan"],
                        )
                    else:
                        df.addWidget(c["QLabel"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QLabel"].setToolTip(param["tooltip"])

                # place indicator_buttons
                elif param.get("type") == "indicator_button":
                    # the QPushButton
                    c["QPushButton"] = qt.QPushButton(param["label"])
                    c["QPushButton"].setCheckable(True)
                    c["QPushButton"].setChecked(param["checked"][-1])

                    # style
                    c["QPushButton"].setProperty("state", param["states"][-1])
                    ind = c["QPushButton"]
                    self.update_style(ind)

                    # tooltip
                    if param.get("tooltip"):
                        c["QPushButton"].setToolTip(param["tooltip"])

                    # rowspan / colspan
                    if param.get("rowspan") and param.get("colspan"):
                        df.addWidget(
                            c["QPushButton"],
                            param["row"],
                            param["col"],
                            param["rowspan"],
                            param["colspan"],
                        )
                    else:
                        df.addWidget(c["QPushButton"], param["row"], param["col"])

                    # commands for the QPushButton
                    if param.get("argument"):
                        c["QPushButton"].clicked[bool].connect(
                            lambda state,
                            dev=dev,
                            cmd_list=param["action_commands"],
                            arg=dev.config["control_params"][
                                param["argument"]
                            ]: self.queue_command(
                                dev, cmd_list[int(state)] + "(" + arg["value"] + ")"
                            )
                        )
                    else:
                        c["QPushButton"].clicked[bool].connect(
                            lambda state,
                            dev=dev,
                            cmd_list=param["action_commands"]: self.queue_command(
                                dev, cmd_list[int(state)] + "()"
                            )
                        )

                # place indicators_lineedits
                elif param.get("type") == "indicator_lineedit":
                    # the label
                    df.addWidget(
                        qt.QLabel(param["label"]),
                        param["row"],
                        param["col"] - 1,
                        alignment=PyQt5.QtCore.Qt.AlignRight,
                    )

                    # the QLineEdit
                    c["QLineEdit"] = qt.QLineEdit()
                    c["QLineEdit"].setText(param["value"])
                    c["QLineEdit"].textChanged[str].connect(
                        lambda text, dev=dev, ctrl=c_name: dev.config.change_param(
                            ctrl, text, sect="control_params"
                        )
                    )
                    df.addWidget(c["QLineEdit"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QLineEdit"].setToolTip(param["tooltip"])

                    # commands for the QLineEdit
                    if param.get("enter_cmd"):
                        if param.get("enter_cmd") != "None":
                            c["QLineEdit"].returnPressed.connect(
                                lambda dev=dev,
                                cmd=param["enter_cmd"],
                                qle=c["QLineEdit"]: self.queue_command(
                                    dev, cmd + "(" + qle.text() + ")"
                                )
                            )

                    # disable auto-updating when the text is being edited
                    dev.config.change_param(
                        GUI_element=c_name, key="currently_editing", val=False
                    )
                    c["QLineEdit"].textEdited[str].connect(
                        lambda text, dev=dev, c_name=c_name: dev.config.change_param(
                            GUI_element=c_name, key="currently_editing", val=True
                        )
                    )
                    c["QLineEdit"].returnPressed.connect(
                        lambda dev=dev, c_name=c_name: dev.config.change_param(
                            GUI_element=c_name, key="currently_editing", val=False
                        )
                    )

                elif param.get("type") == "device_list":
                    # the label
                    df.addWidget(
                        qt.QLabel(param["label"]),
                        param["row"],
                        param["col"] - 1,
                        alignment=PyQt5.QtCore.Qt.AlignRight,
                    )

                    # Device QComboBox
                    devices = list(self.parent.devices.keys())
                    c["QComboBox"] = qt.QComboBox()
                    update_QComboBox(
                        cbx=c["QComboBox"],
                        options=list(set(devices) | set([param["value"]])),
                        value="divide by?",
                    )
                    c["QComboBox"].setCurrentText(param["value"])
                    df.addWidget(c["QComboBox"], param["row"], param["col"])

                    # tooltip
                    if param.get("tooltip"):
                        c["QComboBox"].setToolTip(param["tooltip"])

                    # commands for the QComboBox
                    c["QComboBox"].activated[str].connect(
                        lambda text, dev=dev, config=c_name: dev.config.change_param(
                            config, text, sect="control_params"
                        )
                    )
                    if param.get("command"):
                        c["QComboBox"].activated[str].connect(
                            lambda text,
                            dev=dev,
                            cmd=param["command"],
                            qcb=c["QComboBox"]: self.queue_command(
                                dev, cmd + "('" + qcb.currentText() + "')"
                            )
                        )

                elif param.get("type") == "device_returns_list":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(param["label"], type="hbox")
                    df.addWidget(box, param["row"], param["col"])

                    # Device QComboBox
                    devices = list(self.parent.devices.keys())
                    d = qt.QComboBox()
                    update_QComboBox(
                        cbx=d,
                        options=list(set(devices) | set([param["device_value"]])),
                        value="divide by?",
                    )

                    # commands for the QComboBox
                    def change_param(text, dev=dev, config=c_name):
                        dev.config["control_params"][config]["device_value"] = text
                        value = dev.config["control_params"][config]["value"]
                        dev.config["control_params"][config]["value"] = (text, value[1])

                    d.activated[str].connect(change_param)
                    d.setCurrentText(param["device_value"])
                    ctrl_frame.addWidget(d)

                    # tooltip
                    if param.get("tooltip"):
                        d.setToolTip(param["tooltip"])

                    r = qt.QComboBox()
                    update_QComboBox(
                        cbx=r,
                        options=list(
                            self.parent.devices[d.currentText()].col_names_list
                        ),
                        value="divide by?",
                    )

                    def change_param(text, dev=dev, config=c_name):
                        dev.config["control_params"][config]["return_value"] = text
                        value = dev.config["control_params"][config]["value"]
                        dev.config["control_params"][config]["value"] = (value[0], text)

                    r.activated[str].connect(change_param)
                    r.setCurrentText(param["return_value"])

                    d.currentTextChanged.connect(
                        lambda device, cbx=r: update_QComboBox(
                            cbx, list(self.parent.devices[device].col_names_list), ""
                        )
                    )

                    ctrl_frame.addWidget(r)

                elif param.get("type") == "device_n_returns_list":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(param["label"], type="hbox")
                    df.addWidget(box, param["row"], param["col"])

                    # Device QComboBox
                    devices = list(self.parent.devices.keys())
                    d = qt.QComboBox()
                    update_QComboBox(
                        cbx=d,
                        options=list(set(devices) | set([param["device_value"]])),
                        value="divide by?",
                    )

                    # commands for the QComboBox
                    def change_param(text, dev=dev, config=c_name):
                        dev.config["control_params"][config]["device_value"] = text
                        value = dev.config["control_params"][config]["value"]
                        dev.config["control_params"][config]["value"] = (
                            text,
                            value[1],
                            value[2],
                        )

                    d.activated[str].connect(change_param)
                    d.setCurrentText(param["device_value"])
                    ctrl_frame.addWidget(d)

                    # tooltip
                    if param.get("tooltip"):
                        d.setToolTip(param["tooltip"])

                    returns = []
                    for idr in range(int(param["nr_returns"])):
                        returns.append(qt.QComboBox())
                        r = returns[-1]
                        update_QComboBox(
                            cbx=r,
                            options=list(
                                self.parent.devices[d.currentText()].col_names_list
                            ),
                            value="divide by?",
                        )

                        def change_param(text, dev=dev, config=c_name):
                            dev.config["control_params"][config][
                                f"return_value_{idr+1}"
                            ] = text
                            value = list(dev.config["control_params"][config]["value"])
                            value[idr + 1] = text
                            dev.config["control_params"][config]["value"] = tuple(value)

                        r.activated[str].connect(change_param)
                        r.setCurrentText(param[f"return_value_{idr+1}"])

                        ctrl_frame.addWidget(r)

                    def update_returns(device, returns=returns):
                        for r in returns:
                            update_QComboBox(
                                r, list(self.parent.devices[device].col_names_list), ""
                            )

                    d.currentTextChanged.connect(update_returns)

            ##################################
            # MONITORING                     #
            ##################################

            # layout for monitoring info
            df_box, df = qt.QWidget(), qt.QGridLayout()
            df_box.setLayout(df)
            if not self.parent.config["monitoring_visible"]:
                df_box.hide()
            dcf.addWidget(df_box)
            dev.config["monitoring_GUI_elements"] = {"df_box": df_box}

            # length of the data queue
            df.addWidget(
                qt.QLabel("Queue length:"), 0, 0, alignment=PyQt5.QtCore.Qt.AlignRight
            )
            dev.config["monitoring_GUI_elements"]["qsize"] = qt.QLabel("N/A")
            df.addWidget(
                dev.config["monitoring_GUI_elements"]["qsize"],
                0,
                1,
                alignment=PyQt5.QtCore.Qt.AlignLeft,
            )

            # NaN count
            df.addWidget(
                qt.QLabel("NaN count:"), 1, 0, alignment=PyQt5.QtCore.Qt.AlignRight
            )
            dev.config["monitoring_GUI_elements"]["NaN_count"] = qt.QLabel("N/A")
            df.addWidget(
                dev.config["monitoring_GUI_elements"]["NaN_count"],
                1,
                1,
                alignment=PyQt5.QtCore.Qt.AlignLeft,
            )

            # column names
            dev.col_names_list = split(dev.config["attributes"]["column_names"])
            dev.column_names = "\n".join(dev.col_names_list)
            dev.config["monitoring_GUI_elements"]["col_names"] = qt.QLabel(
                dev.column_names, alignment=PyQt5.QtCore.Qt.AlignRight
            )
            df.addWidget(dev.config["monitoring_GUI_elements"]["col_names"], 2, 0)

            # data
            dev.config["monitoring_GUI_elements"]["data"] = qt.QLabel("(no data)")
            df.addWidget(
                dev.config["monitoring_GUI_elements"]["data"],
                2,
                1,
                alignment=PyQt5.QtCore.Qt.AlignLeft,
            )

            # units
            units = split(dev.config["attributes"]["units"])
            dev.units = "\n".join(units)
            dev.config["monitoring_GUI_elements"]["units"] = qt.QLabel(dev.units)
            df.addWidget(
                dev.config["monitoring_GUI_elements"]["units"],
                2,
                2,
                alignment=PyQt5.QtCore.Qt.AlignLeft,
            )

            # latest event / command sent to device & its return value
            df.addWidget(
                qt.QLabel("Last event:"), 3, 0, alignment=PyQt5.QtCore.Qt.AlignRight
            )
            dev.config["monitoring_GUI_elements"]["events"] = qt.QLabel("(no events)")
            dev.config["monitoring_GUI_elements"]["events"].setWordWrap(True)
            df.addWidget(
                dev.config["monitoring_GUI_elements"]["events"],
                3,
                1,
                1,
                2,
                alignment=PyQt5.QtCore.Qt.AlignLeft,
            )

    def rename_HDF(self, state):
        # check we're not running already
        if self.parent.config["control_active"]:
            logging.warning(
                "Warning: Rename HDF while control is running takes                   "
                " effect only after restarting control."
            )
            qt.QMessageBox.information(
                self,
                "Rename while running",
                (
                    "Control running. Renaming HDF file will only take effect after"
                    " restarting control."
                ),
            )

        # get old file path
        old_fname = self.parent.config["files"]["hdf_fname"]

        # strip the old name from the full path
        path = "/".join(old_fname.split("/")[0:-1])

        # add the new filename
        path += "/" + dt.datetime.strftime(dt.datetime.now(), "%Y_%m_%d") + ".hdf"

        # set the hdf_fname to the new path
        self.parent.config["files"]["hdf_fname"] = path

        # update the QLineEdit
        self.hdf_fname_qle.setText(path)

    def open_file(self, sect, config, qle=None):
        # ask the user to select a file
        val = qt.QFileDialog.getSaveFileName(self, "Select file")[0]
        if not val:
            return

        # set the config entry
        self.parent.config.change(sect, config, val)

        # update the QLineEdit if given
        if qle:
            qle.setText(val)

        return val

    def open_dir(self, sect, config, qle=None):
        # ask the user to select a directory
        val = str(qt.QFileDialog.getExistingDirectory(self, "Select Directory"))
        if not val:
            return

        # set the config entry
        self.parent.config.change(sect, config, val)

        # update the QLineEdit if given
        if qle:
            qle.setText(val)

        return val

    def set_config_dir(self, state):
        # ask the user to select a directory
        if not self.open_dir("files", "config_dir", self.config_dir_qle):
            return

        # update device controls
        self.devices_frame.clear()
        self.make_devices()
        self.place_device_controls()

        # changes the list of devices in send custom command
        dev_list = [dev_name for dev_name in self.parent.devices]
        update_QComboBox(
            cbx=self.custom_dev_cbx,
            options=list(
                set(dev_list) | set([self.parent.config["general"]["custom_device"]])
            ),
            value=self.parent.config["general"]["custom_device"],
        )

        # update the available devices for plotting
        self.parent.PlotsGUI.refresh_all_run_lists()

    def get_dev_list(self):
        dev_list = []
        for dev_name, dev in self.parent.devices.items():
            if dev.config["control_params"]["enabled"]["value"]:
                dev_list.append(dev_name)
        return dev_list

    def queue_custom_command(self):
        # check the command is valid
        cmd = f"{self.custom_func_cbx.currentText()}({self.custom_params_qle.text()})"
        search = re.compile(r'[^A-Za-z0-9()".?!*# ]_=').search
        if bool(search(cmd)):
            error_box("Command error", "Invalid command.")
            return

        # check the device is valid
        dev_name = self.custom_dev_cbx.currentText()
        dev = self.parent.devices.get(dev_name)
        if not dev:
            error_box("Device error", "Device not found.")
            return
        if not dev.operational:
            error_box("Device error", "Device not operational.")
            return

        self.queue_command(dev, cmd)

    def queue_command(self, dev, cmd):
        dev.commands.append(cmd)

    def refresh_COM_ports(self, button_pressed):
        for dev_name, dev in self.parent.devices.items():
            # check device has a COM_port control
            if not dev.config["control_GUI_elements"].get("COM_port"):
                continue
            else:
                cbx = dev.config["control_GUI_elements"]["COM_port"]["QComboBox"]

            # update the QComboBox of COM_port options
            update_QComboBox(
                cbx=cbx,
                options=list(pyvisa.ResourceManager().list_resources())
                + [cbx.currentText()],
                value=cbx.currentText(),
            )

    def edit_attrs(self, dev):
        # open the AttrEditor dialog window
        w = AttrEditor(self.parent, dev)
        w.setWindowTitle("Attributes for " + dev.config["name"])
        w.exec_()

    def start_control(self):
        logging.info("Start control")
        # check we're not running already
        if self.parent.config["control_active"]:
            return

        # check at least one device is enabled
        at_least_one_enabled = False
        for dev_name, dev in self.parent.devices.items():
            if dev.config["control_params"]["enabled"]["value"]:
                at_least_one_enabled = True
        if not at_least_one_enabled:
            logging.warning("Cannot start: no device enabled.")
            return

        if self.mandatory_parameters:
            parameter_popup = MandatoryParametersPopup(self.parent)
            parameter_popup.exec()

        # select the time offset
        self.parent.config["time_offset"] = time.time()

        # setup & check connections of all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["control_params"]["enabled"]["value"]:
                # update the status label
                self.status_label.setText("Starting " + dev_name + " ...")
                self.parent.app.processEvents()

                # re-instantiate the thread (since Python only allows threads to be
                # started once, this is necessary to allow repeatedly stopping and
                # starting control)
                self.parent.devices[dev_name] = Device(dev.config)
                dev = self.parent.devices[dev_name]

                # setup connection
                dev.setup_connection(self.parent.config["time_offset"])
                if not dev.operational:
                    error_box(
                        "Device error",
                        "Error: " + dev.config["label"] + " not responding.",
                        dev.error_message,
                    )
                    self.status_label.setText("Device configuration error")
                    return

        # update device controls with new instances of Devices
        self.devices_frame.clear()
        self.place_device_controls()

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent, self.parent.hdf_clear)
        self.HDF_writer.start()

        # start control for all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["control_params"]["enabled"]["value"]:
                dev.clear_queues()
                dev.start()

        # update and start the monitoring thread
        self.monitoring = Monitoring(self.parent)
        self.monitoring.update_style.connect(self.update_style)
        self.monitoring.active.set()
        self.monitoring.start()

        # start the networking thread
        if self.parent.config["networking"]["enabled"] in ["1", "2", "True"]:
            self.networking = Networking(self.parent)
            self.networking.start()
        else:
            self.networking = False

        # update program status
        self.parent.config["control_active"] = True
        self.status_label.setText("Running")

        # update the values of the above controls
        # make all plots display the current run and file, and clear f(y) for fast data
        self.parent.config["files"]["plotting_hdf_fname"] = self.parent.config["files"][
            "hdf_fname"
        ]
        self.parent.PlotsGUI.refresh_all_run_lists(select_defaults=False)
        self.parent.PlotsGUI.clear_all_fast_y()

    def stop_control(self):
        # stop the sequencer
        self.seq.stop_sequencer()

        # check we're not stopped already
        if not self.parent.config["control_active"]:
            return

        # stop all plots
        self.parent.PlotsGUI.stop_all_plots()

        # stop monitoring
        if self.monitoring.active.is_set():
            self.monitoring.active.clear()
            self.monitoring.join()

        # stop networking
        if self.networking:
            if self.networking.active.is_set():
                self.networking.active.clear()
                self.networking.join()

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()
            self.HDF_writer.join()

        # remove background color of the HDF status label
        HDF_status = self.parent.ControlGUI.HDF_status
        HDF_status.setProperty("state", "disabled")
        HDF_status.setStyle(HDF_status.style())

        # stop each Device thread
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                # update the status label
                self.status_label.setText("Stopping " + dev_name + " ...")
                self.parent.app.processEvents()

                # reset the status of all indicators
                for c_name, params in dev.config["control_params"].items():
                    if params.get("type") == "indicator":
                        ind = dev.config["control_GUI_elements"][c_name]["QLabel"]
                        ind.setText(params["texts"][-1])
                        ind.setProperty("state", params["states"][-1])
                        ind.setStyle(ind.style())

                    elif params.get("type") == "indicator_button":
                        ind = dev.config["control_GUI_elements"][c_name]["QPushButton"]
                        ind.setChecked(params["checked"][-1])
                        ind.setText(params["texts"][-1])
                        ind.setProperty("state", params["states"][-1])
                        ind.setStyle(ind.style())

                    elif params.get("type") == "indicator_lineedit":
                        ind = dev.config["control_GUI_elements"][c_name]["QLineEdit"]
                        ind.setText(params["label"])

                # stop the device, and wait for it to finish
                dev.active.clear()
                dev.join()
                logging.info(f"{dev_name}: stopped")

        # update status
        self.parent.config["control_active"] = False
        self.status_label.setText("Recording finished")


class CentrexGUI(qt.QMainWindow):
    def __init__(
        self,
        app,
        settings_path: Path,
        auto_start: bool = False,
        clear: bool = False,
        mandatory_parameters: bool = False,
    ):
        super().__init__()

        self.hdf_clear = clear

        logging.info("Starting CeNTREX DAQ")
        self.app = app
        self.setWindowTitle("CENTREX DAQ")

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self.load_stylesheet()

        # read program configuration
        self.config = ProgramConfig(settings_path)

        # set debug level
        logging.getLogger().setLevel(self.config["general"]["debug_level"])

        # GUI elements
        self.ControlGUI = ControlGUI(self, mandatory_parameters=mandatory_parameters)
        self.PlotsGUI = PlotsGUI(self)

        # put GUI elements in a QSplitter
        self.qs = qt.QSplitter()
        self.setCentralWidget(self.qs)
        self.qs.addWidget(self.ControlGUI)
        self.qs.addWidget(self.PlotsGUI)
        self.PlotsGUI.hide()

        # default main window size
        self.resize(1100, 900)

        # keyboard shortcuts
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+C"), self).activated.connect(
            self.ControlGUI.toggle_control
        )
        qt.QShortcut(QtGui.QKeySequence("Esc"), self).activated.connect(
            lambda: self.ControlGUI.toggle_control(show_only=True)
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+P"), self).activated.connect(
            self.ControlGUI.toggle_plots
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+M"), self).activated.connect(
            self.ControlGUI.toggle_monitoring
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+S"), self).activated.connect(
            self.ControlGUI.start_control
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self).activated.connect(
            self.ControlGUI.stop_control
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+T"), self).activated.connect(
            self.PlotsGUI.toggle_all_plot_controls
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+V"), self).activated.connect(
            self.toggle_orientation
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+S"), self).activated.connect(
            self.PlotsGUI.start_all_plots
        )
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Q"), self).activated.connect(
            self.PlotsGUI.stop_all_plots
        )

        self.show()

        if auto_start:
            self.ControlGUI.start_control()

    def load_stylesheet(self, reset=False):
        if reset:
            self.app.setStyleSheet("")
        else:
            with open(Path(__file__).parent / "darkstyle.qss", "r") as f:
                self.app.setStyleSheet(f.read())

    def toggle_orientation(self):
        if self.config["horizontal_split"]:
            self.qs.setOrientation(PyQt5.QtCore.Qt.Vertical)
            self.config["horizontal_split"] = False
            self.ControlGUI.orientation_pb.setText("Vertical mode")
            self.ControlGUI.orientation_pb.setToolTip(
                "Put controls and plots/monitoring side-by-side (Ctrl+V)."
            )
        else:
            self.qs.setOrientation(PyQt5.QtCore.Qt.Horizontal)
            self.config["horizontal_split"] = True
            self.ControlGUI.orientation_pb.setText("Horizontal mode")
            self.ControlGUI.orientation_pb.setToolTip(
                "Put controls and plots/monitoring on top of each other (Ctrl+V)."
            )

    def closeEvent(self, event):
        self.ControlGUI.seq.stop_sequencer()
        if self.config["control_active"]:
            if (
                qt.QMessageBox.question(
                    self,
                    "Confirm quit",
                    "Control running. Do you really want to quit?",
                    qt.QMessageBox.Yes | qt.QMessageBox.No,
                    qt.QMessageBox.No,
                )
                == qt.QMessageBox.Yes
            ):
                self.ControlGUI.stop_control()
                event.accept()
            else:
                event.ignore()
