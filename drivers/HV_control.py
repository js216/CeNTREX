from __future__ import annotations

import logging
import threading
import time

import numpy as np
import pyvisa


class RampVoltage(threading.Thread):
    def __init__(
        self,
        control: HV_control,
        setpoint: float,
        ramp_time: float,
        step_time: float = 0.05,
    ):
        super().__init__()

        self.control = control
        self.setpoint = setpoint
        self.ramp_time = time
        self.step_time = step_time

    def run(self):
        delta_voltage = self.control.ReadValue()[3] - self.setpoint
        ramp_rate = delta_voltage / self.ramp_time

        tstart = time.time()
        while True:
            new_setpoint = ramp_rate * (time.time() - tstart)
            new_setpoint = (
                new_setpoint if new_setpoint < self.setpoint else self.setpoint
            )
            self.control.SetVoltage(ramp_rate * time.time())
            if new_setpoint == self.setpoint:
                break
            time.sleep(self.step_time)


class HV_control:
    def __init__(self, time_offset: float, resource_name: str):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.term_char = "\n"
        self.instr.read_termination = "\r\n"
        self.instr.timeout = 1000

        # internal status
        self.HV_enabled = False
        self.polarity = "positive"
        self.voltage = 0

        # make the verification string
        try:
            self.verification_string = self.QueryIdentification()
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (6,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [time.time() - self.time_offset, *self.ReadVoltages()]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            time.sleep(2)
            return self.instr.query("?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HV_control warning in QueryIdentification(): " + str(err))
            return str(err)

    def ReadVoltages(self):
        # read the particulates data from the Arduino
        try:
            resp = self.instr.query("a")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HV_control warning in ReadVoltages(): " + str(err))
            return 5 * [np.nan]

        # convert the response to a number
        try:
            voltages = [float(x) for x in resp.split(",")]
            voltages = [
                (int(x) - 32768) / 65535 * (2 * 3 * 4.096) for x in resp.split(",")
            ]
        except ValueError as err:
            logging.warning("HV_control warning in ReadVoltages(): " + str(err))
            return 5 * [np.nan]

        # units conversion
        voltage_monitor = voltages[0] * 30 / 10
        current_monitor = voltages[1] * 400 / 10
        voltage_program = voltages[2] * 30 / 10
        divider_voltage = voltages[3]
        error_voltage = voltages[4]

        return [
            voltage_monitor,
            current_monitor,
            voltage_program,
            divider_voltage,
            error_voltage,
        ]

    def EnableHV(self):
        self.HV_enabled = True
        self.instr.write(f"h0")

    def DisableHV(self):
        self.HV_enabled = False
        self.instr.write(f"h1")

    def QueryEnabled(self):
        en_read = self.instr.query("H")
        if en_read == "0":
            return "enabled"
        elif en_read == "1":
            return "disabled"

    def SetPositive(self):
        if self.HV_enabled:
            logging.warning(
                "HV_control warning in SetPolarity(): cannot change polarity with HV enabled."
            )
        else:
            self.instr.write(f"p1")
            self.polarity = "positive"

    def SetNegative(self):
        if self.HV_enabled:
            logging.warning(
                "HV_control warning in SetPolarity(): cannot change polarity with HV enabled."
            )
        else:
            self.instr.write(f"p0")
            self.polarity = "negative"

    def QueryPolarity(self):
        pol_read = self.instr.query("P")
        if pol_read == "1":
            return "positive"
        elif pol_read == "0":
            return "negative"

    def SetVoltage(self, voltage):
        # convert units
        self.voltage = voltage
        voltage_DAC = int(55355 * (voltage / 30))
        self.instr.write(f"d{voltage_DAC}")

    def RampVoltage(
        self, voltage: float, ramp_time: float = 10, ramp_step: float = 0.05
    ):
        ramp = RampVoltage(self, voltage, ramp_time, ramp_step)
        ramp.start()

    def DoNothing(self, param):
        pass

    def DoNothing(self, param):
        pass
