import time

import pyvisa
from big_sky_yag import BigSkyYag as BigSkyYagDriver
from big_sky_yag.attributes import QSwitchMode, Status, Trigger


class BigSkyYag(BigSkyYagDriver):
    def __init__(self, time_offset: float, resource_name: str):
        self.time_offset = time_offset
        if resource_name != "client":
            try:
                super().__init__(resource_name=resource_name)
            except pyvisa.errors.VisaIOError as err:
                self.verification_string = str(err)
                self.instrument = False
                return
        self.verification_string = self.serial_number

        # HDF attributes generated when the constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (1,)
        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instrument:
            self.instrument.close()

    def ReadValue(self):
        return [
            time.time() - self.time_offset,
            self.temperature_cooling_group,
            self.flashlamp.voltage,
            self.pump,
            self.status(),
        ]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def status(self) -> bool:
        laser_status = self.laser_status
        return (
            laser_status.interlock
            & (laser_status.flashlamp == Status.START)
            & (laser_status.q_switch == Status.START)
        )

    def open_shutter(self):
        self.shutter = True

    def close_shutter(self):
        self.shutter = False

    def state_shutter(self) -> bool:
        return self.shutter

    def flashlamp_frequency(self, frequency: float):
        self.flashlamp.frequency = frequency

    def flashlamp_trigger(self, trigger: str):
        self.flashlamp.trigger = Trigger[trigger]

    def state_flashlamp_trigger(self) -> str:
        return self.flashlamp.trigger.name

    def flashlamp_voltage(self, voltage: float):
        self.flashlamp.voltage = voltage

    def state_flashlamp_voltage(self) -> float:
        return self.flashlamp.voltage

    def activate_flashlamp(self):
        self.flashlamp.activate()

    def stop_flashlamp(self):
        self.flashlamp.stop()

    def qswitch_mode(self, mode: str):
        self.qswitch.mode = QSwitchMode[mode]

    def state_qswitch_mode(self) -> str:
        return self.qswitch.mode.name

    def qswitch_delay(self, delay: int):
        self.qswitch.delay = delay

    def state_qswitch_delay(self) -> int:
        return self.qswitch.delay

    def on_qswitch(self):
        self.qswitch.on()

    def off_qswitch(self):
        self.qswitch.off()

    def start_qswitch(self):
        self.qwitch.start()

    def stop_qswitch(self):
        self.qswitch.stop()

    def start_pump(self):
        self.pump = "on"

    def stop_pump(self):
        self.pump = "off"

    def status_pump(self):
        return str(self.pump)

    def start(self):
        self.shutter = "open"
        self.flashlamp.activate()
        self.qswitch.start()

    def stop(self):
        self.qswitch.stop()
        self.flashlamp.stop()
        self.shutter = "close"

    def status_string(self) -> str:
        return str(self.status())
