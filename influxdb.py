import copy
import datetime
import logging
import threading
import time
import traceback
from typing import Dict, Sequence, Tuple

import numpy as np
import urllib3
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision

from config import DeviceConfig
from protocols import CentrexGUIProtocol, DeviceProtocol


class InfluxDBWriter(threading.Thread):
    def __init__(self, parent: CentrexGUIProtocol, dt: float = 1):
        super().__init__()
        self.parent = parent

        self.time_last_monitored = 0

        self.connect()

        self.influx_last_write_timestamp = dict(
            [(dev_name, 0) for dev_name in self.parent.devices.keys()]
        )
        self.dev_warnings = dict(
            [(dev_name, []) for dev_name in self.parent.devices.keys()]
        )

        self.dt = dt

        self.active = threading.Event()

    def connect(self):
        # connect to InfluxDB
        conf = self.parent.config["influxdb"]
        self.influxdb_client = InfluxDBClient(
            url=f"{conf['host']}:{conf['port']}",
            token=conf["token"],
            org=conf["org"],
            timeout=2_000,
        )
        self.influxdb_org: str = conf["org"]
        self.influxdb_bucket: str = conf["bucket"]
        self.write_api = self.influxdb_client.write_api(write_options=SYNCHRONOUS)

    def run(self):
        logging.info("InfluxDBWriter: started")
        while self.active.is_set():
            if self.parent.config["influxdb"]["enabled"] in [
                1,
                2,
                True,
                "2",
                "1",
                "True",
            ]:
                for dev_name, dev in self.parent.devices.items():
                    # check if there is data to write, if the data is slow data or if
                    # the device has the influxDB enabled flag set to True
                    if (
                        len(dev.config["plots_queue"]) == 0
                        or not dev.config["slow_data"]
                        or (
                            dev.config["control_params"]["InfluxDB_enabled"]["value"]
                            not in [
                                1,
                                2,
                                True,
                                "1",
                                "2",
                                "True",
                            ]
                        )
                    ):
                        continue
                    else:
                        data = copy.copy(dev.config["plots_queue"])
                        for d in data:
                            # check if already written data with the same timestamp and
                            # if the data is of list format
                            if isinstance(d, list) and (
                                d[0] >= self.influx_last_write_timestamp[dev_name]
                            ):
                                self.write_to_influxdb(dev, d)
                                self.influx_last_write_timestamp[dev_name] = d[0]

                            # add a check to see if the thread is still active,
                            # otherwise have to cycle through all devices before a
                            # shutdown
                            if not self.active.is_set():
                                break

                    # check warnings and empty after push
                    warnings = copy.copy(self.dev_warnings[dev_name])
                    self.dev_warnings[dev_name] = []

                    for warning in warnings:
                        self.push_warnings_to_influxdb(dev.config, warning)
                        # add a check to see if the thread is still active, otherwise
                        # have to cycle through all devices before a shutdown
                        if not self.active.is_set():
                            break

                    # add a check to see if the thread is still active, otherwise have
                    # to cycle through all devices before a shutdown
                    if not self.active.is_set():
                        break
            time.sleep(self.dt)

        logging.info("InfluxDBWriter: stopped")

    def write_to_influxdb(self, dev: DeviceProtocol, data):
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
            logging.warning(
                "InfluxDBWriter: error in write_to_influxdb for"
                f" {dev.config['name']} -> {e1}"
            )
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
                        "InfluxDBWriter: error in write_to_influxdb for"
                        f" {dev.config['name']} -> {e2}: {key}, {val}, {type(val)}"
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
        except urllib3.exceptions.ConnectTimeoutError as err:
            logging.warning(
                "InfluxDBWriter: error in write_to_influxdb for"
                f" {dev.config['name']} -> {err}"
            )
        except Exception as err:
            logging.warning(
                "InfluxDBWriter: error in write_to_influxdb for"
                f" {dev.config['name']} -> {err}"
            )
            logging.warning(traceback.format_exc())

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
