import io
import json
import logging
import os
import secrets
import ipaddress
import re
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlencode, urlparse

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory, session
import segno
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash

from bson import ObjectId

from pymongo.errors import DuplicateKeyError

from db_mongo import active_backend, ensure_indexes, get_db as _mongo_db, oid
from mailer import send_smtp_mail, smtp_status

load_dotenv(Path(__file__).resolve().parent / ".env")

LEVELS = frozenset({"pro", "medium", "noob"})
ROLES = frozenset({"dev", "admin", "teacher", "tester", "user"})
ROLE_RANK = {"user": 0, "teacher": 1, "admin": 2, "tester": 2, "dev": 3}
# Tester teilt sich Rang 2 mit Admin: niemand unter Dev kann Tester anlegen
# oder verwalten (Peer-Rang, wie Admin<->Admin), aber Tester selbst duerfen
# nirgends schreiben (siehe admin_write_api) - Rang ist fuer sie nur relevant,
# damit sie nicht von einem Admin verwaltet werden koennen.
CHAT_SUBJECT_ORDER = ("german", "math", "english", "biology", "pgw", "spanish", "art")
CHAT_SUBJECTS = frozenset(CHAT_SUBJECT_ORDER)
CHAT_SUBJECT_LABELS = {
    "german": "Deutsch",
    "math": "Mathe",
    "english": "Englisch",
    "biology": "Biologie",
    "pgw": "PGW",
    "spanish": "Spanisch",
    "art": "Kunst",
}
CHAT_LEVEL_COLUMN = {subject: f"level_{subject}" for subject in CHAT_SUBJECT_ORDER}
CHAT_VERIFIED_COLUMN = {
    subject: f"pro_verified_{subject}" for subject in CHAT_SUBJECT_ORDER
}

# Standard-Kontrollfragen fuers Onboarding (5 pro Fach, Ueberpruefung der
# selbst gewaehlten Stufe). Gilt als globaler Fallback (school="", class_name=""
# in quiz_questions), solange niemand ein eigenes Set fuer eine Schule/Klasse
# hinterlegt hat (siehe /api/admin/quiz-questions).
DEFAULT_QUIZ_QUESTIONS = {
    "german": [
        {"q": "Welcher Artikel gehört zu „Tisch“?", "choices": ["der", "die", "das"], "correct": 0},
        {"q": "Was ist ein Synonym für „schnell“?", "choices": ["langsam", "rasch", "müde"], "correct": 1},
        {"q": "Wie lautet die Mehrzahl von „Kind“?", "choices": ["Kinder", "Kinden", "Kindes"], "correct": 0},
        {"q": "Welches Wort ist ein Verb?", "choices": ["Haus", "laufen", "schön"], "correct": 1},
        {"q": "Wie schreibt man richtig: „Ich weiß, ___ du kommst.“?", "choices": ["das", "dass", "daß"], "correct": 1},
    ],
    "math": [
        {"q": "7 × 8 = ?", "choices": ["54", "56", "64"], "correct": 1},
        {"q": "Was ist die Hälfte von 100?", "choices": ["40", "50", "60"], "correct": 1},
        {"q": "12 + 15 = ?", "choices": ["27", "25", "29"], "correct": 0},
        {"q": "Wie viele Seiten hat ein Dreieck?", "choices": ["2", "3", "4"], "correct": 1},
        {"q": "Was ist 9²?", "choices": ["18", "81", "72"], "correct": 1},
    ],
    "english": [
        {"q": "What is the English word for „Hund“?", "choices": ["cat", "dog", "bird"], "correct": 1},
        {"q": "Complete: „She ___ to school every day.“", "choices": ["go", "goes", "going"], "correct": 1},
        {"q": "What is the past tense of „go“?", "choices": ["goed", "went", "gone"], "correct": 1},
        {"q": "What is the opposite of „big“?", "choices": ["small", "tall", "long"], "correct": 0},
        {"q": "How do you say „Danke“ in English?", "choices": ["Please", "Sorry", "Thank you"], "correct": 2},
    ],
    "biology": [
        {"q": "Welches Organ pumpt das Blut durch den Körper?", "choices": ["Lunge", "Herz", "Leber"], "correct": 1},
        {"q": "Wie viele Beine hat ein Insekt normalerweise?", "choices": ["4", "6", "8"], "correct": 1},
        {"q": "Was brauchen Pflanzen zur Photosynthese?", "choices": ["Licht", "Dunkelheit", "Salz"], "correct": 0},
        {"q": "Wie nennt man die kleinste Einheit des Lebens?", "choices": ["Atom", "Zelle", "Molekül"], "correct": 1},
        {"q": "Welches Gas atmen wir zum Leben ein?", "choices": ["Kohlenstoffdioxid", "Sauerstoff", "Stickstoff"], "correct": 1},
    ],
    "pgw": [
        {"q": "Wie heißt die deutsche Verfassung?", "choices": ["Grundgesetz", "Bundesgesetz", "Staatsgesetz"], "correct": 0},
        {"q": "Wie oft finden in Deutschland Bundestagswahlen normalerweise statt?", "choices": ["alle 2 Jahre", "alle 4 Jahre", "alle 6 Jahre"], "correct": 1},
        {"q": "Wie heißt die Regierungschefin/der Regierungschef Deutschlands?", "choices": ["Präsident/in", "Kanzler/in", "König/in"], "correct": 1},
        {"q": "Was bedeutet „Demokratie“ grob übersetzt?", "choices": ["Herrschaft eines Einzelnen", "Herrschaft des Volkes", "Herrschaft des Geldes"], "correct": 1},
        {"q": "Wofür steht die Abkürzung EU?", "choices": ["Europäische Union", "Einheitliche Union", "Europäische Universität"], "correct": 0},
    ],
    "spanish": [
        {"q": "Was bedeutet „hola“?", "choices": ["tschüss", "hallo", "danke"], "correct": 1},
        {"q": "Wie sagt man „eins“ auf Spanisch?", "choices": ["uno", "dos", "tres"], "correct": 0},
        {"q": "Was bedeutet „gracias“?", "choices": ["bitte", "danke", "entschuldigung"], "correct": 1},
        {"q": "Wie sagt man „ich bin“ auf Spanisch?", "choices": ["yo soy", "tú eres", "él es"], "correct": 0},
        {"q": "Was bedeutet „casa“?", "choices": ["Auto", "Haus", "Straße"], "correct": 1},
    ],
    "art": [
        {"q": "Welche drei Farben sind die Grundfarben?", "choices": ["Rot, Grün, Blau", "Rot, Gelb, Blau", "Gelb, Grün, Lila"], "correct": 1},
        {"q": "Wer malte die „Mona Lisa“?", "choices": ["Picasso", "Da Vinci", "Van Gogh"], "correct": 1},
        {"q": "Was entsteht, wenn man Blau und Gelb mischt?", "choices": ["Grün", "Lila", "Orange"], "correct": 0},
        {"q": "Wie nennt man ein Bild von sich selbst?", "choices": ["Landschaft", "Selbstporträt", "Stillleben"], "correct": 1},
        {"q": "Welches Werkzeug benutzt man typischerweise zum Zeichnen?", "choices": ["Pinsel", "Bleistift", "Meißel"], "correct": 1},
    ],
}
QUIZ_MIN_CORRECT = {"pro": 4, "medium": 2}
QUIZ_DOWNGRADE = {"pro": "medium", "medium": "noob"}
ONBOARDING_QUIZ_QUESTION_COUNT = 3
ONBOARDING_QUIZ_MIN_CORRECT = {"pro": 2, "medium": 1}
LEVEL_RANK = {"noob": 0, "medium": 1, "pro": 2}

CHAT_MAX_USERS = 5
CHAT_BODY_MAX = 500
CHAT_ROOM_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
AVATAR_UPLOAD_DIR = Path(__file__).resolve().parent / "flutter_app" / "docs" / "uploads" / "avatars"
AVATAR_ALLOWED_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})
AVATAR_MAX_BYTES = 2 * 1024 * 1024
# Zeugnis-Upload fuer das Onboarding (GPT-Vision-Auslesung).
ZEUGNIS_ALLOWED_MEDIA = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
ZEUGNIS_MAX_BYTES = 8 * 1024 * 1024
ONBOARDING_MODEL = os.environ.get("ONBOARDING_MODEL", "gpt-4o")
STATIC_DIR = Path(__file__).resolve().parent / "flutter_app" / "docs"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-nur-lokal-bitte-aendern")

# Ein Render-Service liefert Frontend (flutter_app/docs) und API unter
# derselben Origin aus -> normalerweise same-origin, SameSite=Lax reicht.
# SESSION_COOKIE_SECURE=1 (Render/Prod) erzwingt trotzdem Secure+SameSite=None,
# das bleibt kompatibel falls doch mal cross-site zugegriffen wird (z. B.
# SESSION_COOKIE_DOMAIN/FLASK_ALLOWED_ORIGINS lokal gesetzt). Lokal (COOKIE_SECURE
# nicht gesetzt) bleibt es bei den Flask-Defaults (Lax, kein Secure), damit
# http://localhost funktioniert.
_cookie_secure = os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
if _cookie_secure:
    app.config.update(
        SESSION_COOKIE_SAMESITE="None",
        SESSION_COOKIE_SECURE=True,
    )
    _cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN", "").strip()
    if _cookie_domain:
        app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain

