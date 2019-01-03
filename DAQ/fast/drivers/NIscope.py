# TO-DO:
# Monitor how long the data acquisition, and writing to HDF take.
# Would using deque be any faster?

import niscope
import numpy as np
import time
import sys

class PXIe5171:
    def __init__(self, time_offset, COM_port, record, sample, trigger, edge, channels):
        self.time_offset = time_offset
        self.session = niscope.Session(COM_port)

        # each reading is to be written to a different HDF dataset
        self.single_dataset = False

        # verify operation
        self.verification_string = "not implemented"

        # set record parameters
        try:
            self.num_records = int(record["nr_records"].get())
        except ValueError:
            self.num_records = 1
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
            nrSamples        = int(float(record["record_length"].get()))
        except ValueError:
            nrSamples        = 2000
        try:
            self.session.binary_sample_width = int(sample["sample_width"].get())
        except (niscope.errors.DriverError, ValueError):
            self.session.binary_sample_width = 16
        self.session.configure_horizontal_timing(
                min_sample_rate  = 1000 * int(samplingRate_kSs),
                min_num_pts      = nrSamples,
                ref_position     = 50.0,
                num_records      = self.num_records,
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
               ]

        # shape and type of the array of returned data
        self.shape = (self.num_records, nrSamples, len(self.active_channels))
        self.dtype = np.int16

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def ReadValue(self):
        # the array for reading waveform data into
        wfm = np.ndarray(self.shape, dtype = np.int16)

        # get data
        with self.session.initiate():
            try:
                time0 = time.time()
                info = self.session.channels[self.active_channels].fetch_into(
                        wfm.flatten(),
                        num_records=self.num_records,
                        timeout = 1.0
                    )
            except niscope.errors.DriverError:
                return None
            print("scope read time = ", time.time()-time0)
            sys.stdout.flush()


        return (wfm, info)
