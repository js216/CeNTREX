import datetime
import logging
import threading
import time
import traceback
from collections.abc import Sequence
from typing import Any, Dict, List, Tuple

import numpy as np
import PyQt5
import PyQt5.QtWidgets as qt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision

from config import DeviceConfig
from device import Device as DeviceProtocol
from device import restart_device
from protocols import CentrexGUIProtocol


class Monitoring(threading.Thread, PyQt5.QtCore.QObject):
    # signal to update the style of a QWidget
    update_style = PyQt5.QtCore.pyqtSignal(qt.QWidget)

    def __init__(self, parent: CentrexGUIProtocol):
        threading.Thread.__init__(self)
        PyQt5.QtCore.QObject.__init__(self)
        self.parent = parent
        self.active = threading.Event()

        # HDF filename at the time run started (in case it's renamed while running)
        self.hdf_fname: str = self.parent.config["files"]["hdf_fname"]

        self.time_last_monitored = 0.0

        # connect to InfluxDB
        conf = self.parent.config["influxdb"]
        self.influxdb_client = InfluxDBClient(
            url=f"{conf['host']}:{conf['port']}", token=conf["token"], org=conf["org"]
        )
        self.influxdb_org: str = conf["org"]
        self.influxdb_bucket: str = conf["bucket"]
        self.write_api = self.influxdb_client.write_api(write_options=SYNCHRONOUS)

    def run(self):
        while self.active.is_set():
            # check amount of remaining free disk space
            self.parent.ControlGUI.check_free_disk_space()

            HDF_status = self.parent.ControlGUI.HDF_status

            # check that we have written to HDF recently enough
            if self.parent.ControlGUI.HDF_writer.active.is_set():
                time_last_write = self.parent.ControlGUI.HDF_writer.time_last_write
                hdf_time = time.mktime(time_last_write.timetuple())
                status = time_last_write.isoformat()
            else:
                hdf_time = 0
                status = "disabled"
                HDF_status.setProperty("state", "disabled")

            HDF_status.setText(status)

            if time.time() - hdf_time > 5.0:
                HDF_status.setProperty("state", "error")
            else:
                HDF_status.setProperty("state", "enabled")

            # update style
            self.update_style.emit(HDF_status)

            # monitoring dt
            try:
                dt = float(self.parent.config["general"]["monitoring_dt"])
            except ValueError as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())
                dt = 1

            # monitor operation of individual devices
            for dev_name, dev in self.parent.devices.items():
                # check device running
                if not dev.control_started:
                    continue

                # check device enabled
                if not dev.config["control_params"]["enabled"]["value"] == 2:
                    continue

                # automatically restart device if the last read data was more than n
                # seconds ago
                if time.time() - dev.time_last_read > 30.0:
                    self.parent.devices[dev_name] = restart_device(
                        dev, self.parent.config["time_offset"]
                    )

                # check device for abnormal conditions
                if len(dev.warnings) != 0:
                    logging.warning("Abnormal condition in " + str(dev_name))
                    for warning in dev.warnings:
                        logging.warning(str(warning))
                        if self.parent.config["influxdb"]["enabled"] in [
                            1,
                            2,
                            "2",
                            "1",
                            "True",
                        ]:
                            self.push_warnings_to_influxdb(dev.config, warning)
                        self.parent.ControlGUI.update_warnings(str(warning))
                    dev.warnings = []

                # find out and display the data queue length
                dev.config["monitoring_GUI_elements"]["qsize"].setText(
                    str(len(dev.data_queue))
                )

                # get the last event (if any) of the device
                # try:
                #     self.display_last_event(dev)
                # except Exception as e:
                #     logging.warning(
                #         f"Exception for display_last_event for {dev.config['name']}"
                #     )
                #     logging.warning(e)
                #     logging.warning(traceback.format_exc())

                # send monitoring commands
                for c_name, params in dev.config["control_params"].items():
                    if params.get("type") in [
                        "indicator",
                        "indicator_button",
                        "indicator_lineedit",
                    ]:
                        dev.monitoring_commands.add(params["monitoring_command"])

                # obtain monitoring events and update any indicator controls
                # this crashes the GUI, not sure why yet, happens for random devices
                self.display_monitoring_events(dev)

                # get the last row of data from the plots_queue
                if len(dev.config["plots_queue"]) > 0:
                    data = dev.config["plots_queue"][-1]
                else:
                    data = None

                # format the data
                if isinstance(data, list):
                    try:
                        if dev.config["slow_data"]:
                            formatted_data = [
                                np.format_float_scientific(x, precision=3)
                                if not isinstance(x, str)
                                else x
                                for x in data
                            ]
                        else:
                            formatted_data = [
                                np.format_float_scientific(x, precision=3)
                                for x in data[0][0, :, 0]
                            ]
                    except TypeError as err:
                        logging.warning("Warning in Monitoring: " + str(err))
                        logging.warning(traceback.format_exc())
                        continue
                    dev.config["monitoring_GUI_elements"]["data"].setText(
                        "\n".join(formatted_data)
                    )

                    # write slow data to InfluxDB
                    if time.time() - self.time_last_monitored >= dt:
                        self.write_to_influxdb(dev, data)

                # if writing to HDF is disabled, empty the queues
                if not bool(int(dev.config["control_params"]["HDF_enabled"]["value"])):
                    dev.events_queue.clear()
                    dev.data_queue.clear()

            # reset the timer for setting the slow monitoring loop delay
            if time.time() - self.time_last_monitored >= dt:
                self.time_last_monitored = time.time()

            # fixed monitoring fast loop delay
            time.sleep(0.5)
        logging.info("Monitoring: stopped")

    def write_to_influxdb(self, dev: DeviceProtocol, data):
        # check writing to InfluxDB is enabled
        if self.parent.config["influxdb"]["enabled"] not in [1, 2, "1", "2", "True"]:
            return
        if dev.config["control_params"]["InfluxDB_enabled"]["value"] not in [
            1,
            2,
            "1",
            "2",
            "True",
        ]:
            return

        # only slow data can write to InfluxDB
        if not dev.config["slow_data"]:
            return

        # get dtypes from device
        dtype = dev.config["dtype"]
        if isinstance(dtype, str):
            if "f" in dtype:
                dtype = float
        elif isinstance(dtype, Sequence):
            _dtype = []
            for d in dtype[1:]:
                if isinstance(d, str):
                    if "f" in d:
                        _dtype.append(float)
                    elif "S" in d:
                        _dtype.append(str)
                    elif "U" in d:
                        _dtype.append(int)
                    elif "b" in d:
                        _dtype.append(bool)
                    else:
                        _dtype.append(eval(d))
                else:
                    _dtype.append(d)
            dtype = _dtype

        # check there is any non-np.nan data to write
        # try-except because something crashes here
        try:
            _fields = []
            for idk, (key, val) in enumerate(zip(dev.col_names_list[1:], data[1:])):
                if isinstance(dtype, Sequence):
                    val = dtype[idk](val)
                else:
                    val = dtype(val)
                if isinstance(val, str):
                    _fields.append((key, val))
                elif not np.isnan(val):
                    _fields.append((key, val))
            if len(_fields) == 0:
                return
            fields = dict(_fields)
        except Exception as e1:
            logging.warning(f"Error in write_to_influxdb: {e1}")
            for idk, (key, val) in enumerate(zip(dev.col_names_list[1:], data[1:])):
                try:
                    if isinstance(dtype, Sequence):
                        val = dtype[idk](val)
                    else:
                        val = dtype(val)
                    if isinstance(val, str):
                        continue
                    elif not np.isnan(val):
                        continue
                except Exception as e2:
                    logging.warning(
                        f"Error in write_to_influxdb: {key}, {val}, {type(val)}"
                    )
                    logging.warning(f"Error in write_to_influxdb: {str(e2)}")
            return

        # format the message for InfluxDB
        p = (
            Point(dev.config["driver"])
            .tag("run_name", self.parent.run_name)
            .tag("name", dev.config["name"])
        )
        p = p.time(
            time=datetime.datetime.utcfromtimestamp(
                data[0] + self.parent.config["time_offset"]
            ).isoformat()
        )
        for k, v in fields.items():
            p = p.field(k, v)
        # push to InfluxDB
        try:
            self.write_api.write(
                bucket=self.influxdb_bucket, record=p, org=self.influxdb_org
            )
        except Exception as err:
            logging.warning(f"Error in write_to_influxdb: {err}")
            logging.warning(traceback.format_exc())

    def display_monitoring_events(self, dev: DeviceProtocol):
        # check device enabled
        if not dev.config["control_params"]["enabled"]["value"] == 2:
            return

        # empty the monitoring events queue
        monitoring_events: List[Tuple[float, str, Any]] = []
        while len(dev.monitoring_events_queue) > 0:
            monitoring_events.append(dev.monitoring_events_queue.pop())

        # check any events were returned
        if not monitoring_events:
            return

        for c_name, params in dev.config["control_params"].items():
            # check we're dealing with indicator controls
            if params.get("type") not in [
                "indicator",
                "indicator_button",
                "indicator_lineedit",
            ]:
                continue

            # check the returned events
            for event in monitoring_events:
                # skip event if it's related to a different command
                if not params["monitoring_command"] == event[1]:
                    continue

                # check if there's any matching return value
                if params.get("type") in ["indicator", "indicator_button"]:
                    try:
                        if event[2] in params["return_values"]:
                            idx = params["return_values"].index(event[2])
                        else:
                            idx = -2
                    except ValueError as e:
                        logging.warning(e)
                        logging.warning(traceback.format_exc())
                        idx = -2

                # update indicator text and style if necessary

                if params.get("type") == "indicator":
                    ind = dev.config["control_GUI_elements"][c_name]["QLabel"]
                    if ind.text() != params["texts"][idx]:
                        ind.setText(params["texts"][idx])
                        ind.setProperty("state", params["states"][idx])
                        self.update_style.emit(ind)

                elif params.get("type") == "indicator_button":
                    ind = dev.config["control_GUI_elements"][c_name]["QPushButton"]
                    if ind.text() != params["texts"][idx]:
                        ind.setText(params["texts"][idx])
                        ind.setChecked(params["checked"][idx])
                        ind.setProperty("state", params["states"][idx])
                        self.update_style.emit(ind)

                elif params.get("type") == "indicator_lineedit":
                    # crashes here
                    continue
                    logging.info(
                        f"{dev.config['name']} in display_monitoring_events"
                        " indicator_lineedit 0"
                    )
                    if not dev.config["control_GUI_elements"][c_name][
                        "currently_editing"
                    ]:
                        logging.info(
                            f"{dev.config['name']} in display_monitoring_events"
                            " indicator_lineedit 1"
                        )
                        ind = dev.config["control_GUI_elements"][c_name]["QLineEdit"]
                        logging.info(
                            f"{dev.config['name']} in display_monitoring_events"
                            " indicator_lineedit 2"
                        )
                        ind.setText(str(event[2]))

    def display_last_event(self, dev: DeviceProtocol):
        # check device enabled
        if not dev.config["control_params"]["enabled"]["value"] == 2:
            return

        try:
            if len(dev.events_queue) > 0:
                last_event = dev.events_queue.pop()
                dev.config["monitoring_GUI_elements"]["events"].setText(str(last_event))
                return last_event
        except IndexError as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            return

    def push_warnings_to_influxdb(
        self, dev_config: DeviceConfig, warning: Tuple[float, Dict[str, str]]
    ):
        json_body = [
            {
                "measurement": "warnings",
                "tags": {
                    "run_name": self.parent.run_name,
                    "name": dev_config["name"],
                    "driver": dev_config["driver"],
                },
                "time": int(1000 * warning[0]),
                "fields": warning[1],
            }
        ]
        self.write_api.write(
            self.influxdb_bucket, json_body, write_precision=WritePrecision.MS
        )
