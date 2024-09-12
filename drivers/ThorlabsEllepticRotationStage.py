from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from enum import Enum, auto

from thorlabs_elliptec import ELLx


class WarningLevel(Enum):
    WARNING = auto()
    ERROR = auto()


@dataclass
class ThorlabsEllipticRotationStageData:
    time: float
    angle: float


@dataclass
class ThorlabsEllipticRotationStageWarning:
    time: float
    message: str
    level: WarningLevel = WarningLevel.WARNING

    def to_text(self) -> str:
        ts_str = (
            datetime.datetime.fromtimestamp(self.time)
            .replace(microsecond=0)
            .isoformat()
        )
        return f"{ts_str} - {self.level.name} : {self.message}"


class ThorlabsEllipticRotationStage(ELLx):
    def __init__(self, time_offset: float, COM_port: str) -> None:
        super().__init__(x=14, device_serial=COM_port)
        self.time_offset = time_offset
        self.warnings = []
        self.new_attributes = []
        self.verification_string = self.serial_number

    def __exit__(self, *exc) -> None:
        pass

    def __enter__(self) -> ThorlabsEllipticRotationStage:
        return self

    def GetWarnings(self) -> list[ThorlabsEllipticRotationStageWarning]:
        warnings = self.warnings
        self.warnings = []
        status = self.status
        if status not in [0, 9]:
            warnings.append(
                ThorlabsEllipticRotationStageWarning(
                    time=time.time(),
                    message=status.name,
                    level=WarningLevel.ERROR,
                )
            )
        return warnings

    def ReadValue(self) -> ThorlabsEllipticRotationStageData:
        return ThorlabsEllipticRotationStageData(
            time=time.time() - self.time_offset, angle=self.get_position()
        )
