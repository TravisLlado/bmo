#!/usr/bin/env python3
"""
sine_one.py — Sine wave stepper motion via TMC2209 on Raspberry Pi.

Tracks a real-time sine position profile and steps the motor to follow it.

Wiring defaults to M1 (BCM pin numbers, overridable via CLI):
  GPIO 16 → TMC2209 STEP  (Pi header pin 36)
  GPIO 26 → TMC2209 DIR   (Pi header pin 37)
  GPIO 7  → TMC2209 nEN   (Pi header pin 26, active LOW, shared)
  3.3V    → TMC2209 VIO + MS1 + MS2  (16x microstepping)
  GND     → TMC2209 GND (share with Pi GND)
  12–24 V → TMC2209 VM + GND
  Motor coils → A1 A2 B1 B2

Examples:
  python3 sine_one.py
  python3 sine_one.py --freq 1 --amp 0.1
  python3 sine_one.py --freq 0.5 --amp 0.5 --microsteps 8
  python3 sine_one.py --chip 4        # Pi 5 (RP1 uses /dev/gpiochip4)
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

RAMP_DOWN_S = 0.5   # seconds to ramp amplitude to zero on stop


def chk(ret, label):
    """Exit with a useful message if an lgpio call returns an error code."""
    if ret < 0:
        sys.exit(f"lgpio error on {label}: {lgpio.error_text(ret)}")
    return ret


def run_sine(h, step_pin, dir_pin, en_pin, freq, amp_steps, ramp_down=False):
    """
    Tracks amp_steps * sin(2π·freq·t) in real time.
    Steps forward/backward whenever actual position lags target by ≥ 0.5 steps.
    If ramp_down=True, smoothly reduces amplitude to zero over RAMP_DOWN_S seconds
    and returns the motor to position 0.
    """
    cur_dir = 1
    lgpio.gpio_write(h, dir_pin, cur_dir)
    if not ramp_down:
        lgpio.gpio_write(h, en_pin, 0)   # enable driver (active LOW)

    pos = 0.0
    t0  = time.perf_counter()
    ramp_start = t0 if ramp_down else None

    while True:
        now = time.perf_counter()

        if ramp_down:
            frac = 1.0 - min((now - ramp_start) / RAMP_DOWN_S, 1.0)
            effective_amp = amp_steps * frac
            if frac == 0.0:
                while pos > 0.5:
                    lgpio.gpio_write(h, step_pin, 1)
                    lgpio.gpio_write(h, step_pin, 0)
                    pos -= 1.0
                while pos < -0.5:
                    lgpio.gpio_write(h, step_pin, 1)
                    lgpio.gpio_write(h, step_pin, 0)
                    pos += 1.0
                return
        else:
            effective_amp = amp_steps

        target = effective_amp * math.sin(2.0 * math.pi * freq * (now - t0))
        error  = target - pos

        if abs(error) >= 0.5:
            direction = 1 if error > 0 else 0
            if direction != cur_dir:
                lgpio.gpio_write(h, dir_pin, direction)
                time.sleep(DIR_SETUP_S)
                cur_dir = direction
            lgpio.gpio_write(h, step_pin, 1)
            lgpio.gpio_write(h, step_pin, 0)
            pos += 1.0 if cur_dir else -1.0
        else:
            vel = abs(effective_amp * 2.0 * math.pi * freq *
                      math.cos(2.0 * math.pi * freq * (now - t0)))
            if vel > 0:
                time.sleep(min(0.4 / vel, 1e-3))


def main():
    parser = argparse.ArgumentParser(
        description="Continuous sine wave stepper motion via TMC2209",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--freq",       type=float, default=1.0,  help="Sine frequency (Hz)")
    parser.add_argument("--amp",        type=float, default=0.1,  help="Peak amplitude (revolutions)")
    parser.add_argument("--microsteps", type=int,   default=16,   help="Microstep setting (match MS1/MS2 wiring)")
    parser.add_argument("--step-pin",   type=int,   default=MOTORS_BY_NAME["M1"]["step"], help="STEP GPIO BCM pin")
    parser.add_argument("--dir-pin",    type=int,   default=MOTORS_BY_NAME["M1"]["dir"],  help="DIR GPIO BCM pin")
    parser.add_argument("--en-pin",     type=int,   default=NEN_PIN, help="nEN GPIO BCM pin (active LOW, shared)")
    parser.add_argument("--chip",       type=int,   default=0,    help="GPIO chip number (0 for Pi 4, 4 for Pi 5)")
    args = parser.parse_args()

    steps_per_rev = FULL_STEPS_PER_REV * args.microsteps
    amp_steps     = args.amp * steps_per_rev
    peak_rate     = amp_steps * 2.0 * math.pi * args.freq

    print(
        f"STEP={args.step_pin}  DIR={args.dir_pin}  nEN={args.en_pin}  gpiochip{args.chip}  "
        f"freq={args.freq} Hz  amp=±{args.amp} rev (±{amp_steps:.0f} steps)  "
        f"peak={peak_rate:.0f} steps/s"
    )

    try:
        h = lgpio.gpiochip_open(args.chip)
    except lgpio.error as e:
        sys.exit(
            f"Cannot open gpiochip{args.chip}: {e}\n"
            f"Fix: sudo usermod -aG gpio $USER  (then log out/in)\n"
            f"  or: sudo python3 {sys.argv[0]}"
        )

    for pin in (args.step_pin, args.dir_pin, args.en_pin):
        chk(lgpio.gpio_claim_output(h, pin), f"gpio_claim_output({pin})")

    lgpio.gpio_write(h, args.en_pin, 1)   # keep driver disabled until loop starts

    print("Running — Ctrl+C to stop")
    try:
        run_sine(h, args.step_pin, args.dir_pin, args.en_pin, args.freq, amp_steps)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        run_sine(h, args.step_pin, args.dir_pin, args.en_pin, args.freq, amp_steps,
                 ramp_down=True)
        lgpio.gpio_write(h, args.en_pin,   1)
        lgpio.gpio_write(h, args.step_pin, 0)
        lgpio.gpiochip_close(h)


if __name__ == "__main__":
    main()
