# lerngruppen finder

**Statische Webseiten** (HTML/CSS/JS) im Ordner `flutter_app/docs/` — Start, Login, Registrierung,
Dashboard, Chat, Admin, Laden, Datenschutz/Impressum. Damit Konten und Passwörter sicher bleiben,
läuft dazu ein **Python-Server** (`app.py`), der die Seiten ausliefert und Formulare, Session und
Datenbank übernimmt — Frontend und API laufen als **ein Prozess auf einem Origin**.

Live im Einsatz unter **benconnect.cyou**, gehostet auf **Render** (siehe [`DEPLOYMENT.md`](DEPLOYMENT.md)
für Domain-/Deploy-Details). Datenbank ist **MongoDB Atlas**; ohne erreichbares `MONGODB_URI` läuft der
Server lokal automatisch gegen einen In-Memory-Fallback-Store (siehe Abschnitt „Datenbank" unten) — so
lässt sich der Server auch offline/lokal starten, ohne einen echten Atlas-Zugang zu brauchen.

| Pfad | Inhalt |
|------|--------|
| `flutter_app/docs/index.html` | Startseite |
| `flutter_app/docs/login.html` | Login-Formular |
| `flutter_app/docs/register.html` | Registrierung (Einladungscode oder Admin) |
| `flutter_app/docs/einladung.html` | Konto per Einladungscode anlegen |
| `flutter_app/docs/dashboard.html` | Bereich nach Login (Zeugnis-Onboarding, Fach-Übersicht) |
| `flutter_app/docs/chat.html` | Lerngruppen-Chat |
| `flutter_app/docs/laden.html` | Punkte-Laden |
| `flutter_app/docs/settings.html` | Einstellungen (Profil, Passwort, Meine Daten exportieren/löschen) |
| `flutter_app/docs/admin.html` | Admin-Bereich (Nutzer, Einladungscodes, Laden, Lehrer-Kontakte) |
| `flutter_app/docs/datenschutz.html` / `impressum.html` | Pflichtseiten (DSGVO / § 5 DDG) |

Die Seiten kannst du im Editor bearbeiten wie jede andere Website. **Nicht** nur die HTML-Dateien auf
einen rein statischen Webspace legen, wenn du Login brauchst — dann ginge die Anmeldung nicht, weil sie
denselben Flask-Prozess braucht. Lokal: Server starten, im Browser die URLs öffnen (siehe unten).

## Schnellstart: Web-App starten

Einmalig installieren:

```bash
cd lerngruppen-finder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Danach starten:

```bash
cd lerngruppen-finder
source venv/bin/activate
python app.py
```

Öffnen:

- Lokal: `http://127.0.0.1:5000/`
- Im WLAN: `http://<SERVER-IP>:5000/`

Ohne `MONGODB_URI` in `.env` läuft der Server automatisch gegen den lokalen In-Memory-Store (siehe
„Datenbank" unten) — für einen ersten Test reicht das, für echten Mehrbenutzerbetrieb nicht.

## Native Flutter-App (optional, separat vom Produktions-Frontend)

`flutter_app/lib/` enthält zusätzlich eine native Flutter-App (Android/iOS/Desktop), die dieselbe API
anspricht. Das ist **nicht** dasselbe wie `flutter_app/docs/` — die live auf benconnect.cyou laufende
Seite ist die statische HTML/JS-Variante oben, nicht dieser native Client.

Zuerst Backend starten:

```bash
cd lerngruppen-finder
source venv/bin/activate
python app.py
```

Dann Flutter starten:

```bash
cd lerngruppen-finder/flutter_app
flutter pub get
# Nur lokale Entwicklung: HTTP wird fuer lokale Hosts akzeptiert.
flutter run -d chrome --dart-define=API_BASE_URL=http://127.0.0.1:5000
```

Android-Emulator:

```bash
cd lerngruppen-finder/flutter_app
flutter pub get
# Nur lokaler Android-Emulator.
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:5000
```

Echtes Handy im gleichen WLAN:

```bash
cd lerngruppen-finder/flutter_app
flutter pub get
# Fuer ein echtes Geraet nur mit einer HTTPS-Adresse starten:
flutter run --dart-define=API_BASE_URL=https://benconnect.cyou
```

Native Plattformordner ergänzen, falls Flutter sie braucht:

```bash
cd lerngruppen-finder/flutter_app
flutter create --platforms=android,ios,web .
```

Flutter prüfen:

```bash
flutter doctor
flutter --version
```

Für die tatsächliche Produktivumgebung (Render, Custom Domain, `render.yaml`) siehe
[`DEPLOYMENT.md`](DEPLOYMENT.md).

## Datenbank

Der Server nutzt **MongoDB** (`db_mongo.py`), keine SQLite/Datei-Datenbank mehr:

- Ist `MONGODB_URI` gesetzt **und** erreichbar, läuft alles gegen **MongoDB Atlas** — das ist der
  Produktivbetrieb.
- Fehlt `MONGODB_URI` oder ist Atlas gerade nicht erreichbar (z. B. beim Aufwachen eines pausierten
  Atlas-M0-Clusters), fällt der Prozess automatisch auf einen **In-Memory-Fallback-Store**
  (`mongomock`) zurück. Praktisch für lokale Entwicklung ohne Atlas-Zugang — Daten sind dabei aber
  **nicht persistent** und **nicht** zwischen mehreren Gunicorn-Workern geteilt. Der Server versucht
  danach alle 20 Sekunden erneut, auf Atlas umzuschwenken.
- `promote_admin.py USERNAME [user|teacher|admin|tester|dev]` setzt die Rolle eines bestehenden
  Nutzers direkt in der Datenbank (z. B. um sich selbst zum ersten Admin/Dev zu machen, falls
  `/setup.html` schon einmal durchlaufen wurde).

## Konfiguration (optional)

Werte in einer Datei **`.env`** im Projektordner (Vorlage: **`.env.example`**). Beim Start lädt
`app.py` sie automatisch (`python-dotenv`).

| Umgebungsvariable   | Bedeutung |
|--------------------|-----------|
| `FLASK_SECRET_KEY` | Pflicht sinnvoll ab „mehr als nur ich“ — sicherer Session-Schlüssel |
| `FLASK_HOST`       | Standard: `0.0.0.0` |
| `FLASK_PORT`       | Standard: `5000` |
| `FLASK_DEBUG`      | `true` nur zum Entwickeln |
| `MONGODB_URI`      | Atlas-Verbindungs-URI. Ohne (oder unerreichbar) → lokaler Fallback-Store, siehe oben |
| `MONGODB_DB`       | Datenbankname, Standard `grouply` |
| `OPENAI_API_KEY`   | Für die automatische Zeugnis-Auslesung beim Onboarding (optional; ohne Key nur manuelle Eingabe möglich) |
| `FLASK_ALLOWED_ORIGINS` / `SESSION_COOKIE_DOMAIN` | Nur nötig, wenn Frontend und API auf **unterschiedlichen** Domains laufen (Split-Origin). Im aktuellen Setup (ein Render-Service, ein Origin) nicht erforderlich |

### SMTP (Lehrer-Benachrichtigung bei Laden-Käufen)

| Variable | Bedeutung |
|----------|-----------|
| `SMTP_HOST` | Server, z. B. `smtp.gmail.com` — ohne Eintrag wird keine Mail gesendet |
| `SMTP_PORT` | Standard `587` (STARTTLS) |
| `SMTP_USER` / `SMTP_PASSWORD` | Anmeldung beim Provider (bei Gmail oft **App-Passwort**) |
| `SMTP_FROM` | Absender; leer = wie `SMTP_USER` |
| `SMTP_USE_SSL` | `1` für **SMTP_SSL**, typisch mit Port **465** |
| `SMTP_STARTTLS` | `0` deaktiviert STARTTLS (nur bei Bedarf) |
| `SMTP_TIMEOUT` | Sekunden (Standard 30) |

#### Gmail

1. Im Google-Konto **Zwei-Faktor-Authentifizierung** aktivieren.
2. Unter [App-Passwörter](https://myaccount.google.com/apppasswords) ein Passwort für „Mail“ erzeugen (16 Zeichen, Leerzeichen beim Einfügen weglassen).
3. In `.env` (siehe **`.env.example`**): `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` und `SMTP_FROM` = deine Gmail-Adresse, `SMTP_PASSWORD` = **nur** das App-Passwort (nie das normale Anmeldepasswort).
4. Server neu starten, damit `.env` geladen wird.

**Workspace (eigene Domain):** gleicher Host `smtp.gmail.com`, `SMTP_USER` / `SMTP_FROM` = deine `@schule.de`-Adresse, ebenfalls App-Passwort falls von der Organisation erlaubt.

Empfänger sind in der Admin-Oberfläche hinterlegte **Lehrer-Kontakte** plus Nutzer mit **Laden-E-Mail-Benachrichtigung** in den Einstellungen.

### Mail-Server Schnellanleitung (5 Minuten)

1. Datei `.env` anlegen (falls noch nicht da):  
   `cp .env.example .env`
2. In `.env` folgende Werte setzen (Beispiel Gmail mit STARTTLS/587):
   - `SMTP_HOST=smtp.gmail.com`
   - `SMTP_PORT=587`
   - `SMTP_USER=deine.adresse@gmail.com`
   - `SMTP_PASSWORD=<dein-app-passwort>`
   - `SMTP_FROM=deine.adresse@gmail.com`
3. Server neu starten:
   - laufenden Prozess stoppen (`CTRL+C`)
   - neu starten mit `python3 app.py` (oder venv: `python app.py`)
4. In `Admin -> Lehrer (E-Mail)` mindestens eine Lehrer-Adresse eintragen.
5. Test: Einen Punkte-Kauf im Laden auslösen.  
   Im Admin-Tab `Laden` im Protokoll muss danach bei E-Mail entweder **gesendet** stehen oder eine konkrete Fehlermeldung.

#### Typische Fehlerbilder

- `smtp_not_configured`: `SMTP_HOST` fehlt oder ist leer.
- `smtp_no_from`: `SMTP_FROM` und `SMTP_USER` sind leer.
- Auth-Fehler (z. B. `535`): meist falsches Passwort oder kein App-Passwort.
- Timeout/Verbindungsfehler: Port/Firewall/Provider blockiert SMTP.
