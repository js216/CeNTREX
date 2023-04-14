import logging
import time


def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]


def check_voltage(voltage: float, setpoint: float, tolerance: float = 0.02) -> bool:
    if setpoint == 0:
        return setpoint == voltage
    else:
        return abs(voltage - setpoint) < (tolerance * voltage)


def check_voltage_loop(
    device,
    param_name: str,
    voltage: float,
    dt: float = 0.5,
    total_time: float = 10,
    tolerance: float = 0.02,
):
    col_names = split(device.config["attributes"]["column_names"])
    tstart = time.time()
    while True:
        try:
            device.commands.append("ReadValue()")
            latest_data = device.config["plots_queue"][-1]
        except IndexError:
            return
        # enabling 12V fans, doubling stage
        if check_voltage(
            latest_data[col_names.index(param_name)], voltage, tolerance=tolerance
        ):
            break
        if time.time() - tstart >= total_time:
            error_message = (
                f"MicrowaveRCPSU: check_voltage_loop: exceeded {total_time} s,"
                f" {latest_data[col_names.index(param_name)]} V != {voltage} V"
            )
            logging.error(error_message)
            raise ValueError(error_message)
        time.sleep(dt)


class MicrowaveRCPSU:
    def __init__(self, parent, time_offset, psu_12pos_vd_5neg, psu_vg_5pos, psu_a_5pos):
        self.parent = parent
        self.time_offset = time_offset

        self.psu_12pos_vd_5neg = psu_12pos_vd_5neg
        self.psu_vg_5pos = psu_vg_5pos
        self.psu_a_5pos = psu_a_5pos

        # make the verification string
        self.verification_string = "N/A"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (0,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def ReadValue(self):
        return

    def start_J12(self):
        psu_vg_5pos = self.parent.devices[self.psu_vg_5pos]
        psu_12pos_vd_5neg = self.parent.devices[self.psu_12pos_vd_5neg]

        # enable 12V fans, doubling stage
        psu_12pos_vd_5neg.commands.append("set_ch1_voltage(12)")
        psu_12pos_vd_5neg.commands.append("set_ch1_current(3)")
        psu_12pos_vd_5neg.commands.append("output(True, 1)")

        check_voltage_loop(psu_12pos_vd_5neg, "ch1 voltage", 12)

        # enable +/- 5V for the SPDT switches
        psu_vg_5pos.commands.append("output(True, 3)")
        psu_12pos_vd_5neg.commands.append("output(True, 3)")

        # enable amplifiers
        # first set the gate voltage to -1.5V
        psu_vg_5pos.commands.append("set_ch1_voltage(1.5)")
        psu_vg_5pos.commands.append("set_ch1_current(0.07)")
        psu_vg_5pos.commands.append("set_ch2_voltage(1.5)")
        psu_vg_5pos.commands.append("set_ch2_current(0.07)")

        psu_vg_5pos.commands.append("output(True, 1)")
        psu_vg_5pos.commands.append("output(True, 2)")

        check_voltage_loop(psu_vg_5pos, "Vg1 voltage", 1.5)
        check_voltage_loop(psu_vg_5pos, "Vg2 voltage", 1.5)

        # turn on the VD = +6V PSU
        psu_12pos_vd_5neg.commands.append("set_ch2_voltage(6.0)")
        psu_12pos_vd_5neg.commands.append("set_ch2_current(3.2)")

        psu_12pos_vd_5neg.commands.append("output(True, 2)")

        check_voltage_loop(psu_12pos_vd_5neg, "Vd voltage", 6)

    def stop_J12(self):
        psu_vg_5pos = self.parent.devices[self.psu_vg_5pos]
        psu_12pos_vd_5neg = self.parent.devices[self.psu_12pos_vd_5neg]

        psu_vg_5pos.commands.append("ReadValue()")
        latest_data = psu_vg_5pos.config["plots_queue"][-1]
        col_names = split(psu_vg_5pos.config["attributes"]["column_names"])

        # check if Vg1 is already disabled or set to 0 V
        if latest_data[col_names.index("Vg1 voltage")] != 0:
            psu_vg_5pos.commands.append("set_ch1_voltage(1.5)")
            check_voltage_loop(psu_vg_5pos, "Vg1 voltage", 1.5)

        # check if Vg2 is already disabled or set to 0 V
        if latest_data[col_names.index("Vg2 voltage")] != 0:
            psu_vg_5pos.commands.append("set_ch2_voltage(1.5)")
            check_voltage_loop(psu_vg_5pos, "Vg2 voltage", 1.5)

        psu_12pos_vd_5neg.commands.append("set_ch2_voltage(0)")
        psu_12pos_vd_5neg.commands.append("set_ch2_current(0)")

        check_voltage_loop(psu_12pos_vd_5neg, "Vd voltage", 0)

        psu_12pos_vd_5neg.commands.append("output(False, 2)")

        psu_vg_5pos.commands.append("output(False, 1)")
        psu_vg_5pos.commands.append("output(False, 2)")
        psu_vg_5pos.commands.append("output(False, 3)")

    def start_J23(self):
        psu_a_5pos = self.parent.devices[self.psu_a_5pos]
        psu_12pos_vd_5neg = self.parent.devices[self.psu_12pos_vd_5neg]

        # enable 12V fans, doubling stage
        psu_12pos_vd_5neg.commands.append("set_ch1_voltage(12)")
        psu_12pos_vd_5neg.commands.append("set_ch1_current(3)")
        psu_12pos_vd_5neg.commands.append("output(True, 1)")

        check_voltage_loop(psu_12pos_vd_5neg, "ch1 voltage", 12)

        # enable +/- 5V for the SPDT switches
        psu_a_5pos.commands.append("output(True, 3)")
        psu_12pos_vd_5neg.commands.append("output(True, 3)")

        # enable 12V for the two 40 GHz amplifiers
        psu_a_5pos.commands.append("set_ch1_voltage(12)")
        psu_a_5pos.commands.append("set_ch1_current(2.5)")
        psu_a_5pos.commands.append("set_ch2_voltage(12)")
        psu_a_5pos.commands.append("set_ch2_current(2.5)")

        psu_a_5pos.commands.append("output(True, 1)")
        psu_a_5pos.commands.append("output(True, 2)")

        check_voltage_loop(psu_a_5pos, "A1 voltage", 12)
        check_voltage_loop(psu_a_5pos, "A2 voltage", 12)

    def stop_J23(self):
        psu_a_5pos = self.parent.devices[self.psu_a_5pos]

        psu_a_5pos.commands.append("output(False, 3)")
        psu_a_5pos.commands.append("set_ch1_voltage(0)")
        psu_a_5pos.commands.append("set_ch2_voltage(0)")

        # some time to ramp the voltage down
        time.sleep(2)

        psu_a_5pos.commands.append("output(False, 1)")
        psu_a_5pos.commands.append("output(False, 2)")

    def start_all(self):
        self.start_J12()
        self.start_J23()

    def stop_all(self):
        self.stop_J12()
        self.stop_J23()

        psu_12pos_vd_5neg = self.parent.devices[self.psu_12pos_vd_5neg]

        psu_12pos_vd_5neg.commands.append("set_ch1_voltage(0)")

        psu_12pos_vd_5neg.commands.append("output(False, 1)")
        psu_12pos_vd_5neg.commands.append("output(False, 3)")

    def all_status(self) -> str:
        psu_vg_5pos = self.parent.devices[self.psu_vg_5pos]
        psu_12pos_vd_5neg = self.parent.devices[self.psu_12pos_vd_5neg]
        psu_a_5pos = self.parent.devices[self.psu_a_5pos]

        latest_data_vg_5pos = psu_vg_5pos.config["plots_queue"][-1]
        latest_data_12pos_vd_5neg = psu_12pos_vd_5neg.config["plots_queue"][-1]
        lastest_data_a_5pos = psu_a_5pos.config["plots_queue"][-1]

        col_names = split(psu_vg_5pos.config["attributes"]["column_names"])
        vg1 = latest_data_vg_5pos[col_names.index("Vg1 voltage")]
        vg2 = latest_data_vg_5pos[col_names.index("Vg2 voltage")]

        col_names = split(psu_12pos_vd_5neg.config["attributes"]["column_names"])
        twelveV = latest_data_12pos_vd_5neg[col_names.index("ch1 voltage")]

        col_names = split(psu_a_5pos.config["attributes"]["column_names"])
        a1 = lastest_data_a_5pos[col_names.index("A1 voltage")]
        a2 = lastest_data_a_5pos[col_names.index("A2 voltage")]

        if vg1 > 0 and vg2 > 0 and twelveV > 11.9 and a1 > 0 and a2 > 0:
            return "on"
        else:
            return "off"

    def J12_status(self) -> str:
        psu_vg_5pos = self.parent.devices[self.psu_vg_5pos]

        latest_data_vg_5pos = psu_vg_5pos.config["plots_queue"][-1]

        col_names = split(psu_vg_5pos.config["attributes"]["column_names"])
        vg1 = latest_data_vg_5pos[col_names.index("Vg1 voltage")]
        vg2 = latest_data_vg_5pos[col_names.index("Vg2 voltage")]

        if vg1 > 0 and vg2 > 0:
            return "on"
        else:
            return "off"

    def J23_status(self) -> str:
        psu_a_5pos = self.parent.devices[self.psu_a_5pos]

        lastest_data_a_5pos = psu_a_5pos.config["plots_queue"][-1]

        col_names = split(psu_a_5pos.config["attributes"]["column_names"])
        a1 = lastest_data_a_5pos[col_names.index("A1 voltage")]
        a2 = lastest_data_a_5pos[col_names.index("A2 voltage")]

        if a1 > 0 and a2 > 0:
            return "on"
        else:
            return "off"
