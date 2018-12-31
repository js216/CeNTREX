# TO-DO:
# Monitor how long the data acquisition, and writing to HDF take.
# Would using deque be any faster?

import niscope
import numpy as np

class PXIe5171:
    def __init__(self, COM_port, recording, trigger, channels):
        self.session = niscope.Session(COM_port)

        # verify operation TODO
        self.verification_string = ""

        # record parameters
        try:
            self.num_records = int(recording["nr_records"])
        except ValueError:
            self.num_records = 1
        try:
            session.max_input_frequency = 1e6 * float(recording["bandwidth_MHz"].get())
        except ValueError:
            session.max_input_frequency = 100e6
        try:
            samplingRate_kSs = float(recording["sample_rate"])
        except ValueError:
            samplingRate_kSs = 20.0
        try:
            nrSamples        = int(recording["record_length"])
        except ValueError:
            nrSamples        = 2000
        session.binary_sample_width = 16
        session.configure_horizontal_timing(
                min_sample_rate  = 1000 * int(samplingRate_kSs),
                min_num_pts      = nrSamples,
                ref_position     = 50.0,
                num_records      = self.num_records,
                enforce_realtime = True
            )

        # trigger configuration TODO
        trigger_src          = trigger["trigger_src"]
        trigger_slope        = trigger["trigger_slope"]
        try:
            trigger_level    = float(trigger["trigger_level"])
        except ValueError:
            trigger_level    = 0.0
        try:
            trigger_delay    = float(trgger["trigger_delay"])
        except ValueError:
            trigger_delay    = 0.0

        # channel configuration
        self.channels = []
        for ch in [0, 1, 2, 3, 4, 5, 6, 7]:
            if bool(channels[0][ch].get()):
                self.channels.append[ch]
            try:
                range_V = float(channels[2].get())
            except ValueError:
                range_V = 5.0
            if channels[3][ch] == "AC":
                coupling_setting = niscope.VerticalCoupling.AC
            elif channels[3][ch] == "DC":
                coupling_setting = niscope.VerticalCoupling.DC
            else:
                coupling_setting = niscope.VerticalCoupling.GND
            session.channels[ch].configure_vertical(
                    range    = range_V,
                    coupling = coupling_setting
                )

        # shape of the array of returned data
        self.shape = (2, )

        # the array for reading data into
        self.waveform = np.ndarray(nrSamples, dtype = np.int16)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def ReadValue(self):
        with session.initiate():
            info = session.channels[self.channels].fetch_into(
                    self.waveform,
                    num_records=self.num_records
                )[0]
        dset.attrs['gain'] = info.gain
        dset.attrs['offset'] = info.offset
        dset.attrs['x_increment'] = info.x_increment
        dset.attrs['absolute_initial_x'] = info.absolute_initial_x
        return self.waveform
