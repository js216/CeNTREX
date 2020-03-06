import time
from spinapi import pb_select_board, pb_get_firmware_id, pb_reset, pb_core_clock, \
                    pb_start_programming, pb_inst_pbonly, pb_start, pb_read_status

sequence = [{'label': '', 'channels': [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 145000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 9855000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 145000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 9855000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1], 'time': 10000000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 9995000, 'opcode': 'CONTINUE', 'instdata': 0}, {'label': '', 'channels': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 'time': 5000, 'opcode': 'BRANCH', 'instdata': 0}]

class PulseBlaster:
    def __init__(self, time_offset, board_number, addresses, sequence, clock = 250e6, ):
        self.time_offset = time_offset
        self.board_number = board_number
        self.addresses = addresses
        self.clock = clock
        self.sequence = ast.literal_eval(sequence)

        try:
            pb_select_board(board_number)
            self.verification_string = pb_get_firmware_id()
        except Exception as err:
            logging.warning("PulseBlaster error in initial connection : "+str(err))
            self.verification_string = "True"
            self.__exit__()

        self.warnings = []
        self.new_attributes = []
        self.dtype = ('f4', 'int')
        self.shape = (2,)

        try:
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
    return time.time() = self.time_offset, status['running']

#######################################################
# PulseBlaster Commands
#######################################################

def ProgramDevice(self, board_number = None):

    if type(board_number) == None:
        board_number = self.board_number

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
