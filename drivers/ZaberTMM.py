import os
import time
import h5py
import secrets
import logging
import threading
import functools
import numpy as np
from enum import Enum
from zaber.serial import BinaryCommand, BinaryDevice, BinarySerial, BinaryReply
from zaber.serial import TimeoutError

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

class StepRectangle:
    """
    Rectangle in mirror coordinates to step through manually.
    """
    def __init__(self, driver, point_a, point_b, step, **kwargs):
        self.driver = driver
        self.point_a = point_a
        self.point_b = point_b
        self.step = step
        self.index = 0
        self.coords_x = self.calculate_coords_range(point_a[0], point_b[0], step)
        self.coords_y = self.calculate_coords_range(point_a[1], point_b[1], step)
        # generate the coordinates as an array [[x0,y0],[x1,y1],...] to sweep through
        self.coordinates = np.array(np.meshgrid(self.coords_x, self.coords_y)).T.reshape(-1,2)

    def calculate_coords_range(self, a, b, step):
        if a > b:
            return np.arange(a,b-step,-step)
        else:
            return np.arange(a,b+step,step)

    def move(self, x, y):
        try:
            self.driver.MoveAbsoluteX(x)
        except TimeoutError:
            pass
        try:
            self.driver.MoveAbsoluteY(y)
        except TimeoutError:
            pass

    def next(self):
        self.move(*self.coordinates[self.index])
        self.index += 1
        if self.index == len(self.coordinates):
            self.index = 0