# Log-Level konfigurierbar (Default INFO), damit Debug-Meldungen z. B. in den
# Render-Logs sichtbar sind. LOG_LEVEL=DEBUG fuer mehr Details.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
app.logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
ALLOWED_ORIGINS = frozenset(
    origin.strip().rstrip("/")
    for origin in os.environ.get("FLASK_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)


@app.after_request
def add_flutter_cors_headers(response):
    origin = request.headers.get("Origin", "")
    normalized_origin = origin.rstrip("/")
    allow_origin = (
        _is_local_origin(origin)
        or normalized_origin in ALLOWED_ORIGINS
    )
    if allow_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        # Cross-Origin-Cookies (Session) benoetigen credentials-Support. Bei
        # credentials darf Allow-Origin NICHT "*" sein - wir spiegeln die
        # konkrete Origin (siehe oben), daher passt das zusammen.
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = (
            "Authorization, Content-Type"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
    return response


def _is_local_origin(origin):
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


def _normalize_appointment_datetime(raw):
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return None


def _normalize_appointment_location(raw):
    text = (raw or "").strip()
    if not text:
        return None
    if len(text) > 120:
        return None
    return text


def _normalize_school_name(raw):
    text = " ".join((raw or "").strip().split())
    if len(text) > 120:
        return None
    return text


def chat_subject_key(raw):
    if not raw or raw not in CHAT_SUBJECTS:
        return None
    return raw


def chat_room_key(raw):
    value = (raw or "").strip().lower()
    if not value:
        return None, None
    if ":" not in value:
        subject = chat_subject_key(value)
        if not subject:
            return None, None
        return subject, subject
    subject, suffix = value.split(":", 1)
    subject = chat_subject_key(subject)
    if not subject:
        return None, None
    suffix = suffix.strip()
    if not CHAT_ROOM_SUFFIX_RE.fullmatch(suffix):
        return None, None
    return f"{subject}:{suffix}", subject


def chat_room_label(room_key):
    room_key = (room_key or "").strip().lower()
    room, subject = chat_room_key(room_key)
    if not room or not subject:
        return room_key or "Chat"
    base = CHAT_SUBJECT_LABELS.get(subject, subject)
    if room == subject:
        return base
    return f"{base} · {room.split(':', 1)[1]}"


def parse_subject_levels(form):
    levels = tuple(form.get(CHAT_LEVEL_COLUMN[subject]) for subject in CHAT_SUBJECT_ORDER)
    if any(level not in LEVELS for level in levels):
        return None
    return levels


def normalize_class_name(raw):
    class_name = "".join((raw or "").strip().split()).lower()
    if len(class_name) > 20:
        return None
    return class_name


def class_name_for_role(role, raw):
    if role in ("admin", "tester", "dev"):
        return ""
    return normalize_class_name(raw)


def class_grade_number(class_name):
    digits = []
    for ch in (class_name or "").strip():
        if ch.isdigit():
            digits.append(ch)
        elif digits:
            break
    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


# Ab welcher Klassenstufe ein Fach unterrichtet wird (vorgegebene Tabelle).
# Unterhalb der Start-Stufe: "future" -> Fach wird gar nicht gezeigt.
# Oberhalb der End-Stufe: "past" -> Fach wandert in den "Ausgeblendet"-Tab.
SUBJECT_GRADE_START = {
    "german": 1,
    "math": 1,
    "english": 3,
    "biology": 5,
    "spanish": 6,
    "pgw": 7,
    "art": 1,
}
SUBJECT_GRADE_END = {
    "german": 13,
    "math": 13,
    "english": 13,
    "biology": 13,
    "spanish": 13,
    "pgw": 13,
    "art": 13,
}


def subject_visibility(grade, subject):
    """'current' | 'future' | 'past' fuer ein Fach bei gegebener Klassenstufe."""
    start = SUBJECT_GRADE_START.get(subject)
    if start is None or grade is None:
        return "current"
    if grade < start:
        return "future"
    end = SUBJECT_GRADE_END.get(subject)
    if end is not None and grade > end:
        return "past"
    return "current"


def grade_to_level(grade):
    """Deutsche Schulnote (1-6) -> Level. 1-2 = pro, 3-4 = medium, 5-6 = noob."""
    try:
        value = round(float(str(grade).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    if value <= 2:
        return "pro"
    if value <= 4:
        return "medium"
    return "noob"


def user_may_access_subject(db, user_id, subject):
    row = db.users.find_one(
        {"_id": oid(user_id)},
        {"class_name": 1, "role": 1},
    )
    if row is None:
        return False
    role = row["role"] if row.get("role") in ROLES else "user"
    if role in ("teacher", "admin", "dev"):
        return True
    grade = class_grade_number(row.get("class_name"))
    if grade is None:
        # Ohne bekannte Klassenstufe nicht sperren (z. B. Altbestand).
        return True
    # Zukuenftige Faecher (Stufe noch nicht erreicht) sind gesperrt;
    # aktuelle und vergangene ("Ausgeblendet") bleiben zugaenglich.
    return subject_visibility(grade, subject) != "future"


def next_pro_verification_values(row, levels):
    next_values = []
    for subject, level in zip(CHAT_SUBJECT_ORDER, levels):
        level_col = CHAT_LEVEL_COLUMN[subject]
        verified_col = CHAT_VERIFIED_COLUMN[subject]
        if level != "pro":
            next_values.append(0)
        elif row is not None and row.get(level_col) == "pro" and row.get(verified_col):
            next_values.append(1)
        else:
            next_values.append(0)
    return tuple(next_values)


def get_db():
    """Gibt die pymongo-Database zurück (Singleton, kein Verbindung-pro-Request)."""
    return _mongo_db()


def utcnow():
    """Aktueller Zeitstempel als timezone-aware UTC (Ersatz für datetime('now'))."""
    return datetime.now(timezone.utc)


def _new_user_defaults():
    """Vollstaendiger Default-Feldsatz eines users-Dokuments.

    Unter SQLite hatten diese Spalten NOT NULL DEFAULT-Werte, sodass Lesezugriffe
    wie row["school"] immer einen Wert lieferten. MongoDB ist schemalos – fehlt
    ein Feld, wirft row["feld"] KeyError. Daher werden neue Nutzer-Dokumente mit
    diesem Default-Satz angelegt (explizit gesetzte Felder ueberschreiben ihn).
    """
    defaults = {
        "role": "user",
        "display_name": "",
        "onboarded": 0,
        "banned": 0,
        "banned_message": "Dein Konto wurde gesperrt. Bitte den Admin kontaktieren.",
        "school": "",
        "class_name": "",
        "contact_email": None,
        "notify_laden_email": 0,
        "avatar_url": "",
        "iserv_email": "",
        "created_at": utcnow(),
    }
    for col in CHAT_LEVEL_COLUMN.values():
        defaults[col] = "noob"
    for col in CHAT_VERIFIED_COLUMN.values():
        defaults[col] = 0
    return defaults


def _seed_default_quiz_questions(db):
    """Legt den globalen Fallback (school="", class_name="") fuer jedes Fach
    an, falls noch keiner existiert. Idempotent, sicher bei jedem Start."""
    for subject, items in DEFAULT_QUIZ_QUESTIONS.items():
        if db.quiz_questions.count_documents({"school": "", "class_name": "", "subject": subject}):
            continue
        for order, item in enumerate(items):
            db.quiz_questions.update_one(
                {"school": "", "class_name": "", "subject": subject, "order": order},
                {"$setOnInsert": {
                    "question": item["q"],
                    "choices": item["choices"],
                    "correct": item["correct"],
                    "updated_at": utcnow(),
                    "updated_by": None,
                }},
                upsert=True,
            )


def _resolve_quiz_questions(db, school, class_name, subject):
    """5 Fragen fuer (school, class_name, subject), mit Fallback von genau
    passend -> schulweit (class_name="") -> global ("", "")."""
    for scope_school, scope_class in (
        (school, class_name),
        (school, ""),
        ("", ""),
    ):
        rows = list(
            db.quiz_questions.find(
                {"school": scope_school, "class_name": scope_class, "subject": subject}
            ).sort("order", 1)
        )
        if len(rows) == 5:
            return rows
    return []


def _subjects_with_level_increase(row, levels):
    return [
        subject
        for subject, level in zip(CHAT_SUBJECT_ORDER, levels)
        if LEVEL_RANK[level] > LEVEL_RANK.get(row.get(CHAT_LEVEL_COLUMN[subject]), 0)
    ]


def _validate_level_increase_quiz(db, row, levels, quiz_answers):
    """Prueft jede in den Einstellungen angehobene Fach-Stufe."""
    raised_subjects = _subjects_with_level_increase(row, levels)
    if not raised_subjects:
        return None
    if not isinstance(quiz_answers, dict):
        return "level_quiz_required"

    school = row.get("school") or ""
    class_name = row.get("class_name") or ""
    requested_levels = dict(zip(CHAT_SUBJECT_ORDER, levels))
    for subject in raised_subjects:
        official = _resolve_quiz_questions(db, school, class_name, subject)
        if len(official) != 5:
            return "level_quiz_unavailable"
        answers = quiz_answers.get(subject)
        if not isinstance(answers, list) or len(answers) != len(official):
            return "level_quiz_required"
        correct = sum(
            1 for index, question in enumerate(official)
            if isinstance(answers[index], int) and answers[index] == question["correct"]
        )
        if correct < QUIZ_MIN_CORRECT[requested_levels[subject]]:
            return "level_quiz_failed"
    return None


def init_db():
    """Legt Indizes an. Ersatz für die frühere SQLite-Schema-/Migrationslogik.

    MongoDB ist schemalos: CREATE TABLE / ALTER TABLE / PRAGMA entfallen. Das
    Einspielen der Startdaten passiert einmalig über migrate_sqlite_to_mongo.py,
    nicht mehr beim App-Start.
    """
    ensure_indexes()
    _seed_default_quiz_questions(get_db())


def app_setting(db, key, default=""):
    row = db.app_settings.find_one({"_id": key})
    if row is None:
        return default
    return row.get("value") or default


def set_app_setting(db, key, value):
    db.app_settings.update_one(
        {"_id": key},
        {"$set": {"value": value}},
        upsert=True,
    )


def int_app_setting(db, key, default=0):
    raw = app_setting(db, key, str(default))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


def school_license_limit_key(school):
    school = (school or "").strip()
    return f"school_license_limit::{school}" if school else "school_license_limit"


def school_license_limit(db, school):
    return int_app_setting(db, school_license_limit_key(school), 0)


def set_school_license_limit(db, school, limit):
    set_app_setting(db, school_license_limit_key(school), str(max(0, int(limit))))


def invite_license_usage_for_school(db, school):
    school = (school or "").strip()
    users = db.users.count_documents({"school": school})
    codes = db.invite_codes.count_documents({"used_at": None, "school": school})
    return {
        "users": users,
        "codes": codes,
        "active": users + codes,
    }


def invite_code_quota_payload(db, school):
    school = (school or "").strip()
    limit = school_license_limit(db, school)
    usage = invite_license_usage_for_school(db, school)
    active = usage["active"]
    return {
        "school": school,
        "limit": limit,
        "users": usage["users"],
        "codes": usage["codes"],
        "active": active,
        "remaining": None if limit <= 0 else max(0, limit - active),
    }


def school_license_has_free_slot(db, school):
    quota = invite_code_quota_payload(db, school)
    return quota["limit"] <= 0 or quota["active"] < quota["limit"]


def school_logo_key(school):
    school = (school or "").strip()
    return f"school_logo_url::{school}" if school else "school_logo_url"


def school_logo_url_for(db, school):
    school = (school or "").strip()
    if school:
        value = app_setting(db, school_logo_key(school))
        if value:
            return value
    return app_setting(db, "school_logo_url")


def _user_level_for_subject(db, user_id, subject):
    col = CHAT_LEVEL_COLUMN[subject]
    row = db.users.find_one({"_id": oid(user_id)}, {col: 1})
    if row is None:
        return "noob"
    v = row.get(col)
    return v if v in LEVELS else "noob"


def _user_is_verified_pro_for_subject(db, user_id, subject):
    level_col = CHAT_LEVEL_COLUMN[subject]
    verified_col = CHAT_VERIFIED_COLUMN[subject]
    row = db.users.find_one(
        {"_id": oid(user_id)},
        {level_col: 1, verified_col: 1, "role": 1},
    )
    if row is None:
        return False
    return row.get(level_col) == "pro" and (
        bool(row.get(verified_col)) or row.get("role") in ("teacher", "admin", "dev")
    )


def _chat_presence_pro_count(db, subject):
    return db.chat_presence.count_documents({"subject": subject, "level": "pro"})


def _chat_presence_non_pro_count(db, subject):
    return db.chat_presence.count_documents(
        {"subject": subject, "level": {"$ne": "pro"}}
    )


def _purge_chat_non_pros_if_no_pro(db, subject):
    if _chat_presence_pro_count(db, subject) == 0:
        db.chat_presence.delete_many(
            {"subject": subject, "level": {"$ne": "pro"}}
        )


def _delete_chat_room_if_empty(db, subject):
    """Raum (Stunde vorbei + alle weg, oder 0 Mitglieder) komplett aufraeumen."""
    if db.chat_presence.count_documents({"subject": subject}) == 0:
        db.chat_messages.delete_many({"subject": subject})
        db.chat_appointments.delete_one({"_id": subject})
        db.chat_ratings.delete_many({"subject": subject})
        db.chat_message_reports.delete_many({"subject": subject})


def delete_chat_subject_data(db, subject=None):
    """Löscht alle Chat-Daten eines Fachs oder für alle Fächer."""
    if subject is None:
        subject_filter = {}
        room_filter = {}
    else:
        subject_filter = {"subject": subject}
        room_filter = {"_id": {"$regex": f"^{re.escape(subject)}(:|$)"}}

    db.chat_presence.delete_many(subject_filter)
    db.chat_messages.delete_many(subject_filter)
    db.chat_appointments.delete_many(room_filter)
    db.chat_ratings.delete_many(subject_filter)
    db.chat_message_reports.delete_many(subject_filter)


def _user_role_for_chat(db, user_id):
    row = db.users.find_one({"_id": oid(user_id)}, {"role": 1})
    if row is None:
        return "user"
    role = row.get("role")
    return role if role in ROLES else "user"


def _chat_may_use_room(db, user_id, subject):
    """Lesen/Schreiben: Pro im Fach, Staff-Rolle oder mindestens ein Pro im Raum."""
    role = _user_role_for_chat(db, user_id)
    if role in ("teacher", "admin", "dev"):
        return True
    if _user_level_for_subject(db, user_id, subject) == "pro":
        return True
    return _chat_presence_pro_count(db, subject) >= 1


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            q = urlencode({"flash": "needlogin", "next": request.path})
            return redirect(f"/login.html?{q}")
        db = get_db()
        uid = session["user_id"]
        if is_user_banned(db, uid):
            msg = banned_message_for_user(db, uid)
            session.clear()
            q = urlencode({"flash": "banned", "flash_msg": msg})
            return redirect(f"/login.html?{q}")
        return view(*args, **kwargs)

    return wrapped


def login_required_api(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _load_api_auth_context():
            return jsonify(error="auth"), 401
        db = get_db()
        if is_user_banned(db, session["user_id"]):
            msg = banned_message_for_user(db, session["user_id"])
            session.clear()
            return jsonify(error="banned", message=msg), 403
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            q = urlencode({"flash": "needlogin", "next": request.path})
            return redirect(f"/login.html?{q}")
        db = get_db()
        if is_user_banned(db, session["user_id"]):
            msg = banned_message_for_user(db, session["user_id"])
            session.clear()
            q = urlencode({"flash": "banned", "flash_msg": msg})
            return redirect(f"/login.html?{q}")
        if session.get("role") not in ("teacher", "admin", "tester", "dev"):
            return redirect("/dashboard.html?flash=admin_only")
        return view(*args, **kwargs)

    return wrapped


def admin_api(view):
    """Admin-Endpunkte, die nur LESEN. Tester duerfen rein (Read-only-Rolle)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _load_api_auth_context():
            return jsonify(error="auth"), 401
        if session.get("role") not in ("teacher", "admin", "tester", "dev"):
            return jsonify(error="forbidden"), 403
        return view(*args, **kwargs)

    return wrapped


def admin_write_api(view):
    """Wie admin_api, aber fuer schreibende Endpunkte: Tester bleiben aussen
    vor, da die Rolle explizit auf Lesezugriff beschraenkt ist."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _load_api_auth_context():
            return jsonify(error="auth"), 401
        if session.get("role") not in ("teacher", "admin", "dev"):
            return jsonify(error="forbidden"), 403
        return view(*args, **kwargs)

    return wrapped


def _load_api_auth_context():
    if session.get("user_id"):
        return True
    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        return False
    token = auth.split(None, 1)[1].strip()
    if not token:
        return False
    db = get_db()
    tok = db.api_tokens.find_one({"_id": token})
    if tok is None:
        return False
    row = db.users.find_one(
        {"_id": tok["user_id"]},
        {"username": 1, "role": 1, "school": 1},
    )
    if row is None:
        return False
    role = row["role"] if row.get("role") in ROLES else "user"
    # Session speichert die User-ID als String (ObjectId ist nicht
    # JSON-cookie-serialisierbar); Lookups konvertieren via oid() zurueck.
    session["user_id"] = str(row["_id"])
    session["username"] = row["username"]
    session["role"] = role
    session["school"] = row.get("school") or ""
    g.api_token = token
    return True


def is_dev_session():
    return session.get("role") == "dev"


def _has_full_read_access():
    """Unbeschraenkte LESE-Sicht ueber alle Schulen/Klassen: Dev und Tester.

    Tester duerfen wie Dev alles sehen, aber nirgends schreiben - siehe
    admin_write_api fuer die Schreibsperre. Nicht fuer Autorisierungs-
    Entscheidungen (wer darf wen bearbeiten) verwenden, dafuer bleibt
    is_dev_session() massgeblich.
    """
    return session.get("role") in ("dev", "tester")


def role_rank(role):
    return ROLE_RANK.get(role if role in ROLES else "user", 0)


def hidden_roles_for_session():
    if _has_full_read_access():
        return []
    current_rank = role_rank(session.get("role"))
    return [role for role, rank in ROLE_RANK.items() if rank >= current_rank]


def admin_school(db):
    if "school" in session:
        return session.get("school") or ""
    uid = session.get("user_id")
    if not uid:
        return ""
    row = db.users.find_one({"_id": oid(uid)}, {"school": 1})
    school = (row.get("school") if row else "") or ""
    session["school"] = school
    return school


def scoped_user_filter(db):
    """Mongo-Filter für die für die aktuelle Session sichtbaren Nutzer.

    Gibt None zurück, wenn die Session gar nichts sehen darf (z. B. Lehrer ohne
    Klasse) – dann liefert der Aufrufer eine leere Liste.
    """
    if _has_full_read_access():
        return {}
    hidden_roles = hidden_roles_for_session()
    current_role = session.get("role", "user")
    flt = {
        "school": admin_school(db),
        "role": {"$nin": hidden_roles},
    }
    if current_role == "teacher":
        teacher_class = teacher_class_for_session(db)
        if not teacher_class:
            return None
        flt["class_name"] = teacher_class
    return flt


def can_access_user(db, user_id):
    row = db.users.find_one(
        {"_id": oid(user_id)},
        {"role": 1, "school": 1, "class_name": 1},
    )
    if row is None:
        return False
    if is_dev_session():
        return True
    target_role = row["role"] if row.get("role") in ROLES else "user"
    current_role = session.get("role", "user")
    
    # Rank check: can only manage lower-ranked users
    if role_rank(target_role) >= role_rank(current_role):
        return False
    
    # School check
    if (row.get("school") or "") != admin_school(db):
        return False

    if current_role == "teacher":
        teacher_class = teacher_class_for_session(db)
        target_class = normalize_class_name(row.get("class_name")) or ""
        if not teacher_class or teacher_class != target_class:
            return False
    
    return True


def teacher_class_for_session(db):
    if session.get("role") != "teacher":
        return ""
    row = db.users.find_one(
        {"_id": oid(session.get("user_id"))},
        {"class_name": 1},
    )
    return normalize_class_name(row.get("class_name") if row else "") or ""


def can_set_classes():
    return session.get("role") in ("admin", "dev")


def school_names_for_admin(db):
    if _has_full_read_access():
        rows = db.schools.find({}, {"_id": 1})
        return sorted((r["_id"] for r in rows), key=lambda s: s.lower())
    school = admin_school(db)
    return [school] if school else []


def _user_count(db):
    return db.users.count_documents({})


def _admin_count(db):
    return db.users.count_documents({"role": {"$in": ["admin", "dev"]}})


def is_user_banned(db, user_id):
    row = db.users.find_one({"_id": oid(user_id)}, {"banned": 1})
    return bool(row and row.get("banned"))


def banned_message_for_user(db, user_id):
    row = db.users.find_one({"_id": oid(user_id)}, {"banned_message": 1})
    default_msg = "Dein Konto wurde gesperrt. Bitte den Admin kontaktieren."
    if row is None:
        return default_msg
    msg = (row.get("banned_message") or "").strip()
    return msg or default_msg


@app.route("/")
def home():
    if session.get("user_id"):
        return redirect("/dashboard.html")
    return send_from_directory(app.static_folder, "index.html")


@app.route("/dashboard.html")
@login_required
def dashboard_page():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.route("/settings.html")
@login_required
def settings_page():
    return send_from_directory(app.static_folder, "settings.html")


@app.route("/chat.html")
@login_required
def chat_page():
    return send_from_directory(app.static_folder, "chat.html")


@app.route("/register.html")
def register_page_blocked():
    return redirect("/login.html?flash=register_disabled")


@app.route("/setup.html")
def setup_page():
    db = get_db()
    if _admin_count(db) > 0:
        return redirect("/login.html")
    return send_from_directory(app.static_folder, "setup.html")


@app.route("/setup", methods=["GET", "POST"])
def setup_create():
    if request.method == "GET":
        return redirect("/setup.html")

    db = get_db()
    if _admin_count(db) > 0:
        return redirect("/login.html?flash=setup_done")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password_confirm") or ""

    if not username or len(username) < 3:
        return redirect("/setup.html?flash=shortuser")
    if len(password) < 6:
        return redirect("/setup.html?flash=shortpass")
    if password != password2:
        return redirect("/setup.html?flash=mismatch")

    levels = parse_subject_levels(request.form) or tuple("pro" for _ in CHAT_SUBJECT_ORDER)
    lg, lm, le, lb, lp, ls, la = levels
    password_hash = generate_password_hash(password)
    row = db.users.find_one({"username": username}, {"_id": 1})
    if row is not None:
        db.users.update_one(
            {"_id": row["_id"]},
            {"$set": {
                "password_hash": password_hash,
                "level_german": lg, "level_math": lm, "level_english": le,
                "level_biology": lb, "level_pgw": lp, "level_spanish": ls,
                "level_art": la, "role": "dev", "banned": 0, "class_name": "",
            }},
        )
        db.api_tokens.delete_many({"user_id": row["_id"]})
        new_id = row["_id"]
    else:
        try:
            res = db.users.insert_one({
            **_new_user_defaults(),
                "username": username,
                "password_hash": password_hash,
                "level_german": lg, "level_math": lm, "level_english": le,
                "level_biology": lb, "level_pgw": lp, "level_spanish": ls,
                "level_art": la, "role": "dev",
            })
        except DuplicateKeyError:
            return redirect("/setup.html?flash=taken")
        new_id = res.inserted_id

    session.clear()
    session["user_id"] = str(new_id)
    session["username"] = username
    session["role"] = "dev"
    session["school"] = ""
    return redirect("/dashboard.html?flash=setup_done")


@app.route("/api/setup", methods=["POST"])
def api_setup_create():
    db = get_db()
    if _admin_count(db) > 0:
        return jsonify(error="setup_done"), 400

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password_confirm") or ""

    if not username or len(username) < 3:
        return jsonify(error="shortuser"), 400
    if len(password) < 6:
        return jsonify(error="shortpass"), 400
    if password != password2:
        return jsonify(error="mismatch"), 400

    password_hash = generate_password_hash(password)
    row = db.users.find_one({"username": username}, {"_id": 1})
    if row is not None:
        db.users.update_one(
            {"_id": row["_id"]},
            {"$set": {
                "password_hash": password_hash,
                "level_german": "pro", "level_math": "pro", "level_english": "pro",
                "level_biology": "pro", "level_pgw": "pro", "level_spanish": "pro",
                "level_art": "pro", "role": "dev", "banned": 0, "class_name": "",
            }},
        )
        db.api_tokens.delete_many({"user_id": row["_id"]})
        user_id = row["_id"]
    else:
        try:
            res = db.users.insert_one({
            **_new_user_defaults(),
                "username": username,
                "password_hash": password_hash,
                "level_german": "pro", "level_math": "pro", "level_english": "pro",
                "level_biology": "pro", "level_pgw": "pro", "level_spanish": "pro",
                "level_art": "pro", "role": "dev",
            })
            user_id = res.inserted_id
        except DuplicateKeyError:
            return jsonify(error="taken"), 409

    token = secrets.token_urlsafe(32)
    db.api_tokens.insert_one({"_id": token, "user_id": user_id})
    return jsonify(ok=True, token=token, user=_public_user_payload(db, user_id))


@app.route("/admin.html")
@admin_required
def admin_page():
    return send_from_directory(app.static_folder, "admin.html")


@app.route("/admin/users", methods=["POST"])
@admin_required
def admin_create_user():
    if session.get("role") == "tester":
        return redirect("/dashboard.html?flash=admin_only")
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password_confirm") or ""

    if not username or len(username) < 3:
        return redirect("/admin.html?flash=shortuser")
    if len(password) < 6:
        return redirect("/admin.html?flash=shortpass")
    if password != password2:
        return redirect("/admin.html?flash=mismatch")

    levels = parse_subject_levels(request.form)
    if levels is None:
        return redirect("/admin.html?flash=levels")

    role = (request.form.get("role") or "").strip()
    if not role:
        role = "admin" if request.form.get("is_admin") == "1" else "user"
    if role not in ROLES:
        role = "user"
    if role == "dev" and not is_dev_session():
        role = "user"
    if not is_dev_session() and role_rank(role) >= role_rank(session.get("role")):
        role = "user"

    lg, lm, le, lb, lp, ls, la = levels
    vg, vm, ve, vb, vp, vs, va = tuple(1 if level == "pro" else 0 for level in levels)
    db = get_db()
    school = (request.form.get("school") or "").strip()
    class_name = normalize_class_name(request.form.get("class_name"))
    if class_name is None:
        return redirect("/admin.html?flash=invalid_class")
    if not is_dev_session():
        school = admin_school(db)
    if session.get("role") == "teacher":
        teacher_class = teacher_class_for_session(db)
        if not teacher_class:
            return redirect("/admin.html?flash=invalid_class")
        class_name = teacher_class
    class_name = class_name_for_role(role, class_name)
    if class_name is None:
        return redirect("/admin.html?flash=invalid_class")
    if len(school) > 120:
        return redirect("/admin.html?flash=invalid_school")
    if not school_license_has_free_slot(db, school):
        return redirect("/admin.html?flash=code_limit")
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    try:
        db.users.insert_one({
            **_new_user_defaults(),
            "username": username,
            "password_hash": generate_password_hash(password),
            "level_german": lg, "level_math": lm, "level_english": le,
            "level_biology": lb, "level_pgw": lp, "level_spanish": ls,
            "level_art": la,
            "pro_verified_german": vg, "pro_verified_math": vm,
            "pro_verified_english": ve, "pro_verified_biology": vb,
            "pro_verified_pgw": vp, "pro_verified_spanish": vs,
            "pro_verified_art": va,
            "role": role, "school": school, "class_name": class_name,
        })
    except DuplicateKeyError:
        return redirect("/admin.html?flash=taken")

    return redirect("/admin.html?flash=user_created")


@app.route("/api/admin/users", methods=["GET"])
@admin_api
def admin_user_list():
    db = get_db()
    flt = scoped_user_filter(db)
    if flt is None:
        return jsonify(users=[])
    rows = sorted(
        db.users.find(flt),
        key=lambda r: (r.get("username") or "").lower(),
    )
    return jsonify(
        users=[
            {
                "id": str(r["_id"]),
                "username": r.get("username") or "(ohne Benutzername)",
                "role": r.get("role") if r.get("role") in ROLES else "user",
                "school": r.get("school") or "",
                "class_name": r.get("class_name") or "",
                "level_german": r.get("level_german"),
                "level_math": r.get("level_math"),
                "level_english": r.get("level_english"),
                "level_biology": r.get("level_biology"),
                "level_pgw": r.get("level_pgw"),
                "level_spanish": r.get("level_spanish"),
                "level_art": r.get("level_art"),
                "pro_verified_german": bool(r.get("pro_verified_german")),
                "pro_verified_math": bool(r.get("pro_verified_math")),
                "pro_verified_english": bool(r.get("pro_verified_english")),
                "pro_verified_biology": bool(r.get("pro_verified_biology")),
                "pro_verified_pgw": bool(r.get("pro_verified_pgw")),
                "pro_verified_spanish": bool(r.get("pro_verified_spanish")),
                "pro_verified_art": bool(r.get("pro_verified_art")),
                "banned": bool(r.get("banned")),
                "banned_message": r.get("banned_message") or "",
            }
            for r in rows
        ]
    )


@app.route("/api/admin/users/ban", methods=["POST"])
@admin_write_api
def admin_user_ban():
    data = request.get_json(silent=True) or {}
    user_id = oid(data.get("user_id"))
    if user_id is None:
        return jsonify(error="invalid_user"), 400
    ban = data.get("ban")
    if ban in (True, "true", "1", 1):
        banned = 1
    elif ban in (False, "false", "0", 0):
        banned = 0
    else:
        return jsonify(error="invalid_ban"), 400
    message = (data.get("message") or "").strip()
    if banned and not message:
        return jsonify(error="ban_message_required"), 400
    if len(message) > 500:
        return jsonify(error="ban_message_too_long"), 400
    if str(user_id) == session["user_id"]:
        return jsonify(error="self_ban"), 400
    db = get_db()
    if not can_access_user(db, user_id):
        return jsonify(error="not_found"), 404
    if banned:
        db.users.update_one(
            {"_id": user_id},
            {"$set": {"banned": banned, "banned_message": message}},
        )
    else:
        db.users.update_one({"_id": user_id}, {"$set": {"banned": banned}})
    return jsonify(ok=True)


@app.route("/api/admin/users/class", methods=["POST"])
@admin_write_api
def admin_user_class_update():
    if not can_set_classes():
        return jsonify(error="forbidden"), 403
    data = request.get_json(silent=True) or {}
    user_id = oid(data.get("user_id"))
    if user_id is None:
        return jsonify(error="invalid_user"), 400
    class_name = normalize_class_name(data.get("class_name"))
    if class_name is None:
        return jsonify(error="invalid_class"), 400
    db = get_db()
    if not can_access_user(db, user_id):
        return jsonify(error="not_found"), 404
    row = db.users.find_one({"_id": user_id}, {"role": 1})
    role = row["role"] if row and row.get("role") in ROLES else "user"
    class_name = class_name_for_role(role, class_name)
    if class_name is None:
        return jsonify(error="invalid_class"), 400
    db.users.update_one({"_id": user_id}, {"$set": {"class_name": class_name}})
    return jsonify(ok=True, class_name=class_name)


@app.route("/api/admin/users/pro-verification", methods=["POST"])
@admin_write_api
def admin_user_pro_verification():
    data = request.get_json(silent=True) or {}
    user_id = oid(data.get("user_id"))
    if user_id is None:
        return jsonify(error="invalid_user"), 400

    values = {}
    for subject, col in CHAT_VERIFIED_COLUMN.items():
        raw = data.get(subject)
        values[col] = 1 if raw in (True, "true", "1", 1) else 0

    db = get_db()
    if not can_access_user(db, user_id):
        return jsonify(error="not_found"), 404

    row = db.users.find_one(
        {"_id": user_id},
        {col: 1 for col in CHAT_LEVEL_COLUMN.values()},
    )
    if row is None:
        return jsonify(error="not_found"), 404

    for subject, level_col in CHAT_LEVEL_COLUMN.items():
        if row.get(level_col) != "pro":
            values[CHAT_VERIFIED_COLUMN[subject]] = 0

    db.users.update_one(
        {"_id": user_id},
        {"$set": {
            "pro_verified_german": values["pro_verified_german"],
            "pro_verified_math": values["pro_verified_math"],
            "pro_verified_english": values["pro_verified_english"],
            "pro_verified_biology": values["pro_verified_biology"],
            "pro_verified_pgw": values["pro_verified_pgw"],
            "pro_verified_spanish": values["pro_verified_spanish"],
            "pro_verified_art": values["pro_verified_art"],
        }},
    )
    return jsonify(
        ok=True,
        pro_verified_german=bool(values["pro_verified_german"]),
        pro_verified_math=bool(values["pro_verified_math"]),
        pro_verified_english=bool(values["pro_verified_english"]),
        pro_verified_biology=bool(values["pro_verified_biology"]),
        pro_verified_pgw=bool(values["pro_verified_pgw"]),
        pro_verified_spanish=bool(values["pro_verified_spanish"]),
        pro_verified_art=bool(values["pro_verified_art"]),
    )


@app.route("/api/admin/users/<string:user_id>", methods=["PUT"])
@admin_write_api
def admin_user_update(user_id):
    if not is_dev_session():
        return jsonify(error="forbidden"), 403
    user_id = oid(user_id)
    if user_id is None:
        return jsonify(error="not_found"), 404
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "user").strip()
    school = (data.get("school") or "").strip()
    if role not in ROLES:
        return jsonify(error="invalid_role"), 400
    if len(school) > 120:
        return jsonify(error="invalid_school"), 400
    db = get_db()
    row = db.users.find_one({"_id": user_id}, {"school": 1})
    if row is None:
        return jsonify(error="not_found"), 404
    old_school = row.get("school") or ""
    if school != old_school and not school_license_has_free_slot(db, school):
        return jsonify(error="code_limit", **invite_code_quota_payload(db, school)), 429
    class_name = "" if role in ("admin", "dev") else None
    if class_name is None:
        db.users.update_one(
            {"_id": user_id},
            {"$set": {"role": role, "school": school}},
        )
    else:
        db.users.update_one(
            {"_id": user_id},
            {"$set": {"role": role, "school": school, "class_name": class_name}},
        )
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    if str(user_id) == session.get("user_id"):
        session["role"] = role
        session["school"] = school
    else:
        db.api_tokens.delete_many({"user_id": user_id})
    return jsonify(ok=True)


@app.route("/api/admin/schools", methods=["GET"])
@admin_api
def admin_schools_list():
    db = get_db()
    return jsonify(schools=school_names_for_admin(db))


@app.route("/api/admin/schools", methods=["POST"])
@admin_write_api
def admin_schools_create():
    if not is_dev_session():
        return jsonify(error="forbidden"), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name or len(name) > 120:
        return jsonify(error="invalid_school"), 400
    db = get_db()
    try:
        db.schools.insert_one({"_id": name, "created_at": utcnow()})
    except DuplicateKeyError:
        return jsonify(error="duplicate"), 409
    return jsonify(ok=True, name=name)


@app.route("/api/admin/classes", methods=["GET"])
@admin_api
def admin_classes_list():
    db = get_db()
    if _has_full_read_access():
        school = (request.args.get("school") or "").strip()
    else:
        school = admin_school(db)
    flt = {"school": school} if school else {}
    classes = sorted({c for c in db.users.distinct("class_name", flt) if c})
    return jsonify(classes=classes)


def _quiz_scope_for_session(db, requested_school, requested_class):
    """Klemmt (school, class_name) auf das, was die aktuelle Sitzung bearbeiten
    darf: Dev = freie Wahl (inkl. globalem ""/""); Admin = eigene Schule, jede
    Klasse darin; Lehrkraft = nur die eigene Schule UND eigene Klasse."""
    if is_dev_session():
        return requested_school, requested_class
    school = admin_school(db)
    if session.get("role") == "teacher":
        return school, teacher_class_for_session(db)
    return school, requested_class


@app.route("/api/admin/quiz-questions", methods=["GET"])
@admin_api
def admin_quiz_questions_get():
    subject = (request.args.get("subject") or "").strip()
    if subject not in CHAT_SUBJECTS:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    school, class_name = _quiz_scope_for_session(
        db,
        (request.args.get("school") or "").strip(),
        normalize_class_name(request.args.get("class_name")) or "",
    )
    rows = list(
        db.quiz_questions.find(
            {"school": school, "class_name": class_name, "subject": subject}
        ).sort("order", 1)
    )
    questions = [
        {"question": r["question"], "choices": r["choices"], "correct": r["correct"]}
        for r in rows
    ]
    return jsonify(
        school=school, class_name=class_name, subject=subject,
        questions=questions, customized=bool(questions),
    )


@app.route("/api/admin/quiz-questions", methods=["POST"])
@admin_write_api
def admin_quiz_questions_save():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    if subject not in CHAT_SUBJECTS:
        return jsonify(error="invalid_subject"), 400
    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        return jsonify(error="invalid_questions"), 400
    cleaned = []
    for item in questions:
        if not isinstance(item, dict):
            return jsonify(error="invalid_questions"), 400
        q = (item.get("question") or "").strip()
        choices = item.get("choices")
        correct = item.get("correct")
        if not q or len(q) > 300:
            return jsonify(error="invalid_questions"), 400
        if (
            not isinstance(choices, list) or len(choices) != 3
            or any(not isinstance(c, str) or not c.strip() or len(c) > 120 for c in choices)
        ):
            return jsonify(error="invalid_questions"), 400
        if correct not in (0, 1, 2):
            return jsonify(error="invalid_questions"), 400
        cleaned.append({"question": q, "choices": [c.strip() for c in choices], "correct": correct})

    db = get_db()
    school, class_name = _quiz_scope_for_session(
        db,
        (data.get("school") or "").strip(),
        normalize_class_name(data.get("class_name")) or "",
    )
    for order, item in enumerate(cleaned):
        db.quiz_questions.update_one(
            {"school": school, "class_name": class_name, "subject": subject, "order": order},
            {"$set": {**item, "updated_at": utcnow(), "updated_by": oid(session["user_id"])}},
            upsert=True,
        )
    return jsonify(ok=True, school=school, class_name=class_name)


@app.route("/api/admin/quiz-questions", methods=["DELETE"])
@admin_write_api
def admin_quiz_questions_delete():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip()
    if subject not in CHAT_SUBJECTS:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    school, class_name = _quiz_scope_for_session(
        db,
        (data.get("school") or "").strip(),
        normalize_class_name(data.get("class_name")) or "",
    )
    if not school and not class_name:
        return jsonify(error="forbidden"), 403
    db.quiz_questions.delete_many({"school": school, "class_name": class_name, "subject": subject})
    return jsonify(ok=True)


@app.route("/api/admin/app-settings", methods=["GET"])
@admin_api
def admin_app_settings_get():
    db = get_db()
    school = (request.args.get("school") or "").strip() if _has_full_read_access() else admin_school(db)
    return jsonify(school_logo_url=school_logo_url_for(db, school), school=school)


@app.route("/api/admin/app-settings", methods=["POST"])
@admin_write_api
def admin_app_settings_post():
    data = request.get_json(silent=True) or {}
    school_logo_url = (data.get("school_logo_url") or "").strip()
    if len(school_logo_url) > 1000:
        return jsonify(error="invalid_logo_url"), 400
    if school_logo_url and not (
        school_logo_url.startswith("http://")
        or school_logo_url.startswith("https://")
    ):
        return jsonify(error="invalid_logo_url"), 400
    db = get_db()
    school = (data.get("school") or "").strip() if is_dev_session() else admin_school(db)
    if len(school) > 120:
        return jsonify(error="invalid_school"), 400
    set_app_setting(db, school_logo_key(school), school_logo_url)
    return jsonify(ok=True, school_logo_url=school_logo_url, school=school)


@app.route("/api/admin/db-download", methods=["GET"])
def admin_db_download():
    """Exportiert alle MongoDB-Collections als JSON-Datei.

    Nur fuer eingeloggte Devs: Der Export enthaelt Passwort-Hashes und
    E-Mail-Adressen. ObjectId/datetime werden per str() serialisiert.
    """
    if not _load_api_auth_context():
        return jsonify(error="auth"), 401
    if session.get("role") != "dev":
        return jsonify(error="forbidden"), 403
    db = get_db()
    export = {
        name: list(db[name].find({}))
        for name in sorted(db.list_collection_names())
    }
    payload = json.dumps(export, default=str, ensure_ascii=False, indent=2)
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=grouply-export.json"},
    )


@app.route("/api/admin/mail-status", methods=["GET"])
@admin_api
def admin_mail_status():
    return jsonify(smtp=smtp_status())


@app.route("/api/admin/mail-test", methods=["POST"])
@admin_write_api
def admin_mail_test():
    data = request.get_json(silent=True) or {}
    recipient = _valid_contact_email(data.get("email"))
    if not recipient:
        return jsonify(error="invalid_email"), 400
    ok, err = send_smtp_mail(
        [recipient],
        "benconnect: Test-Mail",
        (
            "Das ist eine Test-Mail von benconnect.\n\n"
            "Wenn diese Nachricht angekommen ist, funktioniert der Mailserver.\n"
        ),
    )
    if not ok:
        return jsonify(ok=False, error=err or "send_failed", smtp=smtp_status()), 400
    return jsonify(ok=True, smtp=smtp_status())


@app.route("/api/admin/users/password", methods=["POST"])
@admin_write_api
def admin_user_password():
    data = request.get_json(silent=True) or {}
    user_id = oid(data.get("user_id"))
    if user_id is None:
        return jsonify(error="invalid_user"), 400
    password = data.get("password") or ""
    if len(password) < 6:
        return jsonify(error="shortpass"), 400
    force_change = bool(data.get("force_change"))

    db = get_db()
    if not can_access_user(db, user_id):
        return jsonify(error="not_found"), 404
    row = db.users.find_one({"_id": user_id}, {"username": 1})
    db.users.update_one(
        {"_id": user_id},
        {"$set": {
            "password_hash": generate_password_hash(password),
            "must_change_password": force_change,
        }},
    )
    db.api_tokens.delete_many({"user_id": user_id})
    return jsonify(ok=True, username=row["username"])


@app.route("/api/admin/delete_message/<string:message_id>", methods=["DELETE"])
@admin_write_api
def admin_delete_message(message_id):
    message_id = oid(message_id)
    if message_id is None:
        return jsonify(error="message_not_found"), 404
    db = get_db()
    msg = db.chat_messages.find_one({"_id": message_id}, {"user_id": 1})
    row = None
    if msg is not None:
        row = db.users.find_one(
            {"_id": msg["user_id"]},
            {"school": 1, "role": 1, "class_name": 1},
        )
    target_role = row["role"] if row and row.get("role") in ROLES else "user"
    teacher_class = teacher_class_for_session(db) if row else ""
    if not row or (
        not is_dev_session()
        and (
            (row.get("school") or "") != admin_school(db)
            or role_rank(target_role) >= role_rank(session.get("role"))
            or (
                session.get("role") == "teacher"
                and (
                    not teacher_class
                    or (normalize_class_name(row.get("class_name")) or "") != teacher_class
                )
            )
        )
    ):
        return jsonify(error="message_not_found"), 404
    db.chat_messages.delete_one({"_id": message_id})
    return jsonify(success=True)


@app.route("/api/admin/chat-clear", methods=["POST"])
@admin_write_api
def admin_clear_chat():
    data = request.get_json(silent=True) or {}
    subject = (data.get("subject") or "").strip().lower()
    if subject and subject not in CHAT_SUBJECTS:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    delete_chat_subject_data(db, subject if subject else None)
    return jsonify(ok=True, subject=subject or "all")


@app.route("/api/admin/chat-reports", methods=["GET"])
@admin_api
def admin_chat_reports():
    db = get_db()
    flt = {"resolved_at": None}
    if not _has_full_read_access():
        hidden_roles = hidden_roles_for_session()
        flt["reported_school"] = admin_school(db)
        flt["reported_role"] = {"$nin": hidden_roles}
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                return jsonify(reports=[])
            flt["reported_class_name"] = teacher_class
    rows = list(
        db.chat_message_reports.find(flt)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(100)
    )
    return jsonify(
        reports=[
            {
                "id": str(row["_id"]),
                "message_id": str(row["message_id"]),
                "subject": row["subject"],
                "subject_label": CHAT_SUBJECT_LABELS.get(row["subject"], row["subject"]),
                "reported_user_id": str(row["reported_user_id"]),
                "reported_username": row["reported_username"],
                "reported_school": row.get("reported_school"),
                "reported_class_name": row.get("reported_class_name"),
                "reporter_user_id": str(row["reporter_user_id"]),
                "reporter_username": row["reporter_username"],
                "body": row["body"],
                "reason": row["reason"],
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
    )


@app.route("/api/admin/chat-reports/<string:report_id>/resolve", methods=["POST"])
@admin_write_api
def admin_resolve_chat_report(report_id):
    report_id = oid(report_id)
    if report_id is None:
        return jsonify(error="report_not_found"), 404
    db = get_db()
    row = db.chat_message_reports.find_one(
        {"_id": report_id, "resolved_at": None},
        {"reported_school": 1, "reported_class_name": 1, "reported_role": 1},
    )
    target_role = row["reported_role"] if row and row.get("reported_role") in ROLES else "user"
    teacher_class = teacher_class_for_session(db) if row else ""
    if not row or (
        not is_dev_session()
        and (
            (row.get("reported_school") or "") != admin_school(db)
            or role_rank(target_role) >= role_rank(session.get("role"))
            or (
                session.get("role") == "teacher"
                and (
                    not teacher_class
                    or (normalize_class_name(row.get("reported_class_name")) or "") != teacher_class
                )
            )
        )
    ):
        return jsonify(error="report_not_found"), 404
    db.chat_message_reports.update_one(
        {"_id": report_id},
        {"$set": {"resolved_at": utcnow(), "resolved_by": oid(session["user_id"])}},
    )
    return jsonify(ok=True)


@app.route("/api/admin/chats", methods=["GET"])
@admin_api
def admin_get_chats():
    db = get_db()

    visible_ids = None  # None = keine Einschränkung (dev)
    report_filter_base = None  # zusätzliche Report-Filter für Nicht-Devs
    empty = False
    if not _has_full_read_access():
        school = admin_school(db)
        hidden_roles = hidden_roles_for_session()
        user_flt = {"school": school, "role": {"$nin": hidden_roles}}
        report_filter_base = {
            "reported_school": school,
            "reported_role": {"$nin": hidden_roles},
        }
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                empty = True
            else:
                user_flt["class_name"] = teacher_class
                report_filter_base["reported_class_name"] = teacher_class
        if not empty:
            visible_ids = [
                u["_id"] for u in db.users.find(user_flt, {"_id": 1})
            ]

    result = []
    for subject in CHAT_SUBJECT_ORDER:
        if empty:
            result.append(
                {
                    "subject": subject,
                    "label": CHAT_SUBJECT_LABELS[subject],
                    "message_count": 0,
                    "rating_count": 0,
                    "report_count": 0,
                }
            )
            continue
        if visible_ids is None:
            count = db.chat_messages.count_documents({"subject": subject})
            rating_n = db.chat_ratings.count_documents({"subject": subject})
            report_n = db.chat_message_reports.count_documents(
                {"subject": subject, "resolved_at": None}
            )
        else:
            count = db.chat_messages.count_documents(
                {"subject": subject, "user_id": {"$in": visible_ids}}
            )
            rating_n = db.chat_ratings.count_documents(
                {"subject": subject, "user_id": {"$in": visible_ids}}
            )
            report_n = db.chat_message_reports.count_documents(
                {"subject": subject, "resolved_at": None, **report_filter_base}
            )
        result.append(
            {
                "subject": subject,
                "label": CHAT_SUBJECT_LABELS[subject],
                "message_count": int(count),
                "rating_count": int(rating_n),
                "report_count": int(report_n),
            }
        )
    return jsonify(chats=result)


@app.route("/api/admin/ratings", methods=["GET"])
@admin_api
def admin_list_ratings():
    db = get_db()
    ratings_filter = {}
    if not _has_full_read_access():
        hidden_roles = hidden_roles_for_session()
        user_flt = {"school": admin_school(db), "role": {"$nin": hidden_roles}}
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                return jsonify(ratings=[])
            user_flt["class_name"] = teacher_class
        visible_ids = [u["_id"] for u in db.users.find(user_flt, {"_id": 1})]
        ratings_filter = {"user_id": {"$in": visible_ids}}

    rows = list(
        db.chat_ratings.find(ratings_filter).sort("created_at", -1).limit(500)
    )

    user_ids = list({row["user_id"] for row in rows})
    users = {
        u["_id"]: u
        for u in db.users.find({"_id": {"$in": user_ids}}, {"username": 1})
    }
    subjects = list({row["subject"] for row in rows})
    appointments = {
        a["_id"]: a
        for a in db.chat_appointments.find(
            {"_id": {"$in": subjects}},
            {"started_at": 1, "ended_at": 1},
        )
    }
    scores = {
        (s["user_id"], s["subject"]): s
        for s in db.admin_subject_scores.find(
            {"user_id": {"$in": user_ids}, "subject": {"$in": subjects}},
            {"user_id": 1, "subject": 1, "points": 1, "note": 1},
        )
    }

    def _duration(appt):
        if not appt:
            return None
        started = appt.get("started_at")
        ended = appt.get("ended_at")
        if started is None or ended is None:
            return None
        try:
            return int((ended - started).total_seconds())
        except (TypeError, AttributeError):
            return None

    ratings = []
    for row in rows:
        user = users.get(row["user_id"])
        if user is None:
            # Entspricht dem früheren INNER JOIN users (verwaiste Ratings raus).
            continue
        appt = appointments.get(row["subject"])
        score = scores.get((row["user_id"], row["subject"]))
        ratings.append(
            {
                "subject": row["subject"],
                "subject_label": CHAT_SUBJECT_LABELS.get(
                    row["subject"], row["subject"]
                ),
                "user_id": str(row["user_id"]),
                "username": user["username"],
                "rating": int(row["rating"]),
                "comment": (row.get("comment") or "").strip(),
                "created_at": row.get("created_at"),
                "started_at": appt.get("started_at") if appt else None,
                "ended_at": appt.get("ended_at") if appt else None,
                "duration_seconds": _duration(appt),
                "admin_points": int(score.get("points") or 0) if score else 0,
                "admin_note": (score.get("note") or "") if score else "",
            }
        )
    return jsonify(ratings=ratings)


@app.route("/api/admin/subject-score", methods=["PUT"])
@admin_write_api
def admin_put_subject_score():
    data = request.get_json(silent=True) or {}
    subject = chat_subject_key(data.get("subject"))
    if not subject:
        return jsonify(error="invalid_subject"), 400
    user_id = oid(data.get("user_id"))
    if user_id is None:
        return jsonify(error="invalid_user"), 400
    try:
        points = int(data.get("points", 0))
    except (TypeError, ValueError):
        return jsonify(error="invalid_points"), 400
    if points < -10000 or points > 10000:
        return jsonify(error="invalid_points"), 400
    note = (data.get("note") or "").strip()
    if len(note) > 500:
        return jsonify(error="invalid_note"), 400

    db = get_db()
    if not can_access_user(db, user_id):
        return jsonify(error="not_found"), 404
    admin_id = oid(session["user_id"])
    db.admin_subject_scores.update_one(
        {"user_id": user_id, "subject": subject},
        {"$set": {
            "points": points,
            "note": note or None,
            "updated_at": utcnow(),
            "updated_by": admin_id,
        }},
        upsert=True,
    )
    return jsonify(ok=True)


@app.route("/api/setup-status", methods=["GET"])
def setup_status():
    db = get_db()
    return jsonify(setup_needed=_admin_count(db) == 0)


@app.route("/einladung.html")
def invite_page():
    if session.get("user_id"):
        return redirect("/dashboard.html")
    return send_from_directory(app.static_folder, "einladung.html")


@app.route("/einladung", methods=["POST"])
def invite_redeem():
    if session.get("user_id"):
        return redirect("/dashboard.html")

    code = (request.form.get("code") or "").strip()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password_confirm") or ""

    if not code:
        return redirect("/einladung.html?flash=bad_invite")
    if not username or len(username) < 3:
        return redirect("/einladung.html?flash=shortuser")
    if len(password) < 6:
        return redirect("/einladung.html?flash=shortpass")
    if password != password2:
        return redirect("/einladung.html?flash=mismatch")

    db = get_db()
    inv = db.invite_codes.find_one({"_id": code, "used_at": None})
    if not inv:
        return redirect("/einladung.html?flash=bad_invite")

    invite_role = inv["role"] if inv.get("role") in ROLES else "user"
    invite_class = class_name_for_role(invite_role, inv.get("class_name")) or ""
    try:
        res = db.users.insert_one({
            **_new_user_defaults(),
            "username": username,
            "password_hash": generate_password_hash(password),
            "level_german": "noob", "level_math": "noob", "level_english": "noob",
            "level_biology": "noob", "level_pgw": "noob", "level_spanish": "noob",
            "level_art": "noob",
            "role": invite_role,
            "school": inv.get("school") or "",
            "class_name": invite_class,
        })
    except DuplicateKeyError:
        return redirect("/einladung.html?flash=taken")
    new_id = res.inserted_id

    consumed = db.invite_codes.update_one(
        {"_id": code, "used_at": None},
        {"$set": {"used_at": utcnow(), "used_user_id": new_id}},
    )
    if consumed.matched_count != 1:
        # Code wurde parallel eingelöst – angelegten Nutzer wieder entfernen.
        db.users.delete_one({"_id": new_id})
        return redirect("/einladung.html?flash=bad_invite")

    session.clear()
    session["user_id"] = str(new_id)
    session["username"] = username
    session["role"] = invite_role
    session["school"] = inv.get("school") or ""
    return redirect("/dashboard.html?flash=redeem_ok")


@app.route("/api/invite", methods=["POST"])
def api_invite_redeem():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password_confirm") or ""

    if not code:
        return jsonify(error="bad_invite"), 400
    if not username or len(username) < 3:
        return jsonify(error="shortuser"), 400
    if len(password) < 6:
        return jsonify(error="shortpass"), 400
    if password != password2:
        return jsonify(error="mismatch"), 400

    db = get_db()
    inv = db.invite_codes.find_one({"_id": code, "used_at": None})
    if not inv:
        return jsonify(error="bad_invite"), 400

    invite_role = inv["role"] if inv.get("role") in ROLES else "user"
    invite_class = class_name_for_role(invite_role, inv.get("class_name")) or ""
    try:
        res = db.users.insert_one({
            **_new_user_defaults(),
            "username": username,
            "password_hash": generate_password_hash(password),
            "level_german": "noob", "level_math": "noob", "level_english": "noob",
            "level_biology": "noob", "level_pgw": "noob", "level_spanish": "noob",
            "level_art": "noob",
            "role": invite_role,
            "school": inv.get("school") or "",
            "class_name": invite_class,
        })
    except DuplicateKeyError:
        return jsonify(error="taken"), 409
    new_id = res.inserted_id

    consumed = db.invite_codes.update_one(
        {"_id": code, "used_at": None},
        {"$set": {"used_at": utcnow(), "used_user_id": new_id}},
    )
    if consumed.matched_count != 1:
        db.users.delete_one({"_id": new_id})
        return jsonify(error="bad_invite"), 400

    token = secrets.token_urlsafe(32)
    db.api_tokens.insert_one({"_id": token, "user_id": new_id})

    return jsonify(ok=True, token=token, user=_public_user_payload(db, new_id))


@app.route("/api/admin/invite-codes", methods=["GET"])
@admin_api
def admin_invite_list():
    db = get_db()
    flt = {"used_at": None}
    if not _has_full_read_access():
        flt["school"] = admin_school(db)
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                return jsonify(codes=[])
            flt["class_name"] = teacher_class
    rows = list(
        db.invite_codes.find(flt).sort("created_at", -1).limit(100)
    )
    return jsonify(
        codes=[
            {
                "code": r["_id"],
                "school": r.get("school") or "",
                "class_name": r.get("class_name") or "",
                "role": r.get("role") or "user",
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]
    )


def _pdf_text(value):
    """Return text that can safely be used with PDF's built-in Helvetica font."""
    return str(value or "").encode("cp1252", "replace").decode("latin-1")


def _pdf_escape(value):
    return _pdf_text(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _qr_pdf_commands(value, x, y, size):
    """Render a QR code as vector rectangles in a PDF content stream."""
    matrix = tuple(tuple(row) for row in segno.make(value, error="m", micro=False).matrix)
    border = 4
    scale = size / (len(matrix) + 2 * border)
    rectangles = []
    for row_index, row in enumerate(matrix):
        column = 0
        while column < len(row):
            if not row[column]:
                column += 1
                continue
            run_start = column
            while column < len(row) and row[column]:
                column += 1
            rect_x = x + (border + run_start) * scale
            rect_y = y + size - (border + row_index + 1) * scale
            rect_width = (column - run_start) * scale
            rectangles.append(
                f"{rect_x:.3f} {rect_y:.3f} {rect_width:.3f} {scale:.3f} re"
            )
    return "q 0 g " + " ".join(rectangles) + " f Q"


def _invite_registration_url(code):
    return "https://benconnect.cyou/einladung.html?" + urlencode({"code": str(code or "")})


def _invite_codes_pdf(rows):
    """Create a printable PDF worksheet for unused invite codes."""
    rows = list(rows)
    per_page = 10
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    objects = []

    def add_object(payload):
        objects.append(payload)
        return len(objects)

    catalog_id = add_object(b"")
    pages_id = add_object(b"")
    font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    page_ids = []
    for page_number, page_rows in enumerate(pages, 1):
        commands = [
            "BT /F1 18 Tf 50 800 Td (Schüler_innen-Liste - Einladungscodes) Tj ET",
            f"BT /F1 9 Tf 50 782 Td (Seite {page_number} von {len(pages)}) Tj ET",
            "0.6 w 50 757 m 545 757 l S",
        ]
        start_number = (page_number - 1) * per_page
        for index, row in enumerate(page_rows, 1):
            school = str(row.get("school") or "-")
            class_name = str(row.get("class_name") or "-")
            code = str(row.get("_id") or "")
            registration_url = _invite_registration_url(code)
            column = (index - 1) % 2
            row_index = (index - 1) // 2
            box_x = 50 + column * 253
            box_top = 748 - row_index * 138
            box_bottom = box_top - 126
            text_x = box_x + 10
            commands.extend([
                f"q 0.8 w [4 3] 0 d 0.45 G {box_x} {box_bottom} 242 126 re S Q",
                f"BT /F1 9 Tf {text_x} {box_top - 16} Td "
                f"(Nr. {start_number + index}) Tj ET",
                f"BT /F1 10 Tf {text_x} {box_top - 32} Td "
                f"(Einladungscode: {_pdf_escape(code)}) Tj ET",
                f"BT /F1 9 Tf {text_x} {box_top - 47} Td "
                f"(Schule: {_pdf_escape(school[:32])}) Tj ET",
                f"BT /F1 9 Tf {text_x} {box_top - 61} Td "
                f"(Klasse: {_pdf_escape(class_name[:20])}) Tj ET",
                f"BT /F1 9 Tf {text_x} {box_bottom + 51} Td (Name:) Tj ET",
                f"BT /F1 9 Tf {text_x} {box_bottom + 36} Td (________________________) Tj ET",
                f"BT /F1 8 Tf {text_x} {box_bottom + 14} Td (Webseite: benconnect.cyou) Tj ET",
                f"% QR {start_number + index}",
                _qr_pdf_commands(registration_url, box_x + 164, box_bottom + 7, 70),
            ])
        if not page_rows:
            commands.append("BT /F1 11 Tf 50 720 Td (Keine offenen Einladungscodes vorhanden.) Tj ET")
        commands.append(
            "BT /F1 8 Tf 50 45 Td "
            "(Jeder Code ist nur einmal gültig. QR-Code scannen oder Einladungscode eingeben.) Tj ET"
        )
        stream = "\n".join(commands).encode("latin-1")
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, payload in enumerate(objects, 1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(payload)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return output.getvalue()


@app.route("/api/admin/invite-codes.pdf", methods=["GET"])
@admin_api
def admin_invite_codes_pdf():
    """Export all unused invite codes visible to the current admin as a PDF list."""
    db = get_db()
    flt = {"used_at": None}
    if not _has_full_read_access():
        flt["school"] = admin_school(db)
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                rows = []
            else:
                flt["class_name"] = teacher_class
                rows = list(db.invite_codes.find(flt).sort("class_name", 1))
        else:
            rows = list(db.invite_codes.find(flt).sort("class_name", 1))
    else:
        rows = list(db.invite_codes.find(flt).sort("class_name", 1))
    filename = f"einladungscodes-{utcnow().strftime('%Y-%m-%d-%H%M%S-%f')}.pdf"
    return Response(
        _invite_codes_pdf(rows),
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/api/admin/invite-code-limits", methods=["GET"])
@admin_api
def admin_invite_code_limits_get():
    db = get_db()
    school = (request.args.get("school") or "").strip() if _has_full_read_access() else admin_school(db)
    payload = {
        "school": school,
        "school_limit": school_license_limit(db, school),
        "current": invite_code_quota_payload(db, school),
        "can_edit": is_dev_session(),
    }
    return jsonify(payload)


@app.route("/api/admin/invite-code-limits", methods=["POST"])
@admin_write_api
def admin_invite_code_limits_post():
    if not is_dev_session():
        return jsonify(error="forbidden"), 403
    data = request.get_json(silent=True) or {}
    school = (data.get("school") or "").strip()
    if len(school) > 120:
        return jsonify(error="invalid_school"), 400
    try:
        limit = max(0, int(data.get("school_limit") or data.get("limit") or 0))
    except (TypeError, ValueError):
        return jsonify(error="invalid_limit"), 400
    db = get_db()
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    set_school_license_limit(db, school, limit)
    return jsonify(
        ok=True,
        school=school,
        school_limit=limit,
        current=invite_code_quota_payload(db, school),
    )


@app.route("/api/admin/invite-codes", methods=["POST"])
@admin_write_api
def admin_invite_create():
    data = request.get_json(silent=True) or {}
    school = (data.get("school") or "").strip()
    class_name = normalize_class_name(data.get("class_name"))
    role = (data.get("role") or "user").strip()
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        return jsonify(error="invalid_count", min=1, max=100), 400
    if count < 1 or count > 100:
        return jsonify(error="invalid_count", min=1, max=100), 400
    if role not in ROLES:
        return jsonify(error="invalid_role"), 400
    if class_name is None:
        return jsonify(error="invalid_class"), 400

    db = get_db()
    if not is_dev_session():
        school = admin_school(db)
        if role_rank(role) >= role_rank(session.get("role")):
            return jsonify(error="forbidden"), 403
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class:
                return jsonify(error="forbidden"), 403
            if role != "user":
                return jsonify(error="forbidden"), 403
            class_name = teacher_class
    quota = invite_code_quota_payload(db, school)
    if quota["limit"] > 0 and count > quota["remaining"]:
        return jsonify(error="code_limit", requested=count, **quota), 429
    class_name = class_name_for_role(role, class_name)
    if class_name is None:
        return jsonify(error="invalid_class"), 400
    if len(school) > 120:
        return jsonify(error="invalid_school"), 400
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    uid = session["user_id"]
    creator_role = session.get("role", "user")
    codes = []
    for _ in range(count):
        for _ in range(12):
            code = secrets.token_hex(6)
            try:
                db.invite_codes.insert_one({
                    "_id": code,
                    "created_by": oid(uid),
                    "created_by_role": creator_role,
                    "school": school,
                    "class_name": class_name,
                    "role": role,
                    "created_at": utcnow(),
                    "used_at": None,
                })
                codes.append(code)
                break
            except DuplicateKeyError:
                continue
        else:
            if codes:
                db.invite_codes.delete_many({"_id": {"$in": codes}})
            return jsonify(error="generate"), 500
    return jsonify(
        code=codes[0],
        codes=codes,
        count=len(codes),
        created_by=uid,
        school=school,
        class_name=class_name,
        role=role,
    )


@app.route("/api/admin/invite-codes/<code>", methods=["DELETE"])
@admin_write_api
def admin_invite_delete(code):
    code = (code or "").strip()
    if not code:
        return jsonify(error="bad_invite"), 400
    db = get_db()
    row = db.invite_codes.find_one(
        {"_id": code, "used_at": None},
        {"school": 1, "class_name": 1, "role": 1},
    )
    if not row:
        return jsonify(error="bad_invite"), 404
    target_role = row["role"] if row.get("role") in ROLES else "user"
    if not is_dev_session():
        if (row.get("school") or "") != admin_school(db):
            return jsonify(error="bad_invite"), 404
        if role_rank(target_role) >= role_rank(session.get("role")):
            return jsonify(error="forbidden"), 403
        if session.get("role") == "teacher":
            teacher_class = teacher_class_for_session(db)
            if not teacher_class or (row.get("class_name") or "") != teacher_class:
                return jsonify(error="bad_invite"), 404
            if target_role != "user":
                return jsonify(error="forbidden"), 403
    db.invite_codes.delete_one({"_id": code, "used_at": None})
    return jsonify(ok=True)


@app.route("/api/chat/rooms", methods=["GET"])
@login_required_api
def chat_rooms():
    db = get_db()
    uid = session["user_id"]
    rooms = []
    creatable = []
    for base_subject in CHAT_SUBJECT_ORDER:
        if not user_may_access_subject(db, uid, base_subject):
            continue
        room_keys = sorted(
            db.chat_presence.distinct(
                "subject",
                {"$or": [
                    {"subject": base_subject},
                    {"subject": {"$regex": f"^{re.escape(base_subject)}:"}},
                ]},
            )
        )
        viewer_lv = _user_level_for_subject(db, uid, base_subject)
        viewer_role = _user_role_for_chat(db, uid)
        if viewer_lv == "pro" or viewer_role in ("teacher", "admin", "dev"):
            creatable.append({"subject": base_subject, "label": CHAT_SUBJECT_LABELS[base_subject]})
        for room_key in room_keys:
            verified_col = CHAT_VERIFIED_COLUMN[base_subject]
            presence_rows = list(db.chat_presence.find({"subject": room_key}))
            member_user_ids = [
                p["user_id"] for p in presence_rows if p.get("user_id") is not None
            ]
            member_users = {
                u["_id"]: u
                for u in db.users.find(
                    {"_id": {"$in": member_user_ids}},
                    {verified_col: 1, "role": 1},
                )
            }
            members = []
            for p in presence_rows:
                u = member_users.get(p.get("user_id"))
                members.append({
                    "username": p.get("username"),
                    "level": p.get("level"),
                    "verified": (u.get(verified_col) if u else 0) or 0,
                    "role": (u.get("role") if u and u.get("role") else "user"),
                })
            members.sort(key=lambda m: (m["username"] or "").lower())
            you_in = any(
                p.get("user_id") == oid(uid) for p in presence_rows
            )
            appointment_row = db.chat_appointments.find_one(
                {"_id": room_key},
                {"appointment": 1, "location": 1, "started": 1},
            )
            count_total = len(members)
            if count_total == 0:
                _delete_chat_room_if_empty(db, room_key)
                continue
            non_pro_n = sum(1 for m in members if m["level"] != "pro")
            pro_n = sum(1 for m in members if m["level"] == "pro")
            if pro_n == 0:
                db.chat_presence.delete_many({"subject": room_key})
                _delete_chat_room_if_empty(db, room_key)
                continue
            has_pro = pro_n >= 1
            locked = bool(appointment_row and appointment_row.get("started") and not you_in)
            if viewer_lv == "pro" or viewer_role in ("teacher", "admin", "dev"):
                can_join = not locked
                join_block = "started" if locked else None
                full = False
            else:
                slot_free = non_pro_n < CHAT_MAX_USERS
                can_join = (you_in or (has_pro and slot_free and not locked))
                if you_in:
                    join_block = None
                elif locked:
                    join_block = "started"
                elif not has_pro:
                    join_block = "need_pro"
                elif not slot_free:
                    join_block = "full"
                else:
                    join_block = None
                full = not can_join
            rooms.append(
                {
                    "subject": room_key,
                    "base_subject": base_subject,
                    "label": chat_room_label(room_key),
                    "count": count_total,
                    "count_non_pro": non_pro_n,
                    "count_pro": pro_n,
                    "has_pro": has_pro,
                    "max": CHAT_MAX_USERS,
                    "full": full,
                    "can_join": can_join,
                    "join_block": join_block,
                    "you_in": you_in,
                    "appointment": appointment_row.get("appointment") if appointment_row else None,
                    "location": appointment_row.get("location") if appointment_row else None,
                    "started": bool(appointment_row.get("started")) if appointment_row else False,
                    "members": [
                        {
                            "username": m["username"],
                            "level": m["level"],
                            "pro_verified": m["level"] == "pro"
                            and (bool(m["verified"]) or m["role"] in ("teacher", "admin", "dev")),
                        }
                        for m in members
                    ],
                }
            )
    return jsonify(rooms=rooms, creatable=creatable)


@app.route("/api/chat/appointment", methods=["GET"])
@login_required_api
def chat_appointment_get():
    room_key, base_subject = chat_room_key(request.args.get("subject"))
    if not room_key:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, base_subject):
        return jsonify(error="invalid_subject"), 400
    row = db.chat_appointments.find_one({"_id": room_key})
    if not row:
        return jsonify(appointment=None)

    is_pro = _user_level_for_subject(db, uid, base_subject) == "pro"
    your_rating = None
    rating_count = None
    rating_avg = None
    ratings = None
    if is_pro:
        your_rating = db.chat_ratings.find_one(
            {"subject": room_key, "user_id": oid(uid)},
            {"rating": 1, "comment": 1},
        )
        rating_rows = list(
            db.chat_ratings.find(
                {"subject": room_key},
                {"user_id": 1, "rating": 1, "comment": 1, "created_at": 1},
            ).sort("created_at", 1)
        )
        rating_count = len(rating_rows)
        rating_avg = (
            sum(r["rating"] for r in rating_rows) / rating_count
            if rating_count
            else None
        )
        rater_ids = [r["user_id"] for r in rating_rows]
        rater_users = {
            u["_id"]: u
            for u in db.users.find({"_id": {"$in": rater_ids}}, {"username": 1})
        }
        ratings = []
        for r in rating_rows:
            u = rater_users.get(r["user_id"])
            if u is None:
                continue
            ratings.append({
                "username": u["username"],
                "rating": int(r["rating"]),
                "comment": (r.get("comment") or "").strip(),
            })
    return jsonify(
        appointment=row.get("appointment"),
        location=row.get("location"),
        created_at=row.get("created_at"),
        started=bool(row.get("started")),
        started_at=row.get("started_at"),
        ended=bool(row.get("ended")),
        ended_at=row.get("ended_at"),
        your_rating={
            "rating": your_rating["rating"],
            "comment": your_rating.get("comment"),
        } if your_rating else None,
        rating_count=rating_count,
        rating_avg=rating_avg,
        ratings=ratings,
    )


@app.route("/api/chat/appointment", methods=["POST"])
@login_required_api
def chat_appointment_post():
    data = request.get_json(silent=True) or {}
    room_key, base_subject = chat_room_key(data.get("subject"))
    appointment = _normalize_appointment_datetime(data.get("appointment"))
    location = _normalize_appointment_location(data.get("location"))
    if not room_key:
        return jsonify(error="invalid_subject"), 400
    if data.get("appointment") is None or not str(data.get("appointment")).strip():
        return jsonify(error="empty"), 400
    if not appointment:
        return jsonify(error="invalid_datetime"), 400
    if data.get("location") is None or not str(data.get("location")).strip():
        return jsonify(error="empty_location"), 400
    if not location:
        return jsonify(error="invalid_location"), 400

    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, base_subject):
        return jsonify(error="invalid_subject"), 400
    level = _user_level_for_subject(db, uid, base_subject)
    if level != "pro":
        return jsonify(error="permission"), 403

    now = utcnow()
    db.chat_appointments.update_one(
        {"_id": room_key},
        {
            "$set": {
                "appointment": appointment,
                "location": location,
                "created_by": oid(uid),
                "updated_at": now,
                "started": 0,
                "started_at": None,
                "ended": 0,
                "ended_at": None,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return jsonify(ok=True)


@app.route("/api/chat/appointment/start", methods=["POST"])
@login_required_api
def chat_appointment_start():
    data = request.get_json(silent=True) or {}
    room_key, base_subject = chat_room_key(data.get("subject"))
    if not room_key:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, base_subject):
        return jsonify(error="invalid_subject"), 400
    level = _user_level_for_subject(db, uid, base_subject)
    if level != "pro":
        return jsonify(error="permission"), 403
    row = db.chat_appointments.find_one(
        {"_id": room_key}, {"started": 1, "ended": 1}
    )
    if not row:
        return jsonify(error="no_appointment"), 400
    if row.get("ended"):
        return jsonify(error="already_ended"), 400
    if row.get("started"):
        return jsonify(ok=True)
    now = utcnow()
    db.chat_appointments.update_one(
        {"_id": room_key},
        {"$set": {"started": 1, "started_at": now, "updated_at": now}},
    )
    return jsonify(ok=True)


@app.route("/api/chat/appointment/end", methods=["POST"])
@login_required_api
def chat_appointment_end():
    data = request.get_json(silent=True) or {}
    room_key, base_subject = chat_room_key(data.get("subject"))
    if not room_key:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, base_subject):
        return jsonify(error="invalid_subject"), 400
    level = _user_level_for_subject(db, uid, base_subject)
    if level != "pro":
        return jsonify(error="permission"), 403
    row = db.chat_appointments.find_one(
        {"_id": room_key}, {"started": 1, "ended": 1}
    )
    if not row:
        return jsonify(error="no_appointment"), 400
    if row.get("ended"):
        return jsonify(ok=True)
    if not row.get("started"):
        return jsonify(error="not_started"), 400
    now = utcnow()
    db.chat_appointments.update_one(
        {"_id": room_key},
        {"$set": {"ended": 1, "ended_at": now, "updated_at": now}},
    )
    db.chat_messages.delete_many({"subject": room_key})
    return jsonify(ok=True, cleared=True)


@app.route("/api/chat/appointment/rate", methods=["POST"])
@login_required_api
def chat_appointment_rate():
    data = request.get_json(silent=True) or {}
    room_key, base_subject = chat_room_key(data.get("subject"))
    if not room_key:
        return jsonify(error="invalid_subject"), 400
    try:
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return jsonify(error="invalid_rating"), 400
    if rating < 1 or rating > 5:
        return jsonify(error="invalid_rating"), 400
    comment = (data.get("comment") or "").strip()
    if rating < 4 and not comment:
        return jsonify(error="need_comment"), 400
    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, base_subject):
        return jsonify(error="invalid_subject"), 400
    level = _user_level_for_subject(db, uid, base_subject)
    if level != "pro":
        return jsonify(error="permission"), 403
    appointment = db.chat_appointments.find_one(
        {"_id": room_key}, {"ended": 1}
    )
    if not appointment or not appointment.get("ended"):
        return jsonify(error="not_ended"), 400
    in_room = db.chat_presence.find_one(
        {"subject": room_key, "user_id": oid(uid)}, {"_id": 1}
    )
    if not in_room:
        return jsonify(error="not_in_room"), 403
    db.chat_ratings.update_one(
        {"subject": room_key, "user_id": oid(uid)},
        {"$set": {"rating": rating, "comment": comment, "created_at": utcnow()}},
        upsert=True,
    )
    return jsonify(ok=True)


@app.route("/api/chat/join", methods=["POST"])
@login_required_api
def chat_join():
    data = request.get_json(silent=True) or {}
    subject = chat_subject_key(data.get("subject"))
    if not subject:
        return jsonify(error="invalid_subject"), 400

    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, subject):
        return jsonify(error="invalid_subject"), 400
    uname = session["username"]
    lvl = _user_level_for_subject(db, uid, subject)
    role = _user_role_for_chat(db, uid)

    row = db.chat_presence.find_one(
        {"subject": subject, "user_id": oid(uid)}, {"_id": 1}
    )
    if row:
        db.chat_presence.update_one(
            {"subject": subject, "user_id": oid(uid)},
            {"$set": {"last_seen": utcnow(), "username": uname, "level": lvl}},
        )
        return jsonify(ok=True, you_in=True)

    appointment_row = db.chat_appointments.find_one(
        {"_id": subject}, {"started": 1}
    )
    if appointment_row and appointment_row.get("started") and role not in ("teacher", "admin", "dev"):
        return jsonify(error="room_closed"), 403

    if role not in ("teacher", "admin", "dev") and lvl != "pro":
        if _chat_presence_pro_count(db, subject) < 1:
            return jsonify(error="need_pro"), 403
        if _chat_presence_non_pro_count(db, subject) >= CHAT_MAX_USERS:
            return jsonify(error="full", max=CHAT_MAX_USERS), 409

    db.chat_presence.insert_one({
        "subject": subject,
        "user_id": oid(uid),
        "username": uname,
        "level": lvl,
        "last_seen": utcnow(),
    })
    return jsonify(ok=True, you_in=True)


@app.route("/api/chat/leave", methods=["POST"])
@login_required_api
def chat_leave():
    data = request.get_json(silent=True) or {}
    subject = chat_subject_key(data.get("subject"))
    if not subject:
        return jsonify(error="invalid_subject"), 400
    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, subject):
        return jsonify(error="invalid_subject"), 400
    prow = db.chat_presence.find_one(
        {"subject": subject, "user_id": oid(uid)}, {"level": 1}
    )
    was_pro = prow is not None and prow.get("level") == "pro"
    db.chat_presence.delete_one({"subject": subject, "user_id": oid(uid)})
    if was_pro:
        _purge_chat_non_pros_if_no_pro(db, subject)
    _delete_chat_room_if_empty(db, subject)
    return jsonify(ok=True)


@app.route("/api/chat/messages", methods=["GET"])
@login_required_api
def chat_messages():
    subject = chat_subject_key(request.args.get("subject"))
    if not subject:
        return jsonify(error="invalid_subject"), 400
    since = oid(request.args.get("since"))

    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, subject):
        return jsonify(error="invalid_subject"), 400
    level_col = CHAT_LEVEL_COLUMN[subject]
    verified_col = CHAT_VERIFIED_COLUMN[subject]
    in_room = db.chat_presence.find_one(
        {"subject": subject, "user_id": oid(uid)}, {"_id": 1}
    )
    if not in_room:
        return jsonify(error="not_in_room"), 403
    appointment_row = db.chat_appointments.find_one(
        {"_id": subject}, {"ended": 1}
    )
    if appointment_row and appointment_row.get("ended"):
        return jsonify(error="appointment_ended"), 400
    if not _chat_may_use_room(db, uid, subject):
        db.chat_presence.delete_one({"subject": subject, "user_id": oid(uid)})
        return jsonify(error="need_pro"), 403

    db.chat_presence.update_one(
        {"subject": subject, "user_id": oid(uid)},
        {"$set": {"last_seen": utcnow()}},
    )
    msg_filter = {"subject": subject}
    if since is not None:
        msg_filter["_id"] = {"$gt": since}
    message_rows = list(
        db.chat_messages.find(msg_filter).sort("_id", 1).limit(200)
    )
    sender_ids = [
        m["user_id"] for m in message_rows if m.get("user_id") is not None
    ]
    senders = {
        u["_id"]: u
        for u in db.users.find(
            {"_id": {"$in": sender_ids}},
            {"role": 1, level_col: 1, verified_col: 1},
        )
    }
    messages = []
    for m in message_rows:
        u = senders.get(m.get("user_id"))
        role = (u.get("role") if u and u.get("role") else "user")
        level = (u.get(level_col) if u and u.get(level_col) else "noob")
        pro_verified = (u.get(verified_col) if u else 0) or 0
        messages.append({
            "id": str(m["_id"]),
            "user_id": str(m["user_id"]) if m.get("user_id") is not None else None,
            "username": m.get("username"),
            "role": role,
            "level": level,
            "pro_verified": level == "pro"
            and (bool(pro_verified) or role in ("teacher", "admin", "dev")),
            "body": m.get("body"),
            "created_at": m.get("created_at"),
        })
    return jsonify(messages=messages)


@app.route("/api/chat/send", methods=["POST"])
@login_required_api
def chat_send():
    data = request.get_json(silent=True) or {}
    subject = chat_subject_key(data.get("subject"))
    body = (data.get("body") or "").strip()
    if not subject:
        return jsonify(error="invalid_subject"), 400
    if not body:
        return jsonify(error="empty"), 400
    body = body[:CHAT_BODY_MAX]

    db = get_db()
    uid = session["user_id"]
    if not user_may_access_subject(db, uid, subject):
        return jsonify(error="invalid_subject"), 400
    uname = session["username"]

    in_room = db.chat_presence.find_one(
        {"subject": subject, "user_id": oid(uid)}, {"_id": 1}
    )
    if not in_room:
        return jsonify(error="not_in_room"), 403
    appointment_row = db.chat_appointments.find_one(
        {"_id": subject}, {"ended": 1}
    )
    if appointment_row and appointment_row.get("ended"):
        return jsonify(error="appointment_ended"), 400
    if not _chat_may_use_room(db, uid, subject):
        db.chat_presence.delete_one({"subject": subject, "user_id": oid(uid)})
        return jsonify(error="need_pro"), 403

    db.chat_presence.update_one(
        {"subject": subject, "user_id": oid(uid)},
        {"$set": {"last_seen": utcnow()}},
    )
    db.chat_messages.insert_one({
        "subject": subject,
        "user_id": oid(uid),
        "username": uname,
        "body": body,
        "created_at": utcnow(),
    })
    return jsonify(ok=True)


@app.route("/api/chat/report-message", methods=["POST"])
@login_required_api
def chat_report_message():
    data = request.get_json(silent=True) or {}
    message_id = oid(data.get("message_id"))
    if message_id is None:
        return jsonify(error="invalid_message"), 400
    reason = (data.get("reason") or "").strip()
    if len(reason) > 300:
        return jsonify(error="reason_too_long"), 400

    db = get_db()
    uid = session["user_id"]
    msg = db.chat_messages.find_one(
        {"_id": message_id},
        {"subject": 1, "user_id": 1, "username": 1, "body": 1},
    )
    reported = None
    if msg is not None and msg.get("user_id") is not None:
        reported = db.users.find_one(
            {"_id": msg["user_id"]},
            {"school": 1, "class_name": 1, "role": 1},
        )
    if not msg or reported is None:
        return jsonify(error="message_not_found"), 404
    if msg["user_id"] == oid(uid):
        return jsonify(error="own_message"), 400
    if not user_may_access_subject(db, uid, msg["subject"]):
        return jsonify(error="message_not_found"), 404
    in_room = db.chat_presence.find_one(
        {"subject": msg["subject"], "user_id": oid(uid)}, {"_id": 1}
    )
    if not in_room:
        return jsonify(error="not_in_room"), 403

    reporter = db.users.find_one({"_id": oid(uid)}, {"username": 1})
    reported_role = reported.get("role") if reported.get("role") in ROLES else "user"
    try:
        db.chat_message_reports.insert_one({
            "message_id": message_id,
            "subject": msg["subject"],
            "reported_user_id": msg["user_id"],
            "reported_username": msg.get("username"),
            "reported_school": reported.get("school") or "",
            "reported_class_name": reported.get("class_name") or "",
            "reported_role": reported_role,
            "reporter_user_id": oid(uid),
            "reporter_username": reporter["username"] if reporter else session.get("username", ""),
            "body": msg.get("body"),
            "reason": reason,
            "created_at": utcnow(),
            "resolved_at": None,
        })
    except DuplicateKeyError:
        return jsonify(error="already_reported"), 409
    return jsonify(ok=True)


@app.route("/register", methods=["GET", "POST"])
def register():
    return redirect("/login.html?flash=register_disabled")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect("/dashboard.html")

    if request.method == "GET":
        return redirect("/login.html")

    username_input = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    db = get_db()
    row = db.users.find_one(
        {"username": {"$regex": "^" + re.escape(username_input) + "$", "$options": "i"}},
        {"password_hash": 1, "role": 1, "school": 1, "banned": 1, "username": 1},
    )

    if row is None or not check_password_hash(row["password_hash"], password):
        return redirect("/login.html?flash=invalid")
    if row.get("banned"):
        msg = banned_message_for_user(db, row["_id"])
        q = urlencode({"flash": "banned", "flash_msg": msg})
        return redirect(f"/login.html?{q}")

    session.clear()
    session["user_id"] = str(row["_id"])
    session["username"] = row["username"]
    r = row.get("role")
    session["role"] = r if r in ROLES else "user"
    session["school"] = row.get("school") or ""

    next_url = (request.form.get("next") or request.args.get("next") or "").strip()
    if next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect("/dashboard.html")


def _public_user_payload(db, user_id):
    row = db.users.find_one({"_id": oid(user_id)})
    if row is None:
        return None
    role = row["role"] if row.get("role") in ROLES else "user"
    grade = class_grade_number(row.get("class_name"))
    subjects = [
        {
            "key": subject,
            "label": CHAT_SUBJECT_LABELS[subject],
            "level": row.get(CHAT_LEVEL_COLUMN[subject]),
            "visibility": subject_visibility(grade, subject),
        }
        for subject in CHAT_SUBJECT_ORDER
    ]
    return {
        "user_id": str(row["_id"]),
        "username": row["username"],
        "display_name": row.get("display_name") or "",
        "onboarded": bool(row.get("onboarded")),
        "grade": grade,
        "subjects": subjects,
        "role": role,
        "school": row.get("school") or "",
        "class_name": row.get("class_name") or "",
        "level_german": row.get("level_german"),
        "level_math": row.get("level_math"),
        "level_english": row.get("level_english"),
        "level_biology": row.get("level_biology"),
        "level_pgw": row.get("level_pgw"),
        "level_spanish": row.get("level_spanish"),
        "level_art": row.get("level_art"),
        "pro_verified_german": bool(row.get("pro_verified_german")),
        "pro_verified_math": bool(row.get("pro_verified_math")),
        "pro_verified_english": bool(row.get("pro_verified_english")),
        "pro_verified_biology": bool(row.get("pro_verified_biology")),
        "pro_verified_pgw": bool(row.get("pro_verified_pgw")),
        "pro_verified_spanish": bool(row.get("pro_verified_spanish")),
        "pro_verified_art": bool(row.get("pro_verified_art")),
        "contact_email": row.get("contact_email") or "",
        "notify_laden_email": bool(row.get("notify_laden_email")),
        "avatar_url": row.get("avatar_url") or "",
        "iserv_email": row.get("iserv_email") or "",
        "school_logo_url": school_logo_url_for(db, row.get("school") or ""),
        "must_change_password": bool(row.get("must_change_password")),
    }


def _erase_user_account(db, user_id):
    """Recht auf Löschung (Art. 17 DSGVO). Loescht das Konto und alles, was
    nur dem Nutzer selbst gehoert (Praesenz, Bewertungen, Lernorte, Zeugnis-
    Punkte, API-Tokens). Chat-Nachrichten, Laden-Kaeufe und Meldungen werden
    anonymisiert statt geloescht, damit gemeinsame Chatverlaeufe und die
    Kaeufer-Buchhaltung anderer Nutzer:innen erhalten bleiben."""
    uid = oid(user_id)
    db.chat_messages.update_many(
        {"user_id": uid},
        {"$set": {"user_id": None, "username": "Gelöschtes Konto"}},
    )
    db.laden_purchases.update_many(
        {"user_id": uid},
        {"$set": {"user_id": None, "username": "Gelöschtes Konto"}},
    )
    db.chat_message_reports.update_many(
        {"reporter_user_id": uid},
        {"$set": {"reporter_user_id": None, "reporter_username": "Gelöschtes Konto"}},
    )
    db.chat_message_reports.update_many(
        {"reported_user_id": uid},
        {"$set": {"reported_user_id": None, "reported_username": "Gelöschtes Konto"}},
    )
    db.invite_codes.update_many({"created_by": uid}, {"$set": {"created_by": None}})
    db.chat_presence.delete_many({"user_id": uid})
    db.chat_ratings.delete_many({"user_id": uid})
    db.admin_subject_scores.delete_many({"user_id": uid})
    db.learning_places.delete_many({"user_id": uid})
    db.api_tokens.delete_many({"user_id": uid})
    db.users.delete_one({"_id": uid})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or request.form
    username_input = (data.get("username") or "").strip()
    password = data.get("password") or ""

    db = get_db()
    row = db.users.find_one(
        {"username": {"$regex": "^" + re.escape(username_input) + "$", "$options": "i"}},
        {"password_hash": 1, "role": 1, "banned": 1},
    )
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify(error="invalid"), 401
    if row.get("banned"):
        msg = banned_message_for_user(db, row["_id"])
        return jsonify(error="banned", message=msg), 403

    token = secrets.token_urlsafe(32)
    db.api_tokens.insert_one({"_id": token, "user_id": row["_id"]})
    user = _public_user_payload(db, row["_id"])
    return jsonify(ok=True, token=token, user=user)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login.html?flash=logout")


@app.route("/api/logout", methods=["POST"])
@login_required_api
def api_logout():
    token = getattr(g, "api_token", None)
    if token:
        db = get_db()
        db.api_tokens.delete_one({"_id": token})
    session.clear()
    return jsonify(ok=True)


def _valid_contact_email(raw):
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > 254 or "@" not in s or " " in s:
        return None
    return s


def _valid_optional_url(raw, max_len=1000):
    s = (raw or "").strip()
    if not s:
        return ""
    if len(s) > max_len:
        return None
    if not (s.startswith("http://") or s.startswith("https://")):
        return None
    return s


def _valid_avatar_value(raw):
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("/uploads/avatars/"):
        return s if len(s) <= 300 else None
    if len(s) > 4000:
        return None
    if s.startswith("data:image/svg+xml"):
        return s
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return None


def _save_avatar_upload(file_storage):
    if file_storage is None or not file_storage.filename:
        return ""
    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in AVATAR_ALLOWED_EXTENSIONS:
        return None
    data = file_storage.read(AVATAR_MAX_BYTES + 1)
    if not data or len(data) > AVATAR_MAX_BYTES:
        return None
    AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_urlsafe(18)}.{ext}"
    path = AVATAR_UPLOAD_DIR / filename
    path.write_bytes(data)
    return f"/uploads/avatars/{filename}"


@app.route("/profile", methods=["POST"])
@login_required
def profile_update():
    levels = parse_subject_levels(request.form)
    if levels is None:
        return redirect("/settings.html?flash=levels")
    lg, lm, le, lb, lp, ls, la = levels
    raw_mail = (request.form.get("contact_email") or "").strip()
    contact_email = _valid_contact_email(raw_mail)
    if raw_mail and contact_email is None:
        return redirect("/settings.html?flash=bad_contact_email")
    want_notify = request.form.get("notify_laden_email") == "1"
    if want_notify and not contact_email:
        return redirect("/settings.html?flash=notify_no_email")
    notify_val = 1 if (want_notify and contact_email) else 0
    email_val = contact_email
    school = _normalize_school_name(request.form.get("school"))
    if school is None:
        return redirect("/settings.html?flash=invalid_school")

    cur_pwd = request.form.get("current_password") or ""
    new_pwd = request.form.get("new_password") or ""
    new_pwd2 = request.form.get("new_password_confirm") or ""
    pwd_change = bool(cur_pwd or new_pwd or new_pwd2)
    if pwd_change:
        if not cur_pwd or not new_pwd or not new_pwd2:
            return redirect("/settings.html?flash=pwd_incomplete")
        if len(new_pwd) < 6:
            return redirect("/settings.html?flash=shortpass")
        if new_pwd != new_pwd2:
            return redirect("/settings.html?flash=mismatch")

    db = get_db()
    uid = oid(session["user_id"])
    level_row = db.users.find_one(
        {"_id": uid},
        {
            **{col: 1 for col in CHAT_LEVEL_COLUMN.values()},
            **{col: 1 for col in CHAT_VERIFIED_COLUMN.values()},
            "avatar_url": 1, "school": 1, "class_name": 1,
        },
    )
    if level_row is None:
        return redirect("/login.html?flash=needlogin")
    try:
        level_quiz_answers = json.loads(request.form.get("level_quiz_answers") or "{}")
    except (TypeError, ValueError):
        level_quiz_answers = None
    quiz_error = _validate_level_increase_quiz(db, level_row, levels, level_quiz_answers)
    if quiz_error:
        return redirect(f"/settings.html?flash={quiz_error}")
    avatar_url = level_row.get("avatar_url") or ""
    uploaded_avatar = _save_avatar_upload(request.files.get("avatar_upload"))
    if uploaded_avatar is None:
        return redirect("/settings.html?flash=bad_avatar")
    if uploaded_avatar:
        avatar_url = uploaded_avatar
    elif request.form.get("avatar_choice") == "builder":
        built_avatar = _valid_avatar_value(request.form.get("avatar_data"))
        if built_avatar is None:
            return redirect("/settings.html?flash=bad_avatar")
        avatar_url = built_avatar
    vg, vm, ve, vb, vp, vs, va = next_pro_verification_values(level_row, levels)
    if school != (level_row.get("school") or "") and not school_license_has_free_slot(db, school):
        return redirect("/settings.html?flash=code_limit")
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    update_fields = {
        "level_german": lg, "level_math": lm, "level_english": le,
        "level_biology": lb, "level_pgw": lp, "level_spanish": ls, "level_art": la,
        "pro_verified_german": vg, "pro_verified_math": vm, "pro_verified_english": ve,
        "pro_verified_biology": vb, "pro_verified_pgw": vp, "pro_verified_spanish": vs,
        "pro_verified_art": va,
        "contact_email": email_val, "notify_laden_email": notify_val,
        "school": school, "avatar_url": avatar_url,
    }
    if pwd_change:
        row = db.users.find_one({"_id": uid}, {"password_hash": 1})
        if row is None or not check_password_hash(row["password_hash"], cur_pwd):
            return redirect("/settings.html?flash=pwd_current_wrong")
        update_fields["password_hash"] = generate_password_hash(new_pwd)
        update_fields["must_change_password"] = False
    db.users.update_one({"_id": uid}, {"$set": update_fields})
    session["school"] = school or ""
    return redirect("/settings.html?flash=saved")


@app.route("/api/profile", methods=["POST"])
@login_required_api
def api_profile_update():
    data = request.get_json(silent=True) or {}
    levels = parse_subject_levels(data)
    if levels is None:
        return jsonify(error="levels"), 400
    lg, lm, le, lb, lp, ls, la = levels
    raw_mail = (data.get("contact_email") or "").strip()
    contact_email = _valid_contact_email(raw_mail)
    if raw_mail and contact_email is None:
        return jsonify(error="bad_contact_email"), 400
    want_notify = data.get("notify_laden_email") in (True, "true", "1", 1)
    if want_notify and not contact_email:
        return jsonify(error="notify_no_email"), 400
    notify_val = 1 if (want_notify and contact_email) else 0
    avatar_url = _valid_avatar_value(data.get("avatar_url"))
    if avatar_url is None:
        return jsonify(error="invalid_avatar_url"), 400
    school = _normalize_school_name(data.get("school"))
    if school is None:
        return jsonify(error="invalid_school"), 400
    raw_iserv = (data.get("iserv_email") or "").strip()
    iserv_email = _valid_contact_email(raw_iserv)
    if raw_iserv and iserv_email is None:
        return jsonify(error="bad_iserv_email"), 400

    cur_pwd = data.get("current_password") or ""
    new_pwd = data.get("new_password") or ""
    new_pwd2 = data.get("new_password_confirm") or ""
    pwd_change = bool(cur_pwd or new_pwd or new_pwd2)
    if pwd_change:
        if not cur_pwd or not new_pwd or not new_pwd2:
            return jsonify(error="pwd_incomplete"), 400
        if len(new_pwd) < 6:
            return jsonify(error="shortpass"), 400
        if new_pwd != new_pwd2:
            return jsonify(error="mismatch"), 400

    db = get_db()
    uid = oid(session["user_id"])
    level_row = db.users.find_one(
        {"_id": uid},
        {
            **{col: 1 for col in CHAT_LEVEL_COLUMN.values()},
            **{col: 1 for col in CHAT_VERIFIED_COLUMN.values()},
            "school": 1, "class_name": 1,
        },
    )
    if level_row is None:
        return jsonify(error="auth"), 401
    quiz_error = _validate_level_increase_quiz(
        db, level_row, levels, data.get("level_quiz_answers")
    )
    if quiz_error:
        return jsonify(error=quiz_error), 400
    vg, vm, ve, vb, vp, vs, va = next_pro_verification_values(level_row, levels)
    if school != (level_row.get("school") or "") and not school_license_has_free_slot(db, school):
        return jsonify(error="code_limit", **invite_code_quota_payload(db, school)), 429
    if school:
        db.schools.update_one(
            {"_id": school},
            {"$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )
    update_fields = {
        "level_german": lg, "level_math": lm, "level_english": le,
        "level_biology": lb, "level_pgw": lp, "level_spanish": ls, "level_art": la,
        "pro_verified_german": vg, "pro_verified_math": vm, "pro_verified_english": ve,
        "pro_verified_biology": vb, "pro_verified_pgw": vp, "pro_verified_spanish": vs,
        "pro_verified_art": va,
        "contact_email": contact_email, "notify_laden_email": notify_val,
        "school": school, "avatar_url": avatar_url, "iserv_email": iserv_email or "",
    }
    if pwd_change:
        row = db.users.find_one({"_id": uid}, {"password_hash": 1})
        if row is None or not check_password_hash(row["password_hash"], cur_pwd):
            return jsonify(error="pwd_current_wrong"), 400
        update_fields["password_hash"] = generate_password_hash(new_pwd)
        update_fields["must_change_password"] = False
    db.users.update_one({"_id": uid}, {"$set": update_fields})
    session["school"] = school or ""
    return jsonify(ok=True, user=_public_user_payload(db, uid))


@app.route("/api/must-change-password", methods=["POST"])
@login_required_api
def api_must_change_password():
    data = request.get_json(silent=True) or {}
    cur_pwd = data.get("current_password") or ""
    new_pwd = data.get("new_password") or ""
    new_pwd2 = data.get("new_password_confirm") or ""
    if not cur_pwd or not new_pwd or not new_pwd2:
        return jsonify(error="pwd_incomplete"), 400
    if len(new_pwd) < 6:
        return jsonify(error="shortpass"), 400
    if new_pwd != new_pwd2:
        return jsonify(error="mismatch"), 400

    db = get_db()
    uid = oid(session["user_id"])
    row = db.users.find_one({"_id": uid}, {"password_hash": 1})
    if row is None or not check_password_hash(row["password_hash"], cur_pwd):
        return jsonify(error="pwd_current_wrong"), 400
    db.users.update_one(
        {"_id": uid},
        {"$set": {
            "password_hash": generate_password_hash(new_pwd),
            "must_change_password": False,
        }},
    )
    return jsonify(ok=True)


@app.route("/api/learning-places", methods=["GET"])
@login_required_api
def learning_places_list():
    db = get_db()
    current_user_id = oid(session["user_id"])
    school = admin_school(db)
    flt = {"$or": [{"school": school}, {"school": ""}]} if school else {}
    rows = list(
        db.learning_places.find(flt)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(50)
    )
    return jsonify(
        places=[
            {
                "id": str(row["_id"]),
                "username": row.get("username"),
                "school": row.get("school") or "",
                "name": row.get("name"),
                "address": row.get("address") or "",
                "note": row.get("note") or "",
                "created_at": row.get("created_at"),
                "can_edit": row.get("user_id") == current_user_id,
            }
            for row in rows
        ]
    )


@app.route("/api/learning-places", methods=["POST"])
@login_required_api
def learning_places_create():
    data = request.get_json(silent=True) or {}
    name = " ".join((data.get("name") or "").strip().split())
    address = " ".join((data.get("address") or "").strip().split())
    note = (data.get("note") or "").strip()
    if not name or len(name) > 120:
        return jsonify(error="invalid_name"), 400
    if len(address) > 200:
        return jsonify(error="invalid_address"), 400
    if len(note) > 500:
        return jsonify(error="invalid_note"), 400
    db = get_db()
    uid = session["user_id"]
    user = _public_user_payload(db, uid)
    if user is None:
        return jsonify(error="auth"), 401
    school = user["school"] or ""
    db.learning_places.insert_one({
        "user_id": oid(uid),
        "username": user["username"],
        "school": school,
        "name": name,
        "address": address,
        "note": note,
        "created_at": utcnow(),
    })
    return jsonify(ok=True)


@app.route("/api/learning-places/<place_id>", methods=["PUT"])
@login_required_api
def learning_places_update(place_id):
    place_oid = oid(place_id)
    if place_oid is None:
        return jsonify(error="invalid_id"), 400

    data = request.get_json(silent=True) or {}
    name = " ".join((data.get("name") or "").strip().split())
    address = " ".join((data.get("address") or "").strip().split())
    note = (data.get("note") or "").strip()
    if not name or len(name) > 120:
        return jsonify(error="invalid_name"), 400
    if len(address) > 200:
        return jsonify(error="invalid_address"), 400
    if len(note) > 500:
        return jsonify(error="invalid_note"), 400

    result = get_db().learning_places.update_one(
        {"_id": place_oid, "user_id": oid(session["user_id"])},
        {"$set": {
            "name": name,
            "address": address,
            "note": note,
            "updated_at": utcnow(),
        }},
    )
    if not result.matched_count:
        return jsonify(error="not_found"), 404
    return jsonify(ok=True)


@app.route("/api/profile/name", methods=["POST"])
def api_profile_name():
    if not _load_api_auth_context():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or request.form
    name = " ".join((data.get("display_name") or "").split())
    if len(name) < 1 or len(name) > 64:
        return jsonify(error="invalid_name"), 400
    db = get_db()
    db.users.update_one(
        {"_id": oid(session["user_id"])},
        {"$set": {"display_name": name}},
    )
    return jsonify(ok=True, display_name=name)


def _extract_zeugnis(image_bytes, media_type):
    """Liest ein Zeugnisbild per GPT Vision aus.

    Gibt ein Dict {display_name, class_name, school, grades:{fach: note}} zurueck.
    Wirft RuntimeError('no_api_key') bzw. RuntimeError('ai_failed').
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        app.logger.warning("Zeugnis-Auslesung: OPENAI_API_KEY nicht gesetzt.")
        raise RuntimeError("no_api_key")
    app.logger.info(
        "Zeugnis-Auslesung startet (Modell=%s, %d Bytes, %s).",
        ONBOARDING_MODEL, len(image_bytes), media_type,
    )
    try:
        import base64
        import json
        from openai import OpenAI
    except ImportError:
        app.logger.exception("Zeugnis-Auslesung: openai-Paket nicht installiert.")
        raise RuntimeError("ai_failed")

    grade_props = {
        subject: {
            "type": ["number", "null"],
            "description": f"Zeugnisnote (deutsche Skala 1-6) fuer {label}, sonst null.",
        }
        for subject, label in CHAT_SUBJECT_LABELS.items()
    }
    tool = {
        "type": "function",
        "function": {
            "name": "zeugnis_daten",
            "description": "Strukturierte Daten aus einem deutschen Schulzeugnis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "display_name": {
                        "type": ["string", "null"],
                        "description": "Voller Name der Schuelerin/des Schuelers.",
                    },
                    "class_name": {
                        "type": ["string", "null"],
                        "description": "Klasse, z. B. '8a' oder '10'.",
                    },
                    "school": {
                        "type": ["string", "null"],
                        "description": "Name der Schule.",
                    },
                    "grades": {
                        "type": "object",
                        "properties": grade_props,
                    },
                },
                "required": ["grades"],
            },
        },
    }

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        client = OpenAI(api_key=api_key)
        msg = client.chat.completions.create(
            model=ONBOARDING_MODEL,
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "zeugnis_daten"}},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Lies dieses deutsche Schulzeugnis aus. Gib Name, Klasse, "
                                "Schule und die Noten der folgenden Faecher zurueck: "
                                + ", ".join(CHAT_SUBJECT_LABELS.values())
                                + ". Verwende die deutsche Notenskala 1 (sehr gut) bis 6 "
                                "(ungenuegend). Fehlt eine Note oder ein Fach, setze null."
                            ),
                        },
                    ],
                }
            ],
        )
    except Exception:
        app.logger.exception("Zeugnis-Auslesung: OpenAI-Aufruf fehlgeschlagen.")
        raise RuntimeError("ai_failed")

    try:
        for call in msg.choices[0].message.tool_calls or []:
            if call.function.name == "zeugnis_daten":
                data = json.loads(call.function.arguments)
                app.logger.info(
                    "Zeugnis-Auslesung erfolgreich (%d Noten erkannt).",
                    len((data or {}).get("grades") or {}),
                )
                return data
    except (AttributeError, IndexError, ValueError):
        app.logger.exception("Zeugnis-Auslesung: Antwort konnte nicht geparst werden.")
        raise RuntimeError("ai_failed")
    app.logger.error(
        "Zeugnis-Auslesung: kein 'zeugnis_daten'-Tool-Call in der Antwort (finish_reason=%s).",
        getattr(msg.choices[0], "finish_reason", "?"),
    )
    raise RuntimeError("ai_failed")


@app.route("/api/onboarding/zeugnis", methods=["POST"])
def api_onboarding_zeugnis():
    if not _load_api_auth_context():
        return jsonify(error="unauthorized"), 401
    if not request.form.get("consent"):
        return jsonify(error="consent_required"), 400
    f = request.files.get("zeugnis")
    if f is None or not f.filename:
        return jsonify(error="no_file"), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    media_type = ZEUGNIS_ALLOWED_MEDIA.get(ext)
    if media_type is None:
        return jsonify(error="bad_type"), 400
    data = f.read(ZEUGNIS_MAX_BYTES + 1)
    if not data or len(data) > ZEUGNIS_MAX_BYTES:
        return jsonify(error="too_large"), 400

    try:
        extracted = _extract_zeugnis(data, media_type)
    except RuntimeError as exc:
        code = "ai_unavailable" if str(exc) == "no_api_key" else "ai_failed"
        status = 503 if code == "ai_unavailable" else 502
        return jsonify(error=code), status

    grades = (extracted or {}).get("grades") or {}
    levels = {}
    for subject in CHAT_SUBJECT_ORDER:
        level = grade_to_level(grades.get(subject))
        levels[subject] = level or "noob"
    return jsonify(
        ok=True,
        display_name=(extracted.get("display_name") or "").strip(),
        class_name=normalize_class_name(extracted.get("class_name")) or "",
        school=_normalize_school_name(extracted.get("school")) or "",
        grades={s: grades.get(s) for s in CHAT_SUBJECT_ORDER},
        levels=levels,
    )


@app.route("/api/quiz-questions", methods=["GET"])
@login_required_api
def api_quiz_questions():
    subjects = [s.strip() for s in (request.args.get("subjects") or "").split(",") if s.strip() in CHAT_SUBJECTS]
    if not subjects:
        return jsonify(error="invalid_subjects"), 400
    db = get_db()
    onboarding_mode = request.args.get("mode") == "onboarding"
    if onboarding_mode:
        school = _normalize_school_name(request.args.get("school"))
        class_name = normalize_class_name(request.args.get("class_name"))
        if school is None or class_name is None:
            return jsonify(error="invalid_profile"), 400
    else:
        row = db.users.find_one(
            {"_id": oid(session["user_id"])}, {"school": 1, "class_name": 1}
        )
        school = (row.get("school") if row else "") or ""
        class_name = (row.get("class_name") if row else "") or ""
    out = {}
    question_count = (
        ONBOARDING_QUIZ_QUESTION_COUNT
        if onboarding_mode
        else 5
    )
    for subject in subjects:
        rows = _resolve_quiz_questions(db, school, class_name, subject)[:question_count]
        out[subject] = [{"q": r["question"], "choices": r["choices"]} for r in rows]
    return jsonify(questions=out)


@app.route("/api/onboarding/confirm", methods=["POST"])
def api_onboarding_confirm():
    if not _load_api_auth_context():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    name = " ".join((data.get("display_name") or "").split())
    if len(name) < 1 or len(name) > 64:
        return jsonify(error="invalid_name"), 400
    class_name = normalize_class_name(data.get("class_name"))
    if class_name is None:
        return jsonify(error="invalid_class"), 400
    school = _normalize_school_name(data.get("school"))
    if school is None:
        return jsonify(error="invalid_school"), 400
    levels_in = data.get("levels") or {}
    levels = {}
    for subject in CHAT_SUBJECT_ORDER:
        level = levels_in.get(subject)
        levels[subject] = level if level in LEVELS else "noob"

    db = get_db()
    quiz_answers = data.get("quiz_answers") or {}
    notes = []
    for subject in CHAT_SUBJECT_ORDER:
        claimed = levels[subject]
        if claimed not in ONBOARDING_QUIZ_MIN_CORRECT:
            continue
        answers = quiz_answers.get(subject) if isinstance(quiz_answers, dict) else None
        official = _resolve_quiz_questions(db, school, class_name, subject)[
            :ONBOARDING_QUIZ_QUESTION_COUNT
        ]
        if len(official) != ONBOARDING_QUIZ_QUESTION_COUNT:
            continue
        correct = sum(
            1 for i, row in enumerate(official)
            if isinstance(answers, list)
            and i < len(answers)
            and isinstance(answers[i], int)
            and answers[i] == row["correct"]
        )
        if correct < ONBOARDING_QUIZ_MIN_CORRECT[claimed]:
            downgraded = QUIZ_DOWNGRADE[claimed]
            notes.append(
                f"{CHAT_SUBJECT_LABELS[subject]}: "
                f"{correct}/{ONBOARDING_QUIZ_QUESTION_COUNT} richtig — Stufe von "
                f"{claimed} auf {downgraded} angepasst."
            )
            levels[subject] = downgraded

    update_fields = {CHAT_LEVEL_COLUMN[s]: levels[s] for s in CHAT_SUBJECT_ORDER}
    update_fields.update({
        "display_name": name,
        "class_name": class_name,
        "school": school,
        "onboarded": 1,
    })
    db.users.update_one(
        {"_id": oid(session["user_id"])},
        {"$set": update_fields},
    )
    session["school"] = school
    return jsonify(ok=True, notes=notes, levels=levels)


@app.route("/api/me")
def api_me():
    if not _load_api_auth_context():
        return jsonify({}), 401
    db = get_db()
    user = _public_user_payload(db, session["user_id"])
    if user is None:
        return jsonify({}), 401
    return jsonify(user)


@app.route("/api/account/export", methods=["GET"])
@login_required_api
def api_account_export():
    db = get_db()
    uid = oid(session["user_id"])
    user = _public_user_payload(db, uid)
    if user is None:
        return jsonify(error="auth"), 401

    messages = [
        {"subject": m.get("subject"), "body": m.get("body"), "created_at": m.get("created_at")}
        for m in db.chat_messages.find({"user_id": uid}).sort("created_at", 1)
    ]
    ratings = [
        {
            "subject": r.get("subject"),
            "rating": r.get("rating"),
            "comment": r.get("comment"),
            "created_at": r.get("created_at"),
        }
        for r in db.chat_ratings.find({"user_id": uid})
    ]
    scores = [
        {
            "subject": s.get("subject"),
            "points": s.get("points"),
            "note": s.get("note"),
            "updated_at": s.get("updated_at"),
        }
        for s in db.admin_subject_scores.find({"user_id": uid})
    ]
    places = [
        {
            "name": p.get("name"),
            "address": p.get("address"),
            "note": p.get("note"),
            "created_at": p.get("created_at"),
        }
        for p in db.learning_places.find({"user_id": uid})
    ]
    purchases = [
        {
            "item_title": p.get("item_title"),
            "points_spent": p.get("points_spent"),
            "created_at": p.get("created_at"),
        }
        for p in db.laden_purchases.find({"user_id": uid})
    ]
    reports_filed = [
        {"subject": r.get("subject"), "reason": r.get("reason"), "created_at": r.get("created_at")}
        for r in db.chat_message_reports.find({"reporter_user_id": uid})
    ]

    return jsonify(
        exported_at=utcnow(),
        profile=user,
        chat_messages=messages,
        chat_ratings=ratings,
        subject_scores=scores,
        learning_places=places,
        laden_purchases=purchases,
        reports_filed=reports_filed,
    )


@app.route("/api/account/delete", methods=["POST"])
@login_required_api
def api_account_delete():
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    db = get_db()
    uid = oid(session["user_id"])
    row = db.users.find_one({"_id": uid}, {"password_hash": 1})
    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify(error="pwd_wrong"), 400
    _erase_user_account(db, uid)
    session.clear()
    return jsonify(ok=True)


@app.route("/uploads/avatars/<path:filename>")
def uploaded_avatar(filename):
    return send_from_directory(str(AVATAR_UPLOAD_DIR), filename)


@app.route("/healthz")
def healthz():
    """Health-/Status-Endpoint. Zeigt an, welches DB-Backend aktiv ist:
    "mongodb" (Atlas-Secret gesetzt und erreichbar) oder "local" (Fallback).
    """
    return jsonify({"status": "ok", "db_backend": active_backend()})


from shop import register_shop_routes

register_shop_routes(app, get_db, admin_api, admin_write_api, login_required, login_required_api)

with app.app_context():
    # Best-effort: Indizes beim Start anlegen. Ist MONGODB_URI gesetzt und
    # erreichbar, laeuft das gegen Atlas; sonst gegen den lokalen Fallback-Store
    # (mongomock). Faellt beides aus (z. B. beim Import in Tests/CI), darf der
    # Import nicht hart scheitern. ensure_indexes() ist idempotent.
    try:
        app.logger.info("Datenbank-Backend beim Start: %s", active_backend())
        init_db()
    except Exception as exc:  # pragma: no cover - nur Startup-Robustheit
        if os.environ.get("MONGODB_REQUIRED", "").lower() in ("1", "true", "yes"):
            raise
        app.logger.warning("init_db/ensure_indexes beim Start uebersprungen: %s", exc)


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", "5000")))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)
