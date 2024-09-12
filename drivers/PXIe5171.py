# TO-DO:
# Monitor how long the data acquisition, and writing to HDF take.
# Would using deque be any faster?

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, TypedDict

import niscope
import numpy as np
import numpy.typing as npt


@dataclass
class PXIe5171Data:
    time: float
    data: npt.NDArray[np.int16]
    shape: tuple[int] = (1, 2, 100)
    dtype: type | tuple[type, ...] = np.int16


class Record(TypedDict):
    record_length: int
    bandwidth_MHz: float
    nr_records: int


class Sample(TypedDict):
    sample_rate: float
    sample_width: int


class Trigger(TypedDict):
    trigger_type: str
    trigger_delay: float


class Edge(TypedDict):
    trigger_src: str
    trigger_slope: str
    trigger_level: float


class Channels(TypedDict):
    enable: List[bool]
    channel: List[int]
    range: str
    coupling: str


class PXIe5171:
    def __init__(
        self,
        time_offset: float,
        COM_port: str,
        record: Record,
        sample: Sample,
        trigger: Trigger,
        edge: Edge,
        channels,
    ):
        try:
            self.session = niscope.Session(COM_port)
        except niscope.errors.DriverError as err:
            logging.error("PXIe5171 error in __init__(): " + str(err))
            self.verification_string = "cannot open session"
            self.instr = False
            return
        self.time_offset = time_offset

        # verify operation
        self.verification_string = "not implemented"

        # set record parameters
        try:
            self.session.max_input_frequency = 1e6 * float(record["bandwidth_MHz"])
        except (niscope.errors.DriverError, ValueError) as err:
            logging.warning(
                "Warning in PXIe5171: invalid max_input_frequency selected: " + str(err)
            )
            self.session.max_input_frequency = 100e6
        try:
            samplingRate_kSs = float(sample["sample_rate"])
        except ValueError as err:
            logging.warning(
                "Warning in PXIe5171: invalid sample rate selected: " + str(err)
            )
            samplingRate_kSs = 20.0
        if samplingRate_kSs > 250e3:
            samplingRate_kSs = 20.0
        try:
            self.num_samples = int(float(record["record_length"]))
        except ValueError as err:
            logging.warning(
                "Warning in PXIe5171: invalid record_length selected: " + str(err)
            )
            self.num_samples = 2000
        try:
            self.session.binary_sample_width = int(sample["sample_width"])
        except (niscope.errors.DriverError, ValueError) as err:
            logging.warning(
                "Warning in PXIe5171: invalid binary_sample_width selected: " + str(err)
            )
            self.session.binary_sample_width = 16
        try:
            self.num_records = int(float(record["nr_records"]))
        except ValueError as err:
            logging.warning(
                "Warning in PXIe5171: invalid nr_records selected: " + str(err)
            )
            self.num_records = 1
        self.session.allow_more_records_than_memory = True
        self.session.configure_horizontal_timing(
            min_sample_rate=1000 * int(samplingRate_kSs),
            min_num_pts=self.num_samples,
            ref_position=0.0,
            num_records=2147483647,
            enforce_realtime=True,
        )

        # set clock configuration to use the PXI clock
        self.session.input_clock_source = "VAL_PXI_CLK"

        # set trigger configuration
        if trigger["trigger_type"] == "Edge":
            self.session.trigger_type = niscope.TriggerType.EDGE
        if trigger["trigger_type"] == "Immediate":
            self.session.trigger_type = niscope.TriggerType.IMMEDIATE
        if trigger["trigger_type"] == "Digital":
            self.session.trigger_type = niscope.TriggerType.DIGITAL
        self.session.trigger_source = edge["trigger_src"]
        if edge["trigger_slope"] == "Falling":
            self.session.trigger_slope = niscope.TriggerSlope.NEGATIVE
        elif edge["trigger_slope"] == "Rising":
            self.session.trigger_slope = niscope.TriggerSlope.POSITIVE
        try:
            self.session.trigger_level = float(edge["trigger_level"])
        except (niscope.errors.DriverError, ValueError) as err:
            logging.warning(
                "Warning in PXIe5171: invalid trigger level selected: " + str(err)
            )
            self.session.trigger_level = 0.0
        try:
            self.session.trigger_delay_time = float(trigger["trigger_delay"])
        except (niscope.errors.DriverError, ValueError) as err:
            logging.warning(
                "Warning in PXIe5171: invalid trigger delay selected: " + str(err)
            )
            self.session.trigger_delay_time = 0.0

        # set channel configuration
        self.active_channels = []
        for ch in [0, 1, 2, 3, 4, 5, 6, 7]:
            if bool(int(channels["enable"][ch])):
                self.active_channels.append(ch)
                try:
                    range_V = float(channels["range"][ch][0:-2])
                except ValueError as err:
                    logging.warning(
                        "Warning in PXIe5171: invalid range selected: " + str(err)
                    )
                    range_V = 5.0
                if channels["coupling"][ch] == "AC":
                    coupling_setting = niscope.VerticalCoupling.AC
                elif channels["coupling"][ch] == "DC":
                    coupling_setting = niscope.VerticalCoupling.DC
                else:
                    coupling_setting = niscope.VerticalCoupling.GND
                self.session.channels[ch].configure_vertical(
                    range=range_V, coupling=coupling_setting
                )

        # specify active channels as attributes for HDF, etc.
        self.new_attributes = [
            ("column_names", ", ".join(["ch" + str(x) for x in self.active_channels])),
            ("units", ", ".join(["binary" for x in self.active_channels])),
            ("sampling", str(1000 * samplingRate_kSs) + " [S/s]"),
        ]

        # shape and type of the array of returned data
        self.shape = (self.num_records, len(self.active_channels), self.num_samples)
        self.dtype = np.int16

        # index of which waveform to acquire
        self.rec_num = 0

        self.trace_attrs = {}

        # start acquisition
        self.session.initiate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.session.close()
        except AttributeError as err:
            logging.error("Error in __exit__() in PXIe5171: " + str(err))

    def ReadValue(self):
        # the structures for reading waveform data into
        attrs = {}
        waveforms_flat = np.ndarray(
            len(self.active_channels) * self.num_records * self.num_samples,
            dtype=np.int16,
        )

        # fetch data & metadata
        try:
            infos = self.session.channels[self.active_channels].fetch_into(
                waveform=waveforms_flat,
                relative_to=niscope.FetchRelativeTo.PRETRIGGER,
                offset=0,
                record_number=self.rec_num,
                num_records=self.num_records,
                timeout=datetime.timedelta(seconds=10),
            )
            timestamp = time.time() - self.time_offset
        except niscope.errors.DriverError as err:
            logging.warning(str(err))
            return np.nan

        # organize metadata in a list of dictionaries
        all_attrs = []
        for i in range(self.num_records):
            attrs = {}
            attrs.update(self.trace_attrs)
            for info in infos:
                if info.record == i + self.rec_num:
                    attrs_upd = {
                        "timestamp": timestamp,
                        # time from trigger to first sample
                        "relative_initial_x": info.relative_initial_x,
                        # timestamp of the first sample
                        "absolute_initial_x": info.absolute_initial_x,
                        # time in seconds between points
                        "x_increment": info.x_increment,
                        "ch" + str(info.channel) + " : channel": info.channel,
                        "ch" + str(info.channel) + " : record": info.record,
                        "ch" + str(info.channel) + " : gain": info.gain,
                        "ch" + str(info.channel) + " : offset": info.offset,
                    }
                    attrs.update(attrs_upd)
            all_attrs.append(attrs)

        # increment record count
        self.rec_num += self.num_records

        return PXIe5171Data(
            timestamp,
            data=waveforms_flat.reshape(self.shape),
            attrs=all_attrs,
            dtype=self.dtype,
        )

    def GetWarnings(self):
        return None

    def UpdateSequenceAttrs(self, parent_info):
        if len(np.shape(parent_info)) == 2:
            for device, function, param in parent_info:
                self.UpdateTraceAttrs({f"{device} {function}": param})
        else:
            device, function, param, enabled = parent_info
            if device == "":
                return
            self.UpdateTraceAttrs({f"{device} {function}": param})

    def UpdateTraceAttrs(self, attrs: Dict):
        self.trace_attrs.update(attrs)

    def DummyFunc(self, val):
        return None

    def ClearBuffer(self, timeout: float = 0.1):
        """
        Convenience function for sequencer to assert that no missed triggers are in
        the device buffer before changing a parameter of a different device
        """
        waveforms_flat = np.ndarray(
            len(self.active_channels) * self.num_records * self.num_samples,
            dtype=np.int16,
        )

        # fetch until no more present in memory
        while True:
            try:
                self.session.channels[self.active_channels].fetch_into(
                    waveform=waveforms_flat,
                    relative_to=niscope.FetchRelativeTo.PRETRIGGER,
                    offset=0,
                    record_number=self.rec_num,
                    num_records=self.num_records,
                    timeout=datetime.timedelta(seconds=timeout),
                )
            except niscope.errors.DriverError:
                break
        return
