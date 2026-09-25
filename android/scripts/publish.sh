#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import hashlib, json, os, pathlib, re, shutil, subprocess
root = pathlib.Path.cwd()
apk = root / 'app/build/outputs/apk/release/app-release.apk'
sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
if not sdk:
    raise SystemExit('ANDROID_HOME auf das Android-SDK setzen.')
subprocess.run([str(pathlib.Path(sdk) / 'build-tools/35.0.0/apksigner'), 'verify', str(apk)], check=True)
metadata = json.loads((apk.parent / 'output-metadata.json').read_text())['elements'][0]
target = root.parent / 'flutter_app/docs/downloads'
target.mkdir(exist_ok=True)
manifest = target / 'android-version.json'
if manifest.exists():
    previous = json.loads(manifest.read_text())
    if metadata['versionCode'] <= previous['versionCode']:
        raise SystemExit('versionCode muss größer sein als die veröffentlichte Version. version.properties erhöhen und neu bauen.')
    previous_apk = target / 'benconnect.apk'
    if previous_apk.exists():
        signer = str(pathlib.Path(sdk) / 'build-tools/35.0.0/apksigner')
        def cert(path):
            output = subprocess.check_output([signer, 'verify', '--print-certs', str(path)], text=True)
            return [line for line in output.splitlines() if 'certificate SHA-256 digest:' in line]
        if not cert(apk) or cert(apk) != cert(previous_apk):
            raise SystemExit('Signierschlüssel stimmt nicht mit der veröffentlichten APK überein.')
# Export only the public certificate from the verified APK, never the keystore.
cert_output = subprocess.check_output([
    str(pathlib.Path(sdk) / 'build-tools/35.0.0/apksigner'),
    'verify', '--print-certs-pem', str(apk),
], text=True)
certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', cert_output, re.S)
if len(certificates) != 1:
    raise SystemExit('Genau ein APK-Signierzertifikat erwartet.')
cert_path = target / 'benconnect-signing-cert.pem'
cert_path.with_suffix('.tmp').write_text(certificates[0] + '\n')
cert_path.with_suffix('.tmp').replace(cert_path)
shutil.copyfile(apk, target / 'benconnect.apk.tmp')
(target / 'benconnect.apk.tmp').replace(target / 'benconnect.apk')
info = dict(versionCode=metadata['versionCode'], versionName=metadata['versionName'],
            sha256=hashlib.sha256(apk.read_bytes()).hexdigest(), url='/downloads/benconnect.apk')
manifest.with_suffix('.tmp').write_text(json.dumps(info, indent=2) + '\n')
manifest.with_suffix('.tmp').replace(manifest)
print('Veröffentlicht: https://benconnect.cyou/android.html')
PY
