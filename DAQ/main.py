import PyQt5.QtWidgets as qt
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
            except IndexError as err:
                logging.error("Cannot read device config file: " + str(err))
                return

            ## populate the list of device controls
            #try:
            #    self.read_device_controls(params)
            #except IndexError as err:
            #    logging.error("Cannot read device config file: " + str(err))
            #    return

            # make a Device object
            self.parent.devices[params["device"]["name"]] = Device(dev_config)

    def read_device_config_options(self, params):
        return {
                    "name"              : params["device"]["name"],
                    "label"             : params["device"]["label"],
                    "path"              : params["device"]["path"],
                    "correct_response"  : params["device"]["correct_response"],
                    "single_dataset"    : True if params["device"]["single_dataset"]=="True" else False,
                    "row"               : params["device"]["row"],
                    "rowspan"           : params["device"]["rowspan"],
                    "monitoring_row"    : params["device"]["monitoring_row"],
                    "column"            : params["device"]["column"],
                    "columnspan"        : params["device"]["columnspan"],
                    "monitoring_column" : params["device"]["monitoring_column"],
                    "constr_params"     : [x.strip() for x in params["device"]["constr_params"].split(",")],
                    "attributes"        : params["attributes"],
                }

    def read_device_controls(self):
            ctrls = {}
            for c in params.sections():
                if params[c].get("type") == "Checkbutton":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
                    ctrls[c]["var"]        = tk.BooleanVar()
                    ctrls[c]["var"].set(params[c]["value"])

                elif params[c].get("type") == "Hidden":
                    ctrls[c] = {}
                    ctrls[c]["var"] = tk.StringVar()
                    ctrls[c]["var"].set(params[c]["value"])
                    ctrls[c]["type"] = "Hidden"

                elif params[c].get("type") == "Button":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
                    ctrls[c]["command"]    = params[c].get("command")
                    ctrls[c]["argument"]   = params[c]["argument"]
                    ctrls[c]["align"]      = params[c].get("align")

                elif params[c].get("type") == "Entry":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
                    ctrls[c]["width"]      = params[c].get("width")
                    ctrls[c]["enter_cmd"]  = params[c].get("enter_command")
                    ctrls[c]["var"]        = tk.StringVar()
                    ctrls[c]["var"].set(params[c]["value"])

                elif params[c].get("type") == "OptionMenu":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
                    ctrls[c]["command"]    = params[c]["command"]
                    ctrls[c]["options"]    = [x.strip() for x in params[c]["options"].split(",")]
                    ctrls[c]["var"]        = tk.StringVar()
                    ctrls[c]["var"].set(params[c]["value"])

                elif params[c].get("type") == "ControlsRow":
                    ctrls[c] = {}
                    ctrls[c]["label"]           = params[c]["label"]
                    ctrls[c]["type"]            = params[c]["type"]
                    ctrls[c]["row"]             = int(params[c]["row"])
                    ctrls[c]["col"]             = int(params[c]["col"])
                    ctrls[c]["control_names"]   = [x.strip() for x in params[c]["control_names"].split(",")]
                    ctrls[c]["control_labels"]  = [x.strip() for x in params[c]["control_labels"].split(",")]
                    ctrls[c]["control_types"]   = [x.strip() for x in params[c]["control_types"].split(",")]
                    ctrls[c]["control_widths"] = params[c].get("control_widths")
                    if ctrls[c]["control_widths"]:
                        ctrls[c]["control_widths"] = [int(x) for x in ctrls[c]["control_widths"].split(",")]
                    ctrls[c]["control_commands"] = params[c].get("control_commands")
                    if ctrls[c]["control_commands"]:
                        ctrls[c]["control_commands"] = ctrls[c]["control_commands"].split(",")
                    ctrls[c]["control_options"] = []
                    control_options = params[c].get("control_options")
                    if not control_options:
                        control_options = ""
                    for c_o in control_options.split(";"):
                        ctrls[c]["control_options"].append([x.strip() for x in c_o.split(",")])
                    ctrls[c]["control_values"]   = {}
                    for name, val in zip(ctrls[c]["control_names"], params[c]["control_values"].split(",")):
                        ctrls[c]["control_values"][name] = tk.StringVar()
                        ctrls[c]["control_values"][name].set(val.strip())

                elif params[c].get("type") == "ControlsTable":
                    ctrls[c] = {}
                    ctrls[c]["label"]         = params[c]["label"]
                    ctrls[c]["type"]          = params[c]["type"]
                    ctrls[c]["row"]           = int(params[c]["row"])
                    ctrls[c]["col"]           = int(params[c]["col"])
                    ctrls[c]["rowspan"]       = int(params[c]["rowspan"])
                    ctrls[c]["columnspan"]    = int(params[c]["columnspan"])
                    ctrls[c]["column_names"]  = [x.strip() for x in params[c]["column_names"].split(",")]
                    ctrls[c]["row_ids"]  = [x.strip() for x in params[c]["row_ids"].split(",")]
                    ctrls[c]["column_labels"] = [x.strip() for x in params[c]["column_labels"].split(",")]
                    ctrls[c]["column_types"]  = [x.strip() for x in params[c]["column_types"].split(",")]
                    ctrls[c]["column_widths"] = params[c].get("column_widths")
                    if ctrls[c]["column_widths"]:
                        ctrls[c]["column_widths"] = [int(x) for x in ctrls[c]["column_widths"].split(",")]
                    ctrls[c]["column_commands"] = params[c].get("column_commands")
                    if ctrls[c]["column_commands"]:
                        ctrls[c]["column_commands"] = ctrls[c]["column_commands"].split(",")
                    ctrls[c]["column_options"] = []
                    for c_v in params[c].get("column_options").split(";"):
                        ctrls[c]["column_options"].append([x.strip() for x in c_v.split(",")])
                    ctrls[c]["column_values"] = []
                    for c_v in params[c].get("column_values").split(";"):
                        ctrls[c]["column_values"].append([])
                        for val in c_v.split(","):
                            ctrls[c]["column_values"][-1].append(tk.StringVar())
                            ctrls[c]["column_values"][-1][-1].set(val.strip())
            return ctrls

    def place_GUI_elements(self):
        # main frame for all ControlGUI elements
        self.cgf = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.cgf, text="Control")
        self.parent.rowconfigure(0, weight=1)
        self.cgf.rowconfigure(2, weight=1)

        ########################################
        # control and status
        ########################################

        control_frame = tk.LabelFrame(self.cgf)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")
        control_frame.grid_columnconfigure(index=2, weight=1)

        # control start/stop buttons
        control_button = tk.Button(control_frame,
                text="\u26ab Start control", command = self.start_control)\
                .grid(row=0, column=0, sticky="nsew")
        stop_button = tk.Button(control_frame,
                text="\u2b1b Stop control", command = self.stop_control)\
                .grid(row=0, column=1, sticky="nsew")

        # the status label
        self.status = "stopped"
        self.status_message = tk.StringVar()
        self.status_message.set("Ready to start")
        self.status_label = tk.Label(control_frame, textvariable=self.status_message,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=3, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tk.LabelFrame(self.cgf, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky="ew")

        # config dir
        tk.Label(files_frame, text="Config dir:")\
                .grid(row=0, column=0, sticky=tk.E)
        tk.Entry(files_frame, width=64,
                textvariable=self.parent.config["files"]["config_dir"])\
                .grid(row=0, column=1, sticky="ew")
        tk.Button(files_frame, text="Open...",
                command = self.set_config_dir)\
                .grid(row=0, column=2, sticky=tk.W)

        # HDF file
        tk.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tk.E)
        tk.Entry(files_frame, width=64,
                textvariable=self.parent.config["files"]["hdf_fname"])\
                .grid(row=1, column=1, sticky="ew")
        tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=1, column=2, sticky=tk.W)

        # HDF writer loop delay
        tk.Label(files_frame, text="HDF writer loop delay:")\
                .grid(row=2, column=0, sticky=tk.E)
        tk.Entry(files_frame,
                textvariable=self.parent.config["general"]["hdf_loop_delay"])\
                .grid(row=2, column=1, sticky="nsew")

        # run name
        tk.Label(files_frame, text="Run name:")\
                .grid(row=3, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame,
                textvariable=self.parent.config["general"]["run_name"])\
                .grid(row=3, column=1, sticky="nsew")

        ########################################
        # devices
        ########################################

        # the control to send a custom command to a specified device
        fc = tk.LabelFrame(self.cgf, text="Send a custom command", padx=10, pady=10)
        fc.grid(row=2, padx=10, pady=10, sticky='ew')
        custom_command = tk.StringVar(fc, value='Enter command ...')
        cmd_entry = tk.Entry(fc, textvariable=custom_command, width=30)
        cmd_entry.grid(row=0, column=0, sticky='nsew')
        custom_dev = tk.StringVar(fc, value='Select device ...')
        dev_list = [dev_name for dev_name in self.parent.devices]
        if not dev_list:
            dev_list = ["(no devices)"]
        dev_selection = tk.OptionMenu(fc, custom_dev, *dev_list)
        dev_selection.grid(row=0, column=1, sticky="e")
        custom_button = tk.Button(fc, text="Send",
                command=lambda: self.queue_custom_command(custom_dev.get(), custom_command.get()))
        custom_button.grid(row=0, column=2, sticky='e')

        # button to refresh the list of COM ports
        tk.Button(fc, text="Refresh COM ports", command=self.refresh_COM_ports)\
                        .grid(row=0, column=3, padx=30, sticky='e')

        # all device-specific controls
        self.place_device_controls()

    def place_device_controls(self):
        self.fr = tk.LabelFrame(self.cgf, text="Devices")
        self.fr.grid(row=4, padx=10, pady=10, sticky='nsew')

        # make GUI elements for all devices
        for dev_name, dev in self.parent.devices.items():
            fd = tk.LabelFrame(self.fr, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"],
                    rowspan=dev.config["rowspan"], columnspan=dev.config["columnspan"])

            # the button to reload attributes
            attr_b = tk.Button(fd, text="Attrs", command=lambda dev=dev: self.reload_attrs(dev))
            attr_b.grid(row=0, column=20, sticky="nsew")

            # device-specific controls
            for c_name, c in dev.config["controls"].items():
                if c_name == "LabelFrame":
                    continue

                # place Checkbuttons
                if c["type"] == "Checkbutton":
                    c["Checkbutton"] = tk.Checkbutton(fd, variable=c["var"])
                    c["Checkbutton"].grid(row=c["row"], column=c["col"], sticky=tk.W)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=c["row"], column=c["col"]-1, sticky=tk.E)

                # place Buttons
                if c["type"] == "Button":
                    # determine the button command
                    if c["argument"] == "":
                        command = lambda dev=dev, cmd=c["command"]+"()": self.queue_command(dev, cmd)
                    else:
                        command = lambda dev=dev, cmd=c["command"],\
                                    arg=dev.config["controls"][c["argument"]]["var"]:\
                                    self.queue_command(dev, cmd+"("+arg.get()+")")
                    # place the button with that command
                    c["Button"] = tk.Button(fd, text=c["label"], command=command)
                    if c.get("align") == None:
                        c["Button"].grid(row=c["row"], column=c["col"], sticky=tk.W)
                    else:
                        c["Button"].grid(row=c["row"], column=c["col"], sticky=c["align"])

                # place Entries
                elif c["type"] == "Entry":
                    if c["width"]:
                        c["Entry"] = tk.Entry(fd, textvariable=c["var"], width=c["width"])
                        c["Entry"].grid(row=c["row"], column=c["col"],sticky="w")
                    else:
                        c["Entry"] = tk.Entry(fd, textvariable=c["var"])
                        c["Entry"].grid(row=c["row"], column=c["col"],sticky="nsew")
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=c["row"], column=c["col"]-1, sticky=tk.E)
                    if c["enter_cmd"]:
                        command = lambda x, dev=dev, cmd=c["enter_cmd"], arg=c["var"]:\
                                    self.queue_command(dev, cmd+"("+arg.get()+")")
                        c["Entry"].bind("<Return>", command)

                # place OptionMenus
                elif c["type"] == "OptionMenu":
                    if c["command"] == "":
                        c["OptionMenu"] = tk.OptionMenu(fd, c["var"], *c["options"])
                    else:
                        c["OptionMenu"] = tk.OptionMenu(fd, c["var"], *c["options"],
                                command= lambda x, dev=dev, cmd=c["command"]:
                                    self.queue_command(dev, cmd+"('"+x.strip()+"')"))
                    c["OptionMenu"].grid(row=c["row"], column=c["col"], sticky=tk.W)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=c["row"], column=c["col"]-1, sticky=tk.E)

                # place ControlsRows
                elif c["type"] == "ControlsRow":
                    c["Frame"] = tk.Frame(fd)
                    c["Frame"].grid(row=c["row"], column=c["col"], sticky='w', pady=10)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=c["row"], column=c["col"]-1, sticky=tk.E)
                    controls_row_args = dict((name, c["control_values"][name]) for name in c["control_names"] if c["control_values"][name].get() != '')
                    for i, name in enumerate(c["control_names"]):
                        c["ctrls"] = {}
                        if c["control_types"][i] == "Entry":
                            c["ctrls"][name] = tk.Entry(c["Frame"],
                                    width=c["control_widths"][i], textvariable=c["control_values"][name])
                        elif c["control_types"][i] == "Button":
                            c["ctrls"][name] = tk.Button(
                                    c["Frame"], width = c["control_widths"][i],
                                    text=c["control_values"][name].get(),
                                    command=lambda dev=dev, args = controls_row_args,
                                        cmd=c["control_commands"][i]: self.queue_command(dev, cmd+"(**"+str(dict((n,v.get()) for n,v in args.items()))+")")
                                )
                        elif c["control_types"][i] == "OptionMenu":
                            c["ctrls"][name] = tk.OptionMenu(c["Frame"],
                                    c["control_values"][name], *c["control_options"][i])
                        elif c["control_types"][i] == "Checkbutton":
                            c["ctrls"][name] = \
                            tk.Checkbutton(c["Frame"], variable=c["control_values"][name])
                        elif c["control_types"][i] == "CheckbuttonCmd":
                            c["ctrls"][name] = \
                            tk.Checkbutton(c["Frame"], variable=c["control_values"][name],
                                           command=lambda dev=dev, arg = c["control_values"][name],
                                           cmd=c["control_commands"][i]: self.queue_command(dev, cmd+"("+arg.get()+")"))

                        c["ctrls"][name].grid(row=1, column=i+1, sticky="nsew", padx=5)
                        tk.Label(c["Frame"], text=c["control_labels"][i])\
                                .grid(row=0, column=i+1)

                # place ControlsTables
                elif c["type"] == "ControlsTable":
                    c["Frame"] = tk.LabelFrame(fd, text=c["label"])
                    c["Frame"].grid(row=c["row"], column=c["col"],
                            columnspan=c["columnspan"], rowspan=c["rowspan"], sticky='w', pady=10, padx=3)
                    for i, name in enumerate(c["column_names"]):
                        tk.Label(c["Frame"], text=c["column_labels"][i]).grid(row=0, column=i)
                        for j, var in enumerate(c["column_values"][i]):
                            cmd = c["column_commands"][i] if c["column_commands"] else None
                            if c["column_types"][i] == "Checkbutton":
                                if cmd:
                                    arg = "('" + c["row_ids"][j] + "', " + var.get() + ")"
                                    cmd_fn = lambda dev=dev, cmd=cmd: self.queue_command(dev, cmd+arg)
                                    tk.Checkbutton(c["Frame"], variable=var, command=cmd_fn).\
                                                    grid(row=j+1, column=i)
                                else:
                                    tk.Checkbutton(c["Frame"], variable=var).grid(row=j+1, column=i)
                            elif c["column_types"][i] == "Entry":
                                tk.Entry(c["Frame"], textvariable=var,
                                        width=c["column_widths"][i]).grid(row=j+1, column=i)
                                if cmd_fn:
                                    pass # TODO
                            elif c["column_types"][i] == "Label":
                                tk.Label(c["Frame"], textvariable=var).grid(row=j+1, column=i)
                            elif c["column_types"][i] == "OptionMenu":
                                if cmd:
                                    arg = "(" + c["row_ids"][j] + ", " + var.get() + ")"
                                    cmd_fn = lambda dev=dev, cmd=cmd: self.queue_command(dev, cmd+arg)
                                    om = tk.OptionMenu(
                                            c["Frame"], var,
                                            *c["column_options"][i],
                                            command=cmd_fn
                                        )
                                else:
                                    om = tk.OptionMenu(c["Frame"], var, *c["column_options"][i])
                                om.config(width=c["column_widths"][i])
                                om.grid(row=j+1, column=i)

    def set_config_dir(self):
        self.open_dir("config_dir")
        self.read_device_config()

        # update device controls
        self.fr.destroy()
        self.place_device_controls()

        # update device data in MonitoringGUI
        self.parent.monitoring.dev_f.destroy()
        self.parent.monitoring.place_device_specific_items()

    def queue_custom_command(self, dev_name, command):
        # check the command is valid
        cmd = command.strip()
        search = re.compile(r'[^A-Za-z0-9()]').search
        if bool(search(cmd)):
            messagebox.showerror("Command error", "Invalid command.")
            return

        # check the device is valid
        dev = self.parent.devices.get(dev_name)
        if not dev:
            messagebox.showerror("Device error", "Device not found.")
            return
        if not dev.operational:
            messagebox.showerror("Device error", "Device not operational.")
            return

        self.queue_command(dev, cmd)

    def queue_command(self, dev, command):
        dev.commands.append(command)

    def reload_attrs(self, dev):
        # read attributes from file
        params = configparser.ConfigParser()
        params.read(dev.config["config_fname"])
        dev.config["attributes"] = params["attributes"]

        # update the column names in MonitoringGUI
        col_names = dev.config["attributes"]["column_names"].split(',')
        col_names = [x.strip() for x in col_names]
        dev.column_names.set("\n".join(col_names))

        # display the new attributes in a message box
        attrs = ""
        for attr_name,attr in dev.config["attributes"].items():
            attrs += attr_name + ": " + str(attr) + "\n\n"
        messagebox.showinfo("Device attributes", attrs)

    def refresh_COM_ports(self):
        rl = pyvisa.ResourceManager().list_resources()
        for dev_name, dev in self.parent.devices.items():
            # check device has a COM_port control
            if not dev.config["controls"].get("COM_port"):
                continue

            # update the menu of COM_port options
            menu = dev.config["controls"].get("COM_port")["OptionMenu"]["menu"]
            COM_var = dev.config["controls"].get("COM_port")["var"]
            menu.delete(0, "end")
            for string in rl:
                menu.add_command(label=string,
                        command=lambda value=string, COM_var=COM_var: COM_var.set(value))

    def open_file(self, prop):
        fname = filedialog.asksaveasfilename(
                initialdir = self.parent.config["files"][prop].get(),
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))
        if not fname:
            return
        else:
            self.parent.config["files"][prop].set(fname)

    def open_dir(self, prop):
        fname = filedialog.askdirectory(
                initialdir = self.parent.config["files"][prop].get(),
                title = "Select directory")
        if not fname:
            return
        else:
            self.parent.config["files"][prop].set(fname)

    def start_control(self):
        # check we're not running already
        if self.status == "running":
            return

        # select the time offset
        self.parent.config["time_offset"] = time.time()

        # setup & check connections of all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.setup_connection(self.parent.config["time_offset"])
                if not dev.operational:
                    messagebox.showerror("Device error",
                            "Error: " + dev.config["label"] + " not responding correctly, or cannot access the directory for data storage.")
                    self.status_message.set("Device configuration error")
                    return

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent)
        self.HDF_writer.start()

        # start control for all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.clear_queues()
                dev.start()

        # update and start the monitoring thread
        self.parent.monitoring.refresh_column_names_and_units()
        self.parent.monitoring.start_monitoring()

        # update program status
        self.status = "running"
        self.status_message.set("Running")

        # make all plots display the current run and file and update parameters
        HDF_fname = self.parent.config["files"]["hdf_fname"].get()
        self.parent.plots.refresh_run_list(HDF_fname)
        self.parent.config["files"]["plotting_hdf_fname"].set(HDF_fname)
        self.parent.plots.refresh_all_parameter_lists()

    def stop_control(self):
        # check we're not stopped already
        if self.status == "stopped":
            return

        # stop devices, waiting for threads to finish
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                dev.active.clear()

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()

        # stop monitoring
        self.parent.monitoring.stop_monitoring()

        # stop all plots
        self.parent.plots.stop_all()

        self.status = "stopped"
        self.status_message.set("Recording finished")

