import time

import tkinter
from tkinter import filedialog

class CentrexGUI:
    def __init__(self, root):
        self.root = root
        self.config = {"run_name"          : tkinter.StringVar(),
                       "current_run_dir"   : tkinter.StringVar(),
                       "HDF_fname"         : tkinter.StringVar()}
        self.RecorderGUI()

    def open_file(self, prop):
        self.config[prop] = filedialog.asksaveasfilename(
                initialdir = "/",
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))

    def open_dir(self, prop):
        self.config[prop] = filedialog.askdirectory(
                initialdir = "/", title = "Select directory")

    def RecorderGUI(self):
        ########################################
        # recording control and status
        ########################################

        control_frame = tkinter.LabelFrame(self.root)
        control_frame.grid(row=0, padx=10, pady=10, sticky="nsew")

        record_button = tkinter.Button(control_frame,
                text="Start recording")\
                .grid(row=0, column=0)
        pause_button = tkinter.Button(control_frame,
                text="Pause recording")\
                .grid(row=0, column=1)

        status_label = tkinter.Label(control_frame, text="                Ready to record",
                font=("Helvetica", 16),anchor='e')\
                .grid(row=0, column=2, sticky='nsew')

        ########################################
        # files
        ########################################

        files_frame = tkinter.LabelFrame(self.root, text="Files")
        files_frame.grid(row=1, padx=10, pady=10, sticky=tkinter.W)

        tkinter.Label(files_frame, text="Current run directory:")\
                .grid(row=0, column=0, sticky=tkinter.E)
        run_dir_entry = tkinter.Entry(files_frame)\
                .grid(row=0, column=1, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame, text="Open...",
                command = lambda: self.open_dir("current_run_dir"))\
                .grid(row=0, column=2, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame,
                text="Delete current run data", width=20)\
                .grid(row=0, column=3, sticky=tkinter.W)

        tkinter.Label(files_frame, text="HDF file:")\
                .grid(row=1, column=0, sticky=tkinter.E)
        HDF_file_entry = tkinter.Entry(files_frame)\
                .grid(row=1, column=1, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame, text="Open...",
                command = lambda: self.open_file("HDF_fname"))\
                .grid(row=1, column=2, sticky=tkinter.W)
        run_dir_button = tkinter.Button(files_frame,
                text="Archive current run...", width=20)\
                .grid(row=1, column=3, sticky=tkinter.W)

        tkinter.Label(files_frame, text="Run name:")\
                .grid(row=2, column=0, sticky=tkinter.E)
        run_name_entry = tkinter.Entry(files_frame,
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
