# BenConnect für Android

Installationsseite: https://benconnect.cyou/android.html

Die Android-App lädt ausschließlich `https://benconnect.cyou/` in einer WebView.
Dadurch bleiben Anmeldung, Chat, Admin, Laden und Einstellungen auf demselben
Origin wie die Website. Website-Updates erscheinen beim nächsten Laden; die App
braucht Internet. Externe Links öffnen eine passende andere App. Android ab 10.

Enthalten: Zurück-Navigation, Systemleisten-/Tastaturabstände, Datei-Auswahl,
Downloads mit Session-Cookie, JSON-Kontoexport, Wiederholen nach Ladefehlern,
Versionsanzeige und Link zur manuellen APK-Aktualisierung. Keine native
Push-Benachrichtigung, keine Offline-Datenbank und keine stille APK-Installation.
Der separate alte Flutter-Client wird hierfür nicht verwendet.

## Bauen

JDK 17, Android SDK mit Plattform 35 und Build Tools 35.0.0 installieren.
`ANDROID_HOME` auf den SDK-Pfad setzen (alternativ `local.properties` mit `sdk.dir`).

```bash
cd android
./scripts/init-signing.sh # genau einmal, erzeugt den privaten Release-Schlüssel
./scripts/release.sh
```

APK: `app/build/outputs/apk/release/app-release.apk`.
In Android Studio den Ordner `android/` öffnen. Der Gradle Wrapper ist enthalten.
Die Versionskombination folgt der [offiziellen AGP-Kompatibilitätstabelle](https://developer.android.com/build/releases/agp-8-9-0-release-notes).

## Updates veröffentlichen

1. `version.properties` ändern: `versionCode` muss bei jedem Release steigen,
   beispielsweise `4`; `versionName` beispielsweise `1.0.3`.
2. `./scripts/release.sh` ausführen und die APK auf einem Android-Gerät testen.
3. Mit gesetztem `ANDROID_HOME` `./scripts/publish.sh` ausführen. Das Skript
   prüft APK-Signatur, steigende Version und denselben Signierschlüssel wie die
   bisher veröffentlichte APK. Es kopiert die APK und Versionsinformationen nach
   `flutter_app/docs/downloads/`.
4. Website wie üblich bereitstellen. Auf diesem Server ist der Projektordner
   bereits in den Web-Container eingebunden; statische Dateien sind sofort verfügbar.
5. In der App: Menü → „App herunterladen / aktualisieren“ → APK herunterladen
   und öffnen → „Aktualisieren“. Nicht vorher deinstallieren.

Die APK und Versionsdatei sind Release-Artefakte und nicht im Git. Auf einem
anderen Webserver müssen sie zusätzlich zum Repository bereitgestellt werden.

## Signierschlüssel sichern

`keystore.properties` ist lokal und von Git ausgeschlossen. Der Schlüssel liegt
standardmäßig unter `~/.local/share/benconnect-android/release.jks`, das Passwort
in `~/.local/share/benconnect-android/password`. Dieses Verzeichnis und die lokale
Konfiguration verschlüsselt an einem zweiten Ort sichern. Nicht ins Repository
oder in den öffentlich erreichbaren Website-Ordner kopieren. Für alle Updates
müssen dieselbe Application-ID `cyou.benconnect.app` und derselbe Schlüssel
verwendet werden. Bei Verlust des Schlüssels lässt sich eine bereits installierte
App nicht mehr mit einem neuen Schlüssel aktualisieren.

## Prüfung

`./gradlew :app:assembleRelease :app:lintRelease` prüft Build und Android Lint.
Zusätzlich auf einem Gerät: Login/Logout, Zurück, Drehung, Tastatur im Chat,
Avatar-Upload, PDF- und Kontoexport, externe Links, ohne Netz neu laden und
Wiederholen nach Netzrückkehr testen. Für einen Update-Test zuerst die alte APK
installieren und danach die neue mit `adb install -r <apk>`; Login sollte erhalten
bleiben. Keine Zugangsdaten in Testprotokollen speichern.

WebView-Sicherheitskonfiguration orientiert sich an der
[Android-Dokumentation](https://developer.android.com/privacy-and-security/risks/webview-unsafe-file-inclusion):
HTTPS, keine lokale Datei-Freigabe, kein JavaScript-Interface, keine fremden Cookies.

Das App-Symbol verwendet das vorhandene Logo-Bild aus
`flutter_app/docs/assets/benconnect-logo.jpeg` unverändert und im ursprünglichen
Seitenverhältnis. Android passt die äußere Symbolform an den Launcher an.

## Angemeldet bleiben

Der Server stellt für die Android-App ein HttpOnly-Sitzungscookie mit 90 Tagen
Laufzeit aus und verlängert es bei Nutzung. Die WebView speichert es bereits
beim Laden einer Seite und beim Wechsel in den Hintergrund. Dadurch bleibt die
Anmeldung auch nach einem App-Neustart erhalten. Vorhandene App-Sitzungen werden
beim nächsten Request übernommen; falls die alte Sitzung schon verloren ist,
einmal erneut anmelden. Abmelden löscht das Cookie. Kein APK-Update nötig.

Regressionstest (mit isolierter Testdatenbank):
`MONGODB_URI= MONGODB_REQUIRED=0 python -m unittest discover -s tests -p test_android_session.py -v`
aus dem Repository-Hauptordner mit installierten Python-Abhängigkeiten.

## Öffentliches App-Zertifikat

`/downloads/benconnect-signing-cert.pem` enthält ausschließlich das öffentliche
Signierzertifikat, extrahiert aus der geprüften APK. Es ist auf `/android.html`
mit SHA-256-Fingerabdruck verlinkt. `scripts/publish.sh` aktualisiert die Datei
bei Veröffentlichungen. Der private Schlüssel bleibt außerhalb des Webordners.
Das selbstsignierte App-Zertifikat wird nicht als Vertrauenszertifikat auf
dem Handy installiert; Android prüft die in der APK enthaltene Signatur selbst.