class MirrorSweepRectangle(StoppableThread):
    """
    Mirror sweep in a separate thread to ensure continous data acquisition
    simultaneous to sweeping the mirror.
    Define a rectangle by two opposing corners to sweep through.
    """
    def __init__(self, driver, point_a, point_b, step, wait_time = 0):
        super(MirrorSweepRectangle, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.point_a = point_a
        self.point_b = point_b
        self.step = step
        self.wait_time = wait_time

    def move(self, x, y):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.MoveAbsoluteX(x)
                break
            except TimeoutError:
                continue
        while True:
            try:
                if self.stopped():
                    break
                self.driver.MoveAbsoluteY(y)
                break
            except TimeoutError:
                continue

    def calculate_coords_range(self, a, b, step):
        if a > b:
            return np.arange(a,b-step,-step)
        else:
            return np.arange(a,b+step,step)

    def run(self):
        self.driver.running_sweep = True
        coords_x = self.calculate_coords_range(self.point_a[0], self.point_b[0], self.step)
        coords_y = self.calculate_coords_range(self.point_a[1], self.point_b[1], self.step)
        while True:
            for x in coords_x:
                for y in coords_y:
                    self.move(x,y)
                    time.sleep(self.wait_time)
                    if self.stopped():
                        logging.warning("ZaberTMM info: stopped sweeping")
                        self.driver.running_sweep = False
                        return

class MirrorSweep(StoppableThread):
    """
    Mirror sweep in a separate thread to ensure continous data acquisition
    simultaneous to sweeping the mirror.
    """
    def __init__(self, driver, coords, start_position = 'current'):
        super(MirrorSweep, self).__init__()
        self.driver = driver
        self.driver.running_sweep = False
        self.coordinates = coords
        self.start_position = start_position

    def move(self, x, y):
        while True:
            try:
                if self.stopped():
                    break
                self.driver.MoveAbsoluteX(x)
                break
            except TimeoutError:
                continue
        while True:
            try:
                if self.stopped():
                    break
                self.driver.MoveAbsoluteY(y)
                break
            except TimeoutError:
                continue

    def run(self):
        # generating random start position if random_start enabled
        if self.start_position == 'random':
            coordinates = np.roll(self.coordinates,
                                  secrets.randbelow(len(self.coordinates)),
                                  axis = 0)
        elif self.start_position == 'current':
            current_position    = self.driver.position.coordinates
            # index_current_pos   = np.where((self.coordinates == current_position).all(axis=1))[0]
            index_current_pos  = np.argmin(np.abs(self.coordinates - current_position).sum(axis = 1))
            if index_current_pos.size == 0:
                logging.error('ZaberTMM error: current position not in sweep coordinates hdf')
                self.driver.CreateWarning('current position not in sweep coordinates hdf')
                return
            coordinates = np.roll(self.coordinates, -index_current_pos, axis = 0)
        elif self.start_position == 'origin':
            coordinates = self.coordinates
        else:
            logging.warning('ZaberTMM warning: sweep start position not specified,'+
                            'starting at sweep coordinates origin')
            coordinates = self.coordinates

        self.driver.running_sweep = True
        while True:
            for coord in coordinates:
                x,y = coord
                self.move(x,y)
                if self.stopped():
                    logging.warning("ZaberTMM info: stopped sweeping")
                    self.driver.running_sweep = False
                    return

class ZaberCoordinates:
    def __init__(self, dev1_axis, dev2_axis):
        if dev1_axis not in ['x', 'y']:
            logging.error("ZaberTMM error: Dev01 axis not specified, {0}".format(dev1_axis))
            raise ValueError("ZaberTMM Dev01 axis not specified")
        if dev2_axis not in ['x', 'y']:
            logging.error("ZaberTMM error: Dev02 axis not specified, {0}".format(dev2_axis))
            raise ValueError("ZaberTMM Dev02 axis not specified")
        if dev1_axis == dev2_axis:
            logging.error("ZaberTMM error: Dev01 axis == Dev02 axis, {0}".format(dev1_axis))
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


def SweepCheckWrapper(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].running_sweep:
            warning = '{0} : Currently sweeping, unable to set position'.format(func.__name__)
            logging.warning('ZaberTMM warning in'+warning)
            args[0].CreateWarning(warning)
        else:
            return func(*args, **kwargs)
    return wrapper


class ZaberTMMError(Exception):
    pass

class ZaberTMM:
    def __init__(self, time_offset, COM_port, dev1_axis, dev2_axis, coordinates_fname):
        self.time_offset = time_offset
        self.COM_port = COM_port

        self.coordinates_fname = coordinates_fname
        with h5py.File('drivers/' + coordinates_fname, 'r') as f:
            self.coordinates_random = f['all_points'][()]
            np.random.shuffle(self.coordinates_random)

        # shape and type of the array of returned data from ReadValue
        self.dtype = ('f4', 'int32', 'int32')
        self.shape = (3, )

        try:
            self.port = BinarySerial(COM_port)
            msg = self.command(0,50,0,2)
            msg = [d.data for d in msg]
            if not all(elem == msg[0] for elem in msg):
                raise ValueError('ZaberTMM warning in verification : Device IDs not equal')
        except Exception as err:
            logging.warning("ZaberTMM error in initial connection : "+str(err))
            self.verification_string = "False"
            self.__exit__()
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

        if dev1_axis == 'x':
            self.devx = 1
            self.devy = 2
        elif dev1_axis == 'y':
            self.devx = 2
            self.devy = 1

        if not self.ReadDeviceModeX()[7]:
            warning = 'Home Status bit not set in Dev{0}, home device'.format(self.devx)
            logging.warning('ZaberTMM warning: '+warning)
            self.CreateWarning(warning)
        if not self.ReadDeviceModeY()[7]:
            warning = 'Home Status bit not set in Dev{0}, home device'.format(self.devx)
            logging.warning('ZaberTMM warning: '+warning)
            self.CreateWarning(warning)

        self.sweep_thread = None
        self.running_sweep = False
        self.sweep_start_position = 'current'
        self.sweep_square_params = {}
        self.step_rectangle = None

        self.GetPosition()

        # HDF attributes generated when constructor is run
        self.new_attributes = [
                                ('dev1_axis', dev1_axis),
                                ('dev2_axis', dev2_axis),
                                ('x_speed', str(self.ReadTargetSpeedX())),
                                ('y_speed', str(self.ReadTargetSpeedY())),
                                ('x_acceleration', str(self.ReadAccelerationX())),
                                ('y_acceleration', str(self.ReadAccelerationY()))
                              ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self.running_sweep:
                self.sweep_thread.stop()
            try:
                self.port.close()
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
                *self.position.coordinates
               ]
        return val

    def SweepStatus(self):
        if self.running_sweep:
            return 'Sweeping'
        elif not self.running_sweep:
            return 'Inactive'
        else:
            return 'invalid'

    def SweepStartPosition(self, start_position):
        if start_position in ['current', 'random', 'origin']:
            self.sweep_start_position = start_position
        else:
            warning = 'SweepStartPosition: start_position can be set to current, origin or random'
            self.CreateWarning(warning)
            logging.warning('ZaberTMM warning in '+warning)

    def SweepStartPositionStatus(self):
        return self.sweep_start_position

    @SweepCheckWrapper
    def MoveAbsoluteXGUI(self, position):
        self.MoveAbsoluteX(position)

    @SweepCheckWrapper
    def MoveAbsoluteYGUI(self, position):
        self.MoveAbsoluteY(position)

    @SweepCheckWrapper
    def HomeAllGUI(self):
        self.HomeAll()

    @SweepCheckWrapper
    def RandomPosition(self):
        x,y = self.coordinates_random[0]
        self.MoveAbsoluteX(x)
        self.MoveAbsoluteY(y)
        self.coordinates_random = np.roll(self.coordinates_random, shift = -1,
                                          axis = 0)

    def SetPointAGUI(self, point_a):
        self.sweep_square_params['point_a'] = point_a

    def GetPointAGUI(self):
        return self.sweep_square_params.get('point_a', None)

    def SetPointBGUI(self, point_b):
        self.sweep_square_params['point_b'] = point_b

    def GetPointBGUI(self):
        return self.sweep_square_params.get('point_b', None)

    def SetStepGUI(self, step):
        self.sweep_square_params['step'] = step

    def GetStepGUI(self):
        return self.sweep_square_params.get('step', None)

    def SetWaitGUI(self, wait_time):
        self.sweep_square_params['wait_time'] = float(wait_time)

    def GetWaitGUI(self):
        return self.sweep_square_params.get('wait_time', None)

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
        self.position.dev_coordinates = [-62000, -62000]

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
        while True:
            msgs = self.command(0,60,0,2)
            if isinstance(msgs, type(None)):
                logging.warning('ZaberTMM warning in GetPositions : no return msgs')
            pos = [None, None]
            for msg in msgs:
                pos[msg.device_number-1] = msg.data
            if not type(None) in [type(i) for i in pos]:
                break
        self.position.dev_coordinates = pos
        return pos

    def DisablePotentiometer(self):
        current = self.command(0,53,40,2)[0].data
        msgs = self.command(0, 40, current+8)

    #######################################################
    # Commands for individual devices
    #######################################################

    def MoveAbsoluteX(self, position):
        msgs = self.command(self.devx, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteX : no return msgs')
        for msg in msgs:
            if msg.device_number == self.devx:
                if isinstance(msg.data, int):
                    self.position.x = msg.data
            elif msg.device_number == self.devy:
                if isinstance(msg.data, int):
                    self.position.y = msg.data
        if self.position.x != position:
            logging.warning('ZaberTMM warning in MoveAbsoluteX : motor {0} not @{1} position'.format(self.devx, position))

    def MoveAbsoluteY(self, position):
        msgs = self.command(self.devy, 20, position, 1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in MoveAbsoluteY : no return msgs')
        for msg in msgs:
            if msg.device_number == self.devx:
                if isinstance(msg.data, int):
                    self.position.x = msg.data
            elif msg.device_number == self.devy:
                if isinstance(msg.data, int):
                    self.position.y = msg.data
            if self.position.y != position:
                logging.warning('ZaberTMM warning in MoveAbsoluteY : motor {0} not @{1} position'.format(self.devy, position))

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

    def GetPositionXMemory(self):
        return self.position.x

    def GetPositionY(self):
        msgs = self.command(self.devy,60,0,1)
        if isinstance(msgs, type(None)):
            logging.warning('ZaberTMM warning in GetPositionY : no return msgs')
            return np.nan
        self.position.y = msgs[0].data
        return msgs[0].data

    def GetPositionYMemory(self):
        return self.position.y

    def ReadDeviceModeX(self):
        msg = self.command(self.devx,53,40,1)
        bits = [int(d) for d in bin(msg[0].data)[2:]][::-1]
        return bits

    def ReadDeviceModeY(self):
        msg = self.command(self.devx,53,40,1)
        bits = [int(d) for d in bin(msg[0].data)[2:]][::-1]
        return bits

    def DisablePotentiometerX(self):
        current = self.command(self.devx,53,40,1)[0].data
        msgs = self.command(self.devx,40, current+8)

    def DisablePotentiometerY(self):
        current = self.command(self.devy,53,40,1)[0].data
        msgs = self.command(self.devy,40, current+8)

    def ReadTargetSpeedX(self):
        return self.command(self.devx,53,42,1)[0].data

    def ReadTargetSpeedY(self):
        return self.command(self.devy,53,42,1)[0].data

    def ReadAccelerationX(self):
        return self.command(self.devx,53,43,1)[0].data

    def ReadAccelerationY(self):
        return self.command(self.devy,53,43,1)[0].data

    #######################################################
    # Sweep Mirror
    #######################################################

    def Sweep(self, sweepname):
        with h5py.File('drivers/'+self.coordinates_fname, 'r') as f:
            coordinates = f[sweepname][()]
        if self.running_sweep:
            warning = 'Sweep: Currently sweeping mirror'
            self.CreateWarning(warning)
            logging.warning('ZaberTMM warning in Sweep: Currently sweeping mirror')
        else:
            self.sweep_thread = MirrorSweep(self, coordinates, self.sweep_start_position)
            self.sweep_thread.start()

    def SweepRectangle(self, sweep_params = None):
        if isinstance(sweep_params, type(None)):
            sweep_params = self.sweep_square_params
        if self.running_sweep:
            warning = "SweepRectangle: Currently sweeping mirror"
            self.CreateWarning(warning)
            logging.warning('ZaberTMM warning in SweepRectangle: Currently sweeping mirror')
        else:
            self.sweep_thread = MirrorSweepRectangle(self, **sweep_params)
            self.sweep_thread.start()

    def StopSweep(self):
        if self.running_sweep:
            self.sweep_thread.stop()
            self.sweep_thread = None
            self.running_sweep = False
        else:
            warning = 'StopSweep: No sweep running'
            self.CreateWarning(warning)
            logging.warning("ZaberTMM warning in StopSweep: No sweep running")

    def setupStepRectangle(self, sweep_params = None):
        if isinstance(sweep_params, type(None)):
            sweep_params = self.sweep_square_params
        self.step_rectangle = StepRectangle(self, **sweep_params)

    def nextStep(self):
        if not self.step_rectangle is None:
            self.step_rectangle.next()
        else:
            logging.warning("ZaberTMM warning in nextStep: No rectangle defined")
