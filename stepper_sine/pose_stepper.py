#!/usr/bin/env python3
"""
pose_stepper.py — Right shoulder angle → stepper position via AI Camera.

DISPLAY=:0 python3 pose_stepper.py
sudo DISPLAY=:0 python3 pose_stepper.py   # if GPIO access is denied

If the wrong shoulder is tracked, swap the indices to: P1, VERTEX, P2 = 11, 5, 7
"""

import math, signal, sys, threading, time, types
import numpy as np
import libcamera
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500
import lgpio

sys.modules.setdefault("cv2", types.ModuleType("cv2"))

# ── Tune ──────────────────────────────────────────────────────────────────────
STEP_PIN  = 16
DIR_PIN   = 23
EN_PIN    = 24
AMP_REVS  = 0.25
ANGLE_MIN = 30.0
ANGLE_MAX = 160.0
MIN_SCORE = 0.5     # raise if skeleton is noisy, lower if joints drop out

# ── Fixed ─────────────────────────────────────────────────────────────────────
MODEL         = "/usr/share/imx500-models/imx500_network_posenet.rpk"
STEPS_PER_REV = 200 * 16
MAX_STEPS     = int(AMP_REVS * STEPS_PER_REV)
DIR_SETUP_S   = 20e-6

# Right shoulder angle: right_hip(12) → right_shoulder(6) → right_elbow(8)
# If this tracks the wrong shoulder, use: P1, VERTEX, P2 = 11, 5, 7
P1, VERTEX, P2 = 12, 6, 8

SKELETON = [
    (0, 1), (0, 2), (1, 3), (2, 4),
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
    (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16),
]

BONE_COLOR   = np.array([255, 120,   0, 200], dtype=np.uint8)
VERTEX_COLOR = np.array([  0, 255,   0, 230], dtype=np.uint8)
JOINT_COLOR  = np.array([  0, 180, 255, 230], dtype=np.uint8)


# ── Pose parsing ──────────────────────────────────────────────────────────────

def get_keypoints(outputs):
    if outputs is None:
        return None
    heatmap = outputs[0]             # (H, W, 17) — one heatmap per keypoint
    if heatmap.ndim != 3 or heatmap.shape[2] != 17:
        return None
    H, W, _ = heatmap.shape
    flat  = heatmap.reshape(-1, 17)
    idx   = flat.argmax(axis=0)
    rows, cols = np.divmod(idx, W)
    scores = 1.0 / (1.0 + np.exp(-flat[idx, np.arange(17)]))
    return np.stack([rows / H, cols / W, scores], axis=1).astype(np.float32)


def get_angle(kp):
    if any(kp[i, 2] < MIN_SCORE for i in (P1, VERTEX, P2)):
        return None
    a, b, c = kp[P1, :2], kp[VERTEX, :2], kp[P2, :2]
    v1, v2  = a - b, c - b
    denom   = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom < 1e-9:
        return None
    return math.degrees(math.acos(float(np.clip(np.dot(v1, v2) / denom, -1, 1))))


# ── Overlay drawing (numpy only — no per-frame malloc) ────────────────────────

_overlay = None

def _draw_line(arr, x0, y0, x1, y1, color):
    n  = max(abs(x1 - x0), abs(y1 - y0), 1) * 2
    xs = np.linspace(x0, x1, n).round().astype(int).clip(0, arr.shape[1] - 1)
    ys = np.linspace(y0, y1, n).round().astype(int).clip(0, arr.shape[0] - 1)
    arr[ys, xs] = color


def update_overlay(picam2, kp, w, h):
    global _overlay
    if _overlay is None:
        _overlay = np.zeros((h, w, 4), dtype=np.uint8)
    else:
        _overlay[:] = 0

    for a, b in SKELETON:
        if kp[a, 2] >= MIN_SCORE and kp[b, 2] >= MIN_SCORE:
            _draw_line(_overlay,
                       int(kp[a, 1] * w), int(kp[a, 0] * h),
                       int(kp[b, 1] * w), int(kp[b, 0] * h),
                       BONE_COLOR)
    R = 5
    for i in range(17):
        if kp[i, 2] >= MIN_SCORE:
            cx, cy = int(kp[i, 1] * w), int(kp[i, 0] * h)
            color  = VERTEX_COLOR if i == VERTEX else JOINT_COLOR
            _overlay[max(0, cy - R):cy + R + 1, max(0, cx - R):cx + R + 1] = color

    picam2.set_overlay(_overlay)


