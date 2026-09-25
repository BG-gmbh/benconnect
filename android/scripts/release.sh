#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f keystore.properties ]]; then
  echo 'Zuerst ./scripts/init-signing.sh ausführen.' >&2
  exit 1
fi
./gradlew --no-daemon :app:assembleRelease :app:lintRelease
apk='app/build/outputs/apk/release/app-release.apk'
if [[ ! -f "$apk" ]]; then echo 'Signierte APK fehlt.' >&2; exit 1; fi
echo "Fertig: $PWD/$apk"
echo 'Veröffentlichen nach erfolgreichem Test: ./scripts/publish.sh'
