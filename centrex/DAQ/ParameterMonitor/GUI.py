import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import os
import glob
import pyvisa
import sys
import configparser

from Recorder import Recorder
sys.path.append('..')
from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110

class CentrexGUI:
    def __init__(self, root):
        self.root = root
        self.ReadConfig()
        self.status = tk.StringVar()
        self.status.set("                " + "Ready to record")
        self.RecorderGUI()

    def ReadConfig(self):
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
                        "label"    : devices[d]["label"],
                        "path"     : devices[d]["path"],
                        "driver"   : eval(devices[d]["driver"]),
                        "COM_port" : devices[d]["COM_port"],
                        "name"     : d,
                        "dt"       : devices[d].getfloat("dt")
                    }

        # parse device attributes
        attrs = configparser.ConfigParser()
        attrs.read("config/device_attributes.ini")
        for d in attrs.sections():
            self.devices[d]["attrs"] = {key : attrs[d][key] for key in attrs[d]}

    def open_file(self, prop):
        self.config[prop].set(filedialog.asksaveasfilename(
                initialdir = "C:/Users/CENTREX/Documents/data",
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*"))))

    def open_dir(self, prop):
        self.config[prop].set(filedialog.askdirectory(
                initialdir = "C:/Users/CENTREX/Documents/data",
                title = "Select directory"))

    def delete_current_run(self):
        if messagebox.askyesno("Delete current files",
                "Are you sure you want to delete the current run?"):
            current_run_dir = self.config["current_run_dir"].get()
            try:
                files = glob.glob(current_run_dir+"/beam_source/*/*")
                for f in files:
                    os.remove(f)
            except OSError:
                messagebox.showerror( "Error: cannot delete.")

    def start_recording(self):
        rm = pyvisa.ResourceManager()
        current_run_dir = self.config["current_run_dir"].get()
        for key in self.config["devices"]:
            d = self.config["devices"][key]
            if d.enabled:
                d.recorder = Recorder(rm, current_run_dir, d.path, d.driver,
                        d.COM_port, d.name, d.dt, d.attrs)
                d.recorder.start()
        self.status.set("                      Recording")

    def stop_recording(self):
        for key in self.config["devices"]:
            self.config["devices"][key].recorder.active.clear()
        self.status.set("                Ready to record")

    def RecorderGUI(self):
        ########################################
        # recording control and status
        ########################################

        control_frame = tk.LabelFrame(self.root)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")

        record_button = tk.Button(control_frame,
                text="Start recording", command = self.start_recording)\
                .grid(row=0, column=0)
        stop_button = tk.Button(control_frame,
                text="Stop recording", command = self.stop_recording)\
                .grid(row=0, column=1)

        self.status_label = tk.Label(control_frame, textvariable=self.status,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=2, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tk.LabelFrame(self.root, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky=tk.W)

        tk.Label(files_frame, text="Current run directory:")\
                .grid(row=0, column=0, sticky=tk.E)
        run_dir_entry = tk.Entry(files_frame, width=30,
                textvariable=self.config["current_run_dir"])\
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
                textvariable=self.config["hdf_fname"])\
                .grid(row=1, column=1, sticky=tk.W)
        run_dir_button = tk.Button(files_frame, text="Open...",
                command = lambda: self.open_file("hdf_fname"))\
                .grid(row=1, column=2, sticky=tk.W)
        run_dir_button = tk.Button(files_frame,
                text="Archive current run...", width=20)\
                .grid(row=1, column=3, sticky=tk.W)

        tk.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tk.E)
        run_name_entry = tk.Entry(files_frame, width=30,
                textvariable=self.config["run_name"])\
                .grid(row=2, column=1, sticky=tk.W)
        run_dir_button = tk.Button(files_frame,
                text="Write to HDF", width=20)\
                .grid(row=2, column=3, sticky=tk.W)

        ########################################
        # devices
        ########################################

        devices_frame = tk.LabelFrame(self.root, text="Devices")
        devices_frame.grid(row=2, padx=10, pady=10, sticky='nsew')

        # make the GUI elements for the list of devices
        self.device_GUI_list = {}
        for d in self.devices:
            self.device_GUI_list[d] = [
                tk.Checkbutton(devices_frame),
                tk.Label(devices_frame, text=self.devices[d]["label"]),
                tk.Entry(devices_frame, width=5),
                tk.Entry(devices_frame, width=10),
                tk.Button(devices_frame, text="Attrs..."),
            ]

        # place the device list GUI elements in a grid
        for i,d in enumerate(self.device_GUI_list):
            self.device_GUI_list[d][0].grid(row=i, column=0, sticky=tk.E)
            self.device_GUI_list[d][1].grid(row=i, column=1, sticky=tk.W)
            self.device_GUI_list[d][2].grid(row=i, column=2, sticky=tk.W)
            self.device_GUI_list[d][3].grid(row=i, column=3, sticky=tk.W, padx=10)
            self.device_GUI_list[d][4].grid(row=i, column=4, sticky=tk.W)

root = tk.Tk()
CentrexGUI(root)
root.mainloop()
