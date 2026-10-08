#!/bin/zsh
# PixelTracker live-dev launcher — start de GEÏNSTALLEERDE app, maar met de HTML
# uit deze repo. Wijzigingen in assets/pixel_repair_app.html zijn daardoor meteen
# zichtbaar na herstarten: geen build, geen DMG, geen installeren nodig.
set -e
cd "$(dirname "$0")"

APP_BIN="/Applications/PixelTracker.app/Contents/MacOS/PixelTracker"
HTML="$PWD/assets/pixel_repair_app.html"

if [ ! -x "$APP_BIN" ]; then
  echo "Geïnstalleerde app niet gevonden: $APP_BIN" >&2
  echo "Start anders met ./run_dev.sh (direct vanuit broncode)." >&2
  exit 1
fi

if [ ! -f "$HTML" ]; then
  echo "HTML niet gevonden: $HTML" >&2
  exit 1
fi

echo "==> App:      $APP_BIN"
echo "==> HTML:     $HTML (live uit de repo)"
exec env PIXELTRACKER_HTML="$HTML" "$APP_BIN" "$@"
