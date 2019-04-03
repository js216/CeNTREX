import pyvisa
import time
import numpy as np
import logging

class nXDS:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.read_termination = '\r'
        self.instr.write_termination = '\r'

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (6, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [time.time()-self.time_offset,
                self.MotorCurrent(),
                self.MotorPower(),
                self.LinkVoltage(),
                self.PumpTemperature(),
                self.PumpCtrlrTemperature(),
               ]

    def GetWarnings(self):
        return None

    def QueryIdentification(self):
        try:
            return self.instr.query("?S0")
        except pyvisa.errors.VisaIOError as err:
            return("nXDS warning in QueryIdentification(): " + str(err))

    def StopPump(self):
        try:
            val = self.instr.query("!C802 0")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        if "*C802 0" in val:
            return "*C802 0: No error"
        elif "*C802 1" in val:
            return "*C802 1: Invalid command for object ID"
        elif "*C802 2" in val:
            return "*C802 2: Invalid query/command"
        elif "*C802 3" in val:
            return "*C802 3: Missing parameter"
        elif "*C802 4" in val:
            return "*C802 4: Parameter out of range"
        elif "*C802 5" in val:
            return "*C802 5: Invalid command in current state, e.g., serial\
                command to start/stop when in parallel control mode."
        else:
            return val

    def StartPump(self):
        try:
            val = self.instr.query("!C802 1")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        if "*C802 0" in val:
            return "*C802 0: No error"
        elif "*C802 1" in val:
            return "*C802 1: Invalid command for object ID"
        elif "*C802 2" in val:
            return "*C802 2: Invalid query/command"
        elif "*C802 3" in val:
            return "*C802 3: Missing parameter"
        elif "*C802 4" in val:
            return "*C802 4: Parameter out of range"
        elif "*C802 5" in val:
            return "*C802 5: Invalid command in current state, e.g., serial\
                command to start/stop when in parallel control mode."
        else:
            return val

    def PumpCtrlrTemperature(self):
        try:
            val = self.instr.query("?V808")[6:].split(";")[-1]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpCtrlrTemperature(): " + str(err))
            return np.nan

    def PumpTemperature(self):
        try:
            val = self.instr.query("?V808")[6:].split(";")[-2]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpTemperature(): " + str(err))
            return np.nan

    def LinkVoltage(self):
        try:
            val = self.instr.query("?V809")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val.split(';')[-3])/10
        except ValueError as err:
            logging.warning("nXDS warning in LinkVoltage(): " + str(err))
            return np.nan

    def MotorPower(self):
        try:
            val = self.instr.query("?V809")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val.split(';')[-1])/10
        except ValueError as err:
            logging.warning("nXDS warning in MotorPower(): " + str(err))
            return np.nan

    def MotorCurrent(self):
        try:
            val = self.instr.query("?V809")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val.split(';')[-2])/10
        except ValueError as err:
            logging.warning("nXDS warning in MotorCurrent(): " + str(err))
            return np.nan

    def RunHours(self):
        try:
            val = self.instr.query("?V810")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in RunHours(): " + str(err))
            return np.nan

    def PumpCycles(self):
        try:
            val = self.instr.query("?V811")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpCycles(): " + str(err))
            return np.nan

    def TipSealService(self):
        """
        Number of pump running hours since last tip seal service;
        number of pump running hours left until tip seal service due.
        """
        try:
            return self.instr.query("?V814")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

    def BearingService(self):
        """
        Number of pump running hours since last bearing service;
        number of pump running hours left until bearing service due.
        """
        try:
            return self.instr.query("?V815")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

    def FaultHistory1(self):
        """
        Fault history at last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V816")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

    def FaultHistory2(self):
        """
        Fault history at 2nd last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V817")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

    def FaultHistory3(self):
        """
        Fault history at 3rd last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V818")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)

    def FaultHistory4(self):
        """
        Fault history at 4th last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V819")[6:]
        except pyvisa.errors.VisaIOError as err:
            return str(err)