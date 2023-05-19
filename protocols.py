import datetime
import threading
from typing import Dict
from typing_extensions import Protocol

import PyQt5.QtWidgets as qt

from config import ProgramConfig
from device import Device as DeviceProtocol


class HDF_writerProtocol(Protocol):
    active: threading.Event
    time_last_write: datetime.datetime


class ControlGUIProtocol(Protocol):
    HDF_status: qt.QLabel
    HDF_writer: HDF_writerProtocol

    def check_free_disk_space(self):
        pass

    def update_warnings(self, warnings: str):
        pass


# class DeviceProtocol(Protocol):
#     control_started: bool
#     config: DeviceConfig
#     data_queue: Deque
#     monitoring_commands: Set[str]
#     monitoring_events_queue: Deque[Tuple[float, str, Any]]
#     events_queue: Deque[Tuple[float, str, Any]]
#     col_names_list: List[str]
#     warnings: List[Tuple[float, Dict[str, str]]]


class CentrexGUIProtocol(Protocol):
    run_name: str
    config: ProgramConfig
    ControlGUI: ControlGUIProtocol
    devices: Dict[str, DeviceProtocol]
