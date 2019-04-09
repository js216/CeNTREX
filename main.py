import re
import h5py
import time
import PyQt5
import pickle
import pyvisa
import logging
import threading
import numpy as np
import configparser
import datetime as dt
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
#######            CONVENIENCE FUNCTIONS/CLASSES        ##################
#######                                                 ##################
##########################################################################
##########################################################################

def LabelFrame(label, type="grid", maxWidth=None, fixed=False):
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

    if fixed:
        layout.setSizeConstraint(qt.QLayout.SetFixedSize)

    return box, layout

def ScrollableLabelFrame(label, type="grid", fixed=False, minWidth=None,
        minHeight=None, vert_scroll=True, horiz_scroll=True):
    # make the outer (framed) box
    outer_box = qt.QGroupBox(label)
    outer_layout = qt.QGridLayout()
    outer_box.setLayout(outer_layout)

    # box size
    if minHeight:
        outer_box.setMinimumHeight(minHeight)
    if minWidth:
        outer_box.setMinimumWidth(minWidth)

    # make the inner grid
    inner_box = qt.QWidget()
    if type == "grid":
        inner_layout = qt.QGridLayout()
    elif type == "flexgrid":
        inner_layout = FlexibleGridLayout()
    elif type == "hbox":
        inner_layout = qt.QHBoxLayout()
    elif type == "vbox":
        inner_layout = qt.QVBoxLayout()
    inner_layout.setContentsMargins(0,0,0,0)
    inner_box.setLayout(inner_layout)

    # make a scrollable area, and add the inner area to it
    sa = qt.QScrollArea()
    if not horiz_scroll:
        sa.setHorizontalScrollBarPolicy(PyQt5.QtCore.Qt.ScrollBarAlwaysOff)
    if not vert_scroll:
        sa.setVerticalScrollBarPolicy(PyQt5.QtCore.Qt.ScrollBarAlwaysOff)
        sa.setMinimumHeight(sa.sizeHint().height() - 40) # the recommended height is too large
    sa.setFrameStyle(16)
    sa.setWidgetResizable(True)
    sa.setWidget(inner_box)

    # add the scrollable area to the outer (framed) box
    outer_layout.addWidget(sa)

    if fixed:
        inner_layout.setSizeConstraint(qt.QLayout.SetFixedSize)

    return outer_box, inner_layout

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

def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]

class FlexibleGridLayout(qt.QHBoxLayout):
    """A QHBoxLayout of QVBoxLayouts."""
    def __init__(self):
        super().__init__()
        self.cols = {}

        # populate the grid with placeholders
        for col in range(10):
            self.cols[col] = qt.QVBoxLayout()
            self.addLayout(self.cols[col])

            # add stretchable spacer to prevent stretching the device controls boxes
            self.cols[col].addStretch()

            # reverse the layout order to keep the spacer always at the bottom
            self.cols[col].setDirection(qt.QBoxLayout.BottomToTop)

            # add horizontal placeholders
            vbox = self.cols[col]
            for row in range(10):
                vbox.addLayout(qt.QHBoxLayout())

    def addWidget(self, widget, row, col):
        vbox = self.cols[col]
        rev_row = vbox.count() - 1 - row
        placeholder = vbox.itemAt(rev_row).layout()
        if not placeholder.itemAt(0):
            placeholder.addWidget(widget)

    def clear(self):
        """Remove all widgets."""
        for col_num, col in self.cols.items():
            for i in reversed(range(col.count())):
                try:
                    col.itemAt(i).layout().itemAt(0).widget().setParent(None)
                except AttributeError:
                    pass

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
        self.last_event = []

        # for warnings about device abnormal condition
        self.warnings = []

        # the data and events queues
        self.data_queue = deque()
        self.config["plots_queue"] = deque(maxlen=self.config["plots_queue_maxlen"])
        self.events_queue = deque()

        # the variable for counting the number of NaN returns
        self.nan_count = 0

        # for counting the number of sequential NaN returns
        self.sequential_nan_count = 0
        self.previous_data = True

    def setup_connection(self, time_offset):
        self.time_offset = time_offset

        # get the parameters that are to be passed to the driver constructor
        self.constr_params = [self.time_offset]
        for cp in self.config["constr_params"]:
            self.constr_params.append(self.config["controls"][cp]["value"])

        # for meta devices, include a reference to the parent
        if self.config["meta_device"]:
            self.constr_params = [self.config["parent"]] + self.constr_params

        # verify the device responds correctly
        with self.config["driver"](*self.constr_params) as dev:
            if not isinstance(dev.verification_string, str):
                self.operational = False
                self.error_message = "verification_string is not of type str"
                return
            if dev.verification_string.strip() == self.config["correct_response"].strip():
                self.operational = True
            else:
                self.error_message = "verification string warning: " +\
                        dev.verification_string + "!=" + self.config["correct_response"].strip()
                logging.warning(self.error_message)
                self.operational = False
                return

            # get parameters and attributes, if any, from the driver
            self.config["shape"] = dev.shape
            self.config["dtype"] = dev.dtype
            for attr_name, attr_val in dev.new_attributes:
                self.config["attributes"][attr_name] = attr_val

    def change_plots_queue_maxlen(self, maxlen):
        # sanity check
        try:
            self.config["plots_queue_maxlen"] = int(maxlen)
        except ValueError:
            return

        # create a new deque with a different maxlen
        self.config["plots_queue"] = deque(maxlen=self.config["plots_queue_maxlen"])

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
        try:
            with self.config["driver"](*self.constr_params) as device:
                while self.active.is_set():
                    # get and sanity check loop delay
                    try:
                        dt = float(self.config["controls"]["dt"]["value"])
                        if dt < 0.002:
                            logging.warning("Device dt too small.")
                            raise ValueError
                    except ValueError:
                        time.sleep(0.1)

                    # do the loop delay, checking the device is still enabled
                    else:
                        dt = float(self.config["controls"]["dt"]["value"])
                        for i in range(int(dt)):
                            if not self.active.is_set():
                                return
                            time.sleep(1)
                        time.sleep(dt - int(dt))

                    # check device is enabled
                    if not self.config["controls"]["enabled"]["value"]:
                        continue

                    # check device for abnormal conditions
                    warning = device.GetWarnings()
                    if warning:
                        self.warnings += warning

                    # record numerical values
                    last_data = device.ReadValue()
                    if last_data:
                        self.data_queue.append(last_data)
                        self.config["plots_queue"].append(last_data)

                    # keep track of the number of (sequential and total) NaN returns
                    if isinstance(last_data, float):
                        if np.isnan(last_data):
                            self.nan_count += 1
                            if np.isnan(self.previous_data):
                                self.sequential_nan_count += 1
                        else:
                            self.sequential_nan_count = 0
                    self.previous_data = last_data

                    # issue a warning if there's been too many sequential NaN returns
                    try:
                        max_NaN_count = int(self.config["max_NaN_count"])
                    except TypeError:
                        max_NaN_count = 10
                    if self.sequential_nan_count > max_NaN_count:
                        warning_dict = {
                                "message" : "excess sequential NaN returns: " + str(self.sequential_nan_count),
                                "sequential_NaN_count_exceeded" : 1,
                            }
                        self.warnings.append([time.time(), warning_dict])

                    # send control commands, if any, to the device, and record return values
                    for c in self.commands:
                        try:
                            ret_val = eval("device." + c.strip())
                        except (ValueError, AttributeError, SyntaxError, TypeError) as err:
                            ret_val = str(err)
                        ret_val = "None" if not ret_val else ret_val
                        self.last_event = [ time.time()-self.time_offset, c, ret_val ]
                        self.events_queue.append(self.last_event)
                    self.commands = []

        # report any exception that has occurred in the run() function
        except Exception as err:
            warning_dict = {
                    "message" : "exception: "+str(err),
                    "exception" : 1,
                }
            self.warnings.append([time.time(), warning_dict])

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
            # check amount of remaining free disk space
            self.parent.ControlGUI.check_free_disk_space()

            # monitor operation of individual devices
            for dev_name, dev in self.parent.devices.items():
                # check device running
                if not dev.control_started:
                    continue

                # check device enabled
                if not dev.config["controls"]["enabled"]["value"]:
                    continue

                # check device for abnormal conditions
                if len(dev.warnings) != 0:
                    logging.warning("Abnormal condition in " + str(dev_name))
                    for warning in dev.warnings:
                        logging.warning(str(warning))
                        self.push_warnings_to_influxdb(dev_name, warning)
                        self.parent.ControlGUI.update_warnings(str(warning))
                    dev.warnings = []

                # find out and display the data queue length
                dev.config["monitoring_GUI_elements"]["qsize"].setText(str(len(dev.data_queue)))

                # get the last event (if any) of the device
                self.display_last_event(dev)

                # get the last row of data from the plots_queue
                try:
                    data = dev.config["plots_queue"][-1]
                except IndexError:
                    data = None

                # format the data
                if not isinstance(data, type(None)):
                    # display the data in a tkinter variable
                    try:
                        if dev.config["slow_data"]:
                            formatted_data = [np.format_float_scientific(x, precision=3) for x in data]
                        else:
                            formatted_data = [np.format_float_scientific(x, precision=3) for x in data[0][0,:,0]]
                    except TypeError as err:
                        logging.warning("Warning in Monitoring: " + str(err))
                        continue
                    dev.config["monitoring_GUI_elements"]["data"].setText("\n".join(formatted_data))

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
        try:
            if self.parent.config["influxdb"]["enabled"].strip() == "False":
                return
        except AttributeError as err:
            if isinstance(self.parent.config["influxdb"]["enabled"], int):
                if self.parent.config["influxdb"]["enabled"] == 1:
                    self.parent.config["influxdb"]["enabled"] = "False"
                    return
                elif self.parent.config["influxdb"]["enabled"] == 2:
                    self.parent.config["influxdb"]["enabled"] = "True"
            else:
                logging.warning("InfluxDB error: "+str(err))
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
            try:
                self.influxdb_client.write_points(json_body, time_precision='ms')
            except Exception as err:
                logging.warning("InfluxDB error: " + str(err))

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
                    dev.config["monitoring_GUI_elements"]["events"].setText("(no event)")
                else:
                    dev.config["monitoring_GUI_elements"]["events"].setText(str(events_dset[-1]))

        # if HDF writing not enabled for this device, get events from the events_queue
        else:
            try:
                dev.config["monitoring_GUI_elements"]["events"].setText(str(dev.events_queue.pop()))
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

            # write run attributes
            root.attrs["time_offset"] = self.parent.config["time_offset"]
            for key, val in self.parent.config["run_attributes"].items():
                root.attrs[key] = val

            for dev_name, dev in self.parent.devices.items():
                # check device is enabled
                if not dev.config["controls"]["enabled"]["value"]:
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]["value"]:
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
                        try:
                            dset[-len(data):] = data
                        except TypeError as err:
                            logging.error("Error in write_all_queues_to_HDF(): " + str(err))

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

