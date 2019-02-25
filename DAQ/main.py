import re
import PyQt5
import h5py
import time
import pyvisa
import logging
import threading
import numpy as np
import configparser
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

def LabelFrame(parent, label, col=None, row=None, type="grid"):
    box = qt.QGroupBox(label)
    if type == "grid":
        grid = qt.QGridLayout()
    elif type == "hbox":
        grid = qt.QHBoxLayout()
    elif type == "vbox":
        grid = qt.QVBoxLayout()
    box.setLayout(grid)
    if row and col:
        parent.addWidget(box, row, col)
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

##########################################################################
##########################################################################
#######                                                 ##################
#######            CONTROL CLASSES                      ##################
#######                                                 ##################
##########################################################################
##########################################################################

class Device(threading.Thread):
    def __init__(self, config):
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
        threading.Thread.__init__(self)
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
                    time.sleep(float(self.config["controls"]["dt"]["value"]))
                except ValueError:
                    time.sleep(1)

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
                        self.parent.GUI_elements["Monitoring"].update_warnings(str(warning))
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
        if not dev.config["single_dataset"]:
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
                if dev.config["single_dataset"]:
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
                if dev.config["single_dataset"]:
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
                time.sleep(float(self.parent.config["general"]["hdf_loop_delay"]))
            except ValueError:
                time.sleep(0.1)

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
                if dev.config["single_dataset"]:
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
                    "single_dataset"    : True if params["device"]["single_dataset"]=="True" else False,
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
                                self.queue_command(dev, cmd)
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
        rl = pyvisa.ResourceManager().list_resources()
        for dev_name, dev in self.parent.devices.items():
            # check device has a COM_port control
            if not dev.config["controls"].get("COM_port"):
                continue

            # update the QComboBox of COM_port options
            cbx = dev.config["controls"]["COM_port"]["QComboBox"]
            COM_var = cbx.currentText()
            cbx.clear()
            for string in rl:
                cbx.addItem(string)
            cbx.setCurrentText(COM_var)

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
        self.parent.GUI_elements["Monitoring"].start_monitoring()

        # update program status
        self.parent.config['control_active'] = True
        self.status_label.setText("Running")

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
        self.parent.GUI_elements["Monitoring"].stop_monitoring()

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
        ctrls_f.addWidget(
                qt.QPushButton("Start all"),
                0, 0
            )
        ctrls_f.addWidget(
                qt.QPushButton("Stop all"),
                0, 1
            )
        ctrls_f.addWidget(
                qt.QPushButton("Delete all"),
                0, 2
            )

        # for setting refresh rate of all plots
        ctrls_f.addWidget(
                qt.QLineEdit(),
                0, 3
            )

        # control to select how many data points to display in a graph (to speed up plotting)
        ctrls_f.addWidget(
                qt.QLineEdit(),
                0, 4
            )

        # button to add add plot in the specified column
        self.col_for_new_plots = 0
        ctrls_f.addWidget(
                qt.QLineEdit(),
                0, 5
            )
        ctrls_f.addWidget(
                qt.QPushButton("New plot ..."),
                0, 6
            )

        # the HDF file we're currently plotting from
        ctrls_f.addWidget(
                qt.QLabel("HDF file"),
                1, 0
            )
        ctrls_f.addWidget(
                qt.QLineEdit(),
                1, 1
            )
        ctrls_f.addWidget(
                qt.QPushButton("Open...."),
                1, 2
            )

        # for saving plot configuration
        ctrls_f.addWidget(
                qt.QLabel("Plot config file:"),
                2, 0
            )
        ctrls_f.addWidget(
                qt.QLineEdit(),
                2, 1
            )
        ctrls_f.addWidget(
                qt.QPushButton("Open...."),
                2, 2
            )
        ctrls_f.addWidget(
                qt.QPushButton("Save plots"),
                2, 3
            )
        ctrls_f.addWidget(
                qt.QPushButton("Load plots"),
                2, 4
            )

        # frame to place all the plots in
        self.plots_f = LabelFrame(self.main_frame, "Plots")

        # add one plot
        self.add_plot()

    def add_plot(self, row=False, col=False):
        # find location for the plot if not given to the function
        if (not row) and (not col):
            col = self.col_for_new_plots
            row = max([ r for r in self.all_plots.setdefault(col, {0:None}) ]) + 2

        # frame for the plot
        fr = LabelFrame(self.plots_f, "", row=row, col=col)

        # place the plot
        plot = Plotter(fr, self.parent)
        self.all_plots.setdefault(col, {0:None}) # check the column is in the dict, else add it
        self.all_plots[col][row] = plot

        # button to delete plot
        plot.f.addWidget(
                qt.QPushButton("\u274c"),
                0, 8
            )

        return plot

