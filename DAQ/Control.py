import tkinter as tk
import threading
from collections import deque
import logging
import time
import h5py
from influxdb import InfluxDBClient

class Device(threading.Thread):
    def __init__(self, config):
        self.config = config

        # whether the thread is running
        self.control_started = False
        self.active = threading.Event()
        self.active.clear()

        # whether the connection to the device was successful
        self.operational = False

        # for sending commands to the device
        self.commands = []

        # for warnings about device abnormal condition
        self.warnings = []

        # the data and events queues
        self.data_queue = deque()
        self.events_queue = deque()

        # the variable for counting the number of NaN returns
        self.nan_count = tk.StringVar()
        self.nan_count.set(0)

    def setup_connection(self, time_offset):
        threading.Thread.__init__(self)
        self.time_offset = time_offset

        # get the parameters that are to be passed to the driver constructor
        self.constr_params = [self.time_offset]
        for cp in self.config["constr_params"]:
            cp_obj = self.config["controls"][cp]
            if cp_obj["type"] == "ControlsRow":
                self.constr_params.append( cp_obj["control_values"] )
            elif cp_obj["type"] == "ControlsTable":
                self.constr_params.append( cp_obj["column_values"] )
            else:
                self.constr_params.append( self.config["controls"][cp]["var"].get() )

        with self.config["driver"](*self.constr_params) as dev:
            # verify the device responds correctly
            if not isinstance(dev.verification_string, str):
                self.operational = False
                return
            if dev.verification_string.strip() == self.config["correct_response"].strip():
                self.operational = True
            else:
                logging.warning("verification string warning:" + dev.verification_string + "!=" + self.config["correct_response"].strip())
                self.operational = False
                return

            # get parameters and attributes, if any, from the driver
            self.config["shape"] = dev.shape
            self.config["dtype"] = dev.dtype
            for attr_name, attr_val in dev.new_attributes:
                self.config["attributes"][attr_name] = attr_val

    def clear_queues(self):
        self.data_queue.clear()
        self.events_queue.clear()

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return
        else:
            self.active.set()
            self.control_started = True

        # main control loop
        with self.config["driver"](*self.constr_params) as device:
            while self.active.is_set():
                # loop delay
                try:
                    time.sleep(float(self.config["controls"]["dt"]["var"].get()))
                except ValueError:
                    time.sleep(1)

                # check device is enabled
                if not self.config["controls"]["enabled"]["var"].get():
                    continue

                # check device for abnormal conditions
                warning = device.GetWarnings()
                if warning:
                    self.warnings += warning

                # record numerical values
                last_data = device.ReadValue()
                # keep track of the number of NaN returns
                if isinstance(last_data, float):
                    if np.isnan(last_data):
                        self.nan_count.set( int(self.nan_count.get()) + 1)
                elif len(last_data) > 0:
                    self.data_queue.append(last_data)


                # send control commands, if any, to the device, and record return values
                for c in self.commands:
                    try:
                        ret_val = eval("device." + c.strip())
                    except (ValueError, AttributeError, SyntaxError, TypeError) as err:
                        ret_val = str(err)
                    ret_val = "None" if not ret_val else ret_val
                    last_event = [ time.time()-self.time_offset, c, ret_val ]
                    self.events_queue.append(last_event)
                self.commands = []

