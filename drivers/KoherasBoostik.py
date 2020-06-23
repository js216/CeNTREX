import time
import serial
import logging
import numpy as np

class KoherasBoostik:
    """
    Driver for the NKT Koheras Boostik amplifier, mainly for monitoring the
    status during measurements.

    Available commands for the device are:

    GetEmission()           : (bool) emission state
    SetEmission(bool)       : set emission state
    GetCurrent()            : (float) amplifier current [A]
    GetCurrentSetpoint()    : (float) amplifier current setpoint [A]
    SetCurrent(float [A])       : set amplifier current [A]
    GetInputPower()         : (float) seed input power [A]
    GetBoosterTemperature() : (float) amplifier booster temperature [C]
    """
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset

        try:
            if COM_port != 'client':
                ser = serial.Serial()
                ser.baudrate = 9600
                ser.port = COM_port
                ser.timeout = 0.5
                ser.open()
                self.ser = ser
            self.verification_string = self.GetVerificationString()
        except Exception as err:
            logging.warning('KoherasBoostik error in initial connection')
            self.verification_string = False

        self.warnings = []
        self.new_attributes = []

        self.dtype = ('f4', 'bool', 'float', 'float', 'float', 'float')
        self.shape = (6,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.ser.close()
        except Exception as e:
            return

    def query(self, command):
        self.ser.write(command+b'\r\n')
        return self.ser.readline().decode().strip('\r\n')

    #######################################################
    # Commands for CeNTREX DAQ
    #######################################################

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def GetVerificationString(self):
        """
        Get NKT serial number from the device
        """
        return self.query(b'CDI')

    def ReadValue(self):
        emission = self.GetEmission()
        current = self.GetCurrent()
        current_setpoint = self.GetCurrentSetpoint()
        input_power = self.GetInputPower()
        booster_temp = self.GetBoosterTemperature()

        if np.isnan(current) or np.isnan(input_power) or np.isnan(booster_temp):
            return np.nan
        else:
            return [time.time() - self.time_offset, emission, input_power,
                    current, current_setpoint, booster_temp]

    def SetCurrentGUI(self, current):
        try:
            self.SetCurrent(float(current))
        except:
            logging.error('KoherasBoostik error in SetCurrentGUI : cannot convert to {0} to float'.format(current))

    def GetEmissionGUI(self):
        if self.GetEmission():
            return "True"
        else:
            return False

    #######################################################
    # Commands for CeNTREX DAQ GUI
    #######################################################

    def EmissionOn(self):
        self.SetEmission(True)

    def EmissionOff(self):
        self.SetEmission(False)

    #######################################################
    # Commands for device
    #######################################################

    def SetCurrent(self, current):
        """
        Set the amplifier current

        paremeters:
            (float) current [A]
        """
        if isinstance(current, float):
            set_current = self.query(f'ACC {current}'.encode())
            try:
                if float(set_current) != current:
                        logging.warning(f'KoherasBoostik warning in SetCurrent() : {set_current} != {current}')
            except Exception as e:
                logging.warning('KoherasBoostik warning in SetCurrent() : '+str(e))
        else:
            logging.warning('KoherasBoostik warning in SetCurrent() : supply float for current {0}'.format(current))

    def GetCurrentSetpoint(self):
        """
        Get the amplifier current setpoint

        Return:
            (float) current setpoint [A]
        """
        current = self.query(b'ACC')
        try:
            return float(current)
        except Exception as e:
            return np.nan

    def GetCurrent(self):
        """
        Get the amplifier current

        Return:
            (float) current [A]
        """
        current = self.query(b'AMC')
        try:
            return float(current)
        except Exception as e:
            return np.nan

    def GetInputPower(self):
        """
        Get the seed laser input power

        Return:
            (float) seed laser input power [A]
        """
        input_power = self.query(b'CMP 1')
        try:
            return float(input_power)*1e-4
        except Exception as e:
            return np.nan

    def SetEmission(self, enable):
        """
        Set emission state of the amplifier

        parameters:
            (bool) enable
        """
        if isinstance(enable, bool):
            enable_return = self.query(f'CDO {int(enable)}'.encode())
            try:
                if int(enable_return) != int(enable):
                        logging.warning(f'KoherasBoostik warning in SetEmission() : {enable_return} != {int(enable)}')
            except Exception as e:
                logging.warning('KoherasBoostik warning in SetEmission() : '+str(e))
        else:
            logging.warning('KoherasBoostik warning in SetEmission : enable not bool')

    def GetEmission(self):
        """
        Get emission state of the amplifier

        Return:
            (bool) emission state
        """
        emission = self.query(b'CDO')
        try:
            return bool(int(emission))
        except Exception as e:
            return np.nan

    def GetBoosterTemperature(self):
        """
        Get booster temperature of the amplifier

        Return:
            (float) booster temperature [C]
        """
        try:
            return float(self.query(b'AMT 1'))
        except Exception as e:
            return np.nan
