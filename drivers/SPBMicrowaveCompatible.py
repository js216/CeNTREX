from __future__ import annotations

import json
import math
import threading
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


class SPBMicrowaveCompatible:
    """
    Legacy-compatible SPB microwave client that talks to experiment-control.
    Configured for state-preparation network defaults at 10.10.222.25.

    Commands:
      FastAPI (8001) -> /api/processes/{process_id}/call
    """

    STATE_CODES = {
        "ERROR": -1.0,
        "SAFE_OFF": 0.0,
        "RF_ON": 1.0,
        "POWER_LOCKED": 2.0,
        "CIRCULAR_LOCKED": 3.0,
        "CALIBRATING": 4.0,
    }
    LIVE_RETUNE_STATES = {"RF_ON", "POWER_LOCKED", "CIRCULAR_LOCKED"}

    def __init__(
        self,
        time_offset: float,
        address: str = "10.10.222.25",
        port_api: int = 8001,
        manager_pub_endpoint: str | None = None,
        process_id: str = "spb_microwave",
        rpc_namespace: str = "mw",
        dt_max: float = 5.0,
        request_timeout_s: float = 2.0,
    ) -> None:
        self.time_offset = float(time_offset)
        self.address = str(address).strip('"')
        self.port_api = int(port_api)
        self.manager_pub_endpoint = (
            str(manager_pub_endpoint)
            if manager_pub_endpoint
            else f"tcp://{self.address}:7001"
        )
        self.process_id = str(process_id)
        self.rpc_namespace = str(rpc_namespace).strip(".")
        self.dt_max = float(dt_max)
        self.request_timeout_s = float(request_timeout_s)

        self.verification_string = "SPB_MICROWAVE_EXPERIMENT_CONTROL"
        self.new_attributes, self.dtype, self.shape = self.generate_new_attributes()
        self.warnings: list[list[Any]] = []
        self._cache_lock = threading.Lock()

    @staticmethod
    def generate_new_attributes() -> tuple[list[tuple[str, str]], str, tuple[int]]:
        column_names = [
            "time",
            "state_code",
            "target_frequency",
            "target_detected_power",
            "ch1_enabled",
            "ch1_frequency",
            "ch1_power",
            "ch2_enabled",
            "ch2_frequency",
            "ch2_power",
            "pid_enabled",
            "phase_trim_enabled",
        ]
        units = ["s", "", "GHz", "dBm", "", "GHz", "dBm", "", "GHz", "dBm", "", ""]
        new_attributes = [
            ("column_names", ",".join(column_names)),
            ("units", ",".join(units)),
        ]
        return new_attributes, "f", (len(column_names),)

    def __enter__(self) -> SPBMicrowaveCompatible:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        return None

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

    def _action_name(self, action: str) -> str:
        action_s = str(action)
        if "." in action_s:
            return action_s
        return f"{self.rpc_namespace}.{action_s}"

    def _process_call(
        self, action: str, params: dict[str, Any] | None = None
    ) -> Any:
        if params is None:
            params = {}
        body = json.dumps({"action": self._action_name(action), "params": params}).encode(
            "utf-8"
        )
        encoded_id = quote(self.process_id, safe="")
        url = f"http://{self.address}:{self.port_api}/api/processes/{encoded_id}/call"
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

    def status_detail(self) -> dict[str, Any]:
        result = self._process_call("status_detail", {})
        if not isinstance(result, dict):
            raise RuntimeError("invalid status_detail result")
        return result

    def _status_payload(self) -> dict[str, Any]:
        status = self.status_detail()
        detail = status.get("status_detail")
        if isinstance(detail, dict):
            merged = dict(detail)
            if "state" not in merged:
                merged["state"] = status.get("state")
            return merged
        return status

    def _current_state(self) -> str:
        status = self._status_payload()
        state = status.get("state")
        if not isinstance(state, str) or not state:
            raise RuntimeError("missing process state")
        return state

    def _wait_for_state(
        self,
        target_state: str,
        *,
        timeout_s: float = 30.0,
        poll_s: float = 0.2,
    ) -> str:
        deadline = time.monotonic() + float(timeout_s)
        target = str(target_state)
        while True:
            state = self._current_state()
            if state == target:
                return state
            if state == "ERROR":
                raise RuntimeError(f"process entered ERROR while waiting for {target}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for {target}; current state is {state}")
            time.sleep(float(poll_s))

    def _state_code(self, state: Any) -> float:
        if isinstance(state, str):
            return self.STATE_CODES.get(state, math.nan)
        return math.nan

    def _to_float(self, value: Any, *, field: str) -> float:
        if value is None:
            return math.nan
        try:
            return float(value)
        except Exception as exc:
            raise TypeError(f"{field} is not numeric: {value!r}") from exc

    def _to_bool_float(self, value: Any, *, field: str) -> float:
        if value is None:
            return math.nan
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return 1.0 if bool(value) else 0.0
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "on", "yes"}:
                return 1.0
            if text in {"false", "0", "off", "no"}:
                return 0.0
        raise TypeError(f"{field} is not boolean-like: {value!r}")

    def _freq_hz_to_ghz(self, value: Any, *, field: str) -> float:
        if value is None:
            return math.nan
        return self._to_float(value, field=field) / 1e9

    def ReadValue(self) -> list[float] | None:
        try:
            status = self._status_payload()
            target = status.get("target", {})
            readback = status.get("readback", {})
            synthhd = readback.get("synthhd", {}) if isinstance(readback, dict) else {}
            ch1 = synthhd.get("ch1", {}) if isinstance(synthhd, dict) else {}
            ch2 = synthhd.get("ch2", {}) if isinstance(synthhd, dict) else {}
            pid = status.get("pid", {})
            phase_trim = status.get("phase_trim", {})
            if not isinstance(target, dict):
                target = {}
            if not isinstance(ch1, dict):
                ch1 = {}
            if not isinstance(ch2, dict):
                ch2 = {}
            if not isinstance(pid, dict):
                pid = {}
            if not isinstance(phase_trim, dict):
                phase_trim = {}
            return [
                time.time() - self.time_offset,
                self._state_code(status.get("state")),
                self._to_float(target.get("frequency_ghz"), field="target.frequency_ghz"),
                self._to_float(
                    target.get("detected_power_dbm"),
                    field="target.detected_power_dbm",
                ),
                self._to_bool_float(ch1.get("enabled"), field="ch1.enabled"),
                self._freq_hz_to_ghz(ch1.get("frequency_hz"), field="ch1.frequency_hz"),
                self._to_float(ch1.get("power_dbm"), field="ch1.power_dbm"),
                self._to_bool_float(ch2.get("enabled"), field="ch2.enabled"),
                self._freq_hz_to_ghz(ch2.get("frequency_hz"), field="ch2.frequency_hz"),
                self._to_float(ch2.get("power_dbm"), field="ch2.power_dbm"),
                self._to_bool_float(pid.get("enabled"), field="pid.enabled"),
                self._to_bool_float(
                    phase_trim.get("enabled"),
                    field="phase_trim.enabled",
                ),
            ]
        except Exception as exc:
            self._warn(f"ReadValue failed: {exc}")
            return None

    def _command_result_text(self, result: Any) -> str:
        if isinstance(result, dict):
            if "accepted" in result:
                return "accepted" if bool(result.get("accepted")) else "not accepted"
            return json.dumps(result, sort_keys=True)
        if result is None:
            return "None"
        return str(result)

    def set_target(
        self,
        frequency_ghz: float | None = None,
        power_dbm: float | None = None,
    ) -> str:
        params: dict[str, Any] = {}
        if frequency_ghz is not None:
            params["frequency_ghz"] = float(frequency_ghz)
        if power_dbm is not None:
            params["power_dbm"] = float(power_dbm)
        if not params:
            raise ValueError("set_target requires frequency_ghz and/or power_dbm")
        return self._command_result_text(self._process_call("set_target", params))

    def retune(
        self,
        frequency_ghz: float | None = None,
        power_dbm: float | None = None,
    ) -> str:
        params: dict[str, Any] = {}
        if frequency_ghz is not None:
            params["frequency_ghz"] = float(frequency_ghz)
        if power_dbm is not None:
            params["power_dbm"] = float(power_dbm)
        if not params:
            raise ValueError("retune requires frequency_ghz and/or power_dbm")
        return self._command_result_text(self._process_call("retune", params))

    def set_power(self, power_dbm: float) -> str:
        return self.set_target(power_dbm=float(power_dbm))

    def set_frequency(self, frequency_ghz: float) -> str:
        state = self._current_state()
        if state == "SAFE_OFF":
            return self.set_target(frequency_ghz=float(frequency_ghz))
        if state in self.LIVE_RETUNE_STATES:
            return self.retune(frequency_ghz=float(frequency_ghz))
        return self.retune(frequency_ghz=float(frequency_ghz))

    def enable_rf(self) -> str:
        return self._command_result_text(self._process_call("enable_rf", {}))

    def disable_rf(self) -> str:
        return self._command_result_text(self._process_call("disable_rf", {}))

    def enable_microwaves(self) -> str:
        return self.enable_rf()

    def disable_microwaves(self) -> str:
        return self.disable_rf()

    def turn_on(self) -> str:
        return self.enable_rf()

    def turn_off(self) -> str:
        return self.disable_rf()

    def enable_power_and_phase_loop(
        self,
        gradient_sign: str = "positive",
        *,
        timeout_s: float = 30.0,
        poll_s: float = 0.2,
    ) -> str:
        state = self._current_state()
        if state == "ERROR":
            raise RuntimeError("clear_error before enabling SPB microwave locks")
        if state == "SAFE_OFF":
            self.enable_rf()
            state = self._wait_for_state("RF_ON", timeout_s=timeout_s, poll_s=poll_s)
        if state == "RF_ON":
            self._process_call("enter_power_locked", {})
            state = self._wait_for_state(
                "POWER_LOCKED",
                timeout_s=timeout_s,
                poll_s=poll_s,
            )
        if state == "POWER_LOCKED":
            self._process_call(
                "enter_circular_locked",
                {"gradient_sign": str(gradient_sign)},
            )
            state = self._wait_for_state(
                "CIRCULAR_LOCKED",
                timeout_s=timeout_s,
                poll_s=poll_s,
            )
        if state != "CIRCULAR_LOCKED":
            raise RuntimeError(f"cannot enable power and phase loop from state {state}")
        return "accepted"

    def enable_microwaves_locked(
        self,
        gradient_sign: str = "positive",
        *,
        timeout_s: float = 30.0,
        poll_s: float = 0.2,
    ) -> str:
        return self.enable_power_and_phase_loop(
            gradient_sign,
            timeout_s=timeout_s,
            poll_s=poll_s,
        )

    def turn_on_locked(
        self,
        gradient_sign: str = "positive",
        *,
        timeout_s: float = 30.0,
        poll_s: float = 0.2,
    ) -> str:
        return self.enable_power_and_phase_loop(
            gradient_sign,
            timeout_s=timeout_s,
            poll_s=poll_s,
        )
