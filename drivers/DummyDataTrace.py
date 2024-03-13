import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import signal


@dataclass
class DummyDataTraceData:
    time: float
    data: npt.NDArray[np.float64]
    attrs: list[dict[str, Any]]
    shape: tuple[int] = (1, 2, 100)
    dtype: type | tuple[type, ...] = np.float64


class DummyDataTrace:
    def __init__(self, time_offset, period):
        self.time_offset = time_offset

        self.warnings = []
        self.new_attributes = []

        self.period = float(period)  # seconds
        self.verification_string = "test"

        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1, 2, 2000)
        self.dtype = float

    def __exit__(self, *exc):
        pass

    def __enter__(self):
        return self

    def GetWarnings(self):
        return self.warnings

    def ReadValue(self):
        t = time.time() - self.time_offset
        a = np.random.normal(1, 0.3)

        amp = signal.sawtooth(2 * np.pi / self.period * t, width=0.5) / 2 + 0.5 - 1
        amp *= a

        fl_signal = amp * (
            signal.gaussian(2000, 200) + np.random.randn(2000) / 10 - 0.5 / 10
        )
        ab_signal = a * (
            signal.gaussian(2000, 150) + np.random.randn(2000) / 5 - 0.5 / 10
        )

        return DummyDataTraceData(
            time.time() - self.time_offset,
            data=np.array([fl_signal, ab_signal]).reshape(self.shape),
            attrs=[{}],
            shape=self.shape,
            dtype=self.dtype,
        )
