import PyQt5.QtWidgets as qt
import PyQt5.QtGui as QtGui
import PyQt5
import configparser
import sys, os, glob, importlib
import logging

import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
import h5py
import time
import tkinter as tk
import threading
from collections import deque
import time
import h5py
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
            cp_obj = self.config["controls"][cp]
            if cp_obj["type"] == "ControlsRow":
                self.constr_params.append( cp_obj["control_values"] )
            elif cp_obj["type"] == "ControlsTable":
                self.constr_params.append( cp_obj["column_values"] )
            else:
                self.constr_params.append( self.config["controls"][cp]["var"].get() )

        with self.config["driver"](*self.constr_params) as dev:
            # verify the device responds correctly
            if not isinstance(dev.verification_string, str):
                self.operational = False
                return
            if dev.verification_string.strip() == self.config["correct_response"].strip():
                self.operational = True
            else:
                logging.warning("verification string warning:" + dev.verification_string + "!=" + self.config["correct_response"].strip())
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
                    time.sleep(float(self.config["controls"]["dt"]["var"].get()))
                except ValueError:
                    time.sleep(1)

                # check device is enabled
                if not self.config["controls"]["enabled"]["var"].get():
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
                        self.nan_count.set( int(self.nan_count.get()) + 1)
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
                host     = conf["host"].get(),
                port     = conf["port"].get(),
                username = conf["username"].get(),
                password = conf["password"].get(),
            )
        self.influxdb_client.switch_database(self.parent.config["influxdb"]["database"].get())

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
                        self.parent.monitoring.last_warning.set(str(warning))
                    dev.warnings = []

                # find out and display the data queue length
                dev.qsize.set(len(dev.data_queue))

                # get the last event (if any) of the device
                self.display_last_event(dev)

                # get the last row of data in the HDF dataset
                data = self.get_last_row_of_data(dev)
                if not isinstance(data, type(None)):
                    # format display the data in a tkinter variable
                    formatted_data = [np.format_float_scientific(x, precision=3) for x in data]
                    dev.last_data.set("\n".join(formatted_data))

                    # write slow data to InfluxDB
                    self.write_to_influxdb(dev, data)

                # if writing to HDF is disabled, empty the queues
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
                    dev.events_queue.clear()
                    dev.data_queue.clear()

            # loop delay
            try:
                time.sleep(float(self.parent.config["monitoring_dt"].get()))
            except ValueError:
                time.sleep(1)

    def write_to_influxdb(self, dev, data):
        if self.parent.config["influxdb"]["enabled"].get().strip() == "False":
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
        if not dev.config["controls"]["enabled"]["var"].get():
            return

        # if HDF writing enabled for this device, get data from the HDF file
        if dev.config["controls"]["HDF_enabled"]["var"].get():
            with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
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
        if not dev.config["controls"]["enabled"]["var"].get():
            return

        # if HDF writing enabled for this device, get events from the HDF file
        if dev.config["controls"]["HDF_enabled"]["var"].get():
            with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
                grp = f[self.parent.run_name + "/" + dev.config["path"]]
                events_dset = grp[dev.config["name"] + "_events"]
                if events_dset.shape[0] == 0:
                    dev.last_event.set("(no event)")
                else:
                    dev.last_event.set(str(events_dset[-1]))

        # if HDF writing not enabled for this device, get events from the events_queue
        else:
            try:
                dev.last_event.set(str(dev.events_queue.pop()))
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
        self.filename = self.parent.config["files"]["hdf_fname"].get()
        self.parent.run_name = str(int(time.time())) + " " + self.parent.config["general"]["run_name"].get()

        # create/open HDF file, groups, and datasets
        with h5py.File(self.filename, 'a') as f:
            root = f.create_group(self.parent.run_name)
            root.attrs["time_offset"] = self.parent.config["time_offset"]
            for dev_name, dev in self.parent.devices.items():
                # check device is enabled
                if not dev.config["controls"]["enabled"]["var"].get():
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
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
                time.sleep(float(self.parent.config["general"]["hdf_loop_delay"].get()))
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
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
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
                dev_config = self.read_device_config_options(params)
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

    def read_device_config_options(self, params):
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
                            "value"      : params[c]["value"],
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
                            "command"    : params[c].get("command"),
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
        control_frame.addWidget(
                qt.QPushButton("\u26ab Start control"),
                0, 0,
            )
        control_frame.addWidget(
                qt.QPushButton("\u2b1b Stop control"),
                0, 1,
            )

        # the status label
        status_label = qt.QLabel(
                "Ready to start",
                alignment = PyQt5.QtCore.Qt.AlignRight,
            )
        status_label.setFont(QtGui.QFont("Helvetica", 16))
        control_frame.addWidget(status_label, 0, 2)

        ########################################
        # files
        ########################################

        files_frame = LabelFrame(self.main_frame, "Files")

        # config dir
        files_frame.addWidget(
                qt.QLabel("Config dir:"),
                0, 0
            )
        files_frame.addWidget(
                qt.QLineEdit(),
                0, 1
            )
        files_frame.addWidget(
                qt.QPushButton("Open..."),
                0, 2
            )

        # HDF file
        files_frame.addWidget(
                qt.QLabel("HDF file:"),
                1, 0
            )
        files_frame.addWidget(
                qt.QLineEdit(),
                1, 1
            )
        files_frame.addWidget(
                qt.QPushButton("Open..."),
                1, 2
            )

        # HDF writer loop delay
        files_frame.addWidget(
                qt.QLabel("HDF writer loop delay:"),
                2, 0
            )
        files_frame.addWidget(
                qt.QLineEdit(),
                2, 1
            )

        # run name
        files_frame.addWidget(
                qt.QLabel("Run name:"),
                3, 0
            )
        files_frame.addWidget(
                qt.QLineEdit(),
                3, 1
            )

        ########################################
        # devices
        ########################################

        cmd_frame = LabelFrame(self.main_frame, "Send a custom command")

        # the control to send a custom command to a specified device
        cmd_frame.addWidget(
                qt.QLabel("Cmd:"),
                0, 0
            )
        cmd_frame.addWidget(
                qt.QLineEdit(),
                0, 1
            )
        device_selector = qt.QComboBox()
        device_selector.addItem("Select device ...")
        cmd_frame.addWidget(device_selector, 0, 2)
        cmd_frame.addWidget(
                qt.QPushButton("Send"),
                0, 3
            )

        # button to refresh the list of COM ports
        cmd_frame.addWidget(
                qt.QPushButton("Refresh COM ports"),
                0, 4
            )

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
            df.addWidget(
                    qt.QPushButton("Attrs"),
                    0, 20
                )

            # device-specific controls
            for c_name, c in dev.config["controls"].items():

                # place QCheckBoxes
                if c["type"] == "QCheckBox":
                    df.addWidget(
                            qt.QCheckBox(c["label"]),
                            c["row"], c["col"],
                        )

                # place QPushButtons
                elif c["type"] == "QPushButton":
                    df.addWidget(
                            qt.QPushButton(c["label"]),
                            c["row"], c["col"],
                        )

                # place QLineEdits
                elif c["type"] == "QLineEdit":
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )
                    df.addWidget(
                            qt.QLineEdit(),
                            c["row"], c["col"],
                        )

                # place QComboBoxes
                elif c["type"] == "QComboBox":
                    df.addWidget(
                            qt.QLabel(c["label"]),
                            c["row"], c["col"] - 1,
                            alignment = PyQt5.QtCore.Qt.AlignRight,
                        )
                    combo_box = qt.QComboBox()
                    for option in c["options"]:
                        combo_box.addItem(option)
                    df.addWidget(
                            combo_box,
                            c["row"], c["col"],
                        )

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
        gen_f.addWidget(
                qt.QLabel("Loop delay [s]:"),
                0, 0
            )
        gen_f.addWidget(
                qt.QLineEdit(),
                0, 1
            )
        gen_f.addWidget(
                qt.QCheckBox("InfluxDB enabled"),
                1, 0
            )

        # InfluxDB controls
        db_f = LabelFrame(control_frame, "InfluxDB")
        db_f.addWidget(
                qt.QLabel("Host IP"),
                0, 0
            )
        db_f.addWidget(
                qt.QLineEdit(),
                0, 1
            )
        db_f.addWidget(
                qt.QLabel("Port"),
                1, 0
            )
        db_f.addWidget(
                qt.QLineEdit(),
                1, 1
            )
        db_f.addWidget(
                qt.QLabel("Username"),
                2, 0
            )
        db_f.addWidget(
                qt.QLineEdit(),
                2, 1
            )
        db_f.addWidget(
                qt.QLabel("Password"),
                3, 0
            )
        db_f.addWidget(
                qt.QLineEdit(),
                3, 1
            )

        # for displaying warnings
        w_f = LabelFrame(control_frame, "Warnings")
        w_f.addWidget(
                qt.QLabel("(no warnings)"),
                3, 0
            )

    def place_device_specific_items(self):
        # frame for device data
        self.dev_f = LabelFrame(self.main_frame, "Devices")

        # device-specific text
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
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
            df.addWidget(
                    qt.QLabel("0"),
                    0, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # NaN count
            df.addWidget(
                    qt.QLabel("NaN count:"),
                    1, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            df.addWidget(
                    qt.QLabel("0"),
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
            df.addWidget(
                    qt.QLabel("(no data)"),
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
            df.addWidget(
                    qt.QLabel("(no event)"),
                    3, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

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
        self.setWindowTitle('CENTREX DAQ')
        self.addTab(ControlGUI(self), "Control")
        self.addTab(MonitoringGUI(self), "Monitoring")
        self.addTab(PlotsGUI(self), "Plots")
        self.show()

    def closeEvent(self, event):
        if self.config['control_active']:
            if qt.QMessageBox.question(self, 'Confirm quit',
                "Control running. Do you really want to quit?", qt.QMessageBox.Yes |
                qt.QMessageBox.No, qt.QMessageBox.No) == qt.QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()

if __name__ == '__main__':
    app = qt.QApplication(sys.argv)
    main_window = CentrexGUI(app)
    sys.exit(app.exec_())
