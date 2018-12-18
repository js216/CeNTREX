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

from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110
from drivers import USB6008

from Plotting import PlotsGUI

class HDF_writer(threading.Thread):
    # TODO: events
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
                    grp.create_dataset(dev.config["name"], (0,dev.shape[0]+1),
                            maxshape=(None,dev.shape[0]+1), dtype='f')

        self.active.set()

    def run(self):
        with h5py.File(self.filename, 'a') as f:
            root = f.require_group(self.parent.run_name)
            while self.active.is_set():
                for dev_name, dev in self.parent.devices.items():
                    if dev.config["controls"]["enabled"]["var"].get():
                        # get data
                        data = self.get_data(dev.data)
                        if len(data) == 0:
                            continue

                        # write to HDF
                        grp = root.require_group(dev.config["path"])
                        dset = grp[dev.config["name"]]
                        dset.resize(dset.shape[0]+len(data), axis=0)
                        dset[-len(data):,:] = data

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
        self.data = queue.Queue()
        self.events = queue.Queue()

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
                self.data.put(last_data)

                # send control commands, if any, to the device, and record return values
                for c in self.commands:
                    try:
                        ret_val = eval("device." + c)
                    except (ValueError, AttributeError) as err:
                        ret_val = str(err)
                    ret_val = "None" if not ret_val else ret_val
                    last_event = [ time.time()-self.time_offset, c, ret_val ]
                    self.events.put(last_event)
                self.commands = []

class ControlGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all ControlGUI elements
        cgf = tk.Frame(self.parent.nb)
        self.parent.nb.add(cgf, text="Control")
        self.parent.rowconfigure(0, weight=1)
        cgf.rowconfigure(2, weight=1)

        ########################################
        # control and status
        ########################################

        control_frame = tk.LabelFrame(cgf)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")
        control_frame.grid_columnconfigure(index=2, weight=1)

        # control start/stop buttons
        control_button = tk.Button(control_frame,
                text="\u26ab Start control", command = self.start_control)\
                .grid(row=0, column=0, sticky="nsew")
        stop_button = tk.Button(control_frame,
                text="\u2b1b Stop control", command = self.stop_control)\
                .grid(row=0, column=1, sticky="nsew")

        # button to refresh the list of COM ports
        tk.Button(control_frame, text="Refresh COM ports", command=self.refresh_COM_ports)\
                        .grid(row=1, column=0, sticky='nsew')

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

        files_frame = tk.LabelFrame(cgf, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky="ew")

        tk.Label(files_frame, text="HDF file:")\
                .grid(row=0, column=0, sticky=tk.E)
        tk.Entry(files_frame,
                textvariable=self.parent.config["hdf_fname"])\
                .grid(row=0, column=1, sticky="nsew")
        tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=0, column=2, sticky=tk.W)

        # HDF writer loop delay
        tk.Label(files_frame, text="HDF writer loop delay:")\
                .grid(row=1, column=0, sticky=tk.E)
        tk.Entry(files_frame,
                textvariable=self.parent.config["hdf_loop_delay"])\
                .grid(row=1, column=1, sticky="nsew")

        tk.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame,
                textvariable=self.parent.config["run_name"])\
                .grid(row=2, column=1, sticky="nsew")

        ########################################
        # devices
        ########################################

        fr = tk.LabelFrame(cgf, text="Devices")
        fr.grid(row=2, padx=10, pady=10, sticky='nsew')

        # the control to send a custom command to a specified device
        fc = tk.LabelFrame(fr, text="Send a custom command", padx=10, pady=10)
        fc.grid(row=0, padx=10, pady=10, columnspan=2)
        custom_command = tk.StringVar(fc, value='Enter command ...')
        cmd_entry = tk.Entry(fc, textvariable=custom_command, width=30)
        cmd_entry.grid(row=0, column=0, sticky='nsew')
        custom_dev = tk.StringVar(fc, value='Select device ...')
        dev_list = [dev_name for dev_name in self.parent.devices]
        dev_selection = tk.OptionMenu(fc, custom_dev, *dev_list)
        dev_selection.grid(row=0, column=1, sticky="e")
        custom_button = tk.Button(fc, text="Send",
                command=lambda: self.queue_custom_command(custom_dev.get(), custom_command.get()))
        custom_button.grid(row=0, column=2, sticky='e')

        # make GUI elements for all devices
        for dev_name, dev in self.parent.devices.items():
            fd = tk.LabelFrame(fr, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"])

            # the button to reload attributes
            attr_b = tk.Button(fd, text="Attrs", command=lambda dev=dev: self.reload_attrs(dev))
            attr_b.grid(row=0, column=2, sticky="nsew")

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
        params = configparser.ConfigParser()
        params.read(dev.config["config_fname"])
        dev.config["attributes"] = params["attributes"]
        attrs = ""
        for attr_name,attr in dev.config["attributes"].items():
            attrs += attr_name + ": " + str(attr) + "\n\n"
        messagebox.showinfo("Device attributes", attrs)

    def refresh_COM_ports(self):
        rl = pyvisa.ResourceManager().list_resources()
        for dev_name, dev in self.parent.devices.items():
            menu = dev.config["controls"]["COM_port"]["OptionMenu"]["menu"]
            COM_var = dev.config["controls"]["COM_port"]["var"]
            menu.delete(0, "end")
            for string in rl:
                menu.add_command(label=string,
                        command=lambda value=string: COM_var.set(value))

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
        time_offset = time.time()
        self.parent.config["time_offset"] = time_offset

        # setup & check connections of all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.setup_connection(time_offset)
                if not dev.operational:
                    messagebox.showerror("Device error",
                            "Error: " + dev.config["label"] + " not responding\
                            correctly, or cannot access the directory for data storage.")
                    self.status_message.set("Device configuration error")
                    return

        # start the thread that writes to HDF
        self.HDF_writer = HDF_writer(self.parent)
        self.HDF_writer.start()

        # start control for all devices
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.start()

        # update program status
        self.status = "running"
        self.status_message.set("Running")

        # make all plots display the current run
        HDF_fname = self.parent.config["hdf_fname"].get()
        self.parent.plots.refresh_run_list(HDF_fname)

    def stop_control(self):
        # check we're not stopped already
        if self.status == "stopped":
            return

        # stop HDF writer
        if self.HDF_writer.active.is_set():
            self.HDF_writer.active.clear()

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
        self.control = ControlGUI(self, *args, **kwargs)
        self.plots   = PlotsGUI(self, *args, **kwargs)

    def read_config(self):
        # read program settings
        self.config = {}
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for key in settings["files"]:
            self.config[key] = tk.StringVar()
            self.config[key].set(settings["files"][key])

        # read device settings
        self.devices = {}
        for f in glob.glob("config/devices/*"):
            params = configparser.ConfigParser()
            params.read(f)

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

            # make a Device object
            self.devices[params["device"]["name"]] = Device(dev_config)

if __name__ == "__main__":
    root = tk.Tk()
    CentrexGUI(root).grid()
    root.mainloop()
