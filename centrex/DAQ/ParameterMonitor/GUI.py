import tkinter
from tkinter import filedialog
from tkinter import messagebox
import os
import glob
import pyvisa
import sys

from Recorder import Recorder
sys.path.append('..')
from drivers import Hornet 
from drivers import LakeShore218 
from drivers import LakeShore330 
from drivers import CPA1110

class Device:
    def __init__(self, path, driver, COM_port, name, dt, attrs):
        self.path = path
        self.driver = driver
        self.COM_port = COM_port
        self.name = name
        self.dt = dt
        self.attrs = attrs
        self.enabled = True

# Defaults for the devices
devices = {
        "IG" : Device("beam_source/pressure", Hornet, 'COM4', 'IG', 1, 
            {"IG filament current" : "100 microamps",
             "units" : ["s", "torr"],
             "column_names" : ["time", "IG pressure"] }),
        "L218" : Device("beam_source/thermal", LakeShore218, 'COM1', 'L218', 0.25, 
            {"units" : ["s", "K", "K", "K", "K", "K", "K", "K", "K", "K", "K"],
             "column_names" : ["time", "cell back snorkel", "4K shield top",
                "40K shield top", "40K PT cold head", "cell top plate", "4K shield bottom",
                "40K shield bottom", "16K PT cold head"] }),
         "L330" : Device("beam_source/thermal", LakeShore330, 'GPIB0::16', 'L330', 0.25, 
            {"units" : ["s", "K", "K"],
             "column_names" : ["time", "4K PT warm stage", "cell top plate, target side"] }),
        "top_compressor" : Device("beam_source/thermal", CPA1110, 'COM10', 'top_compressor', 1.00, 
            {"column_names" : ["time", "CoolantInTemp",
             "CoolantOutTemp", "OilTemp", "HeliumTemp", "LowPressure",
             "LowPressureAverage", "HighPressure", "HighPressureAverage",
             "DeltaPressureAverage", "MotorCurrent"],
             "units" : ["s", "F", "F", "F", "F", "psi", "psi",
             "psi", "psi", "psi", "amps"] }),
         "bottom_compressor" : Device("beam_source/thermal", CPA1110, 'COM11', 'bottom_compressor', 1.00, 
            {"column_names" : ["time", "CoolantInTemp",
             "CoolantOutTemp", "OilTemp", "HeliumTemp", "LowPressure",
             "LowPressureAverage", "HighPressure", "HighPressureAverage",
             "DeltaPressureAverage", "MotorCurrent"],
             "units" : ["s", "F", "F", "F", "F", "psi", "psi",
             "psi", "psi", "psi", "amps"] }),
    }

