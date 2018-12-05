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

from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110
from drivers import USB6008

from extra_widgets import VerticalScrolledFrame
from Plotting import PlotsGUI

class Device(threading.Thread):
    def __init__(self, config):
        self.config = config
        self.active = threading.Event()
        self.active.clear()
        self.operational = False

        # for sending commands to the device
        self.commands = []

        # for monitoring
        self.last_data  = tk.StringVar()
        self.last_data.set("(no data)")
        self.last_event = tk.StringVar()
        self.last_event.set("(no event)")

    def setup_connection(self):
        threading.Thread.__init__(self)
        self.rm = pyvisa.ResourceManager()

        # check the directory for CSV files exists, else create it
        self.CSV_dir = self.config["current_run_dir"]+"/"+self.config["path"]
        if not os.path.isdir(self.CSV_dir):
            try:
                os.mkdir(self.CSV_dir)
            except OSError:
                return

        # select and record the time offset
        self.config["time_offset"] = time.time()
        to_fname = self.CSV_dir+"/"+self.config["name"]+"_time_offset.csv"
        with open(to_fname,'w') as to_f:
            to_f.write(str(self.config["time_offset"]))

        # verify the device responds correctly
        constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]
        with self.config["driver"](self.rm, *constr_params) as dev: 
            if dev.verification_string == self.config["correct_response"]:
                self.operational = True
            else:
                self.operational = False

        self.rm.close()

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return

        # open CSV files
        CSV_fname = self.CSV_dir+"/"+self.config["name"]+".csv"
        events_fname = self.CSV_dir+"/"+self.config["name"]+"_events.csv"
        with open(CSV_fname,'a',1) as CSV_f,\
             open(events_fname,'a',1) as events_f:
            dev_dset = csv.writer(CSV_f)
            events_dset = csv.writer(events_f)
            constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]

            # main control loop
            self.rm = pyvisa.ResourceManager()
            with self.config["driver"](self.rm, *constr_params) as device: 
                while self.active.is_set():
                    if self.config["controls"]["enabled"]["var"].get():
                        # record numerical values
                        try:
                            last_data = [time.time() - self.config["time_offset"]] + device.ReadValue()
                            dev_dset.writerow(last_data)
                            self.last_data.set( ''.join([str('%.2E'%Decimal(x))+"\n" for x in last_data[1:]]) )
                        except ValueError as err:
                            ret_val = str(err)
                            ret_val = "None" if not ret_val else ret_val
                            events_dset.writerow([ time.time()-self.config["time_offset"], ret_val ])

                        # send control commands, if any, to the device, and record return values
                        for c in self.commands:
                            try:
                                ret_val = eval("device." + c)
                            except (ValueError, AttributeError) as err:
                                ret_val = str(err)
                            ret_val = "None" if not ret_val else ret_val
                            last_event = [ time.time()-self.config["time_offset"], c, ret_val ]
                            self.last_event.set([round(last_event[0],3)]+last_event[1:])
                            events_dset.writerow(last_event)
                        self.commands = []

                        # loop delay
                        try:
                            time.sleep(float(self.config["controls"]["dt"]["var"].get()))
                        except ValueError:
                            time.sleep(1)

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
        if self.directory_empty(self.parent.config["current_run_dir"].get()):
            self.status_message.set("Ready to start")
        else:
            self.status_message.set("Note: run_dir not empty")
        self.status_label = tk.Label(control_frame, textvariable=self.status_message,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=3, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tk.LabelFrame(cgf, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky="ew")

        tk.Label(files_frame, text="Current run directory:")\
                .grid(row=0, column=0, sticky=tk.E)
        run_dir_entry = tk.Entry(files_frame, width=43,
                textvariable=self.parent.config["current_run_dir"])\
                .grid(row=0, column=1, sticky="nsew")
        run_dir_button = tk.Button(files_frame, text="Open...",
                command = lambda: self.open_dir("current_run_dir"))\
                .grid(row=0, column=2, sticky=tk.W)
        run_dir_button = tk.Button(files_frame,
                text="Delete current run data", width=20,
                command = self.delete_current_run)\
                .grid(row=0, column=3, sticky=tk.W)

        tk.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tk.E)
        HDF_file_entry = tk.Entry(files_frame,
                textvariable=self.parent.config["hdf_fname"])\
                .grid(row=1, column=1, sticky="nsew")
        run_dir_button = tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=1, column=2, sticky=tk.W)
        run_dir_button = tk.Button(files_frame, command=self.backup_current_run,
                text="Backup current run...", width=20)\
                .grid(row=1, column=3, sticky=tk.W)

        tk.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame,
                textvariable=self.parent.config["run_name"])\
                .grid(row=2, column=1, sticky="nsew")
        HDF_write_button = tk.Button(files_frame, command=self.write_to_HDF,
                text="Write to HDF", width=20)\
                .grid(row=2, column=3, sticky=tk.W)

        ########################################
        # devices
        ########################################

        fr = tk.LabelFrame(cgf, text="Devices")
        fr.grid(row=2, padx=10, pady=10, sticky='nsew')

        # scrolled frame
        #fr_object = VerticalScrolledFrame(cgf)
        #fr = fr_object.interior
        #fr_object.grid(row=2, padx=10, pady=10, sticky='nsew')

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
                    # place the button
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

    def backup_current_run(self):
        current_run_dir = self.parent.config["current_run_dir"].get()
        backup_dir = filedialog.askdirectory(
                initialdir = self.parent.config["backup_dir"],
                title = "Select directory to save current CSV files")
        if not backup_dir:
            return
        try:
            shutil.copytree(current_run_dir, backup_dir+"/"+str(int(time.time()))+"_CSV_backup")
            messagebox.showinfo("Backup done", "Backup successful.")
        except OSError as exc:
            if exc.errno == errno.ENOTDIR:
                shutil.copy(src, dst)
            else: raise

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

    def directory_empty(self, dir):
        files = glob.glob(dir+"/*/*/*")
        if len(files) == 0:
            return True
        else:
            return False

    def delete_current_run(self):
        # check we're not currently running control
        if self.status == "running":
            messagebox.showerror("Delete error", "Error: cannot delete while running.")
            return

        # check the user really wants to delete
        confirm_delete = False
        if self.status != "writtenToHDF":
            confirm_delete = messagebox.askyesno("Delete current files",
                    "Are you sure you want to delete the current run?")

        # delete if already written to HDF, or if user confirmed deletion
        if confirm_delete or self.status == "writtenToHDF":
            current_run_dir = self.parent.config["current_run_dir"].get()
            try:
                files = glob.glob(current_run_dir+"/*/*/*")
                for f in files:
                    os.remove(f)
            except OSError:
                messagebox.showerror("Delete error", "Error: cannot delete.")
                return

        # check run_dir is now really empty
        current_run_dir = self.parent.config["current_run_dir"].get()
        if not self.directory_empty(current_run_dir):
            messagebox.showerror("Delete error", "Deleting failed.")
            self.status_message.set("Error: delete failed")
        else:
            self.status_message.set("Ready to start")

    def start_control(self):
        # check we're not running already
        if self.status == "running":
            return

        # check run_dir empty
        current_run_dir = self.parent.config["current_run_dir"].get()
        if not self.directory_empty(current_run_dir):
            messagebox.showerror("Run_dir not empty", "Error: run_dir not empty. Please delete current run data.")
            self.status_message.set("Error: run_dir not empty")
            return

        # check device connections
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.setup_connection()
                if not dev.operational:
                    messagebox.showerror("Device error",
                            "Error: " + dev.config["label"] + " not responding correctly, or cannot access the directory for data storage.")
                    self.status_message.set("Device configuration error")
                    return

        # start control
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.active.set()
                dev.start()

        # update program status
        self.status = "running"
        self.status_message.set("Running")

    def stop_control(self):
        # check we're not stopped already
        if self.status == "stopped":
            return

        # stop devices, waiting for threads to finish
        for dev_name, dev in self.parent.devices.items():
            if dev.active.is_set():
                dev.active.clear()

        self.status = "stopped"
        self.status_message.set("Recording finished")

    def write_to_HDF(self):
        if self.status == "writtenToHDF":
            return

        # open HDF file and create groups
        with h5py.File(self.parent.config["hdf_fname"].get(), 'a') as f:
            root = f.create_group(str(int(time.time())) + " " + self.parent.config["run_name"].get())

            for dev_name, dev in self.parent.devices.items():
                # check the device is enabled
                if not dev.config["controls"]["enabled"]["var"].get():
                    continue

                grp = root.require_group(dev.config["path"])

                # read CSV and write to HDF
                dev_CSV = np.loadtxt(self.parent.config["current_run_dir"].get() + "/" +
                                        dev.config["path"] + "/" + dev.config["name"] + ".csv", delimiter=',')
                dev_dset = grp.create_dataset(dev.config["name"], data=dev_CSV, dtype='f')

                # write command events, if any, to HDF
                events_fname = self.parent.config["current_run_dir"].get() + "/" + dev.config["path"] + "/" + dev.config["name"] + "_events.csv"
                if os.stat(events_fname).st_size != 0:

                    # read events as a list of lists of ascii strings
                    with open(events_fname,'r',newline='\n') as events_f:
                        events_list = []
                        for row in csv.reader(events_f, delimiter=','):
                            events_list.append([x.encode("ascii") for x in row])

                    events_list = np.array(events_list, dtype=object)
                    events_dset = grp.create_dataset(dev.config["name"] + " events",
                            data=events_list, dtype=h5py.special_dtype(vlen=str))

                # write time offset to HDF
                to_fname = dev.config["current_run_dir"] + "/" + dev.config["path"] + "/" + dev_name + "_time_offset.csv"
                with open(to_fname,'r') as to_f:
                    dev_dset.attrs["time_offset"] = float(to_f.read())

                # write attributes to HDF
                for attr_name, attr in dev.config["attributes"].items():
                    dev_dset.attrs[attr_name] = attr

        self.status = "writtenToHDF"
        self.status_message.set("Written to HDF")

class MonitoringGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all MonitoringGUI elements
        mgf = tk.Frame(self.parent.nb)
        self.parent.nb.add(mgf, text="Monitoring")

        # entries for each device
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            fd = tk.LabelFrame(mgf, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"])
            tk.Message(fd, textvariable=dev.last_data, anchor='nw', width=100)\
                    .grid(row=0, column=0, sticky='nsew')
            tk.Message(fd, textvariable=dev.last_event, anchor='nw', width=150).\
                    grid(row=1, column=0, sticky='nsew')

class CentrexGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.winfo_toplevel().title("CENTREX Slow DAQ")
        self.parent = parent
        self.read_config()

        # GUI elements in a tabbed interface
        self.nb = ttk.Notebook(self)
        self.nb.grid()
        ControlGUI(self, *args, **kwargs)
        MonitoringGUI(self, *args, **kwargs)
        PlotsGUI(self, *args, **kwargs)

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
                        "current_run_dir"   : self.config["current_run_dir"].get(),
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
