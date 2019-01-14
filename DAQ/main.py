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
import importlib

from Plotting import PlotsGUI
from Monitoring import MonitoringGUI
from HDF_control import HDF_writer

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

        # for warnings about device abnormal condiotion
        self.warnings = []

        # the data and events queues
        self.data_queue = deque()
        self.events_queue = deque()

        # the variable for counting the number of NaN returns
        self.nan_count = tk.StringVar()
        self.nan_count.set(0)

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
            if dev.verification_string.strip() == self.config["correct_response"].strip():
                self.operational = True
            else:
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
                if  len(last_data) > 0:
                    self.data_queue.append(last_data)

                # keep track of the number of NaN returns
                if isinstance(last_data, float):
                    if np.isnan(last_data):
                        self.nan_count.set( int(self.nan_count.get()) + 1)

                # send control commands, if any, to the device, and record return values
                for c in self.commands:
                    try:
                        ret_val = eval("device." + c.strip())
                    except (ValueError, AttributeError) as err:
                        ret_val = str(err)
                    ret_val = "None" if not ret_val else ret_val
                    last_event = [ time.time()-self.time_offset, c, ret_val ]
                    self.events_queue.append(last_event)
                self.commands = []

class ControlGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.read_device_config()
        self.place_GUI_elements()

    def read_device_config(self):
        self.parent.devices = {}

        if not os.path.isdir(self.parent.config["files"]["config_dir"].get()):
            return

        for f in glob.glob(self.parent.config["files"]["config_dir"].get() + "/*.ini"):
            params = configparser.ConfigParser()
            params.read(f)

            if not "device" in params:
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
            dev_config = {
                        "name"              : params["device"]["name"],
                        "label"             : params["device"]["label"],
                        "config_fname"      : f,
                        "path"              : params["device"]["path"],
                        "correct_response"  : params["device"]["correct_response"],
                        "single_dataset"    : True if params["device"]["single_dataset"]=="True" else False,
                        "row"               : params["device"]["row"],
                        "rowspan"           : params["device"]["rowspan"],
                        "monitoring_row"    : params["device"]["monitoring_row"],
                        "column"            : params["device"]["column"],
                        "columnspan"        : params["device"]["columnspan"],
                        "monitoring_column" : params["device"]["monitoring_column"],
                        "driver"            : driver,
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

class CentrexGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.winfo_toplevel().title("CENTREX Slow DAQ")
        self.parent = parent

        # read program configuration
        self.config = {"time_offset":0}
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for config_group, configs in settings.items():
            self.config[config_group] = {}
            for key, val in configs.items():
                self.config[config_group][key] = tk.StringVar()
                self.config[config_group][key].set(val)

        # GUI elements in a tabbed interface
        self.nb = ttk.Notebook(self)
        self.nb.grid()
        self.control    = ControlGUI(self, *args, **kwargs)
        self.monitoring = MonitoringGUI(self, *args, **kwargs)
        self.plots      = PlotsGUI(self, *args, **kwargs)

    def on_closing(self):
        if self.control.status == "running":
            if messagebox.askokcancel("Confirm quit", "Control running. Do you really want to quit?"):
                self.control.stop_control()
                root.destroy()
        else:
                root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    mainapp = CentrexGUI(root)
    mainapp.grid()
    root.protocol("WM_DELETE_WINDOW", mainapp.on_closing)
    root.mainloop()
