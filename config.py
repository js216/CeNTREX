import configparser
import importlib
import logging
import traceback
from collections import deque

from utils import split


class Config(dict):
    def __init__(self):
        super().__init__()

    def __setitem__(self, key, val):
        # check the key is permitted
        if not key in dict(self.static_keys, **self.runtime_keys, **self.section_keys):
            logging.error("Error in Config: key " + key + " not permitted.")

        # set the value in the dict
        super().__setitem__(key, val)


class ProgramConfig(Config):
    def __init__(self, config_fname=None):
        super().__init__()
        self.fname = config_fname
        self.define_permitted_keys()
        self.set_defaults()
        self.read_from_file()

    def define_permitted_keys(self):
        # list of keys permitted for static options (those in the .ini file)
        self.static_keys = {}

        # list of keys permitted for runtime data (which cannot be written to .ini file)
        self.runtime_keys = {
            "time_offset": float,
            "control_active": bool,
            "control_visible": bool,
            "monitoring_visible": bool,
            "sequencer_visible": bool,
            "plots_visible": bool,
            "horizontal_split": bool,
        }

        # list of keys permitted as names of sections in the .ini file
        self.section_keys = {
            "general": dict,
            "run_attributes": dict,
            "files": dict,
            "influxdb": dict,
            "networking": dict,
        }

    def set_defaults(self):
        self["time_offset"] = 0
        self["control_active"] = False
        self["control_visible"] = True
        self["monitoring_visible"] = False
        self["sequencer_visible"] = False
        self["plots_visible"] = False
        self["horizontal_split"] = True

    def read_from_file(self):
        settings = configparser.ConfigParser()
        settings.read("config/settings.ini")
        for section, section_type in self.section_keys.items():
            self[section] = settings[section]

    def write_to_file(self):
        # collect new configuration parameters to be written
        config = configparser.ConfigParser()
        for sect in self.section_keys:
            config[sect] = self[sect]

        # write them to file
        with open("config/settings.ini", "w") as f:
            config.write(f)

    def change(self, sect, key, val, typ=str):
        try:
            self[sect][key] = typ(val)
        except (TypeError, ValueError) as err:
            logging.warning("PlotConfig error: Invalid parameter: " + str(err))
            logging.warning(traceback.format_exc())


