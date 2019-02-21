# TO-DO:
# Monitor how long the data acquisition, and writing to HDF take.
# Would using deque be any faster?

import niscope
import numpy as np
import time
import sys
import datetime
import logging

class PXIe5171:
    def __init__(self, time_offset, COM_port, record, sample, trigger, edge, channels):
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
            self.session.max_input_frequency = 1e6 * float(record["bandwidth_MHz"].get())
        except (niscope.errors.DriverError, ValueError):
            self.session.max_input_frequency = 100e6
        try:
            samplingRate_kSs = float(sample["sample_rate"].get())
        except ValueError:
            samplingRate_kSs = 20.0
        if samplingRate_kSs > 250e3:
            samplingRate_kSs = 20.0
        try:
            self.num_samples        = int(float(record["record_length"].get()))
        except ValueError:
            self.num_samples        = 2000
        try:
            self.session.binary_sample_width = int(sample["sample_width"].get())
        except (niscope.errors.DriverError, ValueError):
            self.session.binary_sample_width = 16
        try:
            self.num_records = int(float(record["nr_records"].get()))
        except ValueError:
            self.num_records = 1
        self.session.allow_more_records_than_memory = True
        self.session.configure_horizontal_timing(
                min_sample_rate  = 1000 * int(samplingRate_kSs),
                min_num_pts      = self.num_samples,
                ref_position     = 0.0,
                num_records      = 2147483647,
                enforce_realtime = True
            )

        # set trigger configuration
        if trigger["trigger_type"].get() == "Edge":
            self.session.trigger_type = niscope.TriggerType.EDGE
        if trigger["trigger_type"].get() == "Immediate":
            self.session.trigger_type = niscope.TriggerType.IMMEDIATE
        self.session.trigger_source = edge["trigger_src"].get()
        if edge["trigger_slope"].get() == "Falling":
            self.session.trigger_slope = niscope.TriggerSlope.NEGATIVE
        elif edge["trigger_slope"].get() == "Rising":
            self.session.trigger_slope = niscope.TriggerSlope.POSITIVE
        try:
            self.session.trigger_level = float(edge["trigger_level"].get())
        except (niscope.errors.DriverError, ValueError):
            self.session.trigger_level = 0.0
        try:
            self.session.trigger_delay_time    = float(trigger["trigger_delay"].get())
        except (niscope.errors.DriverError, ValueError):
            self.session.trigger_delay_time    = 0.0

        # set channel configuration
        self.active_channels = []
        for ch in [0, 1, 2, 3, 4, 5, 6, 7]:
            if bool(int(channels[0][ch].get())):
                self.active_channels.append(ch)
                try:
                    range_V = float(channels[2][ch].get()[0:-2])
                except ValueError:
                    range_V = 5.0
                if channels[3][ch].get() == "AC":
                    coupling_setting = niscope.VerticalCoupling.AC
                elif channels[3][ch].get() == "DC":
                    coupling_setting = niscope.VerticalCoupling.DC
                else:
                    coupling_setting = niscope.VerticalCoupling.GND
                self.session.channels[ch].configure_vertical(
                        range    = range_V,
                        coupling = coupling_setting
                    )


        # specify active channels as attributes for HDF, etc.
        self.new_attributes = [
                    ("column_names", ", ".join(["ch"+str(x) for x in self.active_channels])),
                    ("units", ", ".join(["binary" for x in self.active_channels])),
                    ("sampling", str(1000*samplingRate_kSs)+" [S/s]")
               ]

        # shape and type of the array of returned data
        self.shape = (self.num_records, len(self.active_channels), self.num_samples)
        self.dtype = np.int16

        # index of which waveform to acquire
        self.rec_num = 0

        # start acquisition
        self.session.initiate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.session.close()
        except AttributeError:
            pass

    def ReadValue(self):
        # the structures for reading waveform data into
        attrs = {}
        waveforms_flat = np.ndarray(len(self.active_channels) * self.num_records * self.num_samples, dtype = np.int16)

        # fetch data & metadata
        try:
            infos = self.session.channels[self.active_channels].fetch_into(
                    waveform      = waveforms_flat,
                    relative_to   = niscope.FetchRelativeTo.PRETRIGGER,
                    offset        = 0,
                    record_number = self.rec_num,
                    num_records   = self.num_records,
                    timeout       = datetime.timedelta(seconds=1.0)
                )
        except niscope.errors.DriverError as err:
            logging.warning(err)
            return np.nan

        # increment record count
        self.rec_num += self.num_records

        # organize metadata in a list of dictionaries
        all_attrs = []
        for i in range(self.num_records):
            attrs = {}
            for info in infos:
                if info.record == i:
                    attrs_upd = {
                            'ch'+str(info.channel)+' : relative_initial_x' : info.relative_initial_x,
                            'ch'+str(info.channel)+' : absolute_initial_x' : info.absolute_initial_x,
                            'ch'+str(info.channel)+' : x_increment'        : info.x_increment,
                            'ch'+str(info.channel)+' : channel'            : info.channel,
                            'ch'+str(info.channel)+' : record'             : info.record,
                            'ch'+str(info.channel)+' : gain'               : info.gain,
                            'ch'+str(info.channel)+' : offset'             : info.offset,
                        }
                    attrs.update(attrs_upd)
            all_attrs.append(attrs)

        return (waveforms_flat.reshape(self.shape), all_attrs)

    def GetWarnings(self):
        return None
