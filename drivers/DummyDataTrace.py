import time
import numpy as np
from scipy import signal

class DummyDataTrace:
    def __init__(self, time_offset, period):
        self.time_offset = time_offset

        self.warnings = []
        self.new_attributes = []

        self.period = float(period) # seconds
        self.verification_string = 'test'

        # shape and type of the array of returned data
        self.shape = (1, 1, 2000)
        self.dtype = np.float

    def __exit__(self, *exc):
        pass

    def __enter__(self):
        return self

    def GetWarnings(self):
        return self.warnings

    def ReadValue(self):
        t = time.time() - self.time_offset
        amp = signal.sawtooth(2*np.pi/self.period * t, width = 0.5)/2+0.5+np.random.random(1)/5-1
        dset = [(amp*(signal.gaussian(2000,200)+np.random.random(2000)/10)).reshape(self.shape), [{'timestamp':t}]]
        # amp = np.sin(2*np.pi/self.period * t)
        # dset = [(amp*np.ones(2000)+np.random.random(2000)).reshape(self.shape), [{'timestamp':t}]]
        return dset
