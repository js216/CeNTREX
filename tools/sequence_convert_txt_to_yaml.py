import json
from pathlib import Path

import yaml

p = Path() / "config"
p = [pi for pi in p.iterdir() if pi.is_dir()]


def loop_through_sequence(seq):
    for se in seq:
        for ids, s in enumerate(se):
            if ids in [2, 3, 4, 5]:
                if s == "":
                    if ids in [2, 3, 5]:
                        se[ids] = None
                    elif ids == 4:
                        se[ids] = False
                try:
                    v = eval(s)
                    if isinstance(v, tuple):
                        v = list(v)
                    se[ids] = v
                except Exception:
                    continue

        se.insert(6, True)
        loop_through_sequence(se[-1])
    return seq


for pi in p:
    for fname in pi.glob("*.txt"):
        with open(fname, "r") as f:
            try:
                seq = json.load(f)
                loop_through_sequence(seq)
            except Exception:
                continue
            try:
                with open(fname.with_suffix(".yaml"), "w") as f:
                    yaml.dump(seq, f, default_flow_style=True)
            except Exception as e:
                print(e)
                continue
