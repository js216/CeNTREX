import ast
import time
import pickle
import logging
import numpy as np
from spinapi import *
from functools import reduce

def gcd(a, b):
    """Return greatest common divisor using Euclid's Algorithm."""
    while b:
        a, b = b, a % b
    return a

def gcdm(*args):
    """Return gcm of args"""
    return reduce(gcd, args)

def all_channels_off(pulses):
    c = [0]*24
    for pulse in pulses:
        if not pulse['active_high']:
            for ch in pulse['channels']:
                c[ch] = 1
            c[-3:] = [1,1,1]
    return c

def generate_repeating_pulses(pulses, masking_pulses, duration = None):
    c = []
    t = []

    min_instruction_len = 20 # minimum instruction length in ns

    # calculating the minimum duration required to perform all pulses
    if type(duration) == type(None):
        frequencies = [p['frequency'] for p in pulses]+[p['frequency'] for p in masking_pulses]
        duration = int(round(max([1/f for f in frequencies])/1e-9,2))
    nr_cycles = int(duration/min_instruction_len)

    # calculating the offset, frequency and amount of time at high state
    # in units of minimum_instruction_len
    pulses_cycle_units = []
    instruction_cycles = []
    for pulse in pulses:
        f = int(1/pulse['frequency'] / (min_instruction_len*1e-9))
        o = int(pulse['offset'] / min_instruction_len)
        h = int(pulse['high'] / min_instruction_len)
        instruction_cycles.append(f)
        instruction_cycles.append(h)
        if o != 0:
            instruction_cycles.append(o)
        pulses_cycle_units.append({'frequency':f, 'offset':o, 'high':h, 'channels':pulse['channels'],
                                   'active_high':pulse['active_high']})

    # calculating the offset, frequency of the masking pulses
    masking_pulses_cycle_units = []
    for pulse in masking_pulses:
        f = int(1/pulse['frequency'] / (min_instruction_len*1e-9))
        o = int(pulse['offset'] / min_instruction_len)
        h = int(f / 2)
        instruction_cycles.append(f)
        instruction_cycles.append(h)
        if o != 0:
            instruction_cycles.append(o)
        masking_pulses_cycle_units.append({'frequency':f, 'offset':o, 'high':h, 'channels':pulse['channels']})

    # checking whether the minimum clock cycles instruction length can be increased
    # by checking for the greatest common denominator to speed up sequence generation
    if instruction_cycles:
        instruction_cycles.append(nr_cycles)
    gcd_cycles = gcdm(*instruction_cycles)
    if gcd_cycles != 1:
        for pulse in pulses_cycle_units:
            pulse['frequency'] //= gcd_cycles
            pulse['offset'] //= gcd_cycles
            pulse['high'] //= gcd_cycles
        for pulse in masking_pulses_cycle_units:
            pulse['frequency'] //= gcd_cycles
            pulse['offset'] //= gcd_cycles
            pulse['high'] //= gcd_cycles

    min_instruction_len *= gcd_cycles
    nr_cycles = int(duration/min_instruction_len)-1

    # print('minimum instruction cycles : {0}'.format(min_instruction_len))

    # generating the pulseblaster instructions
    idx_reset_pulse = [0]*len(pulses)
    idx_reset_masking_pulse = [0]*len(masking_pulses)

    for idx in range(nr_cycles):
        # calculating for the regular switches
        channels_active = []
        for idx_pulse, pulse in enumerate(pulses_cycle_units):
            if idx >= pulse['offset']:
                if idx_reset_pulse[idx_pulse] < pulse['high']:
                    [channels_active.append(ch) for ch in pulse['channels']]
                idx_reset_pulse[idx_pulse] += 1
                idx_reset_pulse[idx_pulse] = idx_reset_pulse[idx_pulse] % pulse['frequency']

        # calculating for the masking switches:
        channels_masking_active = [p for pulse in pulses_cycle_units for p in pulse['channels']]
        for idx_pulse, pulse in enumerate(masking_pulses_cycle_units):
            if idx >= pulse['offset']:
                if idx_reset_masking_pulse[idx_pulse] >= pulse['high']:
                    [channels_masking_active.remove(ch) for ch in pulse['channels']]
                idx_reset_masking_pulse[idx_pulse] += 1
                idx_reset_masking_pulse[idx_pulse] = idx_reset_masking_pulse[idx_pulse] % pulse['frequency']
        if channels_active:
            chs = [0]*24
            chs[-3:] = [1,1,1]
            for idx in channels_active:
                if idx in channels_masking_active:
                    chs[idx] = 1
            if not c:
                t.append(min_instruction_len)
                c.append(chs)
            else:
                if c[-1] == chs:
                    t[-1] += min_instruction_len
                else:
                    t.append(min_instruction_len)
                    c.append(chs)
        else:
            if not c:
                c.append([0]*24)
                t.append(min_instruction_len)
            else:
                if c[-1] == [0]*24:
                    t[-1] += min_instruction_len
                else:
                    c.append([0]*24)
                    t.append(min_instruction_len)

    channels_inverted = [p for pulse in pulses for p in pulse['channels'] if not pulse['active_high']]
    channels_off = all_channels_off(pulses)
    for c_ in c:
        for ch_inv in channels_inverted:
            if c_[ch_inv]:
                c_[ch_inv] = 0
                if c_[:20] == [0]*20:
                    c_[-3:] = [0,0,0]
            else:
                if c_ == [0]*24:
                    c_[-3:] = [1,1,1]
                c_[ch_inv] = 1

    pulse_sequence = []
    for t_, c_ in zip(t,c):
        s = {'label': '', 'channels': c_, 'time': t_, 'opcode': 'CONTINUE', 'instdata': 0}
        pulse_sequence.append(s)
    pulse_sequence.append({'label':'', 'channels':channels_off.copy(), 'time':min_instruction_len, 'opcode':'BRANCH', 'instdata':0})

    t = [0]+t
    c = [channels_off]+c
    t.append(min_instruction_len)
    c.append(channels_off)

    return t, c, pulse_sequence

