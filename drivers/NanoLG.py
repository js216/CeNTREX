import logging
import pyvisa
import time
import array
import numpy as np
import struct
import functools
import threading
import queue

def WriteVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('NanoLG warning in {0}() : '.format(func.__name__) \
                            +str(err))
    return wrapper

def RequestVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('NanoLG warning in {0}() : '.format(func.__name__) \
                        +str(err))
            return np.nan
    return wrapper

class InstrumentCommunication(threading.Thread):
    def __init__(self, resource_name):
        threading.Thread.__init__(self)
        self.daemon = True
        self.active = threading.Event()
        self.rm = pyvisa.ResourceManager()

        self.instr = self.rm.open_resource(resource_name)

        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.baud_rate = 9600
        self.instr.stop_bits = pyvisa.constants.StopBits.one
        self.instr.timeout = 150

        self.system_status_word_idx = {0:'system_state',
                                   1:'pump_state',
                                   2:'laser_state',
                                   3:'shutter_state',
                                   4:'interlock_water_flow',
                                   5:'interlock_water_level',
                                   6:'interlock_water_temp',
                                   7:'interlock_charger2',
                                   8:'interlock_psu_temp',
                                   9:'interlock_charger1',
                                   10:'interlock_external',
                                   11:'interlock_psu_cover',
                                   12:'interlock_laser_head',
                                   13:'interlock_shutter',
                                   14:'interlock_simmer1',
                                   15:'interlock_simmer2',
                                   25:'water_flow',
                                   26:'key_state',
                                   27:'external_qswitch1_trigger',
                                   28:'external_qswitch2_trigger',
                                   29:'external_lamp1_trigger',
                                   30:'external_lamp2_trigger',
                                   31:'interlocks_latched'}

        self.function_status_word_idx = {0:'lamp1_trigger_enable',
                                     1:'lamp2_trigger_enable',
                                     2:'qswitch1_trigger_enable',
                                     3:'qswitch2_trigger_enable',
                                     8:'flashlamp_delay_negative',
                                     9:'rep_rate_div_mode1',
                                     10:'rep_rate_div_mode2',
                                     11:'burst_mode1',
                                     12:'burst_mode2',
                                     13:'trig_mode',
                                     14:'low_frequency1',
                                     15:'low_frequency2',
                                     16:'shutter_inhibit',
                                     19:'crystal_temperature',
                                     20:'wavelength_selector_position_undefined',
                                     21:'mirror_mover_position_undefined'}

        self.num_bytes_to_command_codes = {b'\x00\x12':{b'\x00\x11':[1,2]},
                                           b'\x00\x16':{b'\x00\x11':[2,4],
                                                        b'\x00\x21':[3,5]},
                                           b'\x00\x10':{b'\x00\x11':[4,2]}
                                          }

        self.packet_type_index = {1: {b'\x00\x12':'lamp_volts',
                                      b'\x00\x1a':'system_info'},
                                  2: {b'\x00\x1a\x00\x60':'lamp_total_shotcount',
                                      b'\x00\x1a\x00\x68':'lamp_user_shotcount',},
                                      # b'\x00\x1a\x00\x70':'lamp2_total_shotcount',
                                      # b'\x00\x1a\x00\x78':'lamp2_user_shotcount'},
                                  3: {b'\xff\x02\x1f\x10\x04':'head_crystal_cal_offset',
                                      b'\xff\x02\x1f\x10\x03':'head_crystal_cal_slope',
                                      b'\xff\x02\x1f\x10\x02':'head_crystal_setpoint',
                                      b'\xff\x02\x1f\x10\x01':'head_crystal_temperature',
                                      b'\xff\x04\x1f\x10\x16':'cooler_crystal_cal_offset',
                                      b'\xff\x04\x1f\x10\x15':'cooler_crystal_cal_slope',
                                      b'\xff\x04\x1f\x10\x14':'cooler_crystal_setpoint',
                                      b'\xff\x04\x1f\x10\x18':'cooler_crystal_temperature',
                                      b'\xff\x04\x1f\x10\x02':'cooler_water_cal_offset',
                                      b'\xff\x04\x1f\x10\x01':'cooler_water_cal_slope',
                                      b'\xff\x04\x1f\x10\x00':'cooler_water_setpoint',
                                      b'\xff\x04\x1f\x10\x05':'cooler_water_temperature'},
                                  4: {b'\x00\x03':'system_status_word',
                                      b'\x00\x1C':'function_status_word'}
                             }
        function_status_word = dict([(value,None) for value in
                                        self.function_status_word_idx.values()])
        system_status_word = dict([(value,None) for value in
                                        self.system_status_word_idx.values()])

        system_info = {'pulse_period':None,
                       'flashlamp_delay':None,
                       'qs_delay':None,
                       'rep_rate_divider':None,
                       'burst_value':None,
                       'laser_serial_nr':None,
                       'pulse_period_low_limit':None,
                       'pulse_period_high_limit':None,
                       'qs_delay_high_limit':None,
                       'qs_delay_low_limit':None}

        lamp = {'lamp_volts':None,
                'lamp_total_shotcount':None,
                'lamp_user_shotcount':None}

        head_crystal = {'head_crystal_cal_offset':None,
                        'head_crystal_cal_slope':None,
                        'head_crystal_setpoint':None,
                        'head_crystal_temperature':None}

        cooler_crystal = {'cooler_crystal_cal_offset':None,
                          'cooler_crystal_cal_slope':None,
                          'cooler_crystal_setpoint':None,
                          'cooler_crystal_temperature':None}

        cooler_water = {'cooler_water_cal_offset':None,
                        'cooler_water_cal_slope':None,
                        'cooler_water_setpoint':None,
                        'cooler_water_temperature':None}

        self.data = {'lamp':lamp,
                     'function_status_word':function_status_word,
                     'head_crystal':head_crystal,
                     'cooler_crystal':cooler_crystal,
                     'cooler_water':cooler_water,
                     'system_info':system_info,
                     'system_status_word':system_status_word}

        self.q = queue.Queue()

        self.Ping()

    def run(self):
        time_last_communication = time.time()
        dt_communication = 5
        while self.active.is_set():
            message = self.read_message()
            if message:
                self.handle_message(message)

            while not self.q.empty():
                if not self.active.is_set():
                    return
                cmd = self.q.get()
                self.write(cmd)
                time_last_communication = time.time()
                message = self.read_message()
                if message:
                    self.handle_message(message)

            if time.time() - time_last_communication > dt_communication:
                self.Ping()

    def write(self, data):
        self.instr.write_raw(data)

    def read_message(self):
        try:
            if self.instr.bytes_in_buffer == 0:
                return False
            if self.instr.read_bytes(1) == b'\xaa':
                if self.instr.read_bytes(1) == b'\xaa':
                    header = b'\xaa\xaa'+self.instr.read_bytes(4)
                    num_bytes = int.from_bytes(header[4:], byteorder = 'big')
                    command = self.instr.read_bytes(2)
                    data = self.instr.read_bytes(num_bytes-6-2-2)
                    crc = self.instr.read_bytes(2)
                    if crc == bytearray(self._calculate_crc(command+data)):
                        return header, command, data, crc
                    else:
                        return False
            else:
                return False
        except pyvisa.errors.VisaIOError as e:
            if self.rm.visalib.last_status.name == 'error_timeout':
                return False
            else:
                logging.warning('NanoLG warning in read_message() : '+str(e))

    def handle_message(self, message):
        if message:
            header, command, data, crc = message
            cc_index, nr_bytes = self.num_bytes_to_command_codes[header[-2:]][command]
            packet_type = self.packet_type_index[cc_index].get(data[:nr_bytes])
            if packet_type:
                value = eval('self.parse_'+packet_type+'({0})'.format(data))

    def _calculate_crc(self, data):
        top_byte_index = len(data)-1
        if top_byte_index < 2:
            return 0

        top17bits = int(data[0]) * 256
        top17bits += int(data[1]) * 256
        top17bits += int(data[2])

        byte_number = 3
        next_byte = top17bits & 127
        mask = 64
        top17bits = int(top17bits/128)
        k_x = 69665
        while True:
            crc_flag = 0
            leading_bit = top17bits & 65536
            if leading_bit > 0:
                top17bits = top17bits ^ k_x
            else:
                top17bits = top17bits ^ 0

            if mask == 128:
                crc_flag = 1
                if byte_number < (top_byte_index + 1):
                    if crc_flag == 1:
                        next_byte = int(data[byte_number])
                        byte_number += 1
                else:
                    return bytearray((((top17bits >> 8) & 255), (top17bits & 255)))
            next_bit = next_byte & mask
            if mask > 1:
                mask = mask // 2
            else:
                mask = 128
            top17bits = top17bits * 2
            if next_bit >=1:
                top17bits += 1

    def Ping(self):
        """
        Low bandwidth message for laser internal watchdog to prevent YAG
        shutdown.
        YAG sends a system status word back.
        """
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E,
                            0x00, 0x0B, 0x00, 0x00, 0x00, 0x01,
                            0xF0, 0xF0))
        self.write(bytes(command))

    ##############################
    # Packet Parsing Commands
    ##############################

    def parse_system_status_word(self, data):
        val = int.from_bytes(data[-4:], byteorder = 'big')
        bit_values = [val >> i & 1 for i in range(32)]
        for idx_bit, val_bit in enumerate(bit_values):
            idx = self.system_status_word_idx.get(idx_bit)
            if idx:
                self.data['system_status_word'][idx] = val_bit

    def parse_function_status_word(self, data):
        val = int.from_bytes(data[-4:], byteorder = 'big')
        bit_values = [val >> i & 1 for i in range(32)]
        for idx_bit, val_bit in enumerate(bit_values):
            idx = self.function_status_word_idx.get(idx_bit)
            if idx:
                self.data['function_status_word'][idx] = val_bit

    def parse_system_info(self, data):
        identifier = {
                      0x0020:['pulse_period', 'us'],
                      0x0024:['flashlamp_delay', 'us'],
                      0x0028:['qs_delay', 'us'],
                      0x0040:['rep_rate_divider', None],
                      0x0050:['burst_value', None],
                      0x02A4:['laser_serial_number', None],
                      0x0010:['pulse_period_low_limit', 'us'],
                      0x0014:['pulse_period_high_limit', 'us'],
                      0x0018:['qs_delay_high_limit', 'us'],
                      0x001c:['qs_delay_low_limit', 'us']
                      }

        index = int.from_bytes(data[2:4], byteorder = 'big')
        measurable = identifier.get(index)
        if measurable:
            value = int.from_bytes(data[4:], byteorder = 'big')
            self.data['system_info'][measurable[0]] = (time.time(), value)

    def parse_lamp_volts(self, data):
        lamp = data[3]
        volts = int.from_bytes(data[6:], byteorder = 'big')
        if lamp == 0x01:
            self.data['lamp']['lamp_volts'] = (time.time(), volts)

    def parse_lamp_total_shotcount(self, data):
        shots = int.from_bytes(data[4:], byteorder = 'big')
        self.data['lamp']['lamp_total_shotcount'] = (time.time(), shots)

    def parse_lamp_user_shotcount(self, data):
        shots = int.from_bytes(data[4:], byteorder = 'big')
        self.data['lamp']['lamp_user_shotcount'] = (time.time(), shots)

    def parse_head_crystal_cal_offset(self, data):
        offset = int.from_bytes(data[5:7], byteorder = 'little')
        self.data['head_crystal']['head_crystal_cal_offset'] = (time.time(), offset)

    def parse_head_crystal_cal_slope(self, data):
        slope = int.from_bytes(data[5:9], byteorder = 'little')
        self.data['head_crystal']['head_crystal_cal_slope'] = (time.time(), slope)
        return offset

    def parse_head_crystal_setpoint(self, data):
        setpoint = int.from_bytes(data[5:7], byteorder = 'little')
        self.data['head_crystal']['head_crystal_setpoint'] = (time.time(), setpoint)

    def parse_head_crystal_temperature(self, data):
        temperature = int.from_bytes(data[5:7], byteorder = 'little')
        self.data['head_crystal']['head_crystal_temperature'] = (time.time(), temperature)

    def parse_cooler_crystal_cal_offset(self, data):
        offset = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_crystal']['cooler_crystal_cal_offset'] = (time.time(), offset)

    def parse_cooler_crystal_cal_slope(self, data):
        slope = int.from_bytes(data[5:9], byteorder = 'big')
        self.data['cooler_crystal']['cooler_crystal_cal_slope'] = (time.time(), slope)

    def parse_cooler_crystal_setpoint(self, data):
        setpoint = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_crystal']['cooler_crystal_setpoint'] = (time.time(), setpoint)

    def parse_cooler_crystal_temperature(self, data):
        temperature = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_crystal']['cooler_crystal_temperature'] = (time.time(), temperature)

    def parse_cooler_water_cal_offset(self, data):
        offset = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_water']['cooler_water_cal_offset'] = (time.time(), offset)

    def parse_cooler_water_cal_slope(self, data):
        slope = int.from_bytes(data[5:9], byteorder = 'big')
        self.data['cooler_water']['cooler_water_cal_slope'] = (time.time(), slope)

    def parse_cooler_water_setpoint(self, data):
        setpoint = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_water']['cooler_water_setpoint'] = (time.time(), setpoint)

    def parse_cooler_water_temperature(self, data):
        temperature = int.from_bytes(data[5:7], byteorder = 'big')
        self.data['cooler_water']['cooler_water_temperature'] = (time.time(), temperature)

