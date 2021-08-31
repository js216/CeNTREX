import time
import logging
import numpy as np

class generate2D:
    """Generate 2D array for testing of 2D HDF saving and plotting
    """
    def __init__(self, time_offset):
        self.time_offset = time_offset

        self.verification_string = '2D'

        self.warnings = []
        self.new_attributes = []

        self.dtype = np.int16
        self.shape = (1,2,512,512)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    def GetWarnings(self):
        return self.warnings

    def ReadValue(self):
        data = (np.random.rand(*self.shape)*2**16).astype(np.int16)
        return [data.reshape(*self.shape), [{}]]
