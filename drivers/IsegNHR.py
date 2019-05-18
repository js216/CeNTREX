import time
import logging
import pyvisa
import numpy as np
import functools

def QueryVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('IsegNHR warning in {0}() : '.format(func.__name__) \
                        +str(err))
            return np.nan
    return wrapper

def WriteVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('IsegNHR warning in {0}() : '.format(func.__name__) \
                            +str(err))
    return wrapper

def ArgumentListToString(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        args_tmp = []
        arg_list = False
        for arg in args:
            if isinstance(arg, list):
                args_tmp.append(','.join([str(a) for a in arg]))
                arg_list = True
            else:
                args_tmp.append(arg)
        if arg_list:
            val = func(*args_tmp, **kwargs)
            if isinstance(val, str):
                return val.split(',')
            return val

        else:
            return func(*args_tmp, **kwargs)
    return wrapper

class ConvertToType(object):
    def __init__(self, t):
        self.type = t

    def __call__(self, func, *args, **kwargs):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            value = func(*args, **kwargs)
            if isinstance(value, list):
                for idx, val in enumerate(value):
                    value[idx] = self.type(val)
            else:
                return self.type(value)
            return value
        return wrapper

class ConvertToNumber(object):
    def __init__(self, *units):
        self.units = units

    def __call__(self, func, *args, **kwargs):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            value = func(*args, **kwargs)
            if isinstance(value, str):
                for unit in self.units:
                    value = value.strip(unit)
                value = float(value)
            if isinstance(value, list):
                for idx, val in enumerate(value):
                    for unit in self.units:
                        value[idx] = val.strip(unit)
                    value[idx] = float(value[idx])
            return value
        return wrapper

class IsegNHR:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (14, )

        self.warnings = []

        try:
            self.instr = self.rm.open_resource(resource_name)
            self.instr.parity = pyvisa.constants.Parity.none
            self.instr.baud_rate = 9600
            self.instr.stop_bits = pyvisa.constants.StopBits.one
            self.instr.timeout = 200
            self.instr.read_termination = '\r\n'
            self.instr.write_termination = '\r\n'

        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return

        self.verification_string = self.IDN().split(',')[1]

        self.module_status = {
                                0:'Fine adjustment off',
                                4:'Service required',
                                5:'isHwVLgd',
                                6:'Input Error',
                                8:'Module without failure',
                                9:'No ramp active',
                                10:'Safety loop closed',
                                11:'Any event active and mask set',
                                12:'Module in good state',
                                13:'Power supply good',
                                14:'Temperature good',
                                15:'Kill enabled'
                            }
        self.channel_status = {
                                0:'Positive',
                                2:'Input Error',
                                3:'On',
                                4:'Ramp',
                                5:'Emergency off',
                                6:'Controlled current',
                                7:'Controlled voltage',
                                8:'Low current range',
                                10:'Current bound exceeded',
                                11:'Voltage bound exceeded',
                                12:'External inhibit',
                                13:'Trip exceeded',
                                14:'Current limit exceeded',
                                15:'Voltage limit exceeded'
                            }

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        if self.instr:
            self.instr.close()

    def query(self, command):
        cmd = self.instr.query(command)
        if cmd == command:
            response =self.instr.read()
        else:
            response = np.nan
        return response

    def write(self, command):
        cmd = self.instr.query(command)

    #######################################################
    # CeNTREX DAQ Functions
    #######################################################

    def ReadValue(self):
        v = self.MeasureVoltage([0,1,2,3])
        c = self.MeasureCurrent([0,1,2,3])
        p = self.ReadConfigureOutputPolarity([0,1,2,3])
        p = [0 if po == 'n' else 1 for po in p]
        t = self.ReadModuleTemperature()

        return [time.time()-self.time_offset]+v+c+p+[t]

    def CheckWarnings(self):
        mod_stat = self.ReadModuleStatus()
        bit_values = [mod_stat >> i & 1 for i in range(16)]
        for idx in [8,10,12,13,14]:
            if not bit_values[idx]:
                warning_dict = { "message" : "{} failure".format(self.module_status[idx])}
                self.warnings.append(warning_dict)

        chan_stat = self.ReadChannelStatus([0,1,2,3])
        for idc, chan in enumerate(chan_stat):
            bit_values = [chan >> i & 1 for i in range(16)]
            for idx in [5,10,11,12,13,14,15]:
                if bit_values[idx]:
                    warning_dict = { "message" : "CH{} {}".format(idc, self.channel_status[idx])}
                    self.warnings.append(warning_dict)

    def GetWarnings(self):
        self.CheckWarnings()
        warnings = self.warnings
        self.warnings = []
        return warnings

    def PMTSettings(self):
        for idx, val in enumerate(self.ReadVoltageOn([0,1,2,3])):
            if val:
                logging.warning('IsegNHR warning in PMTSettings() : CH{} still on'.format(idx))
                warning_dict = { "message" : "PMTSettings failure; CH{} still on".format(idx)}
                self.warnings.append(warning_dict)
                return

        self.ConfigureOutputPolarity('n', [0,1,2,3])
        self.ConfigureRampVoltageUp(20, [0,1,2,3])
        self.ConfigureRampVoltageDown(20, [0,1,2,3])
        self.SetVoltage(1000, [0,1,2,3])
        for idc, val in enumerate(self.ReadConfigureOutputPolarity([0,1,2,3])):
            if val != 'n':
                logging.warning('IsegNHR warning in PMTSettings() : CH{} wrong polarity; {}'.format(idc, val))
                warning_dict = { "message" : "CH{} wrong polarity; {}".format(idc, val)}
                self.warnings.append(warning_dict)
        for idc, val in enumerate(self.ReadConfigureRampVoltageUp([0,1,2,3])):
            if val != 20:
                logging.warning('IsegNHR warning in PMTSettings() : CH{} wrong ramp up; {} V/s'.format(idc, val))
                warning_dict = { "message" : "CH{} wrong ramp up; {} V/s".format(idc, val)}
                self.warnings.append(warning_dict)

        for idc, val in enumerate(self.ReadConfigureRampVoltageDown([0,1,2,3])):
            if val != 20:
                logging.warning('IsegNHR warning in PMTSettings() : CH{} wrong ramp down; {} V/s'.format(idc, val))
                warning_dict = { "message" : "CH{} wrong ramp down; {} V/s".format(idc, val)}
                self.warnings.append(warning_dict)

        for idc, val in enumerate(self.ReadVoltage([0,1,2,3])):
            if np.abs(val) != 1000:
                logging.warning('IsegNHR warning in PMTSettings() : CH{} wrong set voltage; {} V'.format(idc, val))
                warning_dict = { "message" : "CH{} wrong set voltage; {} V".format(idc, val)}
                self.warnings.append(warning_dict)

    def AllChannelsOn(self):
        self.ChannelOn([0,1,2,3])

    def AllChannelsOff(self):
        self.ChannelOff([0,1,2,3])

    def ConfigureOutputPolarity0(self, p):
        if self.ReadVoltageOn(0):
            logging.warning('IsegNHR warning in ConfigureOutputPolarity() : CH0 still on')
            warning_dict = { "message" : "Polarity change failure; CH0 still on"}
            self.warnings.append(warning_dict)
            return
        else:
            v = self.ReadVoltage(0)
            self.ConfigureOutputPolarity(p, 0)
            time.sleep(0.1)
            self.SetVoltage(np.abs(v),0)

    def ConfigureOutputPolarity1(self, p):
        if self.ReadVoltageOn(1):
            logging.warning('IsegNHR warning in ConfigureOutputPolarity() : CH1 still on')
            warning_dict = { "message" : "Polarity change failure; CH1 still on"}
            self.warnings.append(warning_dict)
        else:
            v = self.ReadVoltage(1)
            self.ConfigureOutputPolarity(p, 1)
            time.sleep(0.1)
            self.SetVoltage(np.abs(v),1)

    def ConfigureOutputPolarity2(self, p):
        if self.ReadVoltageOn(2):
            logging.warning('IsegNHR warning in ConfigureOutputPolarity() : CH2 still on')
            warning_dict = { "message" : "Polarity change failure; CH2 still on"}
            self.warnings.append(warning_dict)
        else:
            v = self.ReadVoltage(2)
            self.ConfigureOutputPolarity(p, 2)
            time.sleep(0.1)
            self.SetVoltage(np.abs(v),2)

    def ConfigureOutputPolarity3(self, p):
        if self.ReadVoltageOn(3):
            logging.warning('IsegNHR warning in ConfigureOutputPolarity() : CH3 still on')
            warning_dict = { "message" : "Polarity change failure; CH3 still on"}
            self.warnings.append(warning_dict)
        else:
            v = self.ReadVoltage(3)
            self.ConfigureOutputPolarity(p, 3)
            time.sleep(0.1)
            self.SetVoltage(np.abs(v),3)

    def SetVoltage0(self, v):
        self.SetVoltage(v, 0)

    def SetVoltage1(self, v):
        self.SetVoltage(v, 1)

    def SetVoltage2(self, v):
        self.SetVoltage(v, 2)

    def SetVoltage3(self, v):
        self.SetVoltage(v, 3)

    def ChannelOn0(self):
        self.ChannelOn(0)

    def ChannelOn1(self):
        self.ChannelOn(1)

    def ChannelOn2(self):
        self.ChannelOn(2)

    def ChannelOn3(self):
        self.ChannelOn(3)

    def ChannelOff0(self):
        self.ChannelOff(0)

    def ChannelOff1(self):
        self.ChannelOff(1)

    def ChannelOff2(self):
        self.ChannelOff(2)

    def ChannelOff3(self):
        self.ChannelOff(3)

    def IsegStatus(self):
        ch_on = np.sum(self.ReadVoltageOn([0,1,2,3]))
        if ch_on == 4:
            return 'All PMT On'
        elif ch_on >= 1:
            return 'PMT On'
        elif ch_on == 0:
            return 'PMT Off'
        else:
            return 'invalid'

    #######################################################
    # Common Instruction Set
    #######################################################

    @QueryVisaIOError
    def IDN(self):
        return self.query('*IDN?')

    @WriteVisaIOError
    def CLS(self):
        self.write('*CLS')

    @WriteVisaIOError
    def RST(self):
        self.write('*RST')

    @QueryVisaIOError
    def INSTR(self):
        return self.query('*INSTR?')

    #######################################################
    # ISEG SCPI Instruction Set
    #######################################################

    #######################################################
    # Read Submenu
    #######################################################

    # Function not available on our unit
    # def ReadChannelTemperature(self, channel):
    #     return self.query(':READ:CHAN:TEMP? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltage(self, channel):
        return self.query(':READ:VOLT? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltageLimit(self, channel):
        return self.query(':READ:VOLT:LIM? (@{})'.format(channel))

    @ConvertToNumber('V')
    @QueryVisaIOError
    def ReadVoltageNominal(self, channel):
        return self.query(':READ:VOLT:NOM? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltageBounds(self, channel):
        return self.query(':READ:VOLT:BOU? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltageMode(self, channel):
        return self.query(':READ:VOLT:MODE? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltageModeList(self, channel):
        return self.query(':READ:VOLT:MODE:LIST? (@{})'.format(channel))

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadVoltageOn(self, channel):
        return self.query(':READ:VOLT:ON? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrent(self, channel):
        return self.query(':READ:CURR? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrentLimit(self, channel):
        return self.query(':READ:CURR:LIM? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrentNominal(self, channel):
        return self.query(':READ:CURR:NOM? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrentMode(self, channel):
        return self.query(':READ:CURR:MODE? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrentModeList(self, channel):
        return self.query(':READ:CURR:MODE:LIST? (@{})'.format(channel))

    @ConvertToNumber('C')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadCurrentBounds(self, channel):
        return self.query(':READ:CURR:BOU? (@{})'.format(channel))

    @ConvertToNumber('V/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampVolt(self, channel):
        return self.query(':READ:RAMP:VOLT? (@{})'.format(channel))

    @ConvertToNumber('V/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampVoltMin(self, channel):
        return self.query(':READ:RAMP:VOLT:MIN? (@{})'.format(channel))

    @ConvertToNumber('V/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampVoltMax(self, channel):
        returnself.query(':READ:RAMP:VOLT:MAX? (@{})'.format(channel))

    @ConvertToNumber('A/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampCurrent(self, channel):
        return self.query(':READ:RAMP:CURR? (@{})'.format(channel))

    @ConvertToNumber('A/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampCurrentMin(self, channel):
        return self.query(':READ:RAMP:CURR:MIN? (@{})'.format(channel))

    @ConvertToNumber('A/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadRampCurrentMax(self, channel):
        return self.query(':READ:RAMP:CURR:MAX? (@{})'.format(channel))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadChannelControl(self, channel):
        return self.query(':READ:CHAN:CONTR? (@{})'.format(channel))

    @ConvertToType(int)
    @ArgumentListToString
    @QueryVisaIOError
    def ReadChannelStatus(self, channel):
        return self.query(':READ:CHAN:STAT? (@{})'.format(channel))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadChannelEventStatus(self, channel):
        return self.query(':READ:CHAN:EV:STAT? (@{})'.format(channel))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadChannelEventMask(self, channel):
        return self.query(':READ:CHAN:EV:MASK? (@{})'.format(channel))

    #######################################################
    # Measure Submenu
    #######################################################

    @ConvertToNumber('V')
    @ArgumentListToString
    @QueryVisaIOError
    def MeasureVoltage(self, channel):
        return self.query(':MEAS:VOLT? (@{})'.format(channel))

    @ConvertToNumber('A')
    @ArgumentListToString
    @QueryVisaIOError
    def MeasureCurrent(self, channel):
        return self.query(':MEAS:CURR? (@{})'.format(channel))

    #######################################################
    # Configure Submenu
    #######################################################

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureTripTime(self, time, channel):
        self.write(':CONF:TRIP:TIME {},(@{})'.format(time, channel))

    @ConvertToNumber('ms')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureTripTime(self, channel):
        return self.query(':CONF:TRIP:TIME? (@{})'.format(channel))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureTripAction(self, action):
        self.write(':CONF:TRIP:ACT {}'.format(action))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureTripAction(self, channel):
        return int(self.query(':CONF:TRIP:ACT? (@{})'.format(channel)))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureInhibitAction(self, action):
        self.write(':CONF:INH:ACT {}'.format(action))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureInhibitAction(self, channel):
        return int(self.query(':CONF:INH:ACT? (@{})'.format(channel)))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureOutputPolarity(self, polarity, channel):
        self.write(':CONF:OUTP:POL {}, (@{})'.format(polarity, channel))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureOutputPolarity(self, channel):
        return self.query(':CONF:OUTP:POL? (@{})'.format(channel))

    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureOutputPolarityList(self, channel):
        return self.query(':CONF:OUTP:POL:LIST? (@{})'.format(channel))

    @WriteVisaIOError
    def ConfigureRampVoltage(self, ramp):
        self.write(':CONF:RAMP:VOLT {}'.format(ramp))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureRampVoltageUp(self, ramp, channel):
        self.write(':CONF:RAMP:VOLT:UP {},(@{})'.format(ramp, channel))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureRampVoltageDown(self, ramp, channel):
        self.write(':CONF:RAMP:VOLT:UP {},(@{})'.format(ramp, channel))

    @WriteVisaIOError
    def ConfigureRampCurrent(self, ramp):
        self.write(':CONF:RAMP:CURR {}'.format(ramp))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureRampCurrentUp(self, ramp, channel):
        self.write(':CONF:RAMP:CURR:UP {},(@{})'.format(ramp, channel))

    @ArgumentListToString
    @WriteVisaIOError
    def ConfigureRampCurrentDown(self, ramp, channel):
        self.write(':CONF:RAMP:CURR:UP {},(@{})'.format(ramp, channel))

    @WriteVisaIOError
    def ConfigureAverage(self, steps):
        self.write(':CONF:AVER {}'.format(steps))

    @WriteVisaIOError
    def ConfigureKill(self, kill):
        self.write(':CONF:KILL {}'.format(kill))

    @WriteVisaIOError
    def ConfigureAdjust(self, adjust):
        self.write(':CONF:ADJ {}'.format(adjust))

    @ConvertToNumber('%/s')
    @QueryVisaIOError
    def ReadConfigureRampVoltage(self):
        return self.query(':CONF:RAMP:VOLT?')

    @ConvertToNumber('V/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureRampVoltageUp(self, channel):
        return self.query(':CONF:RAMP:VOLT:UP? (@{})'.format(channel))

    @ConvertToNumber('V/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureRampVoltageDown(self, channel):
        return self.query(':CONF:RAMP:VOLT:DOWN? (@{})'.format(channel))

    @ConvertToNumber('%/s')
    @QueryVisaIOError
    def ReadConfigureRampCurrent(self):
        return self.query(':CONF:RAMP:CURR?')

    @ConvertToNumber('A/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureRampCurrentUp(self, channel):
        return self.query(':CONF:RAMP:CURR:UP? (@{})'.format(channel))

    @ConvertToNumber('A/s')
    @ArgumentListToString
    @QueryVisaIOError
    def ReadConfigureRampCurrentDown(self, channel):
        return self.query(':CONF:RAMP:CURR:DOWN? (@{})'.format(channel))

    @QueryVisaIOError
    def ReadConfigureAverage(self):
        return int(self.query(':CONF:AVER?'))

    @QueryVisaIOError
    def ReadConfigureKill(self):
        return int(self.query(':CONF:KILL?'))

    @QueryVisaIOError
    def ReadConfigureAdjust(self):
        return int(self.query(':CONF:ADJ?'))

    #######################################################
    # Module Submenu
    #######################################################

    @QueryVisaIOError
    def ReadModuleControl(self):
        return int(self.query(':READ:MOD:CONT?'))

    @QueryVisaIOError
    def ReadModuleStatus(self):
        return int(self.query(':READ:MOD:STAT?'))

    @QueryVisaIOError
    def ReadModuleEventStatus(self):
        return int(self.query(':READ:MOD:EV:STAT?'))

    @QueryVisaIOError
    def ReadModuleEventMask(self):
        return int(self.query(':READ:MOD:EV:MASK?'))

    @QueryVisaIOError
    def ReadModuleEventChannelStatus(self):
        return int(self.query(':READ:MOD:EV:CHANSTAT?'))

    @QueryVisaIOError
    def ReadModuleEventChannelMask(self):
        return int(self.query(':READ:MOD:EV:CHANMASK?'))

    @ConvertToNumber('V')
    @QueryVisaIOError
    def ReadModuleSupplyP24V(self):
        return self.query(':READ:MOD:SUP:P24V?')

    @ConvertToNumber('V')
    @QueryVisaIOError
    def ReadModuleSupplyN24V(self):
        return self.query(':READ:MOD:SUP:N24V?')

    @ConvertToNumber('V')
    @QueryVisaIOError
    def ReadModuleSupplyP5V(self):
        return self.query(':READ:MOD:SUP:P5V?')

    @ConvertToNumber('C')
    @QueryVisaIOError
    def ReadModuleTemperature(self):
        return self.query(':READ:MOD:TEMP?')

    def ReadModuleChannels(self):
        return self.query(':READ:MOD:CHAN?')
    #######################################################
    # Set Voltage
    #######################################################

    @ArgumentListToString
    @WriteVisaIOError
    def SetVoltage(self, voltage, channel):
        self.write(':VOLT {},(@{})'.format(voltage, channel))

    @ArgumentListToString
    @WriteVisaIOError
    def ChannelOn(self, channel):
        self.write(':VOLT ON,(@{})'.format(channel))

    @ArgumentListToString
    @WriteVisaIOError
    def ChannelOff(self, channel):
        self.write(':VOLT OFF,(@{})'.format(channel))
