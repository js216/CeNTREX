import time
import logging
import numpy as np
from windfreak import SynthHD

class SynthHDPro:
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset
        self.COM_port = COM_port


        self.dtype = ('f4', 'float', 'float', 'float', 'float', 'bool', 'bool')
        self.shape = (7,)

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

        # Loading device state to prevent continuous serial communication for common data
        # device only knows setpoints, not actual frequency or power levels
        self.channels           = {'A': 0, 'B': 1}
        self.frequency_setting  = {}
        self.GetFrequency('A')
        self.GetFrequency('B')
        self.power_setting      = {}
        self.GetPower('A')
        self.GetPower('B')
        self.enabled            = {}
        self.GetStatus('A')
        self.GetStatus('B')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.synth.close()
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
                self.power_setting['B'],
                self.enabled['A'],
                self.enabled['B']
                ]
        return val

    #######################################################
    # GUI Commands
    #######################################################

    def GetFrequencyCHAGUI(self):
        return self.frequency_setting['A']

    def SetFrequencyCHAGUI(self, frequency):
        self.SetFrequency(frequency, 'A')

    def GetFrequencyCHBGUI(self):
        return self.frequency_setting['B']

    def SetFrequencyCHBGUI(self, frequency):
        self.SetFrequency(frequency, 'B')

    def SetPowerCHAGUI(self, power):
        self.SetPower(power, 'A')

    def GetPowerCHAGUI(self):
        return self.power_setting['A']

    def SetPowerCHBGUI(self, power):
        self.SetPower(power, 'B')

    def GetPowerCHBGUI(self):
        return self.power_setting['B']

    def GetCHAStatus(self):
        if self.enabled['A']:
            return 'on'
        else:
            return 'off'

    def GetCHBStatus(self):
        if self.enabled['B']:
            return 'on'
        else:
            return 'off'

    def EnableCHA(self):
        self.Enable(ch = 'A')

    def DisableCHA(self):
        self.Disable(ch = 'A')

    def EnableCHB(self):
        self.Enable(ch = 'B')

    def DisableCHB(self):
        self.Disable(ch = 'B')

    #######################################################
    # Device Commands
    #######################################################

    def SetSweepTimeStep(self, step_time):
        self.write('sweep_time_step', step_time)

    def GetFrequency(self, ch = 'A'):
        chn = self.channels[ch]
        self.frequency_setting[ch] = self.synth[chn].frequency
        return self.frequency_setting[ch]

    def GetPower(self, ch = 'A'):
        chn = self.channels[ch]
        self.power_setting[ch] = self.synth[chn].power
        return self.power_setting[ch]

    def SetFrequency(self, frequency, ch = 'A'):
        chn = self.channels[ch]
        try:
            self.synth[chn].frequency = frequency
            self.frequency_setting[ch] = frequency
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetFrequency() : frequency out of range")
        except Exception as err:
            logging.warning("SynthHDPro warning in SetFrequency() : "+str(err))
            pass

    def SetPower(self, power, ch = 'A'):
        chn = self.channels[ch]
        try:
            self.synth[chn].power = power
            self.power_setting[ch] = power
        except ValueError as warning:
            self.CreateWarning(warning)
            self.logging("SynthHDPro warning in SetPower() : power out of range")
        except Exception as err:
            logging.warning("SynthHDPro warning in SetPower() : "+str(err))

    def Enable(self, ch = 'A'):
        chn = self.channels[ch]
        self.synth[chn].enable = True
        self.enabled[ch] = True

    def Disable(self, ch = 'A'):
        chn = self.channels[ch]
        self.synth[chn].enable = False
        self.enabled[ch] = False

    def FrequencyReference(self, reference):
        references = {'10 MHz': 'internal 10mHz',
                      '27 MHz': 'internal 27mHz',
                      'external': 'external'}
        self.synth.reference_mode = references[reference]

    def GetFrequencyReference(self, reference):
        return self.synth.reference_mode

    def GetStatus(self, ch = 'A'):
        chn = self.channels[ch]
        self.enabled[ch] = self.synth[chn].enable
        return self.enabled[ch]


if __name__ == '__main__':
    com = input('COM PORT : ')
    synth = SynthHDPro(time.time(), com)
    print(synth.verification_string)
    synth.Enable()
    synth.SetFrequency(100e6)
    time.sleep(5)
    synth.SetFrequency(55e6)
    time.sleep(5)
    synth.Disable()
    synth.__exit__()
