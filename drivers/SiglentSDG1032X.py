import time
import pyvisa
import logging
import numpy as np

def validate_channel(func):
    def wrapper(*args, **kwargs):
        if args[1] in [1,2]:
            return func(*args, **kwargs)
        else:
            logging.warning(f'SiglentSDG1032X warning in {func.__name__}: invalid channel')
    return wrapper

class SiglentSDG1032X:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        if resource_name != 'client':
            try:
                self.instr = self.rm.open_resource(resource_name)
            except pyvisa.errors.VisaIOError:
                self.verification_string = "False"
                self.instr = False
                return
            self.instr.parity = pyvisa.constants.Parity.odd
            self.instr.data_bits = 7
            self.instr.baud_rate = 9600
            self.instr.term_char = '\n\r'

            # make the verification string
            self.verification_string = self.QueryIdentification()
        else:
            self.verification_string = 'True'

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = ('f', 'bool', 'S5', 'float', 'float', 'float',
                           'bool', 'S5', 'float', 'float', 'float')
        self.shape = (11, )

        self.waveforms = {1: {}, 2: {}}
        self.outputs = {1: {}, 2: {}}

        self.units = ['HZ', 'S', 'V', 'Vrms']

        if resource_name != 'client':
            self.ParseBasicWave(1)
            self.ParseBasicWave(2)
            self.ParseOutput(1)
            self.ParseOutput(2)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        self.ParseBasicWave(1)
        self.ParseBasicWave(2)
        self.ParseOutput(1)
        self.ParseOutput(2)
        vars = ['WVTP', 'FRQ', 'AMP', 'OFST']
        ret = [time.time()-self.time_offset, self.outputs[1]['STATE']]
        for var in vars:
            ret += [self.waveforms[1][var]]
        ret += [self.outputs[2]['STATE']]
        for var in vars:
            ret += [self.waveforms[2][var]]
        return ret

    def GetWarnings(self):
        return None

    def QueryIdentification(self):
        """Identifies the instrument model and software level.

        Returns:
        <manufacturer>, <model number>, <serial number>, <firmware date>
        """
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError:
            return np.nan

    #################################################################
    ##########         CeNTREX DAQ GUI COMMANDS            ##########
    #################################################################

    def GetOutputState1(self):
        if self.outputs[1]['STATE']:
            return 'On'
        else:
            return 'Off'

    def SetOutputState1(self, state):
        if state:
            self.Output(1,"ON")
        else:
            self.Output(1, "OFF")
        self.ParseOutput(1)

    def SetChannel1Frequency(self, freq):
        self.BasicWaveFrequency(1, freq)

    def SetChannel2Frequency(self, freq):
        self.BasicWaveFrequency(2, freq)

    def SetBurstMicrowaveDelay(self, freq, phase_offset=60):
        self.BasicWaveFrequency(1,freq)
        self.BasicWaveFrequency(2,freq)
        period = 1/freq
        delay1 = (180+phase_offset)*period/360
        delay2 = (180+(2*phase_offset))*period/360
        # minimum delay for a square wave is 591 ns, offset by half the period
        # to compensate
        if delay1 < 591e9:
            delay1 += period/2
            delay2 += period/2
        self.BurstWaveDelay(1, delay1)
        self.BurstWaveDelay(2, delay2)
        self.BurstWaveState(1,"OFF")
        self.BurstWaveState(2,"OFF")
        self.BurstWaveState(1,"ON")
        self.BurstWaveState(2, "ON")
        if not np.isclose(delay1, float(self.instr.query("C1:BTWV?")[8:].split(",")[9].strip('S')),atol = 1e-9):
            logging.warning("SiglentSDG1032X warning in BurstMicrowaveDelay: ch1 delay not set")
        if not np.isclose(delay2, float(self.instr.query("C2:BTWV?")[8:].split(",")[9].strip('S')),atol = 1e-9):
            logging.warning("SiglentSDG1032X warning in BurstMicrowaveDelay: ch2 delay not set")
        return

    def GetFrequencyFromSequencerBurst(self, parent_info):
        if len(np.shape(parent_info)) == 2:
            for info in parent_info:
                device, function, param = info
                if 'Frequency' in function:
                    self.SetBurstMicrowaveDelay(float(param))
        else:
            device, function, param = parent_info
            if device == "":
                return
            if 'Frequency' in function:
                self.SetBurstMicrowaveDelay(float(param))




    #################################################################
    ##########           CONVENIENCE COMMANDS              ##########
    #################################################################

    @validate_channel
    def ParseBasicWave(self, ch: int):
        string = self.GetBasicWave(ch)
        data = string.split(':')[1].split(' ')[1].split(',')
        self.waveforms[ch] = {}
        for idx in range(0,len(data),2):
            d = data[idx+1].strip()
            for u in self.units:
                if d.endswith(u):
                    self.waveforms[ch][data[idx]] = float(d[:-len(u)])
                    break
            else:
                try:
                    self.waveforms[ch][data[idx]] = float(d)
                except ValueError:
                    self.waveforms[ch][data[idx]] = d

    @validate_channel
    def ParseOutput(self, ch: int):
        string = self.GetOutput(ch)
        data = string.split(':')[1].split(' ')[1].split(',')
        self.outputs[ch] = {}
        self.outputs[ch]['STATE'] = True if data[0] in ['ON', 'On'] else False
        for idx in range(1,len(data),2):
            key = data[idx]
            val = data[idx+1].strip()
            self.outputs[ch][key] = val

    #################################################################
    ##########           IEEE-488/SERIAL COMMANDS          ##########
    #################################################################

    def CLS(self):
        """
        Clear all event registers, the error queue and cancels an *opc command
        """
        self.instr.write('*CLS')

    def RST(self):
        """
        Reset the function generator to its factory default state.
        """
        self.instr.write('*RST')

    def OPC(self):
        self.instr.query('*OPC?')

    @validate_channel
    def GetOutput(self, ch: int):
        cmd = f'C{ch}:OUTP?'
        return self.instr.query(cmd)

    @validate_channel
    def Output(self, ch: int, output: str):
        cmd = f'C{ch}:OUTP {output}'
        self.instr.write(cmd)

    @validate_channel
    def OutputImpedance(self, ch: int, impedance: str):
        if impedance in [50, '50', 'HZ']:
            cmd = f'C{ch}:OUTP LOAD,{impedance}'
            self.instr.write(cmd)
        else:
            logging.warning(f'SiglentSDG1032X warning in OutputImpedance: invalid impedance')

    def GetClockSource(self):
        cmd = f'ROSC?'
        return self.instr.query(cmd)

    def ClockSource(self, source: str):
        cmd = f'ROSC {source}'
        self.instr.write(cmd)

    def GetBasicWave(self, ch: int):
        cmd = f'C{ch}:BSWV?'
        return self.instr.query(cmd)

    @validate_channel
    def BasicWaveType(self, ch: int, wave: str):
        cmd = f'C{ch}:BSWV WVTP,{wave}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def BasicWaveFrequency(self, ch: int, freq: float):
        cmd = f'C{ch}:BSWV FRQ,{freq}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def BasicWaveAmplitude(self, ch: int, amp: float):
        cmd = f'C{ch}:BSWV AMP,{amp}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def BasicWaveDelay(self, ch: int, delay: float):
        cmd = f'C{ch}:BSWV DLY,{delay}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def Sinusoidal(self, ch: int, freq: float, amp: float = 1., offset: float = 0., phase: float = 0.):
        cmd = f'C{ch}:BSWV WVTP,SINE,FRQ,{freq},AMP,{amp},OFST,{offset},PHSE,{phase}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def Square(self, ch: int, freq: float, amp: float = 1., offset: float = 0., phase: float = 0.,
               duty: float = 50.):
        cmd = f'C{ch}:BSWV WVTP,SQUARE,FRQ,{freq},AMP,{amp},OFST,{offset},PHSE,{phase},DUTY,{duty}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def Pulse(self, ch: int, freq: float, amp: float = 3.3, offset: float = 1.625, delay: float = 0.,
               duty: float = 50.):
        cmd = f'C{ch}:BSWV WVTP,PULSE,FRQ,{freq},AMP,{amp},OFST,{offset},DLY,{delay},DUTY,{duty}'
        self.instr.write(cmd)
        self.ParseBasicWave(ch)

    @validate_channel
    def BurstWave(self, ch: int, state: str, gate_ncyc: str = 'gate', trigger: str = 'EXT',
                       polarity: str = 'POS', delay: float = 0, edge: str = 'RISE'):
        cmd = f'C{ch}:BTWV STATE,{state},GATE_NCYC,{gate_ncyc},TRSR,{trigger},DLY,{delay},PLRT,{polarity},'
        cmd += f'EDGE,{edge}'
        self.instr.write(cmd)

    @validate_channel
    def BurstWaveState(self, ch: int, state: str):
        cmd = f"C{ch}:BTWV STATE,{state}"
        self.instr.write(cmd)

    @validate_channel
    def BurstWaveDelay(self, ch: int, delay: float):
        cmd = f"C{ch}:BTWV DLAY,{delay}"
        self.instr.write(cmd)

