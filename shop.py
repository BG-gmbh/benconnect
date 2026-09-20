"""Shop-Modul (Laden): Artikel, Punktekäufe, Lehrer-E-Mail-Benachrichtigungen."""

from datetime import datetime, timezone

from bson import ObjectId
from flask import jsonify, request, send_from_directory, session
from pymongo.errors import DuplicateKeyError

from db_mongo import oid
from mailer import send_smtp_mail, smtp_configured

TITLE_MAX = 200
DESC_MAX = 4000
PRICE_MAX = 120
POINTS_PRICE_MAX = 1_000_000
SCHOOL_MAX = 120
CLASS_MAX = 20

_POINT_SUBJECTS = ("german", "math", "english", "biology", "pgw", "spanish", "art")


def ensure_shop_table(db):
    # Schema-Setup entfällt unter MongoDB – Indizes werden von ensure_indexes()
    # in db_mongo.py angelegt. No-op für Rückwärtskompatibilität.
    pass


def _is_dev():
    return session.get("role") == "dev"


def _has_full_read_access():
    """Wie app.py: Dev und Tester (Read-only) sehen alles."""
    return session.get("role") in ("dev", "tester")


def _is_teacher():
    return session.get("role") == "teacher"


def _session_school(db):
    if "school" in session:
        return session.get("school") or ""
    uid = session.get("user_id")
    if not uid:
        return ""
    row = db.users.find_one({"_id": oid(uid)}, {"school": 1})
    school = (row["school"] if row else "") or ""
    session["school"] = school
    return school


def _session_class(db):
    uid = session.get("user_id")
    if not uid:
        return ""
    row = db.users.find_one({"_id": oid(uid)}, {"class_name": 1})
    return _normalize_class_name(row["class_name"] if row else "") or ""


def _admin_item_school(db, raw_school):
    school = (raw_school or "").strip()
    return school if _is_dev() else _session_school(db)


def _normalize_class_name(raw):
    class_name = "".join((raw or "").strip().split()).lower()
    if len(class_name) > CLASS_MAX:
        return None
    return class_name


def _admin_item_class(db, raw_class):
    if _is_teacher():
        return _session_class(db)
    return _normalize_class_name(raw_class)


def _can_admin_access_school(db, school):
    return _is_dev() or (school or "") == _session_school(db)


def _can_admin_access_item_scope(db, school, class_name):
    if not _can_admin_access_school(db, school):
        return False
    if _is_teacher():
        teacher_class = _session_class(db)
        return bool(teacher_class) and (class_name or "") == teacher_class
    return True


def _user_points_sum(db, user_id):
    res = list(
        db.admin_subject_scores.aggregate(
            [
                {
                    "$match": {
                        "user_id": oid(user_id),
                        "subject": {"$in": list(_POINT_SUBJECTS)},
                    }
                },
                {"$group": {"_id": None, "s": {"$sum": "$points"}}},
            ]
        )
    )
    return int(res[0]["s"]) if res else 0


def _deduct_user_points(db, user_id, amount, actor_user_id):
    """Zieht Punkte von positiven admin_subject_scores-Zeilen ab. actor_user_id für updated_by."""
    remaining = amount
    uid = oid(user_id)
    rows = list(
        db.admin_subject_scores.find(
            {
                "user_id": uid,
                "points": {"$gt": 0},
                "subject": {"$in": list(_POINT_SUBJECTS)},
            }
        ).sort("subject", 1)
    )
    now = datetime.now(timezone.utc)
    actor = oid(actor_user_id)
    for row in rows:
        if remaining <= 0:
            break
        p = int(row["points"])
        take = min(p, remaining)
        newp = p - take
        db.admin_subject_scores.update_one(
            {"user_id": uid, "subject": row["subject"]},
            {"$set": {"points": newp, "updated_at": now, "updated_by": actor}},
        )
        remaining -= take
    return remaining == 0


