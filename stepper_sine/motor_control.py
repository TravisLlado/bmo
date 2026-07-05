#!/usr/bin/env python3
"""
motor_control.py — Reads shoulder angle from stdin, drives TMC2209 stepper.

Pipe from camera:
  DISPLAY=:0 python3 pose_camera.py | python3 motor_control.py

Test without camera (holds motor at 90° position):
  echo "90" | python3 motor_control.py
"""

import signal, sys, threading, time
import lgpio

# ── Tune ──────────────────────────────────────────────────────────────────────
STEP_PIN  = 25
DIR_PIN   = 23
EN_PIN    = 24
AMP_REVS  = 0.25    # ±0.25 rev total travel
ANGLE_MIN = 30.0    # maps to -AMP end
ANGLE_MAX = 160.0   # maps to +AMP end

# ── Fixed ─────────────────────────────────────────────────────────────────────
STEPS_PER_REV = 200 * 16
MAX_STEPS     = int(AMP_REVS * STEPS_PER_REV)
DIR_SETUP_S   = 20e-6


def angle_to_steps(angle):
    frac = (angle - ANGLE_MIN) / (ANGLE_MAX - ANGLE_MIN)
    return (min(max(frac, 0.0), 1.0) * 2.0 - 1.0) * MAX_STEPS


def read_angles(shared, stop_flag):
    """Background thread: reads 'left right' angle lines from stdin."""
    for line in sys.stdin:
        if stop_flag[0]:
            break
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            left   = float(parts[0])
            right  = float(parts[1])
            target = angle_to_steps(right)   # change to left if needed
            with shared["lock"]:
                shared["target"] = target
            print(f"\rleft={left:5.1f}°  right={right:5.1f}°  →  {target:+6.0f} steps",
                  end="", flush=True)
        except ValueError:
            pass
    stop_flag[0] = True


def main():
    h = lgpio.gpiochip_open(0)
    for pin in (STEP_PIN, DIR_PIN, EN_PIN):
        lgpio.gpio_claim_output(h, pin)
    lgpio.gpio_write(h, EN_PIN, 0)   # enable driver (active LOW)
    lgpio.gpio_write(h, DIR_PIN, 1)

    shared    = {"target": 0.0, "lock": threading.Lock()}
    stop_flag = [False]

    def _stop(*_): stop_flag[0] = True
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    threading.Thread(target=read_angles, args=(shared, stop_flag), daemon=True).start()

    pos, cur_dir = 0.0, 1
    try:
        while not stop_flag[0]:
            with shared["lock"]:
                target = shared["target"]
            if abs(target - pos) >= 0.5:
                want = 1 if target > pos else 0
                if want != cur_dir:
                    lgpio.gpio_write(h, DIR_PIN, want)
                    time.sleep(DIR_SETUP_S)
                    cur_dir = want
                lgpio.gpio_write(h, STEP_PIN, 1)
                lgpio.gpio_write(h, STEP_PIN, 0)
                pos += 1.0 if cur_dir else -1.0
            else:
                time.sleep(0.5e-3)
    finally:
        print("\nReturning to zero...")
        while pos > 0.5:
            lgpio.gpio_write(h, DIR_PIN, 0); time.sleep(DIR_SETUP_S)
            lgpio.gpio_write(h, STEP_PIN, 1); lgpio.gpio_write(h, STEP_PIN, 0)
            pos -= 1.0
        while pos < -0.5:
            lgpio.gpio_write(h, DIR_PIN, 1); time.sleep(DIR_SETUP_S)
            lgpio.gpio_write(h, STEP_PIN, 1); lgpio.gpio_write(h, STEP_PIN, 0)
            pos += 1.0
        lgpio.gpio_write(h, EN_PIN, 1)
        lgpio.gpiochip_close(h)
        print()


if __name__ == "__main__":
    main()
