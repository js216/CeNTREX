import re
import h5py
import time
import PyQt5
import pickle
import pyvisa
import logging
import threading
import qdarkstyle
import numpy as np
import configparser
import wmi, pythoncom
import pyqtgraph as pg
import PyQt5.QtGui as QtGui
import PyQt5.QtWidgets as qt
from collections import deque
import sys, os, glob, importlib
from influxdb import InfluxDBClient

##########################################################################
##########################################################################
#######                                                 ##################
#######            CONVENIENCE FUNCTIONS                ##################
#######                                                 ##################
##########################################################################
##########################################################################

def LabelFrame(frame, label, col=None, row=None, rowspan=1, colspan=1,
        type="grid", maxWidth=None):
    # make a framed box
    box = qt.QGroupBox(label)

    # box size
    if maxWidth:
        box.setMaximumWidth(maxWidth)

    # select type of layout
    if type == "grid":
        layout = qt.QGridLayout()
    elif type == "hbox":
        layout = qt.QHBoxLayout()
    elif type == "vbox":
        layout = qt.QVBoxLayout()
    box.setLayout(layout)

    # add the box to the parent container
    if row or col:
        frame.addWidget(box, row, col, rowspan, colspan)
    else:
        frame.addWidget(box)

    return layout

def ScrollableLabelFrame(frame, label, col=None, row=None, rowspan=1, colspan=1):
    # make the outer (framed) box
    outer_box = qt.QGroupBox(label)
    outer_layout = qt.QGridLayout()
    outer_box.setLayout(outer_layout)

    # make the inner grid
    inner_box = qt.QWidget()
    inner_layout = qt.QGridLayout()
    inner_layout.setContentsMargins(0,0,0,0)
    inner_box.setLayout(inner_layout)

    # make a scrollable area, and add the inner area to it
    sa = qt.QScrollArea()
    sa.setFrameStyle(16)
    sa.setWidgetResizable(True)
    sa.setWidget(inner_box)

    # add the scrollable area to the outer (framed) box
    outer_layout.addWidget(sa)

    # add the outer (framed) box to the parent container
    if row or col:
        frame.addWidget(outer_box, row, col, rowspan, colspan)
    else:
        frame.addWidget(outer_box)

    return inner_layout

def message_box(title, text, message=""):
    msg = qt.QMessageBox()
    msg.setIcon(qt.QMessageBox.Information)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setInformativeText(message)
    msg.exec_()