class Monitoring(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

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
                # check device running
                if not dev.control_started:
                    continue

                # check device for abnormal conditions
                if len(dev.warnings) != 0:
                    logging.warning("Abnormal condition in " + str(dev_name))
                    for warning in dev.warnings:
                        logging.warning(str(warning))
                        self.push_warnings_to_influxdb(dev_name, warning)
                        self.parent.monitoring.last_warning.set(str(warning))
                    dev.warnings = []

                # find out and display the data queue length
                dev.qsize.set(len(dev.data_queue))

                # get the last event (if any) of the device
                self.display_last_event(dev)

                # get the last row of data in the HDF dataset
                data = self.get_last_row_of_data(dev)
                if not isinstance(data, type(None)):
                    # format display the data in a tkinter variable
                    formatted_data = [np.format_float_scientific(x, precision=3) for x in data]
                    dev.last_data.set("\n".join(formatted_data))

                    # write slow data to InfluxDB
                    self.write_to_influxdb(dev, data)

                # if writing to HDF is disabled, empty the queues
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
                    dev.events_queue.clear()
                    dev.data_queue.clear()

            # loop delay
            try:
                time.sleep(float(self.parent.config["monitoring_dt"].get()))
            except ValueError:
                time.sleep(1)

    def write_to_influxdb(self, dev, data):
        if self.parent.config["influxdb"]["enabled"].get().strip() == "False":
            return
        if not dev.config["single_dataset"]:
            return
        fields = {}
        for col,val in zip(dev.col_names_list[1:], data[1:]):
            if not np.isnan(val):
                fields[col] = val
        if len(fields) > 0:
            json_body = [
                    {
                        "measurement": dev.config["name"],
                        "tags": { "run_name": self.parent.run_name, },
                        "time": int(1000 * (data[0] + self.parent.config["time_offset"])),
                        "fields": fields,
                        }
                    ]
            self.influxdb_client.write_points(json_body, time_precision='ms')

    def get_last_row_of_data(self, dev):
        # check device enabled
        if not dev.config["controls"]["enabled"]["var"].get():
            return

        # if HDF writing enabled for this device, get data from the HDF file
        if dev.config["controls"]["HDF_enabled"]["var"].get():
            with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
                grp = f[self.parent.run_name + "/" + dev.config["path"]]
                if dev.config["single_dataset"]:
                    dset = grp[dev.config["name"]]
                    if dset.shape[0] == 0:
                        return None
                    else:
                        data = dset[-1]
                else:
                    rec_num = len(grp) - 1
                    if rec_num < 3:
                        return None
                    try:
                        data = grp[dev.config["name"] + "_" + str(rec_num)][-1]
                    except KeyError:
                        logging.warning("dset doesn't exist: num = " + str(rec_num))
                        return None
                return data

        # if HDF writing not enabled for this device, get data from the events_queue
        else:
            try:
                return dev.data_queue.pop()
            except IndexError:
                return None

    def display_last_event(self, dev):
        # check device enabled
        if not dev.config["controls"]["enabled"]["var"].get():
            return

        # if HDF writing enabled for this device, get events from the HDF file
        if dev.config["controls"]["HDF_enabled"]["var"].get():
            with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
                grp = f[self.parent.run_name + "/" + dev.config["path"]]
                events_dset = grp[dev.config["name"] + "_events"]
                if events_dset.shape[0] == 0:
                    dev.last_event.set("(no event)")
                else:
                    dev.last_event.set(str(events_dset[-1]))

        # if HDF writing not enabled for this device, get events from the events_queue
        else:
            try:
                dev.last_event.set(str(dev.events_queue.pop()))
            except IndexError:
                return

    def push_warnings_to_influxdb(self, dev_name, warning):
        json_body = [
                {
                    "measurement": "warnings",
                    "tags": {
                        "run_name": self.parent.run_name,
                        "dev_name": dev_name,
                        },
                    "time": int(1000 * warning[0]),
                    "fields": warning[1],
                    }
                ]
        self.influxdb_client.write_points(json_body, time_precision='ms')

class HDF_writer(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # configuration parameters
        self.filename = self.parent.config["files"]["hdf_fname"].get()
        self.parent.run_name = str(int(time.time())) + " " + self.parent.config["general"]["run_name"].get()

        # create/open HDF file, groups, and datasets
        with h5py.File(self.filename, 'a') as f:
            root = f.create_group(self.parent.run_name)
            root.attrs["time_offset"] = self.parent.config["time_offset"]
            for dev_name, dev in self.parent.devices.items():
                # check device is enabled
                if not dev.config["controls"]["enabled"]["var"].get():
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
                    continue

                grp = root.require_group(dev.config["path"])

                # create dataset for data if only one is needed
                # (fast devices create a new dataset for each acquisition)
                if dev.config["single_dataset"]:
                    dset = grp.create_dataset(
                            dev.config["name"],
                            (0, *dev.config["shape"]),
                            maxshape=(None, *dev.config["shape"]),
                            dtype=dev.config["dtype"]
                        )
                    for attr_name, attr in dev.config["attributes"].items():
                        dset.attrs[attr_name] = attr
                else:
                    for attr_name, attr in dev.config["attributes"].items():
                        grp.attrs[attr_name] = attr

                # create dataset for events
                events_dset = grp.create_dataset(dev.config["name"]+"_events", (0,3),
                        maxshape=(None,3), dtype=h5py.special_dtype(vlen=str))

        self.active.set()

    def run(self):
        while self.active.is_set():
            # empty queues to HDF
            try:
                with h5py.File(self.filename, 'a') as fname:
                    self.write_all_queues_to_HDF(fname)
            except OSError as err:
                logging.warning("HDF_writer error: {0}".format(err))

            # loop delay
            try:
                time.sleep(float(self.parent.config["general"]["hdf_loop_delay"].get()))
            except ValueError:
                time.sleep(0.1)

        # make sure everything is written to HDF when the thread terminates
        try:
            with h5py.File(self.filename, 'a') as fname:
                self.write_all_queues_to_HDF(fname)
        except OSError as err:
            logging.warning("HDF_writer error: ", err)

    def write_all_queues_to_HDF(self, fname):
            root = fname.require_group(self.parent.run_name)
            for dev_name, dev in self.parent.devices.items():
                # check device has had control started
                if not dev.control_started:
                    continue

                # check writing to HDF is enabled for this device
                if not dev.config["controls"]["HDF_enabled"]["var"].get():
                    continue

                # get events, if any, and write them to HDF
                events = self.get_data(dev.events_queue)
                if len(events) != 0:
                    grp = root.require_group(dev.config["path"])
                    events_dset = grp[dev.config["name"] + "_events"]
                    events_dset.resize(events_dset.shape[0]+len(events), axis=0)
                    events_dset[-len(events):,:] = events

                # get data
                data = self.get_data(dev.data_queue)
                if len(data) == 0:
                    continue

                grp = root.require_group(dev.config["path"])

                # if writing all data from a single device to one dataset
                if dev.config["single_dataset"]:
                    dset = grp[dev.config["name"]]
                    # check if one queue entry has multiple rows
                    if np.ndim(data) == 3:
                        arr_len = np.shape(data)[1]
                        list_len = len(data)
                        dset.resize(dset.shape[0]+list_len*arr_len, axis=0)
                        # iterate over queue entries with multiple rows and append
                        for idx, d in enumerate(data):
                            idx_start = -arr_len*(list_len-idx)
                            idx_stop = -arr_len*(list_len-(idx+1))
                            if idx_stop == 0:
                                dset[idx_start:] = d
                            else:
                                dset[idx_start:idx_stop] = d
                    else:
                        dset.resize(dset.shape[0]+len(data), axis=0)
                        dset[-len(data):] = data

                # if writing each acquisition record to a separate dataset
                else:
                    for record, all_attrs in data:
                        for waveforms, attrs in zip(record, all_attrs):
                            # data
                            dset = grp.create_dataset(
                                    name        = dev.config["name"] + "_" + str(len(grp)),
                                    data        = waveforms.T,
                                    dtype       = dev.config["dtype"],
                                    compression = None
                                )
                            # metadata
                            for key, val in attrs.items():
                                dset.attrs[key] = val

    def get_data(self, fifo):
        data = []
        while True:
            try:
                data.append( fifo.popleft() )
            except IndexError:
                break
        return data
