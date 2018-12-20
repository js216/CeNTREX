import niscope
import numpy as np

class PXIe5171:
    def __init__(self, rm):
        # shape of the array of returned data
        self.shape = (2, )

        # verify operation
        self.verification_string = "TODO"

        # setup measurement
	self.session = niscope.Session("Dev1")
        session.channels[0].configure_vertical(range=1.0, coupling=niscope.VerticalCoupling.AC)
        session.channels[1].configure_vertical(range=2.0, coupling=niscope.VerticalCoupling.DC)
        session.configure_horizontal_timing(
                in_sample_rate=50000000,
                min_num_pts=1000,
                ref_position=50.0,
                num_records=5,
                enforce_realtime=True)
        session.initiate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def ReadValue(self):
        return session.channels[0,1].fetch(num_records=5)