def error_box(title, text, message=""):
    msg = qt.QMessageBox()
    msg.setIcon(qt.QMessageBox.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setInformativeText(message)
    msg.exec_()

def update_QComboBox(cbx, options, value):
    # update the QComboBox with new runs
    cbx.clear()
    for option in options:
        cbx.addItem(option)

    # select the last run by default
    cbx.setCurrentText(value)

def clear_layout(layout):
    for i in reversed(range(layout.count())):
        layout.itemAt(i).widget().setParent(None)

##########################################################################
##########################################################################
#######                                                 ##################
#######            CONTROL CLASSES                      ##################
#######                                                 ##################
##########################################################################
##########################################################################

class Device(threading.Thread):
    def __init__(self, config):
        threading.Thread.__init__(self)
        self.config = config

        # whether the thread is running
        self.control_started = False
        self.active = threading.Event()
        self.active.clear()

        # whether the connection to the device was successful
        self.operational = False
        self.error_message = ""

        # for sending commands to the device
        self.commands = []

        # for warnings about device abnormal condition
        self.warnings = []

        # the data and events queues
        self.data_queue = deque()
        self.plots_queue = deque(maxlen=self.config["plots_queue_maxlen"])
        self.events_queue = deque()

        # the variable for counting the number of NaN returns
        self.nan_count = 0

    def setup_connection(self, time_offset):
        self.time_offset = time_offset

        # get the parameters that are to be passed to the driver constructor
        self.constr_params = [self.time_offset]
        for cp in self.config["constr_params"]:
            self.constr_params.append(self.config["controls"][cp]["value"])

        # verify the device responds correctly
        with self.config["driver"](*self.constr_params) as dev:
            if not isinstance(dev.verification_string, str):
                self.operational = False
                self.error_message = "verification_string is not of type str"
                return
            if dev.verification_string.strip() == self.config["correct_response"].strip():
                self.operational = True
            else:
                self.error_message = "verification string warning:" +\
                        dev.verification_string + "!=" + self.config["correct_response"].strip()
                logging.warning(self.error_message)
                self.operational = False
                return

            # get parameters and attributes, if any, from the driver
            self.config["shape"] = dev.shape
            self.config["dtype"] = dev.dtype
            for attr_name, attr_val in dev.new_attributes:
                self.config["attributes"][attr_name] = attr_val

    def clear_queues(self):
        self.data_queue.clear()
        self.events_queue.clear()

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return
        else:
            self.active.set()
            self.control_started = True

        # main control loop
        with self.config["driver"](*self.constr_params) as device:
            while self.active.is_set():
                # loop delay
                try:
                    dt = float(self.config["controls"]["dt"]["value"])
                    if dt < 0.002:
                        logging.warning("Device dt too small.")
                        raise ValueError
                    time.sleep(float(self.config["controls"]["dt"]["value"]))
                except ValueError:
                    time.sleep(0.1)

                # check device is enabled
                if not self.config["controls"]["enabled"]["value"]:
                    continue

                # check device for abnormal conditions
                warning = device.GetWarnings()
                if warning:
                    self.warnings += warning

                # record numerical values
                last_data = device.ReadValue()
                # keep track of the number of NaN returns
                if isinstance(last_data, float):
                    if np.isnan(last_data):
                        self.nan_count.set(self.nan_count + 1)
                elif len(last_data) > 0:
                    self.data_queue.append(last_data)
                    self.plots_queue.append(last_data)

                # send control commands, if any, to the device, and record return values
                for c in self.commands:
                    try:
                        ret_val = eval("device." + c.strip())
                    except (ValueError, AttributeError, SyntaxError, TypeError) as err:
                        ret_val = str(err)
                    ret_val = "None" if not ret_val else ret_val
                    last_event = [ time.time()-self.time_offset, c, ret_val ]
                    self.events_queue.append(last_event)
                self.commands = []

class Monitoring(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # connect to InfluxDB
        conf = self.parent.config["influxdb"]
        self.influxdb_client = InfluxDBClient(
                host     = conf["host"],
                port     = conf["port"],
                username = conf["username"],
                password = conf["password"],
            )
        self.influxdb_client.switch_database(self.parent.config["influxdb"]["database"])

    def run(self):
        while self.active.is_set():
            # check the amount of free disk space
            pythoncom.CoInitialize()
            c = wmi.WMI ()
            for d in c.Win32_LogicalDisk():
                if d.Caption == self.parent.config["files"]["hdf_fname"][0:2]:
                    size_MB = float(d.Size) / 1024/1024
                    free_MB = float(d.FreeSpace) / 1024/1024
                    self.parent.MonitoringGUI.free_qpb.setMinimum(0)
                    self.parent.MonitoringGUI.free_qpb.setMaximum(size_MB)
                    self.parent.MonitoringGUI.free_qpb.setValue(size_MB - free_MB)

            # monitor operation of individual devices
            for dev_name, dev in self.parent.devices.items():
                # check device running
                if not dev.control_started:
                    continue

                # check device for abnormal conditions
                if len(dev.warnings) != 0:
                    logging.warning("Abnormal condition in " + str(dev_name))
                    for warning in dev.warnings:
                        logging.warning(str(warning))
                        self.push_warnings_to_influxdb(dev_name, warning)
                        self.MonitoringGUI.update_warnings(str(warning))
                    dev.warnings = []

                # find out and display the data queue length
                dev.monitoring_GUI_elements["qsize"].setText(str(len(dev.data_queue)))

                # get the last event (if any) of the device
                self.display_last_event(dev)

                # get the last row of data in the HDF dataset
                data = self.get_last_row_of_data(dev)
                if not isinstance(data, type(None)):
                    # display the data in a tkinter variable
                    formatted_data = [np.format_float_scientific(x, precision=3) for x in data]
                    dev.monitoring_GUI_elements["data"].setText("\n".join(formatted_data))

                    # write slow data to InfluxDB
                    self.write_to_influxdb(dev, data)

                # if writing to HDF is disabled, empty the queues
                if not dev.config["controls"]["HDF_enabled"]["value"]:
                    dev.events_queue.clear()
                    dev.data_queue.clear()

            # loop delay
            try:
                time.sleep(float(self.parent.config["general"]["monitoring_dt"]))
            except ValueError:
                time.sleep(1)

    def write_to_influxdb(self, dev, data):
        if self.parent.config["influxdb"]["enabled"].strip() == "False":
            return
        if not dev.config["slow_data"]:
            return
        fields = {}
        for col,val in zip(dev.col_names_list[1:], data[1:]):
            if not np.isnan(val):
                fields[col] = val
        if len(fields) > 0:
            json_body = [
                    {
                        "measurement": dev.config["name"],
                        "tags": { "run_name": self.parent.run_name, },
                        "time": int(1000 * (data[0] + self.parent.config["time_offset"])),
                        "fields": fields,
                        }
                    ]
            self.influxdb_client.write_points(json_body, time_precision='ms')

    def get_last_row_of_data(self, dev):
        # check device enabled
        if not dev.config["controls"]["enabled"]["value"]:
            return

        # if HDF writing enabled for this device, get data from the HDF file
        if dev.config["controls"]["HDF_enabled"]["value"]:
            with h5py.File(self.parent.config["files"]["hdf_fname"], 'r') as f:
                grp = f[self.parent.run_name + "/" + dev.config["path"]]
                if dev.config["slow_data"]:
                    dset = grp[dev.config["name"]]
                    if dset.shape[0] == 0:
                        return None
                    else:
                        data = dset[-1]
                else:
                    rec_num = len(grp) - 1
                    if rec_num < 3:
                        return None
                    try:
                        data = grp[dev.config["name"] + "_" + str(rec_num)][-1]
                    except KeyError:
                        logging.warning("dset doesn't exist: num = " + str(rec_num))
                        return None
                return data

        # if HDF writing not enabled for this device, get data from the events_queue
        else:
            try:
                return dev.data_queue.pop()
            except IndexError:
                return None

    def display_last_event(self, dev):
        # check device enabled
        if not dev.config["controls"]["enabled"]["value"]:
            return

        # if HDF writing enabled for this device, get events from the HDF file
        if dev.config["controls"]["HDF_enabled"]["value"]:
            with h5py.File(self.parent.config["files"]["hdf_fname"], 'r') as f:
                grp = f[self.parent.run_name + "/" + dev.config["path"]]
                events_dset = grp[dev.config["name"] + "_events"]
                if events_dset.shape[0] == 0:
                    dev.monitoring_GUI_elements["events"].setText("(no event)")
                else:
                    dev.monitoring_GUI_elements["events"].setText(str(events_dset[-1]))

        # if HDF writing not enabled for this device, get events from the events_queue
        else:
            try:
                dev.monitoring_GUI_elements["events"].setText(str(dev.events_queue.pop()))
            except IndexError:
                return

    def push_warnings_to_influxdb(self, dev_name, warning):
        json_body = [
                {
                    "measurement": "warnings",
                    "tags": {
                        "run_name": self.parent.run_name,
                        "dev_name": dev_name,
                        },
                    "time": int(1000 * warning[0]),
                    "fields": warning[1],
                    }
                ]
        self.influxdb_client.write_points(json_body, time_precision='ms')

class HDF_writer(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # configuration parameters
        self.filename = self.parent.config["files"]["hdf_fname"]
        self.parent.run_name = str(int(time.time())) + " " + self.parent.config["general"]["run_name"]

        # create/open HDF file, groups, and datasets
        with h5py.File(self.filename, 'a') as f:
            root = f.create_group(self.parent.run_name)
            root.attrs["time_offset"] = self.parent.config["time_offset"]
            for dev_name, dev in self.parent.devices.items():
                # check device is enabled
                if not dev.config["controls"]["enabled"]:
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]:
                    continue

                grp = root.require_group(dev.config["path"])

                # create dataset for data if only one is needed
                # (fast devices create a new dataset for each acquisition)
                if dev.config["slow_data"]:
                    dset = grp.create_dataset(
                            dev.config["name"],
                            (0, *dev.config["shape"]),
                            maxshape=(None, *dev.config["shape"]),
                            dtype=dev.config["dtype"]
                        )
                    for attr_name, attr in dev.config["attributes"].items():
                        dset.attrs[attr_name] = attr
                else:
                    for attr_name, attr in dev.config["attributes"].items():
                        grp.attrs[attr_name] = attr

                # create dataset for events
                events_dset = grp.create_dataset(dev.config["name"]+"_events", (0,3),
                        maxshape=(None,3), dtype=h5py.special_dtype(vlen=str))

        self.active.set()

    def run(self):
        while self.active.is_set():
            # empty queues to HDF
            try:
                with h5py.File(self.filename, 'a') as fname:
                    self.write_all_queues_to_HDF(fname)
            except OSError as err:
                logging.warning("HDF_writer error: {0}".format(err))

            # loop delay
            try:
                dt = float(self.parent.config["general"]["hdf_loop_delay"])
                if dt < 0.002:
                    logging.warning("Plot dt too small.")
                    raise ValueError
                time.sleep(dt)
            except ValueError:
                time.sleep(float(self.parent.config["general"]["default_hdf_dt"]))

        # make sure everything is written to HDF when the thread terminates
        try:
            with h5py.File(self.filename, 'a') as fname:
                self.write_all_queues_to_HDF(fname)
        except OSError as err:
            logging.warning("HDF_writer error: ", err)

    def write_all_queues_to_HDF(self, fname):
            root = fname.require_group(self.parent.run_name)
            for dev_name, dev in self.parent.devices.items():
                # check device has had control started
                if not dev.control_started:
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]["value"]:
                    continue

                # get events, if any, and write them to HDF
                events = self.get_data(dev.events_queue)
                if len(events) != 0:
                    grp = root.require_group(dev.config["path"])
                    events_dset = grp[dev.config["name"] + "_events"]
                    events_dset.resize(events_dset.shape[0]+len(events), axis=0)
                    events_dset[-len(events):,:] = events

                # get data
                data = self.get_data(dev.data_queue)
                if len(data) == 0:
                    continue

                grp = root.require_group(dev.config["path"])

                # if writing all data from a single device to one dataset
                if dev.config["slow_data"]:
                    dset = grp[dev.config["name"]]
                    # check if one queue entry has multiple rows
                    if np.ndim(data) == 3:
                        arr_len = np.shape(data)[1]
                        list_len = len(data)
                        dset.resize(dset.shape[0]+list_len*arr_len, axis=0)
                        # iterate over queue entries with multiple rows and append
                        for idx, d in enumerate(data):
                            idx_start = -arr_len*(list_len-idx)
                            idx_stop = -arr_len*(list_len-(idx+1))
                            if idx_stop == 0:
                                dset[idx_start:] = d
                            else:
                                dset[idx_start:idx_stop] = d
                    else:
                        dset.resize(dset.shape[0]+len(data), axis=0)
                        dset[-len(data):] = data

                # if writing each acquisition record to a separate dataset
                else:
                    for record, all_attrs in data:
                        for waveforms, attrs in zip(record, all_attrs):
                            # data
                            dset = grp.create_dataset(
                                    name        = dev.config["name"] + "_" + str(len(grp)),
                                    data        = waveforms.T,
                                    dtype       = dev.config["dtype"],
                                    compression = None
                                )
                            # metadata
                            for key, val in attrs.items():
                                dset.attrs[key] = val

    def get_data(self, fifo):
        data = []
        while True:
            try:
                data.append( fifo.popleft() )
            except IndexError:
                break
        return data

##########################################################################
##########################################################################
#######                                                 ##################
#######            GUI CLASSES                          ##################
#######                                                 ##################
##########################################################################
##########################################################################

class ControlGUI(qt.QWidget):
    def __init__(self, parent):
        super(qt.QWidget, self).__init__(parent)
        self.parent = parent
        self.read_device_config()
        self.place_GUI_elements()
        self.place_device_controls()

    def read_device_config(self):
        self.parent.devices = {}

        # check the config dict specifies a directory with device configuration files
        if not os.path.isdir(self.parent.config["files"]["config_dir"]):
            logging.error("Directory with device configuration files not specified.")
            return

        # iterate over all device config files
        for f in glob.glob(self.parent.config["files"]["config_dir"] + "/*.ini"):
            # config file sanity check
            params = configparser.ConfigParser()
            params.read(f)
            if not "device" in params:
                logging.warning("The device config file " + f + " does not have a [device] section.")
                continue

            # import the device driver
            driver_spec = importlib.util.spec_from_file_location(
                    params["device"]["driver"],
                    "drivers/" + params["device"]["driver"] + ".py",
                )
            driver_module = importlib.util.module_from_spec(driver_spec)
            driver_spec.loader.exec_module(driver_module)
            driver = getattr(driver_module, params["device"]["driver"])

            # read general device options
            try:
                dev_config = self.read_device_config_options(f, params)
                dev_config["config_fname"] = f
                dev_config["driver"] = driver
            except (IndexError, ValueError) as err:
                logging.error("Cannot read device config file: " + str(err))
                return

            # populate the list of device controls
            try:
                dev_config["controls"] = self.read_device_controls(params)
            except (IndexError, ValueError, TypeError, KeyError) as err:
                logging.error("Cannot read device config file" + f + " : " + str(err))
                return

            # make a Device object
            self.parent.devices[params["device"]["name"]] = Device(dev_config)

    def read_device_config_options(self, f, params):
        return {
                    "name"               : params["device"]["name"],
                    "label"              : params["device"]["label"],
                    "path"               : params["device"]["path"],
                    "correct_response"   : params["device"]["correct_response"],
                    "plots_queue_maxlen" : int(params["device"]["plots_queue_maxlen"]),
                    "slow_data"          : True if params["device"]["slow_data"]=="True" else False,
                    "row"                : int(params["device"]["row"]),
                    "rowspan"            : int(params["device"]["rowspan"]),
                    "monitoring_row"     : int(params["device"]["monitoring_row"]),
                    "column"             : int(params["device"]["column"]),
                    "columnspan"         : int(params["device"]["columnspan"]),
                    "monitoring_column"  : int(params["device"]["monitoring_column"]),
                    "constr_params"      : [x.strip() for x in params["device"]["constr_params"].split(",")],
                    "attributes"         : params["attributes"],
                }

    def read_device_controls(self, params):
            ctrls = {}
            for c in params.sections():
                if params[c].get("type") == "QCheckBox":
                    ctrls[c] = {
                            "label"      : params[c]["label"],
                            "type"       : params[c]["type"],
                            "row"        : int(params[c]["row"]),
                            "col"        : int(params[c]["col"]),
                            "value"      : True if params[c]["value"] in ["1", "True"] else False,
                            "tooltip"    : params[c].get("tooltip"),
                        }

                elif params[c].get("type") == "Hidden":
                    ctrls[c] = {
                            "value"      : params[c]["value"],
                            "type"       : "Hidden",
                        }

                elif params[c].get("type") == "QPushButton":
                    ctrls[c] = {
                            "label"      : params[c]["label"],
                            "type"       : params[c]["type"],
                            "row"        : int(params[c]["row"]),
                            "col"        : int(params[c]["col"]),
                            "cmd"        : params[c].get("command"),
                            "argument"   : params[c]["argument"],
                            "align"      : params[c].get("align"),
                            "tooltip"    : params[c].get("tooltip"),
                        }

                elif params[c].get("type") == "QLineEdit":
                    ctrls[c] = {
                            "label"      : params[c]["label"],
                            "type"       : params[c]["type"],
                            "row"        : int(params[c]["row"]),
                            "col"        : int(params[c]["col"]),
                            "enter_cmd"  : params[c].get("enter_command"),
                            "value"      : params[c]["value"],
                            "tooltip"    : params[c].get("tooltip"),
                        }

                elif params[c].get("type") == "QComboBox":
                    ctrls[c] = {
                            "label"      : params[c]["label"],
                            "type"       : params[c]["type"],
                            "row"        : int(params[c]["row"]),
                            "col"        : int(params[c]["col"]),
                            "command"    : params[c]["command"],
                            "options"    : [x.strip() for x in params[c]["options"].split(",")],
                            "value"      : params[c]["value"],
                        }

                elif params[c].get("type"):
                    logging.warning("Control type not supported: " + params[c].get("type"))

            return ctrls

    def place_GUI_elements(self):
        # main frame for all ControlGUI elements
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        ########################################
        # control and status
        ########################################

        control_frame = qt.QGridLayout()
        self.main_frame.addLayout(control_frame)

        # control start/stop buttons
        pb = qt.QPushButton("\u26ab Start control")
        pb.clicked[bool].connect(self.start_control)
        control_frame.addWidget(pb, 0, 0)

        pb = qt.QPushButton("\u2b1b Stop control")
        pb.clicked[bool].connect(self.stop_control)
        control_frame.addWidget(pb, 0, 1)

        # the status label
        self.status_label = qt.QLabel(
                "Ready to start",
                alignment = PyQt5.QtCore.Qt.AlignRight,
            )
        self.status_label.setFont(QtGui.QFont("Helvetica", 16))
        control_frame.addWidget(self.status_label, 0, 2)

        ########################################
        # files
        ########################################

        files_frame = LabelFrame(self.main_frame, "Files")

        # config dir
        files_frame.addWidget(qt.QLabel("Config dir:"), 0, 0)

        self.config_dir_qle = qt.QLineEdit()
        self.config_dir_qle.setToolTip("Directory with .ini files with device configurations.")
        self.config_dir_qle.setText(self.parent.config["files"]["config_dir"])
        self.config_dir_qle.textChanged[str].connect(lambda val: self.change_config("files", "config_dir", val))
        files_frame.addWidget(self.config_dir_qle, 0, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(self.set_config_dir)
        files_frame.addWidget(pb, 0, 2)

        # HDF file
        files_frame.addWidget(qt.QLabel("HDF file:"), 1, 0)

        self.hdf_fname_qle = qt.QLineEdit()
        self.hdf_fname_qle.setToolTip("HDF file for storing all acquired data.")
        self.hdf_fname_qle.setText(self.parent.config["files"]["hdf_fname"])
        self.hdf_fname_qle.textChanged[str].connect(lambda val: self.change_config("files", "hdf_fname", val))
        files_frame.addWidget(self.hdf_fname_qle, 1, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(
                lambda val, qle=self.hdf_fname_qle: self.open_file("files", "hdf_fname", self.hdf_fname_qle)
            )
        files_frame.addWidget(pb, 1, 2)

        # HDF writer loop delay
        files_frame.addWidget(qt.QLabel("HDF writer loop delay:"), 3, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("The loop delay determines how frequently acquired data is written to the HDF file.")
        qle.setText(self.parent.config["general"]["hdf_loop_delay"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "hdf_loop_delay", val))
        files_frame.addWidget(qle, 3, 1)

        # run name
        files_frame.addWidget(qt.QLabel("Run name:"), 4, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("The name given to the HDF group containing all data for this run.")
        qle.setText(self.parent.config["general"]["run_name"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "run_name", val))
        files_frame.addWidget(qle, 4, 1)

        # for giving the HDF file new names
        pb = qt.QPushButton("Rename HDF")
        pb.setToolTip("Give the HDF file a new name based on current time.")
        pb.clicked[bool].connect(self.rename_HDF)
        files_frame.addWidget(pb, 3, 2)

        # for dark/light stylesheets
        self.style_pb = qt.QPushButton("Dark")
        self.style_pb.setToolTip("Change style to dark mode.")
        self.style_pb.clicked[bool].connect(self.toggle_style)
        files_frame.addWidget(self.style_pb, 4, 2)

        ########################################
        # devices
        ########################################

        cmd_frame = LabelFrame(self.main_frame, "Send a custom command")

        # the control to send a custom command to a specified device
        cmd_frame.addWidget(qt.QLabel("Cmd:"), 0, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("Enter a command corresponding to a function in the selected device driver.")
        qle.setText(self.parent.config["general"]["custom_command"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "custom_command", val))
        cmd_frame.addWidget(qle, 0, 1)

        self.custom_dev_cbx = qt.QComboBox()
        dev_list = [dev_name for dev_name in self.parent.devices]
        update_QComboBox(
                cbx     = self.custom_dev_cbx,
                options = list(set(dev_list) | set([ self.parent.config["general"]["custom_device"] ])),
                value   = self.parent.config["general"]["custom_device"],
            )
        self.custom_dev_cbx.activated[str].connect(
                lambda val: self.change_config("general", "custom_device", val)
            )
        cmd_frame.addWidget(self.custom_dev_cbx, 0, 2)

        pb = qt.QPushButton("Send")
        pb.clicked[bool].connect(self.queue_custom_command)
        cmd_frame.addWidget(pb, 0, 3)

        # button to refresh the list of COM ports
        pb = qt.QPushButton("Refresh COM ports")
        pb.setToolTip("Click this to populate all the COM port dropdown menus.")
        pb.clicked[bool].connect(self.refresh_COM_ports)
        cmd_frame.addWidget(pb, 0, 4)

        # frame for device-specific controls
        self.devices_frame = ScrollableLabelFrame(self.main_frame, "Devices")

    def place_device_controls(self):
        for dev_name, dev in self.parent.devices.items():
            df = LabelFrame(
                    self.devices_frame,
                    dev.config["label"],
                    dev.config["column"],
                    dev.config["row"],
                )

            # the button to reload attributes
            pb = qt.QPushButton("Attrs")
            pb.setToolTip("Display or edit device attributes that are written with the data to the HDF file.")
            pb.clicked[bool].connect(lambda val, dev=dev : self.edit_attrs(dev))
            df.addWidget(pb, 0, 20)

            # device-specific controls
            for c_name, c in dev.config["controls"].items():

                # place QCheckBoxes
                if c["type"] == "QCheckBox":
                    # the QCheckBox
                    c["QCheckBox"] = qt.QCheckBox(c["label"])
                    c["QCheckBox"].setCheckState(c["value"])
                    c["QCheckBox"].setTristate(False)
                    df.addWidget(c["QCheckBox"], c["row"], c["col"])

                    # tooltip
                    if c.get("tooltip"):
                        c["QCheckBox"].setToolTip(c["tooltip"])

                    # commands for the QCheckBox
                    c["QCheckBox"].stateChanged[int].connect(
                            lambda state, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, state)
                        )

                # place QPushButtons
                elif c["type"] == "QPushButton":
                    # the QPushButton
                    c["QPushButton"] = qt.QPushButton(c["label"])
                    df.addWidget(c["QPushButton"], c["row"], c["col"])

                    # tooltip
                    if c.get("tooltip"):
                        c["QPushButton"].setToolTip(c["tooltip"])

                    # commands for the QPushButton
                    if c.get("argument"):
                        c["QPushButton"].clicked[bool].connect(
                                lambda state, dev=dev, cmd=c["cmd"],
                                arg=dev.config["controls"][c["argument"]]:
                                    self.queue_command(dev, cmd+"("+arg["value"]+")")
                            )
                    else:
                        c["QPushButton"].clicked[bool].connect(
                                lambda state, dev=dev, cmd=c["cmd"]:
                                    self.queue_command(dev, cmd+"()")
                            )

                # place QLineEdits
                elif c["type"] == "QLineEdit":
                    # the label
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )

                    # the QLineEdit
                    c["QLineEdit"] = qt.QLineEdit()
                    c["QLineEdit"].setText(c["value"])
                    c["QLineEdit"].textChanged[str].connect(
                            lambda text, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, text)
                        )
                    df.addWidget(c["QLineEdit"], c["row"], c["col"])

                    # tooltip
                    if c.get("tooltip"):
                        c["QLineEdit"].setToolTip(c["tooltip"])

                    # commands for the QLineEdit
                    if c.get("enter_cmd"):
                        c["QLineEdit"].returnPressed.connect(
                                lambda dev=dev, cmd=c["enter_cmd"], qle=c["QLineEdit"]:
                                self.queue_command(dev, cmd+"("+qle.text()+")")
                            )

                # place QComboBoxes
                elif c["type"] == "QComboBox":
                    # the label
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )

                    # the QComboBox
                    c["QComboBox"] = qt.QComboBox()
                    update_QComboBox(
                            cbx     = c["QComboBox"],
                            options = list(set(c["options"]) | set([c["value"]])),
                            value   = "divide by?"
                        )
                    c["QComboBox"].setCurrentText(c["value"])
                    df.addWidget(c["QComboBox"], c["row"], c["col"])

                    # tooltip
                    if c.get("tooltip"):
                        c["QComboBox"].setToolTip(c["tooltip"])

                    # commands for the QComboBox
                    c["QComboBox"].activated[str].connect(
                            lambda text, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, text)
                        )
                    if c.get("command"):
                        c["QComboBox"].activated[str].connect(
                                lambda text, dev=dev, cmd=c["command"], qcb=c["QComboBox"]:
                                    self.queue_command(dev, cmd+"('"+qcb.currentText()+"')")
                            )

    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

    def change_dev_control(self, dev, config, val):
        dev.config["controls"][config]["value"] = val

    def toggle_style(self, state):
        if self.style_pb.text() == "Dark":
            self.parent.app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
            self.style_pb.setText("Light")
            self.style_pb.setToolTip("Change style to light mode.")
        else:
            self.parent.app.setStyleSheet("")
            self.style_pb.setText("Dark")
            self.style_pb.setToolTip("Change style to dark mode.")

    def rename_HDF(self, state):
        # get old file path
        old_fname = self.parent.config["files"]["hdf_fname"]

        # strip the old name from the full path
        path = "/".join( old_fname.split('/')[0:-1] )

        # add the new filename
        path += "/" + str( int(time.time()) ) + ".hdf"

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
        self.parent.config[sect][config] = val

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
        self.parent.config[sect][config] = val

        # update the QLineEdit if given
        if qle:
            qle.setText(val)

        return val

    def set_config_dir(self, state):
        # ask the user to select a directory
        self.open_dir("files", "config_dir", self.config_dir_qle)

        # update device controls
        clear_layout(self.devices_frame)
        self.read_device_config()
        self.place_device_controls()

        # update device data in MonitoringGUI
        clear_layout(self.parent.MonitoringGUI.dev_f)
        self.parent.MonitoringGUI.place_device_specific_items()

        # changes the list of devices in send custom command
        dev_list = [dev_name for dev_name in self.parent.devices]
        update_QComboBox(
                cbx     = self.custom_dev_cbx,
                options = list(set(dev_list) | set([ self.parent.config["general"]["custom_device"] ])),
                value   = self.parent.config["general"]["custom_device"],
            )

    def queue_custom_command(self):
        # check the command is valid
        cmd = self.parent.config["general"]["custom_command"]
        search = re.compile(r'[^A-Za-z0-9()]').search
        if bool(search(cmd)):
            error_box("Command error", "Invalid command.")
            return

        # check the device is valid
        dev_name = self.parent.config["general"]["custom_device"]
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
            if not dev.config["controls"].get("COM_port"):
                continue

            # update the QComboBox of COM_port options
            update_QComboBox(
                    cbx     = dev.config["controls"]["COM_port"]["QComboBox"],
                    options = pyvisa.ResourceManager().list_resources(),
                    value   = cbx.currentText()
                )

    class AttrEditor(QtGui.QDialog):
        def __init__(self, parent, dev):
            super().__init__()
            self.dev = dev
            self.parent = parent

            # layout for GUI elements
            self.frame = qt.QGridLayout()
            self.setLayout(self.frame)

            # draw the table
            self.qtw = qt.QTableWidget(len(self.dev.config["attributes"]),2)
            self.frame.addWidget(self.qtw, 0, 0, 1, 2)

            # put the attributes into the table
            for row, (key, val) in enumerate(self.dev.config["attributes"].items()):
                self.qtw.setItem(row, 0, qt.QTableWidgetItem( key ))
                self.qtw.setItem(row, 1, qt.QTableWidgetItem( val ))

            # button to read attrs from file
            pb = qt.QPushButton("Reload attributes from config file")
            pb.clicked[bool].connect(self.reload_attrs_from_file)
            self.frame.addWidget(pb, 1, 0, 1, 2)

            # buttons to add/remove rows
            pb = qt.QPushButton("Add one row")
            pb.clicked[bool].connect(self.add_row)
            self.frame.addWidget(pb, 2, 0)

            pb = qt.QPushButton("Delete last row")
            pb.clicked[bool].connect(self.delete_last_row)
            self.frame.addWidget(pb, 2, 1)

            # buttons to accept or reject the edits
            pb = qt.QPushButton("Accept")
            pb.clicked[bool].connect(lambda state : self.check_attributes())
            self.accepted.connect(self.change_dev_attrs)
            self.frame.addWidget(pb, 3, 0)

            pb = qt.QPushButton("Reject")
            pb.clicked[bool].connect(lambda state : self.reject())
            self.frame.addWidget(pb, 3, 1)

        def reload_attrs_from_file(self, state):
            # reload attributes
            params = configparser.ConfigParser()
            params.read(self.dev.config["config_fname"])
            self.dev.config["attributes"] = params["attributes"]

            # rewrite the table contents
            self.qtw.clear()
            self.qtw.setRowCount(len(self.dev.config["attributes"]))
            for row, (key, val) in enumerate(self.dev.config["attributes"].items()):
                self.qtw.setItem(row, 0, qt.QTableWidgetItem( key ))
                self.qtw.setItem(row, 1, qt.QTableWidgetItem( val ))

        def add_row(self, arg):
            self.qtw.insertRow(self.qtw.rowCount())

        def delete_last_row(self, arg):
            self.qtw.removeRow(self.qtw.rowCount()-1)

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

        def change_dev_attrs(self):
            # write the new attributes to the config dict
            self.dev.config["attributes"] = {}
            for row in range(self.qtw.rowCount()):
                    key = self.qtw.item(row, 0).text()
                    val = self.qtw.item(row, 1).text()
                    self.dev.config["attributes"][key] = val

            # update the column names and units in MonitoringGUI
            self.parent.parent.MonitoringGUI.update_col_names_and_units()

    def edit_attrs(self, dev):
        # open the AttrEditor dialog window
        w = self.AttrEditor(self, dev)
        w.setWindowTitle("Attributes for " + dev.config["name"])
        w.exec_()

    def start_control(self):
        # check we're not running already
        if self.parent.config['control_active']:
            return

        # select the time offset
        self.parent.config["time_offset"] = time.time()

        # setup & check connections of all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["value"]:
                # update the status label
                self.status_label.setText("Starting " + dev_name + " ...")
                self.parent.app.processEvents()

                # setup connection
                dev.setup_connection(self.parent.config["time_offset"])
                if not dev.operational:
                    error_box("Device error", "Error: " + dev.config["label"] +\
                            " not responding.", dev.error_message)
                    self.status_label.setText("Device configuration error")
                    return

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent)
        self.HDF_writer.start()

        # start control for all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["value"]:
                dev.clear_queues()
                dev.start()

        # update and start the monitoring thread
        self.parent.MonitoringGUI.start_monitoring()

        # update program status
        self.parent.config['control_active'] = True
        self.status_label.setText("Running")

        # make all plots display the current run and file, and clear f(y) for fast data
        self.parent.config["files"]["plotting_hdf_fname"] = self.parent.config["files"]["hdf_fname"]
        self.parent.PlotsGUI.refresh_all_run_lists()
        self.parent.PlotsGUI.clear_all_fast_y()

    def stop_control(self):
        # check we're not stopped already
        if not self.parent.config['control_active']:
            return

        # stop devices, waiting for threads to finish
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                dev.active.clear()

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()

        # stop monitoring
        self.parent.MonitoringGUI.stop_monitoring()

        # stop all plots
        self.parent.PlotsGUI.stop_all_plots()

        # update status
        self.parent.config['control_active'] = False
        self.status_label.setText("Recording finished")

