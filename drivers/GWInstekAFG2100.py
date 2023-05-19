import time

import numpy as np
import pyvisa


class GWInstekAFG2100:
    def __init__(self, time_offset, resource_name: str, number_channels: int = 1):
        self.number_channels = int(number_channels)
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.odd
        self.instr.data_bits = 7
        self.instr.baud_rate = 9600
        self.instr.term_char = "\r\n"
        self.instr.read_termination = "\r\n"

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = ["f"] + ["S5", "f", "f"] * self.number_channels
        self.shape = (1 + 4 * self.number_channels,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        values = [time.time() - self.time_offset]
        for ch in range(self.number_channels):
            values.extend(
                [
                    self.GetSourceFunction(ch + 1),
                    self.GetSourceFrequency(ch + 1),
                    self.GetSourceAmplitude(ch + 1),
                ]
            )
        return values

    def GetWarnings(self):
        return None

    def QueryIdentification(self):
        """Identifies the instrument model and software level.

        Returns:
        <manufacturer>, <model number>, <serial number>, <firmware date>
        Format: GW INSTEK, AFG-2125, SN:XXXXXXXX,Vm.mm
        """
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def GetOutputState(self):
        output_state = self.GetOutput(1)
        if output_state:
            return "on"
        else:
            return "off"

    def EnableOutput(self):
        self.Output(1, True)

    def DisableOutput(self):
        self.Output(1, False)

    #################################################################
    ##########           IEEE-488/SERIAL COMMANDS          ##########
    #################################################################

    def CLS(self):
        """
        Clear all event registers, the error queue and cancels an *opc command
        """
        self.instr.write("*CLS")

    def RST(self):
        """
        Reset the function generator to its factory default state.
        """
        self.instr.write("*RST")

    def OPC(self):
        self.instr.query("*OPC?")

    def SAV(self, loc):
        """
        Saves the current instrument state to a specified save location or an
        ARB waveform to the specified location. When a state is saved, all the
        current instrument settings, functions, modulation parameters and
        waveforms are also saved. Memory locations 0~9, save the instrument
        state only, whilst memory locations 10~19 save ARB data.
        """
        cmd = f"*SAV {loc}"
        self.instr.write(cmd)

    def RCL(self, loc):
        """
        Recall previously saved instrument states from memory locations 0~9 or
        recall the previously saved ARB waveforms from memory locations 10~19.
        """
        cmd = f"*RCL {loc}"
        self.instr.write(cmd)

    def GetSourceFunction(self, ch: int):
        cmd = f"SOUR{ch}:FUNC?"
        return self.instr.query(cmd)

    def GetSourceFrequency(self, ch: int):
        cmd = f"SOUR{ch}:FREQ?"
        return self.instr.query(cmd)

    def GetSourceAmplitude(self, ch: int):
        cmd = f"SOUR{ch}:AMPL?"
        return self.instr.query(cmd)

    def GetSourceDCOffset(self, ch: int):
        cmd = f"SOUR{ch}:DCO?"
        return self.instr.query(cmd)

    def GetOutput(self, ch: int):
        cmd = f"SOUR{ch}:OUTP?"
        return self.instr.query(cmd)

    def Output(self, ch: int, output):
        cmd = f"SOUR{ch}:OUTP {output}"
        self.instr.write(cmd)

    def GetSourceVoltageUnit(self, ch: int):
        cmd = f"SOUR{ch}:VOLT:UNIT?"
        return self.instr.query(cmd)

    def SourceVoltageUnit(self, ch: int, unit):
        cmd = f"SOUR{ch}:VOLT:UNIT {unit}"
        return self.instr.write(cmd)

    def GetSourceApply(self, ch: int):
        cmd = f"SOUR{ch}:APPL?"
        return self.instr.query(cmd)

    def SourceApplySinusoid(self, ch: int, frequency, amplitude, offset):
        cmd = f"SOUR{ch}:APPL:SIN {frequency},{amplitude},{offset}"
        self.instr.write(cmd)

    def SourceApplySquare(self, ch: int, frequency, amplitude, offset):
        cmd = f"SOUR{ch}:APPL:SQU {frequency},{amplitude},{offset}"
        self.instr.write(cmd)

    def SourceFrequency(self, ch: int, frequency):
        cmd = f"SOUR{ch}:FREQ {frequency}"
        self.instr.write(cmd)

    def SourceAmplitude(self, ch: int, amplitude):
        cmd = f"SOUR{ch}:AMPL {amplitude}"
        self.instr.write(cmd)

    def SourceDCOffset(self, ch: int, offset):
        cmd = f"SOUR{ch}:DCO {offset}"
        self.instr.write(cmd)


if __name__ == "__main__":
    resource_name = input("specify resource name : ")
    afg = GWInstekAFG2100(time.time(), resource_name)
    print(afg.verification_string)
    print(afg.GetOutput(1))
    afg.Output(1, "OFF")
    afg.SourceFrequency(1, 2e6)
    afg.SourceAmplitude(1, 0.5)
    afg.SourceDCOffset(1, 0.25)
    afg.Output(1, "ON")
    time.sleep(5)
    afg.Output(1, "OFF")
    afg.SourceFrequency(1, 1.562e6)
    afg.SourceAmplitude(1, 0.75)
    afg.SourceDCOffset(1, 0)
    afg.Output(1, "ON")
    time.sleep(5)
    afg.SourceApplySquare(1, 1.5e6, 1.5, 1.5 / 2)
    time.sleep(5)
    afg.Output(1, "OFF")

    afg.__exit__()
