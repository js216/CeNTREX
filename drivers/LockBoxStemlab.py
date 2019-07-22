from pyrpl import Pyrpl
import numpy as np
import time
import logging
import traceback

class LockBoxStemlab:
    def __init__(self, time_offset, hostname, config = 'LockBox', reloadfpga = False):
        self.time_offset = time_offset

        self.reloadfpga = bool(reloadfpga)

        try:
            self.p = Pyrpl(hostname = hostname, config = config, gui = False,
                           reloadfpga = self.reloadfpga)
            self.rp = self.p.rp
            self.verification_string = 'True'
        except Exception as err:
            logging.warning("LockBoxStemlab error in __init__(): "+str(err))
            self.verification_string = 'False'
            print(traceback.print_exc())
            return
        self.rp.scope.decimaton = 2**8

        self._setup()


        self.new_attributes = []

        self.dtype = 'f8'
        self.shape = (1, 2, self.scope_params['data_length'])

        self.warnings = []

    def _setup(self):
        if self.reloadfpga:
            self._init_fpga()
        self._init_ramp_params()
        self._init_pid_params()
        self._init_scope_params()

    def _init_fpga(self):
        logging.warning('Loading FPGA registers')
        # Function generator default settings
        self.rp.asg0.amplitude = 0.5
        self.rp.asg0.frequency = 50
        self.rp.asg0.output_direct = 'out1'
        self.rp.asg0.trigger_source = 'immediately'
        self.rp.asg0.on = True

        # PID default settings
        self.rp.pid0.input = 'in1'
        self.rp.pid0.p = -1
        self.rp.pid0.i = 0
        self.rp.pid0.ival = 0
        self.rp.pid0.output_direct = 'off'

        # Scope default settings
        self.rp.scope.input1 = 'asg0'
        self.rp.scope.input2 = 'in1'
        self.rp.scope.trigger_source = 'ch1_positive_edge'
        self.rp.scope.duration = 1/self.rp.asg0.frequency

    def _init_ramp_params(self):
        params = ['frequency', 'amplitude', 'offset', 'waveform', 'output_direct',
                  'trigger_source', 'on']
        self.ramp = self.rp.asg0
        self.ramp_params = dict([(param, None) for param in params])
        for param in params:
            self.ramp_params[param] = eval('self.rp.asg0.'+param)

    def _init_pid_params(self):
        params = ['input', 'proportional', 'integral', 'inputfilter', 'output_direct',
                  'min_voltage', 'max_voltage', 'setpoint']
        self.pid = self.rp.pid0
        self.pid_params = dict([(param, None) for param in params])
        for param in params:
            self.pid_params[param] = eval('self.rp.pid0.'+param)

    def _init_scope_params(self):
        params = ['input1', 'input2', 'trigger_source',
                  'trigger_delay', 'data_length', 'duration']
        self.scope = self.rp.scope
        self.scope_params = dict([(param, None) for param in params])
        for param in params:
            self.scope_params[param] = eval('self.rp.scope.'+param)

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
        return [d, [{'name':'test'}]]

    ##############################
    # Commands
    ##############################

    # Ramp Commands

    def RampFrequency(self, frequency):
        self.ramp.frequency = float(frequency)
        self.ramp_params['frequency'] = float(frequency)

    def RampAmplitude(self, amplitude):
        self.ramp.amplitude = float(amplitude)
        self.ramp_amplitude['frequency'] = float(amplitude)

    def RampOffset(self, offset):
        self.ramp.offset = float(offset)
        self.ramp_params['offset'] = float(offset)

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
        self.pid_params['setpoint'] = float(setpoint)

    def PIDProportional(self, proportional):
        self.pid.proportional = float(proportional)
        self.pid_params['proportional'] = float(proportional)

    def PIDIntegral(self, integral):
        self.pid.integral = float(integral)
        self.pid_params['integral'] = float(integral)

    def PIDReset(self):
        self.pid.ival = 0

    # Lock commands

    def LockCavity(self):
        self.ramp.output_direct = 'off'
        self.pid.output_direct = 'out1'

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
