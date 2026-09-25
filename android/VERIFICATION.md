# Prüfung vom 25.09.2026

Release 1.0.1 (versionCode 2):

- Gradle Release-Build und Android Lint erfolgreich: 0 Fehler, 5 Hinweise
  (Übersetzbarkeit fest eingebauter Texte, Backup-Konfiguration und ein auf
  älteren Android-Versionen ignoriertes Manifest-Attribut).
- APK-Signatur mit apksigner geprüft.
- Android-15-Emulator: 1.0.0 installiert und gestartet; bei anfangs noch fehlender
  Netzwerkverbindung erschien die Fehleranzeige. Nach Wiederholen wurde die
  produktive BenConnect-Startseite geladen und visuell kontrolliert.
- Anschließend 1.0.1 per `adb install -r` erfolgreich über 1.0.0 installiert
  und gestartet. `firstInstallTime` blieb erhalten, `lastUpdateTime` änderte sich.
- Öffentlicher APK-Download liefert HTTP 200; SHA-256 stimmt mit dem Build überein.
- Erneutes Veröffentlichen derselben Versionsnummer wird abgewiesen.
- Kein Test mit einem echten Benutzerkonto: Login, Chat, Uploads und geschützte
  Downloads müssen noch auf einem echten Gerät mit einem Konto geprüft werden.