class DeviceConfig(Config):
    def __init__(self, config_fname=None):
        super().__init__()
        self.fname = config_fname
        self.define_permitted_keys()
        self.set_defaults()
        self.read_from_file()

    def define_permitted_keys(self):
        # list of keys permitted for static options (those in the .ini file)
        self.static_keys = {
            "name": str,
            "label": str,
            "path": str,
            "driver": str,
            "constr_params": list,
            "correct_response": str,
            "slow_data": bool,
            "COM_port": str,
            "row": int,
            "column": int,
            "plots_queue_maxlen": int,
            "max_NaN_count": int,
            "meta_device": bool,
            "double_connect_dev": bool,
            "dtype": str,
            "shape": list,
            "plots_fn": str,
        }

        # list of keys permitted for runtime data (which cannot be written to .ini file)
        self.runtime_keys = {
            "parent": None,
            "driver_class": None,
            "shape": tuple,
            "dtype": type,
            "plots_queue": deque,
            "monitoring_GUI_elements": dict,
            "control_GUI_elements": dict,
            "time_offset": float,
            "control_active": bool,
        }

        # list of keys permitted as names of sections in the .ini file
        self.section_keys = {"attributes": dict, "control_params": dict}

    def set_defaults(self):
        self["control_params"] = {"InfluxDB_enabled": {"type": "dummy", "value": True}}
        self["double_connect_dev"] = True
        self["plots_fn"] = "2*y"

    def change_param(
        self,
        key,
        val,
        sect=None,
        sub_ctrl=None,
        row=None,
        nonTriState=False,
        GUI_element=None,
    ):
        if row != None:
            self[sect][key]["value"][sub_ctrl][row] = val
        elif GUI_element:
            self["control_GUI_elements"][GUI_element][key] = val
        elif sub_ctrl:
            self[sect][key]["value"][sub_ctrl] = val
        elif sect:
            self[sect][key]["value"] = val
        else:
            self[key] = val

    def read_from_file(self):
        # config file sanity check
        if not self.fname:
            return
        params = configparser.ConfigParser()
        params.read(self.fname)
        if not "device" in params:
            if self.fname[-11:] != "desktop.ini":
                logging.warning(
                    "The device config file "
                    + self.fname
                    + " does not have a [device] section."
                )
            return

        # read general device options
        for key, typ in self.static_keys.items():
            # read a parameter from the .ini file
            val = params["device"].get(key)

            # check the parameter is defined in the file; leave it at its default value if not
            if not val:
                continue

            # if the parameter is defined in the .init file, parse it into correct type:
            if typ == list:
                self[key] = [x.strip() for x in val.split(",")]
            elif typ == bool:
                self[key] = True if val.strip() in ["True", "1"] else False
            else:
                self[key] = typ(val)

        # for single-connect devices, make sure data type and shape are defined
        if not self["double_connect_dev"]:
            if not (self["shape"] and self["dtype"]):
                logging.warning(
                    "Single-connect device {0} didn't specify data shape or type.".format(
                        self.fname
                    )
                )
            else:
                self["shape"] = [float(val) for val in self["shape"]]

        # read device attributes
        self["attributes"] = params["attributes"]

        # import the device driver
        driver_spec = importlib.util.spec_from_file_location(
            params["device"]["driver"], "drivers/" + params["device"]["driver"] + ".py"
        )
        driver_module = importlib.util.module_from_spec(driver_spec)
        driver_spec.loader.exec_module(driver_module)
        self["driver_class"] = getattr(driver_module, params["device"]["driver"])

        # populate the list of device controls
        ctrls = self["control_params"]

        for c in params.sections():
            if params[c].get("type") == "QCheckBox":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "tooltip": params[c].get("tooltip"),
                    "tristate": True
                    if params[c].get("tristate") in ["1", "True"]
                    else False,
                }
                if ctrls[c]["tristate"]:
                    if params[c]["value"] == "1":
                        ctrls[c]["value"] = 1
                    elif params[c]["value"] in ["2", "True"]:
                        ctrls[c]["value"] = 2
                    else:
                        ctrls[c]["value"] = 0
                else:
                    ctrls[c]["value"] = (
                        True if params[c]["value"] in ["1", "True"] else False
                    )

            elif params[c].get("type") == "Hidden":
                ctrls[c] = {"value": params[c]["value"], "type": "Hidden"}

            elif params[c].get("type") == "QPushButton":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "cmd": params[c].get("command"),
                    "argument": params[c]["argument"],
                    "align": params[c].get("align"),
                    "tooltip": params[c].get("tooltip"),
                }

            elif params[c].get("type") == "QLineEdit":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "enter_cmd": params[c].get("enter_cmd"),
                    "value": params[c]["value"],
                    "tooltip": params[c].get("tooltip"),
                }

            elif params[c].get("type") == "QComboBox":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "command": params[c]["command"],
                    "options": split(params[c]["options"]),
                    "value": params[c]["value"],
                }

            elif params[c].get("type") == "ControlsRow":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "ctrl_names": split(params[c]["ctrl_names"]),
                    "ctrl_labels": dict(
                        zip(
                            split(params[c]["ctrl_names"]),
                            split(params[c]["ctrl_labels"]),
                        )
                    ),
                    "ctrl_types": dict(
                        zip(
                            split(params[c]["ctrl_names"]),
                            split(params[c]["ctrl_types"]),
                        )
                    ),
                    "ctrl_options": dict(
                        zip(
                            split(params[c]["ctrl_names"]),
                            [split(x) for x in params[c]["ctrl_options"].split(";")],
                        )
                    ),
                    "value": dict(
                        zip(
                            split(params[c]["ctrl_names"]),
                            split(params[c]["ctrl_values"]),
                        )
                    ),
                }

            elif params[c].get("type") == "ControlsTable":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "rowspan": int(params[c].get("rowspan")),
                    "colspan": int(params[c].get("colspan")),
                    "row_ids": [int(r) for r in split(params[c]["row_ids"])],
                    "col_names": split(params[c]["col_names"]),
                    "col_labels": dict(
                        zip(
                            split(params[c]["col_names"]),
                            split(params[c]["col_labels"]),
                        )
                    ),
                    "col_types": dict(
                        zip(
                            split(params[c]["col_names"]), split(params[c]["col_types"])
                        )
                    ),
                    "col_options": dict(
                        zip(
                            split(params[c]["col_names"]),
                            [split(x) for x in params[c]["col_options"].split(";")],
                        )
                    ),
                    "value": dict(
                        zip(
                            split(params[c]["col_names"]),
                            [split(x) for x in params[c]["col_values"].split(";")],
                        )
                    ),
                }

            elif params[c].get("type") == "indicator":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "rowspan": int(params[c].get("rowspan")),
                    "colspan": int(params[c].get("colspan")),
                    "monitoring_command": params[c]["monitoring_command"],
                    "return_values": split(params[c]["return_values"]),
                    "texts": split(params[c]["texts"]),
                    "states": split(params[c]["states"]),
                }

            elif params[c].get("type") == "indicator_button":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "rowspan": int(params[c]["rowspan"]),
                    "colspan": int(params[c]["colspan"]),
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "argument": params[c]["argument"],
                    "align": params[c].get("align"),
                    "tooltip": params[c].get("tooltip"),
                    "monitoring_command": params[c]["monitoring_command"],
                    "action_commands": split(params[c]["action_commands"]),
                    "return_values": split(params[c]["return_values"]),
                    "checked": [
                        True if x in ["1", "True"] else False
                        for x in split(params[c]["checked"])
                    ],
                    "states": split(params[c]["states"]),
                    "texts": split(params[c]["texts"]),
                }

            elif params[c].get("type") == "indicator_lineedit":
                ctrls[c] = {
                    "label": params[c]["label"],
                    "type": params[c]["type"],
                    "row": int(params[c]["row"]),
                    "col": int(params[c]["col"]),
                    "enter_cmd": params[c].get("enter_cmd"),
                    "value": params[c]["value"],
                    "tooltip": params[c].get("tooltip"),
                    "monitoring_command": params[c]["monitoring_command"],
                }

            elif params[c].get("type") == "dummy":
                ctrls[c] = {"type": params[c]["type"], "value": params[c]["value"]}

            elif params[c].get("type"):
                logging.warning("Control type not supported: " + params[c].get("type"))

        self["control_params"] = ctrls

    def write_to_file(self):
        # collect the configuration parameters to be written
        config = configparser.ConfigParser()
        config["device"] = {}
        for key, typ in self.static_keys.items():
            if typ == list:
                config["device"][key] = ", ".join(self.get(key))
            else:
                config["device"][key] = str(self.get(key))
        config["attributes"] = self["attributes"]

        # collect device control parameters
        for c_name, c in self["control_params"].items():
            config[c_name] = {
                "label": str(c.get("label")),
                "type": str(c["type"]),
                "row": str(c.get("row")),
                "col": str(c.get("col")),
                "tooltip": str(c.get("tooltip")),
                "rowspan": str(c.get("rowspan")),
                "colspan": str(c.get("colspan")),
            }
            if c["type"] in ["QComboBox", "QCheckBox", "QLineEdit"]:
                config[c_name]["value"] = str(c["value"])
            if c["type"] == "QLineEdit":
                config[c_name]["enter_cmd"] = str(c["enter_cmd"])
            if c["type"] == "QComboBox":
                config[c_name]["options"] = ", ".join(c["options"])
                config[c_name]["command"] = str(c.get("command"))
            if c["type"] == "QPushButton":
                config[c_name]["command"] = str(c.get("cmd"))
                config[c_name]["argument"] = str(c.get("argument"))
                config[c_name]["align"] = str(c.get("align"))
            if c["type"] == "ControlsRow":
                config[c_name]["ctrl_values"] = ", ".join(
                    [x for x_name, x in c["value"].items()]
                )
                config[c_name]["ctrl_names"] = ", ".join(c["ctrl_names"])
                config[c_name]["ctrl_labels"] = ", ".join(
                    [x for x_name, x in c["ctrl_labels"].items()]
                )
                config[c_name]["ctrl_types"] = ", ".join(
                    [x for x_name, x in c["ctrl_types"].items()]
                )
                config[c_name]["ctrl_options"] = "; ".join(
                    [", ".join(x) for x_name, x in c["ctrl_options"].items()]
                )
            if c["type"] == "ControlsTable":
                config[c_name]["col_values"] = "; ".join(
                    [", ".join(x) for x_name, x in c["value"].items()]
                )
                config[c_name]["row_ids"] = ", ".join(c["row_ids"])
                config[c_name]["col_names"] = ", ".join(c["col_names"])
                config[c_name]["col_labels"] = ", ".join(
                    [x for x_name, x in c["col_labels"].items()]
                )
                config[c_name]["col_types"] = ", ".join(
                    [x for x_name, x in c["col_types"].items()]
                )
                config[c_name]["col_options"] = "; ".join(
                    [", ".join(x) for x_name, x in c["col_options"].items()]
                )
            if c["type"] == "indicator":
                config[c_name]["monitoring_command"] = str(c.get("monitoring_command"))
                config[c_name]["return_values"] = ", ".join(c["return_values"])
                config[c_name]["texts"] = ", ".join(c["texts"])
                config[c_name]["states"] = ", ".join(c["states"])
            if c["type"] == "indicator_button":
                config[c_name]["monitoring_command"] = str(c.get("monitoring_command"))
                config[c_name]["action_commands"] = ", ".join(c["action_commands"])
                config[c_name]["return_values"] = ", ".join(c["return_values"])
                config[c_name]["checked"] = ", ".join([str(s) for s in c["checked"]])
                config[c_name]["states"] = ", ".join(c["states"])
                config[c_name]["texts"] = ", ".join(c["texts"])
                config[c_name]["argument"] = str(c.get("argument"))
                config[c_name]["align"] = str(c.get("align"))
            if c["type"] == "indicator_lineedit":
                config[c_name]["enter_cmd"] = str(c["enter_cmd"])

        # write them to file
        with open(self.fname, "w") as f:
            config.write(f)


