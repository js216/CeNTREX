import time
import logging
import threading
import numpy as np

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
    simultaneous to sweeping microwave and laser power.
    """
    def __init__(self, driver, sweep_params):
        super(PowerSweep, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.sweep_params = sweep_params

        self.microwave = sweep_params['microwave']
        self.laser     = sweep_params['laser']
        self.wait_time = sweep_params['wait_time']

    def run(self):
        """
        Loop structure:
            loop laser powers
            -> loop microwave powers
        """
        try:
            microwave_frequency = self.microwave['frequency']
            self.driver.parent[self.microwave['device']].commands.append(f'SetFrequency({microwave_fequency})')
            self.driver.parent[self.microwave['device']].commands.append(f'SetSweepTimeStep({self.microwave['time_step']})')
            self.driver.running_sweep = True
            # Iterating over laser powers and then setting up the SynthHD sweep to
            # trigger coincident with the rotational cooling shutter
            while True:
                for la_power in self.laser['powers']:
                    self.driver.parent[self.laser['device']].commands.append(self.laser['cmd'].replace('arg', la_power))
                    self.driver.laser_power = la_power
                    for mu_power in self.microwave['powers']:
                        # define the low microwave power
                        mu_low = self.microwave['power_low']
                        # set the default microwave power to the high value
                        self.driver.parent[self.microwave['device']].commands.append(self.microwave['cmd'].replace('arg', mu_power))
                        # disable the sweep trigger
                        self.driver.parent[self.microwave['device']].commands.append('SetTriggerMode("disabled")')
                        # generate the sweep list, starting at high powers
                        sweep_list = f"LdL0f{microwave_frequency}L0a{mu_power}L1f{microwave_frequency}L1a{mu_low}"
                        self.driver.parent[self.microwave['device']].commands.append(f'_write({sweep_list})')
                        # set the trigger to activate the full frequency sweep
                        # activated when trigger is pulled low
                        self.driver.parent[self.microwave['device']].commands.append('SetTriggerMode("full frequency sweep")')
                        self.driver.microwave_power = mu_power
                        tstart = time.time()
                        while True:
                            time.sleep(0.2)
                            if time.time() - tstart >= self.wait_time:
                                break
                            if self.stopped():
                                logging.warning("J1J2MicrowaveMeasurementControl info: stopped sweeping")
                                self.driver.running_sweep = False
                                return
        except Exception as e:
            logging.warning('Error in PowerSweep() : '+str(e))
            raise e

class J1J2MicrowaveMeasurementControl:
    """
    Driver to control laser and microwave powers for purpose of finding the
    optimum combination for depletion of J1 to J2 with microwaves
    (rotational cooling)
    The rotational cooling line is scanning while the powers are toggled.
    """
    def __init__(self, parent, time_offset, microwave, microwave_cmd,
                 microwave_powers, microwave_power_low, microwave_frequency,
                 microwave_time_step, laser, laser_cmd, laser_powers, wait_time):

        self.parent         = parent
        self.time_offset    = time_offset

        self.microwave          = microwaves
        self.microwave_cmd      = microwaves_cmd
        self.microwave_powers   = microwave_powers
        self.microwave_power_low= microwave_power_low
        self.microwave_frequency= microwave_frequency
        self.microwave_time_step= microwave_time_step
        self.laser              = laser
        self.laser_cmd          = laser_cmd
        self.laser_powers       = laser_powers
        self.wait_time          = wait_time

        self.verification_string = 'test'
        self.warnings = []
        self.new_attributes = []

        self.running_sweep = False
        self.sweep_thread = None

        self.shape = (3,)
        self.dtype = ('f4', 'float', 'float')


        self.microwave_power = np.nan
        self.laser_power = np.nan

    def __exit__(self, *exc):
        try:
            if self.running_sweep:
                self.sweep_thread.stop()
        except:
            return

    def __enter__(self):
        return self

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
        return [time.time()-self.time_offset, self.microwave_power, self.laser_power]

    #######################################################
    # CeNTREX DAQ GUI Commands
    #######################################################

    def StartSweep(self):
        if self.running_sweep:
            warning = 'Sweep: Currently sweeping'
            self.CreateWarning(warning)
            logging.warning('J1J2MicrowaveMeasurementControl warning in Sweep: Currently sweeping')
        else:
            params = {'microwave' : {'device'    : self.microwave,
                                     'powers'    : self.microwave_powers,
                                     'power_low' : self.microwave_power_low
                                     'frequency' : self.microwave_frequency
                                     'cmd'       : self.microwave_cmd,
                                     'time_step' : self.microwave_time_step},
                      'laser'     : {'device'    : self.laser,
                                     'powers'    : self.laser_powers,
                                     'cmd'       : self.laser_cmd},
                      'wait_time' : self.wait_time}
            self.sweep_thread = PowerSweep(self, params)
            self.sweep_thread.start()

    def StopSweep(self):
        if self.running_sweep:
            self.sweep_thread.stop()
            self.sweep_thread = None
            self.running_sweep = False
        else:
            warning = 'StopSweep: No sweep running'
            self.CreateWarning(warning)
            logging.warning('J1J2MicrowaveMeasurementControl warning in StopSweep: No sweep running')

    def GetSweepStatus(self):
        if self.running_sweep:
            return 'Sweeping'
        elif not self.running_sweep:
            return 'Inactive'
        else:
            return 'invalid'
