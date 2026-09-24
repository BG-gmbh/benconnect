"""MongoDB-Zugriffsschicht mit lokalem Fallback.

Ersetzt die frühere SQLite-Anbindung (get_db/close_db/init_db in app.py). Der
Client ist ein prozessweiter, thread-sicherer Singleton – anders als bei SQLite
braucht es keine Verbindung pro Request und kein teardown.

Zwei Backends, automatisch gewählt:

  * "mongodb" – echtes MongoDB Atlas. Wird verwendet, sobald MONGODB_URI gesetzt
    ist UND die Verbindung tatsächlich klappt (Ping beim Start).
  * "local"   – ein in-process, pymongo-kompatibler Store (mongomock). Greift,
    wenn kein MONGODB_URI hinterlegt ist oder die Atlas-Verbindung scheitert.
    Damit läuft die Seite auch ohne externes MongoDB (z. B. lokal oder auf
    Render, wenn kein Secret gesetzt ist).

Achtung Fallback: Der lokale Store hält die Daten nur im Arbeitsspeicher des
Prozesses. Bei einem Neustart des Render-Containers oder über mehrere
Gunicorn-Worker hinweg werden die Daten NICHT geteilt/persistiert. Für echten
Mehrbenutzerbetrieb ist MONGODB_URI zu setzen.

Verbindung/Datenbank kommen aus der Umgebung:
    MONGODB_URI   z. B. mongodb+srv://user:pass@cluster.xxxxx.mongodb.net
    MONGODB_DB    Datenbankname (Default: "grouply")
"""

import logging
import os
import time
from urllib.parse import urlparse

from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError  # noqa: F401  (re-export für app.py)
from bson import ObjectId
from bson.errors import InvalidId

log = logging.getLogger(__name__)

_client = None
# Welches Backend aktiv ist: None (noch nicht initialisiert), "mongodb" | "local".
_backend = None
_last_retry_at = None

# Timeout, damit ein gesetztes-aber-unerreichbares MONGODB_URI nicht ewig blockt,
# bevor auf den lokalen Store zurückgefallen wird.
_MONGO_TIMEOUT_MS = 5000

# Atlas M0-Cluster pausieren nach Inaktivität und brauchen beim Aufwachen oft
# laenger als _MONGO_TIMEOUT_MS. Ohne Retry bliebe ein Worker, der genau in
# diesem Moment zuerst verbindet, fuer seine gesamte Lebensdauer auf dem
# lokalen (nicht geteilten) Fallback haengen -> je nach Gunicorn-Worker
# unterschiedliche, inkonsistente Daten. Deshalb hier alle _RETRY_COOLDOWN_S
# erneut versuchen, auf Atlas umzuschwenken.
_RETRY_COOLDOWN_S = 20


def _make_mongo_client(uri):
    """Baut einen echten MongoClient und verifiziert die Verbindung per Ping.

    Gibt den Client bei Erfolg zurück, sonst None (-> lokaler Fallback).
    """
    try:
        from pymongo import MongoClient

        # tz_aware: Datetimes kommen als timezone-aware (UTC) zurück, passend zu
        # datetime.now(timezone.utc), das wir beim Schreiben verwenden.
        parsed_uri = urlparse(uri)
        local_insecure = (
            parsed_uri.scheme == "mongodb"
            and (parsed_uri.hostname or "").lower()
            in {"localhost", "127.0.0.1", "mongo"}
            and os.environ.get("MONGODB_ALLOW_INSECURE_LOCAL", "").lower()
            in {"1", "true", "yes"}
        )
        client_options = {
            "tz_aware": True,
            "serverSelectionTimeoutMS": _MONGO_TIMEOUT_MS,
        }
        if not local_insecure:
            client_options["tls"] = True
        client = MongoClient(uri, **client_options)
        # Erzwingt eine echte Verbindung: schlägt fehl, wenn Atlas nicht
        # erreichbar / URI falsch ist -> wir fallen auf den lokalen Store zurück.
        client.admin.command("ping")
        return client
    except Exception as exc:  # noqa: BLE001 - jede Verbindungsart soll fallbacken
        log.warning(
            "MONGODB_URI gesetzt, aber Verbindung fehlgeschlagen (%s) – "
            "nutze lokalen Fallback-Store.",
            exc,
        )
        return None


def _make_local_client():
    """In-process, pymongo-kompatibler Store als Fallback ohne echtes MongoDB."""
    import mongomock

    return mongomock.MongoClient(tz_aware=True)


