#!/bin/zsh
set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

# ---------- Versie automatisch ophogen bij elke build ----------
VERSION_FILE="VERSION"
if [ -f "$VERSION_FILE" ]; then
  CUR_VERSION="$(cat "$VERSION_FILE" | tr -d '[:space:]')"
else
  CUR_VERSION="3.0.0"
fi
MAJ="${CUR_VERSION%%.*}"
REST="${CUR_VERSION#*.}"
MIN="${REST%%.*}"
PATCH="${REST##*.}"
NEW_VERSION="${MAJ}.${MIN}.$((PATCH + 1))"
echo "${NEW_VERSION}" > "${VERSION_FILE}"

echo "==> Versie: ${CUR_VERSION} -> ${NEW_VERSION}"

sed -i '' "s/version='${CUR_VERSION}'/version='${NEW_VERSION}'/" build/PixelTracker.spec
sed -i '' "s/'CFBundleShortVersionString': '${CUR_VERSION}'/'CFBundleShortVersionString': '${NEW_VERSION}'/" build/PixelTracker.spec
sed -i '' "s/'CFBundleVersion': '${CUR_VERSION}'/'CFBundleVersion': '${NEW_VERSION}'/" build/PixelTracker.spec
sed -i '' "s/${CUR_VERSION}\.0/${NEW_VERSION}.0/" build/version_info_windows.txt
sed -i '' "s/${CUR_VERSION} Beta/${NEW_VERSION} Beta/" build/version_info_windows.txt
sed -i '' "s/Version=\"${CUR_VERSION}\"/Version=\"${NEW_VERSION}\"/" installer/PixelTracker-Windows.wxs
sed -i '' "s/#define AppVersion \"${CUR_VERSION}\"/#define AppVersion \"${NEW_VERSION}\"/" installer/PixelTracker-Windows.iss
sed -i '' "s/PixelTracker_V${CUR_VERSION}_Beta/PixelTracker_V${NEW_VERSION}_Beta/" installer/PixelTracker-Windows.iss
# update visible UI build badge in the app shell even when the text format is plain or beta-style
sed -i '' "s/Build V[0-9][0-9.]*\( Beta\)*/Build V${NEW_VERSION}/" assets/pixel_repair_app.html
sed -i '' "s/'V[0-9][0-9.]*\( Beta\)*'/'V${NEW_VERSION}'/" assets/pixel_repair_app.html

VERSION="${NEW_VERSION}"
APP_NAME="PixelTracker"
DMG_NAME="${APP_NAME}_V${VERSION}_macOS"

echo "==> Activeer virtuele omgeving..."
source .venv/bin/activate

echo "==> Bouw ${APP_NAME}.app met PyInstaller..."
pyinstaller --noconfirm --clean build/PixelTracker.spec

echo "==> Verwijder oude DMG..."
rm -f "dist/${DMG_NAME}.dmg"

echo "==> Maak DMG met drag-to-Applications layout..."
STAGING_DIR=$(mktemp -d)
cp -R "dist/${APP_NAME}.app" "${STAGING_DIR}/"
ln -s /Applications "${STAGING_DIR}/Applications"

hdiutil create -volname "${APP_NAME}" \
  -srcfolder "${STAGING_DIR}" \
  -ov -format UDZO \
  "dist/${DMG_NAME}.dmg"

rm -rf "${STAGING_DIR}"

echo "==> Klaar!"
echo "    .app: dist/${APP_NAME}.app"
echo "    .dmg: dist/${DMG_NAME}.dmg"