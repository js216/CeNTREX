from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import zmq


class LaserLockCompatible:
    """
    Legacy-compatible LaserLock client that talks to experiment-control.
    Configured for network defaults at 10.10.222.31.

    Telemetry:
      manager PUB (7001) -> ZMQ SUB (manager.telemetry_update)
    Commands:
      FastAPI (8000) -> /api/devices/{device_id}/call
    """

    def __init__(
        self,
        time_offset: float,
        address: str = "10.10.222.31",
        port_api: int = 8001,
        manager_pub_endpoint: str | None = None,
        laser_synths: list[tuple[str, int]] | None = None,
        laser_labels: list[str] | None = None,
        seed_names: list[str] | None = None,
        dt_max: float = 5.0,
        nr_lasers: int | None = None,
        max_lockpoint_step_mhz: float = 6.0,
        lockpoint_in_mhz: bool = True,
        request_timeout_s: float = 2.0,
        seed_emission_signal: str = "emission",
        seed_frequency_signal: str = "frequency",
        seed_frequency_setpoint_signal: str = "frequency_setpoint",
        seed_power_signal: str = "power",
        synth_enable_signal_fmt: str = "enable {channel}",
        synth_frequency_signal_fmt: str = "frequency {channel}",
        synth_power_signal_fmt: str = "power {channel}",
    ) -> None:
        self.time_offset = float(time_offset)
        self.address = str(address).strip('"')
        self.port_api = int(port_api)

        # Updated default port to 7001
        self.manager_pub_endpoint = (
            str(manager_pub_endpoint)
            if manager_pub_endpoint
            else f"tcp://{self.address}:7001"
        )

        default_laser_synths = [("SG1", 0), ("SG1", 1), ("SG3", 1)]
        default_laser_labels = ["RC", "ABS", "DET1"]
        raw_laser_synths = list(laser_synths) if laser_synths is not None else default_laser_synths
        self.laser_synths = [(str(synth), int(channel)) for synth, channel in raw_laser_synths]
        self.nr_lasers = len(self.laser_synths) if nr_lasers is None else int(nr_lasers)
        if laser_labels is not None:
            self.laser_labels = list(laser_labels)
        elif self.laser_synths == default_laser_synths:
            self.laser_labels = default_laser_labels
        else:
            self.laser_labels = [f"laser{i}" for i in range(self.nr_lasers)]
        self.seed_names = list(seed_names) if seed_names is not None else []

        self.dt_max = float(dt_max)
        self.max_lockpoint_step_mhz = float(max_lockpoint_step_mhz)
        self.lockpoint_in_mhz = bool(lockpoint_in_mhz)
        self.request_timeout_s = float(request_timeout_s)

        self.seed_emission_signal = str(seed_emission_signal)
        self.seed_frequency_signal = str(seed_frequency_signal)
        self.seed_frequency_setpoint_signal = str(seed_frequency_setpoint_signal)
        self.seed_power_signal = str(seed_power_signal)
        self.synth_enable_signal_fmt = str(synth_enable_signal_fmt)
        self.synth_frequency_signal_fmt = str(synth_frequency_signal_fmt)
        self.synth_power_signal_fmt = str(synth_power_signal_fmt)

        if self.nr_lasers <= 0:
            raise ValueError("nr_lasers must be > 0")
        if len(self.laser_synths) != self.nr_lasers:
            raise ValueError("laser_synths length must match nr_lasers")
        if len(self.laser_labels) != self.nr_lasers:
            raise ValueError("laser_labels length must match nr_lasers")
        if self.seed_names and len(self.seed_names) != self.nr_lasers:
            raise ValueError("seed_names length must match nr_lasers")

        self.synths: list[str] = []
        for synth, _channel in self.laser_synths:
            if synth not in self.synths:
                self.synths.append(synth)

        self.verification_string = "LASERLOCK_EXPERIMENT_CONTROL"
        self.new_attributes, self.dtype, self.shape = self.generate_new_attributes(
            self.laser_labels
        )
        self.warnings: list[list[Any]] = []

        self._cache_lock = threading.Lock()
        self._telemetry_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._stop_event = threading.Event()
        self._ctx = zmq.Context.instance()
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.setsockopt(zmq.SUBSCRIBE, b"manager.telemetry_update")
        self._sub.setsockopt(zmq.RCVTIMEO, 200)
        self._sub.setsockopt(zmq.LINGER, 0)
        self._sub.connect(self.manager_pub_endpoint)
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop, name="laserlock-telemetry", daemon=True
        )
        self._telemetry_thread.start()

    @staticmethod
    def generate_new_attributes(
        laser_labels: list[str] | None = None,
    ) -> tuple[list[tuple[str, str]], str, tuple[int]]:
        labels = list(laser_labels) if laser_labels is not None else ["RC", "ABS", "DET1"]
        column_names_base = "nltl enable, nltl frequency, nltl power".split(",")
        units_base = ["", "MHz", "dBm"]

        units = ["s"]
        column_names = ["time"]
        for label in labels:
            column_names.extend(
                [f"{label} {cname.strip()}" for cname in column_names_base]
            )
            units.extend(units_base)

        new_attributes = [
            ("column_names", ",".join(column_names)),
            ("units", ",".join(units)),
        ]
        dtype = "f"
        shape = (1 + len(labels) * 3,)
        return new_attributes, dtype, shape

    def __enter__(self) -> LaserLockCompatible:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """ Ensures the class cleans up when exiting a 'with' block. """
        self.close()
        return False  # Propagate exceptions if they occurred inside the block

    def close(self) -> None:
        """
        Signals the background thread to stop and waits for it to join.
        This prevents the 'signaler.cpp' crash by ensuring the thread
        is done before the main process moves on.
        """
        if self._stop_event.is_set():
            return

        self._stop_event.set()

        # We wait for the thread to exit its loop and close its own socket
        if hasattr(self, "_telemetry_thread") and self._telemetry_thread.is_alive():
            # A 1-2 second timeout is usually plenty for ZMQ RCVTIMEO to trigger
            self._telemetry_thread.join(timeout=2.0)

        # Clean up the context if this instance owns it uniquely
        # (Though with zmq.Context.instance(), it's usually shared)

    def GetWarnings(self) -> list[list[Any]]:
        with self._cache_lock:
            out = list(self.warnings)
            self.warnings.clear()
        return out

    def _warn(self, message: str) -> None:
        with self._cache_lock:
            self.warnings.append([time.time(), {"message": str(message)}])
            if len(self.warnings) > 200:
                self.warnings = self.warnings[-200:]

    def _telemetry_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                topic_b, payload_b = self._sub.recv_multipart()
            except zmq.Again:
                continue
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                self._warn(f"telemetry receive error: {exc}")
                continue

            try:
                topic = topic_b.decode("utf-8", errors="replace")
            except Exception:
                topic = ""
            if topic != "manager.telemetry_update":
                continue

            try:
                payload = json.loads(payload_b.decode("utf-8"))
            except Exception as exc:
                self._warn(f"telemetry decode error: {exc}")
                continue
            if not isinstance(payload, dict):
                continue

            device_id = str(payload.get("device_id", "")).strip()
            signals = payload.get("signals")
            if not device_id or not isinstance(signals, dict):
                continue

            bundle_ts = payload.get("ts")
            bundle_wall = time.time()
            if isinstance(bundle_ts, dict):
                raw_t_wall = bundle_ts.get("t_wall")
                if isinstance(raw_t_wall, (int, float)):
                    bundle_wall = float(raw_t_wall)

            recv_wall = time.time()
            with self._cache_lock:
                dev_cache = self._telemetry_cache.setdefault(device_id, {})
                for signal_name, raw_signal in signals.items():
                    if not isinstance(signal_name, str):
                        continue
                    if not isinstance(raw_signal, dict):
                        continue
                    value = raw_signal.get("value")
                    signal_ts = raw_signal.get("ts")
                    signal_wall = bundle_wall
                    if isinstance(signal_ts, dict):
                        raw_signal_wall = signal_ts.get("t_wall")
                        if isinstance(raw_signal_wall, (int, float)):
                            signal_wall = float(raw_signal_wall)
                    dev_cache[signal_name] = {
                        "value": value,
                        "t_wall": signal_wall,
                        "recv_wall": recv_wall,
                    }

    def _device_call(
        self, device_id: str, action: str, params: dict[str, Any] | None = None
    ) -> Any:
        if params is None:
            params = {}
        body = json.dumps({"action": action, "params": params}).encode("utf-8")
        encoded_id = quote(device_id, safe="")
        url = f"http://{self.address}:{self.port_api}/api/devices/{encoded_id}/call"
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=self.request_timeout_s) as resp:
            raw = resp.read()
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise RuntimeError("invalid response payload")
        if not bool(parsed.get("ok")):
            error = parsed.get("error")
            if isinstance(error, dict):
                code = str(error.get("code", "") or "")
                message = str(error.get("message", "") or "")
                if code and message:
                    raise RuntimeError(f"{code}: {message}")
                if message:
                    raise RuntimeError(message)
                if code:
                    raise RuntimeError(code)
            raise RuntimeError(str(error))
        return parsed.get("result")

    def _latest_value(self, device_id: str, signal: str) -> tuple[Any, float]:
        with self._cache_lock:
            dev_cache = self._telemetry_cache.get(device_id, {})
            sample = dev_cache.get(signal)
        if sample is None:
            raise KeyError(f"missing telemetry {device_id}.{signal}")
        t_wall = sample.get("t_wall")
        if not isinstance(t_wall, (int, float)):
            t_wall = sample.get("recv_wall")
        if not isinstance(t_wall, (int, float)):
            t_wall = time.time()
        age_s = time.time() - float(t_wall)
        if age_s > self.dt_max:
            raise AssertionError(
                f"remote data more than {self.dt_max} seconds out of date "
                f"for {device_id}.{signal} (age={age_s:.3f}s)"
            )
        return sample.get("value"), float(age_s)

    def _to_float(self, value: Any, *, field: str) -> float:
        try:
            return float(value)
        except Exception as exc:
            raise TypeError(f"{field} is not numeric: {value!r}") from exc

    def _to_bool(self, value: Any, *, field: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "on", "yes"}:
                return True
            if text in {"false", "0", "off", "no"}:
                return False
        raise TypeError(f"{field} is not boolean-like: {value!r}")

    def ReadValue(self) -> list[Any]:
        try:
            data: list[Any] = [time.time() - self.time_offset]
            for laser_idx, (synth_id, channel) in enumerate(self.laser_synths):
                label = self.laser_labels[laser_idx]
                syn_enable_signal = self.synth_enable_signal_fmt.format(channel=channel)
                syn_frequency_signal = self.synth_frequency_signal_fmt.format(channel=channel)
                syn_power_signal = self.synth_power_signal_fmt.format(channel=channel)
                syn_enable, _ = self._latest_value(synth_id, syn_enable_signal)
                syn_frequency_hz, _ = self._latest_value(synth_id, syn_frequency_signal)
                syn_power_dbm, _ = self._latest_value(synth_id, syn_power_signal)

                row = [
                    self._to_bool(syn_enable, field=f"{label} nltl enable"),
                    self._to_float(syn_frequency_hz, field=f"{label} nltl frequency")
                    / 1e6,
                    self._to_float(syn_power_dbm, field=f"{label} nltl power"),
                ]
                data.extend(row)
            return data
        except Exception:
            return None

    def _current_synth_frequency_mhz(self, synth_id: str, channel: int) -> float:
        signal_name = self.synth_frequency_signal_fmt.format(channel=channel)
        try:
            frequency_hz, _age = self._latest_value(synth_id, signal_name)
            return self._to_float(
                frequency_hz, field=f"{synth_id}.{signal_name}"
            ) / 1e6
        except Exception:
            result = self._device_call(synth_id, f"get_frequency_channel_{channel}", {})
            return self._to_float(
                result, field=f"{synth_id}.get_frequency_channel_{channel}"
            ) / 1e6

    def move_laser_lockpoint(self, laser: int, lockpoint: float) -> None:
        laser_idx = int(laser)
        if laser_idx < 0 or laser_idx >= len(self.laser_synths):
            raise IndexError(f"laser index out of range: {laser_idx}")

        synth_id, channel = self.laser_synths[laser_idx]
        lockpoint_f = float(lockpoint)
        current_mhz = self._current_synth_frequency_mhz(synth_id, channel)
        if abs(lockpoint_f - current_mhz) > self.max_lockpoint_step_mhz:
            raise AssertionError(
                "Can't move frequency more than "
                f"{self.max_lockpoint_step_mhz:g} MHz without loss of lock; "
                f"setpoint={current_mhz:.3f} MHz, lockpoint={lockpoint_f:.3f} MHz"
            )

        target_hz = lockpoint_f * 1e6 if self.lockpoint_in_mhz else lockpoint_f
        self._device_call(
            synth_id,
            f"set_frequency_channel_{int(channel)}",
            {"freq_hz": target_hz},
        )

    def move_laser0_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(0, lockpoint)

    def move_laser1_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(1, lockpoint)

    def move_laser2_lockpoint(self, lockpoint: float) -> None:
        self.move_laser_lockpoint(2, lockpoint)
