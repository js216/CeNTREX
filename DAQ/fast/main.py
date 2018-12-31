import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
import glob
import threading
import h5py
import csv
import shutil, errno
import re
import numpy as np
import time
import sys
import pyvisa
import os
import configparser
from decimal import Decimal
import queue
from collections import deque

from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110
from drivers import USB6008
from drivers import PXIe5171

from Plotting import PlotsGUI
from Monitoring import MonitoringGUI

class HDF_writer(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # configuration parameters
        self.filename = self.parent.config["hdf_fname"].get()
        self.parent.run_name = str(int(time.time())) + " " + self.parent.config["run_name"].get()

        # create/open HDF file, groups, and datasets
        with h5py.File(self.filename, 'a') as f:
            root = f.create_group(self.parent.run_name)
            root.attrs["time_offset"] = self.parent.config["time_offset"]
            for dev_name, dev in self.parent.devices.items():
                if dev.config["controls"]["enabled"]["var"].get():
                    grp = root.require_group(dev.config["path"])

                    # create dataset for data
                    dset = grp.create_dataset(dev.config["name"], (0,dev.shape[0]+1),
                            maxshape=(None,dev.shape[0]+1), dtype='f')
                    for attr_name, attr in dev.config["attributes"].items():
                        dset.attrs[attr_name] = attr

                    # create dataset for events
                    events_dset = grp.create_dataset(dev.config["name"]+"_events", (0,3),
                            maxshape=(None,3), dtype=h5py.special_dtype(vlen=str))

        self.active.set()

    def run(self):
        while self.active.is_set():
            with h5py.File(self.filename, 'a') as f:
                root = f.require_group(self.parent.run_name)
                for dev_name, dev in self.parent.devices.items():
                    if dev.config["controls"]["enabled"]["var"].get():
                        # get data and write to HDF
                        data = self.get_data(dev.data_queue)
                        if len(data) != 0:
                            grp = root.require_group(dev.config["path"])
                            dset = grp[dev.config["name"]]
                            dset.resize(dset.shape[0]+len(data), axis=0)
                            dset[-len(data):,:] = data

                        # get events and write them to HDF
                        events = self.get_data(dev.events_queue)
                        if len(events) != 0:
                            grp = root.require_group(dev.config["path"])
                            events_dset = grp[dev.config["name"] + "_events"]
                            events_dset.resize(events_dset.shape[0]+len(events), axis=0)
                            events_dset[-len(events):,:] = events
                            print(events)
                            sys.stdout.flush()

                # loop delay
                try:
                    time.sleep(float(self.parent.config["hdf_loop_delay"].get()))
                except ValueError:
                    time.sleep(0.1)

    def get_data(self, fifo):
        data = []
        while True:
            try:
                data.append( fifo.get_nowait() )
            except queue.Empty:
                break
        return data

class Device(threading.Thread):
    def __init__(self, config):
        self.config = config

        # whether the thread is running
        self.active = threading.Event()
        self.active.clear()

        # whether the connection to the device was successful
        self.operational = False

        # for sending commands to the device
        self.commands = []

        # the data and events queues
        self.data_queue = queue.Queue()
        self.events_queue = queue.Queue()

        # the variable for counting the number of NaN returns
        self.nan_count = tk.StringVar()
        self.nan_count.set(0)

        # variable for displaying the last event in MonitoringGUI
        self.last_event = tk.StringVar()

    def setup_connection(self, time_offset):
        threading.Thread.__init__(self)
        self.rm = pyvisa.ResourceManager()
        self.time_offset = time_offset

        # verify the device responds correctly
        constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]
        with self.config["driver"](self.rm, *constr_params) as dev: 
            self.shape = dev.shape
            if dev.verification_string == self.config["correct_response"]:
                self.operational = True
            else:
                self.operational = False

        self.rm.close() 

    def clear_queues(self):
        # empty the data queue
        while not self.data_queue.empty():
            try:
                self.data_queue.get(False)
            except queue.Empty:
                break

        # empty the data queue
        while not self.events_queue.empty():
            try:
                self.events_queue.get(False)
            except queue.Empty:
                break

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return
        else:
            self.active.set()

        # main control loop
        constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]
        self.rm = pyvisa.ResourceManager()
        with self.config["driver"](self.rm, *constr_params) as device: 
            while self.active.is_set():
                # loop delay
                try:
                    time.sleep(float(self.config["controls"]["dt"]["var"].get()))
                except ValueError:
                    time.sleep(1)

                # check device is enabled
                if not self.config["controls"]["enabled"]["var"].get():
                    continue

                # record numerical values
                last_data = [time.time() - self.time_offset] + device.ReadValue()
                self.data_queue.put(last_data)

                # keep track of the number of NaN returns
                if np.isnan(last_data[1]):
                    self.nan_count.set( int(self.nan_count.get()) + 1)

                # send control commands, if any, to the device, and record return values
                for c in self.commands:
                    try:
                        ret_val = eval("device." + c)
                    except (ValueError, AttributeError) as err:
                        ret_val = str(err)
                    ret_val = "None" if not ret_val else ret_val
                    last_event = [ time.time()-self.time_offset, c, ret_val ]
                    self.last_event.set(last_event)
                    self.events_queue.put(last_event)
                self.commands = []

class ControlGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.read_device_config()
        self.place_GUI_elements()

    def read_device_config(self):
        self.parent.devices = {}

        if not os.path.isdir(self.parent.config["config_dir"].get()):
            return

        for f in glob.glob(self.parent.config["config_dir"].get() + "/*.ini"):
            params = configparser.ConfigParser()
            params.read(f)

            if not "device" in params:
                continue

            # read general device options
            dev_config = {
                        "name"              : params["device"]["name"],
                        "label"             : params["device"]["label"],
                        "config_fname"      : f,
                        "path"              : params["device"]["path"],
                        "correct_response"  : params["device"]["correct_response"],
                        "row"               : params["device"]["row"],
                        "column"            : params["device"]["column"],
                        "driver"            : eval(params["device"]["driver"]),
                        "constr_params"     : [x.strip() for x in params["device"]["constr_params"].split(",")],
                        "attributes"        : params["attributes"],
                        "controls"          : {},
                    }

            # populate the list of device controls
            ctrls = dev_config["controls"]
            for c in params.sections():
                if params[c].get("type") == "Checkbutton":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
                    ctrls[c]["var"]        = tk.BooleanVar()
                    ctrls[c]["var"].set(params[c]["value"])
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
                    ctrls[c]["options"]    = params[c]["options"].split(",")
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
                    ctrls[c]["columnspan"]    = int(params[c]["columnspan"])
                    ctrls[c]["column_names"]  = [x.strip() for x in params[c]["column_names"].split(",")]
                    ctrls[c]["column_labels"] = [x.strip() for x in params[c]["column_labels"].split(",")]
                    ctrls[c]["column_types"]  = [x.strip() for x in params[c]["column_types"].split(",")]
                    ctrls[c]["column_widths"] = params[c].get("column_widths")
                    if ctrls[c]["column_widths"]:
                        ctrls[c]["column_widths"] = [int(x) for x in ctrls[c]["column_widths"].split(",")]
                    ctrls[c]["column_options"] = []
                    for c_v in params[c].get("column_options").split(";"):
                        ctrls[c]["column_options"].append([x.strip() for x in c_v.split(",")])
                    ctrls[c]["column_values"] = []
                    for c_v in params[c].get("column_values").split(";"):
                        ctrls[c]["column_values"].append([])
                        for val in c_v.split(","):
                            ctrls[c]["column_values"][-1].append(tk.StringVar())
                            ctrls[c]["column_values"][-1][-1].set(val.strip())

            # make a Device object
            self.parent.devices[params["device"]["name"]] = Device(dev_config)

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
                textvariable=self.parent.config["config_dir"])\
                .grid(row=0, column=1, sticky="ew")
        tk.Button(files_frame, text="Open...",
                command = self.set_config_dir)\
                .grid(row=0, column=2, sticky=tk.W)

        # HDF file
        tk.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tk.E)
        tk.Entry(files_frame, width=64,
                textvariable=self.parent.config["hdf_fname"])\
                .grid(row=1, column=1, sticky="ew")
        tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=1, column=2, sticky=tk.W)

        # HDF writer loop delay
        tk.Label(files_frame, text="HDF writer loop delay:")\
                .grid(row=2, column=0, sticky=tk.E)
        tk.Entry(files_frame,
                textvariable=self.parent.config["hdf_loop_delay"])\
                .grid(row=2, column=1, sticky="nsew")

        # run name
        tk.Label(files_frame, text="Run name:")\
                .grid(row=3, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame,
                textvariable=self.parent.config["run_name"])\
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
                    row=dev.config["row"], column=dev.config["column"])

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
                        command = lambda dev=dev, cmd=c["enter_cmd"], arg=c["var"]:\
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
                    for i, name in enumerate(c["control_names"]):
                        c["ctrls"] = {}
                        if c["control_types"][i] == "Entry":
                            c["ctrls"][name] = tk.Entry(c["Frame"],
                                    width=c["control_widths"][i], textvariable=c["control_values"][name])
                        elif c["control_types"][i] == "OptionMenu":
                            c["ctrls"][name] = tk.OptionMenu(c["Frame"],
                                    c["control_values"][name], *c["control_options"][i])
                        c["ctrls"][name].grid(row=1, column=i+1, sticky="nsew", padx=5)
                        tk.Label(c["Frame"], text=c["control_labels"][i])\
                                .grid(row=0, column=i+1)

                # place ControlsTables
                elif c["type"] == "ControlsTable":
                    tk.Label(fd, text=c["label"]).grid(row=c["row"], column=c["col"]-1, sticky="ne")
                    c["Frame"] = tk.LabelFrame(fd)
                    c["Frame"].grid(row=c["row"], column=c["col"],
                            columnspan=c["columnspan"], sticky='w', pady=10, padx=3)
                    for i, name in enumerate(c["column_names"]):
                        tk.Label(c["Frame"], text=c["column_labels"][i]).grid(row=0, column=i)
                        for j, var in enumerate(c["column_values"][i]):
                            if c["column_types"][i] == "Checkbutton":
                                tk.Checkbutton(c["Frame"], variable=var).grid(row=j+1, column=i)
                            elif c["column_types"][i] == "Entry":
                                tk.Entry(c["Frame"], textvariable=var,
                                        width=c["column_widths"][i]).grid(row=j+1, column=i)
                            elif c["column_types"][i] == "Label":
                                tk.Label(c["Frame"], textvariable=var).grid(row=j+1, column=i)
                            elif c["column_types"][i] == "OptionMenu":
                                om = tk.OptionMenu(c["Frame"], var, *c["column_options"][i])
                                om.config(width=c["column_widths"][i])
                                om.grid(row=j+1, column=i)

    def set_config_dir(self):
        self.open_dir("config_dir")
        self.read_device_config()
        self.fr.destroy()
        self.place_device_controls()

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
                initialdir = self.parent.config[prop].get(),
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))
        if not fname:
            return
        else:
            self.parent.config[prop].set(fname)

    def open_dir(self, prop):
        fname = filedialog.askdirectory(
                initialdir = self.parent.config[prop].get(),
                title = "Select directory")
        if not fname:
            return
        else:
            self.parent.config[prop].set(fname)

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
                            "Error: " + dev.config["label"] + " not responding\
                            correctly, or cannot access the directory for data storage.")
                    self.status_message.set("Device configuration error")
                    return

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent)
        self.HDF_writer.start()

        # start the monitoring thread
        self.parent.monitoring.start_monitoring()

        # start control for all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.clear_queues()
                dev.start()

        # update program status
        self.status = "running"
        self.status_message.set("Running")

        # make all plots display the current run and file
        HDF_fname = self.parent.config["hdf_fname"].get()
        self.parent.plots.refresh_run_list(HDF_fname)
        self.parent.config["plotting_hdf_fname"].set(HDF_fname)

    def stop_control(self):
        # check we're not stopped already
        if self.status == "stopped":
            return

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()

        # stop monitoring
        self.parent.monitoring.stop_monitoring()

        # stop devices, waiting for threads to finish
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                dev.active.clear()

        self.status = "stopped"
        self.status_message.set("Recording finished")

class CentrexGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.winfo_toplevel().title("CENTREX Slow DAQ")
        self.parent = parent
        self.read_config()

        # GUI elements in a tabbed interface
        self.nb = ttk.Notebook(self)
        self.nb.grid()
        self.control    = ControlGUI(self, *args, **kwargs)
        self.monitoring = MonitoringGUI(self, *args, **kwargs)
        self.plots      = PlotsGUI(self, *args, **kwargs)

    def read_config(self):
        # read program settings
        self.config = {}
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for key in settings["files"]:
            self.config[key] = tk.StringVar()
            self.config[key].set(settings["files"][key])

if __name__ == "__main__":
    root = tk.Tk()
    CentrexGUI(root).grid()
    root.mainloop()
