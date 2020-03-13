import clr # pythonnet
import time
import logging
import threading
from System import Enum
clr.AddReference('drivers/Litron.Control.PulsedLasers')
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
            assert instance.PortOpen, 'No connection to YAG'
            instance.Ping()
            while (time.time() - self._time > self._delay) or (isinstance(self._data, type(None))):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)

class FunctionStatusData(object):
    def __init__(self, data = None, delay = 300):
        self._data = data
        self._time = time.time()
        self._delay = delay

    def __get__(self, instance, owner):
        if (time.time() - self._time < self._delay) & (not isinstance(self._data, type(None))):
            return self._data
        else:
            assert instance.PortOpen, 'No connection to YAG'
            instance.RequestFunctionStatus()
            while (time.time() - self._time > self._delay) or (isinstance(self._data, type(None))):
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
        if (time.time() - self._time < self._delay) & (not isinstance(self._data, type(None)) or (self._data != 0)):
            return self._data
        else:
            assert instance.PortOpen, 'No connection to YAG'
            instance.RequestChillerData(self._enum)
            while (time.time() - self._time > self._delay) or (isinstance(self._data, type(None)) or (self._data == 0)):
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
            assert instance.PortOpen, 'No connection to YAG'
            instance.RequestFlashlampShots()
            while (time.time() - self._time > self._delay) or ((isinstance(self._data, type(None))) or (self._data == 0)):
                time.sleep(0.01)
            return self._data

    def __set__(self, instance, data):
        self._data = data
        self._time = time.time()

    def __repr__(self):
        return repr(self._data)

class Interlocks(object):
    def __init__(self):
        self._interlocks = {'water flow': 'intwaterflow',
                            'water level': 'intwaterlevel',
                            'water temperature': 'intwatertemp',
                            'lamp 1 PSU': 'intcharger1',
                            'lamp 2 PSU': 'intcharger2',
                            'external': 'intexternal',
                            'PSU temperature': 'intpsutemp',
                            'PSU cover': 'intpsucover',
                            'laser head cover': 'intlaserhead',
                            'shutter': 'intshutter',
                            'lamp 1': 'intsimmer1',
                            'lamp 2': 'intsimmer2',
                            'low frequency 1': 'lowfreq1',
                            'low frequency 2': 'lowfreq2',
                            'crystal temperature': 'tempwrong'}

    def __get__(self, instance, owner):
        assert instance.PortOpen, 'No connection to YAG'
        latched = []
        if instance.interlockslatched:
            for interlock, var in self._interlocks.items():
                if eval(f'instance.{var}') & (var != 'shutter'):
                    latched.append(interlock)
                elif (var == 'shutter') & (not eval(f'instance.{var}')):
                    latched.append(interlock)
            return latched
        else:
            return None

    def __repr__(self):
        return repr("NanoLG YAG interlock object")


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
    intpsutemp = SystemStatusData(delay = smdelay)
    intpsucover = SystemStatusData(delay = smdelay)
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
    totallampshotsvalue = LampShotData(delay = 0.1)
    totallampshotsvalue2 = LampShotData(delay = 0.1)

    watertemperature = ChillerData(0, delay = 1)
    ambienttemperature = ChillerData(2, delay = 1)
    chillersetpoint = ChillerData(4, delay = 1)
    fanspeed = ChillerData(6, delay = 1)
    xtaltemperature = ChillerData(7, delay = 1)
    xtalsetpoint = ChillerData(9, delay = 1)

    interlocks = Interlocks()

    def __init__(self, com_port):
        super(Yag, self).__init__()
        self.device = pulsedLaser()
        self.Change += self.handler
        if isinstance(com_port, str):
            com_port = int(com_port.lower().strip('com'))
        self.PortNumber = com_port

    def handler(self, source, args):
        try:
            if args.PropertyName == 'SystemStatus':
                for value, name in zip(Enum.GetValues(self.SystemStatusMasks_Lamp), Enum.GetNames(self.SystemStatusMasks_Lamp)):
                    exec(f'self.{name.strip("sm").lower()} = self.SystemStatus & {value} > 0')
            elif args.PropertyName == 'FunctionStatus':
                for value, name in zip(Enum.GetValues(self.FunctionStatusMasks), Enum.GetNames(self.FunctionStatusMasks)):
                    exec(f'self.{name.strip("fm").lower()} = self.FunctionStatus & {value} > 0')
            elif args.PropertyName == 'LampShotsValue':
                self.currentlampshotsvalue = self.CurrentLampShotsValue
                self.currentlampshotsvalue2 = self.CurrentLampShotsValue2
                self.totallampshotsvalue = self.TotalLampShotsValue
                self.totallampshotsvalue2 = self.TotalLampShotsValue2
            elif args.PropertyName == 'ChillerWaterTemperature':
                self.watertemperature = self.ChillerWaterTemperature
            elif args.PropertyName == 'ChillerAmbientTemperature':
                self.ambienttemperature = self.ChillerAmbientTemperature
            elif args.PropertyName == 'ChillerSetpoint':
                self.chillersetpoint = self.ChillerSetpoint
            elif args.PropertyName == 'ChillerFanSpeed':
                self.fanspeed = self.ChillerFanSpeed
            elif args.PropertyName == 'ChillerXtalTemperature':
                self.xtaltemperature = self.ChillerXtalTemperature
            elif args.PropertyName == 'ChillerXtalSetPoint':
                self.xtalsetpoint = self.ChillerXtalSetPoint
        except Exception as e:
            print(e)

