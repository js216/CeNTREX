import time
from precilaser import SHGAmplifier

class PrecilaserSHGAmplifier(SHGAmplifier):
    def __init__(self, time_offset: float, resource: str):
        super().__init__(resource, address = 0)
        self.time_offset = time_offset

        self.dtype = (
            "f", "bool", "bool", "f8", "f8", "f8", "f8", "int8", "int8", "int8", "int8"
        )
        self.shape = (11,)

        self.new_attributes = []

        self.warnings = []

        self.verification_string = "precilaser"

    # CeNTREX GUI functions
    
    def __exit__(self, *exc):
        return

    def __enter__(self):
        return self

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        status = self.status
        return [
            time.time() - self.time_offset,
            all(status.driver_unlock.driver_enable_control),
            self.fault,
            sum(self.current),
            self.shg_temperature,
            *status.temperatures[:2],
            *status.pd_value,
        ]

    def get_current(self) -> float:
        return sum(self.current)

    def set_current(self, current: float) -> float:
        self.current = current

    def get_enabled(self) -> str:
        return str(all(self.status.driver_unlock.driver_enable_control))

    