class AttrEditor(QtGui.QDialog):
    def __init__(self, parent, dev=None):
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
            self.qtw.setItem(row, 0, qt.QTableWidgetItem( key ))
            self.qtw.setItem(row, 1, qt.QTableWidgetItem( val ))

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
        pb.clicked[bool].connect(lambda state : self.check_attributes())
        self.accepted.connect(self.change_attrs)
        self.frame.addWidget(pb, 3, 0)

        pb = qt.QPushButton("Reject")
        pb.clicked[bool].connect(lambda state : self.reject())
        self.frame.addWidget(pb, 3, 1)

    def reload_attrs_from_file(self, state):
        # reload attributes
        params = configparser.ConfigParser()
        if self.dev:
            params.read(self.dev.config["config_fname"])
            new_attrs = params["attributes"]
        else:
            params.read("config/settings.ini")
            new_attrs = params["run_attributes"]

        # rewrite the table contents
        self.qtw.clear()
        self.qtw.setRowCount(len(new_attrs))
        for row, (key, val) in enumerate(new_attrs.items()):
            self.qtw.setItem(row, 0, qt.QTableWidgetItem( key ))
            self.qtw.setItem(row, 1, qt.QTableWidgetItem( val ))

    def write_attrs_to_file(self, state):
        # do a sanity check of attributes and change corresponding config dicts
        self.check_attributes()

        # when changing device attributes/settings
        if self.dev:
            # collect new configuration parameters to be written
            config = configparser.ConfigParser()
            config["device"] = {
                    "name"               : str(self.dev.config["name"]),
                    "label"              : str(self.dev.config["label"]),
                    "path"               : str(self.dev.config["path"]),
                    "driver"             : self.dev.config["driver"].__name__,
                    "constr_params"      : ", ".join(self.dev.config["constr_params"]),
                    "correct_response"   : str(self.dev.config["correct_response"]),
                    "slow_data"          : str(self.dev.config["slow_data"]),
                    "row"                : str(self.dev.config["row"]),
                    "column"             : str(self.dev.config["column"]),
                    "plots_queue_maxlen" : str(self.dev.config["plots_queue_maxlen"]),
                    "max_NaN_count"      : str(self.dev.config.get("max_NaN_count")),
                    "meta_device"        : str(self.dev.config.get("meta_device")),
                }
            config["attributes"] = self.dev.config["attributes"]

            # collect device control parameters
            for c_name, c in self.dev.config["controls"].items():
                config[c_name] = {
                        "label"        : str(c.get("label")),
                        "type"         : str(c["type"]),
                        "row"          : str(c.get("row")),
                        "col"          : str(c.get("col")),
                        "tooltip"      : str(c.get("tooltip")),
                        "rowspan"      : str(c.get("rowspan")),
                        "colspan"      : str(c.get("colspan")),
                    }
                if c["type"] in ["QComboBox", "QCheckBox", "QLineEdit"]:
                    config[c_name]["value"] = str(c["value"])
                if c["type"] == "QLineEdit":
                    config[c_name]["enter_cmd"] = str(c["enter_cmd"])
                if c["type"] == "QComboBox":
                    config[c_name]["options"] = ", ".join(c["options"])
                    config[c_name]["command"] = str(c.get("command"))
                if c["type"] == "QPushButton":
                    config[c_name]["command"] = str(c.get("cmd"))
                    config[c_name]["argument"] = str(c.get("argument"))
                    config[c_name]["align"] = str(c.get("align"))
                if c["type"] == "ControlsRow":
                    config[c_name]["ctrl_values"]  = ", ".join([x for x_name,x in c["value"].items()])
                    config[c_name]["ctrl_names"]   = ", ".join(c["ctrl_names"])
                    config[c_name]["ctrl_labels"]  = ", ".join([x for x_name,x in c["ctrl_labels"].items()])
                    config[c_name]["ctrl_types"]   = ", ".join([x for x_name,x in c["ctrl_types"].items()])
                    config[c_name]["ctrl_options"] = "; ".join([", ".join(x) for x_name,x in c["ctrl_options"].items()])
                if c["type"] == "ControlsTable":
                    config[c_name]["col_values"] = "; ".join([", ".join(x) for x_name,x in c["value"].items()])
                    config[c_name]["row_ids"]     = ", ".join(c["row_ids"])
                    config[c_name]["col_names"]   = ", ".join(c["col_names"])
                    config[c_name]["col_labels"]  = ", ".join([x for x_name,x in c["col_labels"].items()])
                    config[c_name]["col_types"]   = ", ".join([x for x_name,x in c["col_types"].items()])
                    config[c_name]["col_options"] = "; ".join([", ".join(x) for x_name,x in c["col_options"].items()])

            # write them to file
            with open(self.dev.config["config_fname"], 'w') as f:
                config.write(f)

        # when changing program attributes/settings
        if not self.dev:
            # collect new configuration parameters to be written
            config = configparser.ConfigParser()
            for sect in ["general", "run_attributes", "files", "influxdb"]:
                config[sect] = self.parent.config[sect]

            # write them to file
            with open("config/settings.ini", 'w') as f:
                config.write(f)

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

    def change_attrs(self):
        if self.dev: # if changing device attributes
            # write the new attributes to the config dict
            self.dev.config["attributes"] = {}
            for row in range(self.qtw.rowCount()):
                    key = self.qtw.item(row, 0).text()
                    val = self.qtw.item(row, 1).text()
                    self.dev.config["attributes"][key] = val

            # update the column names and units
            self.parent.ControlGUI.update_col_names_and_units()

        else: # if changing run attributes
            self.parent.config["run_attributes"] = {}
            for row in range(self.qtw.rowCount()):
                    key = self.qtw.item(row, 0).text()
                    val = self.qtw.item(row, 1).text()
                    self.parent.config["run_attributes"][key] = val

