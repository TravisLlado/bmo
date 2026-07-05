#!/usr/bin/env bash
# One-time dependency install for the Pi.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y python3-pigpio python3-lgpio python3-picamera2 python3-numpy imx500-all

echo "Done. Run:  python3 pose_stepper.py"
