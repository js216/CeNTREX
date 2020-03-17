import time
import serial
import logging
import threading
import functools
import numpy as np
from windfreak import SynthHD

class StoppableThread(threading.Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""

    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

class PowerSweep(StoppableThread):
    """
    Power sweep in separate thread to ensure continous data acquisition
    simultaneous to sweeping microwave power.
    """
    def __init__(self, driver, powers, wait_time):
        super(PowerSweep, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.powers = powers
        self.wait_time = wait_time

    def SetPower(self, power):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.SetPower(power)
                break
            except serial.SerialTimeoutException:
                continue

    def run(self):
        self.driver.running_sweep = True
        while True:
            for power in self.powers:
                self.SetPower(power)
                time.sleep(self.wait_time)
                if self.stopped():
                    logging.warning("SyntHDPro info: stopped sweeping")
                    self.driver.running_sweep = False
                    return

class FrequencySweep(StoppableThread):
    """
    Mirror sweep in a separate thread to ensure continous data acquisition
    simultaneous to sweeping the mirror.
    """
    def __init__(self, driver, start_frequency, stop_frequency, frequency_step,
                 wait_time):
        super(FrequencySweep, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.start_frequency = start_frequency
        self.stop_frequency = stop_frequency
        self.frequency_step = frequency_step
        self.wait_time = wait_time
        self.frequencies = np.arange(start_frequency, stop_frequency+frequency_step,
                                     frequency_step)

    def SetFrequency(self, frequency):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.SetFrequency(frequency)
                break
            except serial.SerialTimeoutException:
                continue

    def run(self):
        self.driver.running_sweep = True
        while True:
            for frequency in self.frequencies:
                self.SetFrequency(frequency)
                time.sleep(self.wait_time)
                if self.stopped():
                    logging.warning("SyntHDPro info: stopped sweeping")
                    self.driver.running_sweep = False
                    return
            for frequency in self.frequencies[1:-1][::-1]:
                self.SetFrequency(frequency)
                time.sleep(self.wait_time)
                if self.stopped():
                    logging.warning("SyntHDPro info: stopped sweeping")
                    self.driver.running_sweep = False
                    return

class FrequencySweepPowerPulsed(StoppableThread):
    """
    Mirror sweep in a separate thread to ensure continous data acquisition
    simultaneous to sweeping the mirror.
    """
    def __init__(self, driver, start_frequency, stop_frequency, frequency_step,
                 wait_time, power_high, power_low, pulse_count):
        super(FrequencySweepPowerSwitching, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.start_frequency = start_frequency
        self.stop_frequency = stop_frequency
        self.frequency_step = frequency_step
        self.wait_time = wait_time
        self.frequencies = np.arange(start_frequency, stop_frequency+frequency_step,
                                     frequency_step)
        self.power_high = power_high
        self.power_low = power_low
        self.pulse_count = pulse_count

    def SetFrequency(self, frequency):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.SetFrequency(frequency)
                break
            except serial.SerialTimeoutException:
                continue

    def SetPower(self, power):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.SetPower(power)
                break
            except serial.SerialTimeoutException:
                continue

    def run(self):
        self.driver.running_sweep = True
        while True:
            for frequency in self.frequencies:
                self.SetFrequency(frequency)
                for _ in range(self.pulse_count):
                    self.SetPower(self.power_high)
                    time.sleep(self.wait_time/self.pulse_count/2)
                    self.SetPower(self.power_low)
                    time.sleep(self.wait_time/self.pulse_count/2)
                if self.stopped():
                    logging.warning("SyntHDPro info: stopped sweeping")
                    self.driver.running_sweep = False
                    return
            for frequency in self.frequencies[1:-1][::-1]:
                self.SetFrequency(frequency)
                for _ in range(self.pulse_count):
                    self.SetPower(self.power_high)
                    time.sleep(self.wait_time/self.pulse_count/2)
                    self.SetPower(self.power_low)
                    time.sleep(self.wait_time/self.pulse_count/2)
                if self.stopped():
                    logging.warning("SyntHDPro info: stopped sweeping")
                    self.driver.running_sweep = False
                    return

def SweepCheckWrapper(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].running_sweep:
            warning = '{0} : Currently sweeping, unable to set position'.format(func.__name__)
            logging.warning('SynthHDPro warning in'+warning)
            args[0].CreateWarning(warning)
        else:
            return func(*args, **kwargs)
    return wrapper

class SynthHDProFrequencySweep:
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset
        self.COM_port = COM_port

        self.dtype = ('f4', 'float', 'float')
        self.shape = (2,)

        try:
            self.synth = SynthHD(COM_port)
        except Exception as err:
            logging.warning('SynthHDPro error in initial connection : '+str(err))
            self.verification_string = "False"
            self.__exit__()
            return

        try:
            if self.synth.hardware_version == 'Hardware Version 1.4a':
                self.verification_string = "True"
            else:
                self.verification_string = "False"
        except Exception as err:
            logging.warning('SynthHDPro error in device verification : '+str(err))

        self.warnings = []

        self.running_sweep = False
        self.sweep_thread = None

        self.sweep_params = {'start_frequency':None, 'stop_frequency':None,
                             'frequency_step':None, 'wait_time':None}
        self.new_attributes = []

        self.frequency_setting = self.GetFrequency()
        self.power_setting = self.GetPower()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self.running_sweep:
                self.sweep_thread.stop()
            try:
                self.synth.close()
            except:
                return
        except:
            return

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################

    def CreateWarning(self, warning):
        warning_dict = { "message" : warning}
        self.warnings.append([time.time(), warning_dict])

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        try:
            val = [
                    time.time() - self.time_offset,
                    self.frequency_setting,
                    self.power_setting
                   ]
            return val
        except serial.SerialTimeoutException:
            return time.time() -self.time_offset, np.nan, np.nan

    def SweepStatus(self):
        if self.running_sweep:
            return 'Sweeping'
        elif not self.running_sweep:
            return 'Inactive'
        else:
            return 'invalid'

    @SweepCheckWrapper
    def SetFrequencyGUI(self, frequency):
        self.SetFrequency(frequency)

    @SweepCheckWrapper
    def SetPowerGUI(self, power):
        self.SetPower(power)

    @SweepCheckWrapper
    def SetSweepStartGUI(self, start):
        self.sweep_params['start_frequency'] = start

    @SweepCheckWrapper
    def SetSweepStopGUI(self, stop):
        self.sweep_params['stop_frequency'] = stop

    @SweepCheckWrapper
    def SetSweepStepGUI(self, step):
        self.sweep_params['frequency_step'] = step

    @SweepCheckWrapper
    def SetSweepWaitGUI(self, wait):
        self.sweep_params['wait_time'] = wait

    @SweepCheckWrapper
    def SetTriggerMode(self, mode):
        self.trigger_mode = mode

    def SetSweepTimeStep(self, step_time):
        self.write('sweep_time_step', step_time)

    def GetFrequencyGUI(self):
        return self.frequency_setting

    def GetPowerGUI(self):
        return self.power_setting

    def FrequencySweep(self):
        if self.running_sweep:
            warning = 'Sweep: Currently sweeping frequency'
            self.CreateWarning(warning)
            logging.warning('SynthHDPro warning in Sweep: Currently sweeping frequency')
        else:
            # self.sweep_thread = FrequencySweepPowerSwitching(self, **self.sweep_params, power_low = -18, power_high = -10, pulse_count = 1)
            self.sweep_thread = FrequencySweep(self, **self.sweep_params)
            self.sweep_thread.start()

    def PowerSweep(self, parameters):
        if self.running_sweep:
            warning = 'Sweep: Currently sweeping power'
            self.CreateWarning(warning)
            logging.warning('SynthHDPro warning in PowerSweep: Currently sweeping')
        else:
            if not isinstance(parameters, list):
                logging.warning('SynthHDPro warning in PowerSweep: list required for parameters')
            else:
                self.sweep_thread = PowerSweep(self, *parameters)
                self.sweep_thread.start()

    def StopSweep(self):
        if self.running_sweep:
            self.sweep_thread.stop()
            self.sweep_thread = None
            self.running_sweep = False
        else:
            warning = 'StopSweep: No sweep running'
            self.CreateWarning(warning)
            logging.warning("SynthHDPro warning in StopSweep: No sweep running")

    #######################################################
    # Commands for device
    #######################################################

    def SetFrequency(self, frequency):
        try:
            self.synth[0].frequency = frequency
            self.frequency_setting = frequency
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetFrequency() : frequency out of range")
        except serial.SerialTimeoutException:
            self.synth[0].frequency = frequency
        except Exception as err:
            logging.warning("SynthHDPro warning in SetFrequency() : "+str(err))
            pass

    def SetPower(self, power):
        try:
            self.synth[0].power = power
            self.power_setting = power
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetPower() : power out of range")
        except Exception as err:
            logging.warning("SynthHDPro warning in SetPower() : "+str(err))

    def GetFrequency(self):
        return self.synth[0].frequency

    def GetPower(self):
        return self.synth[0].power

    def Enable(self):
        self.synth[0].enable = True

    def Disable(self):
        self.synth[0].enable = False

    def GetSweepStart(self):
        return self.sweep_params['start_frequency']

    def GetSweepStop(self):
        return self.sweep_params['stop_frequency']

    def GetSweepStep(self):
        return self.sweep_params['frequency_step']

    def GetSweepWait(self):
        return self.sweep_params['wait_time']
