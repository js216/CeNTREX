import time

import elliptec


class ThorlabsElliptecRotation(elliptec.Rotator):
    def __init__(self, time_offset: float, resource_name: str):
        self.time_offset = time_offset
        self.controller = elliptec.Controller(resource_name)
        super().__init__(controller=self.controller)

        self.dtype = "f"
        self.shape = (2,)

        self.verification_string = self.serial_no
        self.new_attributes = []
        self.warnings = []

    def ReadValue(self) -> tuple[float, float]:
        return [time.time() - self.time_offset, self.get_angle()]

    def GetWarnings(self) -> list:
        warnings = self.warnings
        self.warnings = []
        return warnings

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return
