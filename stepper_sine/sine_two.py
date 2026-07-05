#!/usr/bin/env python3
"""
sine_two.py — Feed-forward sine wave to M1 + M2 at 100 Hz.

Each tick: compute target step position from sin(t), issue the
required steps immediately.  No DMA, no threads — just math + GPIO.

Wiring (BCM, from pinout.md):
  M1  STEP=16  DIR=23
  M2  STEP=5   DIR=6
  nEN=7  (shared active-LOW, controls all four drivers)

Examples:
  python3 sine_two.py
  python3 sine_two.py --freq 0.5 --amp 0.2
  python3 sine_two.py --chip 4        # Pi 5 (RP1 uses /dev/gpiochip4)
"""

import argparse
import math
import sys
import time

try:
    import lgpio  # type: ignore[import]
except ImportError:
    sys.exit("lgpio not found.  Run:  sudo apt install python3-lgpio")

from pinout import FULL_STEPS_PER_REV, DIR_SETUP_S, NEN_PIN, MOTORS_BY_NAME

LOOP_HZ = 100
LOOP_S  = 1.0 / LOOP_HZ

MOTORS = [MOTORS_BY_NAME["M1"], MOTORS_BY_NAME["M2"]]


def chk(ret, label):
    """Exit with a useful message if an lgpio call returns an error code."""
    if ret < 0:
        sys.exit(f"lgpio error on {label}: {lgpio.error_text(ret)}")
    return ret


def step_n(h, step_pin, dir_pin, cur_dir, delta):
    """Change direction if needed, then pulse STEP abs(delta) times."""
    direction = 1 if delta > 0 else 0
    if direction != cur_dir:
        lgpio.gpio_write(h, dir_pin, direction)
        time.sleep(DIR_SETUP_S)
    for _ in range(abs(delta)):
        lgpio.gpio_write(h, step_pin, 1)
        lgpio.gpio_write(h, step_pin, 0)
    return direction


def run(h, freq, amp_steps):
    positions = [0, 0]   # integer step positions for M1, M2
    cur_dirs  = [1, 1]

    for m in MOTORS:                            # establish a known DIR state
        lgpio.gpio_write(h, m["dir"], 1)        # before the first step

    t0        = time.perf_counter()
    next_tick = t0

    while True:
        t      = time.perf_counter() - t0
        target = round(amp_steps * math.sin(2.0 * math.pi * freq * t))

        for i, m in enumerate(MOTORS):
            delta = target - positions[i]
            if delta:
                cur_dirs[i]  = step_n(h, m["step"], m["dir"], cur_dirs[i], delta)
                positions[i] = target

        next_tick += LOOP_S
        wait = next_tick - time.perf_counter()
        if wait > 0:
            time.sleep(wait)


def main():
    parser = argparse.ArgumentParser(
        description="100 Hz feed-forward sine wave on M1 + M2",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--freq",       type=float, default=1.0,
                        help="Sine frequency (Hz)")
    parser.add_argument("--amp",        type=float, default=0.1,
                        help="Peak amplitude (revolutions)")
    parser.add_argument("--microsteps", type=int,   default=16,
                        help="Microstep setting (must match MS1/MS2 wiring)")
    parser.add_argument("--chip",       type=int,   default=0,
                        help="GPIO chip number (0 for Pi 4, 4 for Pi 5)")
    args = parser.parse_args()

    steps_per_rev = FULL_STEPS_PER_REV * args.microsteps
    amp_steps     = round(args.amp * steps_per_rev)
    peak_rate     = amp_steps * 2.0 * math.pi * args.freq

    motor_str = "  |  ".join(f'{m["name"]} STEP={m["step"]} DIR={m["dir"]}' for m in MOTORS)
    print(f"{motor_str}  |  nEN={NEN_PIN} (shared)  |  gpiochip{args.chip}")
    print(f"freq={args.freq} Hz  amp=±{args.amp} rev (±{amp_steps} steps)  "
          f"peak≈{peak_rate:.0f} steps/s  loop={LOOP_HZ} Hz")

    try:
        h = lgpio.gpiochip_open(args.chip)
    except lgpio.error as e:
        sys.exit(
            f"Cannot open gpiochip{args.chip}: {e}\n"
            f"Fix: sudo usermod -aG gpio $USER  (then log out/in)\n"
            f"  or: sudo python3 {sys.argv[0]}"
        )

    all_pins = [NEN_PIN] + [p for m in MOTORS for p in (m["step"], m["dir"])]
    for pin in all_pins:
        chk(lgpio.gpio_claim_output(h, pin), f"gpio_claim_output({pin})")

    lgpio.gpio_write(h, NEN_PIN, 1)   # drivers off until loop is ready

    lgpio.gpio_write(h, NEN_PIN, 0)   # enable drivers
    print("Running — Ctrl+C to stop")
    try:
        run(h, args.freq, amp_steps)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        lgpio.gpio_write(h, NEN_PIN, 1)   # disable drivers
        lgpio.gpiochip_close(h)
        print("Done.")


if __name__ == "__main__":
    main()
