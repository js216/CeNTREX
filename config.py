import datetime
import importlib
import logging
from collections import deque
from dataclasses import dataclass, field, fields
from enum import Enum, auto
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from PySide6 import QtWidgets

__filepath__ = Path(__file__).parent


class RuntimeKeys(BaseModel):
    time_offset: float = 0
    control_active: bool = False
    control_visible: bool = True
    monitoring_visible: bool = False
    sequencer_visible: bool = False
    plots_visible: bool = False
    horizontal_split: bool = True


class GeneralConfig(BaseModel):
    run_name: str = "test"
    plot_dt: float = 0.1
    hdf_loop_delay: float = 0.5
    hdf_flush_dt: float = 10.0
    monitoring_dt: float = 5.0
    debug_level: str = "WARNING"


class FilesConfig(BaseModel):
    config_dir: Path
    hdf_dir: Path
    plotting_config_fname: Path
    sequence_fname: Path
    hdf_fname: str = field(
        default_factory=lambda: datetime.datetime.strftime(
            datetime.datetime.now(), "%Y_%m_%d"
        )
        + ".hdf"
    )


class InfluxDBConfig(BaseModel):
    host: str
    port: int
    org: str
    token: str
    bucket: str
    enabled: bool = False


class NetworkingConfig(BaseModel):
    name: str
    port_readout: int
    port_control: int
    allowed: list[str]
    workers: int
    enabled: bool = False


class ProgramConfig(BaseModel):
    fname: Path  # config filename
    general: GeneralConfig
    networking: NetworkingConfig
    files: FilesConfig
    influxdb: InfluxDBConfig
    time_offset: float = 0
    control_active: bool = False
    control_visible: bool = True
    monitoring_visible: bool = False
    sequencer_visible: bool = False
    plots_visible: bool = False
    horizontal_split: bool = True
    run_attributes: dict[str, Any] = field(default_factory=lambda: {})

    def change(
        self, section: str, config: str, value: int | float | bool | str
    ) -> None:
        if section != "":
            setattr(
                getattr(self, section),
                config,
                type(getattr(getattr(self, section), config))(value),
            )
        else:
            setattr(self, config, value)


def load_program_config(fname: Path) -> ProgramConfig:
    with open(fname, "r") as f:
        settings = yaml.load(f, Loader=yaml.SafeLoader)

    general = GeneralConfig(
        **dict([(key, value) for key, value in settings["general"].items()])
    )

    networking = NetworkingConfig(
        **dict([(key, value) for key, value in settings["networking"].items()])
    )
    files = FilesConfig(
        **dict([(key, value) for key, value in settings["files"].items()])
    )
    influxdb = InfluxDBConfig(
        **dict([(key, value) for key, value in settings["influxdb"].items()])
    )

    return ProgramConfig(
        fname=fname,
        general=general,
        networking=networking,
        files=files,
        influxdb=influxdb,
    )


@dataclass
class Attributes:
    column_names: list[str]
    units: list[str]


class ControlParamTypes(Enum):
    QCHECKBOX = auto()
    QLINEEDIT = auto()
    QPUSHBUTTON = auto()
    QCOMBOBOX = auto()
    CONTROLSROW = auto()
    CONTROLSTABLE = auto()
    INDICATOR = auto()
    INDICATORBUTTON = auto()
    INDICATORLINEEDIT = auto()
    DUMMY = auto()


@dataclass(kw_only=True)
class ControlParam:
    type: ControlParamTypes
    tooltip: str | None = None
    label: str | None = None

    def change(self, param: str, value: int | float | bool | str) -> None:
        data_fields = fields(self)
        field_names = [f.name for f in data_fields]
        idx = field_names.index(param)
        value_type = type(getattr(self, field_names[idx]))
        setattr(self, param, value_type(value))


@dataclass(kw_only=True)
class QCheckBoxParam(ControlParam):
    row: int
    column: int
    value: int
    tristate: bool = False
    type: ControlParamTypes = ControlParamTypes.QCHECKBOX


@dataclass(kw_only=True)
class DummyParam(ControlParam):
    value: int | float | bool | str
    type: ControlParamTypes = ControlParamTypes.DUMMY


@dataclass(kw_only=True)
class QLineEditParam(ControlParam):
    row: int
    column: int
    value: float | int | bool | str
    command: str | None = None
    type: ControlParamTypes = ControlParamTypes.QLINEEDIT


