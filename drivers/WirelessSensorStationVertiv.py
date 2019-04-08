import functools
import numpy as np
import time
import logging
import urllib.request
from urllib.error import URLError, HTTPError

def CatchUrllibErrors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (URLError, HTTPError) as err:
            logging.warning('WirelessSensorStationVertiv warning in {0}() : '.format(func.__name__) \
                            +str(err))
            return np.nan
    return wrapper

class WirelessSensorStationVertiv:
    def __init__(self, time_offset, ip):
        self.time_offset = time_offset
        self.ip = ip
        self.verification_string = self.VerifyOperation()
        if not isinstance(self.verification_string, str):
            self.verification_string = "False"
        self.new_attributes = []
        self.dtype = 'f'
        self.shape = (4,)
        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def GetWarnings(self):
        return []

    @CatchUrllibErrors
    def VerifyOperation(self):
        with urllib.request.urlopen("http://"+self.ip+"/STATUS") as response:
            status = response.read().decode()
        return status.split(',')[0]

    @CatchUrllibErrors
    def ReadValue(self):
        with urllib.request.urlopen("http://"+self.ip+"/temperature") as response:
            value = response.read().decode()
        values = [time.time()-self.time_offset]
        value = [float(v.split(':')[-1].strip()) for v in value.split(',')]
        values.extend(value)
        return values