class Plotter(qt.QWidget):
    def __init__(self, frame, parent):
        self.f = frame
        self.parent = parent

        # plot settings
        self.fn = False
        self.log = False
        self.points = False
        self.plot_drawn = False
        self.animation_running = False

        # select device
        self.dev_list = [dev_name.strip() for dev_name in self.parent.devices]
        if not self.dev_list:
            self.dev_list = ["Select device ..."]
        dev_select = qt.QComboBox()
        for dev in self.dev_list:
            dev_select.addItem(dev)
        self.f.addWidget(
                dev_select,
                0, 0
            )

        # select run
        self.run_list = ["Select run ..."]
        run_select = qt.QComboBox()
        for run in self.run_list:
            run_select.addItem(run)
        self.f.addWidget(
                run_select,
                0, 1
            )

        # select xcol
        self.xcol_list = ["(select device first)"]
        xcol_select = qt.QComboBox()
        for xcol in self.xcol_list:
            xcol_select.addItem(xcol)
        self.f.addWidget(
                xcol_select,
                1, 0
            )

        # select ycol
        self.ycol_list = ["(select device first)"]
        ycol_select = qt.QComboBox()
        for ycol in self.ycol_list:
            ycol_select.addItem(ycol)
        self.f.addWidget(
                ycol_select,
                1, 1
            )

        # plot range controls
        x0 = qt.QLineEdit()
        self.f.addWidget(x0, 1, 2)
        x1 = qt.QLineEdit()
        self.f.addWidget(x1, 1, 3)
        y0 = qt.QLineEdit()
        self.f.addWidget(y0, 1, 4)
        y1 = qt.QLineEdit()
        self.f.addWidget(y1, 1, 5)

        # control buttons
        dt = qt.QLineEdit()
        self.f.addWidget(dt, 1, 6)
        self.f.addWidget(
                qt.QPushButton("\u25b6"),
                0, 2
            )
        self.f.addWidget(
                qt.QPushButton("Log/Lin"),
                0, 3
            )
        self.f.addWidget(
                qt.QPushButton("\u26ab / \u2014"),
                0, 4
            )

        # for displaying a function of the data
        self.f.addWidget(
                qt.QPushButton("f(y)"),
                0, 5
            )

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        self.x, self.y = [], []

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

        # GUI elements in a tabbed interface
        self.GUI_elements = {
                "Control"    : ControlGUI(self),
                "Monitoring" : MonitoringGUI(self),
                "Plots"      : PlotsGUI(self),
                }
        self.setWindowTitle('CENTREX DAQ')
        for e_name, e in self.GUI_elements.items():
            self.addTab(e, e_name)
        self.show()

    def closeEvent(self, event):
        if self.config['control_active']:
            if qt.QMessageBox.question(self, 'Confirm quit',
                "Control running. Do you really want to quit?", qt.QMessageBox.Yes |
                qt.QMessageBox.No, qt.QMessageBox.No) == qt.QMessageBox.Yes:
                self.GUI_elements["Control"].stop_control()
                event.accept()
            else:
                event.ignore()

if __name__ == '__main__':
    app = qt.QApplication(sys.argv)
    main_window = CentrexGUI(app)
    sys.exit(app.exec_())
