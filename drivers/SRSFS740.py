import time

import numpy as np
import numpy.typing as npt
from srs_fs740 import FS740, Channel, parse_timestamps


class SRSFS740(FS740):
    def __init__(self, time_offset: float, resource_name: str, channel: int) -> None:
        super().__init__(resource_name=resource_name)
        self.time_offset = time_offset

        self.verification_string = self.query_identification()

        self.channel = Channel(channel)

        self.dtype = (
            np.float64,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
            np.int16,
        )
        self.units = (
            "s",
            "",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "millisecond",
            "microsecond",
            "nanosecond",
            "picosecond",
        )
        self.shape = (12,)

    def __exit__(self, *exc):
        self.instr.close()

    def setup_time_measurement(self, channel: int | Channel) -> None:
        count = 1_000_000_000
        if not isinstance(channel, Channel):
            channel = Channel(channel)
        self.measure_configure_time(channel)
        self.sample_set_count(count)

    def ReadValue(self) -> list[list[float | np.int16]] | None:
        points_in_memory = self.data_query_points(self.channel)
        if points_in_memory == 0:
            return None
        else:
            data_raw = self.data_remove(self.channel, points_in_memory)
            data = parse_timestamps(data_raw)
            timestamps = np.array(
                [time.time() - self.time_offset for i in range(len(data))]
            )
            return [[ts] + list(dat) for ts, dat in zip(timestamps, data)]