def _purchase_email_notice(mail_err):
    """Deutschsprachiger Hinweis für die Kauf-Bestätigung (keine internen Codes)."""
    if not mail_err:
        return None
    # Kurz halten: Erfolg („gespeichert“ / Punkte) steht schon im Shop-Dialog.
    mapping = {
        "smtp_not_configured": "Lehrer-E-Mail: SMTP ist noch nicht eingerichtet (.env / README).",
        "no_teachers": "Lehrer-E-Mail: keine Benachrichtigungsadresse hinterlegt (Admin).",
        "no_recipients": "Lehrer-E-Mail: keine gültigen Empfänger.",
        "smtp_no_from": "Lehrer-E-Mail: Absender (SMTP_FROM / SMTP_USER) fehlt.",
        "send_failed": "Lehrer-E-Mail konnte nicht gesendet werden.",
    }
    if mail_err in mapping:
        return mapping[mail_err]
    return "Lehrer-E-Mail konnte nicht gesendet werden."


def _notify_teachers_laden(
    db, student_username, item_title, points_spent, created_at, student_school
):
    seen = set()
    emails = []
    for r in db.teacher_contacts.find({"active": 1}).sort("_id", 1):
        sch = r.get("school") or ""
        if sch.strip() != "" and sch != (student_school or ""):
            continue
        raw = (r.get("email") or "").strip()
        low = raw.lower()
        if raw and "@" in raw and low not in seen:
            seen.add(low)
            emails.append(raw)
    for r in db.users.find(
        {
            "notify_laden_email": 1,
            "school": student_school or "",
            "contact_email": {"$ne": None},
        }
    ):
        raw = (r.get("contact_email") or "").strip()
        low = raw.lower()
        if raw and "@" in raw and low not in seen:
            seen.add(low)
            emails.append(raw)
    if not emails:
        return False, "no_teachers"
    subject = f"Laden: {student_username} hat Punkte ausgegeben"
    body = (
        f"Schüler/in (Nutzername): {student_username}\n"
        f"Artikel: {item_title}\n"
        f"Punkte: {points_spent}\n"
        f"Zeitpunkt: {created_at}\n\n"
        f"(Automatische Nachricht von benconnect.)\n"
    )
    ok, err = send_smtp_mail(emails, subject, body)
    if not ok:
        return False, err or "send_failed"
    return True, None


def _row_to_item(r):
    try:
        pp = int(r["points_price"])
    except (KeyError, TypeError, ValueError):
        pp = 0
    return {
        "id": str(r["_id"]),
        "title": r["title"],
        "description": r["description"] or "",
        "price_hint": r["price_hint"] or "",
        "points_price": pp,
        "school": r["school"] or "",
        "class_name": r["class_name"] or "",
        "sort_order": int(r["sort_order"]),
        "active": bool(r["active"]),
        "updated_at": r["updated_at"],
    }


