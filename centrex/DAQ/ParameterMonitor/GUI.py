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

# suppress weird h5py warnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import h5py
warnings.resetwarnings()

from Recorder import Recorder
sys.path.append('..')
from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110

class RecorderGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        ########################################
        # recording control and status
        ########################################

        control_frame = tk.LabelFrame(self.parent)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")
        control_frame.grid_columnconfigure(index=2, weight=1)

        record_button = tk.Button(control_frame,
                text="\u26ab Start recording", command = self.start_recording)\
                .grid(row=0, column=0)
        stop_button = tk.Button(control_frame,
                text="\u2b1b Stop recording", command = self.stop_recording)\
                .grid(row=0, column=1)

        self.status = "stopped"
        self.status_message = tk.StringVar()
        if self.directory_empty(self.parent.config["current_run_dir"].get()):
            self.status_message.set("Ready to record")
        else:
            self.status_message.set("Recording finished")
        self.status_label = tk.Label(control_frame, textvariable=self.status_message,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=2, sticky='nsew')

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

        devices_frame = tk.LabelFrame(self.parent, text="Devices")
        devices_frame.grid(row=2, padx=10, pady=10, sticky='nsew')

        # make the list of VISA resources
        rl = pyvisa.ResourceManager().list_resources()

        # make the GUI elements and their variables for the list of devices
        self.device_GUI_list = {}
        for d in self.parent.devices:
            self.device_GUI_list[d] = {
                "enable_b" : tk.Checkbutton(devices_frame, variable=self.parent.devices[d]["enabled"]),
                "label"    : tk.Label(devices_frame, text=self.parent.devices[d]["label"]),
                "dt"       : tk.Entry(devices_frame, textvariable=self.parent.devices[d]["dt"], width=5),
                "COM_menu" : tk.OptionMenu(devices_frame, self.parent.devices[d]["COM_port"], *rl),
                "attrs"    : tk.Button(devices_frame, text="Attrs..."),
            }

        # place the device list GUI elements in a grid
        for i,d in enumerate(self.device_GUI_list):
            self.device_GUI_list[d]["enable_b"].grid(row=i, column=0, sticky=tk.E)
            self.device_GUI_list[d]["label"].grid(row=i, column=1, sticky=tk.W)
            self.device_GUI_list[d]["dt"].grid(row=i, column=2, sticky=tk.W)
            self.device_GUI_list[d]["COM_menu"].grid(row=i, column=3, sticky='ew', padx=10)
            self.device_GUI_list[d]["attrs"].grid(row=i, column=4, sticky=tk.W)

        # button to refresh the list of COM ports
        tk.Button(devices_frame, text="Refresh COM ports",
                command=self.refresh_COM_ports)\
                        .grid(row=len(self.device_GUI_list), column=3, sticky='ew')

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
        # check we're not currently recording
        if self.status == "recording":
            messagebox.showerror("Delete error", "Error: cannot delete while recording.")
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
                self.status_message.set("Ready to record")
            except OSError:
                messagebox.showerror("Delete error", "Error: cannot delete.")

    def start_recording(self):
        # check we're not recording already
        if self.status == "recording":
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

        # start all recorders
        for key in self.parent.devices:
            if self.parent.devices[key]["enabled"].get():
                self.parent.devices[key]["recorder"].start()

        # update status
        self.status = "recording"
        self.status_message.set("Recording")

    def stop_recording(self):
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

        # read program settings
        self.config = {}
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for sect in settings.sections():
            for key in settings[sect]:
                self.config[key] = tk.StringVar()
                self.config[key].set(settings[sect][key])

        # read list of devices
        self.devices = {}
        devices = configparser.ConfigParser()
        devices.read("config/devices.ini")
        for d in devices.sections():
            self.devices[d] = {
                        "label"             : devices[d]["label"],
                        "path"              : devices[d]["path"],
                        "driver"            : eval(devices[d]["driver"]),
                        "COM_port"          : tk.StringVar(),
                        "name"              : d,
                        "dt"                : tk.StringVar(),
                        "enabled"           : tk.IntVar(),
                        "correct_response"  : devices[d]["correct_response"],
                    }
            self.devices[d]["enabled"].set(devices[d].getboolean("enabled"),)
            self.devices[d]["dt"].set(devices[d].getfloat("dt"),)
            self.devices[d]["COM_port"].set(devices[d]["COM_port"],)

        # parse device attributes
        attrs = configparser.ConfigParser()
        attrs.read("config/device_attributes.ini")
        for d in attrs.sections():
            self.devices[d]["attrs"] = {key : attrs[d][key] for key in attrs[d]}

        # GUI elements
        self.recordergui = RecorderGUI(self, *args, **kwargs)
        self.recordergui.grid(row=0, column=0)

    def save_config(self):
        # write program settings to disk
        with open("config/settings.ini", 'w') as settings_f:
            settings = configparser.ConfigParser()
            settings['files'] = {
                    'current_run_dir' : self.config['current_run_dir'].get(),
                    'hdf_fname'       : self.config['hdf_fname'].get(),
                    'run_name'        : self.config['run_name'].get(),
                }
            settings.write(settings_f)

        # write device configuration to disk
        with open("config/devices.ini", 'w') as dev_f:
            dev = configparser.ConfigParser()
            for d in self.devices:
                dev[d] = {
                        "label"             : self.devices[d]["label"],
                        "path"              : self.devices[d]["path"],
                        "driver"            : self.devices[d]["driver"].__name__,
                        "COM_port"          : self.devices[d]["COM_port"].get(),
                        "dt"                : self.devices[d]["dt"].get(),
                        "enabled"           : self.devices[d]["enabled"].get(),
                        "correct_response"  : self.devices[d]["correct_response"],
                    }
            dev.write(dev_f)

        # write device attributes to disk
        with open("config/device_attributes.ini", 'w') as dev_attr_f:
            dev_attr = configparser.ConfigParser()
            for d in self.devices:
                dev_attr[d] = self.devices[d]["attrs"]
            dev_attr.write(dev_attr_f)

if __name__ == "__main__":
    root = tk.Tk()
    CentrexGUI(root).pack(side="top", fill="both", expand=True)
    root.mainloop()
