from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import deque
from typing import Any, Deque, Dict, List, Set, Tuple, Union

import numpy as np
import numpy.typing as npt

from config import DeviceConfig


def restart_device(device: Device, time_offset: float) -> Device:
    logging.info(f"{device.name}: restart")
    device.active.clear()
    device.join()

    data_queue = device.data_queue
    events_queue = device.events_queue
    plots_queue = device.config["plots_queue"]

    device = Device(device.config)
    device.setup_connection(time_offset)

    device.data_queue = data_queue
    device.events_queue = events_queue
    device.config["plots_queue"] = plots_queue

    device.start()

    logging.info(f"{device.name}: restarted")

    return device


class Device(threading.Thread):
    def __init__(self, config: DeviceConfig):
        threading.Thread.__init__(self)
        self.config = config

        # whether the thread is running
        self.control_started = False
        self.active = threading.Event()
        self.active.clear()

        # whether the connection to the device was successful
        self.operational = False
        self.error_message = ""

        # for commands sent to the device
        self.commands: List[str] = []
        self.last_event: List[Tuple[float, str, Any]] = []
        self.monitoring_commands: Set[str] = set()
        self.sequencer_commands: List[Tuple[int, str]] = []
        self.networking_commands: List[Tuple[int, str]] = []

        # for warnings about device abnormal condition
        self.warnings: List[Tuple[float, Dict[str, str]]] = []

        # the data and events queues
        self.time_last_read = 0.0
        self.data_queue: Deque[
            Union[List[float], List[Tuple[npt.NDArray, List[str]]]]
        ] = deque()
        self.config["plots_queue"] = deque(maxlen=self.config["plots_queue_maxlen"])
        self.events_queue: Deque[Tuple[float, str, Any]] = deque()
        self.monitoring_events_queue: Deque[Tuple[float, str, Any]] = deque()
        self.sequencer_events_queue: Deque[Tuple[int, int, str, Any]] = deque()
        # use a dictionary for the networking queue to allow use of .get() to
        # allow for unique ids if multiple network clients are connected
        self.networking_events_queue: Dict[int, Any] = {}

        # the variable for counting the number of NaN returns
        self.nan_count = 0

        # for counting the number of sequential NaN returns
        self.sequential_nan_count = 0
        self.previous_data = True

        self.col_names_list: List[str] = []

    def setup_connection(self, time_offset: float):
        self.time_offset = time_offset

        # get the parameters that are to be passed to the driver constructor
        self.constr_params = [self.time_offset]
        for cp in self.config["constr_params"]:
            self.constr_params.append(self.config["control_params"][cp]["value"])

        # for meta devices, include a reference to the parent
        if self.config["meta_device"]:
            self.constr_params = [self.config["parent"]] + self.constr_params

        # check we are allowed to instantiate the driver before the main loop starts
        if not self.config["double_connect_dev"]:
            self.operational = True
            return

        # verify the device responds correctly
        with self.config["driver_class"](*self.constr_params) as dev:
            if not isinstance(dev.verification_string, str):
                self.operational = False
                self.error_message = "verification_string is not of type str"
                return
            if (
                dev.verification_string.strip()
                == self.config["correct_response"].strip()
            ):
                self.operational = True
            else:
                self.error_message = (
                    "verification string warning: "
                    + dev.verification_string
                    + "!="
                    + self.config["correct_response"].strip()
                )
                logging.warning(self.error_message)
                self.operational = False
                return

            # get parameters and attributes, if any, from the driver
            self.config["shape"] = dev.shape
            self.config["dtype"] = dev.dtype
            for attr_name, attr_val in dev.new_attributes:
                self.config["attributes"][attr_name] = attr_val

    def change_plots_queue_maxlen(self, maxlen: int):
        # sanity check
        try:
            self.config["plots_queue_maxlen"] = int(maxlen)
        except ValueError as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            return

        # create a new deque with a different maxlen
        self.config["plots_queue"] = deque(maxlen=self.config["plots_queue_maxlen"])

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
            logging.info(f"Start device {self.config['name']}")

        # main control loop
        try:
            with self.config["driver_class"](*self.constr_params) as device:
                while self.active.is_set():
                    # get and sanity check loop delay
                    try:
                        dt = float(self.config["control_params"]["dt"]["value"])
                        if dt < 0.002:
                            logging.warning("Device dt too small.")
                            raise ValueError
                    except ValueError as e:
                        logging.warning(e)
                        logging.info(traceback.format_exc())
                        dt = 0.1

                    # 1 kHz loop delay
                    time.sleep(1e-3)

                    # level 1: check device is enabled for sending commands
                    if self.config["control_params"]["enabled"]["value"] < 1:
                        continue

                    # check device for abnormal conditions
                    warning = device.GetWarnings()
                    if warning:
                        self.warnings += warning

                    # send control commands, if any, to the device, and record return
                    # values
                    for c in self.commands:
                        try:
                            ret_val = eval("device." + c.strip())
                        except Exception as err:
                            logging.warning(err)
                            logging.warning(traceback.format_exc())
                            ret_val = str(err)
                        if (c == "ReadValue()") and ret_val:
                            self.data_queue.append(ret_val)
                            self.config["plots_queue"].append(ret_val)
                        ret_val = "None" if not ret_val else ret_val
                        self.last_event = [time.time() - self.time_offset, c, ret_val]
                        self.events_queue.append(self.last_event)
                    self.commands = []

                    # send sequencer commands, if any, to the device, and record return
                    # values
                    for id0, c in self.sequencer_commands:
                        try:
                            ret_val = eval("device." + c.strip())
                        except Exception as e:
                            logging.warning(e)
                            logging.warning(traceback.format_exc())
                            ret_val = None
                        if (c == "ReadValue()") and ret_val:
                            self.data_queue.append(ret_val)
                            self.config["plots_queue"].append(ret_val)
                        self.sequencer_events_queue.append(
                            [id0, time.time_ns(), c, ret_val]
                        )
                    self.sequencer_commands = []

                    # send monitoring commands, if any, to the device, and record return
                    # values
                    # copy set and clear before iterating to prevent an error when
                    # adding to monitoring commands while iterating over them
                    mc = self.monitoring_commands.copy()
                    self.monitoring_commands.clear()
                    for c in mc:
                        try:
                            ret_val = eval("device." + c.strip())
                        except Exception as err:
                            logging.warning(err)
                            logging.warning(traceback.format_exc())
                            ret_val = str(err)
                        ret_val = "None" if not ret_val else ret_val
                        self.monitoring_events_queue.append(
                            [time.time() - self.time_offset, c, ret_val]
                        )

                    # send networking commands, if any, to the device, and record return
                    # values
                    for uid, cmd in self.networking_commands:
                        try:
                            ret_val = eval("device." + cmd.strip())
                        except Exception as err:
                            logging.warning(err)
                            logging.warning(traceback.format_exc())
                            ret_val = str(err)
                        self.networking_events_queue[uid] = ret_val
                    self.networking_commands = []

                    # level 2: check device is enabled for regular ReadValue
                    if self.config["control_params"]["enabled"]["value"] < 2:
                        continue

                    # record numerical values
                    if time.time() - self.time_last_read >= dt:
                        last_data = device.ReadValue()
                        self.time_last_read = time.time()

                        # keep track of the number of (sequential and total) NaN returns
                        if isinstance(last_data, float):
                            if np.isnan(last_data):
                                self.nan_count += 1
                                if isinstance(self.previous_data, float) and np.isnan(
                                    self.previous_data
                                ):
                                    self.sequential_nan_count += 1
                            else:
                                self.sequential_nan_count = 0
                        else:
                            self.sequential_nan_count = 0
                        self.previous_data = last_data

                        if last_data and not isinstance(last_data, float):
                            self.data_queue.append(last_data)
                            self.config["plots_queue"].append(last_data)

                        # issue a warning if there's been too many sequential NaN
                        # returns
                        try:
                            max_NaN_count = int(self.config["max_NaN_count"])
                        except TypeError:
                            logging.info(traceback.format_exc())
                            max_NaN_count = 10
                        if self.sequential_nan_count > max_NaN_count:
                            warning_dict = {
                                "message": "excess sequential NaN returns: "
                                + str(self.sequential_nan_count),
                                "sequential_NaN_count_exceeded": 1,
                            }
                            self.warnings.append([time.time(), warning_dict])

        # report any exception that has occurred in the run() function
        except Exception as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            err_msg = traceback.format_exc()
            warning_dict = {
                "message": "exception in " + self.config["name"] + ": " + err_msg,
                "exception": 1,
            }
            self.warnings.append([time.time(), warning_dict])
