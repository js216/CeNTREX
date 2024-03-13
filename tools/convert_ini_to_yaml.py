from configparser import ConfigParser
from pathlib import Path

import yaml

p = Path() / "config"
p = [pi for pi in p.iterdir() if p.is_dir]

for pi in p:
    for fname in pi.glob("*.ini"):
        config = ConfigParser()
        config.read(fname)
        print(fname)
        config_dict = {s: dict(config.items(s)) for s in config.sections()}
        for section_key, section in config.items():
            for k, v in list(section.items()):
                if k in ["double_connect_dev"]:
                    del config_dict[section_key][k]
                    continue
                elif k == "col":
                    k = "column"
                    config_dict[section_key][k] = v
                    del config_dict[section_key]["col"]
                elif k == "enter_cmd":
                    k = "command"
                    config_dict[section_key][k] = v
                    del config_dict[section_key]["enter_cmd"]
                try:
                    config_dict[section_key][k] = eval(v)
                except:
                    pass
                try:
                    if k in ["column_names", "units", "constr_params"]:
                        if "," in v:
                            config_dict[section_key][k] = [
                                v.strip()
                                for v in config_dict[section_key][k].split(",")
                            ]
                            config_dict[section_key][k] = [
                                eval(v) for v in config_dict[section_key][k]
                            ]

                        else:
                            config_dict[section_key][k] = [config_dict[section_key][k]]
                    else:
                        pass
                except:
                    pass
        with open(fname.with_suffix(".yaml"), "w") as f:
            yaml.safe_dump(config_dict, f)