# ── Motor thread ──────────────────────────────────────────────────────────────

def run_motor(h_gpio, shared, stop_flag):
    pos, cur_dir = 0.0, 1
    lgpio.gpio_write(h_gpio, DIR_PIN, cur_dir)
    lgpio.gpio_write(h_gpio, EN_PIN, 0)   # enable driver

    while not stop_flag[0]:
        with shared["lock"]:
            target = shared["target"]
        if abs(target - pos) >= 0.5:
            want = 1 if target > pos else 0
            if want != cur_dir:
                lgpio.gpio_write(h_gpio, DIR_PIN, want)
                time.sleep(DIR_SETUP_S)
                cur_dir = want
            lgpio.gpio_write(h_gpio, STEP_PIN, 1)
            lgpio.gpio_write(h_gpio, STEP_PIN, 0)
            pos += 1.0 if cur_dir else -1.0
        else:
            time.sleep(1e-3)

    # Return to zero on exit
    while pos > 0.5:
        lgpio.gpio_write(h_gpio, DIR_PIN, 0); time.sleep(DIR_SETUP_S)
        lgpio.gpio_write(h_gpio, STEP_PIN, 1); lgpio.gpio_write(h_gpio, STEP_PIN, 0)
        pos -= 1.0
    while pos < -0.5:
        lgpio.gpio_write(h_gpio, DIR_PIN, 1); time.sleep(DIR_SETUP_S)
        lgpio.gpio_write(h_gpio, STEP_PIN, 1); lgpio.gpio_write(h_gpio, STEP_PIN, 0)
        pos += 1.0
    lgpio.gpio_write(h_gpio, EN_PIN, 1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    imx500 = IMX500(MODEL)
    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(
        transform=libcamera.Transform(vflip=True),  # --rotation 180 --hflip
        controls={"FrameRate": 30},
    )
    picam2.configure(config)
    picam2.start_preview(True)
    picam2.start()
    ow, oh = config["main"]["size"]

    print("Loading PoseNet onto IMX500 chip...")
    imx500.show_network_fw_progress_bar()

    h_gpio = lgpio.gpiochip_open(0)
    for pin in (STEP_PIN, DIR_PIN, EN_PIN):
        lgpio.gpio_claim_output(h_gpio, pin)
    lgpio.gpio_write(h_gpio, EN_PIN, 1)   # disabled until motor thread enables it

    shared    = {"target": 0.0, "lock": threading.Lock()}
    stop_flag = [False]

    def _stop(*_): stop_flag[0] = True
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    mthread = threading.Thread(
        target=run_motor, args=(h_gpio, shared, stop_flag), daemon=True
    )
    mthread.start()

    print("Running — Ctrl+C to stop")
    try:
        while not stop_flag[0]:
            kp = get_keypoints(imx500.get_outputs(picam2.capture_metadata()))
            if kp is not None:
                update_overlay(picam2, kp, ow, oh)
                angle = get_angle(kp)
                if angle is not None:
                    frac = (angle - ANGLE_MIN) / (ANGLE_MAX - ANGLE_MIN)
                    t    = (float(np.clip(frac, 0, 1)) * 2 - 1) * MAX_STEPS
                    with shared["lock"]:
                        shared["target"] = t
                    print(f"\r{angle:5.1f}°  →  {t:+6.0f} steps", end="", flush=True)
    finally:
        stop_flag[0] = True
        mthread.join(timeout=3.0)
        lgpio.gpiochip_close(h_gpio)
        picam2.stop_preview()
        picam2.stop()
        print()


if __name__ == "__main__":
    main()
