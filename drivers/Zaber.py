import logging
import time

import numpy as np
import zaber_motion
from zaber_motion import Units
from zaber_motion.binary import Connection
import zaber_motion.exceptions as ex

class Zaber:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        try:
            self.connection = Connection.open_serial_port(resource_name)
            self.device = self.connection.detect_devices()[0]
        except (ex.NoDeviceFoundException, ex.serial_port_busy_exception.SerialPortBusyException) as err:
            self.verification_string = str(err)
            self.device = False
            return

        # make the verification string
        try:
            self.verification_string = self.QueryIdentification()
        except zaber_motion.NoDeviceFoundException as err:
            self.verification_string = str(err)

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (2,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.device:
            self.connection.close()

    def ReadValue(self):
        return [time.time() - self.time_offset, self.ReadPosition()]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            return str(self.device)[:19]
        except zaber_motion.NoDeviceFoundException as err:
            logging.warning("Zaber warning in QueryIdentification(): " + str(err))
            return str(err)

    def Home(self):
        self.device.home()

    def SetPosition(self, pos):
        self.device.move_absolute(pos, Units.LENGTH_MILLIMETRES)

    def ReadPosition(self):
        return self.device.get_position(Units.LENGTH_MILLIMETRES)