@dataclass(kw_only=True)
class QPushButtonParam(ControlParam):
    row: int
    column: int
    command: str
    argument: str | None = None
    align: str | None = None
    type: ControlParamTypes = ControlParamTypes.QPUSHBUTTON


@dataclass(kw_only=True)
class QComboBoxParam(ControlParam):
    row: int
    column: int
    command: str
    options: list[str]
    value: int | float | bool | str
    type: ControlParamTypes = ControlParamTypes.QCOMBOBOX


@dataclass(kw_only=True)
class ControlsRowParam(ControlParam):
    row: int
    column: int
    ctrl_names: list[str]
    ctrl_labels: dict[str, str]
    ctrl_types: dict[str, type]
    ctrl_options: dict[str, list[int | float | bool | str]]
    value: dict[str, int | float | bool | str]
    type: ControlParamTypes = ControlParamTypes.CONTROLSROW


@dataclass(kw_only=True)
class ControlsTableParam(ControlParam):
    row: int
    column: int
    rowspan: int
    colspan: int
    row_ids: list[int]
    col_names: list[str]
    col_labels: dict[str, str]
    col_types: dict[str, type]
    col_options: dict[str, list[int | float | bool | str]]
    value: dict[str, list[int | float | bool | str]]
    type: ControlParamTypes = ControlParamTypes.CONTROLSTABLE


@dataclass(kw_only=True)
class IndicatorParam(ControlParam):
    row: int
    column: int
    rowspan: int
    colspan: int
    monitoring_command: str
    return_values: list[int | float | bool | str]
    texts: list[str]
    states: list[str]
    type: ControlParamTypes = ControlParamTypes.INDICATOR


@dataclass(kw_only=True)
class IndicatorButtonParam(IndicatorParam):
    action_commands: list[str]
    argument: str
    checked: list[str]
    type: ControlParamTypes = ControlParamTypes.INDICATORBUTTON


@dataclass(kw_only=True)
class IndicatorLineEditParam(ControlParam):
    row: int
    column: int
    command: str
    value: int | float | bool | str
    monitoring_command: str


control_params_types_mapping: dict[ControlParamTypes, ControlParam] = {
    ControlParamTypes.QCHECKBOX: QCheckBoxParam,
    ControlParamTypes.QLINEEDIT: QLineEditParam,
    ControlParamTypes.QPUSHBUTTON: QPushButtonParam,
    ControlParamTypes.QCOMBOBOX: QComboBoxParam,
    ControlParamTypes.CONTROLSROW: ControlsRowParam,
    ControlParamTypes.CONTROLSTABLE: ControlsTableParam,
    ControlParamTypes.INDICATOR: IndicatorParam,
    ControlParamTypes.INDICATORBUTTON: IndicatorButtonParam,
    ControlParamTypes.INDICATORLINEEDIT: IndicatorLineEditParam,
    ControlParamTypes.DUMMY: DummyParam,
}

control_params_default = {
    "enabled": QCheckBoxParam(
        label="Device enabled", tristate=True, row=0, column=0, value=2
    ),
    "influxdb_enabled": DummyParam(value=True),
    "hdf_enabled": DummyParam(value=True),
    "dt": QLineEditParam(label="Loop delay [s]", row=1, column=1, value=1),
}


@dataclass
class DeviceConfig:
    fname: Path
    name: str
    label: str
    path: str
    driver: str
    constr_params: list
    correct_response: str
    driver_class: object
    dataclass: object
    attributes: Attributes
    shape: tuple
    dtype: type | tuple[type, ...]
    slow_data: bool = True
    max_nan_count: int = 10
    meta_device: bool = False
    plots_queue_maxlen: int = 1_000
    plots_queue: deque = field(default_factory=lambda: deque(maxlen=1_000))
    parent: object | None = None
    row: int = 0
    column: int = 0
    time_offset: float = 0
    control_active: bool = False
    control_params: dict[
        str,
        DummyParam
        | QLineEditParam
        | QCheckBoxParam
        | QPushButtonParam
        | ControlsRowParam
        | ControlsTableParam
        | IndicatorParam
        | IndicatorLineEditParam
        | IndicatorButtonParam,
    ] = field(default_factory=lambda: control_params_default)
    control_gui_elements: dict[str, dict[str, QtWidgets.QWidget]] = field(
        default_factory=lambda: {}
    )

    monitoring_gui_elements: dict[str, QtWidgets.QWidget] = field(
        default_factory=lambda: {}
    )
    plots_fn: str = "2*y"

    def change_param(self, param: str, value: int | float | bool | str) -> None:
        data_fields = fields(DeviceConfig)
        field_names = [f.name for f in data_fields]
        idx = field_names.index(param)
        setattr(self, param, data_fields[idx].type(value))

    def change_param_subsection(
        self, param: str, section: str, value: int | float | bool | str
    ) -> None:
        if section == "control_params":
            self.control_params[param].change("value", value)
        else:
            getattr(self, section).change(param, value)


