import json
import time
import uuid
from typing import Any
from urllib.request import urlopen

import rpyc


class Client(rpyc.Service):
    def __init__(self):
        super(Client, self).__init__()
        self.exposed_uuid = uuid.uuid4()


class LaserLockRPYC:
    def __init__(
        self,
        time_offset: float,
        address: str,
        port_rpyc: int,
        port_api: int,
        laser_synths: list[tuple[str, int]] = [
            ("SG1", 0),
            ("SG1", 1),
            ("SG2", 0),
        ],
        seed_names: list[str] = ["seed1", "seed2", "seed3"],
        linien_names: list[str] = ["linien-seed1", "linien-seed2", "linien-seed3"],
        dt_max: float = 5.0,
    ) -> None:
        """
        Class to interface with the CeNTREX laer lock reference system.

        Args:
            time_offset (float): acquisition start
            address (str): _description_
            port_rpyc (int): rpyc port
            port_api (int): rest api port
            laser_synths (list[tuple[str, int]], optional): List of tuples of SynthHD device names and channels for each laser. Defaults to [ ("SG1", 0), ("SG1", 1), ("SG2", 0), ].
            seed_names (list[str], optional): Seed laser names. Defaults to ["seed1", "seed2", "seed3"].
            linien_names (list[str], optional): Linien instance names. Defaults to ["linien-seed1", "linien-seed2", "linien-seed3"].
            dt_max (float, optional): Maximum allowed time difference between remote device data and local time. Defaults to 5.0.
        """
        self.time_offset = time_offset
        self.address = str(address).strip('"')
        self.port_rpyc = int(port_rpyc)
        self.port_api = int(port_api)
        self.laser_synths = laser_synths
        self.seed_names = seed_names
        self.linien_names = linien_names
        self.dt_max = dt_max

        self.nr_lasers = len(seed_names)

        # grab unique synthesizer device names
        _synths = [val[0] for val in laser_synths]
        self.synths = []
        for synth in _synths:
            if synth not in self.synths:
                self.synths.append(synth)

        self.conn: rpyc.Connection = rpyc.connect(
            self.address,
            self.port_rpyc,
            service=Client,
            config={
                "allow_all_attrs ": True,
                "allow_setattr": True,
                "allow_pickle": True,
                "allow_getattr": True,
                "allow_all_attrs": True,
            },
        )

        self.devices: dict[str, Any] = dict(
            [
                (name, self.conn.root.devices[name][0])
                for name in self.conn.root.devices.keys()
            ]
        )

        self.synth_data: dict[str, dict[str, Any]] = {}

        self.verification_string = self.conn.root.get_service_name()
        self.verification_string = "RUNNER"

        column_names_base = "lock, error mean, error std, control mean, emission, frequency, frequency setpoint, power, nltl enable, nltl frequency, nltl power".split(
            ","
        )
        units_base = ", , , , , GHz, GHz, mW, , MHz, dBm".split(",")
        units_base = [unit.strip() for unit in units_base]

        units = ["s"]
        column_names = ["time"]
        for i in range(self.nr_lasers):
            column_names.extend(
                [f"laser{i} {cname.strip()}" for cname in column_names_base]
            )
            units.extend(units_base)

        self.new_attributes = [
            ("column_names", ",".join(column_names)),
            ("units", ",".join(units)),
        ]
        self.dtype = "f"
        self.shape = (1 + self.nr_lasers * 11,)
        self.warnings = []

    def __exit__(self, *exc):
        # self.conn.close()
        return

    def __enter__(self):
        return self

    def ReadValue(self):
        seed_data: dict[str, dict[str, Any]] = {}
        for seed in self.seed_names:
            response = urlopen(f"http://{self.address}:{self.port_api}/{seed}/data")
            seed_data[seed] = json.loads(response.read())

        linien_data: dict[str, dict[str, Any]] = {}
        for linien in self.linien_names:
            response = urlopen(f"http://{self.address}:{self.port_api}/{linien}/data")
            linien_data[linien] = json.loads(response.read())

        for synth in self.synths:
            response = urlopen(f"http://{self.address}:{self.port_api}/{synth}/data")
            self.synth_data[synth] = json.loads(response.read())

            assert (
                time.time() - self.synth_data[synth]["time"] <= self.dt_max
            ), f"remote data more than {self.dt_max} seconds out of date"

        data = [time.time() - self.time_offset]
        for seed, linien, (synth, channel) in zip(
            self.seed_names, self.linien_names, self.laser_synths
        ):
            lin = linien_data[linien]
            syn = self.synth_data[synth]
            sd = seed_data[seed]

            dat = [
                lin["lock"],
                lin["error_signal_mean"],
                lin["error_signal_std"],
                lin["control_signal_mean"],
                sd["emission"],
                sd["frequency"],
                sd["frequency_setpoint"],
                sd["power"] / 100,
                syn[f"enable{channel}"],
                syn[f"frequency{channel}"] / 1e6,
                syn[f"power{channel}"],
            ]
            data.extend(dat)

        return data

    def GetWarnings(self):
        return

    def _update_synth_data(self, synth_name: str) -> None:
        self.synth_data[synth_name] = json.loads(
            urlopen(f"http://{self.address}:{self.port_api}/{synth_name}/data").read()
        )

    def move_laser_lockpoint(self, laser: int, lockpoint: float) -> None:
        """
        Move the laser lockpoint by changing the NLTL input frequency

        Args:
            laser (int): laser id
            lockpoint (float): lockpoint in MHz
        """
        name, channel = self.laser_synths[laser]
        self._update_synth_data(name)
        assert (
            time.time() - self.synth_data[name]["time"] <= self.dt_max
        ), f"remote data more than {self.dt_max} seconds out of date"

        # checking to make sure to not move the frequency more than a few MHz at a time
        frequency_set = self.synth_data[name][f"frequency{channel}"] / 1e6

        assert (
            abs(lockpoint - frequency_set) <= 6
        ), f"Can't move frequency more than 6 MHz without loss of lock; setpoint={frequency_set:.1f}, lockpoint={lockpoint:.1f}"

        ch = channel
        if name == "SG2":
            ch += 2

        self.devices[name].device.change_frequency_and_amplitude(ch + 1, lockpoint)

    def move_laser0_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(0, lockpoint)

    def move_laser1_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(1, lockpoint)

    def move_laser2_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(2, lockpoint)

    def move_laser3_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(3, lockpoint)
