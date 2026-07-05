#!/usr/bin/env python3
"""
pose_camera.py — Reads shoulder angles from AI Camera, prints to terminal.

DISPLAY=:0 python3 pose_camera.py

Prints both shoulder angles to stderr at 2 hz.
Updates skeleton overlay on LCD at 2 hz.
"""

import math, signal, sys, time, types
import numpy as np
import libcamera
from picamera2 import Picamera2
from picamera2.devices.imx500 import IMX500

sys.modules.setdefault("cv2", types.ModuleType("cv2"))

MODEL      = "/usr/share/imx500-models/imx500_network_posenet.rpk"
UPDATE_HZ  = 2.0
MIN_SCORE  = 2.0    # logit units above per-joint mean (heatmap values are all
                    # negative so sigmoid gives < 5% — use relative confidence)
EMA_ALPHA  = 0.35   # position smoothing
MIN_JOINTS = 7      # skip overlay if fewer confident joints
MAX_JUMP   = 0.15   # per-frame jump limit — rejects argmax glitches to edges

SKELETON = [
    (0,1),(0,2),(1,3),(2,4),
    (5,6),(5,7),(7,9),(6,8),(8,10),
    (5,11),(6,12),(11,12),
    (11,13),(13,15),(12,14),(14,16),
]

BONE_COLOR  = np.array([255, 120,   0, 200], dtype=np.uint8)
JOINT_COLOR = np.array([  0, 180, 255, 230], dtype=np.uint8)

_overlay   = None
_kp_smooth = None


def get_keypoints(heatmap):
    global _kp_smooth
    H, W, _ = heatmap.shape
    flat       = heatmap.reshape(-1, 17)
    idx        = flat.argmax(axis=0)
    rows, cols = np.divmod(idx, W)

    # Confidence = how far the peak stands above the per-joint mean.
    # Sigmoid is meaningless here because all logits are negative (max ~ -3).
    peak   = flat[idx, np.arange(17)]
    scores = (peak - flat.mean(axis=0)).astype(np.float32)

    kp = np.stack([rows / H, cols / W, scores], axis=1).astype(np.float32)

    if _kp_smooth is None:
        _kp_smooth = kp.copy()
    else:
        conf    = kp[:, 2] >= MIN_SCORE
        no_jump = np.abs(kp[:, :2] - _kp_smooth[:, :2]).max(axis=1) < MAX_JUMP
        update  = conf & no_jump
        _kp_smooth[update, :2] = (EMA_ALPHA * kp[update, :2]
                                  + (1 - EMA_ALPHA) * _kp_smooth[update, :2])
        _kp_smooth[:, 2] = kp[:, 2]
    return _kp_smooth


def shoulder_angle(kp, p1, vertex, p2):
    if any(kp[i, 2] < MIN_SCORE for i in (p1, vertex, p2)):
        return None
    a, b, c = kp[p1, :2], kp[vertex, :2], kp[p2, :2]
    v1, v2  = a - b, c - b
    denom   = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom < 1e-9:
        return None
    return math.degrees(math.acos(float(np.clip(np.dot(v1, v2) / denom, -1, 1))))


def _draw_line(arr, x0, y0, x1, y1, color):
    n  = max(abs(x1 - x0), abs(y1 - y0), 1) * 2
    xs = np.linspace(x0, x1, n).round().astype(int).clip(0, arr.shape[1] - 1)
    ys = np.linspace(y0, y1, n).round().astype(int).clip(0, arr.shape[0] - 1)
    arr[ys, xs] = color


def draw_and_set(picam2, kp, w, h):
    global _overlay
    if np.sum(kp[:, 2] >= MIN_SCORE) < MIN_JOINTS:
        return
    if _overlay is None:
        _overlay = np.zeros((h, w, 4), dtype=np.uint8)
    else:
        _overlay[:] = 0

    # IMX500 runs on the raw sensor image (pre-vflip), so y-coords are inverted
    # relative to the vflipped display.  Flip y when drawing into the overlay.
    def oy(y_norm): return h - 1 - int(y_norm * h)
    def ox(x_norm): return int(x_norm * w)

    for a, b in SKELETON:
        if kp[a, 2] >= MIN_SCORE and kp[b, 2] >= MIN_SCORE:
            _draw_line(_overlay,
                       ox(kp[a, 1]), oy(kp[a, 0]),
                       ox(kp[b, 1]), oy(kp[b, 0]),
                       BONE_COLOR)
    R = 5
    for i in range(17):
        if kp[i, 2] >= MIN_SCORE:
            cx, cy = ox(kp[i, 1]), oy(kp[i, 0])
            _overlay[max(0, cy-R):cy+R+1, max(0, cx-R):cx+R+1] = JOINT_COLOR
    picam2.set_overlay(_overlay)


def main():
    imx500 = IMX500(MODEL)
    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(
        transform=libcamera.Transform(vflip=True),
        controls={"FrameRate": 30},
    )
    picam2.configure(config)
    picam2.start_preview(True)
    picam2.start()
    ow, oh = config["main"]["size"]

    print("Loading PoseNet onto IMX500...", file=sys.stderr)
    imx500.show_network_fw_progress_bar()
    print("Running — Ctrl+C to stop\n", file=sys.stderr)

    done = [False]
    def _stop(*_): done[0] = True
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_t   = 0.0
    interval = 1.0 / UPDATE_HZ

    while not done[0]:
        outputs = imx500.get_outputs(picam2.capture_metadata())
        if outputs is None:
            continue

        heatmap = outputs[0]
        if heatmap.ndim != 3 or heatmap.shape[2] != 17:
            continue

        kp = get_keypoints(heatmap)

        now = time.monotonic()
        if now - last_t >= interval:
            left  = shoulder_angle(kp, 11, 5, 7)
            right = shoulder_angle(kp, 12, 6, 8)
            l_str = f"{left:5.1f}°"  if left  is not None else "  ---"
            r_str = f"{right:5.1f}°" if right is not None else "  ---"
            n_conf = int(np.sum(kp[:, 2] >= MIN_SCORE))
            print(f"left={l_str}  right={r_str}  joints={n_conf}/17", file=sys.stderr)
            draw_and_set(picam2, kp, ow, oh)
            last_t = now

    picam2.stop_preview()
    picam2.stop()


if __name__ == "__main__":
    main()