def convert_to_type(to_convert: dict[str, str], dclass: type) -> dict[str, Any]:
    allowed_types = [int, float, bool, str, Path]
    for data_field in fields(dclass):
        if data_field.type in allowed_types:
            if to_convert.get(data_field.name) is not None:
                try:
                    to_convert[data_field.name] = data_field.type(
                        to_convert[data_field.name]
                    )
                except Exception as e:
                    logging.error(
                        data_field.name, data_field.type, to_convert[data_field.name], e
                    )
    return to_convert


def get_shape_from_dataclass(data: object) -> tuple[int]:
    return (
        len(
            [
                f
                for f in fields(data)
                if f.name not in ["dtype", "shape", "units", "column_names"]
            ]
        ),
    )


def get_dtype_from_dataclass(data: object) -> tuple[type, ...]:
    return tuple(
        [
            f.type
            for f in fields(data)
            if f.name not in ["dtype", "shape", "units", "column_names"]
        ]
    )


def load_device_config(fname: Path) -> DeviceConfig:
    with open(fname, "r") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    dev = dict([(key, val) for key, val in config["device"].items()])

    dev["fname"] = fname
    # import the device driver
    driver_spec = importlib.util.spec_from_file_location(
        dev["driver"],
        __filepath__ / "drivers" / (dev["driver"] + ".py"),
    )
    driver_module = importlib.util.module_from_spec(driver_spec)
    driver_spec.loader.exec_module(driver_module)
    dev["driver_class"] = getattr(driver_module, dev["driver"])
    dev["dataclass"] = getattr(driver_module, f"{dev['driver']}Data")

    dev["shape"] = get_shape_from_dataclass(dev["dataclass"])
    dev["dtype"] = get_dtype_from_dataclass(dev["dataclass"])

    attrs = Attributes(
        **dict([(key, val) for key, val in config["attributes"].items()])
    )

    controls = [key for key in config.keys() if key not in ["device", "attributes"]]

    control_params: dict[str, ControlParam] = {}
    for control in controls:
        param_config = dict(config[control].items())
        param_config["type"] = ControlParamTypes[param_config["type"].upper()]
        control_params[control] = control_params_types_mapping[param_config["type"]](
            **param_config
        )

    # check if defaults are present
    for key, val in control_params_default.items():
        if key not in control_params:
            control_params[key] = val

    dev = convert_to_type(dev, DeviceConfig)
    cfg = dev

    cfg.update({"attributes": attrs})
    cfg.update({"control_params": control_params})

    return DeviceConfig(**cfg)


@dataclass
class PlotConfig:
    row: int = 0
    col: int = 0
    symbol: str | None = None
    device: str = "Select device ..."
    fy: str = "np.min(y)"
    x: str = "Select x ..."
    y: str = "Select y ..."
    z: str = "divide by?"
    x0: str = "x0"
    x1: str = "x1"
    y0: str = "y0"
    y1: str = "y1"
    dt: float = 1.0
    active: bool = False
    fn: bool = False
    log: bool = False
    hist: bool = False
    plot_drawn: bool = False
    animation_running: bool = False
    controls: bool = True
    from_hdf: bool = False
    n_average: int = 1
    n_average: int = 1
    n_average: int = 1
    n_average: int = 1
    n_average: int = 1

    def change(self, param: str, value: int | float | bool | str) -> None:
        data_fields = fields(PlotConfig)
        field_names = [f.name for f in data_fields]
        idx = field_names.index(param)
        setattr(self, param, data_fields[idx].type(value))
