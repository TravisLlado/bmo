#!/usr/bin/env python3
"""
pinout.py — Single source of truth for BMO GPIO pin assignments (BCM/GPIO
numbering, not physical header pin numbers).
"""

import re

PIN_MAP = {
    0:  "unused",
    1:  "unused",
    2:  "TP SDA",
    3:  "TP SCL",
    4:  "TP INT",
    5:  "Motor2 Step",
    6:  "Motor2 Direction",
    7:  "Motor3 Step",
    8:  "LCD CS",
    9:  "unused", # Would be LCD MISO, which is not used
    10: "LCD MOSI",
    11: "LCD SCLK",
    12: "LCD BL",
    13: "Motor Enable",
    14: "unused",
    15: "unused",
    16: "Motor1 Step",
    17: "TP RST",
    18: "I2S CLK",
    19: "I2S FS",
    20: "I2S DIN",
    21: "I2S DOUT",
    22: "LCD DC",
    23: "Motor4 Direction",
    24: "Motor4 Step",
    25: "Motor3 Direction",
    26: "Motor1 Direction",
    27: "LCD RST",
}

FULL_STEPS_PER_REV = 200
DIR_SETUP_S        = 20e-6   # TMC2209 DIR settle time before STEP rising edge

NEN_PIN = next(gpio for gpio, fn in PIN_MAP.items() if fn == "Motor Enable")

_motors = {}
for _gpio, _fn in PIN_MAP.items():
    _m = re.fullmatch(r"Motor(\d) (Step|Direction)", _fn)
    if _m:
        _num, _kind = _m.groups()
        _motors.setdefault(_num, {})["step" if _kind == "Step" else "dir"] = _gpio

MOTORS = [{"name": f"M{n}", **_motors[n]} for n in sorted(_motors)]
MOTORS_BY_NAME = {m["name"]: m for m in MOTORS}
