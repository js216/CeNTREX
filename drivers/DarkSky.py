from darksky import forecast
import datetime
import numpy as np
import time

class DarkSky:
    def __init__(self, time_offset, key, latlon, units):
        self.time_offset = time_offset
        self.key = key
        self.latitude = latlon['latitude']
        self.longitude = latlon['longitude']
        self.units = units
        self.verification_string = self.VerifyOperation()

        self.warnings = []
        self.new_attributes = []
        self.dtype = 'f'
        self.shape = (16,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    def GetWarnings(self):
        return []

    def VerifyOperation(self):
        try:
            weather = forecast(self.key, self.latitude, self.longitude,
                               units = self.units, timeout = 1)
            return 'Connected'
        except Exception as e:
            logging.warning("DarkSky warning in VerifyOperation: "+str(e))
            return 'False'

    def ReadValue(self):
        try:
            weather = forecast(self.key, self.latitude, self.longitude,
                               units = self.units, timeout = 1)
        except Exception as e:
            logging.warning("DarkSky warning in Readvalue: "+str(e))
            return np.nan
        try:
            current = weather.currently
        except TimeoutError:
            logging.warning("DarkSky warning in Readvalue: TimeoutError")
            return np.nan
        try:
            nearestStormDistance = current.nearestStormDistance
        except AttributeError:
            nearestStormDistance = np.nan
        values = [time.time() - self.time_offset, current.temperature,
                  current.humidity, current.dewPoint, current.pressure,
                  current.cloudCover, current.uvIndex, current.windSpeed,
                  current.windGust, current.ozone, current.precipIntensity,
                  current.precipProbability, nearestStormDistance,
                  current.visibility, weather.latitude, weather.longitude]
        values = [float(v) for v in values]
        return values
