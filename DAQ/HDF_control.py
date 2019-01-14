import h5py
import time
import threading
import logging
import numpy as np

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
                if dev.config["controls"]["enabled"]["var"].get():
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
