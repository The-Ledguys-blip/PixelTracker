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
# Zichtbare build-badge + BUILD_VERSION in de app-shell. Het Beta-label blijft
# behouden: de HTML-contracttests verwachten "V<versie> Beta".
sed -i '' "s/Build V[0-9][0-9.]*\( Beta\)*/Build V${NEW_VERSION} Beta/" assets/pixel_repair_app.html
sed -i '' "s/'V[0-9][0-9.]*\( Beta\)*'/'V${NEW_VERSION} Beta'/" assets/pixel_repair_app.html

# Alle overige plekken waar de versie letterlijk staat: MSI/Inno-uitvoernamen,
# CI-workflow en documentatie. Zonder deze regels lopen die achter en falen de
# installer-contracttests na een bump.
for f in build_msi.ps1 build_windows.ps1 README.md REPO_MAP.md ".github/workflows/build-windows.yml"; do
  sed -i '' "s/${CUR_VERSION}/${NEW_VERSION}/g" "$f"
done

VERSION="${NEW_VERSION}"
APP_NAME="PixelTracker"
DMG_NAME="${APP_NAME}_V${VERSION}_macOS"

echo "==> Activeer virtuele omgeving..."
source .venv/bin/activate

echo "==> Bouw ${APP_NAME}.app met PyInstaller..."
pyinstaller --noconfirm --clean build/PixelTracker.spec

# ---------- Optionele code-signing / notarisatie ----------
# Zonder certificaat blijft de build ongewijzigd (unsigned, zoals voorheen).
# Voor distributie:
#   export PIXELTRACKER_SIGN_IDENTITY="Developer ID Application: Naam (TEAMID)"
#   export PIXELTRACKER_NOTARY_PROFILE="pixeltracker-notary"   # xcrun notarytool store-credentials
ENTITLEMENTS="build/entitlements.macos.plist"
SIGN_IDENTITY="${PIXELTRACKER_SIGN_IDENTITY:-}"
NOTARY_PROFILE="${PIXELTRACKER_NOTARY_PROFILE:-}"

if [ -n "$SIGN_IDENTITY" ]; then
  echo "==> Code-signeren met: ${SIGN_IDENTITY}"
  codesign --force --deep --options runtime --timestamp \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" "dist/${APP_NAME}.app"
  codesign --verify --deep --strict --verbose=2 "dist/${APP_NAME}.app"
else
  echo "==> PIXELTRACKER_SIGN_IDENTITY niet gezet: app wordt NIET ondertekend."
  echo "    Zet PIXELTRACKER_SIGN_IDENTITY (Developer ID Application) voor distributie."
fi

if [ -n "$NOTARY_PROFILE" ] && [ -n "$SIGN_IDENTITY" ]; then
  echo "==> Notariseren van de app..."
  ZIP_PATH="dist/${APP_NAME}_notarize.zip"
  ditto -c -k --keepParent "dist/${APP_NAME}.app" "$ZIP_PATH"
  xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "dist/${APP_NAME}.app"
  rm -f "$ZIP_PATH"
fi

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

if [ -n "$NOTARY_PROFILE" ] && [ -n "$SIGN_IDENTITY" ]; then
  echo "==> Notariseren van de DMG..."
  if xcrun notarytool submit "dist/${DMG_NAME}.dmg" --keychain-profile "$NOTARY_PROFILE" --wait; then
    xcrun stapler staple "dist/${DMG_NAME}.dmg"
  else
    echo "!! DMG-notarisatie mislukt; de app zelf is wel genotariseerd en gestapeld."
  fi
fi

echo "==> Klaar!"
echo "    .app: dist/${APP_NAME}.app"
echo "    .dmg: dist/${DMG_NAME}.dmg"