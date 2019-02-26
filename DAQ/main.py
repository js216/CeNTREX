import re
import PyQt5
import h5py
import time
import pyvisa
import logging
import threading
import numpy as np
import configparser
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

def LabelFrame(parent, label, col=None, row=None, rowspan=1, colspan=1, type="grid"):
    box = qt.QGroupBox(label)
    if type == "grid":
        grid = qt.QGridLayout()
    elif type == "hbox":
        grid = qt.QHBoxLayout()
    elif type == "vbox":
        grid = qt.QVBoxLayout()
    box.setLayout(grid)
    if row or col:
        parent.addWidget(box, row, col, rowspan, colspan)
    else:
        parent.addWidget(box)
    return grid

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
                        self.nan_count.set( int(self.nan_count) + 1)
                elif len(last_data) > 0:
                    self.data_queue.append(last_data)


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
                    "name"              : params["device"]["name"],
                    "label"             : params["device"]["label"],
                    "path"              : params["device"]["path"],
                    "correct_response"  : params["device"]["correct_response"],
                    "slow_data"         : True if params["device"]["slow_data"]=="True" else False,
                    "row"               : int(params["device"]["row"]),
                    "rowspan"           : int(params["device"]["rowspan"]),
                    "monitoring_row"    : int(params["device"]["monitoring_row"]),
                    "column"            : int(params["device"]["column"]),
                    "columnspan"        : int(params["device"]["columnspan"]),
                    "monitoring_column" : int(params["device"]["monitoring_column"]),
                    "constr_params"     : [x.strip() for x in params["device"]["constr_params"].split(",")],
                    "attributes"        : params["attributes"],
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
                            "value"      : True if params[c]["value"] in ["0", "True"] else False
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
                        }

                elif params[c].get("type") == "QLineEdit":
                    ctrls[c] = {
                            "label"      : params[c]["label"],
                            "type"       : params[c]["type"],
                            "row"        : int(params[c]["row"]),
                            "col"        : int(params[c]["col"]),
                            "enter_cmd"  : params[c].get("enter_command"),
                            "value"      : params[c]["value"],
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

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["files"]["config_dir"])
        qle.textChanged[str].connect(lambda val: self.change_config("files", "config_dir", val))
        files_frame.addWidget(qle, 0, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(lambda val, qle=qle: self.open_dir("files", "config_dir", qle))
        files_frame.addWidget(pb, 0, 2)

        # HDF file
        files_frame.addWidget(qt.QLabel("HDF file:"), 1, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["files"]["hdf_fname"])
        qle.textChanged[str].connect(lambda val: self.change_config("files", "hdf_file", val))
        files_frame.addWidget(qle, 1, 1)

        pb = qt.QPushButton("Open...")
        pb.clicked[bool].connect(lambda val, qle=qle: self.open_file("files", "hdf_file", qle))
        files_frame.addWidget(pb, 1, 2)

        # HDF writer loop delay
        files_frame.addWidget(qt.QLabel("HDF writer loop delay:"), 2, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["hdf_loop_delay"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "hdf_loop_delay", val))
        files_frame.addWidget(qle, 2, 1)

        # run name
        files_frame.addWidget(qt.QLabel("Run name:"), 3, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["run_name"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "run_name", val))
        files_frame.addWidget(qle, 3, 1)

        ########################################
        # devices
        ########################################

        cmd_frame = LabelFrame(self.main_frame, "Send a custom command")

        # the control to send a custom command to a specified device
        cmd_frame.addWidget(qt.QLabel("Cmd:"), 0, 0)

        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["custom_command"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "custom_command", val))
        cmd_frame.addWidget(qle, 0, 1)

        cbx = qt.QComboBox()
        dev_list = [dev_name for dev_name in self.parent.devices]
        cbx.addItem(self.parent.config["general"]["custom_device"])
        if not dev_list:
            cbx.addItem("No devices!")
        else:
            for dev_name in dev_list:
                cbx.addItem(dev_name)
        cbx.activated[str].connect(lambda val: self.change_config("general", "custom_device", val))
        cmd_frame.addWidget(cbx, 0, 2)

        pb = qt.QPushButton("Send")
        pb.clicked[bool].connect(self.queue_custom_command)
        cmd_frame.addWidget(pb, 0, 3)

        # button to refresh the list of COM ports
        pb = qt.QPushButton("Refresh COM ports")
        pb.clicked[bool].connect(self.refresh_COM_ports)
        cmd_frame.addWidget(pb, 0, 4)

        devices_frame = LabelFrame(self.main_frame, "Devices")

        # make GUI elements for all devices
        for dev_name, dev in self.parent.devices.items():
            df = LabelFrame(
                    devices_frame,
                    dev.config["label"],
                    dev.config["column"],
                    dev.config["row"]
                )

            # the button to reload attributes
            pb = qt.QPushButton("Attrs")
            pb.clicked[bool].connect(lambda val, dev=dev : self.reload_attrs(dev))
            df.addWidget(pb, 0, 20)

            # device-specific controls
            for c_name, c in dev.config["controls"].items():

                # place QCheckBoxes
                if c["type"] == "QCheckBox":
                    c["QCheckBox"] = qt.QCheckBox(c["label"])
                    c["QCheckBox"].setCheckState(c["value"])
                    c["QCheckBox"].setTristate(False)
                    c["QCheckBox"].stateChanged[int].connect(
                            lambda state, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, state)
                        )
                    df.addWidget(c["QCheckBox"], c["row"], c["col"])

                # place QPushButtons
                elif c["type"] == "QPushButton":
                    c["QPushButton"] = qt.QPushButton(c["label"])
                    c["QPushButton"].clicked[bool].connect(
                            lambda state, dev=dev, cmd=c["cmd"]:
                                self.queue_command(dev, cmd+"()")
                        )
                    df.addWidget(c["QPushButton"], c["row"], c["col"])

                # place QLineEdits
                elif c["type"] == "QLineEdit":
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )
                    c["QLineEdit"] = qt.QLineEdit()
                    c["QLineEdit"].setText(c["value"])
                    c["QLineEdit"].textChanged[str].connect(
                            lambda text, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, text)
                        )
                    df.addWidget(c["QLineEdit"], c["row"], c["col"])

                # place QComboBoxes
                elif c["type"] == "QComboBox":
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )

                    c["QComboBox"] = qt.QComboBox()
                    c["QComboBox"].setEditable(True)
                    if len(c["options"]) < 1:
                        c["QComboBox"].addItem(c["value"])
                    else:
                        for option in c["options"]:
                            c["QComboBox"].addItem(option)
                    c["QComboBox"].setCurrentText(c["value"])
                    c["QComboBox"].activated[str].connect(
                            lambda text, dev=dev, config=c_name:
                                self.change_dev_control(dev, config, text)
                        )
                    df.addWidget(c["QComboBox"], c["row"], c["col"])

    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

    def change_dev_control(self, dev, config, val):
        dev.config["controls"][config]["value"] = val

    def open_file(self, sect, config, qle):
        val = qt.QFileDialog.getSaveFileName(self, "Select file")[0]
        if not val:
           return
        self.parent.config[sect][config] = val
        qle.setText(val)

    def open_dir(self, sect, config, qle):
        val = str(qt.QFileDialog.getExistingDirectory(self, "Select Directory"))
        if not val:
           return
        self.parent.config[sect][config] = val
        qle.setText(val)

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

    def reload_attrs(self, dev):
        # read attributes from file
        params = configparser.ConfigParser()
        params.read(dev.config["config_fname"])
        dev.config["attributes"] = params["attributes"]

        # display the new attributes in a message box
        attrs = ""
        for attr_name,attr in dev.config["attributes"].items():
            attrs += attr_name + ": " + str(attr) + "\n\n"
        message_box("Device attributes", "New device attributes:", attrs)

    def start_control(self):
        # check we're not running already
        if self.parent.config['control_active']:
            return

        # select the time offset
        self.parent.config["time_offset"] = time.time()

        # setup & check connections of all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["value"]:
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

        # make all plots display the current run and file
        self.parent.config["files"]["plotting_hdf_fname"] = self.parent.config["files"]["hdf_fname"]
        self.parent.PlotsGUI.refresh_all_run_lists()

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
        gen_f = LabelFrame(control_frame, "General")
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
        db_f = LabelFrame(control_frame, "InfluxDB")

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

    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

    def update_warnings(self, warnings):
        self.warnings_label.setText(warnings)

    def place_device_specific_items(self):
        # frame for device data
        self.dev_f = LabelFrame(self.main_frame, "Devices")

        # device-specific text
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
                    dev.monitoring_GUI_elements["qsize"],
                    1, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # column names
            dev.col_names_list = dev.config["attributes"]["column_names"].split(',')
            dev.col_names_list = [x.strip() for x in dev.col_names_list]
            dev.column_names = "\n".join(dev.col_names_list)
            df.addWidget(
                    qt.QLabel(
                        dev.column_names,
                        alignment = PyQt5.QtCore.Qt.AlignRight,
                        ),
                    2, 0,
                )

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
            df.addWidget(
                    qt.QLabel(dev.units),
                    2, 2,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

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
        qle = qt.QLineEdit()
        qle.setText("plot refresh rate")
        qle.textChanged[str].connect(self.set_all_dt)
        ctrls_f.addWidget(qle, 0, 3)

        # button to add plot in the specified column
        qle = qt.QLineEdit()
        qle.setText("col for new plots")
        ctrls_f.addWidget(qle, 0, 4)
        pb = qt.QPushButton("New plot ...")
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

    def set_all_dt(self, dt):
        # sanity check
        try:
            dt = float(dt)
            if dt < 0.002:
                logging.warning("Plot dt too small.")
                raise ValueError
        except ValueError:
            dt = float(self.parent.config["general"]["default_plot_dt"])

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

    def save_plots(self, dt):
        pass # TODO

    def load_plots(self, dt):
        pass # TODO

class Plotter(qt.QWidget):
    def __init__(self, frame, parent):
        super(qt.QWidget, self).__init__()
        self.f = frame
        self.parent = parent
        self.plot = None
        self.config = {
                "active"            : False,
                "fn"                : False,
                "log"               : False,
                "points"            : False,
                "plot_drawn"        : False,
                "animation_running" : False,
                "device"            : "Select device ...",
                "run"               : "Select run ...",
                "x"                 : "Select x value ...",
                "y"                 : "Select y value ...",
                "x0"                : "Select x0 value ...",
                "x1"                : "Select x1 value ...",
                "y0"                : "Select y0 value ...",
                "y1"                : "Select y1 value ...",
                "dt"                : float(self.parent.config["general"]["default_plot_dt"]),
            }
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # select device
        self.dev_cbx = qt.QComboBox()
        self.dev_cbx.activated[str].connect(lambda val: self.change_config("device", val))
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

        # select x and y

        self.x_cbx = qt.QComboBox()
        self.x_cbx.activated[str].connect(lambda val: self.change_config("x", val))
        self.f.addWidget(self.x_cbx, 1, 0)

        self.y_cbx = qt.QComboBox()
        self.y_cbx.activated[str].connect(lambda val: self.change_config("y", val))
        self.f.addWidget(self.y_cbx, 1, 1)

        self.refresh_parameter_lists()

        # plot range controls
        qle = qt.QLineEdit()
        self.f.addWidget(qle, 1, 2)
        qle.textChanged[str].connect(lambda val: self.change_config("x0", val))

        qle = qt.QLineEdit()
        self.f.addWidget(qle, 1, 3)
        qle.textChanged[str].connect(lambda val: self.change_config("x1", val))

        qle = qt.QLineEdit()
        self.f.addWidget(qle, 1, 4)
        qle.textChanged[str].connect(lambda val: self.change_config("y0", val))

        qle = qt.QLineEdit()
        self.f.addWidget(qle, 1, 5)
        qle.textChanged[str].connect(lambda val: self.change_config("y1", val))

        # plot refresh rate
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setText(str(self.config["dt"]))
        self.dt_qle.textChanged[str].connect(lambda val: self.change_config("dt", val))
        self.f.addWidget(self.dt_qle, 1, 6)

        # start button
        pb = qt.QPushButton("Start")
        pb.clicked[bool].connect(self.start_animation)
        self.f.addWidget(pb, 0, 2)

        # stop button
        pb = qt.QPushButton("Stop")
        pb.clicked[bool].connect(self.stop_animation)
        self.f.addWidget(pb, 0, 3)

        # toggle log/lin
        pb = qt.QPushButton("Log/Lin")
        pb.clicked[bool].connect(self.toggle_log_lin)
        self.f.addWidget(pb, 0, 4)

        # toggle lines/points
        pb = qt.QPushButton("\u26ab / \u2014")
        pb.clicked[bool].connect(self.toggle_points)
        self.f.addWidget(pb, 0, 5)

        # for displaying a function of the data
        pb = qt.QPushButton("f(y)")
        pb.clicked[bool].connect(self.toggle_fn)
        self.f.addWidget(pb, 0, 6)

        # button to delete plot
        pb = qt.QPushButton("\u274c")
        self.f.addWidget(pb, 0, 8)
        pb.clicked[bool].connect(lambda val: self.destroy())

    def refresh_parameter_lists(self):
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

        # update x and y QComboBoxes
        self.config["x"] = self.param_list[0]
        update_QComboBox(
                cbx     = self.x_cbx,
                options = self.param_list,
                value   = self.config["x"]
            )
        if len(self.param_list) > 1:
            self.config["y"] = self.param_list[1]
        else:
            self.config["y"] = self.param_list[0]
        update_QComboBox(
                cbx     = self.y_cbx,
                options = self.param_list,
                value   = self.config["y"]
            )

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        self.x, self.y = [], []

    def change_config(self, config, val):
        self.config[config] = val

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

    def get_data(self):
        with h5py.File(self.parent.config["files"]["hdf_fname"], 'r') as f:
            # get raw data
            grp = f[self.config["run"] + "/" + self.dev.config["path"]]

            if self.dev.config["slow_data"]:
                dset = grp[self.dev.config["name"]]
                x = dset[:, self.param_list.index(self.config["x"])]
                y = dset[:, self.param_list.index(self.config["y"])]

            if not self.dev.config["slow_data"]:
                rec_num = len(grp) - 1
                self.record_number.set(rec_num)
                dset = grp[self.dev.config["name"] + "_" + str(rec_num)]
                x = np.arange(dset.shape[0])
                y = dset[:, self.param_list.index(self.config["y"])]

            # return subset of the data
            try:
                x0 = int(float(self.config["x0"]))
                x1 = int(float(self.config["x1"]))
            except ValueError as err:
                x0, x1 = 0, -1
            if x0 >= x1:
                if x1 >= 0:
                    x0, x1 = 0, -1
            if x1 >= dset.shape[0] - 1:
                x0, y1 = 0, -1

            # verify data shape
            if not x.shape == y.shape:
                logging.warning("Plot error: data shapes not matching.")
                return None

            return x[x0:x1], y[x0:x1]

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
            self.f.addWidget(self.plot, 2, 0, 1, 9)
            self.curve = self.plot.plot(*data)
        else:
            self.curve.setData(*data)

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
        self.thread = self.PlotUpdater(self.parent, self.config)
        self.config["active"] = True
        self.thread.start()
        self.thread.signal.connect(self.replot)

    def stop_animation(self):
        self.config["active"] = False

    def destroy(self):
        self.setParent(None)

    def toggle_log_lin(self):
        pass # TODO

    def toggle_points(self):
        pass # TODO

    def toggle_fn(self):
        pass # TODO

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
