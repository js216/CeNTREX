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
import atexit
import threading
import h5py

from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110

class Device(threading.Thread):
    def __init__(self, config):
        self.config = config

    def setup_connection(self):
        # thread control
        threading.Thread.__init__(self)
        self.active = threading.Event()

        # record the device operating parameters
        self.config["time_offset"] = time.time()
        with open(self.config["path"]+"/"+self.config["name"]+"_params.csv",'w') as params_f:
            dev_params = csv.writer(params_f)
            dev_params.writerow(["time_offset", self.config["time_offset"]])
            for key in attrs:
                dev_params.writerow([key, attrs[key]])

        # verify the device responds correctly
        rm = pyvisa.ResourceManager()
        COM_port = self.config[controls]["COM_port"]["var"].get()
        with self.config["driver"](rm, COM_port) as dev: 
            self.operational = dev.VerifyOperation() == self.config["correct_response"]

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return

        # open CSV file
        rm = pyvisa.ResourceManager()
        CSV_fname = self.config["path"]+"/"+self.config["name"]+".csv"
        with open(CSV_fname,'a',1) as CSV_f:
            dev_dset = csv.writer(CSV_f)
            COM_port = self.config[controls]["COM_port"]["var"].get()

            # main control loop
            with self.config["driver"](rm, COM_port) as device: 
                while self.active.is_set():
                    # record numerical values
                    dev_dset.writerow([ time.time() - self.config["time_offset"]] + device.ReadValue() )

                    # send control commands, if any, to the device
                    # TODO

                    # loop delay
                    time.sleep(self.config[controls]["dt"]["var"].get())

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
                .grid(row=0, column=0)
        stop_button = tk.Button(control_frame,
                text="\u2b1b Stop control", command = self.stop_control)\
                .grid(row=0, column=1)

        # button to refresh the list of COM ports
        tk.Button(control_frame, text="Refresh COM ports", command=self.refresh_COM_ports)\
                        .grid(row=1, column=0, sticky='ew')

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
        files_frame.grid(row=1, padx=10, pady=10, sticky=tk.W)

        tk.Label(files_frame, text="Current run directory:")\
                .grid(row=0, column=0, sticky=tk.E)
        run_dir_entry = tk.Entry(files_frame, width=30,
                textvariable=self.parent.config["current_run_dir"])\
                .grid(row=0, column=1, sticky=tk.W)
        run_dir_button = tk.Button(files_frame, text="Open...",
                command = lambda: self.open_dir("current_run_dir"))\
                .grid(row=0, column=2, sticky=tk.W)
        run_dir_button = tk.Button(files_frame,
                text="Delete current run data", width=20,
                command = self.delete_current_run)\
                .grid(row=0, column=3, sticky=tk.W)

        tk.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tk.E)
        HDF_file_entry = tk.Entry(files_frame, width=30,
                textvariable=self.parent.config["hdf_fname"])\
                .grid(row=1, column=1, sticky=tk.W)
        run_dir_button = tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=1, column=2, sticky=tk.W)
        run_dir_button = tk.Button(files_frame, command=self.backup_current_run,
                text="Backup current run...", width=20)\
                .grid(row=1, column=3, sticky=tk.W)

        tk.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame, width=30,
                textvariable=self.parent.config["run_name"])\
                .grid(row=2, column=1, sticky=tk.W)
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
            fd.grid(padx=10, pady=10, row=dev.config["row"], column=dev.config["column"])

            for i, (c_name, c) in enumerate(dev.config["controls"].items()):
                if c_name == "LabelFrame":
                    continue

                # place Checkbuttons
                if c["type"] == "Checkbutton":
                    c["Checkbutton"] = tk.Checkbutton(fd, variable=c["var"])
                    c["Checkbutton"].grid(row=i+1, column=1, sticky=tk.W)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=i+1, column=0)

                # place Buttons
                if c["type"] == "Button":
                    c["Button"] = tk.Button(fd, text=c["label"])
                    c["Button"].grid(row=i+1+c["row_offset"], column=c["column"], sticky=tk.W)

                # place Entries
                elif c["type"] == "Entry":
                    c["Entry"] = tk.Entry(fd, textvariable=c["var"])
                    c["Entry"].grid(row=i+1, column=1, sticky=tk.W)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=i+1, column=0)

                # place OptionMenus
                elif c["type"] == "OptionMenu":
                    c["OptionMenu"] = tk.OptionMenu(fd, c["var"], *c["options"])
                    c["OptionMenu"].grid(row=i+1, column=1, sticky=tk.W)
                    c["Label"] = tk.Label(fd, text=c["label"])
                    c["Label"].grid(row=i+1, column=0)


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
        for d in self.device_GUI_list:
            menu = self.device_GUI_list[d]["COM_menu"]["menu"]
            COM_var = self.device_GUI_list["COM_var"][3]
            menu.delete(0, "end")
            for string in rl:
                menu.add_command(label=string,
                        command=lambda value=string: COM_var.set(value))

    def open_file(self, prop):
        fname = filedialog.asksaveasfilename(
                initialdir = "C:/Users/CENTREX/Documents/data",
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))
        if not fname:
            return
        else:
            self.parent.config[prop].set(fname)

    def open_dir(self, prop):
        fname = filedialog.askdirectory(
                initialdir = "C:/Users/CENTREX/Documents/data",
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

        # connect to devices and check they respond correctly
        for key in self.parent.devices:
            d = self.parent.devices[key]
            if d["enabled"].get():
                d["recorder"] = Recorder(current_run_dir, d["path"],
                                         d["driver"], d["COM_port"].get(), d["name"],
                                         float(d['dt'].get()), d["attrs"])
                if d["recorder"].verify != d["correct_response"]:
                    messagebox.showerror("Device error",
                            "Error: " + d["label"] + " not responding correctly.")
                    self.status_message.set("Device configuration error")
                    return
                d["recorder"].active.set()

        # start all devices
        for key in self.parent.devices:
            if self.parent.devices[key]["enabled"].get():
                self.parent.devices[key]["recorder"].start()

        # update status
        self.status = "running"
        self.status_message.set("Running")

    def stop_control(self):
        if self.status == "stopped":
            return
        for key in self.parent.devices:
            recorder = self.parent.devices[key].get("recorder")
            if recorder:
                recorder.active.clear()
        self.status = "stopped"
        self.status_message.set("Recording finished")

    def write_to_HDF(self):
        if self.status == "writtenToHDF":
            return

        # open HDF file and create groups
        with h5py.File(self.parent.config["hdf_fname"].get(), 'a') as f:
            root = f.create_group(str(int(time.time())) + " " + self.parent.config["run_name"].get())
            for key in self.parent.devices:
                d = self.parent.devices[key]
                grp = root.require_group(d["path"])

                # read CSV and write to HDF
                dev_CSV = np.loadtxt(self.parent.config["current_run_dir"].get() + "/" +
                                        d["path"] + "/" + d["name"] + ".csv", delimiter=',')
                dev_dset = grp.create_dataset(d["name"], data=dev_CSV, dtype='f')

                # write attributes to HDF
                with open(self.parent.config["current_run_dir"].get() + "/" + d["path"] + "/" + d["name"] +
                                        "_params.csv", 'r', newline='\n') as dev_params_f:
                    dev_params_CSV = csv.reader(dev_params_f, delimiter=',')
                    for col in dev_params_CSV:
                        if len(col) == 2:
                            dev_dset.attrs[col[0]] = col[1]
                        else:
                            dev_dset.attrs[col[0]] = asc(col[1:])

        self.status = "writtenToHDF"
        self.status_message.set("Written to HDF")

class CentrexGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.winfo_toplevel().title("CENTREX Slow DAQ")
        self.parent = parent
        atexit.register(self.save_config)
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
                        "path"              : params["device"]["path"],
                        "correct_response"  : params["device"]["correct_response"],
                        "row"               : params["device"]["row"],
                        "column"            : params["device"]["column"],
                        "driver"            : eval(params["device"]["driver"]),
                        "attributes"        : params["attributes"],
                        "controls"          : {},
                    }

            # populate the list of device controls
            ctrls = dev_config["controls"]
            for c in params.sections():
                if params[c].get("type") == "Checkbutton":
                    ctrls[c] = {}
                    ctrls[c]["label"] = params[c]["label"]
                    ctrls[c]["type"]  = params[c]["type"]
                    ctrls[c]["var"]   = tk.BooleanVar()
                    ctrls[c]["var"].set(params[c]["value"])
                if params[c].get("type") == "Button":
                    ctrls[c] = {}
                    ctrls[c]["label"]  = params[c]["label"]
                    ctrls[c]["type"]   = params[c]["type"]
                    ctrls[c]["row_offset"] = int(params[c]["row_offset"])
                    ctrls[c]["column"] = int(params[c]["column"])
                elif params[c].get("type") == "Entry":
                    ctrls[c] = {}
                    ctrls[c]["label"] = params[c]["label"]
                    ctrls[c]["type"]  = params[c]["type"]
                    ctrls[c]["var"]   = tk.StringVar()
                    ctrls[c]["var"].set(params[c]["value"])
                elif params[c].get("type") == "OptionMenu":
                    ctrls[c] = {}
                    ctrls[c]["label"]   = params[c]["label"]
                    ctrls[c]["type"]    = params[c]["type"]
                    ctrls[c]["options"] = params[c]["options"].split(",")
                    ctrls[c]["var"]     = tk.StringVar()
                    ctrls[c]["var"].set(params[c]["value"])

            # make a Device object
            self.devices[params["device"]["name"]] = Device(dev_config)

    def save_config(self):
        # TODO
        pass

if __name__ == "__main__":
    root = tk.Tk()
    CentrexGUI(root).pack(side="top", fill="both", expand=True)
    root.mainloop()
