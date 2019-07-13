import time
import logging
import numpy as np
from zaber.serial import BinaryCommand, BinaryDevice, BinarySerial, BinaryReply

class ZaberTMMError(Exception):
    pass

class ZaberTMM:
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset
        self.COM_port = COM_port

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data from ReadValue
        self.dtype = 'f8'
        self.shape = (2, )

        try:
            self.port = BinarySerial(COM_port)
        except Exception as err:
            logging.warning("Error in initial connection to Zaber T-MM : "+str(err))
            self.verification_string = "False"
            self.__exit()
            return None

        try:
            self.port.write(BinaryCommand(0,55,123))
            msg1 = self.port.read()
            msg2 = self.port.read()
            if msg1.data != 123:
                logging.warning("ZaberTMM warning in verification : motor {0} connection error".format(msg1.device_number))
            if msg2.data != 123:
                logging.warning("ZaberTMM warning in verification : motor {0} connection error".format(msg2.device_number))
            self.verification_string = "True"
        except Exception as err:
            logging.warning('ZaberTMM warning in verification : '+str(err))
            self.verification_string = "False"

        self.warnings = []

    def __exit__(self, *exc):
        try:
            if isistance(port.can_read(), bool):
                port.close()
                return
        except:
            return

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################

    def CheckWarnings(self):
        if self.GetPositions() == [62000, 62000]:
            warning_dict = { "message" : 'power cycle'}
            self.warnings.append(warning_dict)

    def GetWarnings(self):
        self.CheckWarnings()
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        return None

    #######################################################
    # Write/Query Commands
    #######################################################

    def command(self, device, command, data, returns):
        while True:
            if self.port.can_read():
                self.port.read()
            else:
                break
        self.port.write(BinaryCommand(device, command, data))
        if returns:
            msg = []
            for _ in range(returns):
                msg.append(self.port.read())
            return msg
        else:
            return None

    #######################################################
    # Commands for all devices
    #######################################################

    def HomeAll(self):
        msgs = self.command(0, 1, 0, 2)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in HomeAll : no return msgs')
        for msg in msgs:
            if msg.data != -62000:
                logging.warning('ZaberTMM warning in HomeAll : motor {0} not @home position'.format(msg.device_number))

    def MoveAbsoluteAll(self, position):
        msgs = self.command(0, 20, position, 2)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteAll : no return msgs')
        for msg in msgs:
            if msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteAll : motor {0} not @{1} position'.format(msg.device_number, position))

    def GetPosition(self):
        msgs = self.command(0,60,0,2)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositions : no return msgs')
        pos = [None, None]
        for msg in msgs:
            pos[msg.device_number-1] = msg.data
        return pos

    #######################################################
    # Commands for individual devices
    #######################################################

    def MoveAbsoluteX(self, position):
        msgs = self.command(1, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteX : no return msgs')
        for msg in msgs:
            if msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteX : motor {0} not @{1} position'.format(msg.device_number, position))

    def MoveAbsoluteY(self, position):
        msgs = self.command(2, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteY : no return msgs')
        for msg in msgs:
            if msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteY : motor {0} not @{1} position'.format(msg.device_number, position))

    def HomeX(self):
        msgs = self.command(1,1,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in HomeX : no return msgs')
        for msg in msgs:
            if msg.data != -62000:
                logging.warning('ZaberTMM warning in HomeX : motor {0} not @home position'.format(msg.device_number))

    def HomeY(self):
        msgs = self.command(2,1,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in HomeY : no return msgs')
        for msg in msgs:
            if msg.data != -62000:
                logging.warning('ZaberTMM warning in HomeY : motor {0} not @home position'.format(msg.device_number))

    def MoveAbsoluteXNoWait(self, position):
        self.command(1,20,position,0)

    def MoveAbsoluteYNoWait(self, position):
        self.command(2,20,position,0)

    def GetPositionX(self):
        msgs = self.command(1,60,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositionX : no return msgs')
            return np.nan
        return msgs[0].data

    def GetPositionY(self):
        msgs = self.command(2,60,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositionY : no return msgs')
            return np.nan
        return msgs[0].data
