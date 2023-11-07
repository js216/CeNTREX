import time

from pulseblaster import Signal, generate_pulses
from pulseblaster.device import PulseBlaster as Pulseblaster


class PulseBlaster(Pulseblaster):
    def __init__(self, time_offset: float, board_number: int, clock: int = 250):
        super().__init__(board_number, clock)
        self.time_offset = time_offset

        self.dtype = "f"
        self.shape = (1,)

        self.signals: list[Signal] = []

    def __exit__(self, *exc) -> None:
        return

    def ReadValue(self) -> float:
        return time.time() - self.time_offset

    def GetWarnings(self) -> None:
        return None

    def create_signal(
        self,
        frequency: float,
        offset: float,
        channels: int | list[int],
        duty_cycle: float = 0.5,
        high: int = 0,
        active_high: bool = True,
    ) -> None:
        self.signals.append(
            Signal(
                frequency=frequency,
                offset=offset,
                channels=channels,
                duty_cycle=duty_cycle,
                high=high,
                active_high=active_high,
            )
        )

    def clear_signals(self) -> None:
        self.signals = []

    def program_signals(self) -> None:
        sequence = generate_pulses.generate_repeating_pulses(self.signals)
        self.program(sequence.instructions)


if __name__ == "__main__":
    trigger_offset = 1  # ms
    trigger_high = 100_000  # 0.1 ms
    qswitch_delay = 80  # microseconds
    qswitch_high = 100_000
    flashlamp_high = 100_000
    frequency = 26  # Hz

    trigger = Signal(
        frequency=frequency, offset=0, high=100_000, channels=[0, 7], active_high=True
    )

    flashlamp = Signal(
        frequency=frequency,
        offset=int(trigger_offset * 1e6) + 0,
        high=flashlamp_high,
        channels=[1, 4],
        active_high=True,
    )

    qswitch = Signal(
        frequency=frequency,
        offset=int(trigger_offset * 1e6) + +int(qswitch_delay * 1e3),
        high=qswitch_high,
        channels=[2, 5],
        active_high=True,
    )

    shutter = Signal(
        frequency=frequency / 2,
        offset=int(1 / frequency * 1e9) - int(3e6),
        high=int(1 / frequency * 1e9),
        channels=[3, 6],
        active_high=True,
    )

    sequence = generate_pulses.generate_repeating_pulses(
        [trigger, flashlamp, qswitch, shutter]
    )

    pulse_gen = PulseBlaster(time.time(), board_number=0)

    pulse_gen.program(sequence=sequence.instructions)

    pulse_gen.start()

    import pickle

    with open("sequence.pkl", "wb") as f:
        pickle.dump(sequence, f)