class PulseBlaster:
    def __init__(self, time_offset, board_number, addresses = {}, sequence = None, clock = 250e6, ):
        self.time_offset = time_offset
        self.board_number = int(board_number)
        self.addresses = addresses
        self.clock = clock
        self.sequence = sequence
        try:
            pb_select_board(self.board_number)
            if pb_init() != 0:
                self.verification_string = "False"
                logging.warning("PulseBlaster error in itial connection : could not initialize")
                self.__exit__()
            self.verification_string = str(pb_get_firmware_id())
        except Exception as err:
            logging.warning("PulseBlaster error in initial connection : "+str(err))
            self.verification_string = "False"
            self.__exit__()

        self.sequence_parts = None
        self.warnings = []
        self.new_attributes = []
        self.dtype = ('f4', 'int', 'int')
        self.shape = (3,)

        self.qswitch = -1

        try:
            if sequence:
                self.ProgramDevice()
                pb_start()
        except Exception as err:
            logging.warning("PulseBlaster error in programming sequence : "+str(err))
            self.__exit__()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            pb_stop()
            pb_close()
        except:
            return

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        status = pb_read_status()
        return time.time() - self.time_offset, status['running'], self.qswitch

    #######################################################
    # PulseBlaster Commands
    #######################################################

    def GenerateSequenceQSwitch(self, qswitch_delay):
        """
        Hardcoded sequence generation with settable qswitch delay.
        Function used for scanning the qswitch delay when optimizing YAG
        alignment and settings
        """
        flashlamp = {'frequency':50, 'offset':0, 'high': int(1e6), 'channels':[1],
                     'active_high':True}
        qswitch = {'frequency':10, 'offset':int(qswitch_delay*1e3), 'high': int(1e6), 'channels':[2],
                   'active_high':True}
        shutter = {'frequency':5, 'offset':int(qswitch_delay*1e3)+int(70e-3/1e-9)+1, 'high': int(100e-3/1e-9), 'channels':[3,4],
                   'active_high':True}

        self.qswitch = qswitch_delay

        t, c, sequence = generate_repeating_pulses([flashlamp, qswitch, shutter], [])
        self.sequence = sequence

    def ProgramAndStart(self):
        self.ProgramDevice()
        pb_start()

    def ProgramDevice(self, board_number = None):
        if type(board_number) == None:
            board_number = self.board_number
        if not self.sequence:
            logging.warning("PulseBlaster warning in ProgramDevice: no sequence supplied")
        addresses = self.addresses
        sequence = self.sequence
        pb_reset()
        pb_core_clock(int(self.clock/1e6))
        pb_start_programming(PULSE_PROGRAM)
        try:
            for seq in sequence:
                opcode = seq['opcode']
                instdata = seq['instdata']
                duration = seq['time']
                channels = seq['channels']
                channels = np.sum([i*2**idx for idx, i in enumerate(channels)])
                if opcode.upper() == 'JSR':
                    try:
                        pb_inst_pbonly(channels, JSR, addresses[instdata], duration*ns)
                    except KeyError:
                        pb_inst_pbonly(channels, JSR, instdata, duration*ns)
                elif opcode.upper() == 'RTS':
                    pb_inst_pbonly(channels, RTS, 0, duration*ns)
                elif opcode.upper() == 'BRANCH':
                    try:
                        pb_inst_pbonly(channels, BRANCH, addresses[instdata], duration*ns)
                    except KeyError:
                        pb_inst_pbonly(channels, BRANCH, instdata, duration*ns)
                elif opcode.upper() == 'LOOP':
                    pb_inst_pbonly(channels, LOOP, eval(instdata), duration*ns)
                elif opcode.upper() == 'END_LOOP':
                    try:
                        pb_inst_pbonly(channels, END_LOOP, addresses[instdata], duration*ns)
                    except KeyError:
                        pb_inst_pbonly(channels, END_LOOP, instdata, duration*ns)
                elif opcode.upper() == 'LONG_DELAY':
                    pb_inst_pbonly(channels, LONG_DELAY, eval(instdata), duration*ns)
                else:
                    if opcode == '':
                        opcode = '0'
                    pb_inst_pbonly(channels, eval(opcode), 0, duration*ns)
        except Exception as e:
            print(seq)
            raise e
        pb_stop_programming()
        logging.info("PulseBlaster warning in ProgramDevice: finished programming")

