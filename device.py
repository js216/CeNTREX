from __future__ import annotations

import datetime
import logging
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, fields
from enum import Enum, auto
from typing import Any, Union

import numpy as np
import numpy.typing as npt

from config import DeviceConfig


class WarningLevel(Enum):
    WARNING = auto()
    ERROR = auto()


@dataclass
class DeviceWarning:
    time: float
    message: str
    level: WarningLevel = WarningLevel.WARNING

    def to_text(self) -> str:
        ts_str = (
            datetime.datetime.fromtimestamp(self.time)
            .replace(microsecond=0)
            .isoformat()
        )
        return f"{ts_str} - {self.level.name} : {self.message}"


@dataclass
class DeviceData:
    time: float


def get_values_from_slow_device_dataclass(data: object) -> list[Any]:
    return [
        getattr(data, f.name)
        for f in fields(data)
        if f.name not in ["dtype", "shape", "units", "attrs"]
    ]


def get_data_from_fast_device_dataclass(data: object, dtype) -> npt.NDArray:
    d = [
        getattr(data, f.name) for f in fields(data) if f.name not in ["shape", "dtype"]
    ]
    return np.array([tuple(d)], dtype=dtype)


def restart_device(device: Device, time_offset: float) -> Device:
    logging.info(f"{device.name}: restart")
    device.active.clear()
    device.join()

    data_queue = device.data_queue
    events_queue = device.events_queue
    plots_queue = device.config.plots_queue

    device = Device(device.config)
    device.setup_connection(time_offset)

    device.data_queue = data_queue
    device.events_queue = events_queue
    device.config.plots_queue = plots_queue

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
        self.commands: list[str] = []
        self.last_event: list[tuple[float, str, Any]] = []
        self.monitoring_commands: set[str] = set()
        self.sequencer_commands: list[tuple[int, str]] = []
        self.networking_commands: list[tuple[int, str]] = []

        # for warnings about device abnormal condition
        self.warnings: list[DeviceWarning] = []

        # the data and events queues
        self.time_last_read = 0.0
        self.data_queue: deque[
            Union[list[float], list[tuple[npt.NDArray, list[str]]]]
        ] = deque()
        self.config.plots_queue = deque(maxlen=self.config.plots_queue_maxlen)
        self.events_queue: deque[tuple[float, str, Any]] = deque()
        self.monitoring_events_queue: deque[tuple[float, str, Any]] = deque()
        self.sequencer_events_queue: deque[tuple[int, int, str, Any]] = deque()
        # use a dictionary for the networking queue to allow use of .get() to
        # allow for unique ids if multiple network clients are connected
        self.networking_events_queue: dict[int, Any] = {}

        # the variable for counting the number of NaN returns
        self.nan_count = 0

        # for counting the number of sequential NaN returns
        self.sequential_nan_count = 0
        self.previous_data = True

        self.col_names_list: list[str] = []

    def setup_connection(self, time_offset: float):
        self.time_offset = time_offset

        # get the parameters that are to be passed to the driver constructor
        self.constr_params = [self.time_offset]
        for cp in self.config.constr_params:
            self.constr_params.append(self.config.control_params[cp].value)

        # for meta devices, include a reference to the parent
        if self.config.meta_device:
            self.constr_params = [self.config.parent] + self.constr_params

        # check we are allowed to instantiate the driver before the main loop starts
        self.operational = True

        # verify the device responds correctly
        with self.config.driver_class(*self.constr_params) as dev:
            logging.info(
                f"{self.config.name} -> verification_string ="
                f" {dev.verification_string}"
            )
            if not isinstance(dev.verification_string, str):
                self.operational = False
                self.error_message = "verification_string is not of type str"
                return
            if dev.verification_string.strip() == self.config.correct_response.strip():
                self.operational = True
            else:
                self.error_message = (
                    "verification string warning: "
                    + dev.verification_string
                    + "!="
                    + self.config.correct_response.strip()
                )
                logging.warning(self.error_message)
                self.operational = False
                return

            # get parameters and attributes, if any, from the driver
            try:
                self.config.shape = dev.shape
                self.config.dtype = dev.dtype
            except AttributeError:
                pass
            for attr_name, attr_val in dev.new_attributes:
                self.config.attributes[attr_name] = attr_val

    def change_plots_queue_maxlen(self, maxlen: int):
        # sanity check
        try:
            self.config.plots_queue_maxlen = int(maxlen)
        except ValueError as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            return

        # create a new deque with a different maxlen
        self.config.plots_queue = deque(maxlen=self.config.plots_queue_maxlen)

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
            logging.info(f"Start device {self.config.name}")

        # main control loop
        try:
            with self.config.driver_class(*self.constr_params) as device:
                while self.active.is_set():
                    # get and sanity check loop delay
                    try:
                        dt = float(self.config.control_params["dt"].value)
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
                    if self.config.control_params["enabled"].value == 0:
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
                            self.config.plots_queue.append(ret_val)
                            self.events_queue.append(
                                [time.time() - self.time_offset, c, ""]
                            )
                        else:
                            self.last_event = [
                                time.time() - self.time_offset,
                                c,
                                ret_val,
                            ]
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
                            self.config.plots_queue.append(ret_val)
                            self.events_queue.append(
                                [time.time() - self.time_offset, c, ""]
                            )
                        else:
                            self.events_queue.append(
                                [time.time() - self.time_offset, c, ret_val]
                            )
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
                        self.events_queue.append(
                            [time.time() - self.time_offset, cmd, ret_val]
                        )
                    self.networking_commands = []

                    # level 2: check device is enabled for regular ReadValue
                    if self.config.control_params["enabled"].value < 2:
                        continue

                    # record numerical values
                    if time.time() - self.time_last_read >= dt:
                        last_data = device.ReadValue()
                        self.time_last_read = time.time()

                        # keep track of the number of (sequential and total) NaN returns
                        if last_data is None and self.previous_data is None:
                            self.nan_count += 1
                        else:
                            self.sequential_nan_count = 0
                        self.previous_data = last_data

                        if last_data is not None:
                            self.data_queue.append(last_data)
                            self.config.plots_queue.append(last_data)

                        # issue a warning if there's been too many sequential NaN
                        # returns
                        if self.sequential_nan_count > self.config.max_nan_count:
                            self.warnings.append(
                                DeviceWarning(
                                    time.time(),
                                    message=f"excess sequential NaN returns {self.sequential_nan_count}",
                                    level=WarningLevel.ERROR,
                                )
                            )

        # report any exception that has occurred in the run() function
        except Exception as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            err_msg = traceback.format_exc()
            message = f"exception in {self.config.name} : {err_msg}"
            self.warnings.append(
                DeviceWarning(
                    time=time.time(), message=message, level=WarningLevel.ERROR
                )
            )
