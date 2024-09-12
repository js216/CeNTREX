# Driver for Pfeiffer pumps that use the TC 400 Electronic Drive Unit.
# The unit communicates in terms of "telegrams", which are ascii strings of a
# peculiar format. See Operating Instructions for details.
# Jakob Kastelic, 2019-02-11 Mon 12:24 PM

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal

from pfeiffer_turbo import TM700, ConnectionType


class WarningLevel(Enum):
    WARNING = auto()
    ERROR = auto()


@dataclass
class HiPace700Data:
    time: float
    speed: float
    current: float
    voltage: float
    power: float
    temperature_power_stage: float
    temperature_electric: float
    temperature_pump_bottom: float
    temperature_bearing: float
    temperature_motor: float
    rotor_imbalance: float
    bearing_wear: float


@dataclass
class HiPace700Warning:
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


class HiPace700(TM700):
    def __init__(self, time_offset: float, ip_port: str) -> None:
        super().__init__(
            self, resource_name=ip_port, address=1, connection_type=ConnectionType.TCPIP
        )
        self.time_offset = time_offset
        self.warnings = []

        # make the verification string
        self.verification_string = self.elec_name

        # HDF attributes generated when constructor is run
        self.new_attributes = []

    def __enter__(self) -> HiPace700:
        return self

    def __exit__(self, *exc) -> None:
        if self.instrument:
            self.instrument.close()

    def ReadValue(self) -> HiPace700Data:
        return HiPace700Data(
            time=time.time() - self.time_offset,
            speed=self.actual_spd,
            current=self.drv_currrent,
            voltage=self.drv_voltage,
            power=self.drive_power,
            temperature_power_stage=self.temp_pwr_stg,
            temperature_electric=self.temp_elect,
            temperature_pump_bottom=self.temp_pmp_bot,
            temperature_bearing=self.temp_bearng,
            temperature_motor=self.temp_motor,
            rotor_imbalance=self.rotor_imbalance,
            bearing_wear=self.bearing_wear,
        )

    def GetWarnings(self) -> list[HiPace700Warning]:
        if self.ov_temp_elec:
            self.warnings.append(
                HiPace700Warning(
                    time=time.time(),
                    message="overheating electrical",
                    level=WarningLevel.ERROR,
                )
            )
        if self.ov_temp_pump:
            self.warnings.append(
                HiPace700Warning(
                    time=time.time(),
                    message="overheating pump",
                    level=WarningLevel.ERROR,
                )
            )
        warnings = self.warnings
        self.warnings = []
        return warnings

    def TurboStatus(
        self,
    ) -> Literal["stopped", "running", "accelerating", "decelerating", "invalid"]:
        speed = self.actual_spd
        accel = self.pump_accel
        if speed == 0.0:
            return "stopped"
        elif speed and (abs(speed - 820) < 1):
            return "running"
        elif speed and (abs(speed - 820) > 819):
            return "stopped"
        elif speed and accel:
            return "accelerating"
        elif speed and (abs(speed - 820) > 1):
            return "decelerating"
        else:
            return "invalid"

    def BrakeOn(self) -> None:
        self.brake = True

    def BrakeOff(self) -> None:
        self.brake = False

    def StartPump(self) -> None:
        self.start()

    def StopPump(self) -> None:
        self.stop()

    def StartVent(self) -> None:
        self.enable_vent = True

    def StopVent(self) -> None:
        self.enable_vent = False