class MonitoringGUI(qt.QWidget):
    def __init__(self, parent):
        super(qt.QWidget, self).__init__(parent)
        self.parent = parent
        #self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all MonitoringGUI elements
        self.frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.frame, text="Monitoring")

        self.place_device_specific_items()

        # monitoring controls frame
        self.ctrls_f = tk.Frame(self.frame)
        self.ctrls_f.grid(row=0, column=0, padx=10, pady=10)

        # general monitoring controls
        self.gen_f = tk.LabelFrame(self.ctrls_f, text="General")
        self.gen_f.grid(row=0, column=0, padx=10, pady=10, sticky='nsew')
        tk.Label(self.gen_f, text="Loop delay [s]:").grid(row=0, column=0)
        self.parent.config["monitoring_dt"] = tk.StringVar()
        self.parent.config["monitoring_dt"].set("1")
        tk.Entry(self.gen_f, textvariable=self.parent.config["monitoring_dt"]).grid(row=0, column=1)
        tk.Label(self.gen_f, text="InfluxDB enabled:").grid(row=1, column=0)
        tk.Checkbutton(
                self.gen_f,
                variable=self.parent.config["influxdb"]["enabled"],
                onvalue = "True",
                offvalue = "False",
            ).grid(row=1, column=1, sticky='w')

        # InfluxDB controls
        conf = self.parent.config["influxdb"]
        self.db_f = tk.LabelFrame(self.ctrls_f, text="InfluxDB")
        self.db_f.grid(row=0, column=1, padx=10, pady=10, sticky='nsew')
        tk.Label(self.db_f, text="Host IP").grid(row=0, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["host"]).grid(row=0, column=1, sticky='w')
        tk.Label(self.db_f, text="Port").grid(row=1, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["port"]).grid(row=1, column=1, sticky='w')
        tk.Label(self.db_f, text="Username").grid(row=2, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["username"]).grid(row=2, column=1, sticky='w')
        tk.Label(self.db_f, text="Pasword").grid(row=3, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["password"]).grid(row=3, column=1, sticky='w')

        # for displaying warnings
        self.w_f = tk.LabelFrame(self.ctrls_f, text="Warnings")
        self.w_f.grid(row=0, column=2, padx=10, pady=10, sticky='nsew')
        self.last_warning = tk.StringVar()
        self.last_warning.set("no warning")
        tk.Label(self.w_f, textvariable=self.last_warning).grid()

    def place_device_specific_items(self):
        # frame for device data
        self.dev_f = tk.LabelFrame(self.frame, text="Devices")
        self.dev_f.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # device-specific text
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            fd = tk.LabelFrame(self.dev_f, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["monitoring_row"], column=dev.config["monitoring_column"])

            # length of the data queue
            dev.qsize = tk.StringVar()
            dev.qsize.set(0)
            tk.Label(fd, text="Queue length:").grid(row=0, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.qsize).grid(row=0, column=1, sticky='nw')

            # NaN count
            tk.Label(fd, text="NaN count:").grid(row=1, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.nan_count).grid(row=1, column=1, sticky='nw')

            # column names
            dev.col_names_list = dev.config["attributes"]["column_names"].split(',')
            dev.col_names_list = [x.strip() for x in dev.col_names_list]
            dev.column_names = tk.StringVar()
            dev.column_names.set("\n".join(dev.col_names_list))
            tk.Message(fd, textvariable=dev.column_names, anchor='ne', justify="right", width=350)\
                    .grid(row=2, column=0, sticky='nsew')

            # data
            dev.last_data = tk.StringVar()
            tk.Message(fd, textvariable=dev.last_data, anchor='nw', width=350)\
                    .grid(row=2, column=1, sticky='nsew')

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units = tk.StringVar()
            dev.units.set("\n".join(units))
            tk.Message(fd, textvariable=dev.units, anchor='nw', width=350)\
                    .grid(row=2, column=2, sticky='nsew')

            # latest event / command sent to device & its return value
            tk.Label(fd, text="Last event:").grid(row=3, column=0, sticky='ne')
            dev.last_event = tk.StringVar()
            tk.Message(fd, textvariable=dev.last_event, anchor='nw', width=150)\
                    .grid(row=3, column=1, columnspan=2, sticky='nw')

    def refresh_column_names_and_units(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            # column names
            col_names = dev.config["attributes"]["column_names"].split(',')
            col_names = [x.strip() for x in col_names]
            dev.column_names.set("\n".join(col_names))

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units.set("\n".join(units))

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
        return

        # variable to keep track of the plots
        self.all_plots = {}

        # main frame for all PlotsGUI elements
        self.nb_frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.nb_frame, text="Plots")

        # frame
        self.f = tk.Frame(self.nb_frame)
        self.f.grid(row=0, column=0, sticky='n')

        # controls for all plots
        ctrls_f = tk.LabelFrame(self.f, text="Plot controls")
        ctrls_f.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
        tk.Button(ctrls_f, text="Start all", command=self.start_all)\
                .grid(row=0, column=0, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Stop all", command=self.stop_all)\
                .grid(row=0, column=1, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Delete all", command=self.delete_all)\
                .grid(row=0, column=3, sticky='e', padx=10)

        # for setting refresh rate of all plots
        self.dt_var = tk.StringVar()
        self.dt_var.set("dt")
        dt_entry = tk.Entry(ctrls_f, textvariable=self.dt_var, width=7)
        dt_entry.grid(row=0, column=4, sticky='w', padx=5)
        dt_entry.bind("<Return>", self.change_all_animation_dt)

        # control to select how many data points to display in a graph (to speed up plotting)

        self.max_pts = tk.StringVar()
        self.max_pts.set("max_pts")
        tk.Entry(ctrls_f, textvariable=self.max_pts, width=13).grid(row=0, column=6, sticky='w', padx=5)

        # button to add add plot in the specified column
        self.col_var = tk.StringVar()
        self.col_var.set("plot column")
        tk.Entry(ctrls_f, textvariable=self.col_var, width=13).grid(row=0, column=7, sticky='w', padx=5)
        tk.Button(ctrls_f, text="New plot ...", command=self.add_plot)\
            .grid(row=0, column=8, sticky='e', padx=10)

        # the HDF file we're currently plotting from
        tk.Label(ctrls_f, text="HDF file:")\
                .grid(row=1, column=0)
        tk.Entry(ctrls_f,
                textvariable=self.parent.config["files"]["plotting_hdf_fname"])\
                .grid(row=1, column=1, columnspan=5, padx=10, sticky="ew")
        tk.Button(ctrls_f, text="Open...",
                command = lambda: self.open_HDF_file("plotting_hdf_fname"))\
                .grid(row=1, column=6, padx=10, sticky='ew')

        # for saving plot configuration
        tk.Label(ctrls_f, text="Plot config file:")\
                .grid(row=2, column=0)
        tk.Entry(ctrls_f,
                textvariable=self.parent.config["files"]["plotting_config_fname"])\
                .grid(row=2, column=1, columnspan=5, padx=10, sticky="ew")
        tk.Button(ctrls_f, text="Save plots", command = self.save_plots)\
                .grid(row=2, column=6, padx=10, sticky='ew')
        tk.Button(ctrls_f, text="Load plots", command = self.load_plots)\
                .grid(row=2, column=7, padx=10, sticky='ew')

        # add one plot
        self.add_plot()

    def save_plots(self):
        # put essential information about plot configuration in a dictionary
        plot_config = {}
        for col, col_plots in self.all_plots.items():
            plot_config[col] = {}
            for row, plot in col_plots.items():
                if plot:
                    plot_info = {
                            "device" : plot.dev_var.get(),
                            "run"    : plot.run_var.get(),
                            "param"  : plot.param_var.get(),
                            "xcol"   : plot.xcol_var.get(),
                            "x0"     : plot.x0_var.get(),
                            "x1"     : plot.x1_var.get(),
                            "y0"     : plot.y0_var.get(),
                            "y1"     : plot.y1_var.get(),
                            "dt"     : plot.dt_var.get(),
                            "fn"     : plot.fn,
                            "fn_var" : plot.fn_var.get(),
                            "points" : plot.points,
                            "log"    : plot.log,
                            }
                    plot_config[col][row] = plot_info

        # save this info as a pickled dictionary
        with open(self.parent.config["files"]["plotting_config_fname"].get(), "wb") as f:
            pickle.dump(plot_config, f)

    def load_plots(self):
        # remove all plots
        self.delete_all()

        # read pickled plot config
        with open(self.parent.config["files"]["plotting_config_fname"].get(), "rb") as f:
            plot_config = pickle.load(f)

        # re-create all plots
        for col, col_plots in plot_config.items():
            for row, plot_info in col_plots.items():
                plot = self.add_plot(row, col)
                plot.dev_var.set(   plot_info["device"] )
                plot.run_var.set(   plot_info["run"]    )
                plot.refresh_parameter_list(plot_info["device"])
                plot.param_var.set( plot_info["param"]  )
                plot.xcol_var.set(  plot_info["xcol"]   )
                plot.x0_var.set(    plot_info["x0"]     )
                plot.x1_var.set(    plot_info["x1"]     )
                plot.y0_var.set(    plot_info["y0"]     )
                plot.y1_var.set(    plot_info["y1"]     )
                plot.dt_var.set(    plot_info["dt"]     )
                plot.change_animation_dt()
                if plot_info["fn"]:
                    plot.fn_var.set(plot_info["fn_var"])
                    plot.toggle_fn()
                if plot_info["points"]:
                    plot.toggle_points()
                if plot_info["log"]:
                    plot.toggle_log()
                plot.start_animation()

        self.refresh_run_list(self.parent.config["files"]["plotting_hdf_fname"].get())

    def open_HDF_file(self, prop):
        # ask for a file name
        fname = filedialog.askopenfilename(
                initialdir = self.parent.config["files"][prop].get(),
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))

        # check a filename was returned
        if not fname:
            return

        # check it's a valid HDF file
        try:
            with h5py.File(fname, 'r') as f:
                self.parent.config["files"][prop].set(fname)
                self.refresh_run_list(fname)
        except OSError:
            messagebox.showerror("File error", "Not a valid HDF file.")

    def change_all_animation_dt(self, i=0):
        # determine what the plot refresh rate is
        try:
            dt = float(self.dt_var.get())
        except ValueError:
            dt = 1
        if dt < 0.01:
            dt = 0.01

        # set all plots to that refresh rate
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.change_animation_dt(0, dt)

    def refresh_run_list(self, fname):
        # get list of runs
        with h5py.File(fname, 'r') as f:
            self.run_list = list(f.keys())

        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    # update the OptionMenu
                    menu = plot.run_select["menu"]
                    menu.delete(0, "end")
                    for p in self.run_list:
                        menu.add_command(label=p, command=lambda val=p: plot.run_var.set(val))

                    # select the last run by default
                    plot.run_var.set(self.run_list[-1])

    def delete_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.destroy()
        self.all_plots = {}

    def start_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.start_animation()

    def stop_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.stop_animation()

    def refresh_all_parameter_lists(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.refresh_parameter_list(plot.dev_var.get())

    def add_plot(self, row=False, col=False):
        # find location for the plot if not given to the function
        if (not row) and (not col):
            try:
                col = int(self.col_var.get())
            except ValueError:
                col = 0
            row = max([ r for r in self.all_plots.setdefault(col, {0:None}) ]) + 2

        # frame for the plot
        fr = tk.LabelFrame(self.f, text="")
        fr.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        # place the plot
        plot = Plotter(fr, self.parent)
        self.all_plots.setdefault(col, {0:None}) # check the column is in the dict, else add it
        self.all_plots[col][row] = plot

        # button to delete plot
        del_b = tk.Button(plot.f, text="\u274c", command=lambda plot=plot,
                row=row, col=col: self.delete_plot(row,col,plot))
        del_b.grid(row=0, column=8, sticky='e', padx=10)

        # update list of runs if a file was supplied
        fname = self.parent.config["files"]["plotting_hdf_fname"].get()
        try:
            with h5py.File(fname, 'r') as f:
                self.run_list = list(f.keys())
                menu = plot.run_select["menu"]
                menu.delete(0, "end")
                for p in self.run_list:
                    menu.add_command(label=p, command=lambda val=p: plot.run_var.set(val))
                plot.run_var.set(self.run_list[-1])
        except OSError:
            pass

        return plot

    def delete_plot(self, row, col, plot):
        if plot:
            plot.destroy()
        self.all_plots[col].pop(row, None)

class Plotter(tk.Frame):
    def __init__(self, frame, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.f = frame
        self.parent = parent
        self.log = False
        self.points = False
        self.plot_drawn = False
        self.record_number = tk.StringVar()
        self.animation_running = False

        # select device
        self.dev_list = [dev_name.strip() for dev_name in self.parent.devices]
        if not self.dev_list:
            self.dev_list = ["(no devices)"]
        self.dev_var = tk.StringVar()
        self.dev_var.set(self.dev_list[0])
        dev_select = tk.OptionMenu(self.f, self.dev_var, *self.dev_list,
                command=self.refresh_parameter_list)
        dev_select.grid(row=0, column=0, columnspan=1, sticky='ew')
        dev_select.configure(width=22)

        # select run
        self.run_list = [""]
        self.run_var = tk.StringVar()
        self.run_var.set("Select run ...")
        self.run_select = tk.OptionMenu(self.f, self.run_var, *self.run_list)
        self.run_select.grid(row=0, column=1, columnspan=1, sticky='ew')
        self.run_select.configure(width=18)

        # select parameter
        self.param_list = ["(select device first)"]
        self.param_var = tk.StringVar()
        self.param_var.set("y ...")
        self.param_select = tk.OptionMenu(self.f, self.param_var, *self.param_list)
        self.param_select.grid(row=1, column=1, columnspan=1, sticky='ew')
        self.param_select.configure(width=18)

        # select xcol
        self.xcol_list = ["(select device first)"]
        self.xcol_var = tk.StringVar()
        self.xcol_var.set("x ...")
        self.xcol_select = tk.OptionMenu(self.f, self.xcol_var, *self.xcol_list)
        self.xcol_select.grid(row=1, column=0, columnspan=1, sticky='ew')
        self.xcol_select.configure(width=18)

        self.refresh_parameter_list(self.dev_var.get())

        # plot range controls
        num_width = 7 # width of numeric entry boxes
        self.x0_var = tk.StringVar()
        self.x0_var.set("x0")
        tk.Entry(self.f, textvariable=self.x0_var, width=num_width)\
                .grid(row=1, column=2, columnspan=2, sticky='w', padx=1)
        self.x1_var = tk.StringVar()
        self.x1_var.set("x1")
        tk.Entry(self.f, textvariable=self.x1_var, width=num_width)\
                .grid(row=1, column=4, sticky='w', padx=1)
        self.y0_var = tk.StringVar()
        self.y0_var.set("y0")
        tk.Entry(self.f, textvariable=self.y0_var, width=num_width)\
                .grid(row=1, column=5, sticky='w', padx=1)
        self.y1_var = tk.StringVar()
        self.y1_var.set("y1")
        tk.Entry(self.f, textvariable=self.y1_var, width=num_width)\
                .grid(row=1, column=6, sticky='w', padx=1)

        # control buttons
        self.dt_var = tk.StringVar()
        self.dt_var.set("dt")
        dt_entry = tk.Entry(self.f, textvariable=self.dt_var, width=num_width)
        dt_entry.grid(row=1, column=7, columnspan=1)
        dt_entry.bind("<Return>", self.change_animation_dt)
        self.play_pause_button = tk.Button(self.f, text="\u25b6", command=self.start_animation)
        self.play_pause_button.grid(row=0, column=5, padx=2)
        tk.Button(self.f, text="Log/Lin", command=self.toggle_log)\
                .grid(row=0, column=6, padx=2)
        tk.Button(self.f, text="\u26ab / \u2014", command=self.toggle_points)\
                .grid(row=0, column=7, padx=2)

        # for displaying a function of the data
        self.fn = False
        self.fn_var = tk.StringVar()
        self.fn_var.set("np.sum(y, dtype=np.int32)")
        self.x = []
        self.y = []
        tk.Button(self.f, text="f(y)", command=self.toggle_fn).grid(row=0, column=3, padx=0)
        self.fn_entry = tk.Entry(self.f, textvariable=self.fn_var)
        self.fn_clear_button = tk.Button(self.f, text="Clear", command=self.clear_fn)

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        if self.fn:
            self.x, self.y = [], []

    def toggle_fn(self):
        """Toggle controls for applying a custom function to the data."""
        # start animation and (if not yet drawn) draw plot
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
        else:
            self.start_animation()

        # toggle the fn flag
        self.fn = not self.fn

        # display/hide function controls
        if self.fn:
            self.fn_entry.grid(row=3, column=0, columnspan=6, sticky='nsew', padx=10, pady=10)
            self.fn_clear_button.grid(row=3, column=7, sticky='nsew', padx=10, pady=10)
        else:
            self.fn_entry.grid_remove()
            self.fn_clear_button.grid_remove()

    # whether to draw with just lines or also with points
    def toggle_points(self):
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)

        self.points = False if self.points==True else True

        # change marker style
        if self.points:
            self.line.set_marker('.')
        else:
            self.line.set_marker(None)

        # update plot
        self.canvas.draw()

    def toggle_log(self):
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)

        self.log = False if self.log==True else True

        # change log/lin
        if self.log:
            self.ax.set_yscale('log')
        else:
            self.ax.set_yscale('linear')

        # update plot
        self.canvas.draw()

    def start_animation(self):
        if not self.plot_drawn:
            if self.new_plot():
                self.ani.event_source.start()
        else:
            self.ani.event_source.start()
        self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
        self.animation_running = True

    def stop_animation(self):
        if self.plot_drawn:
            self.ani.event_source.stop()
        self.animation_running = False
        self.play_pause_button.configure(text="\u25b6", command=self.start_animation)

    def change_animation_dt(self, i=0, dt=-1):
        if self.plot_drawn:
            if dt > 0.1:
                self.ani.event_source.interval = 1000 * dt
            else:
                self.ani.event_source.interval = 1000 * self.dt()

    def destroy(self):
        self.f.destroy()

    def refresh_parameter_list(self, dev_name):
        self.dev_var.set(dev_name)

        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            return None

        # update the parameter list
        self.param_list = dev.config["attributes"]["column_names"].split(',')
        self.param_list = [x.strip() for x in self.param_list]
        menu = self.param_select["menu"]
        menu.delete(0, "end")
        for p in self.param_list:
            menu.add_command(label=p, command=lambda val=p: self.param_var.set(val))

        # update xcol list
        if "time" in self.param_list:
            self.xcol_list = self.param_list.copy()
        else:
            self.xcol_list = ["None"]+self.param_list.copy()
        menu = self.xcol_select["menu"]
        menu.delete(0, "end")
        for p in self.xcol_list:
            menu.add_command(label=p, command=lambda val=p: self.xcol_var.set(val))

    def get_data(self):
        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            self.stop_animation()
            messagebox.showerror("Device error", "Error: invalid device.")
            return None

        # check parameter is valid
        if ((self.param_var.get() in self.param_list) and (self.xcol_var.get() in self.xcol_list)) or \
           ((self.param_var.get() in self.param_list) and (self.xcol_var.get() == "None")):
            yparam = self.param_var.get()
            yunit = dev.config["attributes"]["units"].split(',')[self.param_list.index(yparam)]
            xparam = self.xcol_var.get()
            if xparam == "None":
                xunit = ""
                xparam = ""
            else:
                xunit = dev.config["attributes"]["units"].split(',')[self.xcol_list.index(xparam)]
        elif len(self.param_list) == 0:
            self.stop_animation()
            messagebox.showerror("Parameter error", "Error: device has no parameters.")
            return None
        else:
            # set a default parameter
            if len(self.param_list) >= 2:
                if "time" in self.param_list:
                    self.param_var.set(self.param_list[1])
                else:
                    self.param_var.set(self.param_list[0])
                self.xcol_var.set(self.xcol_list[0])
            else:
                self.param_var.set(self.param_list[0])
                self.xcol_var.set("None")
            # check the newly set parameter is valid
            if ((self.param_var.get() in self.param_list) and (self.xcol_var.get() in self.xcol_list)) or \
               ((self.param_var.get() in self.param_list) and (self.xcol_var.get() == "None")):
                yparam = self.param_var.get()
                yunit = dev.config["attributes"]["units"].split(',')[self.param_list.index(yparam)]
                xparam = self.xcol_var.get()
                if xparam == "None":
                    xunit = ""
                    xparam = ""
                else:
                    xunit = dev.config["attributes"]["units"].split(',')[self.xcol_list.index(xparam)]
            else:
                self.stop_animation()
                messagebox.showerror("Parameter error", "Error: invalid parameter.")
                return None

        # check run is valid
        try:
            with h5py.File(self.parent.config["files"]["plotting_hdf_fname"].get(), 'r') as f:
                if not self.run_var.get() in f.keys():
                    self.stop_animation()
                    messagebox.showerror("Run error", "Run not found in the HDF file.")
                    return None
        except OSError:
                self.stop_animation()
                messagebox.showerror("File error", "Not a valid HDF file.")
                return NonFalse

        # check dataset exists in the run
        with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
            try:
                grp = f[self.run_var.get() + "/" + dev.config["path"]]
            except KeyError:
                if time.time() - self.parent.config["time_offset"] > 5:
                    messagebox.showerror("Data error", "Dataset not found in this run.")
                self.stop_animation()
                return None

        # get data
        with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
            grp = f[self.run_var.get() + "/" + dev.config["path"]]

            # make sure there is enough data collected to plot it
            if not dev.config["single_dataset"]:
                if len(grp) < 2:
                    self.stop_animation()
                    return None

            # if displaying a function of the data (e.g., integrated data)
            if self.fn:
                # when each acquisition is its own dataset, evaluate a
                # scalar-valued function of the latest dataset (e.g. integral of
                # entire trace plotted vs trace index)
                if not dev.config["single_dataset"]:
                    rec_num = len(grp) - 1
                    dset = grp[dev.config["name"] + "_" + str(rec_num)]
                    trace_y = dset[:, self.param_list.index(yparam)]
                    # if the most recent value hasn't been calculated yet, calculate it
                    if len(self.x) == 0 or self.x[-1] != rec_num:
                        y_fn = self.evaluate_fn(trace_y)
                        if y_fn:
                            self.x.append(rec_num)
                            self.y.append(y_fn)
                    # make sure the x, y arrays have correct shape
                    try:
                        x, y = np.array(self.x), np.array(self.y)
                    except ValueError: # else just return the trace
                        rec_num = len(grp) - 1
                        self.record_number.set(rec_num)
                        dset = grp[dev.config["name"] + "_" + str(rec_num)]
                        x = np.arange(dset.shape[0])
                        y = dset[:, self.param_list.index(yparam)]

                # when all acquisitions are in one dataset, evaluate a
                # function of individual datapoints (e.g. sqrt of the entire trace)
                else:
                    dset = grp[dev.config["name"]]
                    if self.xcol_var.get() == "None":
                        xunit = dset.attrs["sampling"].split("[")[0]
                        continuous_sampling = True
                        x = np.arange(dset.shape[0])*1/int(xunit)
                        xunit = "s"
                    else:
                        x = dset[:, self.param_list.index(self.xcol_var.get())]
                    y = self.evaluate_fn(dset[:, self.param_list.index(yparam)])

                    # check y has correct shape
                    try:
                        if isinstance(y, type(None)):
                            raise ValueError("NoneType returned")
                        elif x.shape != y.shape:
                            raise ValueError("x.shape != y.shape")
                    except ValueError as err:
                        logging.warning("Function returns invalid data: " + str(err))
                        if self.xcol_var.get() == "None":
                            xunit = dset.attrs["sampling"].split("[")[0]
                            continuous_sampling = True
                            x = np.arange(dset.shape[0])*1/int(xunit)
                            xunit = "s"
                        else:
                            x = dset[:, self.param_list.index(self.xcol_var.get())]
                        y = dset[:, self.param_list.index(yparam)]

            # if displaying data as recorded (not evaluating a function of the data)
            else:
                if dev.config["single_dataset"]:
                    try:
                        dset = grp[dev.config["name"]]
                    except KeyError as err:
                        messagebox.showerror("Data error", "Dataset not found in this run.")
                        return None
                    if self.xcol_var.get() == "None":
                        try:
                            xunit = dset.attrs["sampling"].split("[")[0]
                        except KeyError:
                            xunit = 1
                        continuous_sampling = True
                        x = np.arange(dset.shape[0])*1/int(xunit)
                        xunit = "s"
                    else:
                        x = dset[:, self.param_list.index(self.xcol_var.get())]
                    y = dset[:, self.param_list.index(yparam)]
                else: # if each acquisition is its own dataset, return latest run only
                    rec_num = len(grp) - 1
                    self.record_number.set(rec_num)
                    dset = grp[dev.config["name"] + "_" + str(rec_num)]
                    x = np.arange(dset.shape[0])
                    y = dset[:, self.param_list.index(yparam)]

            # range of data to obtain
            try:
                i1, i2 = int(float(self.x0_var.get())), int(float(self.x1_var.get()))
            except ValueError as err:
                i1, i2 = 0, -1
            if i1 >= i2:
                if i2 >= 0:
                    i1, i2 = 0, -1
            if i2 >= dset.shape[0] - 1:
                i1, i2 = 0, -1

            # don't return more than about max_pts points
            try:
                max_pts = int(self.parent.plots.max_pts.get())
            except ValueError:
                max_pts = 10000
            dset_len = len(x)
            slice_length = (i2 if i2>=0 else dset_len+i2) - (i1 if i1>=0 else dset_len+i1)
            stride = 1 if slice_length < max_pts else int(slice_length/max_pts)
            return x[i1:i2:stride], y[i1:i2:stride], xparam, yparam, xunit, yunit

    def evaluate_fn(self, data):
        fn_var = self.fn_var.get()

        # make sure the function is not empty
        if len(fn_var) == 0:
            return None

        # make sure the function contains x (the argument of function)
        if not "y" in fn_var:
            return None

        # find the requested function
        try:
            fn = lambda y : eval(fn_var)
        except (TypeError, AttributeError) as err:
            logging.warning("Cannot evaluate function: " + str(err))
            return None

        # apply the function to the data
        try:
            ret_val = fn(data)
        except (SyntaxError, AttributeError, NameError, TypeError) as err:
            logging.warning("Cannot evaluate function: " + str(err))
            return None

        return ret_val

    def new_plot(self):
        data = self.get_data()

        if data:
            x, y, xparam, yparam, xunit, yunit = data
        else:
            return False

        if self.plot_drawn:
            return False

        # draw plot
        self.fig = Figure(figsize=(6.2,2.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot(x, y)

        # labels
        if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
            self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
        else:
            self.ax.set_xlabel("sample number")
        self.ax.set_ylabel(yparam + " [" + yunit.strip() + "]")

        # plot layout
        self.fig.set_tight_layout(True)
        self.ax.grid()
        self.ax.ticklabel_format(axis='y', scilimits=(-3,3))

        # update drawing
        self.canvas = FigureCanvasTkAgg(self.fig, self.f)
        self.canvas.get_tk_widget().grid(row=4, columnspan=9)
        self.ani = animation.FuncAnimation(self.fig, self.replot,
                interval=1000*self.dt(), blit=True)
        self.ani.event_source.stop()

        ## place the plot navigation toolbar
        #t_f = tk.Frame(self.f)
        #t_f.grid(row=3, columnspan=5)
        #toolbar = NavigationToolbar2Tk(self.canvas, t_f)
        #toolbar.update()
        self.canvas._tkcanvas.grid()

        self.plot_drawn = True
        return True

    def dt(self):
        try:
            dt = float(self.dt_var.get())
        except ValueError:
            dt = 1
        if dt < 0.01:
            dt = 0.01
        return dt

    def replot(self, i=0):
        if not self.plot_drawn:
            self.new_plot()
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
            return

        data = self.get_data()

        if data:
            # update plot data
            x, y, xparam, yparam, xunit, yunit = data
            self.line.set_data(x, y)

            # update x limits
            try:
                x0, x1 = np.nanmin(x), np.nanmax(x)
                if x0 >= x1:
                    raise ValueError
            except ValueError:
                x0, x1 = 0, 1
            self.ax.set_xlim((x0, x1))

            # update y limits
            try:
                y0, y1 = float(self.y0_var.get()), float(self.y1_var.get())
                if y0 >= y1:
                    raise ValueError
            except ValueError as err:
                try:
                    y0, y1 = np.nanmin(y), np.nanmax(y)
                    if y0 == y1:
                        y0, y1 = y0 - 1, y0 + 1
                except ValueError:
                    y0, y1 = 0, 10
            try:
                self.ax.set_ylim((y0, y1))
            except ValueError as err:
                logging.warning("Cannot set ylim: " + str(err))

            # update plot labels
            if self.fn:
                self.ax.set_title(self.fn_var.get())
                if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
                    self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
                else:
                    self.ax.set_xlabel("dset number")
            else:
                if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
                    self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
                    self.ax.set_title("")
                else:
                    self.ax.set_xlabel("sample number")
                    self.ax.set_title("record #"+str(self.record_number.get()))
            self.ax.set_ylabel(yparam + " [" + yunit.strip() + "]")

            # redraw plot
            self.canvas.draw()

        return self.line,

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