class MonitoringGUI(qt.QWidget):
    def __init__(self, parent):
        super(qt.QWidget, self).__init__(parent)
        self.parent = parent
        self.place_GUI_elements()
        self.place_device_specific_items()

    def place_GUI_elements(self):
        # main frame for all MonitoringGUI elements
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        # monitoring controls frame
        control_frame = LabelFrame(self.main_frame, "Controls", type="hbox")

        # general monitoring controls
        gen_f = LabelFrame(control_frame, "General", maxWidth=200)
        gen_f.addWidget(qt.QLabel("Loop delay [s]:"), 0, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["monitoring_dt"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("general", "monitoring_dt", val)
            )
        gen_f.addWidget(qle, 0, 1)

        qcb = qt.QCheckBox("InfluxDB enabled")
        qcb.setCheckState(True if self.parent.config["influxdb"]["enabled"] in ["1", "True"] else False)
        qcb.stateChanged[int].connect(
                lambda val: self.change_config("influxdb", "enabled", val)
            )
        gen_f.addWidget(qcb, 1, 0)

        # InfluxDB controls
        db_f = LabelFrame(control_frame, "InfluxDB", maxWidth=200)

        db_f.addWidget(qt.QLabel("Host IP"), 0, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["influxdb"]["host"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "host", val)
            )
        db_f.addWidget(qle, 0, 1)

        db_f.addWidget(qt.QLabel("Port"), 1, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["influxdb"]["port"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "port", val)
            )
        db_f.addWidget(qle, 1, 1)

        db_f.addWidget(qt.QLabel("Username"), 2, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["influxdb"]["username"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "username", val)
            )
        db_f.addWidget(qle, 2, 1)

        db_f.addWidget(qt.QLabel("Password"), 3, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["influxdb"]["password"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "password", val)
            )
        db_f.addWidget(qle, 3, 1)

        # for displaying warnings
        w_f = LabelFrame(control_frame, "Warnings")
        self.warnings_label = qt.QLabel("(no warnings)")
        w_f.addWidget(self.warnings_label, 3, 0)

        # disk space usage
        w_f.addWidget(qt.QLabel("Disk usage:"), 2, 0)
        self.free_qpb = qt.QProgressBar()
        w_f.addWidget(self.free_qpb, 2, 1)

        # frame for device data
        self.dev_f = ScrollableLabelFrame(self.main_frame, "Devices")

    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

    def update_warnings(self, warnings):
        self.warnings_label.setText(warnings)

    def place_device_specific_items(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            dev.monitoring_GUI_elements = {}
            df = LabelFrame(
                    self.dev_f, dev.config["label"],
                    row=dev.config["monitoring_row"],
                    col=dev.config["monitoring_column"]
                )

            # length of the data queue
            df.addWidget(
                    qt.QLabel("Queue length:"),
                    0, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.monitoring_GUI_elements["qsize"] = qt.QLabel("N/A")
            df.addWidget(
                    dev.monitoring_GUI_elements["qsize"],
                    0, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # NaN count
            df.addWidget(
                    qt.QLabel("NaN count:"),
                    1, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.monitoring_GUI_elements["NaN_count"] = qt.QLabel("N/A")
            df.addWidget(
                    dev.monitoring_GUI_elements["NaN_count"],
                    1, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # column names
            dev.col_names_list = dev.config["attributes"]["column_names"].split(',')
            dev.col_names_list = [x.strip() for x in dev.col_names_list]
            dev.column_names = "\n".join(dev.col_names_list)
            dev.monitoring_GUI_elements["col_names"] = qt.QLabel(
                    dev.column_names, alignment = PyQt5.QtCore.Qt.AlignRight
                )
            df.addWidget(dev.monitoring_GUI_elements["col_names"], 2, 0)

            # data
            dev.monitoring_GUI_elements["data"] = qt.QLabel("(no data)")
            df.addWidget(
                    dev.monitoring_GUI_elements["data"],
                    2, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units = "\n".join(units)
            dev.monitoring_GUI_elements["units"] = qt.QLabel(dev.units)
            df.addWidget(dev.monitoring_GUI_elements["units"], 2, 2, alignment = PyQt5.QtCore.Qt.AlignLeft)

            # latest event / command sent to device & its return value
            df.addWidget(
                    qt.QLabel("Last event:"),
                    3, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.monitoring_GUI_elements["events"] = qt.QLabel("(no events)")
            df.addWidget(
                    dev.monitoring_GUI_elements["events"],
                    3, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

    def update_col_names_and_units(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            # column names
            dev.col_names_list = dev.config["attributes"]["column_names"].split(',')
            dev.col_names_list = [x.strip() for x in dev.col_names_list]
            dev.column_names = "\n".join(dev.col_names_list)
            dev.monitoring_GUI_elements["col_names"].setText(dev.column_names)

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units = "\n".join(units)
            dev.monitoring_GUI_elements["units"].setText(dev.units)

    def start_monitoring(self):
        self.monitoring = Monitoring(self.parent)
        self.monitoring.active.set()
        self.monitoring.start()

    def stop_monitoring(self):
        if self.monitoring.active.is_set():
            self.monitoring.active.clear()

class PlotsGUI(qt.QWidget):
    def __init__(self, parent):
        super(qt.QWidget, self).__init__(parent)
        self.parent = parent
        self.all_plots = {}
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all PlotsGUI elements
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        # controls for all plots
        ctrls_f = LabelFrame(self.main_frame, "Controls")

        pb = qt.QPushButton("Start all")
        pb.clicked[bool].connect(self.start_all_plots)
        ctrls_f.addWidget(pb, 0, 0)

        pb = qt.QPushButton("Stop all")
        pb.clicked[bool].connect(self.stop_all_plots)
        ctrls_f.addWidget(pb, 0, 1)

        pb = qt.QPushButton("Delete all")
        pb.clicked[bool].connect(self.destroy_all_plots)
        ctrls_f.addWidget(pb, 0, 2)

        # for setting refresh rate of all plots
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setText("plot refresh rate")
        self.dt_qle.setToolTip("Delay between updating all plots, i.e. smaller dt means faster plot refresh rate.")
        self.dt_qle.textChanged[str].connect(self.set_all_dt)
        ctrls_f.addWidget(self.dt_qle, 0, 3)

        #for setting x limits of all plots

        qle = qt.QLineEdit()
        qle.setText("x0")
        qle.setToolTip("Set the index of first point to plot for all plots.")
        qle.textChanged[str].connect(self.set_all_x0)
        ctrls_f.addWidget(qle, 1, 3)

        qle = qt.QLineEdit()
        qle.setText("x1")
        qle.setToolTip("Set the index of last point to plot for all plots.")
        qle.textChanged[str].connect(self.set_all_x1)
        ctrls_f.addWidget(qle, 1, 4)

        # button to add plot in the specified column
        qle = qt.QLineEdit()
        qle.setText("col for new plots")
        qle.setToolTip("Column to place new plots in.")
        ctrls_f.addWidget(qle, 0, 4)
        pb = qt.QPushButton("New plot ...")
        pb.setToolTip("Add a new plot in the specified column.")
        ctrls_f.addWidget(pb, 0, 5)
        pb.clicked[bool].connect(lambda val, qle=qle : self.add_plot(col=qle.text()))

        # the HDF file we're currently plotting from
        ctrls_f.addWidget(qt.QLabel("HDF file"), 1, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["files"]["plotting_hdf_fname"])
        qle.textChanged[str].connect(lambda val: self.change_config("files", "plotting_hdf_fname", val))
        ctrls_f.addWidget(qle, 1, 1)
        pb = qt.QPushButton("Open....")
        ctrls_f.addWidget(pb, 1, 2)
        pb.clicked[bool].connect(lambda val, qle=qle: self.open_file("files", "plotting_hdf_fname", qle))

        # for saving plot configuration
        ctrls_f.addWidget(qt.QLabel("Plot config file:"), 2, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["files"]["plotting_config_fname"])
        qle.textChanged[str].connect(lambda val: self.change_config("files", "plotting_config_fname", val))
        ctrls_f.addWidget(qle, 2, 1)

        pb = qt.QPushButton("Open....")
        ctrls_f.addWidget(pb, 2, 2)
        pb.clicked[bool].connect(lambda val, qle=qle: self.open_file("files", "plotting_config_fname", qle))

        pb = qt.QPushButton("Save plots")
        ctrls_f.addWidget(pb, 2, 3)
        pb.clicked[bool].connect(lambda val, fname=qle.text(): self.save_plots(fname))

        pb = qt.QPushButton("Load plots")
        ctrls_f.addWidget(pb, 2, 4)
        pb.clicked[bool].connect(lambda val, fname=qle.text(): self.load_plots(fname))

        # frame to place all the plots in
        self.plots_f = LabelFrame(self.main_frame, "Plots")

        # prevent the above from being stretched across the whole screen
        self.main_frame.addStretch()

        # add one plot
        self.add_plot()

    def add_plot(self, row=None, col=None):
        # find location for the plot if not given to the function
        try:
            col = int(col)
        except (ValueError, TypeError):
            col = 0
        try:
            row = int(row) if row else max([ r for r in self.all_plots.setdefault(col, {0:None}) ]) + 2
        except ValueError:
            logging.error("Row name not valid.")
            return

        # frame for the plot
        fr = LabelFrame(self.plots_f, "", row=row, col=col)

        # place the plot
        plot = Plotter(fr, self.parent)
        plot.config["row"], plot.config["col"] = row, col
        self.all_plots.setdefault(col, {0:None}) # check the column is in the dict, else add it
        self.all_plots[col][row] = plot

        return plot

    def open_file(self, sect, config, qle):
        val = qt.QFileDialog.getSaveFileName(self, "Select file")[0]
        if not val:
           return
        self.parent.config[sect][config] = val
        qle.setText(val)

    def start_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.start_animation()

    def stop_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.stop_animation()

    def destroy_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.destroy()

    def set_all_x0(self, x0):
        # sanity check
        try:
            x0 = int(x0)
        except ValueError:
            x0 = 0

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.change_config("x0", x0)
                    plot.x0_qle.setText(str(x0))

    def set_all_x1(self, x1):
        # sanity check
        try:
            x1 = int(x1)
        except ValueError:
            x1 = -1

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.change_config("x1", x1)
                    plot.x1_qle.setText(str(x1))

    def set_all_dt(self, dt):
        # sanity check
        try:
            dt = float(dt)
            if dt < 0.002:
                logging.warning("Plot dt too small.")
                raise ValueError
        except ValueError:
            dt = float(self.parent.config["general"]["default_plot_dt"])

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.change_config("dt", dt)
                    plot.dt_qle.setText(str(dt))

    def refresh_all_run_lists(self):
        # get list of runs
        with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
            runs = list(f.keys())

        # update all run QComboBoxes
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.refresh_parameter_lists()
                    update_QComboBox(
                            cbx     = plot.run_cbx,
                            options = runs,
                            value   = runs[-1]
                        )

    def clear_all_fast_y(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.fast_y = []

    def save_plots(self, dt):
        # put essential information about plot configuration in a dictionary
        plot_configs = {}
        for col, col_plots in self.all_plots.items():
            plot_configs[col] = {}
            for row, plot in col_plots.items():
                if plot:
                    plot_configs[col][row] = plot.config

        # save this info as a pickled dictionary
        with open(self.parent.config["files"]["plotting_config_fname"], "wb") as f:
            pickle.dump(plot_configs, f)

    def load_plots(self, dt):
        # remove all plots
        self.destroy_all_plots()

        # read pickled plot config
        with open(self.parent.config["files"]["plotting_config_fname"], "rb") as f:
            plot_configs = pickle.load(f)

        # re-create all plots
        for col, col_plots in plot_configs.items():
            for row, config in col_plots.items():
                # add a plot
                plot = self.add_plot(row, col)

                # restore configuration
                plot.config = config

                # set the GUI elements to the restored values
                plot.x0_qle.setText(config["x0"])
                plot.x1_qle.setText(config["x1"])
                plot.y0_qle.setText(config["y0"])
                plot.y1_qle.setText(config["y1"])
                plot.dt_qle.setText(str(config["dt"]))
                plot.fn_qle.setText(config["f(y)"])
                plot.avg_qle.setText(str(config["n_average"]))
                plot.refresh_parameter_lists(select_defaults=False)

class Plotter(qt.QWidget):
    def __init__(self, frame, parent):
        super(qt.QWidget, self).__init__()
        self.f = frame
        self.parent = parent

        self.plot = None
        self.curve = None
        self.fast_y = []

        self.config = {
                "active"            : False,
                "fn"                : False,
                "log"               : False,
                "symbol"            : None,
                "plot_drawn"        : False,
                "animation_running" : False,
                "from_HDF"          : False,
                "n_average"         : 1,
                "f(y)"              : "2*y",
                "device"            : "Select device ...",
                "run"               : "Select run ...",
                "x"                 : "Select x ...",
                "y"                 : "Select y ...",
                "z"                 : "divide by?",
                "x0"                : "x0",
                "x1"                : "x1",
                "y0"                : "y0",
                "y1"                : "y1",
                "dt"                : float(self.parent.config["general"]["default_plot_dt"]),
            }

        self.place_GUI_elements()

    def place_GUI_elements(self):
        # select device
        self.dev_cbx = qt.QComboBox()
        self.dev_cbx.activated[str].connect(lambda val: self.change_config("device", val))
        self.dev_cbx.activated[str].connect(lambda val: self.refresh_parameter_lists())
        update_QComboBox(
                cbx     = self.dev_cbx,
                options = [dev_name.strip() for dev_name in self.parent.devices],
                value   = self.config["device"]
            )
        self.f.addWidget(self.dev_cbx, 0, 0)

        # get list of runs
        with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
            runs = list(f.keys())

        # select run
        self.run_cbx = qt.QComboBox()
        self.run_cbx.activated[str].connect(lambda val: self.change_config("run", val))
        update_QComboBox(
                cbx     = self.run_cbx,
                options = runs,
                value   = runs[-1]
            )
        self.f.addWidget(self.run_cbx, 0, 1)

        # select x, y, and z

        self.x_cbx = qt.QComboBox()
        self.x_cbx.setToolTip("Select the independent variable.")
        self.x_cbx.activated[str].connect(lambda val: self.change_config("x", val))
        self.f.addWidget(self.x_cbx, 1, 0)

        self.y_cbx = qt.QComboBox()
        self.y_cbx.setToolTip("Select the dependent variable.")
        self.y_cbx.activated[str].connect(lambda val: self.change_config("y", val))
        self.f.addWidget(self.y_cbx, 1, 1)

        self.z_cbx = qt.QComboBox()
        self.z_cbx.setToolTip("Select the variable to divide y by.")
        self.z_cbx.activated[str].connect(lambda val: self.change_config("z", val))
        self.f.addWidget(self.z_cbx, 1, 2)

        self.refresh_parameter_lists()

        # plot range controls
        self.x0_qle = qt.QLineEdit()
        self.x0_qle.setMaximumWidth(50)
        self.f.addWidget(self.x0_qle, 1, 3)
        self.x0_qle.setText(self.config["x0"])
        self.x0_qle.setToolTip("x0 = index of first point to plot")
        self.x0_qle.textChanged[str].connect(lambda val: self.change_config("x0", val))

        self.x1_qle = qt.QLineEdit()
        self.x1_qle.setMaximumWidth(50)
        self.f.addWidget(self.x1_qle, 1, 4)
        self.x1_qle.setText(self.config["x1"])
        self.x1_qle.setToolTip("x1 = index of last point to plot")
        self.x1_qle.textChanged[str].connect(lambda val: self.change_config("x1", val))

        self.y0_qle = qt.QLineEdit()
        self.y0_qle.setMaximumWidth(50)
        self.f.addWidget(self.y0_qle, 1, 5)
        self.y0_qle.setText(self.config["y0"])
        self.y0_qle.setToolTip("y0 = lower y limit")
        self.y0_qle.textChanged[str].connect(lambda val: self.change_config("y0", val))

        self.y1_qle = qt.QLineEdit()
        self.y1_qle.setMaximumWidth(50)
        self.f.addWidget(self.y1_qle, 1, 6)
        self.y1_qle.setText(self.config["y1"])
        self.y1_qle.setToolTip("y1 = upper y limit")
        self.y1_qle.textChanged[str].connect(lambda val: self.change_config("y1", val))

        # plot refresh rate
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setMaximumWidth(50)
        self.dt_qle.setText("dt")
        self.dt_qle.setToolTip("Delay between updating the plot, i.e. smaller dt means faster plot refresh rate.")
        self.dt_qle.textChanged[str].connect(lambda val: self.change_config("dt", val))
        self.f.addWidget(self.dt_qle, 1, 7)

        # start button
        self.start_pb = qt.QPushButton("Start")
        self.start_pb.setMaximumWidth(50)
        self.start_pb.clicked[bool].connect(self.start_animation)
        self.f.addWidget(self.start_pb, 0, 3)

        # HDF/Queue
        self.HDF_pb = qt.QPushButton("HDF")
        self.HDF_pb.setToolTip("Force reading the data from HDF instead of the queue.")
        self.HDF_pb.setMaximumWidth(50)
        self.HDF_pb.clicked[bool].connect(self.toggle_HDF_or_queue)
        self.f.addWidget(self.HDF_pb, 0, 4)

        # toggle log/lin
        pb = qt.QPushButton("Log/Lin")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_log_lin)
        self.f.addWidget(pb, 0, 5)

        # toggle lines/points
        pb = qt.QPushButton("\u26ab / \u2014")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_points)
        self.f.addWidget(pb, 0, 6)

        # for displaying a function of the data
        self.fn_qle = qt.QLineEdit()
        self.fn_qle.setText(self.config["f(y)"])
        self.fn_qle.setToolTip("Apply the specified function before plotting the data.")
        self.fn_qle.textChanged[str].connect(lambda val: self.change_config("f(y)", val))
        self.f.addWidget(self.fn_qle, 0, 2)
        pb = qt.QPushButton("f(y)")
        pb.setToolTip("Apply the specified function before plotting the data.")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_fn)
        self.f.addWidget(pb, 0, 7)

        # for averaging last n curves
        self.avg_qle = qt.QLineEdit()
        self.avg_qle.setMaximumWidth(50)
        self.avg_qle.setToolTip("Enter the number of traces to average. Default = 1, i.e. no averaging.")
        self.avg_qle.setText("avg?")
        self.avg_qle.textChanged[str].connect(lambda val: self.change_config("n_average", val, typ=int))
        self.f.addWidget(self.avg_qle, 1, 8)

        # button to delete plot
        pb = qt.QPushButton("\u274c")
        pb.setMaximumWidth(50)
        pb.setToolTip("Delete the plot")
        self.f.addWidget(pb, 0, 8)
        pb.clicked[bool].connect(lambda val: self.destroy())

    def refresh_parameter_lists(self, select_defaults=True):
        # check device is valid, else select the first device on the list
        if self.config["device"] in self.parent.devices:
            self.dev = self.parent.devices[self.config["device"]]
        else:
            self.config["device"] = list(self.parent.devices.keys())[0]
            self.dev_cbx.setCurrentText(self.config["device"])
            self.dev = self.parent.devices[self.config["device"]]

        # select latest run
        with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
            self.config["run"] = list(f.keys())[-1]
            self.run_cbx.setCurrentText(self.config["run"])

        # get parameters
        self.param_list = [x.strip() for x in self.dev.config["attributes"]["column_names"].split(',')]
        if not self.param_list:
            logging.warning("Plot error: No parameters to plot.")
            return

        # select x, y, and z
        if select_defaults:
            self.config["x"] = self.param_list[0]
            if len(self.param_list) > 1:
                self.config["y"] = self.param_list[1]
            else:
                self.config["y"] = self.param_list[0]

        # update x, y, and z QComboBoxes
        update_QComboBox(
                cbx     = self.x_cbx,
                options = self.param_list,
                value   = self.config["x"]
            )
        update_QComboBox(
                cbx     = self.y_cbx,
                options = self.param_list,
                value   = self.config["y"]
            )
        update_QComboBox(
                cbx     = self.z_cbx,
                options = ["divide by?"] + self.param_list,
                value   = self.config["z"]
            )

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        self.x, self.y = [], []

    def change_config(self, config, val, typ=str):
        if typ == str:
            self.config[config] = val
        else:
            try:
                self.config[config] = typ(val)
            except (TypeError,ValueError) as err:
                logging.warning("Plot error: Invalid parameter: " + str(err))

    def parameters_good(self):
        # check device is valid
        if self.config["device"] in self.parent.devices:
            self.dev = self.parent.devices[self.config["device"]]
        else:
            self.stop_animation()
            logging.warning("Plot error: Invalid device: " + self.config["device"])
            return False

        # check run is valid
        try:
            with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
                if not self.config["run"] in f.keys():
                    self.stop_animation()
                    logging.warning("Plot error: Run not found in the HDF file:" + self.config["run"])
                    return False
        except OSError:
                self.stop_animation()
                logging.warning("Plot error: Not a valid HDF file.")
                return False

        # check dataset exists in the run
        with h5py.File(self.parent.config["files"]["hdf_fname"], 'r') as f:
            try:
                grp = f[self.config["run"] + "/" + self.dev.config["path"]]
            except KeyError:
                if time.time() - self.parent.config["time_offset"] > 5:
                    logging.warning("Plot error: Dataset not found in this run.")
                self.stop_animation()
                return False

        # check parameters are valid
        if not self.config["x"] in self.param_list:
            logging.warning("Plot warning: x not valid.")
            return False

        if not self.config["y"] in self.param_list:
            logging.warning("Plot error: y not valid.")
            return False

        # return 
        return True

    def get_raw_data_from_HDF(self):
        with h5py.File(self.parent.config["files"]["hdf_fname"], 'r') as f:
            grp = f[self.config["run"] + "/" + self.dev.config["path"]]

            if self.dev.config["slow_data"]:
                dset = grp[self.dev.config["name"]]
                x = dset[:, self.param_list.index(self.config["x"])]
                y = dset[:, self.param_list.index(self.config["y"])]

                # divide y by z (if applicable)
                if self.config["z"] in self.param_list:
                    y /= dset[:, self.param_list.index(self.config["z"])]

            if not self.dev.config["slow_data"]:
                # find the latest record
                rec_num = len(grp) - 1
                self.record_number.set(rec_num)

                # get the latest curve
                dset = grp[self.dev.config["name"] + "_" + str(rec_num)]
                x = np.arange(dset.shape[0])
                y = dset[:, self.param_list.index(self.config["y"])]

                # divide y by z (if applicable)
                if self.config["z"] in self.param_list:
                    y /= dset[:, self.param_list.index(self.config["z"])]

                # average last n curves (if applicable)
                for i in range(self.config["n_average"] - 1):
                    dset = grp[self.dev.config["name"] + "_" + str(rec_num-i)]
                    if self.config["z"] in self.param_list:
                        y += dset[:, self.param_list.index(self.config["y"])] \
                                / dset[:, self.param_list.index(self.config["z"])]
                    else:
                        y += dset[:, self.param_list.index(self.config["y"])]
                y /= self.config["n_average"]

        return x, y

    def get_raw_data_from_queue(self):
        # for slow data: copy the queue contents into a np array
        if self.dev.config["slow_data"]:
            dset = np.empty((len(self.dev.plots_queue), *self.dev.config["shape"]))
            for i in range(len(self.dev.plots_queue)):
                dset[i] = self.dev.plots_queue[i]
            x = dset[:, self.param_list.index(self.config["x"])]
            y = dset[:, self.param_list.index(self.config["y"])]

        # for fast data: return only the latest value
        if not self.dev.config["slow_data"]:
            dset = self.dev.plots_queue.popleft()
            x = np.arange(dset.shape[0])
            y = dset[:, self.param_list.index(self.config["y"])]

        # divide y by z (if applicable)
        if self.config["z"] in self.param_list:
            y /= dset[:, self.param_list.index(self.config["z"])]

        return x, y

    def get_data(self):
        # decide where to get data from
        if self.dev.config["plots_queue_maxlen"] < 1\
                or not self.parent.config['control_active']\
                or self.config["from_HDF"]:
            data = self.get_raw_data_from_HDF()
        else:
            data = self.get_raw_data_from_queue()

        x, y = data[0], data[1]

        # select indices for subsetting
        try:
            x0 = int(float(self.config["x0"]))
            x1 = int(float(self.config["x1"]))
        except ValueError as err:
            x0, x1 = 0, -1
        if x0 >= x1:
            if x1 >= 0:
                x0, x1 = 0, -1
        if x1 >= len(x) - 1:
            x0, y1 = 0, -1

        # verify data shape
        if not x.shape == y.shape:
            logging.warning("Plot error: data shapes not matching.")
            return None

        # if not applying f(y), return the data ...
        if not self.config["fn"]:
            return x[x0:x1], y[x0:x1]

        # ... else apply f(y) to the data

        if self.dev.config["slow_data"]:
            try:
                y_fn = eval(self.config["f(y)"])
                if not x.shape == y_fn.shape:
                    raise ValueError("x.shape != y_fn.shape")
            except Exception as err:
                logging.warning(str(err))
                y_fn = y
            else:
                return x[x0:x1], y_fn[x0:x1]

        if not self.dev.config["slow_data"]:
            try:
                y_fn = eval(self.config["f(y)"])
                if not isinstance(y_fn, float):
                    raise TypeError("isinstance(y_fn, float) == False")
            except Exception as err:
                logging.warning(str(err))
                return x[x0:x1], y[x0:x1]
            else:
                self.fast_y.append()
                return np.arange(len(self.fast_y)), np.array(self.fast_y)

    def replot(self):
        # check parameters
        if not self.parameters_good():
            logging.warning("Plot warning: bad parameters.")
            return

        # get data
        data = self.get_data()
        if not data:
            logging.warning("Plot warning: no data returned.")
            return

        # plot data
        if not self.plot:
            self.plot = pg.PlotWidget()
            self.plot.showGrid(True, True)
            self.f.addWidget(self.plot, 2, 0, 1, 9)
        if not self.curve:
            self.curve = self.plot.plot(*data, symbol=self.config["symbol"])
        else:
            self.curve.setData(*data)

        # set y limits
        try:
            y0 = float(self.config["y0"])
            y1 = float(self.config["y1"])
        except ValueError:
            self.plot.enableAutoRange()
        else:
            self.plot.setYRange(y0, y1)

    class PlotUpdater(PyQt5.QtCore.QThread):
        signal = PyQt5.QtCore.pyqtSignal()

        def __init__(self, parent, config):
            self.parent = parent
            self.config = config
            super().__init__()

        def run(self):
            while self.config["active"]:
                self.signal.emit()

                # loop delay
                try:
                    dt = float(self.config["dt"])
                    if dt < 0.002:
                        logging.warning("Plot dt too small.")
                        raise ValueError
                except ValueError:
                    dt = float(self.parent.config["general"]["default_plot_dt"])
                time.sleep(dt)

    def start_animation(self):
        # start animation
        self.thread = self.PlotUpdater(self.parent, self.config)
        self.thread.start()
        self.thread.signal.connect(self.replot)

        # update status
        self.config["active"] = True

        # change the "Start" button into a "Stop" button
        self.start_pb.setText("Stop")
        self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.stop_animation)

    def stop_animation(self):
        # stop animation
        self.config["active"] = False

        # change the "Stop" button into a "Start" button
        self.start_pb.setText("Start")
        self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.start_animation)

    def destroy(self):
        # get the position of the plot
        row, col = self.config["row"], self.config["col"]

        # remove the plot from the all_plots dict
        self.parent.PlotsGUI.all_plots[col][row] = None

        # remove the GUI elements related to the plot
        self.parent.PlotsGUI.plots_f.itemAtPosition(row, col).widget().setParent(None)

    def toggle_HDF_or_queue(self, state):
        # toggle the config flag
        self.change_config("from_HDF", self.config["from_HDF"]==False)

        # change the button appearance
        if self.config["from_HDF"]:
            self.HDF_pb.setText("Queue")
            self.HDF_pb.setToolTip("Force reading the data from the Queue instead of the HDF file.")
        else:
            self.HDF_pb.setText("HDF")
            self.HDF_pb.setToolTip("Force reading the data from HDF instead of the queue.")

    def toggle_log_lin(self):
        if not self.config["log"]:
            self.config["log"] = True
            self.plot.setLogMode(False, True)
        else:
            self.config["log"] = False
            self.plot.setLogMode(False, False)

    def toggle_points(self):
        if not self.config["symbol"]:
            self.curve.clear()
            self.curve = None
            self.config["symbol"] = 'o'
        else:
            self.curve.clear()
            self.curve = None
            self.config["symbol"] = None

    def toggle_fn(self):
        if not self.config["fn"]:
            self.config["fn"] = True
        else:
            self.config["fn"] = False
            self.fast_y = []

class CentrexGUI(qt.QTabWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app

        # read program configuration
        self.config = {
                "time_offset"    : 0,
                "control_active" : False,
                }
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for config_group, configs in settings.items():
            self.config[config_group] = {}
            for key, val in configs.items():
                self.config[config_group][key] = val

        # GUI elements
        self.ControlGUI = ControlGUI(self)
        self.MonitoringGUI = MonitoringGUI(self)
        self.PlotsGUI = PlotsGUI(self)

        # put them in tabbed interface
        self.setWindowTitle('CENTREX DAQ')
        self.addTab(self.ControlGUI, "Control")
        self.addTab(self.MonitoringGUI, "Monitoring")
        self.addTab(self.PlotsGUI, "Plots")
        self.show()

    def closeEvent(self, event):
        if self.config['control_active']:
            if qt.QMessageBox.question(self, 'Confirm quit',
                "Control running. Do you really want to quit?", qt.QMessageBox.Yes |
                qt.QMessageBox.No, qt.QMessageBox.No) == qt.QMessageBox.Yes:
                self.ControlGUI.stop_control()
                event.accept()
            else:
                event.ignore()

if __name__ == '__main__':
    app = qt.QApplication(sys.argv)
    main_window = CentrexGUI(app)
    sys.exit(app.exec_())