def register_shop_routes(app, get_db, admin_api, admin_write_api, login_required, login_required_api):
    @app.route("/laden.html")
    @login_required
    def laden_page():
        return send_from_directory(app.static_folder, "laden.html")

    @app.route("/shop.html")
    @login_required
    def shop_page():
        return send_from_directory(app.static_folder, "laden.html")

    @app.route("/api/shop", methods=["GET"])
    @login_required_api
    def api_shop_public():
        db = get_db()
        uid = session["user_id"]
        user_row = db.users.find_one(
            {"_id": oid(uid)}, {"school": 1, "class_name": 1}
        )
        user_school = (user_row.get("school") if user_row else "") or ""
        user_class = _normalize_class_name((user_row.get("class_name") if user_row else "")) or ""
        rows = list(
            db.shop_items.find(
                {
                    "active": 1,
                    "$and": [
                        {"$or": [{"school": ""}, {"school": user_school}]},
                        {"$or": [{"class_name": ""}, {"class_name": user_class}]},
                    ],
                }
            ).sort([("sort_order", 1), ("_id", 1)])
        )
        bal = _user_points_sum(db, uid)
        return jsonify(
            items=[_row_to_item(r) for r in rows],
            points_balance=bal,
            smtp_configured=smtp_configured(),
        )

    @app.route("/api/shop/purchase", methods=["POST"])
    @login_required_api
    def api_shop_purchase():
        data = request.get_json(silent=True) or {}
        item_id = oid(data.get("item_id"))
        if item_id is None:
            return jsonify(error="invalid_item"), 400

        db = get_db()
        uid = session["user_id"]
        uname = session.get("username") or ""

        row = db.shop_items.find_one({"_id": item_id})
        if not row or not row["active"]:
            return jsonify(error="not_found"), 404
        user_row = db.users.find_one(
            {"_id": oid(uid)}, {"school": 1, "class_name": 1}
        )
        user_school = (user_row.get("school") if user_row else "") or ""
        user_class = _normalize_class_name((user_row.get("class_name") if user_row else "")) or ""
        item_school = (row["school"] or "").strip()
        item_class = _normalize_class_name(row["class_name"]) or ""
        if item_school and item_school != user_school:
            return jsonify(error="not_found"), 404
        if item_class and item_class != user_class:
            return jsonify(error="not_found"), 404
        cost = int(row["points_price"] or 0)
        if cost <= 0:
            return jsonify(error="not_purchasable"), 400

        try:
            bal = _user_points_sum(db, uid)
            if bal < cost:
                return jsonify(error="insufficient_points", balance=bal, cost=cost), 400
            if not _deduct_user_points(db, uid, cost, uid):
                return jsonify(error="deduct_failed"), 500
            now = datetime.now(timezone.utc)
            res = db.laden_purchases.insert_one(
                {
                    "user_id": oid(uid),
                    "username": uname,
                    "shop_item_id": item_id,
                    "item_title": row["title"],
                    "points_spent": cost,
                    "created_at": now,
                    "email_sent": 0,
                    "email_error": None,
                }
            )
            pid = res.inserted_id
        except Exception:
            return jsonify(error="database"), 500

        mail_ok = False
        mail_err = None
        try:
            sent, merr = _notify_teachers_laden(
                db, uname, row["title"], cost, now, user_school
            )
            mail_ok = bool(sent)
            mail_err = merr
        except OSError as ex:
            mail_err = str(ex)[:200]
        db.laden_purchases.update_one(
            {"_id": pid},
            {"$set": {"email_sent": 1 if mail_ok else 0, "email_error": mail_err}},
        )

        new_bal = _user_points_sum(db, uid)
        return jsonify(
            ok=True,
            points_balance=new_bal,
            mail_sent=mail_ok,
            mail_notice=_purchase_email_notice(mail_err) if not mail_ok else None,
        )

    @app.route("/api/admin/shop", methods=["GET"])
    @admin_api
    def admin_shop_list():
        db = get_db()
        filt = {}
        if not _has_full_read_access():
            filt["school"] = _session_school(db)
            if _is_teacher():
                teacher_class = _session_class(db)
                if not teacher_class:
                    return jsonify(items=[])
                filt["class_name"] = teacher_class
        rows = list(
            db.shop_items.find(filt).sort([("sort_order", 1), ("_id", 1)])
        )
        return jsonify(items=[_row_to_item(r) for r in rows])

    @app.route("/api/admin/shop", methods=["POST"])
    @admin_write_api
    def admin_shop_create():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title or len(title) > TITLE_MAX:
            return jsonify(error="invalid_title"), 400
        description = (data.get("description") or "").strip()
        if len(description) > DESC_MAX:
            return jsonify(error="invalid_description"), 400
        price_hint = (data.get("price_hint") or "").strip()
        if len(price_hint) > PRICE_MAX:
            return jsonify(error="invalid_price_hint"), 400
        db = get_db()
        school = _admin_item_school(db, data.get("school"))
        if len(school) > SCHOOL_MAX:
            return jsonify(error="invalid_school"), 400
        class_name = _admin_item_class(db, data.get("class_name"))
        if class_name is None:
            return jsonify(error="invalid_class"), 400
        if _is_teacher() and not class_name:
            return jsonify(error="forbidden"), 403
        try:
            points_price = int(data.get("points_price", 0))
        except (TypeError, ValueError):
            return jsonify(error="invalid_points_price"), 400
        if points_price < 0 or points_price > POINTS_PRICE_MAX:
            return jsonify(error="invalid_points_price"), 400
        try:
            sort_order = int(data.get("sort_order", 0))
        except (TypeError, ValueError):
            return jsonify(error="invalid_sort"), 400
        active = 1 if data.get("active") in (True, "true", "1", 1) else 0

        now = datetime.now(timezone.utc)
        res = db.shop_items.insert_one(
            {
                "title": title,
                "description": description,
                "price_hint": price_hint,
                "points_price": points_price,
                "school": school,
                "class_name": class_name,
                "sort_order": sort_order,
                "active": active,
                "updated_at": now,
            }
        )
        if school:
            db.schools.update_one(
                {"_id": school},
                {"$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        new_id = res.inserted_id
        row = db.shop_items.find_one({"_id": new_id})
        return jsonify(item=_row_to_item(row))

    @app.route("/api/admin/shop/<string:item_id>", methods=["PUT"])
    @admin_write_api
    def admin_shop_update(item_id):
        item_id = oid(item_id)
        if item_id is None:
            return jsonify(error="invalid_id"), 400
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title or len(title) > TITLE_MAX:
            return jsonify(error="invalid_title"), 400
        description = (data.get("description") or "").strip()
        if len(description) > DESC_MAX:
            return jsonify(error="invalid_description"), 400
        price_hint = (data.get("price_hint") or "").strip()
        if len(price_hint) > PRICE_MAX:
            return jsonify(error="invalid_price_hint"), 400
        db = get_db()
        school = _admin_item_school(db, data.get("school"))
        if len(school) > SCHOOL_MAX:
            return jsonify(error="invalid_school"), 400
        class_name = _admin_item_class(db, data.get("class_name"))
        if class_name is None:
            return jsonify(error="invalid_class"), 400
        if _is_teacher() and not class_name:
            return jsonify(error="forbidden"), 403
        try:
            points_price = int(data.get("points_price", 0))
        except (TypeError, ValueError):
            return jsonify(error="invalid_points_price"), 400
        if points_price < 0 or points_price > POINTS_PRICE_MAX:
            return jsonify(error="invalid_points_price"), 400
        try:
            sort_order = int(data.get("sort_order", 0))
        except (TypeError, ValueError):
            return jsonify(error="invalid_sort"), 400
        active = 1 if data.get("active") in (True, "true", "1", 1) else 0

        existing = db.shop_items.find_one(
            {"_id": item_id}, {"school": 1, "class_name": 1}
        )
        if existing is None:
            return jsonify(error="not_found"), 404
        if not _can_admin_access_item_scope(
            db, existing["school"] or "", existing["class_name"] or ""
        ):
            return jsonify(error="not_found"), 404
        now = datetime.now(timezone.utc)
        res = db.shop_items.update_one(
            {"_id": item_id},
            {
                "$set": {
                    "title": title,
                    "description": description,
                    "price_hint": price_hint,
                    "points_price": points_price,
                    "school": school,
                    "class_name": class_name,
                    "sort_order": sort_order,
                    "active": active,
                    "updated_at": now,
                }
            },
        )
        if school:
            db.schools.update_one(
                {"_id": school},
                {"$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        if res.matched_count != 1:
            return jsonify(error="not_found"), 404
        row = db.shop_items.find_one({"_id": item_id})
        return jsonify(item=_row_to_item(row))

    @app.route("/api/admin/shop/<string:item_id>", methods=["DELETE"])
    @admin_write_api
    def admin_shop_delete(item_id):
        item_id = oid(item_id)
        if item_id is None:
            return jsonify(error="invalid_id"), 400
        db = get_db()
        existing = db.shop_items.find_one(
            {"_id": item_id}, {"school": 1, "class_name": 1}
        )
        if existing is None or not _can_admin_access_item_scope(
            db, existing["school"] or "", existing["class_name"] or ""
        ):
            return jsonify(error="not_found"), 404
        res = db.shop_items.delete_one({"_id": item_id})
        if res.deleted_count != 1:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True)

    @app.route("/api/admin/laden-purchases", methods=["GET"])
    @admin_api
    def admin_laden_purchases():
        db = get_db()
        if not _has_full_read_access():
            ufilt = {"school": _session_school(db)}
            if _is_teacher():
                teacher_class = _session_class(db)
                if not teacher_class:
                    return jsonify(purchases=[])
                ufilt["class_name"] = teacher_class
            user_ids = [u["_id"] for u in db.users.find(ufilt, {"_id": 1})]
            purchase_filter = {"user_id": {"$in": user_ids}}
        else:
            purchase_filter = {}
        rows = list(
            db.laden_purchases.find(purchase_filter)
            .sort([("created_at", -1), ("_id", -1)])
            .limit(300)
        )
        return jsonify(
            purchases=[
                {
                    "id": str(r["_id"]),
                    "user_id": str(r["user_id"]),
                    "username": r["username"],
                    "shop_item_id": str(r["shop_item_id"]),
                    "item_title": r["item_title"],
                    "points_spent": int(r["points_spent"]),
                    "created_at": r["created_at"],
                    "email_sent": bool(r["email_sent"]),
                    "email_error": r["email_error"] or "",
                }
                for r in rows
            ]
        )

    @app.route("/api/admin/teachers", methods=["GET"])
    @admin_api
    def admin_teachers_list():
        db = get_db()
        filt = {}
        if not _has_full_read_access():
            filt["school"] = _session_school(db)
        rows = list(db.teacher_contacts.find(filt).sort("_id", 1))
        return jsonify(
            teachers=[
                {
                    "id": str(r["_id"]),
                    "email": r["email"],
                    "display_name": r["display_name"] or "",
                    "school": r["school"] or "",
                    "active": bool(r["active"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        )

    @app.route("/api/admin/teachers", methods=["POST"])
    @admin_write_api
    def admin_teachers_create():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        display_name = (data.get("display_name") or "").strip()[:120]
        if not email or "@" not in email or len(email) > 254:
            return jsonify(error="invalid_email"), 400
        db = get_db()
        school = _admin_item_school(db, data.get("school"))
        dup = db.teacher_contacts.find_one({"email": email})
        if dup:
            return jsonify(error="duplicate"), 409
        now = datetime.now(timezone.utc)
        res = db.teacher_contacts.insert_one(
            {
                "email": email,
                "display_name": display_name or None,
                "school": school,
                "active": 1,
                "created_at": now,
            }
        )
        if school:
            db.schools.update_one(
                {"_id": school},
                {"$setOnInsert": {"created_at": now}},
                upsert=True,
            )
        rid = res.inserted_id
        row = db.teacher_contacts.find_one({"_id": rid})
        return jsonify(
            teacher={
                "id": str(row["_id"]),
                "email": row["email"],
                "display_name": row["display_name"] or "",
                "school": row["school"] or "",
                "active": bool(row["active"]),
                "created_at": row["created_at"],
            }
        )

    @app.route("/api/admin/teachers/<string:tid>", methods=["DELETE"])
    @admin_write_api
    def admin_teachers_delete(tid):
        tid = oid(tid)
        if tid is None:
            return jsonify(error="invalid_id"), 400
        db = get_db()
        existing = db.teacher_contacts.find_one({"_id": tid}, {"school": 1})
        if existing is None or not _can_admin_access_school(db, existing["school"] or ""):
            return jsonify(error="not_found"), 404
        res = db.teacher_contacts.delete_one({"_id": tid})
        if res.deleted_count != 1:
            return jsonify(error="not_found"), 404
        return jsonify(ok=True)

    @app.route("/api/admin/teachers/<string:tid>", methods=["PUT"])
    @admin_write_api
    def admin_teachers_update(tid):
        tid = oid(tid)
        if tid is None:
            return jsonify(error="invalid_id"), 400
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        display_name = (data.get("display_name") or "").strip()[:120]
        active = 1 if data.get("active") in (True, "true", "1", 1) else 0
        if not email or "@" not in email or len(email) > 254:
            return jsonify(error="invalid_email"), 400
        db = get_db()
        school = _admin_item_school(db, data.get("school"))
        existing = db.teacher_contacts.find_one({"_id": tid}, {"school": 1})
        if existing is None or not _can_admin_access_school(db, existing["school"] or ""):
            return jsonify(error="not_found"), 404
        res = db.teacher_contacts.update_one(
            {"_id": tid},
            {
                "$set": {
                    "email": email,
                    "display_name": display_name or None,
                    "school": school,
                    "active": active,
                }
            },
        )
        if school:
            db.schools.update_one(
                {"_id": school},
                {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True,
            )
        if res.matched_count != 1:
            return jsonify(error="not_found"), 404
        row = db.teacher_contacts.find_one({"_id": tid})
        return jsonify(
            teacher={
                "id": str(row["_id"]),
                "email": row["email"],
                "display_name": row["display_name"] or "",
                "school": row["school"] or "",
                "active": bool(row["active"]),
                "created_at": row["created_at"],
            }
        )
