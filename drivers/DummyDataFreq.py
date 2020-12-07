import time
import numpy as np
from scipy import signal

class DummyDataFreq:
    def __init__(self, time_offset, period, frequency_span):
        self.time_offset = time_offset

        self.warnings = []
        self.new_attributes = []

        self.verification_string = 'test'

        self.period = float(period) # seconds
        self.frequency_span = float(frequency_span)

        # shape and type of the array of returned data
        self.shape = (2,)
        self.dtype = ('f4', 'float')

    def __exit__(self, *exc):
        pass

    def __enter__(self):
        return self

    def GetWarnings(self):
        return self.warnings

    def ReadValue(self):
        t = time.time() - self.time_offset
        return [t, self.frequency_span*signal.sawtooth(2*np.pi/self.period * t, width = 1)]
