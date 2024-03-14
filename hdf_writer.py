import datetime
import logging
import subprocess
import threading
import time
import traceback
from dataclasses import fields
from pathlib import Path
from typing import Deque

import h5py
import numpy as np

from device import get_data_from_fast_device_dataclass
from protocols import CentrexGUIProtocol


class HDF_writer(threading.Thread):
    def __init__(self, parent: CentrexGUIProtocol, clear: bool = False):
        threading.Thread.__init__(self)
        self.parent = parent
        self.active = threading.Event()
        self.hdf_error = threading.Event()

        # configuration parameters
        self.filename: Path = (
            self.parent.config.files.hdf_dir / self.parent.config.files.hdf_fname
        )
        current_time = datetime.datetime.utcnow().astimezone().replace(microsecond=0)
        self.parent.run_name = (
            current_time.isoformat() + " " + str(self.parent.config.general.run_name)
        )

        if clear:
            if self.filename.is_file():
                ret = subprocess.call(f"h5clear -s {self.filename}", shell=True)
                if ret != 0:
                    logging.error("HDF_writer: h5clear error")

        # time since last write
        self.time_last_write = datetime.datetime.now().replace(microsecond=0)

        # create/open HDF file, groups, and datasets
        try:
            with h5py.File(self.filename, "a", libver="latest") as f:
                root = f.create_group(self.parent.run_name)

                # write run attributes
                root.attrs.time_offset = self.parent.config.time_offset
                for key, val in self.parent.config.run_attributes.items():
                    root.attrs[key] = val

                for dev_name, dev in self.parent.devices.items():
                    # check device is enabled
                    if dev.config.control_params["enabled"].value < 1:
                        continue

                    grp = root.require_group(dev.config.path)

                    # create dataset for data if only one is needed
                    # (fast devices create a new dataset for each acquisition)
                    if dev.config.slow_data:
                        if isinstance(dev.config.dtype, (list, tuple, np.ndarray)):
                            dtype = np.dtype(
                                [
                                    (name.strip(), dtype)
                                    for name, dtype in zip(
                                        dev.config.attributes.column_names,
                                        dev.config.dtype,
                                    )
                                ]
                            )
                        else:
                            dtype = np.dtype(
                                [
                                    (name.strip(), dev.config.dtype)
                                    for name in dev.config.attributes.column_names
                                ]
                            )
                        dset = grp.create_dataset(
                            dev.config.name, (0,), maxshape=(None,), dtype=dtype
                        )
                        for f in fields(dev.config.attributes):
                            dset.attrs[f.name] = getattr(dev.config.attributes, f.name)
                    else:
                        for f in fields(dev.config.attributes):
                            grp.attrs[f.name] = getattr(dev.config.attributes, f.name)

                    # create dataset for events
                    grp.create_dataset(
                        f"{dev.config.name}_events",
                        (0, 3),
                        maxshape=(None, 3),
                        dtype=h5py.special_dtype(vlen=str),
                    )

        except Exception as e:
            self.hdf_error.set()
            logging.error(f"HDF_witer error: {e}")

    def run(self):
        self.active.set()
        if self.hdf_error.is_set():
            return
        # file.swmr_mode = True
        time_last_flush = time.time()
        while self.active.is_set():
            # empty queues to HDF
            try:
                with h5py.File(self.filename, "a", libver="latest") as file:
                    self.write_all_queues_to_HDF(file)
                    # update the last write time
                    self.time_last_write = datetime.datetime.now().replace(
                        microsecond=0
                    )
                    if (
                        time.time() - time_last_flush
                        >= self.parent.config.general.hdf_flush_dt
                    ):
                        file.flush()
            except OSError as err:
                if (
                    str(err)
                    == "Unable to open file (file is already open in read-only mode)"
                ):
                    continue
                else:
                    logging.warning(f"HDF_writer error: {err}")
                    logging.warning(traceback.format_exc())

            # loop delay
            time.sleep(self.parent.config.general.hdf_loop_delay)

        # make sure everything is written to HDF when the thread terminates
        try:
            with h5py.File(self.filename, "a", libver="latest") as file:
                self.write_all_queues_to_HDF(file)
                file.flush()
        except OSError as err:
            logging.warning("HDF_writer error: ", err)
            logging.warning(traceback.format_exc())
        logging.info("HDF_writer: stopped")

    def write_all_queues_to_HDF(self, file: h5py.File):
        root = file[self.parent.run_name]
        for dev_name, dev in self.parent.devices.items():
            # check device has had control started
            if not dev.control_started:
                continue

            # check writing to HDF is enabled for this device
            if not int(dev.config.control_params["HDF_enabled"].value):
                continue

            # get events, if any, and write them to HDF
            events = self.get_data(dev.events_queue)
            if len(events) != 0:
                # make sure all are strings
                events = [[str(v) for v in e] for e in events]
                grp = root[dev.config.path]
                events_dset = grp[dev.config.name + "_events"]
                events_dset.resize(events_dset.shape[0] + len(events), axis=0)
                events_dset[-len(events) :, :] = events

            # get data
            data = self.get_data(dev.data_queue)
            if len(data) == 0:
                continue

            grp = root[dev.config.path]

            # if writing all data from a single device to one dataset
            if dev.config.slow_data:
                dset = grp[dev.config.name]
                # check if one queue entry has multiple rows
                if np.shape(data)[0] >= 2:
                    list_len = len(data)
                    dset.resize(dset.shape[0] + list_len, axis=0)
                    # iterate over queue entries with multiple rows and append
                    for idx, d in enumerate(data):
                        idx_start = -list_len + idx
                        idx_stop = -list_len + idx + 1
                        try:
                            if idx_stop == 0:
                                dset[idx_start:] = get_data_from_fast_device_dataclass(
                                    d, dset.dtype
                                )
                            else:
                                dset[idx_start:idx_stop] = (
                                    get_data_from_fast_device_dataclass(d, dset.dtype)
                                )
                        except Exception as err:
                            logging.error(
                                f"Error in write_all_queues_to_HDF: {dev_name};"
                                f" {str(err)}"
                            )
                else:
                    dset.resize(dset.shape[0] + len(data), axis=0)
                    try:
                        data = get_data_from_fast_device_dataclass(data[0], dset.dtype)
                        dset[-len(data) :] = data
                    except (ValueError, TypeError) as err:
                        logging.error(
                            "Error in write_all_queues_to_HDF(): "
                            + f"{dev_name}; "
                            + str(err)
                        )
                        logging.error(traceback.format_exc())

            # if writing each acquisition record to a separate dataset
            else:
                # parse and write the data
                for dat in data:
                    for d, attrs in zip(dat.data, dat.attrs):
                        # data
                        dset = grp.create_dataset(
                            name=f"{dev.config.name}_{str(len(grp))}",
                            data=d.T,
                            dtype=dev.config.dtype,
                            compression=None,
                        )
                        # metadata
                        for key, val in attrs.items():
                            dset.attrs[key] = val

    def get_data(self, fifo: Deque):
        data = []
        while len(fifo) > 0:
            data.append(fifo.popleft())
        return data
