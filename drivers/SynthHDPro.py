import time
import logging
import numpy as np
from windfreak import SynthHD

class SynthHDPro:
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

        self.new_attributes = []

        self.channels = {'A': 0, 'B': 1}

        self.frequency_setting  = {'A': self.GetFrequency('A'), 'B': self.GetFrequency('B')}
        self.power_setting      = {'A': self.GetPower('A'), 'B': self.GetPower('B')}

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
        val = [
                time.time() - self.time_offset,
                self.frequency_setting['A'],
                self.frequency_setting['B'],
                self.power_setting['A'],
                self.power_setting['B']
                ]
        return val

    #######################################################
    # GUI Commands
    #######################################################

    def GetFrequencyGUI(self):
        return self.frequency_setting

    def GetPowerGUI(self):
        return self.power_setting

    #######################################################
    # Device Commands
    #######################################################

    def SetSweepTimeStep(self, step_time):
        self.write('sweep_time_step', step_time)

    def GetFrequency(self, ch = 'A'):
        ch = self.channels[ch]
        return self.synth[ch].frequency

    def GetPower(self, ch = 'A'):
        ch = self.channels[ch]
        return self.synth[ch].power

    def SetFrequency(self, frequency, ch = 'A'):
        ch = self.channels[ch]
        try:
            self.synth[ch].frequency = frequency
            self.frequency_setting[ch] = frequency
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetFrequency() : frequency out of range")
        except Exception as err:
            logging.warning("SynthHDPro warning in SetFrequency() : "+str(err))
            pass

    def SetPower(self, power, ch = 'A'):
        ch = self.channels[ch]
        try:
            self.synth[ch].power = power
            self.power_setting[ch] = power
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetPower() : power out of range")
        except Exception as err:
            logging.warning("SynthHDPro warning in SetPower() : "+str(err))

    def Enable(self, ch = 'A'):
        ch = self.channels[ch]
        self.synth[ch].enable = True

    def Disable(self, ch = 'A'):
        ch = self.channels[ch]
        self.synth[ch].enable = False

    def FrequencyReference(self, reference):
        references = {'10 MHz': 'internal 10mHz',
                      '27 MHz': 'internal 27mHz',
                      'external': 'external'}
        self.synth.reference_mode = references[reference]
    
    def GetFrequencyReference(self, reference):
        return self.synth.reference_mode


if __name__ == '__main__':
    com = input('COM PORT : ')
    synth = SynthHDPro(time.time(), com)
    synth.SetFrequency(100e6)
    time.sleep(5)
    synth.SetFrequency(55e6)
    synth.__exit__()