class ControlGUI(qt.QWidget):
    def __init__(self, parent):
        super().__init__()
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
                if f[-11:] != "desktop.ini":
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

            # for meta devices, include a reference to the parent
            if dev_config["meta_device"]:
                dev_config["parent"] = self.parent

            # populate the list of device controls
            try:
                dev_config["controls"] = self.read_device_controls(params)
            except (IndexError, ValueError, TypeError, KeyError) as err:
                logging.error("Cannot read device config file " + f + " : " + str(err))
                return

            # make a Device object
            if params["device"]["name"] in self.parent.devices:
                logging.warning("Warning in read_device_config(): duplicate device name: " + params["device"]["name"])
            self.parent.devices[params["device"]["name"]] = Device(dev_config)

    def read_device_config_options(self, f, params):
        return {
                    "name"               : params["device"]["name"],
                    "label"              : params["device"]["label"],
                    "path"               : params["device"]["path"],
                    "correct_response"   : params["device"]["correct_response"],
                    "max_NaN_count"      : params["device"].get("max_NaN_count"),
                    "plots_queue_maxlen" : int(params["device"]["plots_queue_maxlen"]),
                    "slow_data"          : True if params["device"]["slow_data"]=="True" else False,
                    "row"                : int(params["device"]["row"]),
                    "column"             : int(params["device"]["column"]),
                    "constr_params"      : split(params["device"]["constr_params"]),
                    "meta_device"        : True if params["device"].get("meta_device")=="True" else False,
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
                            "enter_cmd"  : params[c].get("enter_cmd"),
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
                            "options"    : split(params[c]["options"]),
                            "value"      : params[c]["value"],
                        }

                elif params[c].get("type") == "ControlsRow":
                    ctrls[c] = {
                            "label"        : params[c]["label"],
                            "type"         : params[c]["type"],
                            "row"          : int(params[c]["row"]),
                            "col"          : int(params[c]["col"]),
                            "ctrl_names"   : split(params[c]["ctrl_names"]),
                            "ctrl_labels"  : dict(zip(
                                                    split(params[c]["ctrl_names"]),
                                                    split(params[c]["ctrl_labels"])
                                                )),
                            "ctrl_types"   : dict(zip(
                                                    split(params[c]["ctrl_names"]),
                                                    split(params[c]["ctrl_types"])
                                                )),
                            "ctrl_options" : dict(zip(
                                                    split(params[c]["ctrl_names"]),
                                                    [split(x) for x in params[c]["ctrl_options"].split(";")]
                                                )),
                            "value"        : dict(zip(
                                                    split(params[c]["ctrl_names"]),
                                                    split(params[c]["ctrl_values"])
                                                )),
                        }

                elif params[c].get("type") == "ControlsTable":
                    ctrls[c] = {
                            "label"        : params[c]["label"],
                            "type"         : params[c]["type"],
                            "row"          : int(params[c]["row"]),
                            "col"          : int(params[c]["col"]),
                            "rowspan"      : int(params[c].get("rowspan")),
                            "colspan"      : int(params[c].get("colspan")),
                            "row_ids"      : split(params[c]["row_ids"]),
                            "col_names"    : split(params[c]["col_names"]),
                            "col_labels"   : dict(zip(
                                                    split(params[c]["col_names"]),
                                                    split(params[c]["col_labels"])
                                                )),
                            "col_types"    : dict(zip(
                                                    split(params[c]["col_names"]),
                                                    split(params[c]["col_types"])
                                                )),
                            "col_options"  : dict(zip(
                                                    split(params[c]["col_names"]),
                                                    [split(x) for x in params[c]["col_options"].split(";")]
                                                )),
                            "value"        : dict(zip(
                                                    split(params[c]["col_names"]),
                                                    [split(x) for x in params[c]["col_values"].split(";")]
                                                )),
                        }

                elif params[c].get("type") == "dummy":
                    ctrls[c] = {
                            "type"       : params[c]["type"],
                            "value"      : params[c]["value"],
                        }

                elif params[c].get("type"):
                    logging.warning("Control type not supported: " + params[c].get("type"))

            return ctrls

    def place_GUI_elements(self):
        # main frame for all ControlGUI elements
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        # the status label
        self.status_label = qt.QLabel(
                "Ready to start",
                alignment = PyQt5.QtCore.Qt.AlignRight,
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
        self.orientation_pb.setToolTip("Put controls and plots/monitoring on top of each other (Ctrl+V).")
        self.orientation_pb.clicked[bool].connect(self.parent.toggle_orientation)
        control_frame.addWidget(self.orientation_pb, 2, 0)

        # for dark/light stylesheets
        self.style_pb = qt.QPushButton("Dark style")
        self.style_pb.setToolTip("Change style to dark mode (Ctrl+D).")
        self.style_pb.clicked[bool].connect(self.toggle_style)
        control_frame.addWidget(self.style_pb, 2, 1)

        # button to refresh the list of COM ports
        pb = qt.QPushButton("Refresh COM ports")
        pb.setToolTip("Click this to populate all the COM port dropdown menus.")
        pb.clicked[bool].connect(self.refresh_COM_ports)
        control_frame.addWidget(pb, 3, 0)

        # the control to send a custom command to a specified device

        cmd_frame = qt.QHBoxLayout()
        control_frame.addLayout(cmd_frame, 4, 0, 1, 2)

        cmd_frame.addWidget(qt.QLabel("Cmd:"))

        qle = qt.QLineEdit()
        qle.setToolTip("Enter a command corresponding to a function in the selected device driver.")
        qle.setText(self.parent.config["general"]["custom_command"])
        qle.textChanged[str].connect(lambda val: self.change_config("general", "custom_command", val))
        cmd_frame.addWidget(qle)

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
        cmd_frame.addWidget(self.custom_dev_cbx)

        pb = qt.QPushButton("Send")
        pb.clicked[bool].connect(self.queue_custom_command)
        cmd_frame.addWidget(pb)

        ########################################
        # files
        ########################################

        box, files_frame = LabelFrame("Files")
        self.top_frame.addWidget(box)

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

        # button to edit run attributes
        pb = qt.QPushButton("Attrs...")
        pb.setToolTip("Display or edit device attributes that are written with the data to the HDF file.")
        pb.clicked[bool].connect(self.edit_run_attrs)
        files_frame.addWidget(pb, 4, 2)

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

        # disk space usage
        gen_f.addWidget(qt.QLabel("Disk usage:"), 1, 0)
        self.free_qpb = qt.QProgressBar()
        gen_f.addWidget(self.free_qpb, 1, 1, 1, 2)
        self.check_free_disk_space()

        gen_f.addWidget(qt.QLabel("Loop delay [s]:"), 0, 0)
        qle = qt.QLineEdit()
        qle.setText(self.parent.config["general"]["monitoring_dt"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("general", "monitoring_dt", val)
            )
        gen_f.addWidget(qle, 0, 1, 1, 2)


        # InfluxDB controls

        qch = qt.QCheckBox("InfluxDB")
        qch.setToolTip("InfluxDB enabled")
        qch.setTristate(False)
        qch.setChecked(True if self.parent.config["influxdb"]["enabled"] in ["1", "True"] else False)
        qch.stateChanged[int].connect(
                lambda val: self.change_config("influxdb", "enabled", val)
            )
        gen_f.addWidget(qch, 4, 0)

        qle = qt.QLineEdit()
        qle.setToolTip("Host IP")
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["influxdb"]["host"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "host", val)
            )
        gen_f.addWidget(qle, 4, 1)

        qle = qt.QLineEdit()
        qle.setToolTip("Port") 
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["influxdb"]["port"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "port", val)
            )
        gen_f.addWidget(qle, 4, 2)

        qle = qt.QLineEdit()
        qle.setMaximumWidth(50)
        qle.setToolTip("Username") 
        qle.setText(self.parent.config["influxdb"]["username"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "username", val)
            )
        gen_f.addWidget(qle, 5, 1)

        qle = qt.QLineEdit()
        qle.setToolTip("Password") 
        qle.setMaximumWidth(50)
        qle.setText(self.parent.config["influxdb"]["password"])
        qle.textChanged[str].connect(
                lambda val: self.change_config("influxdb", "password", val)
            )
        gen_f.addWidget(qle, 5, 2)

        # for displaying warnings
        self.warnings_label = qt.QLabel("(no warnings)")
        self.warnings_label.setWordWrap(True)
        gen_f.addWidget(self.warnings_label, 6, 0, 1, 3)

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

    def update_warnings(self, warnings):
        self.warnings_label.setText(warnings)

    def check_free_disk_space(self):
        pythoncom.CoInitialize()
        c = wmi.WMI ()
        for d in c.Win32_LogicalDisk():
            if d.Caption == self.parent.config["files"]["hdf_fname"][0:2]:
                size_MB = float(d.Size) / 1024/1024
                free_MB = float(d.FreeSpace) / 1024/1024
                self.free_qpb.setMinimum(0)
                self.free_qpb.setMaximum(size_MB)
                self.free_qpb.setValue(size_MB - free_MB)
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
            box, dcf = LabelFrame(dev.config["label"], type="vbox")
            self.devices_frame.addWidget(box, dev.config["row"], dev.config["column"])

            # layout for controls
            df_box, df = qt.QWidget(), qt.QGridLayout()
            df_box.setLayout(df)
            dcf.addWidget(df_box)
            df.setColumnStretch(1, 1)
            df.setColumnStretch(20, 0)

            # the button to reload attributes
            pb = qt.QPushButton("Attrs...")
            pb.setToolTip("Display or edit device attributes that are written with the data to the HDF file.")
            pb.clicked[bool].connect(lambda val, dev=dev : self.edit_attrs(dev))
            df.addWidget(pb, 0, 1)

            # for changing plots_queue maxlen
            qle = qt.QLineEdit()
            qle.setToolTip("Change plots_queue maxlen.")
            qle.setText(str(dev.config["plots_queue_maxlen"]))
            qle.textChanged[str].connect(lambda maxlen, dev=dev: dev.change_plots_queue_maxlen(maxlen))
            df.addWidget(qle, 1, 1)

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
                            lambda state, dev=dev, ctrl=c_name:
                                self.change_dev_config(dev, "controls", state, ctrl, sub_ctrl=None)
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
                            lambda text, dev=dev, ctrl=c_name:
                                self.change_dev_config(dev, "controls", text, ctrl, sub_ctrl=None)
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
                                self.change_dev_config(dev, "controls", text, config, sub_ctrl=None)
                        )
                    if c.get("command"):
                        c["QComboBox"].activated[str].connect(
                                lambda text, dev=dev, cmd=c["command"], qcb=c["QComboBox"]:
                                    self.queue_command(dev, cmd+"('"+qcb.currentText()+"')")
                            )

                # place ControlsRows
                elif c["type"] == "ControlsRow":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(c["label"], type="hbox")
                    df.addWidget(box, c["row"], c["col"])

                    # the individual controls that compose a ControlsRow
                    for ctrl in c["ctrl_names"]:
                        if c["ctrl_types"][ctrl] == "QLineEdit":
                            qle = qt.QLineEdit()
                            qle.setText(c["value"][ctrl])
                            qle.setToolTip(c["ctrl_labels"][ctrl])
                            qle.textChanged[str].connect(
                                    lambda val, dev=dev, config=c_name, ctrl=ctrl:
                                        self.change_dev_config(dev, "controls", val, config, sub_ctrl=ctrl)
                                )
                            ctrl_frame.addWidget(qle)

                        elif c["ctrl_types"][ctrl] == "QComboBox":
                            cbx = qt.QComboBox()
                            cbx.setToolTip(c["ctrl_labels"][ctrl])
                            cbx.activated[str].connect(
                                    lambda val, dev=dev, config=c_name, ctrl=ctrl:
                                        self.change_dev_config(dev, "controls", val, config, sub_ctrl=ctrl)
                                )
                            update_QComboBox(
                                    cbx     = cbx,
                                    options = c["ctrl_options"][ctrl],
                                    value   = c["value"][ctrl],
                                )
                            ctrl_frame.addWidget(cbx)

                        else:
                            logging.warning("ControlsRow error: sub-control type not supported: " + c["ctrl_types"][ctrl])


                # place ControlsTables
                elif c["type"] == "ControlsTable":
                    # the frame for the row of controls
                    box, ctrl_frame = LabelFrame(c["label"], type="grid")
                    if c.get("rowspan") and c.get("colspan"):
                        df.addWidget(box, c["row"], c["col"], c["rowspan"], c["colspan"])
                    else:
                        df.addWidget(box, c["row"], c["col"])

                    for i, row in enumerate(c["row_ids"]):
                        for j, col in enumerate(c["col_names"]):
                            if c["col_types"][col] == "QLabel":
                                ql = qt.QLabel()
                                ql.setToolTip(c["col_labels"][col])
                                ql.setText(c["value"][col][i])
                                ctrl_frame.addWidget(ql, i, j)

                            elif c["col_types"][col] == "QLineEdit":
                                qle = qt.QLineEdit()
                                qle.setToolTip(c["col_labels"][col])
                                qle.setText(c["value"][col][i])
                                qle.textChanged[str].connect(
                                        lambda val, dev=dev, config=c_name, col=col, row=row:
                                            self.change_dev_config(dev, "controls",
                                                val, config, sub_ctrl=col, row=row)
                                    )
                                ctrl_frame.addWidget(qle, i, j)

                            elif c["col_types"][col] == "QCheckBox":
                                qch = qt.QCheckBox()
                                qch.setToolTip(c["col_labels"][col])
                                qch.setCheckState(int(c["value"][col][i]))
                                qch.setTristate(False)
                                qch.stateChanged[int].connect(
                                        lambda val, dev=dev, config=c_name, col=col, row=row:
                                            self.change_dev_config(dev, "controls",
                                                val, config, sub_ctrl=col, row=row)
                                    )
                                ctrl_frame.addWidget(qch, i, j)

                            elif c["col_types"][col] == "QComboBox":
                                cbx = qt.QComboBox()
                                cbx.setToolTip(c["col_labels"][col])
                                cbx.activated[str].connect(
                                        lambda val, dev=dev, config=c_name, col=col, row=row:
                                            self.change_dev_config(dev, "controls",
                                                val, config, sub_ctrl=col, row=row)
                                    )
                                update_QComboBox(
                                        cbx     = cbx,
                                        options = c["col_options"][col],
                                        value   = c["value"][col][i],
                                    )
                                ctrl_frame.addWidget(cbx, i, j)

                            else:
                                logging.warning("ControlsRow error: sub-control type not supported: " + c["col_types"][col])

            # layout for monitoring info
            df_box, df = qt.QWidget(), qt.QGridLayout()
            df_box.setLayout(df)
            if not self.parent.config["monitoring_visible"]:
                df_box.hide()
            dcf.addWidget(df_box)
            dev.config["monitoring_GUI_elements"] = {
                    "df_box" : df_box,
                    }

            # length of the data queue
            df.addWidget(
                    qt.QLabel("Queue length:"),
                    0, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.config["monitoring_GUI_elements"]["qsize"] = qt.QLabel("N/A")
            df.addWidget(
                    dev.config["monitoring_GUI_elements"]["qsize"],
                    0, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # NaN count
            df.addWidget(
                    qt.QLabel("NaN count:"),
                    1, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.config["monitoring_GUI_elements"]["NaN_count"] = qt.QLabel("N/A")
            df.addWidget(
                    dev.config["monitoring_GUI_elements"]["NaN_count"],
                    1, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # column names
            dev.col_names_list = split(dev.config["attributes"]["column_names"])
            dev.column_names = "\n".join(dev.col_names_list)
            dev.config["monitoring_GUI_elements"]["col_names"] = qt.QLabel(
                    dev.column_names, alignment = PyQt5.QtCore.Qt.AlignRight
                )
            df.addWidget(dev.config["monitoring_GUI_elements"]["col_names"], 2, 0)

            # data
            dev.config["monitoring_GUI_elements"]["data"] = qt.QLabel("(no data)")
            df.addWidget(
                    dev.config["monitoring_GUI_elements"]["data"],
                    2, 1,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )

            # units
            units = split(dev.config["attributes"]["units"])
            dev.units = "\n".join(units)
            dev.config["monitoring_GUI_elements"]["units"] = qt.QLabel(dev.units)
            df.addWidget(dev.config["monitoring_GUI_elements"]["units"], 2, 2, alignment = PyQt5.QtCore.Qt.AlignLeft)

            # latest event / command sent to device & its return value
            df.addWidget(
                    qt.QLabel("Last event:"),
                    3, 0,
                    alignment = PyQt5.QtCore.Qt.AlignRight,
                )
            dev.config["monitoring_GUI_elements"]["events"] = qt.QLabel("(no events)")
            dev.config["monitoring_GUI_elements"]["events"].setWordWrap(True)
            df.addWidget(
                    dev.config["monitoring_GUI_elements"]["events"],
                    3, 1, 1, 2,
                    alignment = PyQt5.QtCore.Qt.AlignLeft,
                )


    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

    def change_dev_config(self, dev, config, val, ctrl=None, sub_ctrl=None, row=None):
        if row: # used in ControlsTables
            dev.config[config][ctrl]["value"][sub_ctrl][i] = val
        elif sub_ctrl: # used in ControlsRows
            dev.config[config][ctrl]["value"][sub_ctrl] = val
        elif ctrl:
            dev.config[config][ctrl]["value"] = val
        else:
            dev.config[config] = val

    def toggle_style(self, state=""):
        if self.style_pb.text() == "Dark style":
            with open("darkstyle.qss", 'r') as f:
                self.parent.app.setStyleSheet(f.read())
            self.style_pb.setText("Light style")
            self.style_pb.setToolTip("Change style to light mode (Ctrl+D).")
        else:
            self.parent.app.setStyleSheet("")
            self.style_pb.setText("Dark style")
            self.style_pb.setToolTip("Change style to dark mode (Ctrl+D).")

    def rename_HDF(self, state):
        # check we're not running already
        if self.parent.config['control_active']:
            logging.warning("Warning: Cannot rename HDF while control is running.")
            return

        # get old file path
        old_fname = self.parent.config["files"]["hdf_fname"]

        # strip the old name from the full path
        path = "/".join( old_fname.split('/')[0:-1] )

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
        self.devices_frame.clear()
        self.read_device_config()
        self.place_device_controls()

        # changes the list of devices in send custom command
        dev_list = [dev_name for dev_name in self.parent.devices]
        update_QComboBox(
                cbx     = self.custom_dev_cbx,
                options = list(set(dev_list) | set([ self.parent.config["general"]["custom_device"] ])),
                value   = self.parent.config["general"]["custom_device"],
            )

        # update the available devices for plotting
        self.parent.PlotsGUI.refresh_all_run_lists()

    def get_dev_list(self):
        dev_list = []
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["value"]:
                dev_list.append(dev_name)
        return dev_list

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
            else:
                cbx = dev.config["controls"]["COM_port"]["QComboBox"]

            # update the QComboBox of COM_port options
            update_QComboBox(
                    cbx     = cbx,
                    options = pyvisa.ResourceManager().list_resources(),
                    value   = cbx.currentText()
                )

    def edit_attrs(self, dev):
        # open the AttrEditor dialog window
        w = AttrEditor(self.parent, dev)
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

                ## reinstantiate the thread (since Python only allows threads to
                ## be started once, this is necessary to allow stopping and restarting control)
                self.parent.devices[dev_name] = Device(dev.config)
                dev = self.parent.devices[dev_name]

                # setup connection
                dev.setup_connection(self.parent.config["time_offset"])
                if not dev.operational:
                    error_box("Device error", "Error: " + dev.config["label"] +\
                            " not responding.", dev.error_message)
                    self.status_label.setText("Device configuration error")
                    return

        # update device controls with new instances of Devices
        self.devices_frame.clear()
        self.place_device_controls()

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent)
        self.HDF_writer.start()

        # start control for all devices;
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["value"]:
                dev.clear_queues()
                dev.start()

        # update and start the monitoring thread
        self.monitoring = Monitoring(self.parent)
        self.monitoring.active.set()
        self.monitoring.start()

        # update program status
        self.parent.config['control_active'] = True
        self.status_label.setText("Running")

        # make all plots display the current run and file, and clear f(y) for fast data
        self.parent.config["files"]["plotting_hdf_fname"] = self.parent.config["files"]["hdf_fname"]
        self.parent.PlotsGUI.refresh_all_run_lists(select_defaults=False)
        self.parent.PlotsGUI.clear_all_fast_y()

    def stop_control(self):
        # check we're not stopped already
        if not self.parent.config['control_active']:
            return

        # stop devices
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                dev.active.clear()

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()

        # stop monitoring
        if self.monitoring.active.is_set():
            self.monitoring.active.clear()

        # stop all plots
        self.parent.PlotsGUI.stop_all_plots()

        # update status
        self.parent.config['control_active'] = False
        self.status_label.setText("Recording finished")

class PlotsGUI(qt.QSplitter):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.all_plots = {}
        self.place_GUI_elements()

        # QSplitter options
        self.setSizes([1,10000])
        self.setOrientation(PyQt5.QtCore.Qt.Vertical)

    def place_GUI_elements(self):
        # controls for all plots
        self.ctrls_box, ctrls_f = LabelFrame("Controls")
        self.addWidget(self.ctrls_box)
        ctrls_f.setColumnStretch(1, 1)

        pb = qt.QPushButton("Start all")
        pb.setToolTip("Start all plots (Ctrl+Shift+S).")
        pb.clicked[bool].connect(self.start_all_plots)
        ctrls_f.addWidget(pb, 0, 0)

        pb = qt.QPushButton("Stop all")
        pb.setToolTip("Stop all plots (Ctrl+Shift+Q).")
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

        # button to toggle plot controls visible/invisible
        pb = qt.QPushButton("Toggle controls")
        pb.setToolTip("Show or hide individual plot controls (Ctrl+T).")
        ctrls_f.addWidget(pb, 1, 5)
        pb.clicked[bool].connect(lambda val : self.toggle_all_plot_controls())

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
        box, self.plots_f = LabelFrame("Plots")
        self.addWidget(box)

        # add one plot
        self.add_plot()

    def add_plot(self, row=None, col=None):
        # find column for the plot if not given to the function
        try:
            col = int(col)
        except (ValueError, TypeError):
            col = 0

        # find row for the plot if not given to the function
        try:
            if row:
                row = int(row)
            else:
                row = 0
                for row_key, plot in self.all_plots.setdefault(col, {0:None}).items():
                    if plot:
                        row += 1
        except ValueError:
            logging.error("Row name not valid.")
            return

        # frame for the plot
        box = qt.QSplitter()
        box.setOrientation(PyQt5.QtCore.Qt.Vertical)
        self.plots_f.addWidget(box, row, col)

        # place the plot
        plot = Plotter(box, self.parent)
        plot.config["row"], plot.config["col"] = row, col
        self.all_plots.setdefault(col, {0:None}) # check the column is in the dict, else add it
        self.all_plots[col][row] = plot

        return plot

    def open_file(self, sect, config, qle):
        val = qt.QFileDialog.getOpenFileName(self, "Select file")[0]
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

    def refresh_all_run_lists(self, select_defaults=True):
        # get list of runs
        with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
            runs = list(f.keys())

        # update all run QComboBoxes
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.refresh_parameter_lists(select_defaults=select_defaults)
                    plot.update_labels()
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

    def toggle_all_plot_controls(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                plot.toggle_controls()

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
        try:
            with open(self.parent.config["files"]["plotting_config_fname"], "rb") as f:
                plot_configs = pickle.load(f)
        except OSError as err:
            logging.warning("Warning in load_plots: " + str(err))
            return

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

    def change_config(self, sect, config, val):
        self.parent.config[sect][config] = val

class Plotter(qt.QWidget):
    def __init__(self, frame, parent):
        super().__init__()
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
                "controls"          : True,
                "n_average"         : 1,
                "f(y)"              : "np.min(y)",
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

    def toggle_controls(self):
        if self.config.setdefault("controls", True):
            self.config["controls"] = False
            self.ctrls_box.hide()
        else:
            self.config["controls"] = True
            self.ctrls_box.show()

    def place_GUI_elements(self):
        # scrollable area for controls
        self.ctrls_box, ctrls_f = ScrollableLabelFrame("", fixed=True, vert_scroll=False)
        self.f.addWidget(self.ctrls_box)

        # select device
        self.dev_cbx = qt.QComboBox()
        self.dev_cbx.activated[str].connect(lambda val: self.change_config("device", val))
        self.dev_cbx.activated[str].connect(lambda val: self.refresh_parameter_lists())
        self.dev_cbx.activated[str].connect(self.update_labels)
        update_QComboBox(
                cbx     = self.dev_cbx,
                options = self.parent.ControlGUI.get_dev_list(),
                value   = self.config["device"]
            )
        ctrls_f.addWidget(self.dev_cbx, 0, 0)

        # get list of runs
        try:
            with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
                runs = list(f.keys())
        except OSError as err:
            runs = ["(no runs found)"]
            logging.warning("Warning in class Plotter: " + str(err))

        # select run
        self.run_cbx = qt.QComboBox()
        self.run_cbx.setMaximumWidth(100)
        self.run_cbx.activated[str].connect(lambda val: self.change_config("run", val))
        self.run_cbx.activated[str].connect(self.update_labels)
        update_QComboBox(
                cbx     = self.run_cbx,
                options = runs,
                value   = runs[-1]
            )
        ctrls_f.addWidget(self.run_cbx, 0, 1)

        # select x, y, and z

        self.x_cbx = qt.QComboBox()
        self.x_cbx.setToolTip("Select the independent variable.")
        self.x_cbx.activated[str].connect(lambda val: self.change_config("x", val))
        self.x_cbx.activated[str].connect(self.update_labels)
        ctrls_f.addWidget(self.x_cbx, 1, 0)

        self.y_cbx = qt.QComboBox()
        self.y_cbx.setToolTip("Select the dependent variable.")
        self.y_cbx.activated[str].connect(lambda val: self.change_config("y", val))
        self.y_cbx.activated[str].connect(self.update_labels)
        ctrls_f.addWidget(self.y_cbx, 1, 1)

        self.z_cbx = qt.QComboBox()
        self.z_cbx.setToolTip("Select the variable to divide y by.")
        self.z_cbx.activated[str].connect(lambda val: self.change_config("z", val))
        ctrls_f.addWidget(self.z_cbx, 1, 2)

        self.refresh_parameter_lists()

        # plot range controls
        self.x0_qle = qt.QLineEdit()
        self.x0_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.x0_qle, 1, 3)
        self.x0_qle.setText(self.config["x0"])
        self.x0_qle.setToolTip("x0 = index of first point to plot")
        self.x0_qle.textChanged[str].connect(lambda val: self.change_config("x0", val))

        self.x1_qle = qt.QLineEdit()
        self.x1_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.x1_qle, 1, 4)
        self.x1_qle.setText(self.config["x1"])
        self.x1_qle.setToolTip("x1 = index of last point to plot")
        self.x1_qle.textChanged[str].connect(lambda val: self.change_config("x1", val))

        self.y0_qle = qt.QLineEdit()
        self.y0_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.y0_qle, 1, 5)
        self.y0_qle.setText(self.config["y0"])
        self.y0_qle.setToolTip("y0 = lower y limit")
        self.y0_qle.textChanged[str].connect(lambda val: self.change_config("y0", val))
        self.y0_qle.textChanged[str].connect(lambda val: self.change_y_limits())

        self.y1_qle = qt.QLineEdit()
        self.y1_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.y1_qle, 1, 6)
        self.y1_qle.setText(self.config["y1"])
        self.y1_qle.setToolTip("y1 = upper y limit")
        self.y1_qle.textChanged[str].connect(lambda val: self.change_config("y1", val))
        self.y1_qle.textChanged[str].connect(lambda val: self.change_y_limits())

        # plot refresh rate
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setMaximumWidth(50)
        self.dt_qle.setText("dt")
        self.dt_qle.setToolTip("Delay between updating the plot, i.e. smaller dt means faster plot refresh rate.")
        self.dt_qle.textChanged[str].connect(lambda val: self.change_config("dt", val))
        ctrls_f.addWidget(self.dt_qle, 1, 7)

        # start button
        self.start_pb = qt.QPushButton("Start")
        self.start_pb.setMaximumWidth(50)
        self.start_pb.clicked[bool].connect(self.start_animation)
        ctrls_f.addWidget(self.start_pb, 0, 3)

        # HDF/Queue
        self.HDF_pb = qt.QPushButton("HDF")
        self.HDF_pb.setToolTip("Force reading the data from HDF instead of the queue.")
        self.HDF_pb.setMaximumWidth(50)
        self.HDF_pb.clicked[bool].connect(self.toggle_HDF_or_queue)
        ctrls_f.addWidget(self.HDF_pb, 0, 4)

        # toggle log/lin
        pb = qt.QPushButton("Log/Lin")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_log_lin)
        ctrls_f.addWidget(pb, 0, 5)

        # toggle lines/points
        pb = qt.QPushButton("\u26ab / \u2014")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_points)
        ctrls_f.addWidget(pb, 0, 6)

        # for displaying a function of the data

        self.fn_qle = qt.QLineEdit()
        self.fn_qle.setText(self.config["f(y)"])
        self.fn_qle.setToolTip("Apply the specified function before plotting the data.")
        self.fn_qle.textChanged[str].connect(lambda val: self.change_config("f(y)", val))
        ctrls_f.addWidget(self.fn_qle, 0, 2)

        self.fn_pb = qt.QPushButton("f(y)")
        self.fn_pb.setToolTip("Apply the specified function before plotting the data. Double click to clear the old calculations for fast data.")
        self.fn_pb.setMaximumWidth(50)
        self.fn_pb.clicked[bool].connect(self.toggle_fn)
        ctrls_f.addWidget(self.fn_pb, 0, 7)

        # for averaging last n curves
        self.avg_qle = qt.QLineEdit()
        self.avg_qle.setMaximumWidth(50)
        self.avg_qle.setToolTip("Enter the number of traces to average. Default = 1, i.e. no averaging.")
        self.avg_qle.setText("avg?")
        self.avg_qle.textChanged[str].connect(lambda val: self.change_config("n_average", val, typ=int))
        ctrls_f.addWidget(self.avg_qle, 1, 8)

        # button to delete plot
        pb = qt.QPushButton("\u274c")
        pb.setMaximumWidth(50)
        pb.setToolTip("Delete the plot")
        ctrls_f.addWidget(pb, 0, 8)
        pb.clicked[bool].connect(lambda val: self.destroy())

    def refresh_parameter_lists(self, select_defaults=True):
        # update the list of available devices
        available_devices = self.parent.ControlGUI.get_dev_list()
        update_QComboBox(
                cbx     = self.dev_cbx,
                options = available_devices,
                value   = self.config["device"]
            )

        # check device is available, else select the first device on the list
        if self.config["device"] in available_devices:
            self.dev = self.parent.devices[self.config["device"]]
        elif len(self.parent.devices) != 0:
            self.config["device"] = available_devices[0]
            self.dev = self.parent.devices[self.config["device"]]
        else:
            logging.warning("Plot error: No devices in self.parent.devices.")
            return
        self.dev_cbx.setCurrentText(self.config["device"])

        # select latest run
        try:
            with h5py.File(self.parent.config["files"]["plotting_hdf_fname"], 'r') as f:
                self.config["run"] = list(f.keys())[-1]
                self.run_cbx.setCurrentText(self.config["run"])
        except OSError as err:
            self.config["run"] = "(no runs found)"
            self.run_cbx.setCurrentText(self.config["run"])
            logging.warning("Warning in class Plotter: " + str(err))

        # get parameters
        if self.dev.config["slow_data"]:
            self.param_list = split(self.dev.config["attributes"]["column_names"])
        else:
            self.param_list = ["(none)"] + split(self.dev.config["attributes"]["column_names"])
        if not self.param_list:
            logging.warning("Plot error: No parameters to plot.")
            return

        # check x and y are good
        if not self.config["x"] in self.param_list:
            if self.dev.config["slow_data"]: # fast data does not need an x variable
                select_defaults = True
        if not self.config["y"] in self.param_list:
            select_defaults = True

        # select x and y
        if select_defaults:
            if self.dev.config["slow_data"]:
                self.config["x"] = self.param_list[0]
            else:
                self.config["x"] = "(none)"
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

        if self.dev.config["controls"]["HDF_enabled"]["value"]:
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
            if self.dev.config["slow_data"]: # fast data does not need an x variable
                logging.warning("Plot warning: x not valid.")
                return False

        if not self.config["y"] in self.param_list:
            logging.warning("Plot error: y not valid.")
            return False

        # return
        return True

    def get_raw_data_from_HDF(self):
        if not self.dev.config["controls"]["HDF_enabled"]["value"]:
            logging.warning("Plot error: cannot plot from HDF when HDF is disabled")
            self.toggle_HDF_or_queue()
            return

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

                # get the latest curve
                try:
                    dset = grp[self.dev.config["name"] + "_" + str(rec_num)]
                except KeyError as err:
                    logging.warning("Plot error: not found in HDF: " + str(err))
                    return None

                x = np.arange(dset.shape[0])
                y = dset[:, self.param_list.index(self.config["y"])]

                # divide y by z (if applicable)
                if self.config["z"] in self.param_list:
                    y = y / dset[:, self.param_list.index(self.config["z"])]

                # average sanity check
                if self.config["n_average"] > len(grp):
                    logging.warning("Plot error: Cannot average more traces than exist.")
                    return x, y

                # average last n curves (if applicable)
                for i in range(self.config["n_average"] - 1):
                    try:
                        dset = grp[self.dev.config["name"] + "_" + str(rec_num-i)]
                    except KeyError as err:
                        logging.warning("Plot averaging error: " + str(err))
                        break
                    if self.config["z"] in self.param_list:
                        y += dset[:, self.param_list.index(self.config["y"])] \
                                / dset[:, self.param_list.index(self.config["z"])]
                    else:
                        y += dset[:, self.param_list.index(self.config["y"])]
                if self.config["n_average"] > 0:
                    y = y / self.config["n_average"]

        return x, y

    def get_raw_data_from_queue(self):
        # for slow data: copy the queue contents into a np array
        if self.dev.config["slow_data"]:
            dset = np.array(self.dev.config["plots_queue"])
            if len(dset.shape) < 2:
                return None
            x = dset[:, self.param_list.index(self.config["x"])]
            y = dset[:, self.param_list.index(self.config["y"])]

            # divide y by z (if applicable)
            if self.config["z"] in self.param_list:
                y = y / dset[0][0, self.param_list.index(self.config["z"])]

        # for fast data: return only the latest value
        if not self.dev.config["slow_data"]:
            try:
                dset = self.dev.config["plots_queue"][-1]
            except IndexError:
                return None
            x = np.arange(dset[0].shape[2])
            y = dset[0][0, self.param_list.index(self.config["y"])]

            # divide y by z (if applicable)
            if self.config["z"] in self.param_list:
                y = y / dset[0][0, self.param_list.index(self.config["z"])]

            # if not averaging, return the data
            if self.config["n_average"] < 2:
                return x, y

            # average sanity check
            if self.config["n_average"] > self.dev.config["plots_queue_maxlen"]:
                logging.warning("Plot error: Cannot average more traces than are stored in plots_queue when plotting from the queue.")
                return x, y

            # average last n curves (if applicable)
            y_avg = np.array(y)
            for i in range(self.config["n_average"] - 1):
                try:
                    dset = self.dev.config["plots_queue"][-(i+1)]
                except (KeyError,IndexError) as err:
                    logging.warning("Plot averaging error: " + str(err))
                    break
                y_avg += dset[0][0, self.param_list.index(self.config["y"])]
            if self.config["n_average"] > 0:
                y = y_avg / self.config["n_average"]

        return x, y

    def get_data(self):
        # decide where to get data from
        if self.dev.config["plots_queue_maxlen"] < 1\
                or not self.parent.config['control_active']\
                or self.config["from_HDF"]:
            data = self.get_raw_data_from_HDF()
        else:
            data = self.get_raw_data_from_queue()

        try:
            x, y = data[0], data[1]
            if len(x) < 5: # require at least five datapoints
                raise ValueError
        except (ValueError, TypeError):
            return None

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
            logging.warning("Plot error: data shapes not matching: " +
                    str(x.shape) + " != " + str(y.shape))
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
                # test the result is a scalar
                try:
                    float(y_fn)
                except Exception as err:
                    raise TypeError(str(err))
            except Exception as err:
                logging.warning(str(err))
                return x[x0:x1], y[x0:x1]
            else:
                self.fast_y.append(y_fn)
                return np.arange(len(self.fast_y)), np.array(self.fast_y)

    def replot(self):
        # check parameters
        if not self.parameters_good():
            logging.warning("Plot warning: bad parameters.")
            return

        # get data
        data = self.get_data()
        if not data:
            return

        # plot data
        if not self.plot:
            self.plot = pg.PlotWidget()
            self.plot.showGrid(True, True)
            self.f.addWidget(self.plot)
        if not self.curve:
            self.curve = self.plot.plot(*data, symbol=self.config["symbol"])
            self.update_labels()
        else:
            self.curve.setData(*data)

    def update_labels(self):
        if self.plot:
            self.plot.setLabel("bottom", self.config["x"])
            self.plot.setLabel("left", self.config["y"])
            self.plot.setLabel("top", self.config["device"] + "; " + self.config["run"])

    def change_y_limits(self):
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
        self.stop_animation()
        # get the position of the plot
        row, col = self.config["row"], self.config["col"]

        # remove the plot from the all_plots dict
        self.parent.PlotsGUI.all_plots[col][row] = None

        # remove the GUI elements related to the plot
        try:
            self.parent.PlotsGUI.plots_f.itemAtPosition(row, col).widget().setParent(None)
        except AttributeError as err:
            logging.warning("Plot warning: cannot remove plot: " + str(err))

    def toggle_HDF_or_queue(self, state=""):
        if not self.dev.config["controls"]["HDF_enabled"]["value"]:
            logging.warning("Plot error: cannot plot from HDF when HDF is disabled")
            return

        if self.config["from_HDF"]:
            self.config["from_HDF"] = False
            self.HDF_pb.setText("Queue")
            self.HDF_pb.setToolTip("Force reading the data from the Queue instead of the HDF file.")
        else:
            self.config["from_HDF"] = True
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
            self.fn_pb.setText("Raw")
            self.fn_pb.setToolTip("Display raw data and/or clear the old calculations for fast data.")
        else:
            self.config["fn"] = False
            self.fast_y = []
            self.fn_pb.setText("f(y)")
            self.fn_pb.setToolTip("Apply the specified function before plotting the data. Double click to clear the old calculations for fast data.")

