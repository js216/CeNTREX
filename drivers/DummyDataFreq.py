import logging
import time
from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass
class DummyDataFreqData:
    time: float
    frequency: float


class DummyDataFreq:
    def __init__(self, time_offset, period, frequency_span):
        self.time_offset = time_offset

        self.warnings = []
        self.new_attributes = []

        self.verification_string = "test"

        self.period = float(period)  # seconds
        self.frequency_span = float(frequency_span)

        self.new_attributes = []

    def __exit__(self, *exc):
        pass

    def __enter__(self):
        return self

    def GetWarnings(self):
        return self.warnings

    def ReadValue(self) -> DummyDataFreqData:
        t = time.time() - self.time_offset

        if np.random.choice([0, 1]):
            return DummyDataFreqData(
                t,
                self.frequency_span
                * signal.sawtooth(2 * np.pi / self.period * t, width=1),
            )
        else:
            return DummyDataFreqData(t, -1000)

    def test(self, value):
        logging.info(f"DummyDataFreq: test({value})")
