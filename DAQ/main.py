import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import os
import glob
import pyvisa
import sys
import configparser
import time
import numpy as np
import csv
import shutil, errno
import threading
import h5py

from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110
from drivers import USB6008

class Device(threading.Thread):
    def __init__(self, config):
        self.active = threading.Event()
        self.active.clear()
        self.config = config
        self.commands = []

    def setup_connection(self):
        threading.Thread.__init__(self)
        self.rm = pyvisa.ResourceManager()

        # select and record the time offset
        self.config["time_offset"] = time.time()
        to_fname = self.config["current_run_dir"]+"/"+self.config["path"]+"/"+self.config["name"]+"_time_offset.csv"
        with open(to_fname,'w') as to_f:
            to_f.write(str(self.config["time_offset"]))

        # verify the device responds correctly
        constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]
        with self.config["driver"](self.rm, *constr_params) as dev: 
            self.operational = dev.VerifyOperation() == self.config["correct_response"]

        self.rm.close()

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return

        # open CSV files
        CSV_fname = self.config["current_run_dir"]+"/"+self.config["path"]+"/"+self.config["name"]+".csv"
        events_fname = self.config["current_run_dir"]+"/"+self.config["path"]+"/"+self.config["name"]+"_events.csv"
        with open(CSV_fname,'a',1) as CSV_f,\
             open(events_fname,'a',1) as events_f:
            dev_dset = csv.writer(CSV_f)
            events_dset = csv.writer(events_f)
            constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]

            # main control loop
            self.rm = pyvisa.ResourceManager()
            with self.config["driver"](self.rm, *constr_params) as device: 
                while self.active.is_set():
                    # record numerical values
                    dev_dset.writerow( [time.time() - self.config["time_offset"]] + device.ReadValue() )

                    # send control commands, if any, to the device, and record return values
                    for c in self.commands:
                        ret_val = eval("device." + c)
                        ret_val = "None" if not ret_val else ret_val
                        events_dset.writerow([ time.time()-self.config["time_offset"], c, ret_val ])
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
        ########################################
        # control and status
        ########################################

        control_frame = tk.LabelFrame(self.parent)
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
            self.status_message.set("Recording finished")
        self.status_label = tk.Label(control_frame, textvariable=self.status_message,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=3, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tk.LabelFrame(self.parent, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky="nsew")

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

        fr = tk.LabelFrame(self.parent, text="Devices")
        fr.grid(row=2, padx=10, pady=10, sticky='nsew')

        # make GUI elements for all devices
        for dev_name, dev in self.parent.devices.items():
            fd = tk.LabelFrame(fr, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"])

            # the button to reload attributes
            attr_b = tk.Button(fd, text="Attrs", command=lambda dev=dev: self.reload_attrs(dev))
            attr_b.grid(row=0, column=2, sticky="nsew")

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
                    if c["argument"] == "":
                        c["Button"] = tk.Button(fd, text=c["label"],
                                command= lambda dev=dev, cmd=c["command"]+"()": self.queue_command(dev, cmd))
                    else:
                        c["Button"] = tk.Button(fd, text=c["label"], command= lambda dev=dev,
                                cmd=c["command"], arg=dev.config["controls"][c["argument"]]["var"]:
                                    self.queue_command(dev, cmd+"("+arg.get()+")"))
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
                initialdir = "C:/Users/CENTREX/Documents/data",
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
                files = glob.glob(current_run_dir+"/beam_source/*/*")
                for f in files:
                    os.remove(f)
                self.status_message.set("Ready to start")
            except OSError:
                messagebox.showerror("Delete error", "Error: cannot delete.")
                return

        # check run_dir is now really empty
        current_run_dir = self.parent.config["current_run_dir"].get()
        if not self.directory_empty(current_run_dir):
            messagebox.showerror("Delete error", "Error: cannot delete.")

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

        # check device connections and start control
        for dev_name, dev in self.parent.devices.items():
            if dev.config["controls"]["enabled"]["var"].get():
                dev.setup_connection()
                if not dev.operational:
                    messagebox.showerror("Device error",
                            "Error: " + dev.config["label"] + " not responding correctly.")
                    self.status_message.set("Device configuration error")
                    return
                else:
                    dev.active.set()
                    dev.start()

        # update program status
        self.status = "running"
        self.status_message.set("Running")

    def stop_control(self):
        # check we're not stopped already
        if self.status == "stopped":
            return

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

                    events_dset = grp.create_dataset(dev.config["name"] + " events",
                            data=events_list, dtype=h5py.special_dtype(vlen=bytes))

                # write time offset to HDF
                to_fname = dev.config["current_run_dir"] + "/" + dev.config["path"] + "/" + dev_name + "_time_offset.csv"
                with open(to_fname,'r') as to_f:
                    dev_dset.attrs["time_offset"] = float(to_f.read())

                # write attributes to HDF
                for attr_name, attr in dev.config["attributes"].items():
                    dev_dset.attrs[attr_name] = attr

        self.status = "writtenToHDF"
        self.status_message.set("Written to HDF")

class CentrexGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.winfo_toplevel().title("CENTREX Slow DAQ")
        self.parent = parent
        self.read_config()

        # GUI elements
        ControlGUI(self, *args, **kwargs).grid(row=0, column=0)

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
                    ctrls[c]["command"]    = params[c]["command"]
                    ctrls[c]["argument"]   = params[c]["argument"]
                    ctrls[c]["align"]      = params[c].get("align")
                elif params[c].get("type") == "Entry":
                    ctrls[c] = {}
                    ctrls[c]["label"]      = params[c]["label"]
                    ctrls[c]["type"]       = params[c]["type"]
                    ctrls[c]["row"]        = int(params[c]["row"])
                    ctrls[c]["col"]        = int(params[c]["col"])
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
    CentrexGUI(root).pack(side="top", fill="both", expand=True)
    root.mainloop()