class CentrexGUI(qt.QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle('CENTREX DAQ')
        #self.setWindowFlags(PyQt5.QtCore.Qt.Window | PyQt5.QtCore.Qt.FramelessWindowHint)

        # read program configuration
        self.config = {
                "time_offset"        : 0,
                "control_active"     : False,
                "control_visible"    : True,
                "monitoring_visible" : False,
                "plots_visible"      : False,
                "horizontal_split"   : True,
                }
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for config_group, configs in settings.items():
            self.config[config_group] = {}
            for key, val in configs.items():
                self.config[config_group][key] = val

        # GUI elements
        self.ControlGUI = ControlGUI(self)
        if self.config["general"].get("style") == "dark":
            self.ControlGUI.toggle_style()
        self.PlotsGUI = PlotsGUI(self)

        # put GUI elements in a QSplitter
        self.qs = qt.QSplitter()
        self.setCentralWidget(self.qs)
        self.qs.addWidget(self.ControlGUI)
        self.qs.addWidget(self.PlotsGUI)
        self.PlotsGUI.hide()

        # default main window size
        self.resize(700, 900)

        # keyboard shortcuts
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+C"), self)\
                .activated.connect(self.ControlGUI.toggle_control)
        qt.QShortcut(QtGui.QKeySequence("Esc"), self)\
                .activated.connect(lambda: self.ControlGUI.toggle_control(show_only=True))
        qt.QShortcut(QtGui.QKeySequence("Ctrl+P"), self)\
                .activated.connect(self.ControlGUI.toggle_plots)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+M"), self)\
                .activated.connect(self.ControlGUI.toggle_monitoring)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+D"), self)\
                .activated.connect(self.ControlGUI.toggle_style)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+S"), self)\
                .activated.connect(self.ControlGUI.start_control)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self)\
                .activated.connect(self.ControlGUI.stop_control)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+T"), self)\
                .activated.connect(self.PlotsGUI.toggle_all_plot_controls)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+V"), self)\
                .activated.connect(self.toggle_orientation)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+S"), self)\
                .activated.connect(self.PlotsGUI.start_all_plots)
        qt.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Q"), self)\
                .activated.connect(self.PlotsGUI.stop_all_plots)

        self.show()

    def toggle_orientation(self):
        if self.config["horizontal_split"]:
            self.qs.setOrientation(PyQt5.QtCore.Qt.Vertical)
            self.config["horizontal_split"] = False
            self.ControlGUI.orientation_pb.setText("Vertical mode")
            self.ControlGUI.orientation_pb.setToolTip("Put controls and plots/monitoring side-by-side (Ctrl+V).")
        else:
            self.qs.setOrientation(PyQt5.QtCore.Qt.Horizontal)
            self.config["horizontal_split"] = True
            self.ControlGUI.orientation_pb.setText("Horizontal mode")
            self.ControlGUI.orientation_pb.setToolTip("Put controls and plots/monitoring on top of each other (Ctrl+V).")

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
