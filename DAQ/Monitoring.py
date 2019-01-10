import tkinter as tk
import threading
import time
import sys
import queue
import h5py
from influxdb import InfluxDBClient
import numpy as np
from decimal import Decimal

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
        self.monitoring = Monitoring(self.parent)

        # monitoring controls frame
        self.ctrls_f = tk.Frame(self.frame)
        self.ctrls_f.grid(row=0, column=0, padx=10, pady=10)

        # general monitoring controls
        self.gen_f = tk.LabelFrame(self.ctrls_f, text="General")
        self.gen_f.grid(row=0, column=0, padx=10, pady=10)
        tk.Label(self.gen_f, text="Loop delay [s]:").grid(row=0, column=0)
        tk.Entry(self.gen_f, textvariable=self.monitoring.dt_var).grid(row=0, column=1)

        # InfluxDB controls
        conf = self.parent.config["influxdb"]
        self.db_f = tk.LabelFrame(self.ctrls_f, text="InfluxDB")
        self.db_f.grid(row=0, column=1, padx=10, pady=10)
        tk.Label(self.db_f, text="Host IP").grid(row=0, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["host"]).grid(row=0, column=1, sticky='w')
        tk.Label(self.db_f, text="Port").grid(row=1, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["port"]).grid(row=1, column=1, sticky='w')
        tk.Label(self.db_f, text="Username").grid(row=2, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["username"]).grid(row=2, column=1, sticky='w')
        tk.Label(self.db_f, text="Pasword").grid(row=3, column=0, sticky='e')
        tk.Entry(self.db_f, textvariable=conf["password"]).grid(row=3, column=1, sticky='w')


    def place_device_specific_items(self):
        # frame for device data
        self.dev_f = tk.LabelFrame(self.frame, text="Devices")
        self.dev_f.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # device-specific text
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            fd = tk.LabelFrame(self.dev_f, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["monitoring_row"], column=dev.config["monitoring_column"])

            # length of the data queue
            dev.qsize = tk.StringVar()
            dev.qsize.set(0)
            tk.Label(fd, text="Queue length:").grid(row=0, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.qsize).grid(row=0, column=1, sticky='nw')

            # NaN count
            tk.Label(fd, text="NaN count:").grid(row=1, column=0, sticky='ne')
            tk.Label(fd, textvariable=dev.nan_count).grid(row=1, column=1, sticky='nw')

            # column names
            dev.col_names_list = dev.config["attributes"]["column_names"].split(',')
            dev.col_names_list = [x.strip() for x in dev.col_names_list]
            dev.column_names = tk.StringVar()
            dev.column_names.set("\n".join(dev.col_names_list))
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
            dev.last_event = tk.StringVar()
            tk.Message(fd, textvariable=dev.last_event, anchor='nw', width=150)\
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
        self.monitoring.active.set()
        self.monitoring.start()

    def stop_monitoring(self):
        if self.monitoring.active.is_set():
            self.monitoring.active.clear()

class Monitoring(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # variables
        self.dt_var = tk.StringVar()
        self.dt_var.set("1")

        # connect to InfluxDB
        conf = self.parent.config["influxdb"]
        self.influxdb_client = InfluxDBClient(
                host     = conf["host"].get(),
                port     = conf["port"].get(),
                username = conf["username"].get(),
                password = conf["password"].get(),
            )
        self.influxdb_client.switch_database(self.parent.config["influxdb"]["database"].get())

    def run(self):
        while self.active.is_set():
            for dev_name, dev in self.parent.devices.items():
                if dev.config["controls"]["enabled"]["var"].get():
                    with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
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
                        formatted_data = [np.format_float_scientific(x, precision=3) for x in data]
                    else:
                        if len(data) > 1:
                            formatted_data = [str(x) for x in data[0][-1][:,-1]]
                        else:
                            formatted_data = str(data)
                    dev.last_data.set("\n".join(formatted_data))

                    # find out and display the data queue length
                    dev.qsize.set(len(dev.data_queue))

                    # write slow data to InfluxDB
                    if not dev.config["single_dataset"]:
                        continue
                    if self.parent.config["influxdb"]["enabled"].get().strip() == "False":
                        print ("aa")
                        continue
                    fields = {}
                    for col,val in zip(dev.col_names_list[1:], data[1:]):
                        if not np.isnan(val):
                            fields[col] = val
                    if len(fields) > 0:
                        json_body = [
                                {
                                    "measurement": dev_name,
                                    "tags": { "run_name": self.parent.run_name, },
                                    "time": int(1000 * (data[0] + self.parent.config["time_offset"])),
                                    "fields": fields,
                                    }
                                ]
                        self.influxdb_client.write_points(json_body, time_precision='ms')

            # loop delay
            try:
                time.sleep(float(self.dt_var.get()))
            except ValueError:
                time.sleep(1)
