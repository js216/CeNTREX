import tkinter as tk
import threading
import time
import sys
import queue

class MonitoringGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all MonitoringGUI elements
        mgf = tk.Frame(self.parent.nb)
        self.parent.nb.add(mgf, text="Monitoring")

        # frame for device data
        dev_f = tk.LabelFrame(mgf, text="devices")
        dev_f.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # device-specific text
        for i, (dev_name, dev) in enumerate(self.parent.devices.items()):
            fd = tk.LabelFrame(dev_f, text=dev.config["label"])
            fd.grid(padx=10, pady=10, sticky="nsew",
                    row=dev.config["row"], column=dev.config["column"])

            # column names
            col_names = dev.config["attributes"]["column_names"].split(',')
            col_names = [x.strip() for x in col_names]
            dev.column_names = tk.StringVar()
            dev.column_names.set("\n".join(col_names))
            tk.Message(fd, textvariable=dev.column_names, anchor='ne', justify="right", width=350)\
                    .grid(row=0, column=0, sticky='nsew')

            # data
            dev.last_data = tk.StringVar()
            tk.Message(fd, textvariable=dev.last_data, anchor='nw', width=350)\
                    .grid(row=0, column=1, sticky='nsew')

            # units
            units = dev.config["attributes"]["units"].split(',')
            units = [x.strip() for x in units]
            dev.units = tk.StringVar()
            dev.units.set("\n".join(units))
            tk.Message(fd, textvariable=dev.units, anchor='nw', width=350)\
                    .grid(row=0, column=2, sticky='nsew')

        # monitoring controls
        self.ctrls_f = tk.Frame(mgf)
        self.ctrls_f.grid(row=0, column=0, padx=10, pady=10)

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
                    # look at the element at the beginning of the data queue
                    try:
                        data = dev.data.queue[-1]
                    except IndexError:
                        continue

                    # format display the data in a tkinter variable
                    formatted_data = ["{0:.3f}".format(x) for x in data]
                    dev.last_data.set("\n".join(formatted_data))

            # loop delay
            try:
                time.sleep(float(self.dt_var.get()))
            except ValueError:
                time.sleep(1)
