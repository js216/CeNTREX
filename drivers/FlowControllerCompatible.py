from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import zmq


class FlowControllerCompatible:
    def __init__(
        self,
        time_offset: float,
        address: str = "10.10.222.12",
        port_api: int = 8001,
        manager_pub_endpoint: str | None = None,
        device_id: str = "usb6008",
        dt_max: float = 5.0,
        request_timeout_s: float = 2.0,
        flow_signal: str = "flow_signal_sccm",
        setpoint_signal: str = "setpoint_sccm",
        flowing_threshold_sccm: float = 0.05,
    ) -> None:
        self.time_offset = float(time_offset)
        self.address = str(address).strip('"')
        self.port_api = int(port_api)
        self.manager_pub_endpoint = (
            str(manager_pub_endpoint)
            if manager_pub_endpoint
            else f"tcp://{self.address}:7001"
        )
        self.device_id = str(device_id)
        self.dt_max = float(dt_max)
        self.request_timeout_s = float(request_timeout_s)
        self.flow_signal = str(flow_signal)
        self.setpoint_signal = str(setpoint_signal)
        self.flowing_threshold_sccm = float(flowing_threshold_sccm)

        self.verification_string = "operational"
        self.new_attributes, self.dtype, self.shape = self.generate_new_attributes()
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
            target=self._telemetry_loop, name="flow-controller-telemetry", daemon=True
        )
        self._telemetry_thread.start()

    @staticmethod
    def generate_new_attributes() -> tuple[list[tuple[str, str]], str, tuple[int]]:
        column_names = ["time", "flow signal", "setpoint value"]
        units = ["s", "sccm", "sccm"]
        new_attributes = [
            ("column_names", ",".join(column_names)),
            ("units", ",".join(units)),
        ]
        return new_attributes, "f", (len(column_names),)

    def __enter__(self) -> FlowControllerCompatible:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if hasattr(self, "_telemetry_thread") and self._telemetry_thread.is_alive():
            self._telemetry_thread.join(timeout=2.0)

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
        self, action: str, params: dict[str, Any] | None = None
    ) -> Any:
        if params is None:
            params = {}
        body = json.dumps({"action": action, "params": params}).encode("utf-8")
        encoded_id = quote(self.device_id, safe="")
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

    def _latest_value(self, signal: str) -> tuple[Any, float]:
        with self._cache_lock:
            dev_cache = self._telemetry_cache.get(self.device_id, {})
            sample = dev_cache.get(signal)
        if sample is None:
            raise KeyError(f"missing telemetry {self.device_id}.{signal}")
        t_wall = sample.get("t_wall")
        if not isinstance(t_wall, (int, float)):
            t_wall = sample.get("recv_wall")
        if not isinstance(t_wall, (int, float)):
            t_wall = time.time()
        age_s = time.time() - float(t_wall)
        if age_s > self.dt_max:
            raise AssertionError(
                f"remote data more than {self.dt_max} seconds out of date "
                f"for {self.device_id}.{signal} (age={age_s:.3f}s)"
            )
        return sample.get("value"), float(age_s)

    def _to_float(self, value: Any, *, field: str) -> float:
        try:
            return float(value)
        except Exception as exc:
            raise TypeError(f"{field} is not numeric: {value!r}") from exc

    def VerifyOperation(self) -> str:
        try:
            self._device_call("read_setpoint_sccm", {})
        except Exception as exc:
            self._warn(f"VerifyOperation failed: {exc}")
            return "invalid"
        return self.verification_string

    def ReadValue(self) -> list[float] | None:
        try:
            flow_signal, _ = self._latest_value(self.flow_signal)
            setpoint, _ = self._latest_value(self.setpoint_signal)
            return [
                time.time() - self.time_offset,
                self._to_float(flow_signal, field=self.flow_signal),
                self._to_float(setpoint, field=self.setpoint_signal),
            ]
        except Exception as exc:
            self._warn(f"ReadValue failed: {exc}")
            return None

    def SetPointControl(self, value: float) -> None:
        self._device_call("set_setpoint_sccm", {"value": float(value)})

    def NeonStatus(self) -> str:
        try:
            flow_signal, _ = self._latest_value(self.flow_signal)
            setpoint, _ = self._latest_value(self.setpoint_signal)
            flow_f = self._to_float(flow_signal, field=self.flow_signal)
            setpoint_f = self._to_float(setpoint, field=self.setpoint_signal)
        except Exception as exc:
            self._warn(f"NeonStatus failed: {exc}")
            return "invalid"
        if max(abs(flow_f), abs(setpoint_f)) > self.flowing_threshold_sccm:
            return "flowing"
        return "not flowing"
