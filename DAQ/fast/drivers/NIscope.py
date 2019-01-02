# TO-DO:
# Monitor how long the data acquisition, and writing to HDF take.
# Would using deque be any faster?

import niscope
import numpy as np

class PXIe5171:
    def __init__(self, COM_port, record, sample, trigger, channels):
        self.session = niscope.Session(COM_port)

        # verify operation
        self.verification_string = "TODO"

        # set record parameters
        try:
            self.num_records = int(record["nr_records"].get())
        except ValueError:
            self.num_records = 1
        try:
            session.max_input_frequency = 1e6 * float(record["bandwidth_MHz"].get())
        except ValueError:
            session.max_input_frequency = 100e6
        try:
            samplingRate_kSs = float(sample["sample_rate"].get())
        except ValueError:
            samplingRate_kSs = 20.0
        try:
            nrSamples        = int(record["record_length"].get())
        except ValueError:
            nrSamples        = 2000
        try:
            session.binary_sample_width = int(sample["sample_width"].get())
        except ValueError:
            session.binary_sample_width = 16
        session.configure_horizontal_timing(
                min_sample_rate  = 1000 * int(samplingRate_kSs),
                min_num_pts      = nrSamples,
                ref_position     = 50.0,
                num_records      = self.num_records,
                enforce_realtime = True
            )

        # set trigger configuration
        trigger_src          = trigger["trigger_src"].get()
        trigger_slope        = trigger["trigger_slope"].get()
        try:
            trigger_level    = float(trigger["trigger_level"].get())
        except ValueError:
            trigger_level    = 0.0
        try:
            trigger_delay    = float(trigger["trigger_delay"].get())
        except ValueError:
            trigger_delay    = 0.0

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
                session.channels[ch].configure_vertical(
                        range    = range_V,
                        coupling = coupling_setting
                    )

        # shape of the array of returned data
        self.shape = (len(self.active_channels), num_records, nrSamples)

        # the array for reading data into
        self.waveform = np.ndarray(self.shape, dtype = np.int16)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()
        ...

    def ReadValue(self):
        with session.initiate():
            info = session.channels[self.active_channels].fetch_into(
                    self.waveform,
                    num_records=self.num_records
                )
        return self.waveform
