#!/usr/bin/env bash
# Builds Velox for Safari and installs it on a Mac over ssh (unsigned, for testing).
#
#   scripts/safari-mac.sh [ssh-host]     (default host: mac)
#
# On the Mac: Xcode installed and launched once. Everything goes into
# ~/velox-safari there: extension/ (the build), xcode/ (generated once by
# safari-web-extension-converter), build/; the app lands in ~/Applications.
# In Safari: Settings → Developer → "Allow unsigned extensions" (again after
# every Safari restart), then Settings → Extensions → Velox.
set -euo pipefail

HOST="${1:-mac}"
BUNDLE_ID="be.trivium.velox" # temporary: the App Store ID is chosen with the account holder
cd "$(dirname "$0")/.."

npm run build:safari --silent
ssh "$HOST" 'mkdir -p ~/velox-safari'
rsync -a --delete dist/safari/ "$HOST:velox-safari/extension/"

ssh "$HOST" BUNDLE_ID="$BUNDLE_ID" bash -s <<'EOF'
set -euo pipefail
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
cd ~/velox-safari
if [ ! -d xcode/Velox/Velox.xcodeproj ]; then
  xcrun safari-web-extension-converter extension --project-location xcode --app-name Velox \
    --bundle-identifier "$BUNDLE_ID" --macos-only --swift --no-open --no-prompt --force
  # The converter capitalises the app's ID ("…Velox") but not the extension's
  # ("…velox.Extension"); Xcode refuses an extension ID that doesn't start with the app's.
  sed -i '' "s/PRODUCT_BUNDLE_IDENTIFIER = ${BUNDLE_ID%.*}.Velox;/PRODUCT_BUNDLE_IDENTIFIER = $BUNDLE_ID;/" \
    xcode/Velox/Velox.xcodeproj/project.pbxproj
fi
cd xcode/Velox
xcodebuild -project Velox.xcodeproj -scheme Velox -configuration Debug -derivedDataPath ~/velox-safari/build \
  CODE_SIGN_IDENTITY=- CODE_SIGNING_REQUIRED=NO DEVELOPMENT_TEAM= build | grep -E "error:|BUILD"
osascript -e 'quit app "Velox"' 2>/dev/null || true
mkdir -p ~/Applications
rm -rf ~/Applications/Velox.app
cp -R ~/velox-safari/build/Build/Products/Debug/Velox.app ~/Applications/
open ~/Applications/Velox.app # registers the extension with Safari
echo "Installed ~/Applications/Velox.app"
EOF