class PlotConfig(Config):
    def __init__(self, config=None):
        super().__init__()
        self.define_permitted_keys()
        self.set_defaults()
        if config:
            for key, val in config.items():
                self[key] = val

    def define_permitted_keys(self):
        # list of keys permitted for static options (those that can be written to file)
        self.static_keys = {
            "row": int,
            "col": int,
            "fn": bool,
            "log": bool,
            "symbol": str,
            "from_HDF": bool,
            "controls": bool,
            "n_average": int,
            "device": str,
            "f(y)": str,
            "run": str,
            "x": str,
            "y": str,
            "z": str,
            "x0": str,
            "x1": str,
            "y0": str,
            "y1": str,
            "dt": float,
        }

        # list of keys permitted for runtime data (which cannot be written to a file)
        self.runtime_keys = {
            "active": bool,
            "plot_drawn": bool,
            "animation_running": bool,
        }

        # list of keys permitted as names of sections in the .ini file
        self.section_keys = {}

    def set_defaults(self):
        self["active"] = False
        self["fn"] = False
        self["log"] = False
        self["symbol"] = None
        self["plot_drawn"] = False
        self["animation_running"] = False
        self["from_HDF"] = False
        self["controls"] = True
        self["n_average"] = 1
        self["f(y)"] = "np.min(y)"
        self["device"] = "Select device ..."
        self["run"] = "Select run ..."
        self["x"] = "Select x ..."
        self["y"] = "Select y ..."
        self["z"] = "divide by?"
        self["x0"] = "x0"
        self["x1"] = "x1"
        self["y0"] = "y0"
        self["y1"] = "y1"
        self["dt"] = 0.25

    def change(self, key, val, typ=str):
        try:
            self[key] = typ(val)
        except (TypeError, ValueError) as err:
            logging.warning("PlotConfig error: Invalid parameter: " + str(err))
            logging.warning(traceback.format_exc())

    def get_static_params(self):
        return {key: self[key] for key in self.static_keys}
