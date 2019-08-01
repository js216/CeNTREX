from stemlab import StemLab
import numpy as np
import time
import logging
import traceback

class LockBoxStemlab:
    def __init__(self, time_offset, hostname, reloadfpga = False):
        self.time_offset = time_offset
        self.reloadfpga = reloadfpga

        self.verification_string = 'False'
        try:
            self.rp = StemLab(hostname = hostname, reloadfpga = reloadfpga)
            self.verification_string = 'True'
        except Exception as err:
            logging.warning("LockBoxStemlab error in __init__(): "+str(err))
            self.verification_string = 'False'
            print(traceback.print_exc())
            return

        self._setup()

        self.new_attributes = []

        self.dtype = 'f8'
        self.shape = (1, 2, self.scope.data_length)

        self.warnings = []

    def _setup(self):
        if self.reloadfpga:
            self._init_fpga()
        self.rp.scope.decimaton = 2**8
        self._init_ramp_params()
        self._init_pid_params()
        self._init_scope_params()

    def _init_fpga(self):
        logging.warning('Loading FPGA registers')
        # Function generator default settings
        self.rp.asg0.amplitude = 0.5
        self.rp.asg0.frequency = 50
        self.rp.asg0.offset = 0.4
        self.rp.asg0.output_direct = 'out1'
        self.rp.asg0.trigger_source = 'immediately'
        self.rp.asg0.on = True

        # PID default settings
        self.rp.pid0.input = 'in1'
        self.rp.pid0.p = 5
        self.rp.pid0.i = 100
        self.rp.pid0.ival = 0
        self.rp.pid0.output_direct = 'off'
        self.rp.pid0.inputfilter = [1e5, 0, 0, 0]

        # Scope default settings
        self.rp.scope.input1 = 'asg0'
        self.rp.scope.input2 = 'in1'
        self.rp.scope.trigger_source = 'asg0'
        self.rp.scope.duration = 0.5*1/self.rp.asg0.frequency

    def _init_ramp_params(self):
        self.ramp = self.rp.asg0

    def _init_pid_params(self):
        self.pid = self.rp.pid0

    def _init_scope_params(self):
        self.scope = self.rp.scope

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    ##############################
    # CeNTREX DAQ Commands
    ##############################

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        self.scope._start_acquisition()
        while True:
            if self.scope.curve_ready():
                d = np.array([self.scope._get_curve()])
                break
        timestamp = time.time()-self.time_offset
        return [d, [{'timestamp':timestamp}]]

    ##############################
    # Commands
    ##############################

    # Ramp Commands

    def RampFrequency(self, frequency):
        self.ramp.frequency = float(frequency)

    def GetRampFrequency(self):
        return round(self.ramp.frequency,1)

    def RampAmplitude(self, amplitude):
        self.ramp.amplitude = float(amplitude)

    def GetRampAmplitude(self):
        return round(self.ramp.amplitude,3)

    def RampOffset(self, offset):
        if offset > 0.97:
            offset = 0.97
        elif offset < -0.97:
            offset = -0.97
        self.ramp.offset = float(offset)

    def GetRampOffset(self):
        return round(self.ramp.offset,3)

    def RampOn(self):
        self.pid.output_direct = 'off'
        self.ramp.output_direct = 'out1'

    def RampOff(self):
        self.ramp.output_direct = 'off'

    def RampStatus(self):
        if self.ramp.output_direct == 'out1':
            return 'On'
        elif not self.ramp.output_direct == 'out1':
            return 'Off'
        else:
            return 'invalid'

    # PID commands

    def PIDSetPoint(self, setpoint):
        self.pid.setpoint = float(setpoint)

    def GetPIDSetpoint(self):
        return round(self.pid.setpoint,3)

    def PIDProportional(self, proportional):
        self.pid.proportional = float(proportional)

    def GetPIDProportional(self):
        return round(self.pid.proportional,3)

    def PIDIntegral(self, integral):
        self.pid.integral = float(integral)

    def GetPIDIntegral(self):
        return round(self.pid.integral,3)

    def PIDIVal(self, ival):
        self.pid.ival = float(ival)

    def GetPIDIval(self):
        return round(self.pid.ival,3)

    def PIDReset(self):
        self.pid.ival = 0

    def PIDFilter(self, frequency):
        self.pid.inputfilter = [frequency, 0, 0, 0]

    def GetPIDFilter(self):
        return round(self.pid.inputfilter[0], 3)

    # Scope commands
    def ScopeTrigger(self, trigger_source):
        self.scope.trigger_source = trigger_source

    def ScopeCH1Input(self, input):
        self.scope.input1 = input

    def ScopeCH2Input(self, input):
        self.scope.input2 = input

    # Lock commands

    def LockCavity(self):
        self.ramp.output_direct = 'off'
        self.pid.output_direct = 'out1'
        self.pid.ival = 0

    def UnlockCavity(self):
        self.pid.output_direct = 'off'
        self.ramp.output_direct = 'out1'

    def LockStatus(self):
        if  (not self.ramp.output_direct == 'out1') & (self.pid.output_direct == 'out1'):
            return 'Locked'
        elif (self.ramp.output_direct == 'out1') & (not self.pid.output_direct == 'out1'):
            return 'Unlocked'
        elif (self.ramp_out_direct == 'out1') & (self.pid.output_direct == 'out1'):
            return 'Unlocked'
        else:
            return 'invalid'