class NanoLG(Yag):
    def __init__(self, time_offset, com_port):
        """
        Control class for the Nano LG pulsed laser using the supplied .net 2.0
        dll.
        """
        super(NanoLG, self).__init__(com_port)
        self.time_offset = time_offset

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f8'
        self.shape = (15, )

        self.warnings = []

        try:
            self.PortOpen = True
            self.RequestSystemData()
            self.RequestConfigurationData()
            self.verification_string = self.GetVerificationString()
        except Exception as err:
            logging.warning('NanoLG warning in initial connection : '+str(err))
            self.verification_string = "False"
            self.__exit__()
        self.warnings = []
        self.new_attributes = []
        self.dtype = ('f8',)
        self.shape = (15,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.CloseShutter()
            self.PortOpen = False
        except Exception as err:
            logging.warning('NanoLG warning in __exit__ : '+str(err))

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################
    def GetVerificationString(self):
        return self.get_SerialNumber()

    def GetWarnings(self):
        self.CheckInterlocks()
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        self.Ping()
        return [time.time() - self.time_offset,
                self.systemstate,
                self.pumpstate,
                self.laserstate,
                self.shutterstate,
                self.watertemperature,
                self.ambienttemperature,
                self.xtaltemperature,
                self.FLPeriodValue,
                self.QDelay1Value,
                self.currentlampshotsvalue,
                self.totallampshotsvalue,
                self.extqtrig,
                self.extlamptrig,
                self.interlockslatched,
                self.RepRateDivisor1Value
               ]

    #######################################################
    # General Utility Commands
    #######################################################

    def CheckInterlocks(self):
        if self.interlocks:
            for interlock in self.interlocks:
                warning_dict = {"message": f"NanoLG interlock : {interlock}"}
                self.warnings.append([time.time(), warning_dict])

    def SetQSwitchDelay(self, delay):
        self.LampAndQswData(self.FLPeriodValue, self.FLDelayValue, delay, delay, 0xF)

    def GetQSwitchDelay(self):
        return self.QDelay1Value

    def SetRepRateDivider(self, divider):
        self.RepRateDivide1(divider, bool(self.extqtrig))

    def EnableRepRateDivider(self, enable):
        self.RepRateDivide1(self.RepRateDivide1, enable)

    def SetSystemOn(self):
        self.SystemOn()

    def SetSystemOff(self):
        self.SystemOff()

    def GetSystemState(self):
        return str(self.systemstate)

    def SetPumpOn(self):
        self.PumpOn()

    def SetPumpOff(self):
        self.PumpOff()

    def GetPumpState(self):
        return str(self.pumpstate)

    def SetLaserOn(self):
        self.LaserOn()

    def SetLaserOff(self):
        self.LaserOff()

    def GetLaserState(self):
        return str(self.laserstate)

    def SetShutterOpen(self):
        self.ShutterOpen()

    def SetShutterClosed(self):
        self.ShutterClosed()

    def GetShutterState(self):
        return str(self.shutterstate)

    def EnableExtQTrig(self):
        self.DirectAccess1 = True

    def DisableExtQTrig(self):
        self.DirectAccess1 = False

    def EnableExtLampTrig(self):
        self.ExtTrig1 = True

    def DisableExtLampTrig(self):
        self.ExtTrig1 = False

    def GetExtLampTrig(self):
        return str(self.extlamptrig)

    def GetExtQTrig(self):
        return str(self.extqtrig)

    def GetSystemStatus(self):
        if self.interlockslatched:
            return "Interlocked"
        elif self.laserstate & self.shutterstate:
            return "Laser On"
        elif self.laserstate:
            return "Laser On/Shutter Closed"
        elif self.pumpstate:
            return "Pump On"
        elif self.systemstate:
            return "Pump Off"
        elif not self.systemstate:
            return "YAG Off"
        else:
            return "invalid"
