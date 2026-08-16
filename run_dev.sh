#!/bin/zsh
# PixelTracker dev launcher — start app direct vanuit broncode (geen installer nodig)
cd "$(dirname "$0")"
.venv/bin/python src/pixel_repair_desktop.py