class NanoLG:
    def __init__(self, time_offset, resource_name, rep_rate = 10):
        """
        Control class for the Nano LG pulsed laser.

        Data to the pulsed YAG laser is sent as a binary packet:
        header | command | data | crc

        header
        B0   | B1   | B2     | B3          | B4             | B5
        0xAA | 0xAA | sender | destination | byte count MSB | byte count LSB

        sender address
        0x00    laser       -> controller
        0x01    controller  -> laser

        byte count
        16 bit; # bytes in packet

        command
        16 bit; primary command code

        crc
        Litron inhouse CRC generated by _calculate_crc
        """
        self.time_offset = time_offset

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f8'
        self.shape = (15, )

        self.warnings = []

        self.system_status_word_idx = {0:'system_state',
                                   1:'pump_state',
                                   2:'laser_state',
                                   3:'shutter_state',
                                   4:'interlock_water_flow',
                                   5:'interlock_water_level',
                                   6:'interlock_water_temp',
                                   7:'interlock_charger2',
                                   8:'interlock_psu_temp',
                                   9:'interlock_charger1',
                                   10:'interlock_external',
                                   11:'interlock_psu_cover',
                                   12:'interlock_laser_head',
                                   13:'interlock_shutter',
                                   14:'interlock_simmer1',
                                   15:'interlock_simmer2',
                                   25:'water_flow',
                                   26:'key_state',
                                   27:'external_qswitch1_trigger',
                                   28:'external_qswitch2_trigger',
                                   29:'external_lamp1_trigger',
                                   30:'external_lamp2_trigger',
                                   31:'interlocks_latched'}

        self.function_status_word_idx = {0:'lamp1_trigger_enable',
                                     1:'lamp2_trigger_enable',
                                     2:'qswitch1_trigger_enable',
                                     3:'qswitch2_trigger_enable',
                                     8:'flashlamp_delay_negative',
                                     9:'rep_rate_div_mode1',
                                     10:'rep_rate_div_mode2',
                                     11:'burst_mode1',
                                     12:'burst_mode2',
                                     13:'trig_mode',
                                     14:'low_frequency1',
                                     15:'low_frequency2',
                                     16:'shutter_inhibit',
                                     19:'crystal_temperature',
                                     20:'wavelength_selector_position_undefined',
                                     21:'mirror_mover_position_undefined'}

        if resource_name not in ['client', '']:
            self.communication = InstrumentCommunication(resource_name)
            self.communication.active.set()
            self.communication.start()
            time.sleep(0.5)
            try:
                self.Ping()
                if type(self.communication.data['system_status_word']['system_state']) == type(None):
                    self.verification_string = "False"
                    self.communication.instr = False
                    return
            except pyvisa.errors.VisaIOError:
                self.verification_string = "False"
                self.communication.instr = False
                return



        # make the verification string
        self.verification_string = 'NanoLG'

        self.pump_start_time = None

        # acceptable time difference between requesting parameter and time stored in self.data
        self.param_delay = 2

        self.RequestCoolerCrystalCalibrationSlope()
        self.RequestCoolerCrystalCalibrationOffset()
        self.RequestCoolerWaterCalibrationSlope()
        self.RequestCoolerWaterCalibrationOffset()
        self.RequestSystemData()
        self.RequestPulsePeriodLowLimit()
        self.RequestPulsePeriodHighLimit()
        self.RequestQSwitchDelayLowLimit()
        self.RequestQSwitchDelayHighLimit()
        self.RepetitionRateDivider(rep_rate)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.communication.instr:
            self.StopSystem()
            self.communication.active.clear()
            self.communication.instr.close()

    def __exitclient__(self, *exc):
        return

    def write(self, data):
        self.communication.q.put(data)

    def _calculate_crc(self, data):
        top_byte_index = len(data)-1
        if top_byte_index < 2:
            return 0

        top17bits = int(data[0]) * 256
        top17bits += int(data[1]) * 256
        top17bits += int(data[2])

        byte_number = 3
        next_byte = top17bits & 127
        mask = 64
        top17bits = int(top17bits/128)
        k_x = 69665
        while True:
            crc_flag = 0
            leading_bit = top17bits & 65536
            if leading_bit > 0:
                top17bits = top17bits ^ k_x
            else:
                top17bits = top17bits ^ 0

            if mask == 128:
                crc_flag = 1
                if byte_number < (top_byte_index + 1):
                    if crc_flag == 1:
                        next_byte = int(data[byte_number])
                        byte_number += 1
                else:
                    return bytearray((((top17bits >> 8) & 255), (top17bits & 255)))
            next_bit = next_byte & mask
            if mask > 1:
                mask = mask // 2
            else:
                mask = 128
            top17bits = top17bits * 2
            if next_bit >=1:
                top17bits += 1


    ##############################
    # CeNTREX DAQ Commands
    ##############################

    def CheckWarnings(self):
      for idx in range(4,13):
          interlock = self.system_status_word_idx[idx]
          if self.communication.data['system_status_word'][interlock]:
              warning_dict = { "message" : ' '.join(interlock.split('_'))+' failed'}
              self.warnings.append([time.time(), warning_dict])
      for idx in range(14,16):
          interlock = self.system_status_word_idx[idx]
          if self.communication.data['system_status_word'][interlock]:
              warning_dict = { "message" : ' '.join(interlock.split('_'))+' failed'}
              self.warnings.append([time.time(), warning_dict])
      if not self.communication.data['system_status_word']['interlock_shutter']:
          warning_dict = { "message" : ' '.join(interlock.split('_'))+' failed'}
          self.warnings.append([time.time(), warning_dict])

      for idx in [14,15,16,19]:
          parameter = self.function_status_word_idx[idx]
          if self.communication.data['function_status_word'][parameter]:
              warning_dict = { "message" : ' '.join(parameter.split('_'))+' failed'}
              self.warnings.append([time.time(), warning_dict])

    def GetWarnings(self):
        self.CheckWarnings()
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        self.RequestSystemData()
        crystal_temp = self.RequestCoolerCrystalTemperature()
        water_temp = self.RequestCoolerWaterTemperature()
        self.Ping()

        system_state = self.communication.data['system_status_word']['system_state']
        pump_state = self.communication.data['system_status_word']['pump_state']
        laser_state = self.communication.data['system_status_word']['laser_state']
        shutter_state = self.communication.data['system_status_word']['shutter_state']
        qs_delay = self.communication.data['system_info']['qs_delay'][1]
        rep_rate_divider = self.communication.data['system_info']['rep_rate_divider'][1]
        rep_rate_mode = self.communication.data['function_status_word']['rep_rate_div_mode1']
        lamp_total = self.RequestFlashlampTotalShots()
        lamp_user = self.RequestFlashlampUserShots()
        lamp_trigger_external = self.communication.data['system_status_word']['external_lamp1_trigger']
        qswitch_trigger_external = self.communication.data['system_status_word']['external_qswitch1_trigger']

        # interlocks
        interlock = 0
        for idx in range(4,13):
            interlock = interlock | self.communication.data['system_status_word'][self.system_status_word_idx[idx]]
        for idx in range(14,16):
            interlock = interlock | self.communication.data['system_status_word'][self.system_status_word_idx[idx]]
        if not self.communication.data['system_status_word']['interlock_shutter']:
            interlock = interlock | 1
        if not self.communication.data['system_status_word']['key_state']:
            interlock = interlock | 1

        return [time.time()- self.time_offset, system_state, pump_state,
                laser_state, shutter_state, water_temp, crystal_temp, qs_delay,
                rep_rate_divider, rep_rate_mode, lamp_total, lamp_user,
                lamp_trigger_external, qswitch_trigger_external, interlock]

    def NanoLGSystemStatus(self):
        if self.communication.data['system_status_word']['laser_state'] & self.communication.data['system_status_word']['shutter_state']:
            return 'Laser On'
        elif self.communication.data['system_status_word']['laser_state']:
            return 'Laser On/Shutter Closed'
        elif self.communication.data['system_status_word']['pump_state']:
            return 'Pump On'
        elif not self.communication.data['system_status_word']['pump_state']:
            return 'YAG Off'
        else:
            return 'invalid'

    def SystemOnStatus(self):
        if self.communication.data['system_status_word']['system_state']:
            return 'System on'
        elif not self.communication.data['system_status_word']['system_state']:
            return 'System off'
        else:
            return 'invalid'

    def PumpStatus(self):
        if self.communication.data['system_status_word']['pump_state']:
            return 'Pump on'
        elif not self.communication.data['system_status_word']['pump_state']:
            return 'Pump off'
        else:
            return 'invalid'

    def LaserStatus(self):
        if self.communication.data['system_status_word']['laser_state']:
            return 'Laser on'
        elif not self.communication.data['system_status_word']['laser_state']:
            return 'Laser off'
        else:
            return 'invalid'

    def ShutterStatus(self):
        if self.communication.data['system_status_word']['shutter_state']:
            return 'Shutter open'
        elif not self.communication.data['system_status_word']['shutter_state']:
            return 'Shutter closed'
        else:
            return 'invalid'

    def LampTriggerStatus(self):
        if self.communication.data['system_status_word']['external_lamp1_trigger']:
            return 'external'
        elif not self.communication.data['system_status_word']['external_lamp1_trigger']:
            return 'internal'
        else:
            return 'invalid'

    def QSwitchTriggerStatus(self):
        if self.communication.data['system_status_word']['external_qswitch1_trigger']:
            return 'external'
        elif not self.communication.data['system_status_word']['external_qswitch1_trigger']:
            return 'internal'
        else:
            return 'invalid'

    ##############################
    # Commands
    ##############################

    @WriteVisaIOError
    def StopSystem(self):
        self.LaserOff()
        self.PumpOff()
        self.LaserOff()

    @WriteVisaIOError
    def StartLaser(self):
        interlock = 0
        for idx in range(4,13):
            interlock = interlock | self.communication.data['system_status_word'][self.system_status_word_idx[idx]]
        for idx in range(14,16):
            interlock = interlock | self.communication.data['system_status_word'][self.system_status_word_idx[idx]]
        if not self.communication.data['system_status_word']['interlock_shutter']:
            interlock = interlock | 1
        if not self.communication.data['system_status_word']['key_state']:
            interlock = interlock | 1

        if interlock:
            logging.warning('NanoLG warning in StartLaser() : interlock prevents starting of laser')
            warning_dict = { "message" : 'interlock prevents starting of laser'}
            self.warnings.append([time.time(), warning_dict])
            return
        elif self.pump_start_time:
          if time.time()- self.pump_start_time > 6:
            self.LaserOn()
          else:
            logging.warning('NanoLG warning in StartLaser(): laser requires pump on for at least 5s')
            warning_dict = { "message" : 'laser requires pump on for at least 5s'}
            self.warnings.append([time.time(), warning_dict])
        else:
            logging.warning('NanoLG warning in StartLaser(): laser requires pump on')
            warning_dict = { "message" : 'laser requires pump on'}
            self.warnings.append([time.time(), warning_dict])

    @WriteVisaIOError
    def StartPump(self):
        interlock = 0
        if not self.communication.data['system_status_word']['key_state']:
            interlock = interlock | 1
        if interlock:
            logging.warning("NanoLG warning in StartPump() : key prevents starting of pump")
            warning_dict = { "message" : "key prevents starting of pump"}
            self.warnings.append([time.time(), warning_dict])
        else:
            self.PumpOn()


    @WriteVisaIOError
    def SystemOn(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x01,
                             0x00, 0x00, 0x00, 0x2D, 0x37, 0x1D, 0xAA, 0xAA,
                             0x01, 0x00, 0x00, 0x0E, 0x00, 0x0C, 0x10, 0x00,
                             0x00, 0x01, 0x76, 0x13))
        self.write(bytes(command))

    @WriteVisaIOError
    def SystemOff(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x02,
                             0x00, 0x00, 0x00, 0x2D, 0x6E, 0x4D, 0xAA, 0xAA,
                             0x01, 0x00, 0x00, 0x0E, 0x00, 0x0C, 0x00, 0x00,
                             0x00, 0x01, 0x75, 0x60))
        self.write(bytes(command))

    @WriteVisaIOError
    def PumpOn(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x01,
                            0x00, 0x00, 0x00, 0x21, 0x37, 0x11, 0xAA, 0xAA,
                            0x01, 0x00, 0x00, 0x0E, 0x00, 0x01, 0x00, 0x00,
                            0x00, 0x20, 0x37, 0x10))
        self.write(bytes(command))
        self.pump_start_time = time.time()

    @WriteVisaIOError
    def PumpOff(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x02,
                            0x00, 0x00, 0x00, 0x21, 0x6E, 0x41))
        self.write(bytes(command))

    @WriteVisaIOError
    def LaserOn(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x02,
                            0x00, 0x00, 0x00, 0x23, 0x6E, 0x43, 0xAA, 0xAA,
                            0x01, 0x00, 0x00, 0x0E, 0x00, 0x01, 0x00, 0x00,
                            0x00, 0x22, 0x37, 0x12))
        self.write(bytes(command))

    @WriteVisaIOError
    def LaserOff(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x01,
                            0x00, 0x00, 0x00, 0x23, 0x37, 0x13))
        self.write(bytes(command))

    @WriteVisaIOError
    def ShutterOpen(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12, 0x00, 0x0D,
                            0x00, 0x00, 0x00, 0x69, 0x00, 0x00, 0x00, 0x24,
                            0xEF, 0xD4))
        self.write(bytes(command))

    @WriteVisaIOError
    def ShutterClose(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12, 0x00, 0x0D,
                            0x00, 0x00, 0x00, 0x69, 0x00, 0x00, 0x00, 0x25,
                            0xEF, 0xD5))
        self.write(bytes(command))

    @WriteVisaIOError
    def LampExternalTrigger(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x01,
                            0x00, 0x00, 0x00, 0x32, 0x37, 0x02))
        self.write(bytes(command))

    @WriteVisaIOError
    def LampInternalTrigger(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x02,
                            0x00, 0x00, 0x00, 0x32, 0x6E, 0x52))
        self.write(bytes(command))

    @WriteVisaIOError
    def LinkedTriggerMode(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12, 0x00, 0x11,
                            0x00, 0x11, 0x00, 0x09, 0x00, 0x00, 0x00, 0x01,
                            0xBF, 0x81))
        self.write(bytes(command))

    @WriteVisaIOError
    def IndependentTriggerMode(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12, 0x00, 0x11,
                            0x00, 0x11, 0x00, 0x09, 0x00, 0x00, 0x00, 0x00,
                            0xBF, 0x80))
        self.write(bytes(command))

    @WriteVisaIOError
    def QSwitchExternalTrigger(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x01,
                            0x00, 0x00, 0x00, 0x34, 0x37, 0x04))
        self.write(bytes(command))

    @WriteVisaIOError
    def QSwitchInternalTrigger(self):
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E, 0x00, 0x02,
                            0x00, 0x00, 0x00, 0x34, 0x6E, 0x54))
        self.write(bytes(command))

    @WriteVisaIOError
    def RepetitionRateDivider(self, divider):
        """
        Set the qswitch vs flashlamp repetition rate divider
        """
        if isinstance(divider, str):
          divider = int(divider)
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12))
        cmd = bytearray((0x00, 0x11))
        data = bytearray((0x00, 0x11, 0x00,0x06))
        data += bytearray(struct.pack(">I", divider | 1 << 31))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

    @WriteVisaIOError
    def QSwitchDelay(self, delay):
        """
        Set the qswitch delay
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x1F))
        cmd = bytearray((0x00, 0x11))
        data = bytearray((0x00, 0x11, 0x00, 0x01))
        lamp1_trig_internal = self.communication.data['function_status_word']['lamp1_trigger_enable']
        lamp2_trig_internal = self.communication.data['function_status_word']['lamp1_trigger_enable']
        qswitch1_trig_internal = self.communication.data['function_status_word']['qswitch1_trigger_enable']
        qswitch2_trig_internal = self.communication.data['function_status_word']['qswitch2_trigger_enable']
        flashlamp_delay_neg = self.communication.data['function_status_word']['flashlamp_delay_negative']
        config = bytearray([lamp1_trig_internal << 0 | lamp2_trig_internal << 1 | qswitch1_trig_internal << 2 | qswitch2_trig_internal << 3 | flashlamp_delay_neg << 4])
        pulse_period = bytearray(struct.pack(">I", self.communication.data['system_info']['pulse_period'][1]))
        flashlamp_delay = bytearray(struct.pack(">I", self.communication.data['system_info']['flashlamp_delay'][1]))
        qswitch1_delay = bytearray(struct.pack(">I", int(delay)))
        qswitch2_delay = bytearray(struct.pack(">I", int(delay)))
        data = data + config + pulse_period + flashlamp_delay + qswitch1_delay + qswitch2_delay
        crc = self._calculate_crc(cmd + data)
        command = header+cmd+data+crc
        self.write(bytes(command))

    @WriteVisaIOError
    def Burst(self, bursts):
        """
        Set the number of burst shots to fire
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x12))
        cmd = bytearray((0x00, 0x11))
        data = bytearray((0x00, 0x11, 0x00))
        data += bytearray(struct.pack(">I", bursts | 1 << 31))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

    @RequestVisaIOError
    def Ping(self):
        """
        Low bandwidth message for laser internal watchdog to prevent YAG
        shutdown.
        YAG sends a system status word back.
        """
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E,
                            0x00, 0x0B, 0x00, 0x00, 0x00, 0x01,
                            0xF0, 0xF0))
        self.write(bytes(command))
        return self.communication.data['system_status_word']

    @RequestVisaIOError
    def RequestFunctionStatus(self):
        """
        Request current value of function status word.
        """
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E,
                            0x00, 0x1C, 0x00, 0x00, 0x00, 0x01,
                            0x36, 0x03))
        self.write(bytes(command))

    # !!!! Function does not work as described in manual !!!!
    @RequestVisaIOError
    def RequestRepetitionRate(self):
        """
        Request the repetition rate of lamp 1, but only seems to return a
        function status word instead of the system info.
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0D))
        cmd = bytearray((0x00, 0x1C))
        data = bytearray((0x00, 0x40, 0x04))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['system_info']['rep_rate_divider']:
                t, val = self.communication.data['system_info']['rep_rate_divider']
                if t >  time.time()-self.param_delay:
                    return val
            time.sleep(0.05)
        logging.warning('NanoLG warning in RequestRepetitionRate() : no value returned')
        return np.nan

    # !!!! Function does not work as described in manual !!!!
    @RequestVisaIOError
    def RequestBurst(self):
        """
        Request the burst rate of lamp 1, but only seems to return a
        function status word instead of the system info.
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0D))
        cmd = bytearray((0x00, 0x1C))
        data = bytearray((0x00, 0x50, 0x04))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['system_info']['burst_value']:
                t, val = self.communication.data['system_info']['burst_value']
                if t >  time.time()-self.param_delay:
                    return val
            time.sleep(0.05)
        logging.warning('NanoLG warning in RequestBurst() : no value returned')
        return np.nan

    @RequestVisaIOError
    def RequestFlashlampTotalShots(self):
        """
        Request the total number of flashlamp shots.
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0D))
        cmd = bytearray((0x00, 0x1A))
        data = bytearray((0x00, 0x60, 0x08))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['lamp']['lamp_total_shotcount']:
                t, val = self.communication.data['lamp']['lamp_total_shotcount']
                if t >  time.time()-self.param_delay:
                    return val
            time.sleep(0.05)
        logging.warning('NanoLG warning in RequestFlashlampTotalShots() : no value returned')
        return np.nan

    @RequestVisaIOError
    def RequestFlashlampUserShots(self):
        """
        Request the count of the user resettable flashlamp shot count.
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0D))
        cmd = bytearray((0x00, 0x1A))
        data = bytearray((0x00, 0x68, 0x08))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['lamp']['lamp_user_shotcount']:
                t, req = self.communication.data['lamp']['lamp_user_shotcount']
                if t >  time.time()-self.param_delay:
                    return req
            time.sleep(0.05)
        logging.warning('NanoLG warning in RequestFlashlampUserShots() : no value returned')
        return np.nan

    @WriteVisaIOError
    def ResetFlashlampUserShots(self):
        """
        Reset the user count of flashlamp shots of lamp 1
        """
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x14))
        cmd = bytearray((0x00, 0x19))
        data = bytearray((0x00, 0x68, 0x00, 0x00, 0x00, 0x00,
                        0x00, 0x00, 0x00, 0x00))
        crc = bytearray((0xB1, 0x95))
        command = header+cmd+data+crc
        self.write(bytes(command))

    @RequestVisaIOError
    def RequestSystemData(self):
        """
        Request system data, requests the following values:
            Function Status
            Flashlamp 1 Voltage
            Flashlamp 2 Voltage
            Pulse Period
            Flashlamp Delay
            Q-Switch Delay 1
            Q-Switch Delay 2
            Attenuator value
            Attenuator 2 value
        Function does not actually return the values, stores them in the data
        dictionary
        """
        command = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0E,
                            0x00, 0x1B, 0x00, 0x00, 0x00, 0x01,
                            0xB3, 0x93))
        self.write(bytes(command))

    def request_head_data(self, param):
        parameters = {'head_crystal_setpoint':0x00, 'head_crystal_cal_slope':0x03,
                'head_crystal_cal_offset':0x04, 'head_crystal_temperature':0x1B}
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x17))
        cmd = bytearray((0x00, 0x21))
        data = bytearray((0x18, 0x1E, 0x01, 0x02, 0x01))
        data += bytearray([parameters[param]])
        data += bytearray((0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['head_crystal'][param]:
                t, req = self.communication.data['head_crystal'][param]
                if t >  time.time()-self.param_delay:
                    return req
            time.sleep(0.05)
        return np.nan

    @RequestVisaIOError
    def RequestHeadCrystalSetpoint(self):
        val = self.request_head_data('head_crystal_setpoint')
        offset = self.communication.data['head_crystal_cal_offset'][1]
        slope = self.communication.data['head_crystal_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            logging.warning('NanoLG warning in RequestHeadCrystalSetpoint() : no value returned')
            return val

    @RequestVisaIOError
    def RequestHeadCrystalCalibrationSlope(self):
        val =  self.request_head_data('head_crystal_cal_slope')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestHeadCrystalCalibrationSlope() : no value returned')
            return val

    @RequestVisaIOError
    def RequestHeadCrystalCalibrationOffset(self):
        val = self.request_head_data('head_crystal_cal_offset')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestHeadCrystalCalibrationOffset() : no value returned')
            return val

    @RequestVisaIOError
    def RequestHeadCrystalTemperature(self):
        val = self.request_head_data('head_crystal_temperature')
        offset = self.communication.data['head_crystal_cal_offset'][1]
        slope = self.communication.data['head_crystal_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            logging.warning('NanoLG warning in RequestHeadCrystalTemperature() : no value returned')
            return val

    def request_cooler_crystal_data(self, param):
        parameters = {'cooler_crystal_setpoint':0x14, 'cooler_crystal_cal_slope':0x15,
                  'cooler_crystal_cal_offset':0x16, 'cooler_crystal_temperature':0x18}
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x17))
        cmd = bytearray((0x00, 0x21))
        data = bytearray((0x18, 0x1E, 0x01, 0x04, 0x01))
        data += bytearray([parameters[param]])
        data += bytearray((0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['cooler_crystal'][param]:
                t, req = self.communication.data['cooler_crystal'][param]
                if t >  time.time()-self.param_delay:
                    return req
            time.sleep(0.05)
        return np.nan

    @RequestVisaIOError
    def RequestCoolerCrystalSetpoint(self):
        val = self.request_cooler_crystal_data('cooler_crystal_setpoint')
        offset = self.communication.data['cooler_crystal']['cooler_crystal_cal_offset'][1]
        slope = self.communication.data['cooler_crystal']['cooler_crystal_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            logging.warning('NanoLG warning in RequestCoolerCrystalSetpoint() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerCrystalCalibrationSlope(self):
        val = self.request_cooler_crystal_data('cooler_crystal_cal_slope')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestCoolerCrystalCalibrationSlope() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerCrystalCalibrationOffset(self):
        val = self.request_cooler_crystal_data('cooler_crystal_cal_offset')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestCoolerCrystalCalibrationOffset() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerCrystalTemperature(self):
        val = self.request_cooler_crystal_data('cooler_crystal_temperature')
        offset = self.communication.data['cooler_crystal']['cooler_crystal_cal_offset'][1]
        slope = self.communication.data['cooler_crystal']['cooler_crystal_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            return val

    def request_cooler_water_data(self, param):
        parameters = {'cooler_water_setpoint':0x00, 'cooler_water_cal_slope':0x01,
                  'cooler_water_cal_offset':0x02, 'cooler_water_temperature':0x05}
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x17))
        cmd = bytearray((0x00, 0x21))
        data = bytearray((0x18, 0x1E, 0x01, 0x04, 0x01))
        data += bytearray([parameters[param]])
        data += bytearray((0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['cooler_water'][param]:
                t, val = self.communication.data['cooler_water'][param]
                if t >  time.time()-self.param_delay:
                    return val
            time.sleep(0.05)
        return np.nan

    @RequestVisaIOError
    def RequestCoolerWaterSetpoint(self):
        val = self.request_cooler_water_data('cooler_water_setpoint')
        offset = self.communication.data['cooler_water']['cooler_water_cal_offset'][1]
        slope = self.communication.data['cooler_water']['cooler_water_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            logging.warning('NanoLG warning in RequestCoolerWaterSetpoint() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerWaterCalibrationSlope(self):
        val = self.request_cooler_water_data('cooler_water_cal_slope')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestCoolerWaterCalibrationSlope() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerWaterCalibrationOffset(self):
        val = self.request_cooler_water_data('cooler_water_cal_offset')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestCoolerWaterCalibrationOffset() : no value returned')
            return val

    @RequestVisaIOError
    def RequestCoolerWaterTemperature(self):
        val = self.request_cooler_water_data('cooler_water_temperature')
        offset = self.communication.data['cooler_water']['cooler_water_cal_offset'][1]
        slope = self.communication.data['cooler_water']['cooler_water_cal_slope'][1]
        if not np.isnan(val):
            return (val-offset)*(slope/10000)
        else:
            logging.warning('NanoLG warning in RequestCoolerWaterTemperature() : no value returned')
            return val

    def request_timing_limits(self, param):
        parameters = {'pulse_period_low_limit':0x10,
                      'pulse_period_high_limit':0x14,
                      'qs_delay_low_limit':0x1c,
                      'qs_delay_high_limit':0x18}
        header = bytearray((0xAA, 0xAA, 0x01, 0x00, 0x00, 0x0D))
        cmd = bytearray((0x00, 0x1a))
        data = bytearray((0x00, parameters[param], 0x04))
        crc = self._calculate_crc(cmd+data)
        command = header+cmd+data+crc
        self.write(bytes(command))

        for _ in range(5):
            if self.communication.data['system_info'][param]:
                t, val = self.communication.data['system_info'][param]
                if t >  time.time()-self.param_delay:
                    return val
            time.sleep(0.05)
        return np.nan

    @RequestVisaIOError
    def RequestPulsePeriodLowLimit(self):
        val = self.request_timing_limits('pulse_period_low_limit')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestPulsePeriodLowLimit() : no value returned')
            return val

    @RequestVisaIOError
    def RequestPulsePeriodHighLimit(self):
        val = self.request_timing_limits('pulse_period_high_limit')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestPulsePeriodHighLimit() : no value returned')
            return val

    @RequestVisaIOError
    def RequestQSwitchDelayLowLimit(self):
        val = self.request_timing_limits('qs_delay_low_limit')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestQSwitchDelayLowLimit() : no value returned')
            return val

    @RequestVisaIOError
    def RequestQSwitchDelayHighLimit(self):
        val = self.request_timing_limits('qs_delay_high_limit')
        if not np.isnan(val):
            return val
        else:
            logging.warning('NanoLG warning in RequestQSwitchDelayHighLimit() : no value returned')
            return val
