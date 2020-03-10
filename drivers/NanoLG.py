import clr # pythonnet
import time
import logging
import threading
from System import Enum
clr.AddReference('Litron.Control.PulsedLasers')\
import Litron
from Litron.Control.PulsedLasers import pulsedLaser

class SystemStatusData(object):
    def __init__(self, data = None, delay = 300):
        self._data = data
        self._time = time.time()
        self._delay = delay

    def __get__(self, instance, owner):
        if (time.time() - self._time < self._delay) & (not isinstance(self._data, type(None))):
            return self._data
        else:
            instance.Ping()
            while (time.time() - self._time > self._delay) or (isinstance(self._data, type(None))):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)

class FunctionStatusDataData(object):
    def __init__(self, data = None, delay = 300):
        self._data = data
        self._time = time.time()
        self._delay = delay

    def __get__(self, instance, owner):
        if (time.time() - self._time < self._delay) & (not isinstance(self._data, type(None))):
            return self._data
        else:
            instance.RequestionFunctionStatusDataData()
            while (time.time() - self._time > self._delay) & (isinstance(self._data, type(None))):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)

class ChillerData(object):
    def __init__(self, enum, data = None, delay = 300):
        self._enum = enum
        self._data = data
        self._time = time.time()
        self._delay = delay

    def __get__(self, instance, owner):
        if (time.time() - self._time < self._delay) & (not isinstance(self._data, type(None))):
            return self._data
        else:
            instance.RequestChillerData(self._enum)
            while (time.time() - self._time > self._delay) & (isinstance(self._data, type(None))):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)

class LampShotData(object):
    def __init__(self, data = None, delay = 300):
        self._data = data
        self._time = time.time()
        self._delay = delay

    def __get__(self, instance, owner):
        if (time.time() - self._time < self._delay) & ((not isinstance(self._data, type(None))) or (self._data != 0)):
            return self._data
        else:
            instance.RequestFlashlampShots()
            while (time.time() - self._time > self._delay) & ((isinstance(self._data, type(None))) or (self._data == 0)):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)


class Yag(pulsedLaser):
    smdelay = 10
    fmdelay = 60

    systemstate = SystemStatusData(delay = smdelay)
    pumpstate = SystemStatusData(delay = smdelay)
    laserstate = SystemStatusData(delay = smdelay)
    shutterstate = SystemStatusData(delay = smdelay)
    intwaterflow = SystemStatusData(delay = smdelay)
    intwaterlevel = SystemStatusData(delay = smdelay)
    intwatertemp = SystemStatusData(delay = smdelay)
    intcharger1 = SystemStatusData(delay = smdelay)
    intcharger2 = SystemStatusData(delay = smdelay)
    intexternal = SystemStatusData(delay = smdelay)
    intpuscover = SystemStatusData(delay = smdelay)
    intlaserhead = SystemStatusData(delay = smdelay)
    intshutter = SystemStatusData(delay = smdelay)
    intsimmer1 = SystemStatusData(delay = smdelay)
    intsimmer2 = SystemStatusData(delay = smdelay)
    intpfc = SystemStatusData(delay = smdelay)
    intglobal = SystemStatusData(delay = smdelay)
    keystate = SystemStatusData(delay = smdelay)
    flowstate = SystemStatusData(delay = smdelay)
    extqtrig = SystemStatusData(delay = smdelay)
    extqtrig2 = SystemStatusData(delay = smdelay)
    extlamptrig = SystemStatusData(delay = smdelay)
    extlamptrig2 = SystemStatusData(delay = smdelay)
    interlockslatched = SystemStatusData(delay = smdelay)

    lamp1enabled = FunctionStatusData(delay = fmdelay)
    lamp2enabled = FunctionStatusData(delay = fmdelay)
    q1enabled = FunctionStatusData(delay = fmdelay)
    q2enabled = FunctionStatusData(delay = fmdelay)
    fldelayneg = FunctionStatusData(delay = fmdelay)
    repdiv1 = FunctionStatusData(delay = fmdelay)
    repdiv2 = FunctionStatusData(delay = fmdelay)
    burst1 = FunctionStatusData(delay = fmdelay)
    burst2 = FunctionStatusData(delay = fmdelay)
    trigmode = FunctionStatusData(delay = fmdelay)
    lowfreq1 = FunctionStatusData(delay = fmdelay)
    lowfreq2 = FunctionStatusData(delay = fmdelay)
    shutterinhibit = FunctionStatusData(delay = fmdelay)
    strikelamp1 = FunctionStatusData(delay = fmdelay)
    strikelamp2 = FunctionStatusData(delay = fmdelay)
    tempwrong = FunctionStatusData(delay = fmdelay)

    currentlampshotsvalue = LampShotData(delay = 0.1)
    currentlampshotsvalue2 = LampShotData(delay = 0.1)

    watertemperature = ChillerData(0, delay = 1)
    ambienttemperature = ChillerData(2, delay = 1)
    chillersetpoint = ChillerData(4, delay = 1)
    fanspeed = ChillerData(6, delay = 1)
    xtaltemperature = ChillerData(7, delay = 1)
    xtalsetpoint = ChillerData(9, delay = 1)


    def __init__(self, com_port):
        super(Yag, self).__init__()
        self.device = pulsedLaser()
        self.Change += self.handler
        self.PortNumber = com_port

    def handler(self, source, args):
        if args.PropertyName == 'SystemStatus':
            for value, name in zip(Enum.GetValues(self.SystemStatusMasks_Lamp), Enum.GetNames(self.SystemStatusMasks_Lamp)):
                exec(f'self.{name.strip("sm").lower()} = self.SystemStatus & {value} > 0')
        elif args.PropertyName == 'FunctionStatusData':
            for value, name in zip(Enum.GetValues(self.FunctionStatusDataMasks), Enum.GetNames(self.FunctionStatusDataMasks)):
                exec(f'self.{name.strip("fm").lower()} = self.FunctionStatusData & {value} > 0')
        elif args.PropertyName == 'LampShotsValue':
            self.currentlampshotsvalue = self.CurrentLampShotsValue
            self.currentlampshotsvalue2 = self.CurrentLampShotsValue2
        elif args.PropertyName == 'ChillerWaterTemperature':
            self.watertemperature = yag.ChillerWaterTemperature
        elif args.PropertyName == 'ChillerAmbientTemperature':
            self.ambienttemperature = yag.ChillerAmbientTemperature
        elif args.PropertyName == 'ChillerSetpoint':
            self.chillersetpoint = yag.ChillerSetpoint
        elif args.PropertyName == 'ChillerFanSpeed':
            self.fanspeed = yag.ChillerFanSpeed
        elif args.PropertyName == 'ChillerXtalTemperature':
            self.xtaltemperature = yag.ChillerXtalTemperature
        elif args.PropertyName == 'ChillerXtalSetPoint':
            self.xtalsetpoint = yag.ChillerXtalSetPoint
        else:
            print(args.PropertyName)


class NanoLG:
    def __init__(self, time_offset, com_port):
        """
        Control class for the Nano LG pulsed laser using the supplied .net 2.0
        dll.
        """
        self.time_offset = time_offset

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f8'
        self.shape = (15, )

        self.warnings = []

        self.yag = YagData(com_port)
        self.yag.OpenPort = True
        self.yag.RequestSystemData()
        self.yag.RequestConfigurationData()
