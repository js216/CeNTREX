import time

import numpy as np
import numpy.typing as npt
from srs_fs740 import FS740, parse_timestamps, MeasureChannel


class SRSFS740(FS740):
    def __init__(self, time_offset: float, resource_name: str, channel: str | int) -> None:
        super().__init__(resource_name=resource_name)
        self.time_offset = time_offset

        self.verification_string = self.query_identification()

        if isinstance(channel, str):
            channel = int(channel)
        elif isinstance(channel, int):
            pass
        else:
            raise TypeError("Channel should be either int or string")
        self.channel = MeasureChannel(channel)

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

        self.warnings = []
        # HDF attributes generated when constructor is run
        self.new_attributes = []

        self.setup_time_measurement(self.channel)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.measure_abort(self.channel)
        self.instr.close()

    def setup_time_measurement(self, channel: int | MeasureChannel) -> None:
        count = 1_000_000_000
        if not isinstance(channel, MeasureChannel):
            channel = MeasureChannel(channel)
        self.channel = channel
        self.measure_abort(MeasureChannel.FRONT)
        self.measure_abort(MeasureChannel.REAR)
        for _ in range(5):
            if self.query_operation_complete():
                break
            time.sleep(0.2)
        self.instr.write(f"INP{channel}:LEV 1.0")
        self.instr.write(f"INP{channel}:SLOP POS")
        self.measure_configure_time(channel)
        # self.sample_set_count(count)
        self.instr.write(f"SAMP{channel}:COUN {count}")
        # timeout for checking if operations are complete
        for _ in range(5):
            if self.query_operation_complete():
                break
            time.sleep(0.2)
        self.measure_initiate(channel)

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
            dat = [[ts] + list(dat) for ts, dat in zip(timestamps, data)]
            return dat

    def GetWarnings(self) -> None:
        return None