class CentrexGUI:
    def __init__(self, root):
        self.root = root
        self.config = {"run_name"          : tkinter.StringVar(),
                       "current_run_dir"   : tkinter.StringVar(),
                       "HDF_fname"         : tkinter.StringVar(),
                       "devices"           : devices}
        self.status = tkinter.StringVar()

        # set defaults
        self.config["current_run_dir"].set("C:/Users/CENTREX/Documents/data/current_run_dir")
        self.status.set("                Ready to record")

        # display the GUI
        self.RecorderGUI()

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

        control_frame = tkinter.LabelFrame(self.root)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")

        record_button = tkinter.Button(control_frame,
                text="Start recording", command = self.start_recording)\
                .grid(row=0, column=0)
        stop_button = tkinter.Button(control_frame,
                text="Stop recording", command = self.stop_recording)\
                .grid(row=0, column=1)

        self.status_label = tkinter.Label(control_frame, textvariable=self.status,
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=2, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tkinter.LabelFrame(self.root, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky=tkinter.W)

        tkinter.Label(files_frame, text="Current run directory:")\
                .grid(row=0, column=0, sticky=tkinter.E)
        run_dir_entry = tkinter.Entry(files_frame, width=30,
                textvariable=self.config["current_run_dir"])\
                .grid(row=0, column=1, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame, text="Open...",
                command = lambda: self.open_dir("current_run_dir"))\
                .grid(row=0, column=2, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame,
                text="Delete current run data", width=20,
                command = self.delete_current_run)\
                .grid(row=0, column=3, sticky=tkinter.W)

        tkinter.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tkinter.E)
        HDF_file_entry = tkinter.Entry(files_frame, width=30,
                textvariable=self.config["HDF_fname"])\
                .grid(row=1, column=1, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame, text="Open...",
                command = lambda: self.open_file("HDF_fname"))\
                .grid(row=1, column=2, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame,
                text="Archive current run...", width=20)\
                .grid(row=1, column=3, sticky=tkinter.W)

        tkinter.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tkinter.E)
        run_name_entry = tkinter.Entry(files_frame, width=30,
                textvariable=self.config["run_name"])\
                .grid(row=2, column=1, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame,
                text="Write to HDF", width=20)\
                .grid(row=2, column=3, sticky=tkinter.W)

        ########################################
        # devices
        ########################################

        devices_frame = tkinter.LabelFrame(self.root, text="Devices")
        devices_frame.grid(row=2, padx=10, pady=10, sticky='nsew')

        L218_ch = tkinter.Checkbutton(devices_frame)\
                .grid(row=0, column=0, sticky=tkinter.E)
        tkinter.Label(devices_frame, text="LakeShore 218")\
                .grid(row=0, column=1, sticky=tkinter.W)
        L218_delay_entry = tkinter.Entry(devices_frame,width=5)\
                .grid(row=0, column=2, sticky=tkinter.W)
        L218_COM_entry = tkinter.Entry(devices_frame,width=10)\
                .grid(row=0, column=3, sticky=tkinter.W,padx=10)
        L218_attrs_button = tkinter.Button(devices_frame, text="Attrs...")\
                .grid(row=0, column=4, sticky=tkinter.W)

        L330_ch = tkinter.Checkbutton(devices_frame)\
                .grid(row=1, column=0, sticky=tkinter.E)
        tkinter.Label(devices_frame, text="LakeShore 330")\
                .grid(row=1, column=1, sticky=tkinter.W)
        L330_delay_entry = tkinter.Entry(devices_frame,width=5)\
                .grid(row=1, column=2, sticky=tkinter.W)
        L330_COM_entry = tkinter.Entry(devices_frame,width=10)\
                .grid(row=1, column=3, sticky=tkinter.W,padx=10)
        L330_attrs_button = tkinter.Button(devices_frame, text="Attrs...")\
                .grid(row=1, column=4, sticky=tkinter.W)

        CPA1110_ch = tkinter.Checkbutton(devices_frame)\
                .grid(row=2, column=0, sticky=tkinter.E)
        tkinter.Label(devices_frame, text="CPA1110")\
                .grid(row=2, column=1, sticky=tkinter.W)
        CPA1110_delay_entry = tkinter.Entry(devices_frame,width=5)\
                .grid(row=2, column=2, sticky=tkinter.W)
        CPA1110_COM_entry = tkinter.Entry(devices_frame,width=10)\
                .grid(row=2, column=3, sticky=tkinter.W,padx=10)
        CPA1110_attrs_button = tkinter.Button(devices_frame, text="Attrs...")\
                .grid(row=2, column=4, sticky=tkinter.W)

        Hornet_ch = tkinter.Checkbutton(devices_frame)\
                .grid(row=3, column=0, sticky=tkinter.E)
        tkinter.Label(devices_frame, text="Hornet")\
                .grid(row=3, column=1, sticky=tkinter.W)
        Hornet_delay_entry = tkinter.Entry(devices_frame,width=5)\
                .grid(row=3, column=2, sticky=tkinter.W)
        Hornet_COM_entry = tkinter.Entry(devices_frame,width=10)\
                .grid(row=3, column=3, sticky=tkinter.W,padx=10)
        Hornet_attrs_button = tkinter.Button(devices_frame, text="Attrs...")\
                .grid(row=3, column=4, sticky=tkinter.W)

root = tkinter.Tk()
CentrexGUI(root)
root.mainloop()
