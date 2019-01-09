import tkinter as tk
import threading
import time
import sys
import queue
import h5py

class MonitoringGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all MonitoringGUI elements
        self.frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.frame, text="Monitoring")

        self.place_device_specific_items()

        # monitoring controls
        self.ctrls_f = tk.Frame(self.frame)
        self.ctrls_f.grid(row=0, column=0, padx=10, pady=10)

    def place_device_specific_items(self):
        # frame for device data
        self.dev_f = tk.LabelFrame(self.frame, text="Devices")
        self.dev_f.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # device-specific text
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            fd = tk.LabelFrame(self.dev_f, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"])

            # length of the data queue
            dev.qsize = tk.StringVar()
            dev.qsize.set(0)
            tk.Label(fd, text="Queue length:").grid(row=0, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.qsize).grid(row=0, column=1, sticky='nw')

            # NaN count
            tk.Label(fd, text="NaN count:").grid(row=1, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.nan_count).grid(row=1, column=1, sticky='nw')

            # column names
            col_names = dev.config["attributes"]["column_names"].split(',')
            col_names = [x.strip() for x in col_names]
            dev.column_names = tk.StringVar()
            dev.column_names.set("\n".join(col_names))
            tk.Message(fd, textvariable=dev.column_names, anchor='ne', justify="right", width=350)\
                    .grid(row=2, column=0, sticky='nsew')

            # data
            dev.last_data = tk.StringVar()
            tk.Message(fd, textvariable=dev.last_data, anchor='nw', width=350)\
                    .grid(row=2, column=1, sticky='nsew')

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units = tk.StringVar()
            dev.units.set("\n".join(units))
            tk.Message(fd, textvariable=dev.units, anchor='nw', width=350)\
                    .grid(row=2, column=2, sticky='nsew')

            # latest event / command sent to device & its return value
            tk.Label(fd, text="Last event:").grid(row=3, column=0, sticky='ne')
            tk.Message(fd, textvariable=dev.last_event, anchor='nw', width=100)\
                    .grid(row=3, column=1, columnspan=2, sticky='nw')

    def refresh_column_names_and_units(self):
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            # column names
            col_names = dev.config["attributes"]["column_names"].split(',')
            col_names = [x.strip() for x in col_names]
            dev.column_names.set("\n".join(col_names))

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units.set("\n".join(units))

    def start_monitoring(self):
        self.monitoring = Monitoring(self.parent)
        self.monitoring.active.set()

        tk.Label(self.ctrls_f, text="Loop delay [s]:").grid(row=0, column=0)
        tk.Entry(self.ctrls_f, textvariable=self.monitoring.dt_var).grid(row=0, column=1)

        self.monitoring.start()

    def stop_monitoring(self):
        if self.monitoring.active.is_set():
            self.monitoring.active.clear()

class Monitoring(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()
        self.dt_var = tk.StringVar()
        self.dt_var.set("1")

    def run(self):
        while self.active.is_set():
            for dev_name, dev in self.parent.devices.items():
                if dev.config["controls"]["enabled"]["var"].get():
                    with h5py.File(self.parent.config["hdf_fname"].get(), 'r') as f:
                        grp = f[self.parent.run_name + "/" + dev.config["path"]]

                        # look at the last row of data in the HDF dataset
                        if dev.config["single_dataset"]:
                            dset = grp[dev.config["name"]]
                            if dset.shape[0] == 0:
                                continue
                            else:
                                data = dset[-1]
                        else:
                            rec_num = len(grp) - 1
                            if rec_num < 1:
                                continue
                            data = grp[dev.config["name"] + "_" + str(rec_num)][-1]

                        # look at last event (if any) of the device
                        events_dset = grp[dev.config["name"] + "_events"]
                        if events_dset.shape[0] == 0:
                            dev.last_event.set("(no event)")
                        else:
                            dev.last_event.set(str(events_dset[-1]))

                    # format display the data in a tkinter variable
                    if len(dev.config["shape"]) == 1:
                        formatted_data = ["{0:.3f}".format(x) for x in data]
                    else:
                        formatted_data = [str(x) for x in data[0][-1][:,-1]]
                    dev.last_data.set("\n".join(formatted_data))

                    ## find out and display the data queue length
                    dev.qsize.set(len(dev.data_queue))

            # loop delay
            try:
                time.sleep(float(self.dt_var.get()))
            except ValueError:
                time.sleep(1)