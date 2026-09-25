#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -e keystore.properties ]]; then
  echo 'Signierkonfiguration existiert bereits; bleibt unverändert.'
  exit 0
fi
umask 077
key_dir="${BENCONNECT_SIGNING_DIR:-$HOME/.local/share/benconnect-android}"
mkdir -p "$key_dir"
if [[ -e "$key_dir/release.jks" ]]; then
  echo 'Schlüssel existiert bereits. Vorhandene keystore.properties wiederherstellen; keinen neuen Schlüssel erzeugen.' >&2
  exit 1
fi
password="$(openssl rand -hex 32)"
printf '%s' "$password" > "$key_dir/password"
keytool -genkeypair -keystore "$key_dir/release.jks" -storetype PKCS12 \
  -storepass:file "$key_dir/password" -keypass:file "$key_dir/password" \
  -alias benconnect -keyalg RSA -keysize 4096 -validity 10000 \
  -dname 'CN=BenConnect Android, O=BenConnect'
printf 'storeFile=%s/release.jks\nstorePassword=%s\nkeyAlias=benconnect\nkeyPassword=%s\n' \
  "$key_dir" "$password" "$password" > keystore.properties
printf 'Signierung eingerichtet. Schlüssel und Passwort sicher sichern: %s\n' "$key_dir"