def get_client():
    """Prozessweiter Client-Singleton (lazy). Wählt MongoDB oder lokalen Store."""
    global _client, _backend, _last_retry_at
    uri = os.environ.get("MONGODB_URI")
    if _client is None:
        client = _make_mongo_client(uri) if uri else None
        if client is not None:
            _client, _backend = client, "mongodb"
            log.info("Datenbank-Backend: MongoDB (Atlas).")
        else:
            if os.environ.get("MONGODB_REQUIRED", "").lower() in {"1", "true", "yes"}:
                raise RuntimeError(
                    "MONGODB_URI ist erforderlich, aber MongoDB konnte nicht verbunden werden."
                )
            _client, _backend = _make_local_client(), "local"
            _last_retry_at = time.monotonic()
            log.info(
                "Datenbank-Backend: lokaler Fallback-Store (kein/kein "
                "erreichbares MONGODB_URI). Daten sind nicht persistent."
            )
        return _client

    if _backend == "local" and uri:
        now = time.monotonic()
        if _last_retry_at is None or (now - _last_retry_at) >= _RETRY_COOLDOWN_S:
            _last_retry_at = now
            client = _make_mongo_client(uri)
            if client is not None:
                _client, _backend = client, "mongodb"
                log.info(
                    "Datenbank-Backend: nach Fallback erfolgreich auf MongoDB "
                    "(Atlas) umgeschwenkt. Waehrend des lokalen Fallbacks "
                    "angelegte Daten dieses Workers sind NICHT uebernommen."
                )
    return _client


def active_backend():
    """Gibt "mongodb" oder "local" zurück – initialisiert den Client bei Bedarf."""
    if _backend is None:
        get_client()
    return _backend


def get_db():
    """Gibt die pymongo-Database zurück (Ersatz für das alte get_db())."""
    return get_client()[os.environ.get("MONGODB_DB", "grouply")]


def oid(value):
    """Parst einen String/ObjectId zu ObjectId. Gibt None bei ungültigem Wert.

    Ersetzt die frühere int()-Konvertierung von IDs. Aufrufer behandeln None
    als "nicht gefunden / 400".
    """
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError, ValueError):
        return None


def ensure_indexes():
    """Legt alle Indizes an (idempotent). Ersatz für init_db()/_ensure_*.

    MongoDB ist schemalos, daher entfallen CREATE TABLE / ALTER TABLE. Wir legen
    nur die Unique-/Sekundär-Indizes an, die die frühere SQLite-Schemadefinition
    hatte.
    """
    db = get_db()

    # users.username war UNIQUE NOT NULL.
    db.users.create_index("username", unique=True, name="uq_users_username")

    # schools.name war PRIMARY KEY -> als _id gespeichert, kein extra Index nötig.

    # learning_places: Index (school, created_at).
    db.learning_places.create_index(
        [("school", ASCENDING), ("created_at", ASCENDING)],
        name="idx_learning_places_school_created",
    )

    db.learning_groups.create_index("member_ids", name="idx_learning_groups_members")

    # chat_presence: PRIMARY KEY (subject, user_id).
    db.chat_presence.create_index(
        [("subject", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="uq_chat_presence_subject_user",
    )

    # chat_messages: Index (subject, _id) für Cursor-Paginierung.
    db.chat_messages.create_index(
        [("subject", ASCENDING), ("_id", ASCENDING)],
        name="idx_chat_messages_subject_id",
    )

    # chat_appointments.subject war PRIMARY KEY -> als _id gespeichert.

    # chat_ratings: PRIMARY KEY (subject, user_id).
    db.chat_ratings.create_index(
        [("subject", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="uq_chat_ratings_subject_user",
    )

    # chat_message_reports: UNIQUE(message_id, reporter_user_id) + Index.
    db.chat_message_reports.create_index(
        [("message_id", ASCENDING), ("reporter_user_id", ASCENDING)],
        unique=True,
        name="uq_chat_reports_message_reporter",
    )
    db.chat_message_reports.create_index(
        [("subject", ASCENDING), ("created_at", ASCENDING)],
        name="idx_chat_reports_subject_created",
    )

    # invite_codes.code war PRIMARY KEY -> als _id gespeichert.

    # admin_subject_scores: PRIMARY KEY (user_id, subject).
    db.admin_subject_scores.create_index(
        [("user_id", ASCENDING), ("subject", ASCENDING)],
        unique=True,
        name="uq_admin_subject_scores_user_subject",
    )

    # api_tokens.token war PRIMARY KEY -> als _id gespeichert. Index auf user_id.
    db.api_tokens.create_index("user_id", name="idx_api_tokens_user_id")

    # app_settings.key war PRIMARY KEY -> als _id gespeichert.

    # laden_purchases: Index created_at.
    db.laden_purchases.create_index("created_at", name="idx_laden_purchases_created")

    # quiz_questions: pro (school, class_name, subject) genau eine Frage je order (0-4).
    db.quiz_questions.create_index(
        [("school", ASCENDING), ("class_name", ASCENDING), ("subject", ASCENDING), ("order", ASCENDING)],
        unique=True,
        name="uq_quiz_questions_scope_order",
    )
