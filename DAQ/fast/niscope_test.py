import niscope
import numpy as np

class PXIe5171:
    def __init__(self, COM_port)
        self.session = niscope.Session(COM_port)

        # verify operation
        self.verification_string = "TODO"

        # set record parameters
        self.num_records = 1
        session.max_input_frequency = 100e6
        samplingRate_kSs = 20.0
        nrSamples        = 2000
        session.binary_sample_width = 16
        session.configure_horizontal_timing(
                min_sample_rate  = 1000 * int(samplingRate_kSs),
                min_num_pts      = nrSamples,
                ref_position     = 50.0,
                num_records      = self.num_records,
                enforce_realtime = True
            )

        # set channel configuration
        self.active_channels = [2]
        session.channels[2].configure_vertical(
                range    = 5.0,
                coupling = niscope.VerticalCoupling.DC
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

if __name__ == "__main__":
    scope = PXIe5171("PXI1Slot2")