if __name__ == "__main__":
    com_port = "USB0::0xF4EC::0x1103::SDG1XCAD2R3284::INSTR"
    sdg = SiglentSDG1032X(time.time(), com_port)
    print(sdg.QueryIdentification())
    print(sdg.GetOutputState1())
    print(sdg.ReadValue())

    # sdg.Pulse(1,1.5e6, amp = 3.3, offset = 1.625)
    # sdg.Pulse(2,1.5e6, amp = 3.3, offset = 1.625)
    # sdg.Output(1,'ON')

    # print(sdg.GetClockSource())

    # sdg.BasicWaveFrequency(1, 10e3)
    # sdg.BasicWaveType(1,'SQUARE')
    # print(sdg.waveforms)
    # print()
    # sdg.Output(1,'ON')
    # time.sleep(2)
    # sdg.Square(1,20e3, 3)
    # time.sleep(2)
    # sdg.Output(1,'OFF')
    # sdg.OutputImpedance(1,50)
    # time.sleep(2)
    # sdg.OutputImpedance(1,'HZ')

    # print('='*75)
    # print('Checking handling of invalid channel assignment')
    # sdg.OutputImpedance(3,'HZ')
    # print('='*75)

    # sdg.ParseOutput(1)
    # print(sdg.ReadValue())
    sdg.__exit__()
