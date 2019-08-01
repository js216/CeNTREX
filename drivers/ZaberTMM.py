import time
import h5py
import logging
import numpy as np
from enum import Enum
from zaber.serial import BinaryCommand, BinaryDevice, BinarySerial, BinaryReply

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

class MirrorSweep(StoppableThread):
    """
    Mirror sweep in a separate thread to ensure continous data acquisition
    simultaneous to sweeping the mirror.
    """
    def __init__(self, driver, coords):
        super(MirrorSweep, self).__init__()
        driver.running_sweep = True

    def run(self):
        while True:
            for coord in coords:
                self.driver.MoveAbsoluteAll(coord)
                if self.stopped():
                    logging.warning("ZaberTMM warning: stopped sweeping")
                    return

class ZaberCoordinates:
    def __init__(self, dev1_axis, dev2_axis):
        if dev1_axis not in ['x', 'y']:
            logging.warning("ZaberTMM error: Dev01 axis not specified, {0}".format(dev1_axis))
            raise ValueError("ZaberTMM Dev01 axis not specified")
        if dev2_axis not in ['x', 'y']:
            logging.warning("ZaberTMM error: Dev02 axis not specified, {0}".format(dev2_axis))
            raise ValueError("ZaberTMM Dev02 axis not specified")
        if dev1_axis == dev2_axis:
            logging.warning("ZaberTMM error: Dev01 axis == Dev02 axis, {0}".format(dev1_axis))
            raise ValueError("ZaberTMM Dev01 axis == Dev02 axis")

        self._dev1_axis = dev1_axis
        self._dev2_axis = dev2_axis

        self.x = None
        self.y = None

    @property
    def coordinates(self):
        return (self.x, self.y)

    @coordinates.setter
    def coordinates(self, val):
        self.x, self.y = val

    @property
    def dev1(self):
        if self._dev1_axis == 'x':
            return self.x
        elif self._dev1_axis == 'y':
            return self.y

    @dev1.setter
    def dev1(self, val):
        if self._dev1_axis == 'x':
            self.x = val
        elif self._dev1_axis == 'y':
            self.y = val

    @property
    def dev2(self):
        if self._dev2_axis == 'x':
            return self.x
        elif self._dev2_axis == 'y':
            return self.y

    @dev2.setter
    def dev2(self, val):
        if self._dev2_axis == 'x':
            self.x = val
        elif self._dev2_axis == 'y':
            self.y = val

    @property
    def dev_coordinates(self):
        if self._dev1_axis == 'x':
            return (self.x, self.y)
        elif self._dev2_axis == 'x':
            return (self.y, self.x)

    @dev_coordinates.setter
    def dev_coordinates(self, val):
        if self._dev1_axis == 'x':
            self.x, self.y = val
        elif self._dev2_axis == 'x':
            self.y, self.x = val

    def __repr__(self):
        return "ZaberCoordinates(dev1_axis, dev2_axis)"

    def __str__(self):
        return "{0} in xy plane, {1} in device coordinates".format(self.coordinates,
                                                                   self.dev_coordinates)


class ZaberTMMError(Exception):
    pass

class ZaberTMM:
    def __init__(self, time_offset, COM_port, dev1_axis, dev2_axis):
        self.time_offset = time_offset
        self.COM_port = COM_port

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data from ReadValue
        self.dtype = ('f4', int, int, int, int)
        self.shape = (5, )

        try:
            self.port = BinarySerial(COM_port)
            self.verification_string = "True"
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

        self.position = ZaberCoordinates(dev1_axis, dev2_axis)

        if dev1_axis = 'x':
            self.dev1 = 1
            self.dev2 = 2
        elif dev2_axis = 'y':
            self.dev1 = 2
            self.dev1 = 1

        self.sweep_thread = None
        self.running_sweep = False

    def __exit__(self, *exc):
        try:
            if self.sweep:
                self.sweep_thread.stop()
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
        return [
                time.time() - self.time_offset,
                *self.position.coordinates,
                *self.position.dev_coordinates,
               ]

    def SetPosition(self, params):
        x = int(params[0])
        y = int(params[1])

        if self.dev1 == 1:
            self.MoveAbsoluteAll((x,y))
        else:
            self.MoveAbsoluteAll((y,x))

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
            if msg.data == position:
                self.position.dev_coordinates = position
            elif msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteAll : motor {0} not @{1} position'.format(msg.device_number, position))

    def GetPosition(self):
        msgs = self.command(0,60,0,2)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositions : no return msgs')
        pos = [None, None]
        for msg in msgs:
            pos[msg.device_number-1] = msg.data

        self.position.dev_coordinates = pos
        return pos

    #######################################################
    # Commands for individual devices
    #######################################################

    def MoveAbsoluteX(self, position):
        msgs = self.command(self.devx, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteX : no return msgs')
        for msg in msgs:
            if msg.data == position:
                self.position.x = position
            elif msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteX : motor {0} not @{1} position'.format(msg.device_number, position))

    def MoveAbsoluteY(self, position):
        msgs = self.command(self.devy, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteY : no return msgs')
        for msg in msgs:
            if msg.data == position:
                self.position.y = position
            elif msg.data != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteY : motor {0} not @{1} position'.format(msg.device_number, position))

    def HomeX(self):
        msgs = self.command(self.devx,1,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in HomeX : no return msgs')
        for msg in msgs:
            if msg.data == -62000:
                self.position.x = -62000
            elif msg.data != -62000:
                logging.warning('ZaberTMM warning in HomeX : motor {0} not @home position'.format(msg.device_number))

    def HomeY(self):
        msgs = self.command(self.devy,1,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in HomeY : no return msgs')
        for msg in msgs:
            if msg.data == -62000:
                self.position.y = -62000
            elif msg.data != -62000:
                logging.warning('ZaberTMM warning in HomeY : motor {0} not @home position'.format(msg.device_number))

    def MoveAbsoluteXNoWait(self, position):
        self.command(self.devx,20,position,0)

    def MoveAbsoluteYNoWait(self, position):
        self.command(self.devy,20,position,0)

    def GetPositionX(self):
        msgs = self.command(self.devx,60,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositionX : no return msgs')
            return np.nan
        self.position.x = msgs[0].data
        return msgs[0].data

    def GetPositionY(self):
        msgs = self.command(self.devy,60,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositionY : no return msgs')
            return np.nan
        self.position.y = msgs[0].data
        return msgs[0].data

    #######################################################
    # Sweep Mirror
    #######################################################

    def Sweep(self, sweepname):
        with h5py.File('ablation_sweeps.sweeps_hdf5', 'r') as f:
            coordinates = f[sweepname].values
        if self.sweep:
            logging.warning('ZaberTMM warning in Sweep: Currently sweeping mirror')
        else:
            self.sweep_thread = MirrorSweep(coordinates)
            self.sweep_thread.start()

    def StopSweep(self):
        if self.sweep:
            self.sweep_thread.stop()
            self.sweep_thread = None
            self.sweep = False
        else:
            logging.warning("ZaberTMM warning in StopSweep: No sweep running")

    def SweepStatus(self):
        if self.sweep:
            return 'Sweeping'
        else:
            return 'Inactive'