if __name__ == "__main__":
    trace_length = 30 # ms
    qswitch_delay = 85 # microseconds
    frequency = 26 # Hz
    # trigger = {'frequency':10, 'offset':0, 'high': int(round(1e-4/1e-9,2)), 'channels':[0],
    #            'active_high':True}
    flashlamp = {'frequency':frequency, 'offset':0, 'high': int(1e6), 'channels':[1,4],
                 'active_high':True}
    qswitch = {'frequency':frequency, 'offset':int(qswitch_delay*1e3), 'high': int(1e6), 'channels':[2,5],
               'active_high':True}
    shutter = {'frequency':frequency/2, 'offset':int(trace_length * 1e6 + 1e6), 'high': int(1/frequency * 1e9), 'channels':[3,6],
               'active_high':True}
    # trigger = {'frequency':20, 'offset':int(qswitch_delay*1e3), 'high': int(1e6), 'channels':[5]}
    # shutter = {'frequency':5, 'offset':int(qswitch_delay*1e3)+int(70e-3/1e-9)+1, 'high': int(100e-3/1e-9), 'channels':[3,4],
    #            'active_high':True}

    # fpol = 1.5e6
    # ppol = 1/fpol
    # high = round((ppol/2)/1e-9 // 4* 4)
    # rcpol = {'frequency':fpol, 'offset':int(0), 'high':high, 'channels': [5],
    #         'active_high':True}
    # J1J2pol = {'frequency':fpol, 'offset':round((ppol/1e-9/360)*45), 'high':high, 'channels': [6],
    #         'active_high':True}
    # J2J3pol = {'frequency':fpol, 'offset':round((ppol/1e-9/360)*90), 'high':high, 'channels': [7],
    #         'active_high':True}

    # shutter = {'frequency': 5/10,'offset':int(round(20e-3/1e-9,2)), 'high':int(round(1/1e-9,2)), 'channels':[3],
    #            'active_high':True}
    # shutter_daq = {'frequency': 5/20,'offset':int(round(20e-3/1e-9,2)), 'high':int(round(2/1e-9,2)), 'channels':[4],
    #            'active_high':True}

    t, c, sequence = generate_repeating_pulses([flashlamp, qswitch, shutter], [])
    pb = PulseBlaster(time.time(), 0, {}, sequence)
