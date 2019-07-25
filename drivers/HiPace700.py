# Driver for Pfeiffer pumps that use the TC 400 Electronic Drive Unit.
# The unit communicates in terms of "telegrams", which are ascii strings of a
# peculiar format. See Operating Instructions for details.
# Jakob Kastelic, 2019-02-11 Mon 12:24 PM

import pyvisa
import time
import numpy as np
import logging

class HiPace700:
    def __init__(self, time_offset, resource_name, RS485_address="001"):
        self.time_offset = time_offset
        self.RS485_address = RS485_address
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
        self.verification_string = self.ElecName()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (12, )

        # for overheating checking
        self.warnings = []

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [time.time()-self.time_offset,
                self.ActualSpd(),
                self.DrvCurrent(),
                self.DrvVoltage(),
                self.DrvPower(),
                self.TempPwrStg(),
                self.TempElec(),
                self.TempPmpBot(),
                self.TempBearng(),
                self.TempMotor(),
                self.RotorImbalance(),
                self.BearingWear(),
               ]

    def GetWarnings(self):
        self.AutoCheckOverheating()
        warnings = self.warnings
        self.warnings = []
        return warnings

    def AutoCheckOverheating(self):
        if self.OvTempElec():
            warning_dict = { "message" : "excess temp turbo drive unit" }
            self.warnings.append([time.time(), warning_dict])
        elif self.OvTempPump():
            warning_dict = { "message" : "excess temp turbo pump" }
            self.warnings.append([time.time(), warning_dict])

    def checksum(self, string):
        return sum([ord(char) for char in string]) % 256

    def query(self, param, control=False, data_len="02", data="=?"):
        # compose the telegram
        action = "10" if control else "00"
        telegram = self.RS485_address + action + str(param) + str(data_len) + str(data)
        telegram += str(self.checksum(telegram)).zfill(3)

        # query the instrument
        try:
            resp = self.instr.query(telegram)
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HiPace700 warning:" + str(err))
            return np.nan

        # check and decode the response
        if resp[0:3] != self.RS485_address:
            logging.warning("HiPace700 warning: wrong address received")
            return np.nan
        elif resp[5:8] != str(param):
            logging.warning("HiPace700 warning: wrong parameter received")
            return np.nan
        elif int(resp[-3:]) != self.checksum(resp[0:-3]):
            logging.warning("HiPace700 warning: checksum doesn't match")
            return np.nan
        else:
            return resp[10:-3]

    #######################################################
    # Query commands
    #######################################################

    def OvTempElec(self):
        """Excess temperature electronic drive unit."""
        try:
            return bool(int(self.query(304)))
        except ValueError as err:
            logging.warning("HiPace700 warning in OvTempElec(): " + str(err))
            return np.nan

    def OvTempPump(self):
        """Excess temperature pump."""
        try:
            return bool(int(self.query(305)))
        except ValueError as err:
            logging.warning("HiPace700 warning in OvTempPump(): " + str(err))
            return np.nan

    def SetSpdAtt(self):
        """Set rotation speed attained."""
        try:
            return bool(int(self.query(306)))
        except ValueError as err:
            logging.warning("HiPace700 warning in SetSpdAtt(): " + str(err))
            return np.nan

    def PumpAccel(self):
        """Pump accelerates."""
        try:
            return bool(int(self.query(307)))
        except ValueError as err:
            logging.warning("HiPace700 warning in PumpAccel(): " + str(err))
            return np.nan

    def SetRotSpd(self):
        """Set rotation speed (Hz)."""
        try:
            return float(self.query(308))
        except ValueError as err:
            logging.warning("HiPace700 warning in SetRotSpd(): " + str(err))
            return np.nan

    def ActualSpd(self):
        """Actual rotation speed (Hz)."""
        try:
            return float(self.query(309))
        except ValueError as err:
            logging.warning("HiPace700 warning in ActualSpd(): " + str(err))
            return np.nan

    def TurboStatus(self):
        speed = self.ActualSpd()
        if speed == 0.0:
            return "stopped"
        elif speed and ( abs(speed-820) < 1 ):
            return "running"
        elif speed and ( abs(speed-820) > 819 ):
            return "stopped"
        elif speed and ( abs(speed-820) > 1 ):
            return "accelerating"
        else:
            print("invalid")
            return "invalid"

    def DrvCurrent(self):
        """Drive current."""
        try:
            return float(self.query(310))/100
        except ValueError as err:
            logging.warning("HiPace700 warning in DrvCurrent(): " + str(err))
            return np.nan

    def DrvVoltage(self):
        """Drive voltage."""
        try:
            return float(self.query(313))/100
        except ValueError as err:
            logging.warning("HiPace700 warning in DrvVoltage(): " + str(err))
            return np.nan

    def DrvPower(self):
        """Drive power."""
        try:
            return float(self.query(316))
        except ValueError as err:
            logging.warning("HiPace700 warning in DrvPower(): " + str(err))
            return np.nan

    def TempPwrStg(self):
        """Temperature power stage."""
        try:
            return float(self.query(324))
        except ValueError as err:
            logging.warning("HiPace700 warning in TempPwrStg(): " + str(err))
            return np.nan

    def TempElec(self):
        """Temperature electronic."""
        try:
            return float(self.query(326))
        except ValueError as err:
            logging.warning("HiPace700 warning in TempElec(): " + str(err))
            return np.nan

    def TempPmpBot(self):
        """Temperature pump bottom part."""
        try:
            return float(self.query(330))
        except ValueError as err:
            logging.warning("HiPace700 warning in TempPmpBot(): " + str(err))
            return np.nan

    def TempBearng(self):
        """Temperature bearing."""
        try:
            return float(self.query(342))
        except ValueError as err:
            logging.warning("HiPace700 warning in TempBearng(): " + str(err))
            return np.nan

    def TempMotor(self):
        """Temperature motor."""
        try:
            return float(self.query(346))
        except ValueError as err:
            logging.warning("HiPace700 warning in TempMotor(): " + str(err))
            return np.nan

    def RotorImbalance(self):
        """Rotor imbalance."""
        try:
            return float(self.query(358))
        except ValueError as err:
            logging.warning("HiPace700 warning in RotorImbalance(): " + str(err))
            return np.nan

    def BearingWear(self):
        """Rotor imbalance."""
        try:
            return float(self.query(329))
        except ValueError as err:
            logging.warning("HiPace700 warning in BearingWear(): " + str(err))
            return np.nan

    def ElecName(self):
        """Name of electronic drive unit."""
        return self.query(349)

    def ErrorCode(self):
        return self.query(303)

    def ErrHis1(self):
        """Error code history, pos. 1."""
        return self.query(360)

    def ErrHis2(self):
        """Error code history, pos. 2."""
        return self.query(361)

    def ErrHis3(self):
        """Error code history, pos. 3."""
        return self.query(362)

    def ErrHis4(self):
        """Error code history, pos. 4."""
        return self.query(363)

    def ErrHis5(self):
        """Error code history, pos. 5."""
        return self.query(364)

    def ErrHis6(self):
        """Error code history, pos. 6."""
        return self.query(365)

    def ErrHis7(self):
        """Error code history, pos. 7."""
        return self.query(366)

    def ErrHis8(self):
        """Error code history, pos. 8."""
        return self.query(367)

    def ErrHis9(self):
        """Error code history, pos. 9."""
        return self.query(368)

    def ErrHis10(self):
        """Error code history, pos. 10."""
        return self.query(369)

   #######################################################
    # Control commands
    #######################################################

    def StartPump(self):
        return self.query(param="010", control=True, data_len="06", data="111111")

    def StopPump(self):
        return self.query(param="010", control=True, data_len="06", data="000000")
