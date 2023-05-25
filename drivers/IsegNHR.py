from iseg_nhr import NHR
import time

def unpack_list(lst):
    unpacked = []
    for l in lst:
        unpacked.extend(l)
    return unpacked

class IsegNHR(NHR):
    def __init__(self, time_offset: int, resource_name: str):
        super().__init__(resource_name)

        self.time_offset = time_offset

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (1+self._channels * 3,)

        self.verification_string = self.firmware_version

        self.warnings = []

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        self._device.close()

    def ReadValue(self):
        setpoints = self.setpoints
        voltages = self.voltages
        currents = self.currents
        return [time.time() - self.time_offset, *unpack_list(list(zip(setpoints, voltages, currents)))]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def set_setpoint0(self, setpoint: float):
        self.channel0.voltage.setpoint = setpoint

    def set_setpoint1(self, setpoint: float):
        self.channel1.voltage.setpoint = setpoint

    def turn_on_ch0(self):
        self.channel0.on()

    def turn_off_ch0(self):
        self.channel0.off()

    def turn_on_ch1(self):
        self.channel1.on()

    def turn_off_ch1(self):
        self.channel1.off()

    def output0_state(self) -> str:
        if self.channel0.on_state:
            return "on"
        else:
            return "off"

    def output1_state(self) -> str:
        if self.channel1.on_state:
            return "on"
        else:
            return "off"
