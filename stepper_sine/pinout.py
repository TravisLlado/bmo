#!/usr/bin/env python3
"""
pinout.py — Single source of truth for BMO stepper GPIO assignments (BCM numbering).

See ../pinout.md for the full 40-pin header and non-motor peripherals.
"""

FULL_STEPS_PER_REV = 200
DIR_SETUP_S        = 20e-6   # TMC2209 DIR settle time before STEP rising edge

NEN_PIN = 7   # shared active-LOW enable for all four TMC2209 drivers

MOTORS = [
    {"name": "M1", "step": 16, "dir": 23},
    {"name": "M2", "step":  5, "dir":  6},
    {"name": "M3", "step": 22, "dir": 26},
    {"name": "M4", "step": 12, "dir":  4},
]

MOTORS_BY_NAME = {m["name"]: m for m in MOTORS}
